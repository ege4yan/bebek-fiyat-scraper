import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random

class BabyProductScraper:
    def __init__(self):
        # Gerçek bir tarayıcı taklidi yapmak için güçlü bir User-Agent kullanıyoruz.
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Connection": "keep-alive"
        }
        self.all_products = []

        # Her sitenin ana 'bebek' kategorisi URL'si ve HTML CSS Seçicileri (Selectors)
        # Not: E-ticaret siteleri class isimlerini periyodik olarak değiştirir (CSS Obfuscation).
        self.site_configs = {
            "ebebek": {
                "url": "https://www.e-bebek.com/bebek-urunleri-c-1",
                "container": "div.product-item",
                "title": "h2",
                "price": "span.price",
                "link": "a",
                "base_url": "https://www.e-bebek.com"
            },
            "trendyol": {
                "url": "https://www.trendyol.com/bebek-cocuk-x-c118",
                "container": "div.p-card-wrppr",
                "title": "span.prdct-desc-cntnr-name",
                "price": "div.prc-box-dscntd",
                "link": "a",
                "base_url": "https://www.trendyol.com"
            },
            "hepsiburada": {
                "url": "https://www.hepsiburada.com/bebek-oyuncaklari-c-94",
                "container": "li.productListContent-item",
                "title": "h3",
                "price": "div[data-test-id='price-current-price']",
                "link": "a",
                "base_url": "https://www.hepsiburada.com"
            },
            "n11": {
                "url": "https://www.n11.com/anne-bebek",
                "container": "li.column",
                "title": "h3.productName",
                "price": "ins",
                "link": "a.plink",
                "base_url": ""
            },
            "amazon_tr": {
                "url": "https://www.amazon.com.tr/b?node=12466391031",
                "container": "div[data-component-type='s-search-result']",
                "title": "span.a-text-normal",
                "price": "span.a-price-whole",
                "link": "a.a-link-normal",
                "base_url": "https://www.amazon.com.tr"
            },
            "civil": {
                "url": "https://www.civilim.com/bebek",
                "container": "div.product-item",
                "title": "div.product-title",
                "price": "div.product-price",
                "link": "a",
                "base_url": "https://www.civilim.com"
            },
            "joker": {
                "url": "https://www.joker.com.tr/kategori/bebek-giyim",
                "container": "div.product-card",
                "title": "h3",
                "price": "span.new-price",
                "link": "a",
                "base_url": "https://www.joker.com.tr"
            },
            "happy_com_tr": {
                "url": "https://www.happy.com.tr/anne-bebek",
                "container": "div.product-item",
                "title": "a.product-title",
                "price": "div.price",
                "link": "a.product-title",
                "base_url": "https://www.happy.com.tr"
            },
            "babymall": {
                "url": "https://www.babymall.com.tr/",
                "container": "div.product-card",
                "title": "div.product-name",
                "price": "div.product-price",
                "link": "a",
                "base_url": "https://www.babymall.com.tr"
            },
            "pazarama": {
                "url": "https://www.pazarama.com/anne-bebek-oyuncak-k-K12",
                "container": "div.product-card",
                "title": "div.product-name",
                "price": "div.price-value",
                "link": "a",
                "base_url": "https://www.pazarama.com"
            },
            "pazaramaplus": {
                "url": "https://www.pazarama.com/pazarama-plus", 
                "container": "div.product-card",
                "title": "div.product-name",
                "price": "div.price-value",
                "link": "a",
                "base_url": "https://www.pazarama.com"
            },
            "pttavm": {
                "url": "https://www.pttavm.com/kategori/anne-bebek-oyuncak",
                "container": "div.product-list-box",
                "title": "div.product-title",
                "price": "div.price",
                "link": "a",
                "base_url": "https://www.pttavm.com"
            }
        }

    def scrape_site(self, site_name, config):
        print(f"[{site_name}] Taranıyor...")
        try:
            # IP ban yememek için istekler arasına rastgele gecikme ekliyoruz
            time.sleep(random.uniform(2.0, 5.0))
            
            # Bazı siteler için session oluşturmak çerez (cookie) yönetimi açısından faydalıdır
            session = requests.Session()
            response = session.get(config['url'], headers=self.headers, timeout=15)

            if response.status_code != 200:
                print(f"[{site_name}] Başarısız bağlantı. Durum kodu: {response.status_code} (Anti-bot engeli olabilir)")
                return

            soup = BeautifulSoup(response.content, 'html.parser')
            products = soup.select(config['container'])

            if not products:
                print(f"[{site_name}] Ürün konteyneri bulunamadı. Site JS Render kullanıyor veya bot doğrulama sayfasındasınız.")
                return

            for product in products:
                try:
                    title_el = product.select_one(config['title'])
                    price_el = product.select_one(config['price'])
                    link_el = product.select_one(config['link'])

                    title = title_el.text.strip() if title_el else "İsim Bulunamadı"
                    price = price_el.text.strip() if price_el else "Fiyat Bulunamadı"
                    link = link_el['href'] if link_el and 'href' in link_el.attrs else ""

                    # Eğer link '/' ile başlıyorsa (göreceli link), base_url ile birleştiriyoruz
                    if link and not link.startswith("http"):
                        link = config['base_url'] + link

                    self.all_products.append({
                        "Platform": site_name,
                        "Ürün Adı": title,
                        "Fiyat": price,
                        "Ürün Linki": link
                    })
                except AttributeError:
                    continue # Eksik HTML bloklarını atla

            print(f"[{site_name}] {len(products)} ürün başarıyla sayfadan çekildi.")

        except requests.exceptions.RequestException as e:
            print(f"[{site_name}] Bağlantı hatası: {str(e)}")

    def run(self):
        for site_name, config in self.site_configs.items():
            self.scrape_site(site_name, config)

        # Çekilen verileri pandas ile işleyip Excel'e aktarma
        if self.all_products:
            df = pd.DataFrame(self.all_products)
            
            # Veri temizleme adımları eklenebilir (örn: Fiyatlardan TL ibaresini kaldırma)
            df['Fiyat'] = df['Fiyat'].str.replace('\n', '', regex=False).str.strip()
            
            output_file = "bebek_kategorisi_fiyat_analizi.xlsx"
            df.to_excel(output_file, index=False)
            print(f"\n✅ İşlem tamamlandı! Toplam {len(self.all_products)} ürün '{output_file}' dosyasına kaydedildi.")
        else:
            print("\n❌ Hiçbir ürün çekilemedi.")

if __name__ == "__main__":
    scraper = BabyProductScraper()
    scraper.run()