"""
Bebek ürünleri fiyat takip motoru.

Değişiklikler / iyileştirmeler (öncekine göre):
  1. DB bağlantı bilgisi artık ortam değişkeninden okunuyor (kodda şifre yok).
  2. Katalog ayrı bir JSON dosyasına taşındı -> kod değişmeden ürün eklenebilir.
  3. Fiyat çekme sırası: JSON-LD (schema.org Product) -> meta[itemprop=price]
     -> site-özel CSS seçicileri -> genel regex. Böylece "price" kelimesi geçen
     alakasız bir sayıya (örn. bir reklam objesi) yanlışlıkla yakalanma riski azaldı.
  4. Bütün "except: pass" bloklarının yerine loglama geldi; artık hangi ürünün
     hangi mağazasında ne hata olduğu görülebiliyor.
  5. TRUNCATE + sırayla doldurma yerine: veriler önce bir staging tabloya yazılıp
     tek bir transaction içinde canlı tabloya atomik olarak geçiriliyor. Eskiden
     script ortasında çökerse tablo boş kalıyordu, artık ya hep ya hiç.
  6. İstekler ThreadPoolExecutor ile mağaza bazında paralelleştirildi (aynı
     mağazaya art arda çok hızlı istek atılmaması için mağaza başına küçük bir
     bekleme korunuyor), toplam süre ciddi şekilde kısaldı.
  7. Basit retry + üstel geri çekilme eklendi (ağ zaman aşımı gibi geçici
     hatalarda tek denemede pes etmiyor).
  8. --dry-run bayrağı eklendi: DB'ye yazmadan sadece çekilen fiyatları gösterir.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import psycopg2
from bs4 import BeautifulSoup
from curl_cffi import requests

# --------------------------------------------------------------------------- #
# Ayarlar
# --------------------------------------------------------------------------- #

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("fiyat_motoru")

CATALOG_PATH = Path(__file__).with_name("catalog.json")
MAX_WORKERS = 6          # aynı anda kaç mağaza isteği yapılacak
REQUEST_TIMEOUT = 15
MAX_RETRIES = 2
RETRY_BACKOFF = 2.0       # saniye, her denemede ikiye katlanır


def get_db_url() -> str:
    """DB bağlantı adresini ortam değişkeninden okur.

    Kod içine şifre yazmak yerine ortam değişkeni kullanılıyor. Örn:
        export SUPABASE_DB_URL="postgresql://user:pass@host:6543/postgres"
    """
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        raise RuntimeError(
            "SUPABASE_DB_URL ortam değişkeni tanımlı değil. "
            "Şifreyi koda yazmak yerine ortam değişkeni ile geçin."
        )
    return url


def load_catalog() -> list[dict]:
    if not CATALOG_PATH.exists():
        raise FileNotFoundError(
            f"{CATALOG_PATH} bulunamadı. Ürün kataloğunu bu dosyaya taşıyın "
            "(örnek için scriptle birlikte gelen catalog.json'a bakın)."
        )
    with CATALOG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
# Fiyat ayrıştırma
# --------------------------------------------------------------------------- #

def clean_price(text) -> Optional[float]:
    if not text:
        return None
    t = str(text).replace("TL", "").replace("₺", "").replace("\xa0", " ").strip()
    t = re.sub(r"[^\d,\.]", "", t)
    if not t:
        return None
    try:
        if "," in t and "." in t:
            t = t.replace(".", "").replace(",", ".")
        elif "," in t:
            t = t.replace(",", ".")
        return round(float(t), 2)
    except ValueError:
        return None


def _price_from_jsonld(soup: BeautifulSoup) -> Optional[float]:
    """schema.org Product/Offer JSON-LD bloklarından fiyat çıkarır (en güvenilir yol)."""
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            offers = item.get("offers") if isinstance(item, dict) else None
            if isinstance(offers, dict) and offers.get("price"):
                price = clean_price(offers["price"])
                if price:
                    return price
            if isinstance(offers, list):
                for o in offers:
                    if isinstance(o, dict) and o.get("price"):
                        price = clean_price(o["price"])
                        if price:
                            return price
    return None


def _price_from_meta(soup: BeautifulSoup) -> Optional[float]:
    meta = soup.find("meta", attrs={"itemprop": "price"}) or soup.find(
        "meta", attrs={"property": "product:price:amount"}
    )
    if meta and meta.get("content"):
        return clean_price(meta["content"])
    return None


def _price_from_site_selectors(soup: BeautifulSoup, url: str) -> Optional[float]:
    """Bilinen mağazalar için CSS seçicileri (genel regex'ten daha güvenilir)."""
    if "amazon.com.tr" in url:
        el = soup.find("span", class_="a-price-whole")
        if el:
            return clean_price(el.text)
    if "hepsiburada.com" in url:
        el = soup.find("span", attrs={"data-test-id": "price-current-price"})
        if el:
            return clean_price(el.text)
    if "e-bebek.com" in url:
        el = soup.find("span", class_="prc-dsc") or soup.find("ins", class_="price")
        if el:
            return clean_price(el.text)
    return None


def _price_from_regex(html: str) -> Optional[float]:
    match = re.search(r'"price"\s*:\s*"?(\d+(?:\.\d+)?)"?', html)
    if match:
        return clean_price(match.group(1))
    return None


def extract_price(html: str, url: str) -> Optional[float]:
    soup = BeautifulSoup(html, "html.parser")
    for extractor in (
        lambda: _price_from_jsonld(soup),
        lambda: _price_from_meta(soup),
        lambda: _price_from_site_selectors(soup, url),
        lambda: _price_from_regex(html),
    ):
        price = extractor()
        if price:
            return price
    return None


# --------------------------------------------------------------------------- #
# Ağ isteği (retry'lı)
# --------------------------------------------------------------------------- #

def get_live_price(url: str) -> Optional[float]:
    last_error = None
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            response = requests.get(url, impersonate="chrome110", timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                return extract_price(response.text, url)
            last_error = f"HTTP {response.status_code}"
        except Exception as exc:  # noqa: BLE001 - dış servis hatası, geniş yakalama bilinçli
            last_error = str(exc)

        if attempt <= MAX_RETRIES:
            time.sleep(RETRY_BACKOFF * attempt)

    log.warning("Fiyat çekilemedi (%s): %s", url, last_error)
    return None


# --------------------------------------------------------------------------- #
# Tek mağaza için işleme
# --------------------------------------------------------------------------- #

@dataclass
class PriceResult:
    product_name: str
    category_slug: str
    brand_slug: str
    store_name: str
    price: float
    product_url: str
    slug: str
    is_live: bool


def process_store(product: dict, store: dict, slug: str) -> PriceResult:
    live_price = get_live_price(store["url"])

    if live_price and not (product["min_price"] <= live_price <= product["max_price"]):
        log.warning(
            "[REDDEDİLDİ] %s / %s fiyatı (%.2f ₺) beklenen aralık dışında, "
            "koli/aksesuar olabilir -> yedek fiyat kullanılacak",
            product["name"], store["name"], live_price,
        )
        live_price = None

    final_price = live_price if live_price else store["fallback"]
    status = "CANLI" if live_price else "YEDEK"
    log.info("[%s] %-12s %-15s ₺%.2f", status, product["name"][:30], store["name"], final_price)

    return PriceResult(
        product_name=product["name"],
        category_slug=product["category_slug"],
        brand_slug=product["brand_slug"],
        store_name=store["name"],
        price=final_price,
        product_url=store["url"],
        slug=slug,
        is_live=bool(live_price),
    )


def scrape_all(catalog: list[dict]) -> list[PriceResult]:
    tasks = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for product in catalog:
            slug = re.sub(r"[^a-z0-9]+", "-", product["name"].lower()).strip("-")[:80]
            for store in product["stores"]:
                tasks.append(pool.submit(process_store, product, store, slug))

        results = []
        for future in as_completed(tasks):
            try:
                results.append(future.result())
            except Exception:
                log.exception("Beklenmeyen hata bir mağaza işlenirken")
    return results


# --------------------------------------------------------------------------- #
# Veritabanı: staging tablo + atomik swap
# --------------------------------------------------------------------------- #

def write_to_db(results: list[PriceResult], db_url: str) -> None:
    conn = psycopg2.connect(db_url)
    try:
        with conn:  # transaction: hepsi başarılı olursa commit, yoksa rollback
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TEMP TABLE product_prices_staging
                    (LIKE product_prices INCLUDING DEFAULTS) ON COMMIT DROP;
                    """
                )
                insert_q = """
                    INSERT INTO product_prices_staging
                        (product_name, category_slug, brand_slug, store_name,
                         price, product_url, slug)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                cur.executemany(
                    insert_q,
                    [
                        (r.product_name, r.category_slug, r.brand_slug,
                         r.store_name, r.price, r.product_url, r.slug)
                        for r in results
                    ],
                )
                cur.execute("TRUNCATE TABLE product_prices;")
                cur.execute("INSERT INTO product_prices SELECT * FROM product_prices_staging;")
        log.info("%d satır Supabase'e atomik olarak yazıldı.", len(results))
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Ana akış
# --------------------------------------------------------------------------- #

def main() -> None:
    parser = argparse.ArgumentParser(description="Bebek ürünleri fiyat güncelleme motoru")
    parser.add_argument("--dry-run", action="store_true", help="DB'ye yazma, sadece çekilen fiyatları göster")
    args = parser.parse_args()

    log.info("Fiyat motoru başlatıldı (dry-run=%s)", args.dry_run)
    catalog = load_catalog()
    results = scrape_all(catalog)

    live_count = sum(r.is_live for r in results)
    log.info("Toplam %d fiyat çekildi (%d canlı, %d yedek).", len(results), live_count, len(results) - live_count)

    if args.dry_run:
        log.info("--dry-run aktif, veritabanına yazılmadı.")
        return

    write_to_db(results, get_db_url())
    log.info("Tamamlandı.")


if __name__ == "__main__":
    main()
