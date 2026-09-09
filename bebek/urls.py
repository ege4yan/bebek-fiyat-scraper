from django.contrib import admin
from django.urls import path
from vitrin.views import ana_sayfa

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', ana_sayfa, name='ana_sayfa'),
]