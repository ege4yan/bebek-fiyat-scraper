from curl_cffi import requests
from bs4 import BeautifulSoup
import re
import psycopg2
import time

SUPABASE_DB_URL = "postgresql://postgres.bwmcjllhzfcqncpefixp:ZggkAkebj4JA8gBt@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres"

MASTER_CATALOG = [
    {
        "name": "Molfix 4 Numara Maxi 100 Adet Bebek Bezi",
        "category_slug": "bebek-bezi", "brand_slug": "molfix",
        "min_price": 300, "max_price": 950,
        "stores": [
            {"name": "Hepsiburada", "url": "https://www.hepsiburada.com/molfix-bebek-bezi-3d-4-beden-maxi-7-14-kg-100lu-ultra-firsat-paketi-p-HBV00000Q2C86", "fallback": 726.50},
            {"name": "Amazon TR", "url": "https://www.amazon.com.tr/dp/B09Y2D71VK", "fallback": 719.90},
            {"name": "eBebek", "url": "https://www.e-bebek.com/molfix-bebek-bezi-4-beden-maxi-ultra-firsat-paketi-7--14-kg-100-p-mol-5057001", "fallback": 799.90}
        ]
    },
    {
        "name": "Prima Premium Care 4 Numara Maxi 126 Adet Bebek Bezi",
        "category_slug": "bebek-bezi", "brand_slug": "prima",
        "min_price": 1000, "max_price": 2500,
        "stores": [
            {"name": "Hepsiburada", "url": "https://www.hepsiburada.com/prima-premiumcare-bebek-bezi-aylik-firsat-paketi-4-numara-126-adet-bez-p-HBV00000RFTBG", "fallback": 1576.72},
            {"name": "Amazon TR", "url": "https://www.amazon.com.tr/dp/B0855HV1ZB", "fallback": 1649.00}
        ]
    },
    {
        "name": "Aptamil 1 Bebek Sütü 800 gr",
        "category_slug": "bebek-mamasi", "brand_slug": "aptamil",
        "min_price": 700, "max_price": 1500,
        "stores": [
            {"name": "Hepsiburada", "url": "https://www.hepsiburada.com/aptamil-1-bebek-sutu-800-gr-0-6-ay-pm-HB00000628G1", "fallback": 1029.90},
            {"name": "Amazon TR", "url": "https://www.amazon.com.tr/dp/B07N4R8G12", "fallback": 1040.00},
            {"name": "eBebek", "url": "https://www.e-bebek.com/aptamil-1-bebek-sutu-800-gr-p-apt-8001", "fallback": 1049.90}
        ]
    },
    {
        "name": "Philips Avent Natural PP Biberon 260 ml",
        "category_slug": "biberon", "brand_slug": "philips-avent",
        "min_price": 150, "max_price": 600,
        "stores": [
            {"name": "Hepsiburada", "url": "https://www.hepsiburada.com/philips-avent-natural-biberon-260-ml-pp-p-HBV000005WZY9", "fallback": 349.90},
            {"name": "Amazon TR", "url": "https://www.amazon.com.tr/dp/B008MWT3J8", "fallback": 329.90},
            {"name": "eBebek", "url": "https://www.e-bebek.com/philips-avent-natural-biberon-260-ml-p-pav-scf69317", "fallback": 359.90}
        ]
    },
    {
        "name": "Doona Yeni Nesil Bebek Arabası",
        "category_slug": "puset", "brand_slug": "doona",
        "min_price": 12000, "max_price": 25000,
        "stores": [
            {"name": "eBebek", "url": "https://www.e-bebek.com/doona-yeni-nesil-bebek-arabasi-p-don-1001", "fallback": 18500.00},
            {"name": "Hepsiburada", "url": "https://www.hepsiburada.com/doona-yeni-nesil-bebek-arabasi-p-HBV00000Q8W9E", "fallback": 18999.00}
        ]
    }
]

def clean_price(text):
    if not text: return None
    t = str(text).replace('TL', '').replace('₺', '').replace('\xa0', ' ').strip()
    t = re.sub(r'[^\d,\.]', '', t)
    try:
        if ',' in t and '.' in t: t = t.replace('.', '').replace(',', '.')
        elif ',' in t: t = t.replace(',', '.')
        return round(float(t), 2)
    except: return None

def get_live_price(url):
    try:
        response = requests.get(url, impersonate="chrome110", timeout=15)
        if response.status_code == 200:
            
            # 1. ÖNCELİK: Sepete özel veya aktif indirimli fiyat (Hepsiburada vb. için)
            basket_match = re.search(r'"basketDiscountedPrice"\s*:\s*"?(\d+(?:\.\d+)?)"?', response.text)
            if basket_match: return float(basket_match.group(1))
            
            discount_match = re.search(r'"discountedPrice"\s*:\s*"?(\d+(?:\.\d+)?)"?', response.text)
            if discount_match: return float(discount_match.group(1))

            # 2. ÖNCELİK: Amazon Özel Fiyat Çekimi
            soup = BeautifulSoup(response.text, 'html.parser')
            amz_price = soup.find('span', class_='a-price-whole')
            if amz_price: return clean_price(amz_price.text)

            # 3. ÖNCELİK: Standart Listeleme Fiyatı (Üsttekiler yoksa devreye girer)
            match_standard = re.search(r'"currentPrice"\s*:\s*"?(\d+(?:\.\d+)?)"?', response.text)
            if match_standard: return float(match_standard.group(1))
            
            match_fallback = re.search(r'"price"\s*:\s*"?(\d+(?:\.\d+)?)"?', response.text)
            if match_fallback: return float(match_fallback.group(1))

    except:
        pass
    return None

def update_database():
    print("🚀 İNDİRİM AVCISI ve AKILLI KALKAN MOTORU BAŞLATILDI...\n")
    
    conn = psycopg2.connect(SUPABASE_DB_URL)
    cur = conn.cursor()
    cur.execute("TRUNCATE TABLE product_prices;")
    conn.commit()

    for product in MASTER_CATALOG:
        print(f"📦 Ürün: {product['name']}")
        slug = re.sub(r'[^a-z0-9]+', '-', product["name"].lower()).strip('-')[:80]
        
        for store in product["stores"]:
            live_price = get_live_price(store["url"])
            
            if live_price and (live_price < product["min_price"] or live_price > product["max_price"]):
                print(f"      ⚠️ [REDDEDİLDİ] {store['name']} fiyatı ({live_price} ₺) reklam veya alakasız ürün!")
                live_price = None 
                
            final_price = live_price if live_price else store["fallback"]
            status = "🟢 CANLI" if live_price else "🟡 YEDEK"
            
            try:
                query = "INSERT INTO product_prices (product_name, category_slug, brand_slug, store_name, price, product_url, slug) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                cur.execute(query, (product["name"], product["category_slug"], product["brand_slug"], store["name"], final_price, store["url"], slug))
                conn.commit()
                print(f"      [{status}] {store['name']:<15} ₺{final_price:<7.2f} Kaydedildi!")
            except Exception as e:
                pass
            time.sleep(1)

    cur.close()
    conn.close()
    print("\n🎉 Tüm veriler Sepet İndirimleri dahil edilerek Supabase'e işlendi!")

if __name__ == "__main__":
    update_database()