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
from django.contrib.auth import views as auth_views
from GO import views
from GO import views_cadastro

urlpatterns = [
    path('admin/', admin.site.urls),

    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.home, name='home'),

    path('os/<int:os_id>/detalhes/', views.detalhes_os, name='detalhes_os'),
    path('os/numero/<int:numero_os>/id/', views.get_os_id_by_number, name='get_os_id_by_number'),
    path('editar_os/<int:os_id>/', views.editar_os, name='editar_os'),
    path('buscar_os/<int:os_id>/', views.buscar_os, name='buscar_os'),
    path('editar_os/', views.editar_os, name='editar_os_post'),
    path('exportar_excel/', views.exportar_ordens_excel, name='exportar_excel'),

    path('cadastrar_usuario/', views_cadastro.cadastrar_usuario, name='cadastrar_usuario'),
    path('cadastrar_cliente/', views_cadastro.cadastrar_cliente, name='cadastrar_cliente'),
    path('cadastrar_unidade/', views_cadastro.cadastrar_unidade, name='cadastrar_unidade'),
    path('os/<int:os_id>/exportar_pdf/', views.exportar_os_pdf, name='exportar_os_pdf'),
]
