from django.shortcuts import render
from .models import Urun
import re

def urun_analiz_et(baslik):
    baslik = baslik.lower()
    markalar = ['molfix', 'sleepy', 'prima', 'baby turco', 'paddlers', 'minies', 'huggies', 'goon', 'evy baby']
    
    bulunan_marka = "Diğer"
    for marka in markalar:
        if marka in baslik:
            bulunan_marka = marka.title()
            break
            
    # Başlığın içindeki 1 ile 7 arasındaki numaraları (bedenleri) cımbızla
    beden = ""
    eslesme = re.search(r'\b([1-7])\b', baslik)
    if eslesme:
        beden = eslesme.group(1)
        
    if beden and bulunan_marka != "Diğer":
        return f"{bulunan_marka} - {beden} Numara Bebek Bezi"
    return bulunan_marka

def ana_sayfa(request):
    urunler = Urun.objects.all()
    gruplu_urunler = {}
    
    for urun in urunler:
        # Fiyatı matematiksel sıralama için temizle
        fiyat_str = urun.fiyat.replace('TL', '').replace('.', '').replace(',', '.').strip()
        try:
            urun.fiyat_num = float(fiyat_str)
        except:
            urun.fiyat_num = 999999
            
        # Eğer fiyat saçma sapan bir değerse (5.74 TL gibi) listeye alma
        if urun.fiyat_num < 50:
            continue
            
        grup_adi = urun_analiz_et(urun.urun_adi)
        if grup_adi not in gruplu_urunler:
            gruplu_urunler[grup_adi] = []
        gruplu_urunler[grup_adi].append(urun)
        
    # Her grubu kendi içinde en ucuzdan en pahalıya sırala
    for grup, liste in gruplu_urunler.items():
        liste.sort(key=lambda x: x.fiyat_num)
        
    # Alfabetik sıraya göre grupları diz
    sirali_gruplar = dict(sorted(gruplu_urunler.items()))

    return render(request, 'index.html', {'gruplu_urunler': sirali_gruplar})