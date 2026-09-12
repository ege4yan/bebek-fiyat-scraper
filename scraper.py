import os
import re
import time
import json
import logging
from urllib.parse import urljoin

import psycopg2
import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

try:
    from playwright_stealth import stealth_sync
    STEALTH_VAR = True
except ImportError:
    STEALTH_VAR = False

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("bebiio_scraper")

SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")
if not SUPABASE_DB_URL:
    raise RuntimeError(
        "SUPABASE_DB_URL ortam değişkeni bulunamadı. "
        "Yerelde .env dosyasına, GitHub Actions'ta Secrets'a ekleyin."
    )

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Hepsiburada'nın bot-korumasının headless tarayıcı (Playwright) imzasına
# tepki verdiği, düz bir HTTP isteğine tepki vermediği gözlemlendi.
# Bu yüzden Hepsiburada için Playwright yerine sade requests kullanıyoruz.
HTTP_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
}

DEBUG_DIR = "debug_output"
os.makedirs(DEBUG_DIR, exist_ok=True)


def debug_snapshot(page, platform_name):
    """Kart bulunamadığında sayfanın o anki ekran görüntüsünü ve HTML'ini kaydeder.
    GitHub Actions'ta bu klasör artifact olarak indirilebiliyor (bkz. bebiio.yml).
    Bot koruması mı yoksa selector mı bozuldu, ayırt etmek için şart."""
    try:
        safe_name = platform_name.lower().replace(" ", "_")
        page.screenshot(path=f"{DEBUG_DIR}/{safe_name}.png", full_page=True)
        with open(f"{DEBUG_DIR}/{safe_name}.html", "w", encoding="utf-8") as f:
            f.write(page.content())
        log.warning(f"[{platform_name}] Debug görüntüsü/HTML'i {DEBUG_DIR}/{safe_name}.* içine kaydedildi.")
    except Exception as e:
        log.warning(f"[{platform_name}] Debug snapshot alınamadı: {e}")


def yeni_sayfa_olustur(context):
    page = context.new_page()
    if STEALTH_VAR:
        stealth_sync(page)
    return page


def fiyati_temizle(fiyat_metni):
    if not fiyat_metni:
        return ""
    temiz = re.sub(r'[^\d,.]', '', fiyat_metni).strip('.,')
    if not temiz:
        return ""
    return temiz + " TL"


def resmi_temizle(img_el, base_url=""):
    if not img_el:
        return ""
    for attr in ("data-src", "data-lazy-src", "src", "srcset"):
        val = img_el.get(attr)
        if val:
            url = val.split(",")[0].strip().split(" ")[0]
            if url.startswith("//"):
                url = "https:" + url
            elif url.startswith("/") and base_url:
                url = urljoin(base_url, url)
            return url
    return ""


def urun_gecerli_mi(baslik, kategori="Bebek Bezi"):
    """Kategoriye gore alakasiz urunleri eler. 'Bebek Bezi' kategorisinde
    diger bebek bakim urunlerini (mendil, krem vb.) bilerek disliyoruz;
    diger kategorilerde (Islak Mendil, Biberon, Mama, Emzik...) bu kisitlama
    gecerli degil, cunku aradigimiz zaten o urun turu."""
    if not baslik:
        return False
    b = baslik.lower()
    if kategori == "Bebek Bezi":
        yasaklilar = ['mendil', 'krem', 'havlu', 'şampuan', 'deterjan', 'sabun', 'ped',
                      'alt açma', 'losyon', 'emzik', 'biberon', 'yatak', 'örtü']
        return not any(y in b for y in yasaklilar)
    return True


def scroll_page(page, adim=6):
    for _ in range(adim):
        page.evaluate("window.scrollBy(0, 1200)")
        time.sleep(1)


def yeni_context(browser):
    return browser.new_context(viewport={'width': 1920, 'height': 1080}, user_agent=UA, locale="tr-TR")


# ==========================================
# 1. AMAZON — çalışıyor, dokunulmadı
# ==========================================
def amazon_tara(max_sayfa=1, url=None, kategori="Bebek Bezi"):
    all_products = []
    base_url = url or "https://www.amazon.com.tr/s?k=bebek+bezi&i=baby&ref=nb_sb_noss_2"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50)
        context = yeni_context(browser)
        page = yeni_sayfa_olustur(context)
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}&page={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[Amazon TR] Sayfa {sayfa_no} taranıyor...")
            try:
                page.goto("https://www.amazon.com.tr", timeout=45000)
                time.sleep(2)
                page.goto(url, timeout=60000)
                time.sleep(3)
                scroll_page(page)
            except Exception as e:
                log.warning(f"[Amazon] Hata: {e}")

            soup = BeautifulSoup(page.content(), 'html.parser')
            cards = soup.select('div[data-component-type="s-search-result"]')
            if not cards:
                cards = soup.find_all("div", attrs={"data-asin": True})
            if not cards:
                debug_snapshot(page, f"Amazon TR_{kategori}")

            eklenen = 0
            for card in cards:
                try:
                    title_el = card.select_one("h2 span") or card.select_one("span.a-text-normal")
                    if not title_el or len(title_el.text) < 5:
                        continue
                    baslik = title_el.text.strip()
                    if not urun_gecerli_mi(baslik, kategori):
                        continue

                    link_el = card.select_one("h2 a") or card.select_one(f"a[href*='/{card.get('data-asin')}/']")
                    price_box = card.select_one("span.a-price:not(.a-text-price)")
                    if not link_el or not price_box:
                        continue

                    whole = price_box.select_one(".a-price-whole")
                    fraction = price_box.select_one(".a-price-fraction")
                    if not whole:
                        continue

                    fiyat_metni = f"{whole.text.strip().replace(',', '').replace('.', '')},{fraction.text.strip() if fraction else '00'}"
                    temiz_fiyat = fiyati_temizle(fiyat_metni)
                    img_el = card.select_one("img.s-image")
                    resim = resmi_temizle(img_el, "https://www.amazon.com.tr")

                    if temiz_fiyat:
                        all_products.append({
                            "Platform": "Amazon TR", "Kategori": kategori,
                            "Ürün Adı": baslik, "Fiyat": temiz_fiyat,
                            "Ürün Linki": "https://www.amazon.com.tr" + link_el.get('href', ''),
                            "Resim": resim
                        })
                        eklenen += 1
                except Exception:
                    continue
            print(f"[Amazon TR] Sayfa {sayfa_no} üzerinden {eklenen} net ürün yakalandı.")
        browser.close()
    return all_products


# ==========================================
# 2. TRENDYOL — HTTP'den Playwright'a geri döndürüldü
# ==========================================
def trendyol_tara(max_sayfa=1, url=None, kategori="Bebek Bezi"):
    all_products = []
    base_url = url or "https://www.trendyol.com/bebek-bezi-x-c1363"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50)
        context = yeni_context(browser)
        page = yeni_sayfa_olustur(context)
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}?pi={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[Trendyol] Sayfa {sayfa_no} taranıyor...")
            try:
                page.goto(url, timeout=60000)
                try:
                    page.wait_for_selector('.product-card', timeout=10000)
                except Exception:
                    log.info("[Trendyol] Selector zaman aşımına uğradı.")
                scroll_page(page)
                soup = BeautifulSoup(page.content(), 'html.parser')
                # GÜNCEL SELECTOR (2026-09): Trendyol artık kartı a.product-card
                # olarak render ediyor; kartın kendisi zaten ürün linki.
                cards = soup.select('.product-card')
                if not cards:
                    log.warning("[Trendyol] Hiç kart bulunamadı.")
                    debug_snapshot(page, f"Trendyol_{kategori}")
                eklenen = 0
                for card in cards:
                    try:
                        href = card.get('href')
                        if not href:
                            continue

                        brand_el = card.select_one('.product-brand')
                        name_el = card.select_one('.product-name')
                        title = ((brand_el.text.strip() + " " if brand_el else "") + (name_el.text.strip() if name_el else "")).strip()
                        if not urun_gecerli_mi(title, kategori):
                            continue

                        price_box = card.select_one('.product-card-price')
                        if not price_box:
                            continue
                        # İndirimli üründe gerçek fiyat data-testid="price-value" içinde,
                        # normal üründe .single-price .price-section içinde.
                        price_el = price_box.select_one('[data-testid="price-value"]') \
                            or price_box.select_one('.price-section')
                        if not price_el:
                            continue
                        temiz_fiyat = fiyati_temizle(price_el.text)

                        img_el = card.select_one("img")
                        resim = resmi_temizle(img_el, "https://www.trendyol.com")

                        if len(title) > 5 and temiz_fiyat:
                            all_products.append({
                                "Platform": "Trendyol", "Kategori": kategori,
                                "Ürün Adı": title, "Fiyat": temiz_fiyat,
                                "Ürün Linki": urljoin("https://www.trendyol.com", href),
                                "Resim": resim
                            })
                            eklenen += 1
                    except Exception:
                        continue
                print(f"[Trendyol] Sayfa {sayfa_no} üzerinden {eklenen} ürün yakalandı.")
            except Exception as e:
                log.warning(f"[Trendyol] Sayfa hatası: {e}")
        browser.close()
    return all_products


# ==========================================
# 3. N11 — HTTP'den Playwright'a geri döndürüldü
# ==========================================
def n11_tara(max_sayfa=1, url=None, kategori="Bebek Bezi"):
    all_products = []
    base_url = url or "https://www.n11.com/bebek-bezi-ve-islak-mendil/bebek-bezi"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50)
        context = yeni_context(browser)
        page = yeni_sayfa_olustur(context)
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}?pg={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[N11] Sayfa {sayfa_no} taranıyor...")
            try:
                page.goto(url, timeout=60000)
                try:
                    page.wait_for_selector('.product-item', timeout=10000)
                except Exception:
                    log.info("[N11] Selector zaman aşımına uğradı.")
                scroll_page(page)
                soup = BeautifulSoup(page.content(), 'html.parser')
                # GÜNCEL SELECTOR (2026-09): a.product-item kartın kendisi, tam URL zaten href'te.
                cards = soup.select('.product-item')
                if not cards:
                    log.warning("[N11] Hiç kart bulunamadı.")
                    debug_snapshot(page, f"N11_{kategori}")
                eklenen = 0
                for card in cards:
                    try:
                        href = card.get('href')
                        title_el = card.select_one('.product-item-title')
                        price_area = card.select_one('.price-area')
                        if not href or not title_el or not price_area:
                            continue

                        title = title_el.text.strip()
                        if not urun_gecerli_mi(title, kategori):
                            continue

                        # Güncel fiyat h3.price-currency içinde; .old-price üstü çizili eski fiyat.
                        price_el = price_area.select_one('h3.price-currency')
                        if not price_el:
                            continue
                        temiz_fiyat = fiyati_temizle(price_el.text)

                        img_el = card.select_one("img.listing-items-image") or card.select_one("img")
                        resim = resmi_temizle(img_el, "https://www.n11.com")

                        if len(title) > 10 and temiz_fiyat:
                            all_products.append({
                                "Platform": "N11", "Kategori": kategori,
                                "Ürün Adı": title, "Fiyat": temiz_fiyat,
                                "Ürün Linki": href, "Resim": resim
                            })
                            eklenen += 1
                    except Exception:
                        continue
                print(f"[N11] Sayfa {sayfa_no} üzerinden {eklenen} ürün yakalandı.")
            except Exception as e:
                log.warning(f"[N11] Sayfa hatası: {e}")
        browser.close()
    return all_products


# ==========================================
# 4. HEPSİBURADA (Görünür Tarayıcı - Anti-Datadome)
# GÜNCEL YÖNTEM: Sayfanın <script> içine gömdüğü tam ürün JSON'unu
# ('STATE': {"data":{"products":[...]}}) doğrudan ayrıştırıyoruz.
# Bu, DOM/CSS selector kırılganlığından tamamen bağımsız ve çok daha
# güvenilir — gerçek "Sepete özel" indirimli fiyatı da net veriyor.
# ==========================================
def _dengeli_json_cikar(metin, baslangic_idx):
    """baslangic_idx'teki '{' karakterinden başlayıp, parantez dengesini
    takip ederek JSON nesnesinin tamamını (kapanış '}' dahil) döndürür."""
    derinlik = 0
    for i in range(baslangic_idx, len(metin)):
        c = metin[i]
        if c == '{':
            derinlik += 1
        elif c == '}':
            derinlik -= 1
            if derinlik == 0:
                return metin[baslangic_idx:i + 1]
    return None


def hepsiburada_tara(max_sayfa=1, url=None, kategori="Bebek Bezi"):
    all_products = []
    base_url = url or "https://www.hepsiburada.com/bebek-bezleri-c-60001049"
    with sync_playwright() as p:
        # NÜKLEER SEÇENEK: headless=False. Datadome görünür açılan
        # tarayıcıları gerçek insan sanıp geçiriyor.
        browser = p.chromium.launch(
            headless=False,
            slow_mo=50,
            args=['--disable-blink-features=AutomationControlled', '--start-maximized']
        )
        context = browser.new_context(no_viewport=True, user_agent=UA, locale="tr-TR")
        page = yeni_sayfa_olustur(context)

        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}?sayfa={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[Hepsiburada] Sayfa {sayfa_no} taranıyor (Görünür Tarayıcı ile)...")
            try:
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
                time.sleep(5)
                scroll_page(page)

                html = page.content()
                marker = "'STATE': {\"data\":{\"products\":"
                idx = html.find(marker)
                eklenen = 0

                if idx == -1:
                    log.warning("[Hepsiburada] Ürün JSON'u sayfada bulunamadı.")
                    debug_snapshot(page, f"Hepsiburada_{kategori}")
                else:
                    json_start = idx + len("'STATE': ")
                    json_str = _dengeli_json_cikar(html, json_start)
                    try:
                        state = json.loads(json_str)
                        products = state.get("data", {}).get("products", [])
                    except Exception as e:
                        log.warning(f"[Hepsiburada] JSON parse hatası: {e}")
                        products = []
                        debug_snapshot(page, f"Hepsiburada_{kategori}")

                    for product in products:
                        try:
                            variants = product.get("variantList") or []
                            if not variants:
                                continue
                            variant = variants[0]
                            title = variant.get("name", "")
                            if not title or not urun_gecerli_mi(title, kategori):
                                continue

                            listing = variant.get("listing") or {}
                            price_info = listing.get("priceInfo") or {}
                            campaign = listing.get("campaignPriceInfo")
                            # "Sepete özel" gibi bir kampanya fiyatı varsa (genelde
                            # daha düşük ve gerçek satış fiyatı) onu, yoksa normal
                            # listeleme fiyatını kullan.
                            if campaign and campaign.get("discountedPrice"):
                                fiyat_deger = campaign["discountedPrice"]
                            else:
                                fiyat_deger = price_info.get("price")
                            if fiyat_deger is None:
                                continue
                            temiz_fiyat = f"{fiyat_deger:.2f}".replace('.', ',') + " TL"

                            href = urljoin("https://www.hepsiburada.com", variant.get("url", ""))

                            resim = ""
                            images = product.get("images") or []
                            if images:
                                resim = images[0].get("link", "").replace("{size}", "240x240")

                            if len(title) > 5:
                                all_products.append({
                                    "Platform": "Hepsiburada", "Kategori": kategori,
                                    "Ürün Adı": title, "Fiyat": temiz_fiyat,
                                    "Ürün Linki": href, "Resim": resim
                                })
                                eklenen += 1
                        except Exception:
                            continue

                    if eklenen == 0:
                        debug_snapshot(page, f"Hepsiburada_{kategori}")

                print(f"[Hepsiburada] Sayfa {sayfa_no} üzerinden {eklenen} ürün yakalandı.")
            except Exception as e:
                log.warning(f"[Hepsiburada] Sayfa hatası: {e}")
        browser.close()
    return all_products

# ==========================================
# 5. EBEBEK — İLK TASLAK (doğrulanmadı, debug ile netleştirilecek)
# ==========================================
def ebebek_tara(max_sayfa=1, url=None, kategori="Bebek Bezi"):
    all_products = []
    base_url = url or "https://www.e-bebek.com/bebek-bezleri-c10111"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50)
        context = yeni_context(browser)
        page = yeni_sayfa_olustur(context)
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}?page={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[eBebek] Sayfa {sayfa_no} taranıyor...")
            try:
                page.goto(url, timeout=60000)
                try:
                    page.wait_for_selector('div.product-item', timeout=10000)
                except Exception:
                    log.info("[eBebek] Selector zaman aşımına uğradı.")
                scroll_page(page, adim=12)
                soup = BeautifulSoup(page.content(), 'html.parser')
                # GÜNCEL SELECTOR (2026-09, test edilip doğrulandı: 48/48)
                cards = soup.select('div.product-item')
                if not cards:
                    log.warning("[eBebek] Hiç kart bulunamadı.")
                    debug_snapshot(page, f"eBebek_{kategori}")
                eklenen = 0
                for card in cards:
                    try:
                        a = card.select_one('a.product-item-anchor')
                        h2 = card.select_one('h2.product-item__brand')
                        price_box = card.select_one('div.price-box.price-box--list')
                        if not a or not h2 or not price_box:
                            continue
                        title = h2.get_text(' ', strip=True)
                        if not urun_gecerli_mi(title, kategori):
                            continue
                        # NOT: eBebek'te 3 farklı fiyat katmanı olabilir:
                        # 1) .cart-price .price -> "Sepette" fiyatı (varsa en düşük, gerçek satış fiyatı)
                        # 2) .discounted-price strong -> siteye özel indirimli fiyat
                        # 3) .old-price -> üstü çizili orijinal fiyat (indirim yoksa asıl fiyat budur)
                        price_el = (price_box.select_one('.cart-price .price')
                                    or price_box.select_one('.discounted-price strong')
                                    or price_box.select_one('.old-price'))
                        if not price_el:
                            continue
                        temiz_fiyat = fiyati_temizle(price_el.get_text(' ', strip=True))
                        img_el = card.select_one("img")
                        resim = resmi_temizle(img_el, "https://www.e-bebek.com")
                        href = urljoin("https://www.e-bebek.com", a.get('href', ''))
                        if len(title) > 5 and temiz_fiyat:
                            all_products.append({
                                "Platform": "eBebek", "Kategori": kategori,
                                "Ürün Adı": title, "Fiyat": temiz_fiyat,
                                "Ürün Linki": href, "Resim": resim
                            })
                            eklenen += 1
                    except Exception:
                        continue
                if eklenen == 0:
                    debug_snapshot(page, f"eBebek_{kategori}")
                else:
                    debug_snapshot(page, f"eBebek_basarili_{kategori}")
                print(f"[eBebek] Sayfa {sayfa_no} üzerinden {eklenen} ürün yakalandı.")
            except Exception as e:
                log.warning(f"[eBebek] Sayfa hatası: {e}")
        browser.close()
    return all_products


# ==========================================
# 6. PAZARAMA — İLK TASLAK (doğrulanmadı, debug ile netleştirilecek)
# ==========================================
def pazarama_tara(max_sayfa=1, url=None, kategori="Bebek Bezi"):
    all_products = []
    base_url = url or "https://www.pazarama.com/bebek-bezi-k-K01057"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50)
        context = yeni_context(browser)
        page = yeni_sayfa_olustur(context)
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}?page={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[Pazarama] Sayfa {sayfa_no} taranıyor...")
            try:
                page.goto(url, timeout=60000)
                try:
                    page.wait_for_selector('div.product-card', timeout=10000)
                except Exception:
                    log.info("[Pazarama] Selector zaman aşımına uğradı.")
                scroll_page(page)
                soup = BeautifulSoup(page.content(), 'html.parser')
                # GÜNCEL SELECTOR (2026-09, test edilip doğrulandı: 60/60)
                cards = soup.select('div.product-card')
                if not cards:
                    log.warning("[Pazarama] Hiç kart bulunamadı.")
                    debug_snapshot(page, f"Pazarama_{kategori}")
                eklenen = 0
                for card in cards:
                    try:
                        h2 = card.select_one('h2')
                        price_box = card.select_one('.product-card__price')
                        a = card.select_one('a[href]')
                        if not h2 or not price_box or not a:
                            continue
                        title = h2.get_text(strip=True)
                        if not urun_gecerli_mi(title, kategori):
                            continue
                        # "Sepette" fiyatı varsa gerçek satış fiyatı odur;
                        # yoksa üstteki <p> etiketindeki fiyatı kullan.
                        sepette_label = price_box.find('span', string=lambda s: s and 'Sepette' in s)
                        price_el = sepette_label.find_next_sibling('div') if sepette_label else None
                        if not price_el:
                            price_el = price_box.find('p')
                        if not price_el:
                            continue
                        temiz_fiyat = fiyati_temizle(price_el.get_text(strip=True))
                        img_el = card.select_one("img")
                        resim = resmi_temizle(img_el, "https://www.pazarama.com")
                        href = urljoin("https://www.pazarama.com", a.get('href', ''))
                        if len(title) > 5 and temiz_fiyat:
                            all_products.append({
                                "Platform": "Pazarama", "Kategori": kategori,
                                "Ürün Adı": title, "Fiyat": temiz_fiyat,
                                "Ürün Linki": href, "Resim": resim
                            })
                            eklenen += 1
                    except Exception:
                        continue
                if eklenen == 0:
                    debug_snapshot(page, f"Pazarama_{kategori}")
                print(f"[Pazarama] Sayfa {sayfa_no} üzerinden {eklenen} ürün yakalandı.")
            except Exception as e:
                log.warning(f"[Pazarama] Sayfa hatası: {e}")
        browser.close()
    return all_products


# ==========================================
# 7. İDEFİX — İLK TASLAK (doğrulanmadı, debug ile netleştirilecek)
# NOT: idefix esasen kitap/kırtasiye odaklı; bebek bezi stoku çok sınırlı
# veya hiç olmayabilir. 0 ürün gelmesi burada selector hatası olmayabilir.
# ==========================================
def idefix_tara(max_sayfa=1, url=None, kategori="Bebek Bezi"):
    all_products = []
    base_url = url or "https://www.idefix.com/bebek-bezleri-c-880181288"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50)
        context = yeni_context(browser)
        page = yeni_sayfa_olustur(context)
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}?page={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[idefix] Sayfa {sayfa_no} taranıyor...")
            try:
                page.goto(url, timeout=60000)
                try:
                    page.wait_for_selector('h3.line-clamp-2', timeout=10000)
                except Exception:
                    log.info("[idefix] Selector zaman aşımına uğradı.")
                scroll_page(page)
                soup = BeautifulSoup(page.content(), 'html.parser')
                # GÜNCEL SELECTOR (2026-09, test edilip doğrulandı: 24/24)
                # idefix tamamen dinamik/utility CSS class'ları kullanıyor,
                # sabit bir "kart" class'ı yok. Bu yüzden başlangıç noktası
                # olarak ürün başlığını (h3.line-clamp-2) alıp, ondan yukarı
                # doğru gerçek kart kutusunu (group+cursor-pointer div) buluyoruz.
                titles = soup.select('h3.line-clamp-2')
                if not titles:
                    log.warning("[idefix] Hiç kart bulunamadı.")
                    debug_snapshot(page, f"idefix_{kategori}")
                eklenen = 0
                for title_el in titles:
                    try:
                        card = title_el.find_parent(
                            lambda tag: tag.name == 'div' and tag.has_attr('class')
                            and 'group' in tag['class'] and 'cursor-pointer' in tag['class']
                        )
                        if not card:
                            continue
                        a = card.find('a', href=True)
                        price_span = card.select_one('span.lg\\:text-title-sm')
                        if not a or not price_span:
                            continue
                        title = title_el.get_text(' ', strip=True)
                        if not urun_gecerli_mi(title, kategori):
                            continue
                        # price_span sadece kuruş kısmını içerebilir (örn. "00"),
                        # tam fiyat parent'ında ("819,00TL" gibi) birlikte duruyor.
                        temiz_fiyat = fiyati_temizle(price_span.parent.get_text(strip=True))
                        img_el = card.select_one('img[src^="https"]')
                        resim = resmi_temizle(img_el, "https://www.idefix.com")
                        href = urljoin("https://www.idefix.com", a.get('href', ''))
                        if len(title) > 5 and temiz_fiyat:
                            all_products.append({
                                "Platform": "idefix", "Kategori": kategori,
                                "Ürün Adı": title, "Fiyat": temiz_fiyat,
                                "Ürün Linki": href, "Resim": resim
                            })
                            eklenen += 1
                    except Exception:
                        continue
                print(f"[idefix] Sayfa {sayfa_no} üzerinden {eklenen} ürün yakalandı.")
            except Exception as e:
                log.warning(f"[idefix] Sayfa hatası: {e}")
        browser.close()
    return all_products


# ==========================================
# 8. PTTAVM — İLK TASLAK (doğrulanmadı, debug ile netleştirilecek)
# ==========================================
def pttavm_tara(max_sayfa=1, url=None, kategori="Bebek Bezi"):
    all_products = []
    base_url = url or "https://www.pttavm.com/arama?q=bebek+bezi"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50)
        context = yeni_context(browser)
        page = yeni_sayfa_olustur(context)
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}&page={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[PTTAVM] Sayfa {sayfa_no} taranıyor...")
            try:
                page.goto(url, timeout=60000)
                try:
                    page.wait_for_selector('article.article__i36EQ', timeout=10000)
                except Exception:
                    log.info("[PTTAVM] Selector zaman aşımına uğradı.")
                scroll_page(page)
                soup = BeautifulSoup(page.content(), 'html.parser')
                # GÜNCEL SELECTOR (2026-09, test edilip doğrulandı: 48/48)
                # NOT: Bu class isimleri CSS-Modules hash'i içeriyor
                # (örn. __i36EQ) — PTTAVM yeni bir build yayınlarsa bu hash
                # değişebilir ve selector'lar tekrar kırılabilir.
                cards = soup.select('article.article__i36EQ')
                if not cards:
                    log.warning("[PTTAVM] Hiç kart bulunamadı.")
                    debug_snapshot(page, f"PTTAVM_{kategori}")
                eklenen = 0
                for card in cards:
                    try:
                        a = card.select_one('a.card__dfYph')
                        title_el = card.select_one('h2.name__yWPWa')
                        if not a or not title_el:
                            continue
                        title = title_el.get_text(strip=True)
                        if not urun_gecerli_mi(title, kategori):
                            continue
                        # İndirimli üründe gerçek fiyat specialPriceValue içinde,
                        # değilse priceRow'un tamamı tek fiyattır.
                        price_el = card.select_one('div.specialPriceValue__HPhRC') \
                            or card.select_one('div.priceRow__PGsNE')
                        if not price_el:
                            continue
                        temiz_fiyat = fiyati_temizle(price_el.get_text(' ', strip=True))
                        # Rozet/badge resmiyle karışmasın diye ürün görselini
                        # figure.imageWrapper içinden alıyoruz.
                        fig = card.select_one('figure.imageWrapper__R7Rwz')
                        img_el = fig.select_one('img') if fig else card.select_one('img')
                        resim = resmi_temizle(img_el, "https://www.pttavm.com")
                        href = urljoin("https://www.pttavm.com", a.get('href', ''))
                        if len(title) > 5 and temiz_fiyat:
                            all_products.append({
                                "Platform": "PTTAVM", "Kategori": kategori,
                                "Ürün Adı": title, "Fiyat": temiz_fiyat,
                                "Ürün Linki": href, "Resim": resim
                            })
                            eklenen += 1
                    except Exception:
                        continue
                print(f"[PTTAVM] Sayfa {sayfa_no} üzerinden {eklenen} ürün yakalandı.")
            except Exception as e:
                log.warning(f"[PTTAVM] Sayfa hatası: {e}")
        browser.close()
    return all_products


def save_to_db(all_products):
    if not all_products:
        print("❌ Kaydedilecek ürün bulunamadı.")
        return
    try:
        conn = psycopg2.connect(SUPABASE_DB_URL)
        cur = conn.cursor()
        eklenen = 0
        for urun in all_products:
            try:
                query = """
                    INSERT INTO urunler (platform, kategori, urun_adi, fiyat, urun_linki, resim_url)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (urun_linki)
                    DO UPDATE SET fiyat = EXCLUDED.fiyat, urun_adi = EXCLUDED.urun_adi, resim_url = EXCLUDED.resim_url;
                """
                cur.execute(query, (urun["Platform"], urun["Kategori"], urun["Ürün Adı"], urun["Fiyat"], urun["Ürün Linki"], urun.get("Resim", "")))
                eklenen += 1
            except Exception as e:
                log.warning(f"DB insert hatası ({urun.get('Ürün Linki')}): {e}")
                conn.rollback()
        conn.commit()
        cur.close()
        conn.close()
        print(f"\n✅ ZAFER! Toplam {eklenen} ürün başarıyla Supabase'e kaydedildi!")
    except Exception as e:
        print(f"❌ Veritabanı bağlantı hatası: {e}")


# ==========================================
# KATEGORİ TANIMLARI
# Yeni bir kategori eklemek için buraya bir satır eklemek yeterli.
# url=None olan siteler için henüz doğrulanmış bir kategori sayfası
# bulunamadı — o kombinasyon otomatik atlanır, hata vermez.
# ==========================================
KATEGORILER = {
    "Bebek Bezi": {
        "amazon": "https://www.amazon.com.tr/s?k=bebek+bezi&i=baby&ref=nb_sb_noss_2",
        "trendyol": "https://www.trendyol.com/bebek-bezi-x-c1363",
        "n11": "https://www.n11.com/bebek-bezi-ve-islak-mendil/bebek-bezi",
        "hepsiburada": "https://www.hepsiburada.com/bebek-bezleri-c-60001049",
        "ebebek": "https://www.e-bebek.com/bebek-bezleri-c10111",
        "pazarama": "https://www.pazarama.com/bebek-bezi-k-K01057",
        "idefix": "https://www.idefix.com/bebek-bezleri-c-880181288",
        "pttavm": "https://www.pttavm.com/arama?q=bebek+bezi",
    },
    "Islak Mendil": {
        # Trendyol, N11, eBebek: web aramasıyla dogrulanmış gerçek kategori URL'leri.
        "amazon": "https://www.amazon.com.tr/s?k=islak+mendil&i=baby&ref=nb_sb_noss_2",
        "trendyol": "https://www.trendyol.com/islak-mendil-x-c101411",
        "n11": "https://www.n11.com/bebek-bezi-ve-islak-mendil/islak-mendil-havlu",
        # Hepsiburada: URL kullanıcı tarafından doğrulandı ama site Akamai ile
        # kalıcı olarak bloklu (bkz. önceki tarama) — bu yüzden None bırakıldı.
        # Gerçek URL: https://www.hepsiburada.com/islak-mendiller-c-301175
        "hepsiburada": None,
        "ebebek": "https://www.e-bebek.com/islak-mendil-c10115",
        "pazarama": "https://www.pazarama.com/islak-mendil-havlu-k-K01058",
        "idefix": "https://www.idefix.com/bebek-islak-mendilleri-c-880155320",
        "pttavm": "https://www.pttavm.com/arama?q=islak+mendil",  # arama tabanlı, muhtemelen çalışır
    },
    "Biberon": {
        "amazon": "https://www.amazon.com.tr/s?k=biberon&i=baby&ref=nb_sb_noss_2",
        "trendyol": "https://www.trendyol.com/biberon-emzik-x-c103755",
        "n11": "https://www.n11.com/biberon-ve-aksesuarlari/bebek-biberon",
        "hepsiburada": "https://www.hepsiburada.com/biberonlar-c-301172",  # Akamai engeli - calismasi beklenmiyor ama URL kayitli
        "ebebek": "https://www.e-bebek.com/biberon-c4025",
        "pazarama": "https://www.pazarama.com/biberon-ve-aksesuarlari-k-K01149",
        "idefix": None,  # idefix'te ayri biberon kategorisi bulunamadi
        "pttavm": "https://www.pttavm.com/biberon-c-1260",
    },
    "Emzik": {
        "amazon": "https://www.amazon.com.tr/s?k=emzik&i=baby&ref=nb_sb_noss_2",
        "trendyol": "https://www.trendyol.com/emzik-x-c165850",
        "n11": "https://www.n11.com/beslenme-ve-mama-sandalyesi/emzik-ve-aksesuarlari",
        "hepsiburada": "https://www.hepsiburada.com/yalanci-emzik-c-297822",
        "ebebek": "https://www.e-bebek.com/silikon-emzik-c3804",
        "pazarama": "https://www.pazarama.com/yalanci-emzik-ve-aksesuarlari-k-K01157",
        "idefix": None,
        "pttavm": "https://www.pttavm.com/emzik-ve-aksesuarlari-c-1258",
    },
    "Bebek Maması": {
        "amazon": "https://www.amazon.com.tr/s?k=bebek+mamasi&i=baby&ref=nb_sb_noss_2",
        "trendyol": "https://www.trendyol.com/bebek-mamalari-x-c103753",
        "n11": "https://www.n11.com/beslenme-ve-mama-sandalyesi/bebek-mamasi",
        "hepsiburada": "https://www.hepsiburada.com/bebek-mamalari-c-301163",
        "ebebek": "https://www.e-bebek.com/bebek-mamalari-c3846",
        "pazarama": "https://www.pazarama.com/bebek-mamalari-k-K01203",
        "idefix": None,
        "pttavm": "https://www.pttavm.com/arama?q=bebek+mamasi",  # pttavm'de ayri kategori bulunamadi, arama kullanildi
    },
    "Bebek Arabası": {
        "amazon": "https://www.amazon.com.tr/Pusetler-ve-Bebek-Arabalari/b?ie=UTF8&node=12793218031",
        "trendyol": "https://www.trendyol.com/bebek-arabasi-puset-x-c103735",
        "n11": "https://www.n11.com/bebek-arabalari",
        "hepsiburada": "https://www.hepsiburada.com/bebek-arabasi-pusetleri-c-305668",
        "ebebek": "https://www.e-bebek.com/bebek-arabalari-c10110",
        "pazarama": "https://www.pazarama.com/bebek-arabalari-ve-tasima-urunleri-k-K01017",
        "idefix": "https://www.idefix.com/bebek-arabalari-c-1107122920",
        "pttavm": "https://www.pttavm.com/travel-sistem-bebek-arabasi-c-4146",  # pttavm birden fazla alt tur var, en genel olani secildi
    },
    "Oto Koltuğu": {
        "amazon": "https://www.amazon.com.tr/s?k=oto+koltuğu&i=baby",
        "trendyol": "https://www.trendyol.com/oto-koltugu-x-c103738",
        "n11": "https://www.n11.com/oto-koltugu-ve-ana-kucagi/oto-koltugu",
        "hepsiburada": "https://www.hepsiburada.com/ana-kucagi-oto-koltuklari-c-305661",  # HB'de ana kucagi ile birlesik
        "ebebek": "https://www.e-bebek.com/bebek-oto-koltugu-c4219",
        "pazarama": "https://www.pazarama.com/oto-koltugu-ve-ana-kucagi-k-K01187",  # Pazarama'da ana kucagi ile birlesik
        "idefix": "https://www.idefix.com/oto-koltugu-ve-aksesuarlari-c-1107456210",
        "pttavm": None,
    },
    "Ana Kucağı": {
        "amazon": "https://www.amazon.com.tr/s?k=bebek+ana+kucağı&i=baby",
        "trendyol": "https://www.trendyol.com/ana-kucagi-x-c103731",
        "n11": "https://www.n11.com/oto-koltugu-ve-ana-kucagi/ev-tipi-ana-kucagi",
        "hepsiburada": "https://www.hepsiburada.com/ana-kucagi-oto-koltuklari-c-305661",  # HB'de oto koltugu ile birlesik
        "ebebek": "https://www.e-bebek.com/ana-kucagi-c4550",
        "pazarama": "https://www.pazarama.com/oto-koltugu-ve-ana-kucagi-k-K01187",  # Pazarama'da oto koltugu ile birlesik
        "idefix": "https://www.idefix.com/ana-kucagi-c-110710079",
        "pttavm": None,
    },
    "Kanguru & Portbebe": {
        "amazon": "https://www.amazon.com.tr/s?k=bebek+kanguru&i=baby",
        "trendyol": "https://www.trendyol.com/portbebe-kanguru-sling-x-c103740",
        "n11": "https://www.n11.com/oto-koltugu-ve-ana-kucagi/kanguru",
        "hepsiburada": "https://www.hepsiburada.com/bebek-tasima-c-80383003",
        "ebebek": "https://www.e-bebek.com/bebek-tasima-gerecleri-c10114",
        "pazarama": None,  # Pazarama'da ayri kategori bulunamadi
        "idefix": "https://www.idefix.com/kanguru-portbebe-c-1107113920",
        "pttavm": None,
    },
    "Mama Sandalyesi": {
        "amazon": "https://www.amazon.com.tr/s?k=mama+sandalyesi&i=baby",
        "trendyol": "https://www.trendyol.com/mama-sandalyesi-x-c1111",
        "n11": "https://www.n11.com/beslenme-ve-mama-sandalyesi/mama-sandalyesi",
        "hepsiburada": "https://www.hepsiburada.com/mama-sandalyeleri-c-301132",
        "ebebek": "https://www.e-bebek.com/mama-sandalyesi-c3818",
        "pazarama": "https://www.pazarama.com/mama-sandalyesi-ve-aksesuarlari-k-K01184",
        "idefix": None,
        "pttavm": None,
    },
    "Yürüteç": {
        "amazon": "https://www.amazon.com.tr/s?k=bebek+yürüteç&i=baby",
        "trendyol": "https://www.trendyol.com/yurutec-x-c103741",
        "n11": "https://www.n11.com/yurutec-ve-yurume-yardimcilari/yurutec",
        "hepsiburada": None,
        "ebebek": "https://www.e-bebek.com/yurutec-c3734",
        "pazarama": "https://www.pazarama.com/yurutec-ve-yurume-yardimcilari-k-K01193",
        "idefix": None,
        "pttavm": None,
    },
    "Bebek Giyim": {
        "amazon": "https://www.amazon.com.tr/s?k=yenidoğan+bebek+kıyafetleri&i=baby",
        "trendyol": None,  # TODO: genel kategori linki dogrulanmadi
        "n11": "https://www.n11.com/bebek-giyim/erkek-bebek",  # N11'de cinsiyete gore ayrilmis, tek link secildi
        "hepsiburada": "https://www.hepsiburada.com/bebek-kiyafetleri-giyim-c-60007347",
        "ebebek": "https://www.e-bebek.com/yenidogan-bebek-giyim-c3742",
        "pazarama": "https://www.pazarama.com/bebek-giyim-k-K01059",
        "idefix": None,
        "pttavm": "https://www.pttavm.com/bebek-giyim-c-1178",
    },
    "Bebek Banyo Ürünleri": {
        "amazon": "https://www.amazon.com.tr/s?k=bebek+banyo+ürünleri&i=baby",
        "trendyol": None,
        "n11": None,
        "hepsiburada": "https://www.hepsiburada.com/bebek-banyo-c-80383032",
        "ebebek": "https://www.e-bebek.com/bebek-banyo-urunleri-c4042",
        "pazarama": None,
        "idefix": "https://www.idefix.com/bebek-dus-banyo-c-1101237920",
        "pttavm": None,
    },
    "Bebek Bakım Çantası": {
        "amazon": "https://www.amazon.com.tr/s?k=bebek+bakim+cantasi&i=baby",
        "trendyol": "https://www.trendyol.com/bebek-bakim-cantasi-x-c1014",
        "n11": None,
        "hepsiburada": "https://www.hepsiburada.com/bebek-bakim-cantalari-c-301143",
        "ebebek": "https://www.e-bebek.com/cantalar-c10102",
        "pazarama": None,
        "idefix": None,
        "pttavm": None,
    },
    "Buhar Makinesi": {
        "amazon": None,
        "trendyol": "https://www.trendyol.com/bebek-buhar-makinesi-y-s3612",
        "n11": None,
        "hepsiburada": "https://www.hepsiburada.com/buhar-makineleri-c-303171",
        "ebebek": None,
        "pazarama": None,
        "idefix": None,
        "pttavm": None,
    },
    "Göğüs Pompası": {
        "amazon": "https://www.amazon.com.tr/s?k=bebek+süt+pompası&i=baby",
        "trendyol": "https://www.trendyol.com/gogus-pompalari-x-c103760",
        "n11": "https://www.n11.com/emzirme-urunleri/gogus-pompalari",
        "hepsiburada": "https://www.hepsiburada.com/emzirme-urunleri-c-23020380",  # HB'de tum emzirme urunleri birlesik
        "ebebek": "https://www.e-bebek.com/sut-pompasi-c3789",
        "pazarama": "https://www.pazarama.com/gogus-pompasi-k-K01164",
        "idefix": None,
        "pttavm": None,
    },
    "Göğüs Pedi": {
        "amazon": None,
        "trendyol": "https://www.trendyol.com/gogus-pedleri-koruyucular-x-c103759",
        "n11": "https://www.n11.com/emzirme-urunleri/gogus-pedleri-koruyucular",
        "hepsiburada": None,
        "ebebek": "https://www.e-bebek.com/gogus-pedi-c3942",
        "pazarama": "https://www.pazarama.com/gogus-pedi-ve-koruyuculari-k-K01163",
        "idefix": None,
        "pttavm": None,
    },
    "Göğüs Kremi": {
        "amazon": "https://www.amazon.com.tr/s?k=göğüs+kremi&i=baby",
        "trendyol": "https://www.trendyol.com/gogus-ucu-kremi-x-c103780",
        "n11": "https://www.n11.com/emzirme-urunleri/gogus-kremi",
        "hepsiburada": None,
        "ebebek": "https://www.e-bebek.com/gogus-kremi-c3944",
        "pazarama": "https://www.pazarama.com/gogus-ucu-kremi-k-K01165",
        "idefix": None,
        "pttavm": None,
    },
    "Süt Saklama Poşeti": {
        "amazon": None,
        "trendyol": None,
        "n11": "https://www.n11.com/emzirme-urunleri/sut-saklama-poset-ve-kaplari",
        "hepsiburada": None,
        "ebebek": "https://www.e-bebek.com/sut-saklama-poseti-ve-kabi-c3796",
        "pazarama": "https://www.pazarama.com/sut-saklama-poseti-kabi-k-K01167",
        "idefix": None,
        "pttavm": None,
    },
    "Emzirme Önlüğü": {
        "amazon": "https://www.amazon.com.tr/s?k=emzirme+önlükleri&i=baby",
        "trendyol": "https://www.trendyol.com/emzirme-onlugu-y-s5605",
        "n11": "https://www.n11.com/emzirme-urunleri/emzirme-yastigi-ve-ortuleri",
        "hepsiburada": None,
        "ebebek": "https://www.e-bebek.com/emzirme-onlugu-c3955",
        "pazarama": "https://www.pazarama.com/emzirme-onlugu-ortusu-k-K01160",
        "idefix": None,
        "pttavm": None,
    },
    "Mama Hazırlayıcı": {
        "amazon": None,
        "trendyol": None,
        "n11": None,
        "hepsiburada": "https://www.hepsiburada.com/mama-hazirlayicilar-c-302888",
        "ebebek": "https://www.e-bebek.com/bebek-mama-hazirlayici-c4267",
        "pazarama": "https://www.pazarama.com/mama-hazirlayici-k-K01154",
        "idefix": None,
        "pttavm": None,
    },
    "Biberon Isıtıcı & Sterilizatör": {
        "amazon": None,
        "trendyol": "https://www.trendyol.com/biberon-isitici-sterilizator-x-c103757",
        "n11": "https://www.n11.com/biberon-ve-aksesuarlari/biberon-isiticilari",
        "hepsiburada": "https://www.hepsiburada.com/biberon-isiticilar-sterilizatorler-c-301166",
        "ebebek": "https://www.e-bebek.com/biberon-isitici-c4021",
        "pazarama": "https://www.pazarama.com/biberon-isitici-ve-sterilizator-k-K01148",
        "idefix": None,
        "pttavm": "https://www.pttavm.com/biberon-mama-isitici-c-1261",
    },
    "Bebek Termosu & Alıştırma Bardağı": {
        "amazon": None,
        "trendyol": "https://www.trendyol.com/alistirma-bardaklari-x-c103756",
        "n11": "https://www.n11.com/biberon-ve-aksesuarlari/termos-ve-alistirma-bardaklari",
        "hepsiburada": "https://www.hepsiburada.com/bebek-termosu-kap-c-10413",
        "ebebek": "https://www.e-bebek.com/termal-saklama-termosu-c3782",
        "pazarama": "https://www.pazarama.com/bebek-termosu-k-K01147",
        "idefix": "https://www.idefix.com/bebek-matara-suluk-c-110210643",
        "pttavm": None,
    },
    "Mama Önlüğü & Kaşık": {
        "amazon": None,
        "trendyol": "https://www.trendyol.com/mama-onlugu-x-c103765",
        "n11": "https://www.n11.com/beslenme-ve-mama-sandalyesi/mama-tabagi-ve-kasik",
        "hepsiburada": None,
        "ebebek": "https://www.e-bebek.com/bebek-onlukleri-c4196",
        "pazarama": "https://www.pazarama.com/mama-onlugu-k-K01155",
        "idefix": "https://www.idefix.com/bebek-mama-onlukleri-c-110210928",
        "pttavm": None,
    },
    "Bebek Telsizi & Kamera": {
        "amazon": "https://www.amazon.com.tr/s?k=bebek+telsizi&i=baby",
        "trendyol": None,
        "n11": "https://www.n11.com/bebek-guvenlik/bebek-telsizi-ve-kamera",
        "hepsiburada": "https://www.hepsiburada.com/bebek-telsizi-c-301154",
        "ebebek": "https://www.e-bebek.com/kamerali-bebek-telsizi-c3885",
        "pazarama": "https://www.pazarama.com/bebek-telsizi-k-K01092",
        "idefix": "https://www.idefix.com/bebek-telsizi-ve-kamerasi-c-1103516940",
        "pttavm": None,
    },
    "Beşik & Park Yatak": {
        "amazon": None,
        "trendyol": "https://www.trendyol.com/besik-x-c104511",
        "n11": "https://www.n11.com/bebek-odasi-ve-park-yatak/besik-park-yatak-salincak",
        "hepsiburada": "https://www.hepsiburada.com/bebek-besikleri-c-60002070",
        "ebebek": "https://www.e-bebek.com/besikler-c7050",
        "pazarama": "https://www.pazarama.com/besik-park-yatak-salincak-k-K01134",
        "idefix": "https://www.idefix.com/bebek-besik-c-110510238",
        "pttavm": "https://www.pttavm.com/bebek-besikleri-c-1269",
    },
    "Bebek Yatakları": {
        "amazon": "https://www.amazon.com.tr/s?k=bebek+yatakları&i=baby",
        "trendyol": "https://www.trendyol.com/bebek-yatak-x-c144368",
        "n11": None,
        "hepsiburada": "https://www.hepsiburada.com/bebek-yataklari-c-23011486",
        "ebebek": "https://www.e-bebek.com/yataklar-c7100",
        "pazarama": None,
        "idefix": None,
        "pttavm": None,
    },
    "Bebek Odası Mobilyaları": {
        "amazon": None,
        "trendyol": "https://www.trendyol.com/bebek-odasi-takimi-x-c105325",
        "n11": "https://www.n11.com/bebek-odasi-ve-park-yatak/bebek-odasi-mobilya",
        "hepsiburada": "https://www.hepsiburada.com/bebek-odasi-mobilyalari-c-23012961",
        "ebebek": "https://www.e-bebek.com/dolaplar-c7060",  # eBebek'te birden fazla mobilya alt kategorisi var, dolaplar temsili secildi
        "pazarama": "https://www.pazarama.com/bebek-odasi-mobilya-k-K01114",
        "idefix": "https://www.idefix.com/bebek-odasi-mobilya-c-1105105550",
        "pttavm": "https://www.pttavm.com/bebek-mobilyasi-c-1266",
    },
    "Bebek Odası Tekstili": {
        "amazon": None,
        "trendyol": "https://www.trendyol.com/bebek-cocuk-nevresim-takimi-x-c105583",
        "n11": "https://www.n11.com/bebek-odasi-ve-park-yatak/bebek-odasi-tekstil",
        "hepsiburada": "https://www.hepsiburada.com/bebek-tekstili-c-80381044",
        "ebebek": None,
        "pazarama": "https://www.pazarama.com/bebek-odasi-tekstil-k-K01121",
        "idefix": "https://www.idefix.com/bebek-koruyucu-tekstil-c-110375728",
        "pttavm": None,
    },
    "Ev & Bebek Güvenlik Ürünleri": {
        "amazon": None,
        "trendyol": None,
        "n11": "https://www.n11.com/bebek-guvenlik/ev-guvenlik-urunleri",
        "hepsiburada": "https://www.hepsiburada.com/evde-guvenlik-c-80381020",
        "ebebek": "https://www.e-bebek.com/bebek-guvenlik-kapisi-c4341",  # eBebek'te birden fazla guvenlik alt kategorisi var, temsili secildi
        "pazarama": "https://www.pazarama.com/ev-guvenlik-urunleri-k-K01093",
        "idefix": "https://www.idefix.com/bebek-emniyet-kilitleri-ve-muhafazalari-c-110310424",
        "pttavm": None,
    },
    "Alt Açma Örtüsü": {
        "amazon": "https://www.amazon.com.tr/s?k=alt+acma+ortusu&i=baby",
        "trendyol": None,
        "n11": "https://www.n11.com/bebek-bezi-ve-islak-mendil/alt-acma-pedi-ve-minderi",
        "hepsiburada": "https://www.hepsiburada.com/bebek-alt-acma-setleri-c-23020713",
        "ebebek": "https://www.e-bebek.com/bebek-alt-acma-ortusu-c4521",
        "pazarama": "https://www.pazarama.com/alt-acma-ortusu-k-K01056",
        "idefix": None,  # idefix'te bez ile birlesik (bebek-bezi-ve-alt-acma), ayri deger uretmez
        "pttavm": "https://www.pttavm.com/alt-acma-pedi-c-1176",
    },
    "Bebek Şampuanı": {
        "amazon": None,
        "trendyol": "https://www.trendyol.com/bebek-sampuani-x-c105562",
        "n11": None,
        "hepsiburada": "https://www.hepsiburada.com/bebek-sampuanlari-c-301173",
        "ebebek": None,
        "pazarama": None,
        "idefix": "https://www.idefix.com/bebek-sac-bakim-c-1101567270",
        "pttavm": None,
    },
    "Bebek Krem & Yağları": {
        "amazon": None,
        "trendyol": "https://www.trendyol.com/bebek-krem-yaglar-x-c103769",
        "n11": None,
        "hepsiburada": "https://www.hepsiburada.com/bebek-pisik-kremi-yaglari-c-23021010",
        "ebebek": None,
        "pazarama": None,
        "idefix": "https://www.idefix.com/bebek-cilt-bakimi-c-1101837660",
        "pttavm": None,
    },
    "Ateş Ölçer": {
        "amazon": None,
        "trendyol": None,
        "n11": None,
        "hepsiburada": "https://www.hepsiburada.com/ates-olcerler-c-80483224",
        "ebebek": None,
        "pazarama": None,
        "idefix": "https://www.idefix.com/bebek-saglik-c-1101102720",
        "pttavm": None,
    },
    # Sırada: Anne Bakım Ürünleri, Oyuncaklar, Hamile Giyim
    # ve idefix'in bakım/temizlik alt kategorileri gibi henüz eklenmemiş kalemler.
}

SITE_FONKSIYONLARI = {
    "amazon": amazon_tara,
    "trendyol": trendyol_tara,
    "n11": n11_tara,
    "hepsiburada": hepsiburada_tara,
    "ebebek": ebebek_tara,
    "pazarama": pazarama_tara,
    "idefix": idefix_tara,
    "pttavm": pttavm_tara,
}

if __name__ == "__main__":
    print("🚀 Bebiio Kusursuz Fiyat Motoru Başlatıldı!\n")
    try:
        toplam_urunler = []
        for kategori_adi, site_urlleri in KATEGORILER.items():
            print(f"\n{'='*50}\n📂 KATEGORİ: {kategori_adi}\n{'='*50}")
            for site_adi, url in site_urlleri.items():
                if url is None:
                    print(f"⏭️  {site_adi}: '{kategori_adi}' için doğrulanmış URL yok, atlanıyor.")
                    continue
                fonksiyon = SITE_FONKSIYONLARI[site_adi]
                try:
                    toplam_urunler.extend(fonksiyon(1, url=url, kategori=kategori_adi))
                except Exception as e:
                    print(f"❌ {site_adi} / {kategori_adi} taramasında hata: {e}")

        print(f"\n🎉 Tarama tamamlandı! Toplam {len(toplam_urunler)} ürün yakalandı. DB'ye yazılıyor...")
        save_to_db(toplam_urunler)
        print("✅ Görev başarıyla tamamlandı! Motor kapanıyor.")
    except Exception as e:
        print(f"❌ Motor çalışırken hata oluştu: {e}")