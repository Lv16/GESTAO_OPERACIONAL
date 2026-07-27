import re
import os

from django.utils import timezone

from .rdo_access import (
    user_can_open_or_edit_rdo,
    user_can_edit_system,
    user_can_manage_rdo_permission_users,
    user_can_manage_responsaveis_coordenadores,
    user_has_rdo_view_only_access,
    user_has_read_only_access,
    user_can_use_alerts_ai,
)

MOBILE_UA_RE = re.compile(r"Mobile|Android|iPhone|iPad|iPod|Opera Mini|IEMobile|WPDesktop", re.I)

def mobile_detector(request):
    force_mobile = False
    try:
        q = request.GET.get('force_mobile') or request.POST.get('force_mobile')
        if q in ('1', 'true', 'yes'):
            force_mobile = True

        ua = ''
        try:
            ua = request.META.get('HTTP_USER_AGENT','') or ''
        except Exception:
            ua = ''

        if ua and MOBILE_UA_RE.search(ua):
            force_mobile = True
    except Exception:
        pass

    android_url = (os.environ.get('MOBILE_APP_ANDROID_URL') or '').strip()
    ios_url = (os.environ.get('MOBILE_APP_IOS_URL') or '').strip()
    enabled_flag = (os.environ.get('MOBILE_APP_DOWNLOAD_ENABLED') or '').strip().lower()
    enabled = enabled_flag in ('1', 'true', 'yes', 'on') or bool(android_url or ios_url)

    return {
        'force_mobile': force_mobile,
        'mobile_app_download_enabled': enabled,
        'mobile_app_android_url': android_url,
        'mobile_app_ios_url': ios_url,
    }


def rdo_permission_flags(request):
    user = getattr(request, 'user', None)
    return {
        'can_edit_system': user_can_edit_system(user),
        'can_open_or_edit_rdo': user_can_open_or_edit_rdo(user),
        'can_manage_rdo_permission_users': user_can_manage_rdo_permission_users(user),
        'can_manage_responsaveis_coordenadores': user_can_manage_responsaveis_coordenadores(user),
        'is_rdo_view_only_user': user_has_rdo_view_only_access(user),
        'is_read_only_user': user_has_read_only_access(user),
    }


ACTIVE_MODULES = {
    'home': 'ordens',
    'detalhes_os': 'ordens',
    'editar_os': 'ordens',
    'editar_os_post': 'ordens',
    'lista_servicos': 'ordens',
    'planejamento': 'planejamento',
    'planejamento_documento': 'planejamento',
    'equipamentos': 'equipamentos',
    'supervisor_access_dashboard': 'metricas',
    'rdo_dashboard': 'dashboard_rdo',
    'rdo': 'rdo',
    'relatorio_diario_operacao': 'rdo',
    'rdo_page': 'rdo',
    'rdo_detail': 'rdo',
    'cadastrar_usuario': 'usuarios',
    'gerenciar_permissoes_rdo': 'permissoes',
    'cadastrar_pessoa': 'pessoas',
    'cadastrar_funcao': 'funcoes',
    'cadastrar_cliente': 'clientes',
    'cadastrar_unidade': 'unidades',
    'curva_s': 'relatorio_tecnico',
    'comercial_propostas': 'comercial',
    'comercial_exportar_excel': 'comercial',
    'comercial_criar_proposta': 'comercial',
    'comercial_criar_cliente': 'comercial',
    'comercial_criar_unidade': 'comercial',
    'comercial_agenda_followups': 'comercial',
    'comercial_criar_followup': 'comercial',
    'comercial_detalhe_proposta': 'comercial',
    'comercial_atualizar_proposta': 'comercial',
    'comercial_atualizar_status': 'comercial',
    'comercial_resumo_propostas': 'comercial',
    'listar_alertas': 'synchro_ai',
    'assistente_rdo': 'synchro_ai',
    'supervisionar_aprendizado': 'synchro_ai',
    'mobile_app_download': 'mobile_app',
    'ajuda': 'ajuda',
}


def _active_shell_module(request):
    match = getattr(request, 'resolver_match', None)
    url_name = getattr(match, 'url_name', '') or ''
    if url_name in ACTIVE_MODULES:
        return ACTIVE_MODULES[url_name]
    if url_name.startswith(('rdo_', 'api_rdo_')):
        return 'rdo'
    if url_name.startswith(('equipamentos_', 'api_equipamentos_')):
        return 'equipamentos'
    if url_name.startswith(('planejamento_', 'api_planejamento_')):
        return 'planejamento'
    if url_name.startswith('comercial_'):
        return 'comercial'
    if getattr(match, 'namespace', '') == 'alertas_inteligentes':
        return 'synchro_ai'
    return ''


def synchro_shell(request):
    """Global, permission-aware data used only by the shared header and drawer."""
    user = getattr(request, 'user', None)
    authenticated = bool(user and getattr(user, 'is_authenticated', False))
    can_use_ai = user_can_use_alerts_ai(user) if authenticated else False

    full_name = (user.get_full_name() or user.get_username()) if authenticated else ''
    name_parts = [part for part in full_name.split() if part]
    initials = ''.join(part[0] for part in name_parts[:2]).upper() or 'US'
    if authenticated and getattr(user, 'is_superuser', False):
        role = 'Administrador'
    elif authenticated:
        first_group = user.groups.order_by('name').values_list('name', flat=True).first()
        role = first_group or ('Equipe Synchro' if getattr(user, 'is_staff', False) else 'Usuário')
    else:
        role = ''

    alerts = []
    alert_count = 0
    if can_use_ai:
        # Both are existing Synchro AI sources. There is no read flag, so the
        # established pending status is used for today's counter.
        from alertas_inteligentes.models import AlertaInteligente, AlertaOperacionalInteligente

        today = timezone.localdate()
        rdo_qs = AlertaInteligente.objects.filter(status='pendente', criado_em__date=today)
        operational_qs = AlertaOperacionalInteligente.objects.filter(status='pendente', criado_em__date=today)
        alert_count = rdo_qs.count() + operational_qs.count()

        for item in rdo_qs.select_related('rdo').order_by('-criado_em')[:5]:
            alerts.append({
                'title': item.identificacao_operacional,
                'message': item.mensagem,
                'priority': item.prioridade,
                'priority_label': item.get_prioridade_display(),
                'created_at': item.criado_em,
            })
        for item in operational_qs.select_related('ordem_servico').order_by('-criado_em')[:5]:
            alerts.append({
                'title': item.identificacao_operacional,
                'message': item.mensagem,
                'priority': item.prioridade,
                'priority_label': item.get_prioridade_display(),
                'created_at': item.criado_em,
            })
        alerts = sorted(alerts, key=lambda item: item['created_at'], reverse=True)[:5]

    return {
        'can_use_alerts_ai': can_use_ai,
        'daily_ai_alert_count': alert_count,
        'daily_ai_alerts': alerts,
        'synchro_active_module': _active_shell_module(request),
        'synchro_user_name': full_name,
        'synchro_user_initials': initials,
        'synchro_user_role': role,
    }
