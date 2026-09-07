import os
import re
import time
import psycopg2
from bs4 import BeautifulSoup
from curl_cffi import requests
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

# Şifremiz GitHub Secrets üzerinden güvenle çekiliyor
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")

# Sitelerin bizi gerçek insan sanması için gereken kalkanlar
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
}

def amazon_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.amazon.com.tr/s?k=bebek+bezi&rh=n%3A12466391031"
    
    for sayfa_no in range(1, max_sayfa + 1):
        url = f"{base_url}&page={sayfa_no}" if sayfa_no > 1 else base_url
        print(f"\n[Amazon TR] Sayfa {sayfa_no} taranıyor (cffi)...")
        try:
            res = requests.get(url, impersonate="chrome110", headers=HEADERS, timeout=20)
            soup = BeautifulSoup(res.text, 'html.parser')
            cards = soup.select("div[data-component-type='s-search-result']")
            eklenen = 0
            
            for card in cards:
                title_el = card.select_one("span.a-text-normal")
                price_el = card.select_one("span.a-price-whole")
                link_el = card.select_one("a.a-link-normal")

                title = title_el.text.strip() if title_el else ""
                price = price_el.text.strip() if price_el else ""
                link = link_el['href'] if link_el and 'href' in link_el.attrs else ""

                if title and price:
                    full_link = link if link.startswith("http") else "https://www.amazon.com.tr" + link
                    price_clean = re.sub(r'[^\d,]', '', price.replace('.', '')) + " TL"
                    all_products.append({
                        "Platform": "Amazon TR", "Kategori": "Bebek Bezi",
                        "Ürün Adı": title, "Fiyat": price_clean, "Ürün Linki": full_link
                    })
                    eklenen += 1
            print(f"[Amazon TR] Sayfa {sayfa_no} üzerinden {eklenen} ürün yakalandı.")
        except Exception as e:
            print(f"[Amazon TR] Hata: {e}")
    return all_products

def trendyol_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.trendyol.com/bebek-bezi-x-c1363"
    
    for sayfa_no in range(1, max_sayfa + 1):
        url = f"{base_url}?pi={sayfa_no}" if sayfa_no > 1 else base_url
        print(f"\n[Trendyol] Sayfa {sayfa_no} taranıyor (cffi)...")
        try:
            res = requests.get(url, impersonate="chrome110", headers=HEADERS, timeout=20)
            soup = BeautifulSoup(res.text, 'html.parser')
            cards = soup.select("div.p-card-wrppr")
            eklenen = 0
            
            for card in cards:
                title_el = card.select_one("span.prdct-desc-cntnr-name")
                price_el = card.select_one("div.prc-box-dscntd")
                link_el = card.select_one("a")

                title = title_el.text.strip() if title_el else ""
                price = price_el.text.strip() if price_el else ""
                link = link_el['href'] if link_el and 'href' in link_el.attrs else ""

                if title and price:
                    full_link = link if link.startswith("http") else "https://www.trendyol.com" + link
                    all_products.append({
                        "Platform": "Trendyol", "Kategori": "Bebek Bezi",
                        "Ürün Adı": title, "Fiyat": price, "Ürün Linki": full_link
                    })
                    eklenen += 1
            print(f"[Trendyol] Sayfa {sayfa_no} üzerinden {eklenen} ürün yakalandı.")
        except Exception as e:
            print(f"[Trendyol] Hata: {e}")
    return all_products

def n11_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.n11.com/bebek-bezi-ve-islak-mendil/bebek-bezi"
    
    for sayfa_no in range(1, max_sayfa + 1):
        url = f"{base_url}?pg={sayfa_no}" if sayfa_no > 1 else base_url
        print(f"\n[N11] Sayfa {sayfa_no} taranıyor (cffi)...")
        try:
            res = requests.get(url, impersonate="chrome110", headers=HEADERS, timeout=20)
            soup = BeautifulSoup(res.text, 'html.parser')
            cards = soup.select("li.column")
            eklenen = 0
            
            for card in cards:
                title_el = card.select_one("h3.productName")
                price_el = card.select_one("ins")
                link_el = card.select_one("a.plink")

                title = title_el.text.strip() if title_el else ""
                price = price_el.text.strip() if price_el else ""
                link = link_el['href'] if link_el and 'href' in link_el.attrs else ""

                if title and price:
                    full_link = link if link.startswith("http") else link
                    price_clean = re.sub(r'\s+', ' ', price).strip()
                    all_products.append({
                        "Platform": "N11", "Kategori": "Bebek Bezi",
                        "Ürün Adı": title, "Fiyat": price_clean, "Ürün Linki": full_link
                    })
                    eklenen += 1
            print(f"[N11] Sayfa {sayfa_no} üzerinden {eklenen} ürün yakalandı.")
        except Exception as e:
            print(f"[N11] Hata: {e}")
    return all_products

# Kusursuz çalışan Hepsiburada Playwright kodumuz
def hepsiburada_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.hepsiburada.com/bebek-bezleri-c-60001049"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=100)
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
            print(f"\n[Hepsiburada] Sayfa {sayfa_no} taranıyor...")
            
            try:
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
            except Exception as e:
                print(f"[Hepsiburada] Sayfa yüklenemedi: {e}")
                continue

            time.sleep(5)
            
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

            eklenen_urun = 0
            for card in cards:
                try:
                    link_el = card.find('a', href=True)
                    if not link_el: continue
                    href = link_el['href']
                    full_link = href if href.startswith('http') else "https://www.hepsiburada.com" + href
                    
                    title_el = card.find('h3') or card.find(attrs={"data-test-id": re.compile(r'title', re.IGNORECASE)})
                    title = title_el.text.strip() if title_el else "İsim Bulunamadı"
                    if title == "İsim Bulunamadı": continue
                    
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
                            except: pass
                                
                        if float_prices:
                            max_val = max(float_prices, key=lambda x: x[0])[0]
                            main_prices = [p for p in float_prices if p[0] > (max_val * 0.4)]
                            if main_prices:
                                best_match = min(main_prices, key=lambda x: x[0])
                                fiyat = best_match[1] + " TL"

                    if "Fiyat Bulunamadı" not in fiyat:
                        all_products.append({
                            "Platform": "Hepsiburada", "Kategori": "Bebek Bezi",
                            "Ürün Adı": title, "Fiyat": fiyat, "Ürün Linki": full_link
                        })
                        eklenen_urun += 1
                except Exception:
                    continue
            print(f"[Hepsiburada] Sayfa {sayfa_no} üzerinden {eklenen_urun} ürün yakalandı.")
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
                query = """
                    INSERT INTO urunler (platform, kategori, urun_adi, fiyat, urun_linki)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (urun_linki) 
                    DO UPDATE SET 
                        fiyat = EXCLUDED.fiyat,
                        urun_adi = EXCLUDED.urun_adi,
                        guncellenme_tarihi = NOW();
                """
                cur.execute(query, (urun["Platform"], urun["Kategori"], urun["Ürün Adı"], urun["Fiyat"], urun["Ürün Linki"]))
                eklenen += 1
            except Exception as e:
                print(f"Supabase yazma hatası ({urun['Platform']}): {e}")
                conn.rollback()
                continue
                
        conn.commit()
        cur.close()
        conn.close()
        print(f"\n✅ {eklenen} ürün başarıyla Supabase'e kaydedildi!")
    except Exception as e:
        print(f"❌ Veritabanı bağlantı hatası: {e}")

if __name__ == "__main__":
    print("🚀 Hedefli Tarama Motorları Başlatılıyor...\n")
    toplam_urunler = []
    
    toplam_urunler.extend(trendyol_tara(1))
    toplam_urunler.extend(amazon_tara(1))
    toplam_urunler.extend(n11_tara(1))
    toplam_urunler.extend(hepsiburada_tara(1))
    
    print(f"\n🎉 Tarama tamamlandı! Toplam {len(toplam_urunler)} ürün yakalandı. Veritabanına yazılıyor...")
    save_to_db(toplam_urunler)