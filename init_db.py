import re
import requests
import psycopg2

# Dosyanın çalıştığını anında görmek için test çıktısı
print("⚡ scraper.py dosyası başarıyla tetiklendi, işlemler başlıyor...")

SUPABASE_DB_URL = "postgresql://postgres.bwmcjllhzfcqncpefixp:ZggkAkebj4JA8gBt@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres"

def extract_unit_quantity(title):
    match = re.search(r'(\d+)\s*(?:adet|lu|lü|lı|li|ad)\b', title, re.IGNORECASE)
    if match:
        return int(match.group(1))
    numbers = re.findall(r'\b\d+\b', title)
    if numbers:
        for num in reversed(numbers):
            if int(num) > 10:
                return int(num)
    return 1

def run_scraper():
    content_id = "36462023"
    api_url = f"https://public.trendyol.com/discovery-web-productdetail-gwc-service/api/productDetail/{content_id}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Culture": "tr-TR"
    }

    print(f"🔎 Trendyol API'sinden canlı ürün verisi çekiliyor (Ürün ID: {content_id})...")
    
    try:
        res = requests.get(api_url, headers=headers, timeout=10)
        if res.status_code != 200:
            print(f"❌ API Bağlantı Hatası: HTTP {res.status_code}")
            return

        data = res.json().get("result", {})
        brand = data.get("brand", {}).get("name", "")
        name = data.get("name", "")
        title = f"{brand} {name}".strip()

        price_data = data.get("price", {})
        price = price_data.get("discountedPrice", {}).get("value") or price_data.get("sellingPrice", {}).get("value")

        if not price or not title:
            print("❌ Ürün verisi çekilemedi.")
            return

        unit_quantity = extract_unit_quantity(title)
        unit_price = round(float(price) / unit_quantity, 4)

        print(f"\n✅ Ürün Başlığı : {title}")
        print(f"💰 Paket Fiyatı : {price} TL")
        print(f"📦 Paket İçi Adet: {unit_quantity}")
        print(f"📊 Birim Fiyat  : {unit_price} TL/Adet\n")

        # Supabase Kaydı
        conn = psycopg2.connect(SUPABASE_DB_URL)
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM merchants WHERE name = 'Trendyol';")
        merchant = cursor.fetchone()
        merchant_id = merchant[0] if merchant else cursor.execute("INSERT INTO merchants (name) VALUES ('Trendyol') RETURNING id;").fetchone()[0]

        cursor.execute("SELECT id FROM categories WHERE slug = 'bebek-bezi';")
        cat_row = cursor.fetchone()
        category_id = cat_row[0] if cat_row else None

        cursor.execute("SELECT id FROM brands WHERE slug = 'prima';")
        brand_row = cursor.fetchone()
        brand_id = brand_row[0] if brand_row else None

        slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:250]
        url = f"https://www.trendyol.com/p-{content_id}"

        cursor.execute("""
            INSERT INTO products (title, slug, brand_id, category_id, unit_type, unit_quantity)
            VALUES (%s, %s, %s, %s, 'adet', %s)
            ON CONFLICT (slug) DO UPDATE SET unit_quantity = EXCLUDED.unit_quantity
            RETURNING id;
        """, (title, slug, brand_id, category_id, unit_quantity))
        product_id = cursor.fetchone()[0]

        cursor.execute("""
            INSERT INTO product_prices (product_id, merchant_id, merchant_product_url, current_price, unit_price, last_updated_at)
            VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (product_id, merchant_id)
            DO UPDATE SET current_price = EXCLUDED.current_price, unit_price = EXCLUDED.unit_price, last_updated_at = CURRENT_TIMESTAMP;
        """, (product_id, merchant_id, url, price, unit_price))

        conn.commit()
        cursor.close()
        conn.close()
        print("💾 Canlı Trendyol verisi Supabase veritabanına başarıyla yazıldı!")

    except Exception as e:
        print(f"❌ İşlem hatası: {e}")

# Doğrudan Fonksiyon Çağrısı
run_scraper()