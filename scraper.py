import os
import re
import time
import psycopg2
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# SUPABASE BAĞLANTISI
SUPABASE_DB_URL = "postgresql://postgres.bbemkqegyvbktqjbjqrr:EgeKuzen2026@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"

def fiyati_temizle(fiyat_metni):
    fiyat_metni = re.sub(r'[^\d,.]', '', fiyat_metni)
    return fiyat_metni + " TL"

def resim_bul(img_el):
    """Farklı sitelerin gizli resim ceplerini (Lazy Load) tarar ve gerçek resmi bulur."""
    if not img_el:
        return ""
    olasi_cepler = ['data-original', 'data-imagesrc', 'data-src', 'src']
    for cep in olasi_cepler:
        url = img_el.get(cep)
        # Eğer url varsa ve 1x1 boş bir piksel (base64) veya svg değilse bunu kullan
        if url and url.startswith('http') and "data:image" not in url:
            return url
    return ""

def amazon_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.amazon.com.tr/s?k=bebek+bezi&i=baby&__mk_tr_TR=%C3%85M%C3%85%C5%BD%C3%95%C3%91&crid=29LRHE03W0Z1I&sprefix=bebek+bezi%2Cbaby%2C141&ref=nb_sb_noss_2"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50, args=['--disable-blink-features=AutomationControlled']) 
        context = browser.new_context(viewport={'width': 1920, 'height': 1080}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = context.new_page()
        
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}&page={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[Amazon TR] Sayfa {sayfa_no} taranıyor...")
            try:
                page.goto("https://www.amazon.com.tr", timeout=45000)
                time.sleep(2)
                page.goto(url, timeout=60000)
                time.sleep(3)
                for _ in range(4):
                    page.mouse.wheel(0, 1000)
                    time.sleep(1.5)
            except: pass

            soup = BeautifulSoup(page.content(), 'html.parser')
            cards = soup.find_all("div", attrs={"data-asin": True})
            
            eklenen = 0
            for card in cards:
                try:
                    asin = card.get("data-asin")
                    if not asin: continue 
                    
                    title_el = card.select_one("h2 span") or card.select_one("span.a-text-normal")
                    title = title_el.text.strip() if title_el else ""
                    if len(title) < 5: continue
                    
                    img_el = card.select_one("img.s-image")
                    resim_url = img_el.get("src", "") if img_el else ""
                    
                    link_el = card.select_one(f"a[href*='/{asin}/']") or card.select_one("h2 a")
                    if not link_el: continue
                    href = link_el.get('href', '')
                    if not href.startswith('http'):
                        href = "https://www.amazon.com.tr" + href
                        
                    whole = card.select_one(".a-price-whole")
                    fraction = card.select_one(".a-price-fraction")
                    
                    fiyat_metni = ""
                    if whole:
                        w_text = whole.text.strip().replace(",", "").replace(".", "")
                        f_text = fraction.text.strip() if fraction else "00"
                        fiyat_metni = f"{w_text},{f_text}"
                            
                    temiz_fiyat = fiyati_temizle(fiyat_metni)
                    if temiz_fiyat == " TL" or temiz_fiyat == "": continue

                    all_products.append({
                        "Platform": "Amazon TR", "Kategori": "Bebek Bezi",
                        "Ürün Adı": title, "Fiyat": temiz_fiyat, "Ürün Linki": href,
                        "Resim": resim_url
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
                for _ in range(4):
                    page.mouse.wheel(0, 1500)
                    time.sleep(2)
                    
                soup = BeautifulSoup(page.content(), 'html.parser')
                cards = soup.find_all('div', class_='p-card-wrppr')
                
                eklenen = 0
                for card in cards:
                    link_el = card.find('a', href=True)
                    if not link_el: continue
                    
                    href = link_el['href']
                    full_link = "https://www.trendyol.com" + href if href.startswith('/') else href
                    
                    # BAŞLIK
                    brand_el = card.find('span', class_='prdct-desc-brnd')
                    name_el = card.find('span', class_='prdct-desc-cntnr-name')
                    if not name_el: continue
                    brand = brand_el.text.strip() + " " if brand_el else ""
                    title = (brand + name_el.text.strip()).strip()
                    
                    # RESİM (Nokta atışı Lazy Load korumalı)
                    img_el = card.find('img', class_='p-card-img')
                    resim_url = resim_bul(img_el)
                    
                    # FİYAT (Sadece asıl indirimli/geçerli fiyatı al)
                    price_el = card.find('div', class_='prc-box-dscntd') or card.find('div', class_='prc-box-sllng')
                    if not price_el: continue
                    fiyat_metni = price_el.text.strip()
                    temiz_fiyat = fiyati_temizle(fiyat_metni)
                    
                    if len(title) > 5 and temiz_fiyat != " TL":
                        all_products.append({
                            "Platform": "Trendyol", "Kategori": "Bebek Bezi", 
                            "Ürün Adı": title, "Fiyat": temiz_fiyat, "Ürün Linki": full_link,
                            "Resim": resim_url
                        })
                        eklenen += 1
                print(f"[Trendyol] Sayfa {sayfa_no} üzerinden {eklenen} ürün yakalandı.")
            except Exception as e: print(f"Hata: {e}")
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
                for _ in range(5):
                    page.mouse.wheel(0, 1500)
                    time.sleep(2)
                    
                soup = BeautifulSoup(page.content(), 'html.parser')
                cards = soup.find_all('li', class_='column')
                
                eklenen = 0
                for card in cards:
                    link_el = card.find('a', class_='plink')
                    if not link_el: continue
                    
                    full_link = link_el.get('href', '')
                    title = link_el.get('title', '').strip()
                    
                    # RESİM
                    img_el = card.find('img', class_='cardImage')
                    resim_url = resim_bul(img_el)
                    
                    # FİYAT (Sadece geçerli, altını çizip sildikleri değil)
                    price_el = card.find('ins') or card.find('span', class_='newPrice')
                    if not price_el: continue
                    temiz_fiyat = fiyati_temizle(price_el.text.strip())
                    
                    if len(title) > 10 and temiz_fiyat != " TL":
                        all_products.append({
                            "Platform": "N11", "Kategori": "Bebek Bezi", 
                            "Ürün Adı": title, "Fiyat": temiz_fiyat, "Ürün Linki": full_link,
                            "Resim": resim_url
                        })
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
                for _ in range(6):
                    page.mouse.wheel(0, 1500)
                    time.sleep(2)
                    
                soup = BeautifulSoup(page.content(), 'html.parser')
                cards = soup.find_all("li", attrs={"data-index": True})
                
                eklenen = 0
                for card in cards:
                    link_el = card.find('a', href=True)
                    if not link_el: continue
                    full_link = link_el['href'] if link_el['href'].startswith('http') else "https://www.hepsiburada.com" + link_el['href']
                    
                    # BAŞLIK
                    title_el = card.find(attrs={"data-test-id": re.compile(r'title', re.IGNORECASE)}) or card.find('h3')
                    title = title_el.text.strip() if title_el else ""
                    
                    # RESİM
                    img_el = card.find('img')
                    resim_url = resim_bul(img_el)

                    # FİYAT (Artık metin tahmini yapmıyoruz, direkt fiyat etiketine vuruyoruz)
                    price_el = card.find(attrs={"data-test-id": "price-current-price"})
                    if not price_el: continue
                    temiz_fiyat = fiyati_temizle(price_el.text.strip())
                    
                    if len(title) > 5 and temiz_fiyat != " TL":
                        all_products.append({
                            "Platform": "Hepsiburada", "Kategori": "Bebek Bezi", 
                            "Ürün Adı": title, "Fiyat": temiz_fiyat, "Ürün Linki": full_link,
                            "Resim": resim_url
                        })
                        eklenen += 1
                print(f"[Hepsiburada] Sayfa {sayfa_no} üzerinden {eklenen} ürün yakalandı.")
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
    print("🚀 Bebiio GitHub Actions Motoru Başlatıldı!\n")
    try:
        toplam_urunler = []
        print("Trendyol taranıyor...")
        toplam_urunler.extend(trendyol_tara(1))
        
        print("Amazon taranıyor...")
        toplam_urunler.extend(amazon_tara(1))
        
        print("N11 taranıyor...")
        toplam_urunler.extend(n11_tara(1))
        
        print("Hepsiburada taranıyor...")
        toplam_urunler.extend(hepsiburada_tara(1))
        
        print(f"\n🎉 Tarama tamamlandı! Toplam {len(toplam_urunler)} ürün yakalandı.")
        print("Veritabanına (Supabase) yazılıyor...")
        
        save_to_db(toplam_urunler)
        print("✅ Görev başarıyla tamamlandı! Motor kapanıyor.")
    except Exception as e:
        print(f"❌ Motor çalışırken hata oluştu: {e}")