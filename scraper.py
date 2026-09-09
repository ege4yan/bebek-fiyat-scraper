import os
import re
import time
import psycopg2
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

SUPABASE_DB_URL = "postgresql://postgres.bbemkqegyvbktqjbjqrr:EgeKuzen2026@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"

def fiyati_temizle(fiyat_metni):
    fiyat_metni = re.sub(r'[^\d,.]', '', fiyat_metni)
    return fiyat_metni + " TL"

def amazon_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.amazon.com.tr/s?k=bebek+bezi&i=baby&__mk_tr_TR=%C3%85M%C3%85%C5%BD%C3%95%C3%91&crid=29LRHE03W0Z1I&sprefix=bebek+bezi%2Cbaby%2C141&ref=nb_sb_noss_2"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50, args=['--disable-blink-features=AutomationControlled', '--start-maximized']) 
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            locale="tr-TR", timezone_id="Europe/Istanbul",
            accept_downloads=True 
        )
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}&page={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[Amazon TR] Sayfa {sayfa_no} taranıyor...")
            try:
                page.goto("https://www.amazon.com.tr", timeout=45000)
                time.sleep(2)
                page.goto(url, timeout=60000)
                
                try:
                    page.wait_for_selector("div[data-asin]", timeout=6000)
                except:
                    print("🚨 AMAZON KORUMASI: Lütfen açılan Chrome penceresinde test çıkarsa çözün! (45 Saniye bekleniyor...)")
                    try:
                        page.wait_for_selector("div[data-asin]", timeout=45000)
                    except: pass
                    
                time.sleep(4)
            except: pass
            
            try:
                for _ in range(5):
                    page.mouse.wheel(0, 1000)
                    time.sleep(1.5)
            except: pass

            soup = BeautifulSoup(page.content(), 'html.parser')
            
            # AMAZON İÇİN ACIKMAZ SÜZGEÇ: Sadece "ASIN" (Ürün Kodu) olan gerçek kartları bul
            cards = soup.find_all("div", attrs={"data-asin": True})
            
            eklenen = 0
            for card in cards:
                try:
                    asin = card.get("data-asin")
                    if not asin: continue 
                    
                    # 1. Başlığı en geniş ihtimallerle ara
                    title_el = card.select_one("h2") or card.select_one("span.a-text-normal")
                    if title_el:
                        title = title_el.text.strip()
                    else:
                        img_el = card.select_one("img.s-image")
                        title = img_el.get("alt", "").strip() if img_el else ""
                        
                    if len(title) < 5: continue
                    
                    # 2. Linki garantiye al
                    link_el = card.select_one(f"a[href*='/{asin}/']") or card.select_one("h2 a") or card.select_one("a.a-link-normal")
                    if not link_el: continue
                    href = link_el.get('href', '')
                    if not href.startswith('http'):
                        href = "https://www.amazon.com.tr" + href
                        
                    # 3. Fiyatı parçalı veya bütün olarak kopar
                    fiyat_metni = ""
                    whole = card.select_one(".a-price-whole")
                    fraction = card.select_one(".a-price-fraction")
                    
                    if whole:
                        w_text = whole.text.strip().replace(",", "").replace(".", "")
                        f_text = fraction.text.strip() if fraction else "00"
                        fiyat_metni = f"{w_text},{f_text}"
                    else:
                        offscreen = card.select_one(".a-price .a-offscreen")
                        if offscreen:
                            fiyat_metni = offscreen.text.strip()
                            
                    temiz_fiyat = fiyati_temizle(fiyat_metni)
                    if temiz_fiyat == " TL" or temiz_fiyat == "": continue

                    all_products.append({
                        "Platform": "Amazon TR", "Kategori": "Bebek Bezi",
                        "Ürün Adı": title, "Fiyat": temiz_fiyat, "Ürün Linki": href
                    })
                    eklenen += 1
                except: continue
                
            print(f"[Amazon TR] Sayfa {sayfa_no} üzerinden {eklenen} ürün yakalandı.")
        browser.close()
    return all_products

def trendyol_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.trendyol.com/bebek-bezi-x-c1363"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50) 
        context = browser.new_context(viewport={'width': 1920, 'height': 1080}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = context.new_page()
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}?pi={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[Trendyol] Sayfa {sayfa_no} taranıyor...")
            try:
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
                time.sleep(3)
                for _ in range(3):
                    page.mouse.wheel(0, 1500)
                    time.sleep(2)
                soup = BeautifulSoup(page.content(), 'html.parser')
                links = soup.find_all('a', href=True)
                eklenen = 0
                for link in links:
                    href = link['href']
                    if '-p-' in href and '/yorumlar' not in href:
                        text_blocks = list(link.stripped_strings)
                        fiyatlar = [t for t in text_blocks if 'TL' in t]
                        if fiyatlar:
                            full_link = "https://www.trendyol.com" + href if href.startswith('/') else href
                            guncel_fiyat = fiyatlar[-1]
                            stop_words = ['TL', 'Sepete Ekle', 'Kargo Bedava', 'Hızlı Teslimat', 'Sponsorlu', 'Peşin Fiyatına', 'Son 30 Günün En Düşük Fiyatı', 'Avantajlı Ürün', 'Kuponlu Ürün', "Trendyol Plus'a Özel", "Plus'a Özel"]
                            name_parts = [t for t in text_blocks if not any(sw.lower() in t.lower() for sw in stop_words)]
                            title = " ".join(name_parts[:4]) if name_parts else "İsim Bulunamadı"
                            title = re.sub(r'\s+', ' ', title).strip()
                            all_products.append({"Platform": "Trendyol", "Kategori": "Bebek Bezi", "Ürün Adı": title, "Fiyat": guncel_fiyat, "Ürün Linki": full_link})
                            eklenen += 1
                print(f"[Trendyol] Sayfa {sayfa_no} üzerinden {eklenen} ürün yakalandı.")
            except: pass
        browser.close()
    return all_products

def n11_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.n11.com/bebek-bezi-ve-islak-mendil/bebek-bezi" 
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50) 
        context = browser.new_context(viewport={'width': 1920, 'height': 1080}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = context.new_page()
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}?pg={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[N11] Sayfa {sayfa_no} taranıyor...")
            try:
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
                time.sleep(3)
                for _ in range(4):
                    page.mouse.wheel(0, 1500)
                    time.sleep(2)
                soup = BeautifulSoup(page.content(), 'html.parser')
                links = soup.find_all('a', href=True)
                eklenen = 0
                for link in links:
                    href = link['href']
                    if '/urun/' in href or ('bebek' in href and '-' in href and not 'arama' in href and not 'kategori' in href):
                        text_blocks = list(link.stripped_strings)
                        if any('TL' in t for t in text_blocks):
                            full_link = href if href.startswith('http') else "https://www.n11.com" + href
                            fiyatlar = [t for t in text_blocks if 'TL' in t]
                            toplam_fiyat = "Fiyat Bulunamadı"
                            for f in fiyatlar:
                                if '/' not in f and 'Adet' not in f and 'adet' not in f:
                                    toplam_fiyat = re.sub(r'\s+', ' ', f).strip()
                            raw_title_blocks = [t for t in text_blocks if 'TL' not in t and '/' not in t]
                            title = " ".join(raw_title_blocks)
                            for kelime in ['ÜCRETSİZ KARGO', 'SÜPER', 'SEPETTE', 'günün en düşük fiyatı!', 'Hızlı Teslimat', 'Sponsorlu', 'Yeni', 'Tükendi', 'Sepete Ekle']:
                                title = re.sub(rf'(?i){re.escape(kelime)}', '', title)
                            title = re.sub(r'\s+', ' ', title).strip()
                            if len(title) > 10:
                                all_products.append({"Platform": "N11", "Kategori": "Bebek Bezi", "Ürün Adı": title, "Fiyat": toplam_fiyat, "Ürün Linki": full_link})
                                eklenen += 1
                print(f"[N11] Sayfa {sayfa_no} üzerinden {eklenen} ürün yakalandı.")
            except: pass
        browser.close()
    return all_products

def hepsiburada_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.hepsiburada.com/bebek-bezleri-c-60001049"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=100)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = context.new_page()
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}?sayfa={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[Hepsiburada] Sayfa {sayfa_no} taranıyor...")
            try:
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
                time.sleep(5)
                for _ in range(5):
                    page.mouse.wheel(0, 1500)
                    time.sleep(2)
                soup = BeautifulSoup(page.content(), 'html.parser')
                cards = soup.select("li[class*='productListContent']") or soup.find_all("li", attrs={"data-index": True})
                eklenen_urun = 0
                for card in cards:
                    link_el = card.find('a', href=True)
                    if not link_el: continue
                    full_link = link_el['href'] if link_el['href'].startswith('http') else "https://www.hepsiburada.com" + link_el['href']
                    title_el = card.find('h3') or card.find(attrs={"data-test-id": re.compile(r'title', re.IGNORECASE)})
                    title = title_el.text.strip() if title_el else ""
                    if not title: continue
                    joined_text = " ".join(card.stripped_strings)
                    joined_text = re.sub(r'(?<=\d)\s*,\s*(?=\d)', ',', joined_text)
                    joined_text = re.sub(r'(?<=\d)\s*\.\s*(?=\d)', '.', joined_text)
                    matches = re.findall(r'((?:\d{1,3}(?:\.\d{3})*|\d+)(?:,\d+)?)\s*(?:TL|₺)', joined_text, re.IGNORECASE)
                    fiyat = ""
                    if matches:
                        float_prices = []
                        for m in matches:
                            try: float_prices.append((float(m.replace('.', '').replace(',', '.')), m))
                            except: pass
                        if float_prices:
                            max_val = max(float_prices, key=lambda x: x[0])[0]
                            main_prices = [p for p in float_prices if p[0] > (max_val * 0.4)]
                            if main_prices: fiyat = min(main_prices, key=lambda x: x[0])[1] + " TL"
                    if fiyat:
                        all_products.append({"Platform": "Hepsiburada", "Kategori": "Bebek Bezi", "Ürün Adı": title, "Fiyat": fiyat, "Ürün Linki": full_link})
                        eklenen_urun += 1
                print(f"[Hepsiburada] Sayfa {sayfa_no} üzerinden {eklenen_urun} ürün yakalandı.")
            except: pass
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
                    INSERT INTO urunler (platform, kategori, urun_adi, fiyat, urun_linki)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (urun_linki) 
                    DO UPDATE SET fiyat = EXCLUDED.fiyat, urun_adi = EXCLUDED.urun_adi;
                """
                cur.execute(query, (urun["Platform"], urun["Kategori"], urun["Ürün Adı"], urun["Fiyat"], urun["Ürün Linki"]))
                eklenen += 1
            except: conn.rollback()
        conn.commit()
        cur.close()
        conn.close()
        print(f"\n✅ ZAFER! Toplam {eklenen} ürün başarıyla Supabase'e kaydedildi!")
    except Exception as e: print(f"❌ Veritabanı bağlantı hatası: {e}")
if __name__ == "__main__":
    print("🚀 Bebiio Otomatik Tarama Tankı Başlatıldı! (30 Dakikada Bir Ateşlenecek)\n")
    
    