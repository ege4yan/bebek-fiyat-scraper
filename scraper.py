import os
import re
import time
import logging
import psycopg2
import requests
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("bebiio_scraper")

SUPABASE_DB_URL = "postgresql://postgres.bbemkqegyvbktqjbjqrr:EgeKuzen2026@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"

# HTTP İstekleri için normal insan kimliği (Bunu görünce Cloudflare genelde izin verir)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive"
}

def fiyati_temizle(fiyat_metni):
    if not fiyat_metni: return ""
    temiz = re.sub(r'[^\d,.]', '', fiyat_metni).strip('.,')
    if not temiz: return ""
    return temiz + " TL"

def resmi_temizle(img_el, base_url=""):
    if not img_el: return ""
    for attr in ("data-src", "data-lazy-src", "src", "srcset"):
        val = img_el.get(attr)
        if val:
            url = val.split(",")[0].strip().split(" ")[0]
            if url.startswith("//"): url = "https:" + url
            elif url.startswith("/") and base_url: url = urljoin(base_url, url)
            return url
    return ""

def urun_gecerli_mi(baslik):
    if not baslik: return False
    b = baslik.lower()
    yasaklilar = ['mendil', 'krem', 'havlu', 'şampuan', 'deterjan', 'sabun', 'ped', 'alt açma', 'losyon', 'emzik', 'biberon', 'yatak', 'örtü']
    for y in yasaklilar:
        if y in b: return False
    return True

def scroll_page(page):
    for _ in range(6):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(1)

# ==========================================
# 1. AMAZON (PLAYWRIGHT İLE DEVAM - ÇALIŞIYOR)
# ==========================================
def amazon_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.amazon.com.tr/s?k=bebek+bezi&i=baby&ref=nb_sb_noss_2"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080}, user_agent=HEADERS["User-Agent"])
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
            except Exception as e: log.warning(f"[Amazon] Hata: {e}")

            soup = BeautifulSoup(page.content(), 'html.parser')
            cards = soup.select('div[data-component-type="s-search-result"]')
            if not cards: cards = soup.find_all("div", attrs={"data-asin": True})

            eklenen = 0
            for card in cards:
                try:
                    title_el = card.select_one("h2 span") or card.select_one("span.a-text-normal")
                    if not title_el or len(title_el.text) < 5: continue
                    baslik = title_el.text.strip()
                    if not urun_gecerli_mi(baslik): continue

                    link_el = card.select_one("h2 a") or card.select_one(f"a[href*='/{card.get('data-asin')}/']")
                    price_box = card.select_one("span.a-price:not(.a-text-price)")
                    if not link_el or not price_box: continue
                    
                    whole = price_box.select_one(".a-price-whole")
                    fraction = price_box.select_one(".a-price-fraction")
                    if not whole: continue

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
                except: continue
            print(f"[Amazon TR] Sayfa {sayfa_no} üzerinden {eklenen} net ürün yakalandı.")
        browser.close()
    return all_products

# ==========================================
# 2. TRENDYOL, N11, HEPSİBURADA (SESSİZ HTTP İSTEĞİ)
# ==========================================
def trendyol_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.trendyol.com/bebek-bezi-x-c1363"
    for sayfa_no in range(1, max_sayfa + 1):
        url = f"{base_url}?pi={sayfa_no}" if sayfa_no > 1 else base_url
        print(f"\n[Trendyol] Sayfa {sayfa_no} HTTP ile taranıyor...")
        try:
            response = requests.get(url, headers=HEADERS, timeout=20)
            soup = BeautifulSoup(response.text, 'html.parser')
            cards = soup.find_all('div', class_='p-card-wrppr')
            eklenen = 0
            for card in cards:
                try:
                    link_el = card.select_one("a.p-card-chldrn-cntnr") or card.find('a', href=True)
                    price_el = card.find('div', class_='prc-box-dscntd') or card.find('div', class_='prc-box-sllng')
                    if not link_el or not price_el: continue

                    title_div = card.find('div', class_='prdct-desc-cntnr-ttl')
                    if title_div and title_div.get('title'): title = title_div.get('title').strip()
                    else:
                        brand_el = card.find('span', class_='prdct-desc-brnd')
                        name_el = card.find('span', class_='prdct-desc-cntnr-name')
                        title = ((brand_el.text.strip() + " " if brand_el else "") + (name_el.text.strip() if name_el else "")).strip()

                    if not urun_gecerli_mi(title): continue

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
                except: continue
            print(f"[Trendyol] Sayfa {sayfa_no} üzerinden {eklenen} ürün yakalandı.")
        except Exception as e: print(f"[Trendyol] HTTP Hata: {e}")
    return all_products

def n11_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.n11.com/bebek-bezi-ve-islak-mendil/bebek-bezi"
    for sayfa_no in range(1, max_sayfa + 1):
        url = f"{base_url}?pg={sayfa_no}" if sayfa_no > 1 else base_url
        print(f"\n[N11] Sayfa {sayfa_no} HTTP ile taranıyor...")
        try:
            response = requests.get(url, headers=HEADERS, timeout=20)
            soup = BeautifulSoup(response.text, 'html.parser')
            cards = soup.find_all('li', class_='column')
            eklenen = 0
            for card in cards:
                try:
                    link_el = card.find('a', class_='plink')
                    price_el = card.find('ins') or card.find('span', class_='newPrice')
                    if not link_el or not price_el: continue

                    title = link_el.get('title', '').strip()
                    if not urun_gecerli_mi(title): continue

                    temiz_fiyat = fiyati_temizle(price_el.text)
                    img_el = card.select_one("img")
                    resim = resmi_temizle(img_el, "https://www.n11.com")
                    href = urljoin("https://www.n11.com", link_el.get('href', ''))

                    if len(title) > 10 and temiz_fiyat:
                        all_products.append({
                            "Platform": "N11", "Kategori": "Bebek Bezi",
                            "Ürün Adı": title, "Fiyat": temiz_fiyat,
                            "Ürün Linki": href, "Resim": resim
                        })
                        eklenen += 1
                except: continue
            print(f"[N11] Sayfa {sayfa_no} üzerinden {eklenen} ürün yakalandı.")
        except Exception as e: print(f"[N11] HTTP Hata: {e}")
    return all_products

def hepsiburada_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.hepsiburada.com/bebek-bezleri-c-60001049"
    for sayfa_no in range(1, max_sayfa + 1):
        url = f"{base_url}?sayfa={sayfa_no}" if sayfa_no > 1 else base_url
        print(f"\n[Hepsiburada] Sayfa {sayfa_no} HTTP ile taranıyor...")
        try:
            response = requests.get(url, headers=HEADERS, timeout=20)
            soup = BeautifulSoup(response.text, 'html.parser')
            cards = soup.find_all('li', attrs={'data-index': True})
            if not cards: cards = soup.find_all('li', class_=re.compile(r'productListContent'))
            
            eklenen = 0
            for card in cards:
                try:
                    link_el = card.find('a', href=True)
                    title_el = card.find(attrs={"data-test-id": re.compile(r'title', re.IGNORECASE)}) or card.find('h3')
                    price_el = card.find(attrs={"data-test-id": "price-current-price"}) or card.find("div", {"data-test-id": "product-price"})
                    if not link_el or not title_el or not price_el: continue

                    title = title_el.text.strip()
                    if not urun_gecerli_mi(title): continue
                    
                    temiz_fiyat = fiyati_temizle(price_el.text)
                    img_el = card.find('img')
                    resim = resmi_temizle(img_el, "https://www.hepsiburada.com")
                    href = urljoin("https://www.hepsiburada.com", link_el['href'])

                    if len(title) > 5 and temiz_fiyat:
                        all_products.append({
                            "Platform": "Hepsiburada", "Kategori": "Bebek Bezi",
                            "Ürün Adı": title, "Fiyat": temiz_fiyat, "Ürün Linki": href,
                            "Resim": resim
                        })
                        eklenen += 1
                except: continue
            print(f"[Hepsiburada] Sayfa {sayfa_no} üzerinden {eklenen} ürün yakalandı.")
        except Exception as e: print(f"[Hepsiburada] HTTP Hata: {e}")
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
            except: conn.rollback()
        conn.commit()
        cur.close()
        conn.close()
        print(f"\n✅ ZAFER! Toplam {eklenen} ürün başarıyla Supabase'e kaydedildi!")
    except Exception as e: print(f"❌ Veritabanı bağlantı hatası: {e}")

if __name__ == "__main__":
    print("🚀 Bebiio Anti-Cloudflare Motoru Başlatıldı!\n")
    try:
        toplam_urunler = []
        toplam_urunler.extend(trendyol_tara(1))
        toplam_urunler.extend(n11_tara(1))
        toplam_urunler.extend(hepsiburada_tara(1))
        toplam_urunler.extend(amazon_tara(1))

        print(f"\n🎉 Tarama tamamlandı! Toplam {len(toplam_urunler)} ürün yakalandı. DB'ye yazılıyor...")
        save_to_db(toplam_urunler)
        print("✅ Görev başarıyla tamamlandı! Motor kapanıyor.")
    except Exception as e:
        print(f"❌ Motor çalışırken hata oluştu: {e}")