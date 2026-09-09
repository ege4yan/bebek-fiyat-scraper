import os
import re
import time
import psycopg2
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# SUPABASE BAĞLANTISI
SUPABASE_DB_URL = "postgresql://postgres.bbemkqegyvbktqjbjqrr:EgeKuzen2026@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"

def fiyati_float_yap(fiyat_metni):
    """Metin içindeki rakamı matematiksel bir sayıya (float) çevirir."""
    temiz = re.sub(r'[^\d,.]', '', fiyat_metni)
    temiz = temiz.strip('.,')
    if not temiz: return 0.0
    # 1.250,50 formatını 1250.50 formatına çevir
    temiz = temiz.replace('.', '').replace(',', '.')
    try:
        return float(temiz)
    except:
        return 0.0

def metinden_gercek_fiyati_bul(text_list):
    """
    Karttaki tüm yazıları tarar, sahte rakamları (kargo, taksit, puan) eler,
    ve geçerli olan en düşük (indirimli) gerçek fiyatı bulur.
    """
    olasi_fiyatlar = []
    # Bu kelimelerin geçtiği satırlardaki rakamları yoksay
    yasakli_kelimeler = ['kazan', 'kargo', 'taksit', 'adet', 'premium', 'birlikte', 'ayda', 'peşin']
    
    for t in text_list:
        t_lower = t.lower()
        if 'tl' in t_lower or '₺' in t_lower:
            if any(yk in t_lower for yk in yasakli_kelimeler):
                continue
            
            f_val = fiyati_float_yap(t)
            # Bebek bezi paketleri 35 TL'den pahalıdır, altındakiler birim(adet) fiyatıdır
            if f_val > 35: 
                olasi_fiyatlar.append(f_val)
                
    if olasi_fiyatlar:
        # Eğer hem eski fiyat hem yeni fiyat varsa, ucuz olanı (güncel fiyatı) seç
        en_dusuk = min(olasi_fiyatlar)
        # Sayıyı tekrar e-ticaret formatına (1.250,50 TL) çevir
        formatli = f"{en_dusuk:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        return formatli + " TL"
    
    return ""

def scroll_page(page):
    """Sayfayı yavaşça kaydırarak ürünlerin tam yüklenmesini sağlar."""
    for _ in range(6):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(1)

def amazon_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.amazon.com.tr/s?k=bebek+bezi&i=baby&__mk_tr_TR=%C3%85M%C3%85%C5%BD%C3%95%C3%91&crid=29LRHE03W0Z1I&sprefix=bebek+bezi%2Cbaby%2C141&ref=nb_sb_noss_2"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50, args=['--disable-blink-features=AutomationControlled']) 
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
                    title = title_el.text.strip() if title_el else ""
                    if len(title) < 5: continue
                    
                    link_el = card.select_one(f"a[href*='/{asin}/']") or card.select_one("h2 a")
                    if not link_el: continue
                    href = link_el.get('href', '')
                    if not href.startswith('http'):
                        href = "https://www.amazon.com.tr" + href
                    
                    # Amazon'un özel fiyat etiketleri çok kararlı olduğu için dokunmuyoruz
                    whole = card.select_one(".a-price-whole")
                    fraction = card.select_one(".a-price-fraction")
                    
                    fiyat_metni = ""
                    if whole:
                        w_text = whole.text.strip().replace(",", "").replace(".", "")
                        f_text = fraction.text.strip() if fraction else "00"
                        fiyat_metni = f"{w_text},{f_text} TL"
                            
                    if not fiyat_metni or fiyat_metni == " TL": continue

                    all_products.append({
                        "Platform": "Amazon TR", "Kategori": "Bebek Bezi",
                        "Ürün Adı": title, "Fiyat": fiyat_metni, "Ürün Linki": href, "Resim": ""
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
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
                time.sleep(3)
                scroll_page(page)
                    
                soup = BeautifulSoup(page.content(), 'html.parser')
                cards = soup.find_all('div', class_='p-card-wrppr')
                
                eklenen = 0
                for card in cards:
                    link_el = card.find('a', href=True)
                    if not link_el: continue
                    
                    href = link_el['href']
                    full_link = "https://www.trendyol.com" + href if href.startswith('/') else href
                    
                    brand_el = card.find('span', class_='prdct-desc-brnd')
                    name_el = card.find('span', class_='prdct-desc-cntnr-name')
                    if not name_el: continue
                    title = ((brand_el.text.strip() + " " if brand_el else "") + name_el.text.strip()).strip()
                    
                    # ZIRHLI FİYAT SÜZGECİ
                    text_list = list(card.stripped_strings)
                    temiz_fiyat = metinden_gercek_fiyati_bul(text_list)
                    
                    if len(title) > 5 and temiz_fiyat:
                        all_products.append({
                            "Platform": "Trendyol", "Kategori": "Bebek Bezi", 
                            "Ürün Adı": title, "Fiyat": temiz_fiyat, "Ürün Linki": full_link, "Resim": ""
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
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
                time.sleep(3)
                scroll_page(page)
                    
                soup = BeautifulSoup(page.content(), 'html.parser')
                cards = soup.find_all('li', class_='column')
                
                eklenen = 0
                for card in cards:
                    link_el = card.find('a', class_='plink')
                    if not link_el: continue
                    
                    full_link = link_el.get('href', '')
                    title = link_el.get('title', '').strip()
                    
                    # ZIRHLI FİYAT SÜZGECİ
                    text_list = list(card.stripped_strings)
                    temiz_fiyat = metinden_gercek_fiyati_bul(text_list)
                    
                    if len(title) > 10 and temiz_fiyat:
                        all_products.append({
                            "Platform": "N11", "Kategori": "Bebek Bezi", 
                            "Ürün Adı": title, "Fiyat": temiz_fiyat, "Ürün Linki": full_link, "Resim": ""
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
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
                time.sleep(3)
                scroll_page(page)
                
                soup = BeautifulSoup(page.content(), 'html.parser')
                cards = soup.find_all("li", attrs={"data-index": True})
                
                eklenen = 0
                for card in cards:
                    link_el = card.find('a', href=True)
                    if not link_el: continue
                    full_link = link_el['href'] if link_el['href'].startswith('http') else "https://www.hepsiburada.com" + link_el['href']
                    
                    title_el = card.find(attrs={"data-test-id": re.compile(r'title', re.IGNORECASE)}) or card.find('h3')
                    title = title_el.text.strip() if title_el else ""
                    if not title: continue
                    
                    # ZIRHLI FİYAT SÜZGECİ (Hepsiburada'nın o karmaşık sahte fiyatlarını yok eder)
                    text_list = list(card.stripped_strings)
                    temiz_fiyat = metinden_gercek_fiyati_bul(text_list)
                    
                    if len(title) > 5 and temiz_fiyat:
                        all_products.append({
                            "Platform": "Hepsiburada", "Kategori": "Bebek Bezi", 
                            "Ürün Adı": title, "Fiyat": temiz_fiyat, "Ürün Linki": full_link, "Resim": ""
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
    print("🚀 Bebiio Zırhlı Fiyat Motoru Başlatıldı!\n")
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