from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import pandas as pd
import time
import random

class DynamicBabyProductScraper:
    def __init__(self):
        self.all_products = []
        
        # Test amaçlı sadece birkaç siteyi bıraktım, diğerlerini önceki koddan ekleyebilirsin
        self.site_configs = {
            "trendyol": {
                "url": "https://www.trendyol.com/bebek-cocuk-x-c118",
                "container": "div.p-card-wrppr",
                "title": "span.prdct-desc-cntnr-name",
                "price": "div.prc-box-dscntd",
                "link": "a",
                "base_url": "https://www.trendyol.com"
            },
            "ebebek": {
                "url": "https://www.e-bebek.com/bebek-urunleri-c-1",
                "container": "div.product-item",
                "title": "h2",
                "price": "span.price",
                "link": "a",
                "base_url": "https://www.e-bebek.com"
            },
             "pazarama": {
                "url": "https://www.pazarama.com/anne-bebek-oyuncak-k-K12",
                "container": "div.product-card",
                "title": "div.product-name",
                "price": "div.price-value",
                "link": "a",
                "base_url": "https://www.pazarama.com"
            }
        }

    def scrape_site(self, page, site_name, config):
        print(f"[{site_name}] Taranıyor...")
        try:
            # Siteye git ve tüm ağ işlemlerinin durulmasını bekle (JS renderı için kritik)
            page.goto(config['url'], timeout=30000, wait_until="domcontentloaded")
            
            # Ürünlerin yüklenmesi için biraz rastgele süre tanı
            time.sleep(random.uniform(3.0, 6.0))
            
            # Ürün kapsayıcısının ekranda belirmesini bekle
            try:
                page.wait_for_selector(config['container'], timeout=10000)
            except Exception:
                print(f"[{site_name}] JS Render süresi doldu veya bot korumasına takıldı (Captcha).")
                # Hata alınsa bile mevcut DOM'u almaya çalışalım
            
            # Render edilmiş dinamik HTML'i alıp BeautifulSoup'a veriyoruz
            html_content = page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            products = soup.select(config['container'])

            if not products:
                print(f"[{site_name}] Ürün bulunamadı.")
                return

            for product in products:
                try:
                    title_el = product.select_one(config['title'])
                    price_el = product.select_one(config['price'])
                    link_el = product.select_one(config['link'])

                    title = title_el.text.strip() if title_el else "İsim Bulunamadı"
                    price = price_el.text.strip() if price_el else "Fiyat Bulunamadı"
                    link = link_el['href'] if link_el and 'href' in link_el.attrs else ""

                    if link and not link.startswith("http"):
                        link = config['base_url'] + link

                    self.all_products.append({
                        "Platform": site_name,
                        "Ürün Adı": title,
                        "Fiyat": price,
                        "Ürün Linki": link
                    })
                except AttributeError:
                    continue

            print(f"[{site_name}] {len(products)} ürün başarıyla sayfadan çekildi.")

        except Exception as e:
            print(f"[{site_name}] Hata oluştu: {str(e)}")

    def run(self):
        # Playwright oturumunu başlatıyoruz
        with sync_playwright() as p:
            # headless=False yaparsan tarayıcının ekranda açılıp siteyi nasıl gezdiğini gözünle görebilirsin.
            # Bot yakalanmalarını debug etmek için harikadır. İşin bitince headless=True yapabilirsin.
            browser = p.chromium.launch(headless=False) 
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            for site_name, config in self.site_configs.items():
                self.scrape_site(page, site_name, config)

            browser.close()

        if self.all_products:
            df = pd.DataFrame(self.all_products)
            df['Fiyat'] = df['Fiyat'].str.replace('\n', '', regex=False).str.strip()
            output_file = "bebek_kategorisi_playwright.xlsx"
            df.to_excel(output_file, index=False)
            print(f"\n✅ İşlem tamamlandı! Toplam {len(self.all_products)} ürün kaydedildi.")
        else:
            print("\n❌ Hiçbir ürün çekilemedi.")

if __name__ == "__main__":
    scraper = DynamicBabyProductScraper()
    scraper.run()