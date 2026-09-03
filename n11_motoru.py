from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import pandas as pd
import time
import re

def n11_tara(max_sayfa=3):
    all_products = []
    base_url = "https://www.n11.com/bebek-bezi-ve-islak-mendil/bebek-bezi" 
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        
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
                        birim_fiyat = "-"
                        
                        for f in fiyatlar:
                            if '/' in f or 'Adet' in f or 'adet' in f:
                                birim_fiyat = re.sub(r'\s+', ' ', f).strip()
                            else:
                                toplam_fiyat = re.sub(r'\s+', ' ', f).strip()
                        
                        if toplam_fiyat == "Fiyat Bulunamadı" and fiyatlar:
                            olasi_toplam = [f for f in fiyatlar if '/' not in f]
                            if olasi_toplam:
                                toplam_fiyat = re.sub(r'\s+', ' ', olasi_toplam[-1]).strip()
                                
                        # Sadece fiyat ve adet bloklarını ayıklayıp başlık bloklarını birleştiriyoruz
                        raw_title_blocks = [t for t in text_blocks if 'TL' not in t and '/' not in t]
                        raw_title = " ".join(raw_title_blocks)
                        
                        # İstenmeyen reklam kelimelerini tüm metni çöpe atmadan temizle (Cımbızlama)
                        silinecekler = [
                            'ÜCRETSİZ KARGO', 'SÜPER', 'SEPETTE', 'günün en düşük fiyatı!', 
                            'Hızlı Teslimat', 'Sponsorlu', 'Yeni', 'Tükendi', 'Sepete Ekle'
                        ]
                        
                        title = raw_title
                        for kelime in silinecekler:
                            # Büyük/küçük harf duyarlılığını kaldırarak kelimeyi metnin içinden siler
                            title = re.sub(rf'(?i){re.escape(kelime)}', '', title)
                            
                        # Fazladan boşlukları temizle
                        title = re.sub(r'\s+', ' ', title).strip()
                        
                        if len(title) > 10:
                            all_products.append({
                                "Platform": "N11",
                                "Kategori": "Bebek Bezi",
                                "Ürün Adı": title,
                                "Toplam Fiyat": toplam_fiyat,
                                "Birim Fiyatı": birim_fiyat,
                                "Ürün Linki": full_link
                            })
                            eklenen_urun += 1
            
            print(f"[N11] Sayfa {sayfa_no} üzerinden {eklenen_urun} ürün yakalandı.")
            
        browser.close()
        
    if all_products:
        df = pd.DataFrame(all_products).drop_duplicates(subset=['Ürün Linki'])
        output_file = "n11_urunler.xlsx"
        df.to_excel(output_file, index=False)
        print(f"\n✅ N11 tamamlandı! Toplam {len(df)} ürün '{output_file}' dosyasına kaydedildi.")
    else:
        print("\n❌ N11'den ürün çekilemedi.")

if __name__ == "__main__":
    n11_tara(max_sayfa=3)