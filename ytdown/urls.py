# ytdown/urls.py
from django.urls import path
from downloader import views
from django.contrib import admin

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('download/', views.download_video, name='download_video'),
    path('convert/<uuid:download_id>/', views.convert_view, name='convert_view'),
    path('download/<uuid:download_id>/', views.download_from_link, name='download_from_link'),
]