import re
import json
import time
import urllib.parse
from curl_cffi import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9"
}

DISCOVERY_CATEGORIES = [
    {
        "category_name": "Bebek Bezi",
        "category_slug": "bebek-bezi",
        "akakce_url": "https://www.akakce.com/bebek-bezi.html"
    }
]

def find_store_link(store_name, search_query):
    """Bulunan temiz ürün adıyla mağazalarda otomatik arama yapıp direct linkini getirir."""
    # Arama terimini sadeleştir (Örn: Molfix 6 Numara 80'li)
    clean_q = re.sub(r"[^\w\s]", "", search_query)
    encoded = urllib.parse.quote(clean_q)
    
    try:
        if store_name == "Trendyol":
            res = requests.get(f"https://www.trendyol.com/sr?q={encoded}", headers=HEADERS, impersonate="chrome120", timeout=8)
            m = re.search(r'href="(/[^"]+-p-\d+)"', res.text)
            return f"https://www.trendyol.com{m.group(1)}" if m else None

        elif store_name == "N11":
            res = requests.get(f"https://www.n11.com/arama?q={encoded}", headers=HEADERS, impersonate="chrome120", timeout=8)
            m = re.search(r'href="(https://www\.n11\.com/urun/[^"]+)"', res.text)
            return m.group(1) if m else None

        elif store_name == "Amazon":
            res = requests.get(f"https://www.amazon.com.tr/s?k={encoded}", headers=HEADERS, impersonate="chrome120", timeout=8)
            m = re.search(r'href="(/[^"]+/dp/[A-Z0-9]+)"', res.text)
            return f"https://www.amazon.com.tr{m.group(1)}" if m else None

        elif store_name == "Idefix":
            res = requests.get(f"https://www.idefix.com/arama?q={encoded}", headers=HEADERS, impersonate="chrome120", timeout=8)
            m = re.search(r'href="(https://www\.idefix\.com/[^"]+-p-\d+)"', res.text)
            return m.group(1) if m else None

        elif store_name == "Hepsiburada":
            res = requests.get(f"https://www.hepsiburada.com/ara?q={encoded}", headers=HEADERS, impersonate="chrome120", timeout=8)
            m = re.search(r'href="(https://www\.hepsiburada\.com/[^"]+-p-[A-Za-z0-9]+)"', res.text)
            return m.group(1) if m else None

    except Exception:
        pass
    return None

def fetch_akakce_popular_playwright(category_url):
    """Playwright ile Akakçe'yi açıp popüler ürün başlıklarını yakalar."""
    products = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            page.goto(category_url, timeout=30000, wait_until="domcontentloaded")
            time.sleep(3)

            titles = page.evaluate('''() => {
                let list = [];
                let els = document.querySelectorAll('li.pn_v8 h3, ul#pL > li h3, [id^="p_"] h3, .pn_v8');
                els.forEach(el => {
                    let txt = el.innerText.trim();
                    if (txt && txt.length > 5 && !list.includes(txt)) {
                        list.push(txt);
                    }
                });
                return list;
            }''')

            browser.close()

            for raw_t in titles[:10]: # İlk 10 popüler ürün
                clean_t = re.sub(r'\s+Fiyatları.*$', '', raw_t, flags=re.IGNORECASE)
                clean_t = re.sub(r'^\d+\.\s*', '', clean_t)
                brand = clean_t.split()[0] if clean_t else "Genel"
                products.append({
                    "title": clean_t,
                    "brand": brand
                })

    except Exception as e:
        print(f"  ❌ Playwright Akakçe Hatası: {e}")

    return products

import os

def update_scraper_file(discovered_products):
    """Bulunan yeni ürünleri doğrudan üst dizindeki scraper.py dosyasının içine yazar."""
    try:
        # Bulunduğun klasörden bir üst klasördeki scraper.py dosyasının tam yolunu bulur
        current_dir = os.path.dirname(os.path.abspath(__file__))
        scraper_path = os.path.abspath(os.path.join(current_dir, "..", "scraper.py"))

        # Eğer üst klasörde yoksa bulunduğun klasörde ara
        if not os.path.exists(scraper_path):
            scraper_path = os.path.join(current_dir, "scraper.py")

        with open(scraper_path, "r", encoding="utf-8") as f:
            content = f.read()

        # PRODUCT_LIST alanını yeni bulunan ürünlerle değiştir
        new_product_list_str = f"PRODUCT_LIST = {json.dumps(discovered_products, indent=4, ensure_ascii=False)}"
        updated_content = re.sub(r'PRODUCT_LIST\s*=\s*\[.*?\]\n', new_product_list_str + "\n", content, flags=re.DOTALL)

        with open(scraper_path, "w", encoding="utf-8") as f:
            f.write(updated_content)

        print(f"\n💾 [BAŞARILI] Bulunan ürünler doğrudan `{scraper_path}` dosyasına yazıldı!")
    except Exception as e:
        print(f"\n❌ `scraper.py` güncellenirken hata oluştu: {e}")

def auto_discover_products():
    print("🚀 Tam Otomatik Ürün & Link Avcısı Başlatılıyor...\n")
    discovered_products = []

    for cat in DISCOVERY_CATEGORIES:
        print(f"📂 Akakçe Kategori Taranıyor: {cat['category_name']}")
        popular_items = fetch_akakce_popular_playwright(cat["akakce_url"])
        
        print(f"  ✨ {len(popular_items)} Adet Popüler Ürün Bulundu. Linkler Aranıyor...\n")

        for idx, item in enumerate(popular_items, 1):
            title = item["title"]
            brand = item["brand"]
            print(f"  [{idx}/{len(popular_items)}] 🔍 {title[:45]}...")

            urls = {}
            for store in ["Trendyol", "Amazon", "N11", "Hepsiburada", "Idefix"]:
                s_link = find_store_link(store, title)
                if s_link:
                    urls[store] = s_link
                    print(f"    🔗 {store} linki bulundu!")

            discovered_products.append({
                "name": title,
                "category_slug": cat["category_slug"],
                "brand_slug": brand.lower().replace(" ", "-"),
                "keywords": [brand.lower()],
                "urls": urls
            })
            print("-" * 50)
            time.sleep(0.5)

    # Scraper dosyasını otomatik güncelle
    if discovered_products:
        update_scraper_file(discovered_products)

if __name__ == "__main__":
    auto_discover_products()