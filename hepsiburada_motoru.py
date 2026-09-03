from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import pandas as pd
import time
import re

def hepsiburada_tara(max_sayfa=3):
    all_products = []
    base_url = "https://www.hepsiburada.com/bebek-bezleri-c-60001049"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}?sayfa={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[Hepsiburada] Sayfa {sayfa_no} taranıyor: {url}")
            
            try:
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
            except Exception as e:
                print(f"[Hepsiburada] Sayfa yüklenemedi: {e}")
                continue

            if sayfa_no == 1:
                print("[Hepsiburada] Bot koruması kontrol ediliyor... (Engeli geçmek için 5 saniyen var)")
                time.sleep(5)
                try:
                    page.locator("text='Kabul Et'").first.click(timeout=3000)
                except:
                    pass
            
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
                    if title_el:
                        title = title_el.text.strip()
                    else:
                        text_blocks = list(card.stripped_strings)
                        uzun_metinler = [t for t in text_blocks if len(t) > 15 and 'TL' not in t]
                        title = uzun_metinler[0] if uzun_metinler else "İsim Bulunamadı"
                    
                    # --- YENİ MATEMATİKSEL FİYAT AYIKLAMA ALGORİTMASI ---
                    joined_text = " ".join(card.stripped_strings)
                    
                    # HTML'deki parçalanmış rakamları birleştir (örn: "645 , 11 TL" -> "645,11 TL")
                    joined_text = re.sub(r'(?<=\d)\s*,\s*(?=\d)', ',', joined_text)
                    joined_text = re.sub(r'(?<=\d)\s*\.\s*(?=\d)', '.', joined_text)
                    
                    # Metin içindeki tüm fiyatları (TL/₺) bul
                    matches = re.findall(r'((?:\d{1,3}(?:\.\d{3})*|\d+)(?:,\d+)?)\s*(?:TL|₺)', joined_text, re.IGNORECASE)
                    fiyat = "Fiyat Bulunamadı"
                    
                    if matches:
                        float_prices = []
                        for m in matches:
                            try:
                                # Stringi matematiksel kıyaslama için ondalık sayıya (float) çeviriyoruz
                                val = float(m.replace('.', '').replace(',', '.'))
                                float_prices.append((val, m))
                            except:
                                pass
                                
                        if float_prices:
                            max_val = max(float_prices, key=lambda x: x[0])[0]
                            
                            # Filtre 1: Birim fiyatları (örn: 5 TL/Adet) ve "Kazancınız 150 TL" etiketlerini çöpe at (Max fiyatın %40'ı sınırı)
                            main_prices = [p for p in float_prices if p[0] > (max_val * 0.4)]
                            
                            if main_prices:
                                # Filtre 2: Kalan asıl fiyatlar arasından her zaman en DÜŞÜK olanı (İndirimli Fiyatı) seç
                                best_match = min(main_prices, key=lambda x: x[0])
                                fiyat = best_match[1] + " TL"

                    # Temizlik
                    if title != "İsim Bulunamadı" and "Fiyat Bulunamadı" not in fiyat:
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
        output_file = "hepsiburada_urunler.xlsx"
        df.to_excel(output_file, index=False)
        print(f"\n✅ Hepsiburada tamamlandı! Toplam {len(df)} ürün '{output_file}' dosyasına kaydedildi.")
    else:
        print("\n❌ Hepsiburada'dan ürün çekilemedi.")

if __name__ == "__main__":
    hepsiburada_tara(max_sayfa=3)