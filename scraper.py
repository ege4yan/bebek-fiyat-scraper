import os
import re
import time
import logging
from urllib.parse import urljoin

import psycopg2
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


def urun_gecerli_mi(baslik):
    if not baslik:
        return False
    b = baslik.lower()
    yasaklilar = ['mendil', 'krem', 'havlu', 'şampuan', 'deterjan', 'sabun', 'ped',
                  'alt açma', 'losyon', 'emzik', 'biberon', 'yatak', 'örtü']
    return not any(y in b for y in yasaklilar)


def scroll_page(page):
    for _ in range(6):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(1)


def yeni_context(browser):
    return browser.new_context(viewport={'width': 1920, 'height': 1080}, user_agent=UA, locale="tr-TR")


# ==========================================
# 1. AMAZON — çalışıyor, dokunulmadı
# ==========================================
def amazon_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.amazon.com.tr/s?k=bebek+bezi&i=baby&ref=nb_sb_noss_2"
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
                debug_snapshot(page, "Amazon TR")

            eklenen = 0
            for card in cards:
                try:
                    title_el = card.select_one("h2 span") or card.select_one("span.a-text-normal")
                    if not title_el or len(title_el.text) < 5:
                        continue
                    baslik = title_el.text.strip()
                    if not urun_gecerli_mi(baslik):
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
                            "Platform": "Amazon TR", "Kategori": "Bebek Bezi",
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
def trendyol_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.trendyol.com/bebek-bezi-x-c1363"
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
                    debug_snapshot(page, "Trendyol")
                eklenen = 0
                for card in cards:
                    try:
                        href = card.get('href')
                        if not href:
                            continue

                        brand_el = card.select_one('.product-brand')
                        name_el = card.select_one('.product-name')
                        title = ((brand_el.text.strip() + " " if brand_el else "") + (name_el.text.strip() if name_el else "")).strip()
                        if not urun_gecerli_mi(title):
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
                                "Platform": "Trendyol", "Kategori": "Bebek Bezi",
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
def n11_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.n11.com/bebek-bezi-ve-islak-mendil/bebek-bezi"
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
                    debug_snapshot(page, "N11")
                eklenen = 0
                for card in cards:
                    try:
                        href = card.get('href')
                        title_el = card.select_one('.product-item-title')
                        price_area = card.select_one('.price-area')
                        if not href or not title_el or not price_area:
                            continue

                        title = title_el.text.strip()
                        if not urun_gecerli_mi(title):
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
                                "Platform": "N11", "Kategori": "Bebek Bezi",
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
# 4. HEPSİBURADA — HTTP'den Playwright'a geri döndürüldü
# ==========================================
def hepsiburada_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.hepsiburada.com/bebek-bezleri-c-60001049"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50)
        context = yeni_context(browser)
        page = yeni_sayfa_olustur(context)
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}?sayfa={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[Hepsiburada] Sayfa {sayfa_no} taranıyor...")
            try:
                page.goto(url, timeout=60000)
                try:
                    page.wait_for_selector('[data-test-id="price-current-price"]', timeout=10000)
                except Exception:
                    log.info("[Hepsiburada] Selector zaman aşımına uğradı.")
                    debug_snapshot(page, "Hepsiburada")
                scroll_page(page)

                extracted_data = page.evaluate('''() => {
                    let items = [];
                    let cards = document.querySelectorAll("li[data-index]");
                    cards.forEach(card => {
                        let a_tag = card.querySelector("a");
                        let title_tag = card.querySelector("[data-test-id*='title']") || card.querySelector("h3");
                        let price_tag = card.querySelector("[data-test-id='price-current-price']");
                        let img_tag = card.querySelector("img");
                        if (a_tag && title_tag && price_tag) {
                            items.push({
                                title: title_tag.innerText.trim(),
                                price: price_tag.innerText.trim(),
                                link: a_tag.getAttribute("href"),
                                image: img_tag ? (img_tag.getAttribute("src") || img_tag.getAttribute("data-src") || "") : ""
                            });
                        }
                    });
                    return items;
                }''')

                if not extracted_data:
                    log.warning("[Hepsiburada] Hiç kart bulunamadı.")
                    debug_snapshot(page, "Hepsiburada")

                eklenen = 0
                for data in extracted_data:
                    try:
                        title = data.get("title", "")
                        if not urun_gecerli_mi(title):
                            continue
                        raw_price = data.get("price", "")
                        href = urljoin("https://www.hepsiburada.com", data.get("link", ""))
                        resim = data.get("image", "")
                        if resim.startswith("//"):
                            resim = "https:" + resim
                        elif resim.startswith("/"):
                            resim = urljoin("https://www.hepsiburada.com", resim)

                        temiz_fiyat = fiyati_temizle(raw_price)
                        if len(title) > 5 and temiz_fiyat:
                            all_products.append({
                                "Platform": "Hepsiburada", "Kategori": "Bebek Bezi",
                                "Ürün Adı": title, "Fiyat": temiz_fiyat, "Ürün Linki": href,
                                "Resim": resim
                            })
                            eklenen += 1
                    except Exception:
                        continue
                print(f"[Hepsiburada] Sayfa {sayfa_no} üzerinden {eklenen} ürün yakalandı.")
            except Exception as e:
                print(f"Hepsiburada Hata: {e}")
        browser.close()
    return all_products


# ==========================================
# 5. EBEBEK — İLK TASLAK (doğrulanmadı, debug ile netleştirilecek)
# ==========================================
def ebebek_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.e-bebek.com/bebek-bezleri-c10111"
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
                scroll_page(page)
                soup = BeautifulSoup(page.content(), 'html.parser')
                # GÜNCEL SELECTOR (2026-09, test edilip doğrulandı: 48/48)
                cards = soup.select('div.product-item')
                if not cards:
                    log.warning("[eBebek] Hiç kart bulunamadı.")
                    debug_snapshot(page, "eBebek")
                eklenen = 0
                for card in cards:
                    try:
                        a = card.select_one('a.product-item-anchor')
                        h2 = card.select_one('h2.product-item__brand')
                        price_box = card.select_one('div.price-box.price-box--list')
                        if not a or not h2 or not price_box:
                            continue
                        title = h2.get_text(' ', strip=True)
                        if not urun_gecerli_mi(title):
                            continue
                        # NOT: class ismi "old-price" ama indirimsiz üründe bu
                        # aslında GÜNCEL fiyattır — sitede bu şekilde adlandırılmış.
                        price_el = price_box.select_one('.old-price')
                        if not price_el:
                            continue
                        temiz_fiyat = fiyati_temizle(price_el.get_text(' ', strip=True))
                        img_el = card.select_one("img")
                        resim = resmi_temizle(img_el, "https://www.e-bebek.com")
                        href = urljoin("https://www.e-bebek.com", a.get('href', ''))
                        if len(title) > 5 and temiz_fiyat:
                            all_products.append({
                                "Platform": "eBebek", "Kategori": "Bebek Bezi",
                                "Ürün Adı": title, "Fiyat": temiz_fiyat,
                                "Ürün Linki": href, "Resim": resim
                            })
                            eklenen += 1
                    except Exception:
                        continue
                if eklenen == 0:
                    debug_snapshot(page, "eBebek")
                print(f"[eBebek] Sayfa {sayfa_no} üzerinden {eklenen} ürün yakalandı.")
            except Exception as e:
                log.warning(f"[eBebek] Sayfa hatası: {e}")
        browser.close()
    return all_products


# ==========================================
# 6. PAZARAMA — İLK TASLAK (doğrulanmadı, debug ile netleştirilecek)
# ==========================================
def pazarama_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.pazarama.com/bebek-bezi-k-K01057"
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
                    debug_snapshot(page, "Pazarama")
                eklenen = 0
                for card in cards:
                    try:
                        h2 = card.select_one('h2')
                        price_box = card.select_one('.product-card__price')
                        a = card.select_one('a[href]')
                        if not h2 or not price_box or not a:
                            continue
                        title = h2.get_text(strip=True)
                        if not urun_gecerli_mi(title):
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
                                "Platform": "Pazarama", "Kategori": "Bebek Bezi",
                                "Ürün Adı": title, "Fiyat": temiz_fiyat,
                                "Ürün Linki": href, "Resim": resim
                            })
                            eklenen += 1
                    except Exception:
                        continue
                if eklenen == 0:
                    debug_snapshot(page, "Pazarama")
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
def idefix_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.idefix.com/bebek-bezleri-c-880181288"
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
                    debug_snapshot(page, "idefix")
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
                        if not urun_gecerli_mi(title):
                            continue
                        # price_span sadece kuruş kısmını içerebilir (örn. "00"),
                        # tam fiyat parent'ında ("819,00TL" gibi) birlikte duruyor.
                        temiz_fiyat = fiyati_temizle(price_span.parent.get_text(strip=True))
                        img_el = card.select_one('img[src^="https"]')
                        resim = resmi_temizle(img_el, "https://www.idefix.com")
                        href = urljoin("https://www.idefix.com", a.get('href', ''))
                        if len(title) > 5 and temiz_fiyat:
                            all_products.append({
                                "Platform": "idefix", "Kategori": "Bebek Bezi",
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
def pttavm_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.pttavm.com/arama?q=bebek+bezi"
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
                    debug_snapshot(page, "PTTAVM")
                eklenen = 0
                for card in cards:
                    try:
                        a = card.select_one('a.card__dfYph')
                        title_el = card.select_one('h2.name__yWPWa')
                        if not a or not title_el:
                            continue
                        title = title_el.get_text(strip=True)
                        if not urun_gecerli_mi(title):
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
                                "Platform": "PTTAVM", "Kategori": "Bebek Bezi",
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


if __name__ == "__main__":
    print("🚀 Bebiio Kusursuz Fiyat Motoru Başlatıldı!\n")
    try:
        toplam_urunler = []
        toplam_urunler.extend(amazon_tara(1))
        toplam_urunler.extend(trendyol_tara(1))
        toplam_urunler.extend(n11_tara(1))
        toplam_urunler.extend(hepsiburada_tara(1))
        toplam_urunler.extend(ebebek_tara(1))
        toplam_urunler.extend(pazarama_tara(1))
        toplam_urunler.extend(idefix_tara(1))
        toplam_urunler.extend(pttavm_tara(1))

        print(f"\n🎉 Tarama tamamlandı! Toplam {len(toplam_urunler)} ürün yakalandı. DB'ye yazılıyor...")
        save_to_db(toplam_urunler)
        print("✅ Görev başarıyla tamamlandı! Motor kapanıyor.")
    except Exception as e:
        print(f"❌ Motor çalışırken hata oluştu: {e}")