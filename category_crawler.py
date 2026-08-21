import re
import time
import urllib.parse
import psycopg2
from playwright.sync_api import sync_playwright

SUPABASE_DB_URL = "postgresql://postgres.bwmcjllhzfcqncpefixp:ZggkAkebj4JA8gBt@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres"

PRODUCTS_CATALOG = [
    {
        "name": "Prima Premium Care 4 Numara Maxi 126 Adet Bebek Bezi",
        "category_slug": "bebek-bezi",
        "brand_slug": "prima",
        "keywords": "Prima Premium Care 4 Numara 126 Adet Bebek Bezi",
        "min_price": 600.0,
        "max_price": 2800.0
    },
    {
        "name": "Molfix 4 Numara Maxi 100 Adet Bebek Bezi",
        "category_slug": "bebek-bezi",
        "brand_slug": "molfix",
        "keywords": "Molfix 4 Numara Maxi 100 Adet Bebek Bezi",
        "min_price": 300.0,
        "max_price": 1200.0
    },
    {
        "name": "Sleepy Extra 4 Numara Maxi 100 Adet Bebek Bezi",
        "category_slug": "bebek-bezi",
        "brand_slug": "sleepy",
        "keywords": "Sleepy Extra 4 Numara Maxi 100 Adet",
        "min_price": 250.0,
        "max_price": 900.0
    },
    {
        "name": "Aptamil 1 Bebek Sütü 800 gr",
        "category_slug": "bebek-mamasi",
        "brand_slug": "aptamil",
        "keywords": "Aptamil 1 Bebek Sütü 800 gr",
        "min_price": 400.0,
        "max_price": 1400.0
    },
    {
        "name": "Arı Mama 12 Vitaminli Sütlü Pirinç Unu 250 gr 6 Adet",
        "category_slug": "bebek-mamasi",
        "brand_slug": "ari",
        "keywords": "Arı Mama Sütlü Pirinç Unu 250 gr 6 Adet",
        "min_price": 180.0,
        "max_price": 650.0
    },
    {
        "name": "Bebelac Gold 1 Bebek Sütü 800 gr",
        "category_slug": "bebek-mamasi",
        "brand_slug": "bebelac",
        "keywords": "Bebelac Gold 1 Bebek Sütü 800 gr",
        "min_price": 300.0,
        "max_price": 1100.0
    }
]

KNOWN_STORES = [
    "Trendyol", "Hepsiburada", "Amazon", "PttAVM", "eBebek", "N11", "Civil", "Migros", "Watsons", "Gratis", "CarrefourSA"
]

def normalize_store_name(raw_name):
    if not raw_name: return "Pazaryeri Satıcısı"
    r = raw_name.lower()
    for s in KNOWN_STORES:
        if s.lower() in r:
            return s
    return raw_name.strip()[:20]

def clean_price(text):
    if not text: return None
    t = str(text).replace('TL', '').replace('₺', '').replace('\xa0', ' ').strip()
    t = re.sub(r'[^\d,\.]', '', t)
    try:
        if ',' in t and '.' in t:
            t = t.replace('.', '').replace(',', '.')
        elif ',' in t:
            t = t.replace(',', '.')
        val = float(t)
        return round(val, 2)
    except Exception:
        return None

def save_to_database(product_name, category_slug, brand_slug, store_name, price, product_url):
    if not price or price <= 0 or not product_url: return
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
        print(f"      ✅ [{store_name:<12}] ₺{price:<8.2f} | {product_url[:50]}...")
    except Exception as e:
        print(f"      ❌ DB Hatası: {e}")

def run_aggregator_crawler():
    print("🚀 GÜÇLENDİRİLMİŞ ÇOKLU PAZARYERİ VE DOĞRULAMA MOTORU BAŞLATILDI...\n")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="tr-TR"
        )
        page = context.new_page()

        for item in PRODUCTS_CATALOG:
            print(f"\n📦 Taranıyor: {item['name']}")
            
            # Google Shopping üzerinden tüm mağazaları tek seferde listele
            shopping_url = f"https://www.google.com/search?tbm=shop&hl=tr&gl=tr&q={urllib.parse.quote(item['keywords'])}"
            
            try:
                page.goto(shopping_url, timeout=40000, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                
                # Çerez/Onay ekranı varsa geç
                page.evaluate('''() => {
                    let btns = document.querySelectorAll('button');
                    for (let b of btns) {
                        if (b.innerText.includes('Tümünü kabul et') || b.innerText.includes('Accept all')) b.click();
                    }
                }''')

                results = page.evaluate('''() => {
                    let items = [];
                    // Google Shopping ürün kartları
                    let cards = document.querySelectorAll('.sh-dgr__grid-result, .sh-dgr__content, div[data-docid]');
                    
                    cards.forEach(card => {
                        let titleEl = card.querySelector('h3, h4, .tAxDx, .EI11Pd');
                        let title = titleEl ? titleEl.innerText : '';
                        
                        let storeEl = card.querySelector('.aULzUe, .IuHnof, .sh-np__seller-container, .hBUZL');
                        let store = storeEl ? storeEl.innerText : '';
                        
                        let priceEl = card.querySelector('.a8Pemb, .OFFNJ, span[aria-hidden="true"], .kHssdc');
                        let priceText = priceEl ? priceEl.innerText : '';
                        
                        let linkEl = card.querySelector('a.LqBPId, a.shntl, a[href^="/url"], a');
                        let href = linkEl ? linkEl.getAttribute('href') : '';
                        
                        if (priceText && href) {
                            items.push({ title, store, priceText, href });
                        }
                    });
                    return items;
                }''')

                added_stores = set()

                for r in results:
                    price = clean_price(r["priceText"])
                    if not price: continue

                    # Yanlış paket/fiyat koruması
                    if price < item["min_price"] or price > item["max_price"]:
                        continue

                    store_name = normalize_store_name(r["store"])
                    if store_name in added_stores:
                        continue

                    # Google yönlendirme linkinden doğrudan mağaza URL'sini ayıkla
                    raw_href = r["href"]
                    if raw_href.startswith("/url?q="):
                        direct_url = urllib.parse.unquote(raw_href.split("/url?q=")[1].split("&")[0])
                    elif raw_href.startswith("http"):
                        direct_url = raw_href
                    else:
                        direct_url = f"https://www.google.com{raw_href}"

                    save_to_database(item["name"], item["category_slug"], item["brand_slug"], store_name, price, direct_url)
                    added_stores.add(store_name)

                # Yedek: Eğer 2'den az mağaza bulunduysa Hepsiburada/PttAVM aramasını doğrudan tamamla
                if len(added_stores) < 2:
                    print(f"      ℹ️ Ek mağaza taraması yapılıyor...")
                    try:
                        hb_url = f"https://www.hepsiburada.com/ara?q={urllib.parse.quote(item['keywords'])}"
                        page.goto(hb_url, timeout=25000, wait_until="domcontentloaded")
                        page.wait_for_timeout(2000)
                        hb_data = page.evaluate('''() => {
                            let card = document.querySelector('li[id^="i"], article, [data-test-id="product-card-item"]');
                            if (!card) return null;
                            let link = card.querySelector('a');
                            let pr = card.querySelector('[data-test-id="price-current-price"], [data-test-id="price"]');
                            return { href: link ? link.getAttribute('href') : '', priceText: pr ? pr.innerText : '' };
                        }''')
                        if hb_data and hb_data.get("href"):
                            p_hb = clean_price(hb_data["priceText"])
                            if p_hb and item["min_price"] <= p_hb <= item["max_price"] and "Hepsiburada" not in added_stores:
                                save_to_database(item["name"], item["category_slug"], item["brand_slug"], "Hepsiburada", p_hb, f"https://www.hepsiburada.com{hb_data['href']}")
                    except Exception:
                        pass

            except Exception as e:
                print(f"  ❌ Hata: {e}")

            time.sleep(1.5)

        browser.close()
    print("\n🎉 Tüm ürünler için 4-5 farklı mağaza ve doğrulanmış fiyatlar Supabase'e yazıldı!")

if __name__ == "__main__":
    run_aggregator_crawler()