from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import os
from supabase import create_client, Client

def amazon_tara(max_sayfa=3):
    all_products = []
    base_url = "https://www.amazon.com.tr/s?k=bebek+bezi&rh=n%3A12466391031"
    
    with sync_playwright() as p:
        # Bulutta çalışacağı için headless=True yapıyoruz
        browser = p.chromium.launch(headless=True, slow_mo=70)
        
        # Gerçek bilgisayar gibi maskeleme
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            locale="tr-TR",
            timezone_id="Europe/Istanbul"
        )
        page = context.new_page()
        
        # SİHİRLİ DOKUNUŞ: Amazon'un bot korumasını aşmak için görünmezlik pelerini
        stealth_sync(page)
        
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}&page={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[Amazon TR] Sayfa {sayfa_no} taranıyor: {url}")
            
            try:
                # Sanki linke Google'dan tıklamışız gibi yapıyoruz (referer)
                page.goto(url, timeout=60000, wait_until="domcontentloaded", referer="https://www.google.com.tr/")
            except Exception as e:
                print(f"[Amazon TR] Sayfa yüklenemedi: {e}")
                continue

            # İnsan gibi doğal bir geçiş süresi (Captcha'yı elinle çözemeyeceğin için süreyi kısalttık)
            time.sleep(4)
            
            try:
                # Varsa çerez onayını kapat
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

   if all_products:
        # GitHub Secrets'tan URL ve KEY'i çek
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        
        if not url or not key:
            print("❌ Supabase kimlik bilgileri eksik! Veritabanına bağlanılamadı.")
            return
            
        supabase: Client = create_client(url, key)
        
        eklenen_guncellenen = 0
        for urun in all_products:
            data = {
                "platform": urun["Platform"],
                "kategori": urun["Kategori"],
                "urun_adi": urun["Ürün Adı"],
                "fiyat": urun["Fiyat"],
                "urun_linki": urun["Ürün Linki"]
            }
            try:
                # on_conflict="urun_linki" parametresi, aynı linkteki ürünün sadece fiyatını günceller
                supabase.table("urunler").upsert(data, on_conflict="urun_linki").execute()
                eklenen_guncellenen += 1
            except Exception as e:
                print(f"Supabase yazma hatası ({urun['Platform']}): {e}")
                
        print(f"\n✅ {eklenen_guncellenen} ürün doğrudan Supabase veritabanına basıldı.")
    else:
        print("\n❌ Ürün bulunamadı, veritabanı işlemi atlandı.")

if __name__ == "__main__":
    amazon_tara(max_sayfa=3)