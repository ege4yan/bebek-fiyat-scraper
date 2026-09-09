import os
import re
import time
import psycopg2
from playwright.sync_api import sync_playwright

SUPABASE_DB_URL = "postgresql://postgres.bbemkqegyvbktqjbjqrr:EgeKuzen2026@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"

def fiyati_temizle(fiyat_metni):
    if not fiyat_metni: return ""
    match = re.search(r'(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)', fiyat_metni.replace(' ', ''))
    if match: return match.group(1).strip('.,') + " TL"
    return ""

def urun_gecerli_mi(baslik):
    b = baslik.lower()
    yasaklilar = ['mendil', 'krem', 'havlu', 'şampuan', 'deterjan', 'sabun', 'ped', 'alt açma', 'losyon', 'emzik', 'biberon', 'yatak', 'örtü']
    for y in yasaklilar:
        if y in b: return False
    return True

def scroll_page(page):
    for _ in range(6):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(1)

def get_stealth_context(browser):
    """Bizi GitHub Actions sunucusunda bir bot değil, gerçek bir insan gibi gösteren Hayalet Zırhı."""
    context = browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        locale="tr-TR",
        timezone_id="Europe/Istanbul",
        extra_http_headers={
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Upgrade-Insecure-Requests": "1"
        }
    )
    return context

def inject_stealth(page):
    """Tarayıcının arka planındaki 'Ben bir botum' (webdriver) kimliğini siler."""
    page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

def amazon_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.amazon.com.tr/s?k=bebek+bezi&i=baby"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50, args=['--disable-blink-features=AutomationControlled', '--no-sandbox'])
        context = get_stealth_context(browser)
        page = context.new_page()
        inject_stealth(page)
        
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}&page={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[Amazon TR] Sayfa {sayfa_no} taranıyor...")
            try:
                page.goto(url, timeout=60000)
                time.sleep(3)
                scroll_page(page)
                extracted = page.evaluate('''() => {
                    let items = [];
                    document.querySelectorAll('div[data-component-type="s-search-result"]').forEach(card => {
                        let title_el = card.querySelector("h2 span") || card.querySelector("span.a-text-normal");
                        let link_el = card.querySelector("h2 a");
                        let price_el = card.querySelector("span.a-price:not(.a-text-price) .a-offscreen") || card.querySelector("span.a-price:not(.a-text-price)");
                        let img_el = card.querySelector("img.s-image");
                        if (title_el && link_el && price_el) {
                            items.push({
                                title: title_el.innerText.trim(),
                                price: price_el.innerText.trim(),
                                link: link_el.getAttribute("href"),
                                image: img_el ? img_el.getAttribute("src") : ""
                            });
                        }
                    });
                    return items;
                }''')
                eklenen = 0
                for data in extracted:
                    if urun_gecerli_mi(data["title"]):
                        fiyat = fiyati_temizle(data["price"])
                        href = data["link"]
                        if not href.startswith('http'): href = "https://www.amazon.com.tr" + href
                        if fiyat:
                            all_products.append({"Platform": "Amazon TR", "Kategori": "Bebek Bezi", "Ürün Adı": data["title"], "Fiyat": fiyat, "Ürün Linki": href, "Resim": data["image"]})
                            eklenen += 1
                print(f"[Amazon TR] Sayfa {sayfa_no} üzerinden {eklenen} net ürün yakalandı.")
            except Exception as e: print(f"Amazon Hata: {e}")
        browser.close()
    return all_products

def trendyol_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.trendyol.com/bebek-bezi-x-c1363"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50, args=['--disable-blink-features=AutomationControlled', '--no-sandbox'])
        context = get_stealth_context(browser)
        page = context.new_page()
        inject_stealth(page)
        
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}?pi={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[Trendyol] Sayfa {sayfa_no} taranıyor...")
            try:
                page.goto(url, timeout=60000)
                time.sleep(4) # Bot korumasını aşmak için ekstra bekleme
                scroll_page(page)
                extracted = page.evaluate('''() => {
                    let items = [];
                    document.querySelectorAll(".p-card-wrppr").forEach(card => {
                        let link_el = card.querySelector("a");
                        let price_el = card.querySelector(".prc-box-dscntd") || card.querySelector(".prc-box-sllng");
                        let img_el = card.querySelector("img.p-card-img");
                        
                        let title_div = card.querySelector(".prdct-desc-cntnr-ttl");
                        let title = title_div && title_div.hasAttribute("title") ? title_div.getAttribute("title") : "";
                        if(!title){
                            let brand = card.querySelector(".prdct-desc-brnd");
                            let name = card.querySelector(".prdct-desc-cntnr-name");
                            title = (brand ? brand.innerText + " " : "") + (name ? name.innerText : "");
                        }
                        
                        let img_src = img_el ? (img_el.getAttribute("src") || img_el.getAttribute("data-src") || "") : "";
                        
                        if (link_el && price_el && title) {
                            items.push({
                                title: title.trim(),
                                price: price_el.innerText.trim(),
                                link: link_el.getAttribute("href"),
                                image: img_src
                            });
                        }
                    });
                    return items;
                }''')
                eklenen = 0
                for data in extracted:
                    if urun_gecerli_mi(data["title"]):
                        fiyat = fiyati_temizle(data["price"])
                        href = data["link"]
                        resim = data["image"]
                        if not href.startswith('http'): href = "https://www.trendyol.com" + href
                        if fiyat:
                            all_products.append({"Platform": "Trendyol", "Kategori": "Bebek Bezi", "Ürün Adı": data["title"], "Fiyat": fiyat, "Ürün Linki": href, "Resim": resim})
                            eklenen += 1
                print(f"[Trendyol] Sayfa {sayfa_no} üzerinden {eklenen} net ürün yakalandı.")
            except Exception as e: print(f"Trendyol Hata: {e}")
        browser.close()
    return all_products

def n11_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.n11.com/bebek-bezi-ve-islak-mendil/bebek-bezi"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50, args=['--disable-blink-features=AutomationControlled', '--no-sandbox'])
        context = get_stealth_context(browser)
        page = context.new_page()
        inject_stealth(page)
        
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}?pg={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[N11] Sayfa {sayfa_no} taranıyor...")
            try:
                page.goto(url, timeout=60000)
                time.sleep(4)
                scroll_page(page)
                extracted = page.evaluate('''() => {
                    let items = [];
                    document.querySelectorAll("li.column").forEach(card => {
                        let link_el = card.querySelector("a.plink");
                        let price_el = card.querySelector("ins") || card.querySelector("span.newPrice");
                        let img_el = card.querySelector("img.cardImage") || card.querySelector("img");
                        
                        let img_src = img_el ? (img_el.getAttribute("data-src") || img_el.getAttribute("data-original") || img_el.getAttribute("src") || "") : "";

                        if (link_el && price_el) {
                            items.push({
                                title: link_el.getAttribute("title") || link_el.innerText.trim(),
                                price: price_el.innerText.trim(),
                                link: link_el.getAttribute("href"),
                                image: img_src
                            });
                        }
                    });
                    return items;
                }''')
                eklenen = 0
                for data in extracted:
                    if urun_gecerli_mi(data["title"]):
                        fiyat = fiyati_temizle(data["price"])
                        href = data["link"]
                        resim = data["image"]
                        if not href.startswith('http'): href = "https://www.n11.com" + href
                        if fiyat:
                            all_products.append({"Platform": "N11", "Kategori": "Bebek Bezi", "Ürün Adı": data["title"], "Fiyat": fiyat, "Ürün Linki": href, "Resim": resim})
                            eklenen += 1
                print(f"[N11] Sayfa {sayfa_no} üzerinden {eklenen} net ürün yakalandı.")
            except Exception as e: print(f"N11 Hata: {e}")
        browser.close()
    return all_products

def hepsiburada_tara(max_sayfa=1):
    all_products = []
    base_url = "https://www.hepsiburada.com/bebek-bezleri-c-60001049"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50, args=['--disable-blink-features=AutomationControlled', '--no-sandbox'])
        context = get_stealth_context(browser)
        page = context.new_page()
        inject_stealth(page)
        
        for sayfa_no in range(1, max_sayfa + 1):
            url = f"{base_url}?sayfa={sayfa_no}" if sayfa_no > 1 else base_url
            print(f"\n[Hepsiburada] Sayfa {sayfa_no} taranıyor...")
            try:
                page.goto(url, timeout=60000)
                time.sleep(5) # Hepsiburada JS'i çok ağır yüklenir
                scroll_page(page)
                extracted = page.evaluate('''() => {
                    let items = [];
                    document.querySelectorAll("li[data-index], li[class*='productListContent']").forEach(card => {
                        let a_tag = card.querySelector("a");
                        let title_tag = card.querySelector("[data-test-id*='title']") || card.querySelector("h3");
                        let price_tag = card.querySelector("[data-test-id='price-current-price']") || card.querySelector("[data-test-id='product-price']");
                        let img_tag = card.querySelector("img");
                        
                        let img_src = img_tag ? (img_tag.getAttribute("src") || img_tag.getAttribute("data-src") || "") : "";

                        if (a_tag && title_tag && price_tag) {
                            items.push({
                                title: title_tag.innerText.trim(),
                                price: price_tag.innerText.trim(),
                                link: a_tag.getAttribute("href"),
                                image: img_src
                            });
                        }
                    });
                    return items;
                }''')
                eklenen = 0
                for data in extracted:
                    if urun_gecerli_mi(data["title"]):
                        fiyat = fiyati_temizle(data["price"])
                        href = data["link"]
                        resim = data["image"]
                        if not href.startswith('http'): href = "https://www.hepsiburada.com" + href
                        if resim and resim.startswith('//'): resim = "https:" + resim
                        if fiyat:
                            all_products.append({"Platform": "Hepsiburada", "Kategori": "Bebek Bezi", "Ürün Adı": data["title"], "Fiyat": fiyat, "Ürün Linki": href, "Resim": resim})
                            eklenen += 1
                print(f"[Hepsiburada] Sayfa {sayfa_no} üzerinden {eklenen} net ürün yakalandı.")
            except Exception as e: print(f"Hepsiburada Hata: {e}")
        browser.close()
    return all_products

def save_to_db(all_products):
    if not all_products:
        print("❌ Kaydedilecek ürün bulunamadı.")
        return
    try:
        conn = psycopg2.connect(SUPABASE_DB_URL)
        cur = conn.cursor()
        eklenen = 0
        for urun in all_products:
            try:
                query = """
                    INSERT INTO urunler (platform, kategori, urun_adi, fiyat, urun_linki, resim_url)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (urun_linki) 
                    DO UPDATE SET fiyat = EXCLUDED.fiyat, urun_adi = EXCLUDED.urun_adi, resim_url = EXCLUDED.resim_url;
                """
                cur.execute(query, (urun["Platform"], urun["Kategori"], urun["Ürün Adı"], urun["Fiyat"], urun["Ürün Linki"], urun.get("Resim", "")))
                eklenen += 1
            except: conn.rollback()
        conn.commit()
        cur.close()
        conn.close()
        print(f"\n✅ ZAFER! Toplam {eklenen} ürün başarıyla Supabase'e kaydedildi!")
    except Exception as e: print(f"❌ Veritabanı bağlantı hatası: {e}")

if __name__ == "__main__":
    print("🚀 Bebiio Ultimate Hayalet Motor Başlatıldı!\n")
    try:
        toplam_urunler = []
        toplam_urunler.extend(trendyol_tara(1))
        toplam_urunler.extend(amazon_tara(1))
        toplam_urunler.extend(n11_tara(1))
        toplam_urunler.extend(hepsiburada_tara(1))
        
        print(f"\n🎉 Tarama tamamlandı! Toplam {len(toplam_urunler)} ürün yakalandı. DB'ye yazılıyor...")
        save_to_db(toplam_urunler)
        print("✅ Görev başarıyla tamamlandı! Motor kapanıyor.")
    except Exception as e:
        print(f"❌ Motor çalışırken hata oluştu: {e}")