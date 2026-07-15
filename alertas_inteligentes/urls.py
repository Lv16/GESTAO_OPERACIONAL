from django.urls import path
from . import views

app_name = "alertas_inteligentes"

urlpatterns = [
    path("", views.listar_alertas, name="listar_alertas"),
    path("resolver/<int:alerta_id>/", views.resolver_alerta, name="resolver_alerta"),
    path("ignorar/<int:alerta_id>/", views.ignorar_alerta, name="ignorar_alerta"),
    path(
        "operacional/resolver/<int:alerta_id>/",
        views.resolver_alerta_operacional,
        name="resolver_alerta_operacional",
    ),
    path(
        "operacional/ignorar/<int:alerta_id>/",
        views.ignorar_alerta_operacional,
        name="ignorar_alerta_operacional",
    ),
    path("assistente-rdo/", views.assistente_rdo, name="assistente_rdo"),
    path(
        "supervisao-aprendizado/",
        views.supervisionar_aprendizado,
        name="supervisionar_aprendizado",
    ),
]
