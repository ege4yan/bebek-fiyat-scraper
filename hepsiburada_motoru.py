from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync
from bs4 import BeautifulSoup
import pandas as pd
import time
import re

def hepsiburada_tara(max_sayfa=3):
    all_products = []
    base_url = "https://www.hepsiburada.com/bebek-bezleri-c-60001049"
    
    with sync_playwright() as p:
        # Bulutta çalışacağı için headless=True yapıyoruz
        browser = p.chromium.launch(headless=True, slow_mo=100)
        
        # Gerçek bir Windows makinesi gibi görünmesi için maskeleme parametreleri
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            java_script_enabled=True,
            bypass_csp=True, # Güvenlik politikalarını esnet
            locale="tr-TR",
            timezone_id="Europe/Istanbul"
        )
        
        page = context.new_page()
        
        # SİHİRLİ DOKUNUŞ: Tarayıcıyı WebDriver testlerinden kaçırır
        stealth_sync(page)
        
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}?sayfa={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[Hepsiburada] Sayfa {sayfa_no} taranıyor: {url}")
            
            try:
                # Referer ekleyerek sanki Google'dan geliyormuşuz izlenimi veriyoruz
                page.goto(url, timeout=60000, wait_until="domcontentloaded", referer="https://www.google.com.tr/")
            except Exception as e:
                print(f"[Hepsiburada] Sayfa yüklenemedi: {e}")
                continue

            # Bulutta elinle Captcha çözemeyeceğin için bekleme süresini siliyoruz, 
            # doğrudan sayfa kaydırmaya ve veri çekmeye geçiyoruz.
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
                    
                    # Matematiksel fiyat ayıklama
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

    if all_products:
        df = pd.DataFrame(all_products).drop_duplicates(subset=['Ürün Linki'])
        df.to_excel("hepsiburada_urunler.xlsx", index=False)
        print(f"\n✅ Hepsiburada tamamlandı! Toplam {len(df)} ürün kaydedildi.")
    else:
        print("\n❌ Hepsiburada Captcha duvarına takıldı.")

if __name__ == "__main__":
    hepsiburada_tara(max_sayfa=3)