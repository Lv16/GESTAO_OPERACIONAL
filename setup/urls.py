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
from django.conf import settings
from django.conf.urls.static import static
import os

from django.contrib.auth import views as auth_views
from GO import views
from GO import views_cadastro

from GO import views_ajuda
from GO import views_rdo
from GO import views_equipamentos
from GO import dashboard_views
from GO import views_dashboard_rdo

urlpatterns = [
    path('admin/', admin.site.urls),

    # Usar a LoginView customizada que redireciona Supervisores para /rdo/?mobile=1
    path('login/', views.CustomLoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.home, name='home'),

    path('os/<int:os_id>/detalhes/', views.detalhes_os, name='detalhes_os'),
    path('os/numero/<int:numero_os>/id/', views.get_os_id_by_number, name='get_os_id_by_number'),
    path('editar_os/<int:os_id>/', views.editar_os, name='editar_os'),
    path('buscar_os/<int:os_id>/', views.buscar_os, name='buscar_os'),
    path('editar_os/', views.editar_os, name='editar_os_post'),
    path('exportar_excel/', views.exportar_ordens_excel, name='exportar_excel'),
    path('equipamentos/exportar_excel/', views.exportar_equipamentos_excel, name='exportar_equipamentos_excel'),
    path('equipamentos/<int:pk>/relatorio_pdf/', views_equipamentos.relatorio_equipamento_pdf, name='relatorio_equipamento_pdf'),
    path('ajuda/', views_ajuda.ajuda, name='ajuda'),
    path('creditos/', views.creditos, name='creditos'),
    path('cadastrar_usuario/', views_cadastro.cadastrar_usuario, name='cadastrar_usuario'),
    path('cadastrar_cliente/', views_cadastro.cadastrar_cliente, name='cadastrar_cliente'),
    path('cadastrar_pessoa/', views_cadastro.cadastrar_pessoa, name='cadastrar_pessoa'),
    path('cadastrar_funcao/', views_cadastro.cadastrar_funcao, name='cadastrar_funcao'),
    path('cadastrar_unidade/', views_cadastro.cadastrar_unidade, name='cadastrar_unidade'),
    path('equipamentos/', views.equipamentos, name='equipamentos'),
    path('os/<int:os_id>/exportar_pdf/', views.exportar_os_pdf, name='exportar_os_pdf'),
    path('nova_os/', views.lista_servicos, name='lista_servicos'),
    path('ajuda/', views_ajuda.ajuda, name='ajuda'),
    path('relatorio_diario_operacao/', views_rdo.rdo, name='relatorio_diario_operacao'),
    path('rdo/', views_rdo.rdo, name='rdo'),
    path('rdo/<int:rdo_id>/print/', views_rdo.rdo_print, name='rdo_print'),
    path('rdo/<int:rdo_id>/pdf/', views_rdo.rdo_pdf, name='rdo_pdf'),
    path('rdo/<int:rdo_id>/page/', views_rdo.rdo_page, name='rdo_page'),
    # APIs RDO
    path('api/rdo/gerar-atividade/', views_rdo.gerar_atividade, name='api_rdo_gerar_atividade'),
    path('api/rdo/supervisor/salvar/', views_rdo.salvar_supervisor, name='api_rdo_salvar_supervisor'),
    path('api/os/<int:os_id>/', views_rdo.lookup_os, name='api_lookup_os'),
    path('api/os/<int:os_id>/tanks/', views_rdo.tanks_for_os, name='api_os_tanks'),
    path('api/rdo/<int:rdo_id>/', views_rdo.rdo_detail, name='api_rdo_detail'),
    path('api/rdo/translate/preview/', views_rdo.translate_preview, name='api_rdo_translate_preview'),
    path('api/rdo/pending_os/', views_rdo.pending_os_json, name='api_rdo_pending_os'),
    # Endpoint para obter dados canônicos e acumulados de um tanque por código
    path('api/rdo/tank/<str:codigo>/', views_rdo.rdo_tank_detail, name='api_rdo_tank_detail'),
    # Endpoint que retorna próximo número de RDO (compatibilidade com frontend)
    path('api/rdo/next_rdo/', views_rdo.next_rdo, name='api_rdo_next_rdo'),
    path('api/rdo/next/', views_rdo.next_rdo, name='api_rdo_next'),
    # Aliases para compatibilidade com o frontend (JS espera estas URLs)
    path('rdo/<int:rdo_id>/detail/', views_rdo.rdo_detail, name='rdo_detail'),
    path('rdo/pending_os_json/', views_rdo.pending_os_json, name='rdo_pending_os'),
    # Compatibilidade: permitir chamadas antigas/sem prefixo para next_rdo
    path('rdo/next_rdo/', views_rdo.next_rdo, name='rdo_next_rdo'),
    path('rdo/next/', views_rdo.next_rdo, name='rdo_next'),
    # Endpoint que retorna resumo de status de OS (deduplicado por numero_os)
    path('rdo/os_status_summary', dashboard_views.os_status_summary, name='rdo_os_status_summary'),
    # Rotas AJAX para compatibilidade com frontend
    path('api/rdo/create_ajax/', views_rdo.create_rdo_ajax, name='api_rdo_create_ajax'),
    path('api/rdo/update_ajax/', views_rdo.update_rdo_ajax, name='api_rdo_update_ajax'),
    path('api/rdo/delete_photo_basename/', views_rdo.delete_photo_basename_ajax, name='api_rdo_delete_photo_basename'),
    # caminhos alternativos (sem prefixo api) usados por scripts antigos
    path('rdo/create_ajax/', views_rdo.create_rdo_ajax, name='rdo_create_ajax'),
    path('rdo/update_ajax/', views_rdo.update_rdo_ajax, name='rdo_update_ajax'),
    # Endpoint para adicionar tanques incrementais a um RDO existente
    path('api/rdo/<int:rdo_id>/add_tank/', views_rdo.add_tank_ajax, name='api_rdo_add_tank'),
    path('rdo/<int:rdo_id>/add_tank/', views_rdo.add_tank_ajax, name='rdo_add_tank'),
    # Endpoint para upload incremental de fotos (cliente pode chamar após criar RDO)
    path('api/rdo/<int:rdo_id>/upload_photos/', views_rdo.upload_rdo_photos, name='api_rdo_upload_photos'),
    path('rdo/<int:rdo_id>/upload_photos/', views_rdo.upload_rdo_photos, name='rdo_upload_photos'),
    # Endpoint para atualizar um RdoTanque existente
    path('api/rdo/tank/<int:tank_id>/update/', views_rdo.update_rdo_tank_ajax, name='api_rdo_update_tank'),
    path('rdo/tank/<int:tank_id>/update/', views_rdo.update_rdo_tank_ajax, name='rdo_update_tank'),
    # Endpoint para salvar equipamento vindo do modal
    path('api/equipamentos/save/', views_equipamentos.save_equipamento_ajax, name='api_equipamentos_save'),
    # Endpoints compatíveis para obter equipamento por id (GET) — compatibilidade com frontend antigo
    path('api/equipamentos/<int:pk>/', views_equipamentos.get_equipamento_ajax, name='api_equipamentos_get'),
    path('api/equipamentos/<int:pk>/json/', views_equipamentos.get_equipamento_ajax, name='api_equipamentos_get_json'),
    path('api/equipamentos/get/', views_equipamentos.get_equipamento_ajax, name='api_equipamentos_get_query'),
]

# Registrar endpoints da dashboard
urlpatterns += [
    path('api/dashboard/ordens_por_dia/', dashboard_views.ordens_por_dia, name='api_dashboard_ordens_por_dia'),
    path('api/dashboard/status_os/', dashboard_views.status_os, name='api_dashboard_status_os'),
    path('api/dashboard/servicos_mais_frequentes/', dashboard_views.servicos_mais_frequentes, name='api_dashboard_servicos_mais_frequentes'),
    path('api/dashboard/top_clientes/', dashboard_views.top_clientes, name='api_dashboard_top_clientes'),
    path('api/dashboard/metodos_mais_utilizados/', dashboard_views.metodos_mais_utilizados, name='api_dashboard_metodos_mais_utilizados'),
    path('api/dashboard/supervisores_tempo_medio/', dashboard_views.supervisores_tempo_medio, name='api_dashboard_supervisores_tempo_medio'),
    path('api/dashboard/kpis/', dashboard_views.dashboard_kpis, name='api_dashboard_kpis'),
    path('api/dashboard/supervisores_status/', dashboard_views.supervisores_status, name='api_dashboard_supervisores_status'),
    # Novos endpoints para dashboard RDO
    path('api/rdo-dashboard/hh_confinado_por_dia/', dashboard_views.rdo_soma_hh_confinado_por_dia, name='api_rdo_hh_confinado'),
    path('api/rdo-dashboard/hh_fora_confinado_por_dia/', dashboard_views.rdo_soma_hh_fora_confinado_por_dia, name='api_rdo_hh_fora_confinado'),
    path('api/rdo-dashboard/ensacamento_por_dia/', dashboard_views.rdo_ensacamento_por_dia, name='api_rdo_ensacamento'),
    path('api/rdo-dashboard/tambores_por_dia/', dashboard_views.rdo_tambores_por_dia, name='api_rdo_tambores'),
    path('api/rdo-dashboard/residuos_liquido_por_dia/', dashboard_views.rdo_residuos_liquido_por_dia, name='api_rdo_residuos_liquido'),
    path('api/rdo-dashboard/residuos_solido_por_dia/', dashboard_views.rdo_residuos_solido_por_dia, name='api_rdo_residuos_solido'),
    path('api/rdo-dashboard/liquido_por_supervisor/', dashboard_views.rdo_liquido_por_supervisor, name='api_rdo_liquido_supervisor'),
    path('api/rdo-dashboard/solido_por_supervisor/', dashboard_views.rdo_solido_por_supervisor, name='api_rdo_solido_supervisor'),
    path('api/rdo-dashboard/volume_por_tanque/', dashboard_views.rdo_volume_por_tanque, name='api_rdo_volume_tanque'),
    path('api/rdo-dashboard/pob_comparativo/', views_dashboard_rdo.pob_comparativo, name='api_rdo_pob_comparativo'),
    path('api/rdo-dashboard/top_supervisores/', views_dashboard_rdo.top_supervisores, name='api_rdo_top_supervisores'),
    path('api/rdo-dashboard/summary_operations/', views_dashboard_rdo.summary_operations_json, name='api_rdo_summary_operations'),
    path('rdo/api/get_ordens_servico/', views_dashboard_rdo.get_ordens_servico, name='api_get_ordens_servico'),
    # Endpoint para contagem de movimentações por OS (usado no dashboard quando filtrar por cliente/unidade)
    path('rdo/api/get_os_movimentacoes_count/', views_dashboard_rdo.get_os_movimentacoes_count, name='api_get_os_movimentacoes_count'),
    # Rota para renderizar o dashboard RDO
    path('dashboard/rdo/', dashboard_views.rdo_dashboard_view, name='rdo_dashboard'),
]

try:
    # Debug-only route to parse supervisor payloads without persisting (safe for testing)
    if settings.DEBUG:
        try:
            urlpatterns += [
                path('api/rdo/debug_parse_supervisor/', views_rdo.debug_parse_supervisor, name='api_rdo_debug_parse_supervisor'),
            ]
        except Exception:
            # if import issues or similar, don't break URL configuration
            pass
except Exception:
    # qualquer erro aqui não deve impedir a inicialização de URLs
    pass

# Controlar se Django deve servir arquivos de mídia em produção via variável de
# ambiente `DJANGO_SERVE_MEDIA`. Valores aceitos: '1', 'true', 'yes', 'on' (case-insensitive).
# Em desenvolvimento (`DEBUG=True`) o Django continua servindo normalmente.
def _env_bool(varname):
    v = os.environ.get(varname, '')
    return str(v).strip().lower() in ('1', 'true', 'yes', 'on')

if settings.DEBUG or _env_bool('DJANGO_SERVE_MEDIA'):
    try:
        urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
        # Compatibilidade rápida: também expor o caminho legado '/fotos_rdo/'
        # para permitir que clientes que ainda usam esse prefixo acessem os arquivos
        # diretamente quando DJANGO_SERVE_MEDIA estiver ativo.
        try:
            urlpatterns += static('/fotos_rdo/', document_root=settings.MEDIA_ROOT)
        except Exception:
            pass
    except Exception:
        pass
