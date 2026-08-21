import re
import time
import urllib.parse
import psycopg2
from playwright.sync_api import sync_playwright

SUPABASE_DB_URL = "postgresql://postgres.bwmcjllhzfcqncpefixp:ZggkAkebj4JA8gBt@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres"

PRODUCTS_CATALOG = [
    {
        "name": "Prima Premium Care 4 Numara Maxi 126 Adet",
        "category_slug": "bebek-bezi",
        "brand_slug": "prima",
        "keywords": "Prima Premium Care 4 Numara Maxi 126"
    },
    {
        "name": "Molfix 4 Numara Maxi 100 Adet Bebek Bezi",
        "category_slug": "bebek-bezi",
        "brand_slug": "molfix",
        "keywords": "Molfix 4 Numara Maxi 100"
    },
    {
        "name": "Sleepy Extra 4 Numara Maxi 100 Adet Bebek Bezi",
        "category_slug": "bebek-bezi",
        "brand_slug": "sleepy",
        "keywords": "Sleepy Extra 4 Numara 100"
    },
    {
        "name": "Aptamil 1 Bebek Sütü 800 gr",
        "category_slug": "bebek-mamasi",
        "brand_slug": "aptamil",
        "keywords": "Aptamil 1 Bebek Sütü 800 gr"
    },
    {
        "name": "Arı Mama 12 Vitaminli Sütlü Pirinç Unu 250 gr 6 Adet",
        "category_slug": "bebek-mamasi",
        "brand_slug": "ari",
        "keywords": "Arı Mama Sütlü Pirinç Unu 250 gr 6"
    }
]

def clean_price(text):
    if not text:
        return None
    t = str(text).replace('TL', '').replace('₺', '').replace('\xa0', ' ').strip()
    # Sadece rakam, nokta ve virgülü tut
    t = re.sub(r'[^\d,\.]', '', t)
    try:
        if ',' in t and '.' in t:
            # "1.576,72" -> "1576.72"
            t = t.replace('.', '').replace(',', '.')
        elif ',' in t:
            t = t.replace(',', '.')
        val = float(t)
        # Bebek bezi ve maması için mantıklı fiyat aralığı filtresi
        if 15.0 <= val <= 5000.0:
            return round(val, 2)
        elif val > 5000.0:
            # PttAVM gibi yerlerde "82269" -> 822.69 düzeltmesi
            val_corrected = val / 100.0
            if 15.0 <= val_corrected <= 5000.0:
                return round(val_corrected, 2)
    except Exception:
        pass
    return None

def save_to_database(product_name, category_slug, brand_slug, store_name, price, product_url):
    if not price or price <= 0 or not product_url:
        return
    try:
        conn = psycopg2.connect(SUPABASE_DB_URL)
        cur = conn.cursor()
        slug = re.sub(r'[^a-z0-9]+', '-', product_name.lower()).strip('-')[:80]
        query = """
            INSERT INTO product_prices (product_name, category_slug, brand_slug, store_name, price, product_url, slug)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (slug, store_name) 
            DO UPDATE SET price = EXCLUDED.price, product_url = EXCLUDED.product_url, updated_at = NOW();
        """
        cur.execute(query, (product_name, category_slug, brand_slug, store_name, price, product_url, slug))
        conn.commit()
        cur.close()
        conn.close()
        print(f"      ✅ [{store_name:<11}] ₺{price:<8.2f} | {product_url[:50]}...")
    except Exception as e:
        print(f"      ❌ DB Hatası: {e}")

# 1. HEPSİBURADA
def fetch_hepsiburada(context, query):
    page = context.new_page()
    try:
        url = f"https://www.hepsiburada.com/ara?q={urllib.parse.quote(query)}"
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        data = page.evaluate('''() => {
            let cards = document.querySelectorAll('li[id^="i"], article, [data-test-id="product-card-item"], div[class*="ProductList"] li');
            for (let card of cards) {
                let linkEl = card.querySelector('a');
                let priceEl = card.querySelector('[data-test-id="price-current-price"], [data-test-id="price"], div[data-test-id*="price"]');
                if (linkEl && priceEl) {
                    return {
                        href: linkEl.getAttribute('href') || '',
                        priceText: priceEl.innerText || ''
                    };
                }
            }
            return null;
        }''')

        if data and data.get("href"):
            raw_href = data["href"]
            full_url = raw_href if raw_href.startswith("http") else f"https://www.hepsiburada.com{raw_href}"
            price = clean_price(data.get("priceText"))
            if price:
                page.close()
                return {"store": "Hepsiburada", "price": price, "url": full_url}
    except Exception:
        pass
    try: page.close()
    except Exception: pass
    return None

# 2. TRENDYOL
def fetch_trendyol(context, query):
    page = context.new_page()
    try:
        url = f"https://www.trendyol.com/sr?q={urllib.parse.quote(query)}"
        page.goto(url, timeout=35000, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        page.evaluate("window.scrollBy(0, 400)")
        page.wait_for_timeout(1000)

        data = page.evaluate('''() => {
            let cards = document.querySelectorAll('.p-card-wrppr, div[data-id], .product-down, [class*="product-card"], .prdct-cntnr-wrppr > div');
            for (let card of cards) {
                let linkEl = card.querySelector('a');
                let priceEl = card.querySelector('.prc-box-dscntd, .discounted-price, [class*="price-box"], [class*="product-price"], .prc-box-sllng, .prc-box-orgnl');
                if (linkEl && priceEl) {
                    let href = linkEl.getAttribute('href') || '';
                    let pText = priceEl.innerText || '';
                    if (href && pText) return { href, priceText: pText };
                }
            }
            return null;
        }''')

        if data and data.get("href"):
            raw_href = data["href"]
            full_url = raw_href if raw_href.startswith("http") else f"https://www.trendyol.com{raw_href}"
            price = clean_price(data.get("priceText"))
            if price:
                page.close()
                return {"store": "Trendyol", "price": price, "url": full_url}
    except Exception:
        pass
    try: page.close()
    except Exception: pass
    return None

# 3. AMAZON TR
def fetch_amazon(context, query):
    page = context.new_page()
    try:
        url = f"https://www.amazon.com.tr/s?k={urllib.parse.quote(query)}"
        page.goto(url, timeout=35000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        data = page.evaluate('''() => {
            let cards = document.querySelectorAll('div[data-asin]:not([data-asin=""]), div[data-component-type="s-search-result"]');
            for (let card of cards) {
                let linkEl = card.querySelector('h2 a, a.a-link-normal[href*="/dp/"]');
                let priceEl = card.querySelector('.a-price .a-offscreen, .a-price');
                let whole = card.querySelector('.a-price-whole');
                let fraction = card.querySelector('.a-price-fraction');
                
                let pText = "";
                if (whole) {
                    pText = whole.innerText.replace('.', '') + ',' + (fraction ? fraction.innerText : '00');
                } else if (priceEl) {
                    pText = priceEl.innerText;
                }

                if (linkEl && pText) {
                    return {
                        href: linkEl.getAttribute('href') || '',
                        priceText: pText
                    };
                }
            }
            return null;
        }''')

        if data and data.get("href"):
            raw_href = data["href"].split('?')[0]
            full_url = raw_href if raw_href.startswith("http") else f"https://www.amazon.com.tr{raw_href}"
            price = clean_price(data.get("priceText"))
            if price:
                page.close()
                return {"store": "Amazon TR", "price": price, "url": full_url}
    except Exception:
        pass
    try: page.close()
    except Exception: pass
    return None

# 4. PTTAVM
def fetch_pttavm(context, query):
    page = context.new_page()
    try:
        url = f"https://www.pttavm.com/arama?q={urllib.parse.quote(query)}"
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        data = page.evaluate('''() => {
            let cards = document.querySelectorAll('div[class*="product-card"], a[href*="-p-"]');
            for (let card of cards) {
                let linkEl = card.tagName === 'A' ? card : card.querySelector('a');
                let priceEl = card.querySelector('[class*="price"], span[class*="price"]');
                if (linkEl && priceEl) {
                    return {
                        href: linkEl.getAttribute('href') || '',
                        priceText: priceEl.innerText || ''
                    };
                }
            }
            return null;
        }''')

        if data and data.get("href"):
            raw_href = data["href"]
            full_url = raw_href if raw_href.startswith("http") else f"https://www.pttavm.com{raw_href}"
            price = clean_price(data.get("priceText"))
            if price:
                page.close()
                return {"store": "PttAVM", "price": price, "url": full_url}
    except Exception:
        pass
    try: page.close()
    except Exception: pass
    return None

# 5. EBEBEK
def fetch_ebebek(context, query):
    page = context.new_page()
    try:
        url = f"https://www.e-bebek.com/search?text={urllib.parse.quote(query)}"
        page.goto(url, timeout=35000, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        page.evaluate("window.scrollBy(0, 300)")

        data = page.evaluate('''() => {
            let cards = document.querySelectorAll('eb-product-list-item, .product-item, .product-card, div.product-list-item, article');
            for (let card of cards) {
                let linkEl = card.querySelector('a');
                let priceEl = card.querySelector('.price, .product-price, .product-price-current, [class*="price"]');
                if (linkEl && priceEl) {
                    return {
                        href: linkEl.getAttribute('href') || '',
                        priceText: priceEl.innerText || ''
                    };
                }
            }
            return null;
        }''')

        if data and data.get("href"):
            raw_href = data["href"]
            full_url = raw_href if raw_href.startswith("http") else f"https://www.e-bebek.com{raw_href}"
            price = clean_price(data.get("priceText"))
            if price:
                page.close()
                return {"store": "eBebek", "price": price, "url": full_url}
    except Exception:
        pass
    try: page.close()
    except Exception: pass
    return None

def run_crawler():
    print("🚀 DOĞRUDAN MAĞAZA VE FİYAT BOTU BAŞLATILDI...\n")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="tr-TR"
        )

        for item in PRODUCTS_CATALOG:
            print(f"\n📦 Aranıyor: {item['name']}")

            # 1. Hepsiburada
            res_hb = fetch_hepsiburada(context, item["keywords"])
            if res_hb:
                save_to_database(item["name"], item["category_slug"], item["brand_slug"], res_hb["store"], res_hb["price"], res_hb["url"])
            else:
                print("      ❌ Hepsiburada: Sonuç bulunamadı.")

            # 2. Trendyol
            res_ty = fetch_trendyol(context, item["keywords"])
            if res_ty:
                save_to_database(item["name"], item["category_slug"], item["brand_slug"], res_ty["store"], res_ty["price"], res_ty["url"])
            else:
                print("      ❌ Trendyol: Sonuç bulunamadı.")

            # 3. Amazon TR
            res_amz = fetch_amazon(context, item["keywords"])
            if res_amz:
                save_to_database(item["name"], item["category_slug"], item["brand_slug"], res_amz["store"], res_amz["price"], res_amz["url"])
            else:
                print("      ❌ Amazon TR: Sonuç bulunamadı.")

            # 4. PttAVM
            res_ptt = fetch_pttavm(context, item["keywords"])
            if res_ptt:
                save_to_database(item["name"], item["category_slug"], item["brand_slug"], res_ptt["store"], res_ptt["price"], res_ptt["url"])
            else:
                print("      ❌ PttAVM: Sonuç bulunamadı.")

            # 5. eBebek
            res_ebk = fetch_ebebek(context, item["keywords"])
            if res_ebk:
                save_to_database(item["name"], item["category_slug"], item["brand_slug"], res_ebk["store"], res_ebk["price"], res_ebk["url"])
            else:
                print("      ❌ eBebek: Sonuç bulunamadı.")

            time.sleep(1)

        browser.close()
    print("\n🎉 Tüm fiyatlar ve doğrudan linkler başarıyla güncellendi!")

if __name__ == "__main__":
    run_crawler()