import os
import re
import time
import psycopg2
from playwright.sync_api import sync_playwright

# Şifreyi koddan sildik, artık GitHub Secrets'tan güvenle çekecek
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")

# ... (Kategoriler ve kodun geri kalanı aynı kalacak) ...

# Supabase Veritabanı Bağlantısını GitHub Secrets'tan Çekiyoruz
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")

def trendyol_tara(max_sayfa=3):
    all_products = []
    base_url = "https://www.trendyol.com/bebek-bezi-x-c1363"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}?pi={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"[Trendyol] Sayfa {sayfa_no} taranıyor...")
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            
            if sayfa_no == 1:
                try:
                    page.locator("text='Tüm Tanımlama Bilgilerini Kabul Et'").click(timeout=5000)
                    time.sleep(1)
                except:
                    pass
            
            # Sayfayı kademeli kaydır
            for _ in range(3):
                page.mouse.wheel(0, 1500)
                time.sleep(2)
                
            soup = BeautifulSoup(page.content(), 'html.parser')
            links = soup.find_all('a', href=True)
            
            for link in links:
                href = link['href']
                if '-p-' in href and '/yorumlar' not in href:
                    text_blocks = list(link.stripped_strings)
                    
                    # Fiyat içeren stringleri bul (örn: 1.310,36 TL)
                    fiyatlar = [t for t in text_blocks if 'TL' in t]
                    
                    if fiyatlar:
                        full_link = "https://www.trendyol.com" + href if href.startswith('/') else href
                        
                        # Son bulunan fiyat genelde sepetteki/indirimli veya Plus fiyattır
                        guncel_fiyat = fiyatlar[-1]
                        eski_fiyat = fiyatlar[0] if len(fiyatlar) > 1 else guncel_fiyat
                        
                        # Başlıktan temizlenecek gereksiz filtre kelimeleri
                        stop_words = [
                            'TL', 'Sepete Ekle', 'Kargo Bedava', 'Hızlı Teslimat', 
                            'Sponsorlu', 'Peşin Fiyatına', 'Son 30 Günün En Düşük Fiyatı', 
                            'Avantajlı Ürün', 'Kuponlu Ürün', "Trendyol Plus'a Özel", "Plus'a Özel"
                        ]
                        
                        name_parts = [t for t in text_blocks if not any(sw.lower() in t.lower() for sw in stop_words)]
                        title = " ".join(name_parts[:4]) if name_parts else "İsim Bulunamadı"
                        
                        # Artık metinleri temizle
                        title = re.sub(r'\s+', ' ', title).strip()
                        
                        all_products.append({
                            "Platform": "Trendyol",
                            "Kategori": "Bebek Bezi",
                            "Ürün Adı": title,
                            "Fiyat": guncel_fiyat,
                            "Liste Fiyatı": eski_fiyat,
                            "Plus / İndirim Var mı": "Evet" if len(fiyatlar) > 1 or "Plus" in " ".join(text_blocks) else "Hayır",
                            "Ürün Linki": full_link
                        })
                        
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
    trendyol_tara(max_sayfa=3)