import os
import re
import time
import logging
import psycopg2
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# --- LOGLAMA ---
# Artık hatalar sessizce yutulmuyor; ne zaman/nerede bir kart parse edilemediyse
# konsola yazılıyor. "Yanlış veri" sorununu debug etmek için bu şart.
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("bebiio_scraper")

# SUPABASE BAĞLANTISI
# GÜVENLİK UYARISI: Şifreyi asla kod içine gömmeyin. Ortam değişkeninden okuyun
# ve bu şifreyi (bu dosya paylaşıldığı için) MUTLAKA değiştirin.
SUPABASE_DB_URL = os.environ.get(
    "SUPABASE_DB_URL",
    "postgresql://postgres.bbemkqegyvbktqjbjqrr:EgeKuzen2026@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"
)


def fiyati_temizle(fiyat_metni):
    if not fiyat_metni:
        return ""
    temiz = re.sub(r'[^\d,.]', '', fiyat_metni)
    temiz = temiz.strip('.,')
    if not temiz:
        return ""
    return temiz + " TL"


def resmi_temizle(img_el, base_url=""):
    """img etiketinden gerçek görsel URL'sini çıkarır.
    Çoğu site lazy-load yaptığı için src her zaman doğru değildir;
    data-src / srcset öncelikli kontrol edilir."""
    if not img_el:
        return ""
    for attr in ("data-src", "data-lazy-src", "src", "srcset"):
        val = img_el.get(attr)
        if val:
            # srcset "url1 1x, url2 2x" formatında olabilir, ilkini al
            url = val.split(",")[0].strip().split(" ")[0]
            if url.startswith("//"):
                url = "https:" + url
            elif url.startswith("/") and base_url:
                url = urljoin(base_url, url)
            return url
    return ""


def scroll_page(page):
    for _ in range(6):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(1)


def amazon_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.amazon.com.tr/s?k=bebek+bezi&i=baby&ref=nb_sb_noss_2"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = context.new_page()
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
                log.warning(f"[Amazon] Sayfaya gidilemedi: {e}")

            soup = BeautifulSoup(page.content(), 'html.parser')

            # ÖNEMLİ DÜZELTME: sadece gerçek arama sonucu kartlarını al.
            # Eski hali div[data-asin] idi; bu, kart içindeki "bunu alanlar
            # şunu da aldı" gibi iç içe mini-carousel'leri de yakalayıp
            # başlık/fiyat karışmasına (yanlış eşleşme) sebep oluyordu.
            cards = soup.select('div[data-component-type="s-search-result"]')
            if not cards:
                # Amazon düzen değiştirdiyse eski yönteme düş, ama uyar.
                log.warning("[Amazon] s-search-result bulunamadı, data-asin fallback kullanılıyor.")
                cards = soup.find_all("div", attrs={"data-asin": True})

            eklenen = 0
            for card in cards:
                try:
                    asin = card.get("data-asin")
                    if not asin:
                        continue
                    title_el = card.select_one("h2 span") or card.select_one("span.a-text-normal")
                    if not title_el or len(title_el.text) < 5:
                        continue
                    link_el = card.select_one(f"a[href*='/{asin}/']") or card.select_one("h2 a")
                    if not link_el:
                        continue

                    # ÖNEMLİ DÜZELTME: .a-text-price (üstü çizili/eski fiyat)
                    # içindeki whole/fraction'ı hariç tutuyoruz; sadece
                    # gerçek satış fiyatını alıyoruz.
                    price_box = card.select_one("span.a-price:not(.a-text-price)")
                    if not price_box:
                        log.info(f"[Amazon] Fiyat bulunamadı, atlanıyor: {title_el.text.strip()[:40]}")
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
                            "Ürün Adı": title_el.text.strip(), "Fiyat": temiz_fiyat,
                            "Ürün Linki": "https://www.amazon.com.tr" + link_el.get('href', ''),
                            "Resim": resim
                        })
                        eklenen += 1
                except Exception as e:
                    log.info(f"[Amazon] Kart parse hatası: {e}")
                    continue
            print(f"[Amazon TR] Sayfa {sayfa_no} üzerinden {eklenen} ürün yakalandı.")
        browser.close()
    return all_products


def trendyol_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.trendyol.com/bebek-bezi-x-c1363"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = context.new_page()
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}?pi={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[Trendyol] Sayfa {sayfa_no} taranıyor...")
            try:
                page.goto(url, timeout=60000)
                try:
                    page.wait_for_selector('.prc-box-dscntd', timeout=5000)
                except Exception:
                    log.info("[Trendyol] Fiyat kutusu selector'ı zaman aşımına uğradı (site class'ı değişmiş olabilir).")
                scroll_page(page)
                soup = BeautifulSoup(page.content(), 'html.parser')
                cards = soup.find_all('div', class_='p-card-wrppr')
                if not cards:
                    log.warning("[Trendyol] Hiç kart bulunamadı — site HTML yapısı değişmiş olabilir, selector güncellenmeli.")
                eklenen = 0
                for card in cards:
                    try:
                        # ÖNEMLİ DÜZELTME: kartın ilk <a> etiketi her zaman ana
                        # ürün linki olmayabilir (kampanya/rozet linki olabilir).
                        # Önce görsel/başlık kapsayıcısını içeren asıl linki dene.
                        link_el = card.select_one("a.p-card-chldrn-cntnr") or card.find('a', href=True)
                        price_el = card.find('div', class_='prc-box-dscntd') or card.find('div', class_='prc-box-sllng')
                        if not link_el or not price_el:
                            continue

                        title_div = card.find('div', class_='prdct-desc-cntnr-ttl')
                        if title_div and title_div.get('title'):
                            title = title_div.get('title').strip()
                        else:
                            brand_el = card.find('span', class_='prdct-desc-brnd')
                            name_el = card.find('span', class_='prdct-desc-cntnr-name')
                            title = ((brand_el.text.strip() + " " if brand_el else "") + (name_el.text.strip() if name_el else "")).strip()

                        temiz_fiyat = fiyati_temizle(price_el.text)

                        img_el = card.select_one("img")
                        resim = resmi_temizle(img_el, "https://www.trendyol.com")

                        if len(title) > 5 and temiz_fiyat:
                            all_products.append({
                                "Platform": "Trendyol", "Kategori": "Bebek Bezi",
                                "Ürün Adı": title, "Fiyat": temiz_fiyat,
                                "Ürün Linki": urljoin("https://www.trendyol.com", link_el['href']),
                                "Resim": resim
                            })
                            eklenen += 1
                    except Exception as e:
                        log.info(f"[Trendyol] Kart parse hatası: {e}")
                        continue
                print(f"[Trendyol] Sayfa {sayfa_no} üzerinden {eklenen} ürün yakalandı.")
            except Exception as e:
                log.warning(f"[Trendyol] Sayfa hatası: {e}")
        browser.close()
    return all_products


def n11_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.n11.com/bebek-bezi-ve-islak-mendil/bebek-bezi"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = context.new_page()
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}?pg={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[N11] Sayfa {sayfa_no} taranıyor...")
            try:
                page.goto(url, timeout=60000)
                try:
                    page.wait_for_selector('ins', timeout=5000)
                except Exception:
                    log.info("[N11] Fiyat selector'ı zaman aşımına uğradı.")
                scroll_page(page)
                soup = BeautifulSoup(page.content(), 'html.parser')
                cards = soup.find_all('li', class_='column')
                if not cards:
                    log.warning("[N11] Hiç kart bulunamadı — site HTML yapısı değişmiş olabilir.")
                eklenen = 0
                for card in cards:
                    try:
                        link_el = card.find('a', class_='plink')
                        price_el = card.find('ins') or card.find('span', class_='newPrice')
                        if not link_el or not price_el:
                            continue

                        title = link_el.get('title', '').strip()
                        temiz_fiyat = fiyati_temizle(price_el.text)

                        img_el = card.select_one("img")
                        resim = resmi_temizle(img_el, "https://www.n11.com")

                        # ÖNEMLİ DÜZELTME: href göreli (relative) gelebiliyordu,
                        # bu da bozuk linklere sebep oluyordu.
                        href = urljoin("https://www.n11.com", link_el.get('href', ''))

                        if len(title) > 10 and temiz_fiyat:
                            all_products.append({
                                "Platform": "N11", "Kategori": "Bebek Bezi",
                                "Ürün Adı": title, "Fiyat": temiz_fiyat,
                                "Ürün Linki": href, "Resim": resim
                            })
                            eklenen += 1
                    except Exception as e:
                        log.info(f"[N11] Kart parse hatası: {e}")
                        continue
                print(f"[N11] Sayfa {sayfa_no} üzerinden {eklenen} ürün yakalandı.")
            except Exception as e:
                log.warning(f"[N11] Sayfa hatası: {e}")
        browser.close()
    return all_products


def hepsiburada_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.hepsiburada.com/bebek-bezleri-c-60001049"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = context.new_page()
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}?sayfa={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[Hepsiburada] Sayfa {sayfa_no} taranıyor...")
            try:
                page.goto(url, timeout=60000)
                try:
                    page.wait_for_selector('[data-test-id="price-current-price"]', timeout=8000)
                except Exception:
                    log.info("[Hepsiburada] Fiyat selector'ı zaman aşımına uğradı.")
                scroll_page(page)

                # ÖNEMLİ DÜZELTME: görsel de aynı kart sınırı içinden,
                # başlık/fiyatla birlikte tek seferde çekiliyor. Bu sayede
                # görsel başka bir karta ait olmuyor.
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

                eklenen = 0
                for data in extracted_data:
                    try:
                        title = data.get("title", "")
                        raw_price = data.get("price", "")
                        href = data.get("link", "")
                        resim = data.get("image", "")

                        href = urljoin("https://www.hepsiburada.com", href)
                        if resim and resim.startswith("//"):
                            resim = "https:" + resim
                        elif resim and resim.startswith("/"):
                            resim = urljoin("https://www.hepsiburada.com", resim)

                        temiz_fiyat = fiyati_temizle(raw_price)

                        if len(title) > 5 and temiz_fiyat:
                            all_products.append({
                                "Platform": "Hepsiburada", "Kategori": "Bebek Bezi",
                                "Ürün Adı": title, "Fiyat": temiz_fiyat, "Ürün Linki": href,
                                "Resim": resim
                            })
                            eklenen += 1
                    except Exception as e:
                        log.info(f"[Hepsiburada] Kart parse hatası: {e}")
                        continue
                print(f"[Hepsiburada] Sayfa {sayfa_no} üzerinden {eklenen} ürün yakalandı.")
            except Exception as e:
                print(f"Hepsiburada Hata: {e}")
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
        toplam_urunler.extend(trendyol_tara(1))
        toplam_urunler.extend(amazon_tara(1))
        toplam_urunler.extend(n11_tara(1))
        toplam_urunler.extend(hepsiburada_tara(1))

        print(f"\n🎉 Tarama tamamlandı! Toplam {len(toplam_urunler)} ürün yakalandı. DB'ye yazılıyor...")
        save_to_db(toplam_urunler)
        print("✅ Görev başarıyla tamamlandı! Motor kapanıyor.")
    except Exception as e:
        print(f"❌ Motor çalışırken hata oluştu: {e}")