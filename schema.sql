-- PostgreSQL Eklentileri (Benzersiz ID'ler için UUID kullanımı)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. KATEGORİLER TABLOSU
CREATE TABLE categories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(120) NOT NULL UNIQUE,
    parent_id UUID REFERENCES categories(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. MARKALAR TABLOSU
CREATE TABLE brands (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL UNIQUE,
    slug VARCHAR(120) NOT NULL UNIQUE,
    logo_url TEXT
);

-- 3. ANA ÜRÜN KATALOĞU (Ürün Eşleştirmenin Hedef Noktası)
CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(255) NOT NULL,
    slug VARCHAR(280) NOT NULL UNIQUE,
    barcode VARCHAR(50), -- EAN / UPC Kodu (Product Matching için kritik)
    brand_id UUID REFERENCES brands(id) ON DELETE RESTRICT,
    category_id UUID REFERENCES categories(id) ON DELETE RESTRICT,
    
    -- Anne-Bebek Analitiğine Özel Alanlar (Birim Fiyat Hesaplama)
    unit_type VARCHAR(20), -- 'adet', 'gram', 'ml'
    unit_quantity NUMERIC(10, 2), -- örn: 120 (adet) veya 800 (gram)
    
    image_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. MAĞAZALAR / SATICILAR TABLOSU
CREATE TABLE merchants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL UNIQUE, -- 'ebebek', 'Trendyol - Satıcı A', 'Amazon'
    logo_url TEXT,
    affiliate_params TEXT -- Gelir ortaklığı yönlendirme parametreleri
);

-- 5. MAĞAZA ÜRÜN VE FİYAT EŞLEŞMELERİ (Anlık Fiyat Durumu)
CREATE TABLE product_prices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    
    merchant_product_url TEXT NOT NULL, -- Mağazadaki doğrudan ürün linki
    merchant_product_title VARCHAR(255), -- Mağazadaki ham ürün başlığı
    
    current_price NUMERIC(10, 2) NOT NULL,
    original_price NUMERIC(10, 2), -- İndirim öncesi üstü çizili fiyat
    
    -- Birim Fiyat (SQL veya Python tarafında otomatik hesaplanır)
    -- Örn: 600 TL / 120 adet = 5.00 TL/Adet
    unit_price NUMERIC(10, 4), 
    
    in_stock BOOLEAN DEFAULT TRUE,
    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(product_id, merchant_id)
);

-- 6. FİYAT GEÇMİŞİ (Zaman Serisi Analizi ve Grafik Çizimi İçin)
CREATE TABLE price_history (
    id BIGSERIAL PRIMARY KEY,
    product_price_id UUID NOT NULL REFERENCES product_prices(id) ON DELETE CASCADE,
    price NUMERIC(10, 2) NOT NULL,
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- PERFORMANS İNDEKSLERİ (Arama ve Filtrelemeyi Hızlandırma)
CREATE INDEX idx_products_barcode ON products(barcode);
CREATE INDEX idx_products_category ON products(category_id);
CREATE INDEX idx_product_prices_product ON product_prices(product_id);
CREATE INDEX idx_price_history_recorded ON price_history(recorded_at);
