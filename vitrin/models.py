
from django.db import models

class Urun(models.Model):
    platform = models.CharField(max_length=50)
    kategori = models.CharField(max_length=50)
    urun_adi = models.CharField(max_length=255)
    fiyat = models.CharField(max_length=50)
    urun_linki = models.TextField(unique=True)
    resim_url = models.TextField(null=True, blank=True) # Yeni Fotoğraf Sütunu
    guncellenme_tarihi = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'urunler'
        managed = False

    def __str__(self):
        return f"{self.platform} - {self.urun_adi}"