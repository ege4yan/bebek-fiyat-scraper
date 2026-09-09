import os
from pathlib import Path
import dj_database_url

# Proje ana dizini
BASE_DIR = Path(__file__).resolve().parent.parent

# Güvenlik ve Geliştirme Ayarları
SECRET_KEY = 'django-insecure-favorim-beta-key'
DEBUG = True
ALLOWED_HOSTS = ['*']

# Uygulamalarımız (Vitrin eklendi)
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'vitrin', 
]

# Ara Katmanlar
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Ana URL Dosyasının Yeri
ROOT_URLCONF = 'bebek.urls'

# HTML Şablon Ayarları
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'bebek.wsgi.application'

# Supabase Veritabanı Bağlantısı
DATABASES = {
    'default': dj_database_url.parse(
        'postgresql://postgres.bbemkqegyvbktqjbjqrr:EgeKuzen2026@aws-1-eu-west-1.pooler.supabase.com:6543/postgres',
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# Dil ve Saat Ayarları
LANGUAGE_CODE = 'tr-tr'
TIME_ZONE = 'Europe/Istanbul'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'