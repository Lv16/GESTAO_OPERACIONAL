from django.urls import path
from . import views

app_name = "alertas_inteligentes"

urlpatterns = [
    path("", views.listar_alertas, name="listar_alertas"),
    path("api/notificacoes/", views.api_notificacoes, name="api_notificacoes"),
    path(
        "api/notificacoes/marcar-todas-lidas/",
        views.api_notificacoes_marcar_todas_lidas,
        name="api_notificacoes_marcar_todas_lidas",
    ),
    path(
        "api/notificacoes/<str:source>/<int:alert_id>/",
        views.api_notificacao_detalhe,
        name="api_notificacao_detalhe",
    ),
    path(
        "api/notificacoes/<str:source>/<int:alert_id>/leitura/",
        views.api_notificacao_leitura,
        name="api_notificacao_leitura",
    ),
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
