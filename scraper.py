import re
import json
import time
import os
from datetime import datetime
from curl_cffi import requests
import psycopg2

SUPABASE_DB_URL = "postgresql://postgres.bwmcjllhzfcqncpefixp:ZggkAkebj4JA8gBt@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres"

PRODUCT_LIST = [
    {
        "name": "Prima Premium Care 4 Numara (126 Adet)",
        "category_slug": "bebek-bezi",
        "brand_slug": "prima",
        "keywords": ["prima", "bezi", "care", "4"],
        "urls": {
            "Trendyol": "https://www.trendyol.com/prima/bebek-bezi-premium-care-4-numara-126-adet-aylik-firsat-paketi-p-36462023",
            "N11": "https://www.n11.com/urun/prima-bebek-bezi-premium-care-4-numara-aylik-firsat-paketi-126-adet-1598809",
            "Amazon": "https://www.amazon.com.tr/dp/B0855HV1ZB",
            "Idefix": "https://www.idefix.com/prima-premium-care-4-beden-bebek-bezi-126-adet-maxi-aylik-firsat-paketi-p-382470",
            "Hepsiburada": "https://www.hepsiburada.com/prima-premiumcare-bebek-bezi-aylik-firsat-paketi-4-numara-126-adet-bez-p-HBV00000RFTBG"
        }
    }
]

def extract_unit_quantity(title):
    match = re.search(r'(\d+)\s*(?:adet|lu|lü|lı|li|ad|g|gr)\b', title, re.IGNORECASE)
    if match:
        return int(match.group(1))
    numbers = re.findall(r'\b\d+\b', title)
    if numbers:
        for num in reversed(numbers):
            if int(num) > 10:
                return int(num)
    return 1

def parse_turkish_price(price_input, is_amazon=False):
    if not price_input:
        return None
    
    # Temizlik ve string'e çevirme
    price_str = str(price_input).strip()
    
    if is_amazon:
        price_str = price_str.replace('.', '').replace(',', '.')
        try:
            val = float(price_str)
            if val > 50000:
                val = val / 100.0
            return val
        except ValueError:
            return None

    # TL, boşluk gibi metinleri temizleme
    price_str = re.sub(r'[^\d.,]', '', price_str)
    if not price_str:
        return None

    # Standart Türkçe Format Dönüşümü (Örn: 1.699,90 -> 1699.90 veya 1582 -> 1582.0)
    if '.' in price_str and ',' in price_str:
        price_str = price_str.replace('.', '').replace(',', '.')
    elif ',' in price_str:
        price_str = price_str.replace(',', '.')
    elif '.' in price_str:
        parts = price_str.split('.')
        if len(parts) == 2 and len(parts[1]) == 3:
            price_str = price_str.replace('.', '')
            
    try:
        val = float(price_str)
        # Mantıklı ürün fiyatı kontrolü (Bebek bezi paketi için 1000 TL - 5000 TL arası olmalı)
        if 800 <= val <= 5000:
            return val
        return None
    except ValueError:
        return None

def save_to_supabase(title, price, merchant_name, product_url, category_slug, brand_slug, keywords):
    title_lower = title.lower()
    match_found = any(kw.lower() in title_lower for kw in keywords)
    
    if not match_found or "loading" in title_lower:
        print(f"  ⚠️ [{merchant_name}] İptal: Yanlış/Eksik İçerik Yakalandı ({title[:35]}...)")
        return

    try:
        unit_quantity = extract_unit_quantity(title)
        unit_price = round(float(price) / unit_quantity, 4)

        print(f"  ✅ [{merchant_name}] Başlık    : {title[:45]}...")
        print(f"  💰 [{merchant_name}] Fiyat/Birim: {price} TL / {unit_price} TL")

        conn = psycopg2.connect(SUPABASE_DB_URL)
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM merchants WHERE name = %s;", (merchant_name,))
        merchant = cursor.fetchone()
        if merchant:
            merchant_id = merchant[0]
        else:
            cursor.execute("INSERT INTO merchants (name) VALUES (%s) RETURNING id;", (merchant_name,))
            merchant_id = cursor.fetchone()[0]

        cursor.execute("SELECT id FROM categories WHERE slug = %s;", (category_slug,))
        cat_row = cursor.fetchone()
        category_id = cat_row[0] if cat_row else None

        cursor.execute("SELECT id FROM brands WHERE slug = %s;", (brand_slug,))
        brand_row = cursor.fetchone()
        brand_id = brand_row[0] if brand_row else None

        slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:250]

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
        """, (product_id, merchant_id, product_url, price, unit_price))

        conn.commit()
        cursor.close()
        conn.close()
        print(f"  💾 [{merchant_name}] Supabase'e kaydedildi!\n")

    except Exception as e:
        print(f"  ❌ [{merchant_name}] Veritabanı Hatası: {e}\n")

def scrape_hepsiburada_custom_profile(url, cat_slug, brand_slug, keywords):
    custom_profile_dir = os.path.join(os.getcwd(), "hb_chrome_profile")
    
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=custom_profile_dir,
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--start-maximized"
                ],
                viewport=None
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            page.goto(url, timeout=40000, wait_until="domcontentloaded")
            time.sleep(3)

            content = page.content()
            title, price = None, None

            # 1. Hepsiburada Sepet / Kampanya Fiyatı (DOM Seçiciler)
            raw_hb_price = page.evaluate('''() => {
                const elCheckout = document.querySelector('[data-test-id="checkout-price"]');
                if (elCheckout && elCheckout.innerText) return elCheckout.innerText;
                
                const elCurrent = document.querySelector('[data-test-id="price-current-price"]');
                if (elCurrent && elCurrent.innerText) return elCurrent.innerText;
                
                const elOffering = document.querySelector('#offering-price');
                if (elOffering && elOffering.innerText) return elOffering.innerText;

                return null;
            }''')

            if raw_hb_price:
                price = parse_turkish_price(raw_hb_price)

            # 2. Next.js JSON Nesnesinden Sepet Fiyatını Çekme (Yedek)
            if not price:
                next_data = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', content, re.DOTALL)
                if next_data:
                    try:
                        js_val = json.loads(next_data.group(1))
                        product_data = js_val.get("props", {}).get("pageProps", {}).get("product", {})
                        title = product_data.get("name") or product_data.get("title")
                        
                        listings = product_data.get("listings", [])
                        if listings:
                            p_obj = listings[0].get("price", {})
                            for k in ["checkoutPrice", "basketPrice", "discountedPrice", "currentPrice", "value"]:
                                if p_obj.get(k):
                                    candidate = parse_turkish_price(p_obj.get(k))
                                    if candidate:
                                        price = candidate
                                        break
                    except Exception:
                        pass

            if not title:
                title = page.evaluate('''() => {
                    const h1 = document.querySelector('h1');
                    if (h1 && h1.innerText.trim()) return h1.innerText.trim();
                    return document.title.split('|')[0].trim();
                }''')

            context.close()

            if title and price and "loading" not in title.lower():
                save_to_supabase(title, price, "Hepsiburada", url, cat_slug, brand_slug, keywords)
            else:
                print(f"  ⚠️ [Hepsiburada] Fiyat ayıklanamadı.")
    except Exception as e:
        print(f"  ❌ [Hepsiburada] Profil Hatası: {e}")

def scrape_generic(url, merchant_name, cat_slug, brand_slug, keywords):
    if merchant_name == "Hepsiburada":
        scrape_hepsiburada_custom_profile(url, cat_slug, brand_slug, keywords)
        return

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "tr-TR,tr;q=0.9"
    }
    try:
        res = requests.get(url, headers=headers, impersonate="chrome120", timeout=15)
        if res.status_code != 200:
            print(f"  ⚠️ [{merchant_name}] Sayfa açılamadı (HTTP Status: {res.status_code})")
            return

        title, price = None, None
        is_amazon = (merchant_name == "Amazon")

        scripts = re.findall(r'<script type="application/ld\+json">(.*?)</script>', res.text, re.DOTALL)
        for s in scripts:
            try:
                data = json.loads(s)
                if isinstance(data, list): data = data[0]
                if isinstance(data, dict) and (data.get("@type") == "Product" or "Product" in str(data.get("@type"))):
                    title = title or data.get("name")
                    offers = data.get("offers", {})
                    if isinstance(offers, list): offers = offers[0]
                    if isinstance(offers, dict):
                        raw_p = offers.get("price") or offers.get("lowPrice")
                        price = parse_turkish_price(raw_p, is_amazon)
            except Exception:
                pass

        if not title:
            m_t = re.search(r'<meta\s+property="og:title"\s+content="(.*?)"', res.text, re.IGNORECASE) or \
                  re.search(r'<title>(.*?)</title>', res.text, re.IGNORECASE)
            if m_t:
                title = m_t.group(1).split('|')[0].split('-')[0].split('Fiyatları')[0].strip()

        if not price:
            m_p = re.search(r'"priceAmount"\s*:\s*"?([\d.,]+)"?', res.text) or \
                  re.search(r'class="a-price-whole">([\d.,]+)', res.text) or \
                  re.search(r'"displayPrice"\s*:\s*"?([\d.,]+)"?', res.text) or \
                  re.search(r'"price"\s*:\s*"?([\d.,]+)"?', res.text) or \
                  re.search(r'<ins[^>]*>([\d.,\sTL]+)</ins>', res.text, re.IGNORECASE)
            if m_p:
                price = parse_turkish_price(m_p.group(1), is_amazon)

        if title and price:
            save_to_supabase(title, price, merchant_name, url, cat_slug, brand_slug, keywords)
        else:
            print(f"  ⚠️ [{merchant_name}] Veri ayıklanamadı.")

    except Exception as e:
        print(f"  ❌ [{merchant_name}] Bağlantı Hatası: {e}")

if __name__ == "__main__":
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"⚡ [{now_str}] Hassas Fiyat Doğrulama Taraması Başlatılıyor...\n")
    
    for idx, item in enumerate(PRODUCT_LIST, 1):
        print(f"📌 [{idx}/{len(PRODUCT_LIST)}] {item['name']}")
        
        for store_name, store_url in item["urls"].items():
            scrape_generic(store_url, store_name, item["category_slug"], item["brand_slug"], item["keywords"])
            time.sleep(1)
            
    print("🎉 Tüm mağazaların fiyat taraması tamamlandı!")
