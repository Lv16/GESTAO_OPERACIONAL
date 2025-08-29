"""
URL configuration for setup project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from GO import views 

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'), 
    path('os/<int:os_id>/detalhes/', views.detalhes_os, name='detalhes_os'), 
    path('os/numero/<int:numero_os>/id/', views.get_os_id_by_number, name='get_os_id_by_number'), 
    path('editar_os/<int:os_id>/', views.editar_os, name='editar_os'), 
    path('buscar_os/<int:os_id>/', views.buscar_os, name='buscar_os'),
    path('editar_os/', views.editar_os, name='editar_os_post'),
]
