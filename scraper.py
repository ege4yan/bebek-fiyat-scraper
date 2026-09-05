import os
import re
import time
import psycopg2
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from playwright_stealth import stealth_sync

# Şifreyi koddan sildik, artık GitHub Secrets'tan güvenle çekecek
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")

def amazon_tara(max_sayfa=3):
    all_products = []
    base_url = "https://www.amazon.com.tr/s?k=bebek+bezi&rh=n%3A12466391031"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=70)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            locale="tr-TR",
            timezone_id="Europe/Istanbul"
        )
        page = context.new_page()
        stealth_sync(page)
        
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}&page={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[Amazon TR] Sayfa {sayfa_no} taranıyor: {url}")
            
            try:
                page.goto(url, timeout=60000, wait_until="domcontentloaded", referer="https://www.google.com.tr/")
            except Exception as e:
                print(f"[Amazon TR] Sayfa yüklenemedi: {e}")
                continue

            time.sleep(4)
            
            try:
                page.locator("input#sp-cc-accept").click(timeout=3000)
                time.sleep(1)
            except:
                pass
            
            try:
                for _ in range(5):
                    page.mouse.wheel(0, 1000)
                    time.sleep(1.5)
            except:
                pass

            soup = BeautifulSoup(page.content(), 'html.parser')
            cards = soup.find_all("div", attrs={"data-component-type": "s-search-result"})
            if not cards:
                cards = soup.find_all("div", class_="s-result-item")
                
            print(f"[Amazon TR] DOM'da {len(cards)} adet ürün kutusu tespit edildi.")
            eklenen_urun = 0
            
            for card in cards:
                try:
                    title = "İsim Bulunamadı"
                    full_link = ""
                    
                    title_el = card.find("h2") or card.find("h3") or card.find(class_=re.compile(r'title', re.IGNORECASE))
                    if title_el:
                        title = title_el.text.strip()
                        link_el = title_el.find("a") or card.find("a", class_="a-link-normal")
                    else:
                        link_el = card.find("a", class_="a-link-normal")
                        
                    if link_el and 'href' in link_el.attrs:
                        href = link_el['href']
                        if '/dp/' in href or '/gp/' in href:
                            full_link = href if href.startswith('http') else "https://www.amazon.com.tr" + href

                    if title == "İsim Bulunamadı" and link_el:
                        alt_text = link_el.text.strip()
                        if len(alt_text) > 15:
                            title = alt_text

                    if title == "İsim Bulunamadı" or not full_link:
                        continue

                    fiyat = "Fiyat Bulunamadı"
                    whole_el = card.find("span", class_="a-price-whole")
                    fraction_el = card.find("span", class_="a-price-fraction")
                    
                    if whole_el:
                        w_text = whole_el.text.strip().replace(',', '').replace('.', '')
                        f_text = fraction_el.text.strip() if fraction_el else "00"
                        fiyat = f"{w_text},{f_text} TL"
                    else:
                        offscreen = card.find("span", class_="a-offscreen")
                        if offscreen:
                            fiyat = offscreen.text.strip().replace('₺', 'TL')

                    fiyat = re.sub(r'\s+', ' ', fiyat).strip()
                    
                    if "Fiyat Bulunamadı" not in fiyat:
                        all_products.append({
                            "Platform": "Amazon TR",
                            "Kategori": "Bebek Bezi",
                            "Ürün Adı": title,
                            "Fiyat": fiyat,
                            "Ürün Linki": full_link
                        })
                        eklenen_urun += 1
                except Exception:
                    continue
                    
            print(f"[Amazon TR] Sayfa {sayfa_no} üzerinden {eklenen_urun} ürün yakalandı.")
        browser.close()
    return all_products

def hepsiburada_tara(max_sayfa=3):
    all_products = []
    base_url = "https://www.hepsiburada.com/bebek-bezleri-c-60001049"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=100)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            java_script_enabled=True,
            bypass_csp=True,
            locale="tr-TR",
            timezone_id="Europe/Istanbul"
        )
        page = context.new_page()
        stealth_sync(page)
        
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}?sayfa={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[Hepsiburada] Sayfa {sayfa_no} taranıyor: {url}")
            
            try:
                page.goto(url, timeout=60000, wait_until="domcontentloaded", referer="https://www.google.com.tr/")
            except Exception as e:
                print(f"[Hepsiburada] Sayfa yüklenemedi: {e}")
                continue

            time.sleep(4)
            
            try:
                for _ in range(5):
                    page.mouse.wheel(0, 1500)
                    time.sleep(2)
            except:
                pass

            soup = BeautifulSoup(page.content(), 'html.parser')
            cards = soup.select("li[class*='productListContent']")
            if not cards:
                cards = soup.find_all("li", attrs={"data-index": True})

            print(f"[Hepsiburada] DOM'da {len(cards)} adet ürün kutusu tespit edildi.")
            eklenen_urun = 0
            
            for card in cards:
                try:
                    link_el = card.find('a', href=True)
                    if not link_el:
                        continue
                    href = link_el['href']
                    full_link = href if href.startswith('http') else "https://www.hepsiburada.com" + href
                    
                    title_el = card.find('h3') or card.find(attrs={"data-test-id": re.compile(r'title', re.IGNORECASE)})
                    title = title_el.text.strip() if title_el else "İsim Bulunamadı"
                    if title == "İsim Bulunamadı":
                        continue
                    
                    joined_text = " ".join(card.stripped_strings)
                    joined_text = re.sub(r'(?<=\d)\s*,\s*(?=\d)', ',', joined_text)
                    joined_text = re.sub(r'(?<=\d)\s*\.\s*(?=\d)', '.', joined_text)
                    
                    matches = re.findall(r'((?:\d{1,3}(?:\.\d{3})*|\d+)(?:,\d+)?)\s*(?:TL|₺)', joined_text, re.IGNORECASE)
                    fiyat = "Fiyat Bulunamadı"
                    
                    if matches:
                        float_prices = []
                        for m in matches:
                            try:
                                val = float(m.replace('.', '').replace(',', '.'))
                                float_prices.append((val, m))
                            except:
                                pass
                                
                        if float_prices:
                            max_val = max(float_prices, key=lambda x: x[0])[0]
                            main_prices = [p for p in float_prices if p[0] > (max_val * 0.4)]
                            if main_prices:
                                best_match = min(main_prices, key=lambda x: x[0])
                                fiyat = best_match[1] + " TL"

                    if "Fiyat Bulunamadı" not in fiyat:
                        all_products.append({
                            "Platform": "Hepsiburada",
                            "Kategori": "Bebek Bezi",
                            "Ürün Adı": title,
                            "Fiyat": fiyat,
                            "Ürün Linki": full_link
                        })
                        eklenen_urun += 1
                except Exception:
                    continue
                    
            print(f"[Hepsiburada] Sayfa {sayfa_no} üzerinden {eklenen_urun} ürün yakalandı.")
        browser.close()
    return all_products

def n11_tara(max_sayfa=3):
    all_products = []
    base_url = "https://www.n11.com/bebek-bezi-ve-islak-mendil/bebek-bezi" 
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        stealth_sync(page)
        
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}?pg={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[N11] Sayfa {sayfa_no} taranıyor: {url}")
            
            try:
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
            except Exception as e:
                print(f"[N11] Sayfa yüklenemedi: {e}")
                continue
                
            if "Aradığın sayfa bulunamadı" in page.content():
                print("[N11] 404 Hata Sayfası - Link geçersiz veya kategori sonu.")
                break
                
            if sayfa_no == 1:
                try:
                    page.locator("text='Kabul Et'").first.click(timeout=5000)
                    time.sleep(1)
                except:
                    pass
            
            try:
                for _ in range(4):
                    page.mouse.wheel(0, 1500)
                    time.sleep(2)
            except Exception:
                print("[N11] Kaydırma sırasında hata, tarama devam ediyor...")
                
            soup = BeautifulSoup(page.content(), 'html.parser')
            links = soup.find_all('a', href=True)
            eklenen_urun = 0
            
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
                        
                        if toplam_fiyat == "Fiyat Bulunamadı" and fiyatlar:
                            olasi_toplam = [f for f in fiyatlar if '/' not in f]
                            if olasi_toplam:
                                toplam_fiyat = re.sub(r'\s+', ' ', olasi_toplam[-1]).strip()
                                
                        raw_title_blocks = [t for t in text_blocks if 'TL' not in t and '/' not in t]
                        raw_title = " ".join(raw_title_blocks)
                        
                        silinecekler = [
                            'ÜCRETSİZ KARGO', 'SÜPER', 'SEPETTE', 'günün en düşük fiyatı!', 
                            'Hızlı Teslimat', 'Sponsorlu', 'Yeni', 'Tükendi', 'Sepete Ekle'
                        ]
                        
                        title = raw_title
                        for kelime in silinecekler:
                            title = re.sub(rf'(?i){re.escape(kelime)}', '', title)
                            
                        title = re.sub(r'\s+', ' ', title).strip()
                        
                        if len(title) > 10:
                            all_products.append({
                                "Platform": "N11",
                                "Kategori": "Bebek Bezi",
                                "Ürün Adı": title,
                                "Fiyat": toplam_fiyat,
                                "Ürün Linki": full_link
                            })
                            eklenen_urun += 1
            
            print(f"[N11] Sayfa {sayfa_no} üzerinden {eklenen_urun} ürün yakalandı.")
        browser.close()
    return all_products

def trendyol_tara(max_sayfa=3):
    all_products = []
    base_url = "https://www.trendyol.com/bebek-bezi-x-c1363"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        stealth_sync(page)
        
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}?pi={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[Trendyol] Sayfa {sayfa_no} taranıyor: {url}")
            
            try:
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
            except Exception as e:
                print(f"[Trendyol] Sayfa yüklenemedi: {e}")
                continue
            
            if sayfa_no == 1:
                try:
                    page.locator("text='Tüm Tanımlama Bilgilerini Kabul Et'").click(timeout=5000)
                    time.sleep(1)
                except:
                    pass
            
            for _ in range(3):
                page.mouse.wheel(0, 1500)
                time.sleep(2)
                
            soup = BeautifulSoup(page.content(), 'html.parser')
            links = soup.find_all('a', href=True)
            eklenen_urun = 0
            
            for link in links:
                href = link['href']
                if '-p-' in href and '/yorumlar' not in href:
                    text_blocks = list(link.stripped_strings)
                    fiyatlar = [t for t in text_blocks if 'TL' in t]
                    
                    if fiyatlar:
                        full_link = "https://www.trendyol.com" + href if href.startswith('/') else href
                        guncel_fiyat = fiyatlar[-1]
                        
                        stop_words = [
                            'TL', 'Sepete Ekle', 'Kargo Bedava', 'Hızlı Teslimat', 
                            'Sponsorlu', 'Peşin Fiyatına', 'Son 30 Günün En Düşük Fiyatı', 
                            'Avantajlı Ürün', 'Kuponlu Ürün', "Trendyol Plus'a Özel", "Plus'a Özel"
                        ]
                        
                        name_parts = [t for t in text_blocks if not any(sw.lower() in t.lower() for sw in stop_words)]
                        title = " ".join(name_parts[:4]) if name_parts else "İsim Bulunamadı"
                        title = re.sub(r'\s+', ' ', title).strip()
                        
                        all_products.append({
                            "Platform": "Trendyol",
                            "Kategori": "Bebek Bezi",
                            "Ürün Adı": title,
                            "Fiyat": guncel_fiyat,
                            "Ürün Linki": full_link
                        })
                        eklenen_urun += 1
                        
            print(f"[Trendyol] Sayfa {sayfa_no} üzerinden {eklenen_urun} ürün yakalandı.")
        browser.close()
    return all_products

def save_to_db(all_products):
    if not all_products:
        print("❌ Kaydedilecek ürün bulunamadı.")
        return
    
    if not SUPABASE_DB_URL:
        print("❌ SUPABASE_DB_URL bulunamadı! Veritabanı işlemi atlandı.")
        return
        
    try:
        conn = psycopg2.connect(SUPABASE_DB_URL)
        cur = conn.cursor()
        eklenen = 0
        
        for urun in all_products:
            try:
                # urunler tablosu için düzeltilmiş SQL komutu
                query = """
                    INSERT INTO urunler (platform, kategori, urun_adi, fiyat, urun_linki)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (urun_linki) 
                    DO UPDATE SET 
                        fiyat = EXCLUDED.fiyat,
                        urun_adi = EXCLUDED.urun_adi;
                """
                cur.execute(query, (
                    urun["Platform"], 
                    urun["Kategori"], 
                    urun["Ürün Adı"], 
                    urun["Fiyat"], 
                    urun["Ürün Linki"]
                ))
                eklenen += 1
            except Exception as e:
                print(f"Supabase yazma hatası ({urun['Platform']}): {e}")
                conn.rollback() # Hata olan ürünü atla, sistemi çökertmeden sonrakine geç
                continue
                
        conn.commit()
        cur.close()
        conn.close()
        print(f"\n✅ {eklenen} ürün başarıyla Supabase'e kaydedildi!")
        
    except Exception as e:
        print(f"❌ Veritabanı bağlantı hatası: {e}")

if __name__ == "__main__":
    print("🚀 Akıllı Tarama Motorları Başlatılıyor...\n")
    toplam_urunler = []
    
    # Tüm platformları sırayla tek dosyada çalıştırıyoruz
    # Test aşamasında olduğumuz için max_sayfa=1 ile bıraktım, dilersen artırabilirsin
    toplam_urunler.extend(trendyol_tara(1))
    toplam_urunler.extend(amazon_tara(1))
    toplam_urunler.extend(hepsiburada_tara(1))
    toplam_urunler.extend(n11_tara(1))
    
    print(f"\n🎉 Tarama tamamlandı! Toplam {len(toplam_urunler)} ürün yakalandı. Veritabanına yazılıyor...")
    save_to_db(toplam_urunler)