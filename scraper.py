import os
import re
import time
import psycopg2
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# SUPABASE BAĞLANTISI
SUPABASE_DB_URL = "postgresql://postgres.bbemkqegyvbktqjbjqrr:EgeKuzen2026@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"

def fiyati_temizle(fiyat_metni):
    if not fiyat_metni: return ""
    match = re.search(r'(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)', fiyat_metni.replace(' ', ''))
    if match:
        bulunan_fiyat = match.group(1).strip('.,')
        return bulunan_fiyat + " TL"
    return ""

def scroll_page(page):
    for _ in range(6):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(1)

def amazon_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.amazon.com.tr/s?k=bebek+bezi&i=baby&__mk_tr_TR=%C3%85M%C3%85%C5%BD%C3%95%C3%91&crid=29LRHE03W0Z1I&sprefix=bebek+bezi%2Cbaby%2C141&ref=nb_sb_noss_2"
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
            except: pass
            soup = BeautifulSoup(page.content(), 'html.parser')
            cards = soup.find_all("div", attrs={"data-asin": True})
            eklenen = 0
            for card in cards:
                try:
                    asin = card.get("data-asin")
                    if not asin: continue 
                    title_el = card.select_one("h2 span") or card.select_one("span.a-text-normal")
                    if not title_el or len(title_el.text) < 5: continue
                    link_el = card.select_one(f"a[href*='/{asin}/']") or card.select_one("h2 a")
                    if not link_el: continue
                    
                    whole = card.select_one(".a-price-whole")
                    fraction = card.select_one(".a-price-fraction")
                    if not whole: continue
                    
                    fiyat_metni = f"{whole.text.strip().replace(',', '').replace('.', '')},{fraction.text.strip() if fraction else '00'}"
                    temiz_fiyat = fiyati_temizle(fiyat_metni)
                    
                    if temiz_fiyat:
                        all_products.append({
                            "Platform": "Amazon TR", "Kategori": "Bebek Bezi",
                            "Ürün Adı": title_el.text.strip(), "Fiyat": temiz_fiyat, 
                            "Ürün Linki": "https://www.amazon.com.tr" + link_el.get('href', ''), "Resim": ""
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
        context = browser.new_context(viewport={'width': 1920, 'height': 1080}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = context.new_page()
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}?pi={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[Trendyol] Sayfa {sayfa_no} taranıyor...")
            try:
                page.goto(url, timeout=60000)
                try: page.wait_for_selector('.prc-box-dscntd', timeout=5000)
                except: pass
                scroll_page(page)
                soup = BeautifulSoup(page.content(), 'html.parser')
                cards = soup.find_all('div', class_='p-card-wrppr')
                eklenen = 0
                for card in cards:
                    link_el = card.find('a', href=True)
                    price_el = card.find('div', class_='prc-box-dscntd') or card.find('div', class_='prc-box-sllng')
                    if not link_el or not price_el: continue
                    
                    brand_el = card.find('span', class_='prdct-desc-brnd')
                    name_el = card.find('span', class_='prdct-desc-cntnr-name')
                    title = ((brand_el.text.strip() + " " if brand_el else "") + (name_el.text.strip() if name_el else "")).strip()
                    
                    temiz_fiyat = fiyati_temizle(price_el.text)
                    if len(title) > 5 and temiz_fiyat:
                        all_products.append({
                            "Platform": "Trendyol", "Kategori": "Bebek Bezi", 
                            "Ürün Adı": title, "Fiyat": temiz_fiyat, 
                            "Ürün Linki": "https://www.trendyol.com" + link_el['href'], "Resim": ""
                        })
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
        context = browser.new_context(viewport={'width': 1920, 'height': 1080}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = context.new_page()
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}?pg={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[N11] Sayfa {sayfa_no} taranıyor...")
            try:
                page.goto(url, timeout=60000)
                try: page.wait_for_selector('ins', timeout=5000)
                except: pass
                scroll_page(page)
                soup = BeautifulSoup(page.content(), 'html.parser')
                cards = soup.find_all('li', class_='column')
                eklenen = 0
                for card in cards:
                    link_el = card.find('a', class_='plink')
                    price_el = card.find('ins') or card.find('span', class_='newPrice')
                    if not link_el or not price_el: continue
                    
                    title = link_el.get('title', '').strip()
                    temiz_fiyat = fiyati_temizle(price_el.text)
                    if len(title) > 10 and temiz_fiyat:
                        all_products.append({
                            "Platform": "N11", "Kategori": "Bebek Bezi", 
                            "Ürün Adı": title, "Fiyat": temiz_fiyat, 
                            "Ürün Linki": link_el.get('href', ''), "Resim": ""
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
        browser = p.chromium.launch(headless=True, slow_mo=50)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = context.new_page()
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}?sayfa={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[Hepsiburada] Sayfa {sayfa_no} taranıyor...")
            try:
                page.goto(url, timeout=60000)
                try: page.wait_for_selector('[data-test-id="price-current-price"]', timeout=8000)
                except: pass
                scroll_page(page)
                
                # BÜYÜK DEĞİŞİM: HTML'i dışarıdan okumayı bıraktık. 
                # Doğrudan tarayıcının JavaScript motoruyla içeriden nokta atışı veri çekiyoruz.
                extracted_data = page.evaluate('''() => {
                    let items = [];
                    let cards = document.querySelectorAll("li[data-index]");
                    cards.forEach(card => {
                        let a_tag = card.querySelector("a");
                        let title_tag = card.querySelector("[data-test-id*='title']") || card.querySelector("h3");
                        let price_tag = card.querySelector("[data-test-id='price-current-price']");
                        
                        if (a_tag && title_tag && price_tag) {
                            items.push({
                                title: title_tag.innerText.trim(),
                                price: price_tag.innerText.trim(),
                                link: a_tag.getAttribute("href")
                            });
                        }
                    });
                    return items;
                }''')
                
                eklenen = 0
                for data in extracted_data:
                    title = data.get("title", "")
                    raw_price = data.get("price", "")
                    href = data.get("link", "")
                    
                    if not href.startswith('http'):
                        href = "https://www.hepsiburada.com" + href
                        
                    temiz_fiyat = fiyati_temizle(raw_price)
                    
                    if len(title) > 5 and temiz_fiyat:
                        all_products.append({
                            "Platform": "Hepsiburada", "Kategori": "Bebek Bezi", 
                            "Ürün Adı": title, "Fiyat": temiz_fiyat, "Ürün Linki": href, "Resim": ""
                        })
                        eklenen += 1
                print(f"[Hepsiburada] Sayfa {sayfa_no} üzerinden {eklenen} ürün yakalandı.")
            except Exception as e: print(f"Hepsiburada Hata: {e}")
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
                    DO UPDATE SET fiyat = EXCLUDED.fiyat, urun_adi = EXCLUDED.urun_adi;
                """
                cur.execute(query, (urun["Platform"], urun["Kategori"], urun["Ürün Adı"], urun["Fiyat"], urun["Ürün Linki"], ""))
                eklenen += 1
            except: conn.rollback()
        conn.commit()
        cur.close()
        conn.close()
        print(f"\n✅ ZAFER! Toplam {eklenen} ürün başarıyla Supabase'e kaydedildi!")
    except Exception as e: print(f"❌ Veritabanı bağlantı hatası: {e}")

if __name__ == "__main__":
    print("🚀 Bebiio JS Enjeksiyonlu Motor Başlatıldı!\n")
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