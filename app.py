import re
from flask import Flask, render_template_string, make_response
import requests

app = Flask(__name__)

SUPABASE_URL = "https://bwmcjllhzfcqncpefixp.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJ3bWNqbGxoemZjcW5jcGVmaXhwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODU5NTU0OTAsImV4cCI6MjEwMTUzMTQ5MH0.gohRsZ208d2sLLLz3VHng7MUfVhuBL7bTp0BG9-_P2Y"

def get_grouped_products():
    endpoint = f"{SUPABASE_URL}/rest/v1/product_prices?select=*&order=created_at.desc"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}"
    }

    try:
        response = requests.get(endpoint, headers=headers, timeout=10)
        if response.status_code != 200:
            return []
        rows = response.json()
    except Exception as e:
        return []

    grouped = {}

    for row in rows:
        title = (row.get("product_name") or "").strip()
        if not title: continue

        raw_price = row.get("price")
        try:
            price = float(raw_price)
            if price <= 0: continue
        except (ValueError, TypeError):
            continue

        key = row.get("slug") or title

        if key not in grouped:
            count_match = re.search(r'(\d+)\s*(Adet|\'l[ıi]|l[ıi]|L[ıi])', title, re.IGNORECASE)
            piece_count = int(count_match.group(1)) if count_match else None
            brand = (row.get("brand_slug") or title.split()[0]).capitalize()
            category = (row.get("category_slug") or "Bebek Bezi").replace("-", " ").title()

            grouped[key] = {
                "id": row.get("id", key),
                "baslik": title,
                "birim_miktari": piece_count,
                "kategori": category,
                "marka": brand,
                "gorsel": "https://images.unsplash.com/photo-1515488042361-ee00e0ddd4e4?w=500&auto=format&fit=crop&q=80",
                "fiyatlar": []
            }

        store_name = (row.get("store_name") or "Satıcı").strip()
        direct_url = row.get("product_url") or "#"
        unit_price = round(price / grouped[key]["birim_miktari"], 2) if grouped[key]["birim_miktari"] else None

        grouped[key]["fiyatlar"].append({
            "magaza": store_name,
            "fiyat": round(price, 2),
            "birim": unit_price,
            "url": direct_url
        })

    product_list = list(grouped.values())
    for prod in product_list:
        prod["fiyatlar"].sort(key=lambda x: x["fiyat"])
        if prod["fiyatlar"]:
            cheapest = prod["fiyatlar"][0]["fiyat"]
            highest = prod["fiyatlar"][-1]["fiyat"]
            prod["en_ucuz"] = prod["fiyatlar"][0]
            prod["tasarruf"] = round(highest - cheapest, 2) if highest > cheapest else 0

    return product_list

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Favorim • Bebek Fiyat Kıyaslama</title>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --primary: #059669;
      --primary-light: #ecfdf5;
      --text-main: #0f172a;
      --text-muted: #64748b;
      --border: #e2e8f0;
      --badge: #0284c7;
      --badge-light: #e0f2fe;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
    body { background-color: var(--bg); color: var(--text-main); padding: 40px 20px; }
    .container { max-width: 1040px; margin: 0 auto; }
    
    .top-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; }
    .brand-logo { font-size: 26px; font-weight: 800; color: #0f172a; display: flex; align-items: center; gap: 8px; }
    .brand-logo span { color: var(--primary); }
    .engine-status { background: var(--primary-light); color: var(--primary); padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 700; border: 1px solid #a7f3d0; }
    
    .product-wrapper { background: var(--card-bg); border-radius: 28px; padding: 32px; margin-bottom: 32px; box-shadow: 0 10px 30px rgba(0,0,0,0.04); border: 1px solid var(--border); }
    .card-top { display: grid; grid-template-columns: 140px 1fr 240px; gap: 24px; align-items: center; margin-bottom: 28px; }
    .product-img { width: 140px; height: 140px; border-radius: 20px; object-fit: cover; background: #f1f5f9; }
    
    .tags { display: flex; gap: 8px; margin-bottom: 10px; }
    .tag-cat { background: #0f172a; color: #fff; padding: 4px 10px; border-radius: 8px; font-size: 11px; font-weight: 700; }
    .tag-count { background: var(--badge-light); color: var(--badge); padding: 4px 10px; border-radius: 8px; font-size: 11px; font-weight: 700; }
    
    .product-title { font-size: 20px; font-weight: 700; line-height: 1.4; margin-bottom: 12px; }
    .meta-badges { display: flex; gap: 10px; align-items: center; }
    .meta-item { font-size: 13px; color: var(--text-muted); font-weight: 600; }
    .saving-badge { background: #dcfce7; color: #15803d; font-size: 12px; font-weight: 700; padding: 4px 10px; border-radius: 8px; }
    
    .cheapest-hero { background: #0f172a; color: #fff; padding: 20px; border-radius: 20px; text-align: left; }
    .hero-label { font-size: 10px; font-weight: 800; color: #94a3b8; letter-spacing: 0.5px; }
    .hero-price-row { display: flex; align-items: baseline; justify-content: space-between; margin-top: 4px; }
    .hero-price { font-size: 26px; font-weight: 800; color: #fff; }
    .hero-store { background: var(--primary); color: #fff; font-size: 12px; font-weight: 700; padding: 4px 10px; border-radius: 8px; }
    .hero-unit { font-size: 12px; color: #cbd5e1; margin-top: 6px; }

    .stores-title { font-size: 12px; font-weight: 800; color: var(--text-muted); letter-spacing: 0.5px; margin-bottom: 14px; display: flex; justify-content: space-between; }
    .stores-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }
    
    .store-card { background: #f8fafc; border: 1px solid var(--border); border-radius: 16px; padding: 14px 18px; display: flex; justify-content: space-between; align-items: center; transition: all 0.2s ease; }
    .store-card:hover { border-color: #cbd5e1; transform: translateY(-2px); }
    .store-card.best-deal { border: 2px solid var(--primary); background: var(--primary-light); }
    
    .store-left { display: flex; flex-direction: column; gap: 2px; }
    .store-header { display: flex; align-items: center; gap: 6px; }
    .store-name { font-size: 15px; font-weight: 800; color: #0f172a; }
    .mini-badge { background: var(--primary); color: #fff; font-size: 9px; font-weight: 800; padding: 2px 6px; border-radius: 4px; }
    .unit-cost { font-size: 12px; color: var(--text-muted); font-weight: 600; }
    
    .store-right { display: flex; align-items: center; gap: 14px; }
    .store-price { font-size: 16px; font-weight: 800; color: var(--text-main); }
    .btn-goto { background: #0f172a; color: #fff; text-decoration: none; padding: 8px 14px; border-radius: 10px; font-size: 12px; font-weight: 700; display: inline-flex; align-items: center; gap: 4px; }
    .btn-goto:hover { background: #1e293b; }
    .best-deal .btn-goto { background: var(--primary); }
    .best-deal .btn-goto:hover { background: #047857; }

    @media (max-width: 860px) {
      .card-top { grid-template-columns: 1fr; }
      .product-img { width: 100%; height: 200px; }
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="top-bar">
      <div class="brand-logo">favorim<span>.</span> <small style="font-size: 13px; color: #64748b; font-weight: 600;">BEBEK INTELLIGENCE</small></div>
      <div class="engine-status">● Canlı Supabase Motoru Aktif</div>
    </div>

    {% for prod in products %}
    <div class="product-wrapper">
      <div class="card-top">
        <img class="product-img" src="{{ prod.gorsel }}" alt="{{ prod.baslik }}">
        
        <div class="product-info">
          <div class="tags">
            <span class="tag-cat">{{ prod.kategori.upper() }}</span>
            <span class="tag-count">{{ prod.fiyatlar|length }} MAĞAZA KIYASLANDI</span>
          </div>
          <h2 class="product-title">{{ prod.baslik }}</h2>
          <div class="meta-badges">
            {% if prod.birim_miktari %}
              <span class="meta-item">📦 Paket: {{ prod.birim_miktari }} Adet</span>
            {% endif %}
            {% if prod.tasarruf > 0 %}
              <span class="saving-badge">₺{{ prod.tasarruf }} Tasarruf</span>
            {% endif %}
          </div>
        </div>

        {% if prod.en_ucuz %}
        <div class="cheapest-hero">
          <span class="hero-label">EN UCUZ SEÇENEK</span>
          <div class="hero-price-row">
            <span class="hero-price">₺{{ "%.2f"|format(prod.en_ucuz.fiyat) }}</span>
            <span class="hero-store">{{ prod.en_ucuz.magaza }}</span>
          </div>
          {% if prod.en_ucuz.birim %}
            <div class="hero-unit">Adet: ₺{{ "%.2f"|format(prod.en_ucuz.birim) }}</div>
          {% endif %}
        </div>
        {% endif %}
      </div>

      <div class="stores-section">
        <div class="stores-title">
          <span>CANLI PAZARYERİ FİYATLARI</span>
          <span style="font-weight: 600;">En düşükten sıralı</span>
        </div>
        <div class="stores-grid">
          {% for f in prod.fiyatlar %}
          <div class="store-card {% if loop.first %}best-deal{% endif %}">
            <div class="store-left">
              <div class="store-header">
                <span class="store-name">{{ f.magaza }}</span>
                {% if loop.first %}<span class="mini-badge">EN UCUZ</span>{% endif %}
              </div>
              {% if f.birim %}
                <span class="unit-cost">Adet: ₺{{ "%.2f"|format(f.birim) }}</span>
              {% endif %}
            </div>
            <div class="store-right">
              <span class="store-price">₺{{ "%.2f"|format(f.fiyat) }}</span>
              <a href="{{ f.url }}" target="_blank" rel="noopener noreferrer" class="btn-goto">
                Ürüne Git ↗
              </a>
            </div>
          </div>
          {% endfor %}
        </div>
      </div>
    </div>
    {% endfor %}
  </div>
</body>
</html>
"""

@app.route("/")
def index():
    products = get_grouped_products()
    resp = make_response(render_template_string(HTML_TEMPLATE, products=products))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)