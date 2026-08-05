import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.dateparse import parse_date
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from GO.models import OrdemServico, Pessoa, PlanejamentoEquipeHistorico, PlanejamentoEquipeMembro, PlanejamentoEquipeOS


def _get_user_display_name(user):
    if not user:
        return ''
    try:
        full_name = user.get_full_name()
        if full_name:
            return full_name
    except Exception:
        pass
    for attr in ('username', 'email'):
        try:
            value = getattr(user, attr, '')
            if value:
                return str(value)
        except Exception:
            continue
    return ''


def _normalize_status_value(value):
    return str(value or '').strip().casefold()


def _ordem_servico_bloqueada(os_obj):
    status_linha = _normalize_status_value(getattr(os_obj, 'status_geral', ''))
    status_operacao = _normalize_status_value(getattr(os_obj, 'status_operacao', ''))
    return status_linha in {'finalizado', 'finalizada'} or status_operacao in {'finalizado', 'finalizada'}


def _planejamento_requer_justificativa(planejamento):
    return bool(planejamento and planejamento.status == PlanejamentoEquipeOS.STATUS_CONCLUIDO)


def _get_planejamento_home_block_message():
    return 'Esta movimentação está finalizada na Home e o planejamento está bloqueado para alterações.'


def _get_planejamento_justificativa_message():
    return 'Planejamento já concluído. Informe uma justificativa para realizar alterações.'


def _get_planejamento_edit_block_reason(planejamento):
    ordem_servico = getattr(planejamento, 'ordem_servico', None)
    if ordem_servico and _ordem_servico_bloqueada(ordem_servico):
        return _get_planejamento_home_block_message()
    if planejamento.status == PlanejamentoEquipeOS.STATUS_CANCELADO:
        return 'Planejamento cancelado não permite edição.'
    return ''


def _get_os_edit_block_reason(os_obj):
    if _ordem_servico_bloqueada(os_obj):
        return _get_planejamento_home_block_message()
    planejamento = getattr(os_obj, 'planejamento_equipe', None)
    if planejamento and planejamento.status == PlanejamentoEquipeOS.STATUS_CANCELADO:
        return 'Planejamento cancelado não permite edição.'
    return ''


def _validar_funcao_planejada(funcao):
    funcoes_validas = {value for value, _ in OrdemServico.FUNCOES}
    if not funcao or funcao not in funcoes_validas:
        raise ValidationError('Função planejada inválida.')


def _parse_optional_time_text(raw_value, field_label):
    raw_value = str(raw_value or '').strip()
    if not raw_value:
        return ''
    if len(raw_value) != 5 or raw_value[2] != ':':
        raise ValidationError(f'{field_label} invÃ¡lido. Use o formato HH:MM.')
    hours, minutes = raw_value.split(':', 1)
    if not (hours.isdigit() and minutes.isdigit()):
        raise ValidationError(f'{field_label} invÃ¡lido. Use o formato HH:MM.')
    hour = int(hours)
    minute = int(minutes)
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValidationError(f'{field_label} invÃ¡lido. Use o formato HH:MM.')
    return f'{hour:02d}:{minute:02d}'


def _serialize_membro(membro):
    return {
        'id': membro.id,
        'planejamento_id': membro.planejamento_id,
        'pessoa_id': membro.pessoa_id,
        'nome_snapshot': membro.nome_snapshot,
        'funcao_planejada': membro.funcao_planejada,
        'status': membro.status,
        'substitui_id': membro.substitui_id,
        'substitui_nome_snapshot': getattr(getattr(membro, 'substitui', None), 'nome_snapshot', '') or '',
        'motivo_substituicao': membro.motivo_substituicao or '',
        'data_inicio': membro.data_inicio.isoformat() if membro.data_inicio else None,
        'data_fim': membro.data_fim.isoformat() if membro.data_fim else None,
        'data_desembarque': membro.data_desembarque.isoformat() if membro.data_desembarque else None,
        'horario_desembarque': membro.horario_desembarque or '',
        'local_desembarque_membro': membro.local_desembarque_membro or '',
        'observacao_desembarque': membro.observacao_desembarque or '',
        'ordem': membro.ordem,
        'observacao': membro.observacao or '',
        'criado_em': membro.criado_em.isoformat() if membro.criado_em else None,
        'atualizado_em': membro.atualizado_em.isoformat() if membro.atualizado_em else None,
    }


def _split_planejamento_membros_por_status(membros):
    ativos = []
    substituidos = []
    cancelados = []
    for membro in membros:
        status = _normalize_status_value(getattr(membro, 'status', ''))
        if status == _normalize_status_value(PlanejamentoEquipeMembro.STATUS_ATIVO):
            ativos.append(membro)
        elif status in {
            _normalize_status_value(PlanejamentoEquipeMembro.STATUS_SUBSTITUIDO),
            _normalize_status_value('Substituido'),
        }:
            substituidos.append(membro)
        elif status == _normalize_status_value(PlanejamentoEquipeMembro.STATUS_CANCELADO):
            cancelados.append(membro)
    return ativos, substituidos, cancelados


def _snapshot_planejamento_cabecalho(planejamento):
    return {
        'titulo_planejamento': planejamento.titulo_planejamento or '',
        'data_prevista_subida': planejamento.data_prevista_subida.isoformat() if planejamento.data_prevista_subida else None,
        'horario_previsto_subida': planejamento.horario_previsto_subida or '',
        'local_subida': planejamento.local_subida or '',
        'observacao': planejamento.observacao or '',
        'data_prevista_desembarque': planejamento.data_prevista_desembarque.isoformat() if planejamento.data_prevista_desembarque else None,
        'horario_previsto_desembarque': planejamento.horario_previsto_desembarque or '',
        'local_desembarque': planejamento.local_desembarque or '',
        'observacao_desembarque': planejamento.observacao_desembarque or '',
        'status': planejamento.status,
    }


def _snapshot_membro(membro):
    return {
        'id': membro.id,
        'pessoa_id': membro.pessoa_id,
        'nome_snapshot': membro.nome_snapshot,
        'funcao_planejada': membro.funcao_planejada,
        'status': membro.status,
        'data_inicio': membro.data_inicio.isoformat() if membro.data_inicio else None,
        'data_fim': membro.data_fim.isoformat() if membro.data_fim else None,
        'data_desembarque': membro.data_desembarque.isoformat() if membro.data_desembarque else None,
        'horario_desembarque': membro.horario_desembarque or '',
        'local_desembarque_membro': membro.local_desembarque_membro or '',
        'observacao_desembarque': membro.observacao_desembarque or '',
        'ordem': membro.ordem,
        'observacao': membro.observacao or '',
        'motivo_substituicao': membro.motivo_substituicao or '',
        'substitui_id': membro.substitui_id,
    }


def _extract_request_justificativa(request):
    if request.content_type and 'application/json' in request.content_type:
        payload = _parse_json_body(request)
        return payload, str(payload.get('justificativa') or '').strip()
    return None, str(request.POST.get('justificativa') or '').strip()


def _require_justificativa_if_needed(request, planejamento):
    payload = None
    justificativa = ''
    if _planejamento_requer_justificativa(planejamento):
        payload, justificativa = _extract_request_justificativa(request)
        if not justificativa:
            raise ValidationError(_get_planejamento_justificativa_message())
    return payload, justificativa


def _registrar_historico_planejamento(planejamento, acao, justificativa, criado_por, membro=None, dados_anteriores=None, dados_novos=None):
    PlanejamentoEquipeHistorico.objects.create(
        planejamento=planejamento,
        membro=membro,
        acao=acao,
        justificativa=justificativa or '',
        dados_anteriores=dados_anteriores,
        dados_novos=dados_novos,
        criado_por=criado_por,
    )


def _serialize_planejamento(planejamento):
    membros = list(getattr(planejamento, '_prefetched_objects_cache', {}).get('membros', []) or planejamento.membros.all())
    historicos = list(getattr(planejamento, '_prefetched_objects_cache', {}).get('historicos', []) or planejamento.historicos.all())
    ativos, substituidos, cancelados = _split_planejamento_membros_por_status(membros)
    block_reason = _get_planejamento_edit_block_reason(planejamento)
    requer_justificativa = _planejamento_requer_justificativa(planejamento) and not block_reason
    return {
        'id': planejamento.id,
        'ordem_servico_id': planejamento.ordem_servico_id,
        'supervisor_id': planejamento.supervisor_id,
        'supervisor_nome_snapshot': planejamento.supervisor_nome_snapshot or '',
        'titulo_planejamento': planejamento.titulo_planejamento or '',
        'data_prevista_subida': planejamento.data_prevista_subida.isoformat() if planejamento.data_prevista_subida else None,
        'horario_previsto_subida': planejamento.horario_previsto_subida or '',
        'local_subida': planejamento.local_subida or '',
        'data_prevista_desembarque': planejamento.data_prevista_desembarque.isoformat() if planejamento.data_prevista_desembarque else None,
        'horario_previsto_desembarque': planejamento.horario_previsto_desembarque or '',
        'local_desembarque': planejamento.local_desembarque or '',
        'observacao_desembarque': planejamento.observacao_desembarque or '',
        'status': planejamento.status,
        'observacao': planejamento.observacao or '',
        'criado_por': _get_user_display_name(planejamento.criado_por),
        'atualizado_por': _get_user_display_name(planejamento.atualizado_por),
        'criado_em': planejamento.criado_em.isoformat() if planejamento.criado_em else None,
        'atualizado_em': planejamento.atualizado_em.isoformat() if planejamento.atualizado_em else None,
        'permite_edicao': not bool(block_reason),
        'motivo_bloqueio_edicao': block_reason,
        'requer_justificativa_alteracao': bool(requer_justificativa),
        'motivo_justificativa_alteracao': _get_planejamento_justificativa_message() if requer_justificativa else '',
        'quantidade_membros_ativos': len(ativos),
        'quantidade_membros_substituidos': len(substituidos),
        'quantidade_membros_cancelados': len(cancelados),
        'membros_ativos': [_serialize_membro(m) for m in ativos],
        'membros_substituidos': [_serialize_membro(m) for m in substituidos],
        'membros_cancelados': [_serialize_membro(m) for m in cancelados],
        'historicos_count': len(historicos),
    }


def _serialize_os(os_obj):
    planejamento = getattr(os_obj, 'planejamento_equipe', None)
    block_reason = _get_os_edit_block_reason(os_obj)
    payload = {
        'id': os_obj.id,
        'numero_os': os_obj.numero_os,
        'cliente': getattr(os_obj, 'cliente', '') or '',
        'unidade': getattr(getattr(os_obj, 'Unidade', None), 'nome', '') or '',
        'servico': os_obj.servico or '',
        'metodo': os_obj.metodo or '',
        'tanque': os_obj.tanque or '',
        'especificacao': os_obj.especificacao or '',
        'coordenador': os_obj.coordenador or '',
        'status_linha': os_obj.status_geral or '',
        'status_operacao': os_obj.status_operacao or '',
        'status_planejamento': os_obj.status_planejamento or 'Pendente',
        'supervisor_nome': _get_user_display_name(getattr(os_obj, 'supervisor', None)),
        'pob': os_obj.pob,
        'data_inicio': os_obj.data_inicio.isoformat() if os_obj.data_inicio else None,
        'data_fim': os_obj.data_fim.isoformat() if os_obj.data_fim else None,
        'tem_planejamento': bool(planejamento),
        'permite_edicao': not bool(block_reason),
        'motivo_bloqueio_edicao': block_reason,
        'home_finalizada': _ordem_servico_bloqueada(os_obj),
        'planejamento_id': None,
        'planejamento_status': '',
        'quantidade_membros_ativos': 0,
        'quantidade_membros_substituidos': 0,
        'quantidade_membros_cancelados': 0,
    }
    if planejamento:
        serialized = _serialize_planejamento(planejamento)
        payload.update(
            {
                'planejamento_id': planejamento.id,
                'planejamento_status': planejamento.status,
                'data_embarque': serialized['data_prevista_subida'],
                'requer_justificativa_alteracao': serialized['requer_justificativa_alteracao'],
                'quantidade_membros_ativos': serialized['quantidade_membros_ativos'],
                'quantidade_membros_substituidos': serialized['quantidade_membros_substituidos'],
                'quantidade_membros_cancelados': serialized['quantidade_membros_cancelados'],
            }
        )
    else:
        payload['data_embarque'] = None
        payload['requer_justificativa_alteracao'] = False
    return payload


def _recalcular_status_planejamento_os(ordem_servico):
    try:
        planejamento = ordem_servico.planejamento_equipe
    except PlanejamentoEquipeOS.DoesNotExist:
        planejamento = None

    if not planejamento:
        novo_status = 'Pendente'
    elif planejamento.status == PlanejamentoEquipeOS.STATUS_RASCUNHO:
        novo_status = 'Em andamento'
    elif planejamento.status == PlanejamentoEquipeOS.STATUS_CONCLUIDO:
        novo_status = 'Concluído'
    else:
        novo_status = 'Pendente'

    if ordem_servico.status_planejamento != novo_status:
        ordem_servico.status_planejamento = novo_status
        ordem_servico.save(update_fields=['status_planejamento'])
    return novo_status


def _get_planejamento_with_relations_queryset():
    return PlanejamentoEquipeOS.objects.select_related(
        'ordem_servico',
        'ordem_servico__Cliente',
        'ordem_servico__Unidade',
        'ordem_servico__supervisor',
        'supervisor',
        'criado_por',
        'atualizado_por',
    ).prefetch_related(
        Prefetch(
            'membros',
            queryset=PlanejamentoEquipeMembro.objects.select_related('substitui').order_by('ordem', 'id'),
        ),
        Prefetch(
            'historicos',
            queryset=PlanejamentoEquipeHistorico.objects.select_related('membro', 'criado_por').order_by('-criado_em', '-id'),
        ),
    )


def _parse_positive_small_int(raw_value, default=0):
    if raw_value in (None, ''):
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        raise ValidationError('Valor numérico inválido.')
    if value < 0:
        raise ValidationError('Valor numérico inválido.')
    return value


def _parse_optional_date(raw_value, field_label):
    raw_value = str(raw_value or '').strip()
    if not raw_value:
        return None
    parsed = parse_date(raw_value)
    if parsed is None:
        raise ValidationError(f'{field_label} inválida. Use o formato YYYY-MM-DD.')
    return parsed


def _parse_json_body(request):
    try:
        body = (request.body or b'').decode('utf-8').strip()
    except UnicodeDecodeError:
        raise ValidationError('Corpo JSON inválido.')
    if not body:
        return {}
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise ValidationError('Corpo JSON inválido.')
    if not isinstance(payload, dict):
        raise ValidationError('O corpo JSON deve ser um objeto.')
    return payload


def _build_membro_from_request(request, planejamento, instance=None, allow_status_edit=False):
    pessoa = None
    pessoa_id = request.POST.get('pessoa_id')
    if pessoa_id:
        pessoa = get_object_or_404(Pessoa, pk=pessoa_id)

    nome_snapshot = (request.POST.get('nome_snapshot') or '').strip()
    funcao_planejada = (request.POST.get('funcao_planejada') or '').strip()
    ordem = _parse_positive_small_int(request.POST.get('ordem'), default=getattr(instance, 'ordem', 0) if instance else 0)
    data_inicio = _parse_optional_date(request.POST.get('data_inicio'), 'Data de início') if request.POST.get('data_inicio') else None
    observacao = request.POST.get('observacao')
    data_desembarque = _parse_optional_date(request.POST.get('data_desembarque'), 'Data de desembarque') if request.POST.get('data_desembarque') else None
    horario_desembarque = _parse_optional_time_text(request.POST.get('horario_desembarque'), 'HorÃ¡rio de desembarque')
    local_desembarque_membro = str(request.POST.get('local_desembarque_membro') or '').strip()
    observacao_desembarque = request.POST.get('observacao_desembarque') or ''

    _validar_funcao_planejada(funcao_planejada)
    if not nome_snapshot and not pessoa:
        raise ValidationError('Informe nome ou pessoa para o membro planejado.')

    membro = instance or PlanejamentoEquipeMembro(planejamento=planejamento)
    membro.pessoa = pessoa
    membro.nome_snapshot = nome_snapshot
    membro.funcao_planejada = funcao_planejada
    membro.ordem = ordem
    membro.data_inicio = data_inicio
    membro.observacao = observacao
    membro.data_desembarque = data_desembarque
    membro.horario_desembarque = horario_desembarque
    membro.local_desembarque_membro = local_desembarque_membro
    membro.observacao_desembarque = observacao_desembarque
    if not allow_status_edit and not instance:
        membro.status = PlanejamentoEquipeMembro.STATUS_ATIVO
    return membro


def _aplicar_agenda_inicial_do_planejamento(membro, planejamento):
    """Copia a agenda geral somente para a primeira alocacao da equipe."""
    if membro.data_inicio is None:
        membro.data_inicio = planejamento.data_prevista_subida
    if membro.data_desembarque is None:
        membro.data_desembarque = planejamento.data_prevista_desembarque
    if not membro.horario_desembarque:
        membro.horario_desembarque = planejamento.horario_previsto_desembarque or ''
    if not membro.local_desembarque_membro:
        membro.local_desembarque_membro = planejamento.local_desembarque or ''
    if not membro.observacao_desembarque:
        membro.observacao_desembarque = planejamento.observacao_desembarque or ''
    return membro


@login_required(login_url='/login/')
def planejamento_home(request):
    return render(
        request,
        'planejamento.html',
        {
            'pessoas_planejamento': list(Pessoa.objects.order_by('nome').values('id', 'nome', 'funcao')),
            'funcoes_planejamento': [{'value': value, 'label': label} for value, label in OrdemServico.FUNCOES if value],
        },
    )


@login_required(login_url='/login/')
@require_GET
def api_planejamento_os_list(request):
    query = (request.GET.get('q') or '').strip()
    status_filter = _normalize_status_value(request.GET.get('status') or 'all')
    qs = (
        OrdemServico.objects.all()
        .select_related('Cliente', 'Unidade', 'supervisor', 'planejamento_equipe__supervisor')
        .prefetch_related(
            Prefetch(
                'planejamento_equipe__membros',
                queryset=PlanejamentoEquipeMembro.objects.select_related('substitui').order_by('ordem', 'id'),
            )
        )
        .order_by('-data_inicio', '-numero_os', '-id')
    )
    if query:
        qs = qs.filter(
            Q(id__icontains=query)
            | Q(numero_os__icontains=query)
            | Q(Cliente__nome__icontains=query)
            | Q(Unidade__nome__icontains=query)
            | Q(servico__icontains=query)
            | Q(metodo__icontains=query)
            | Q(supervisor__username__icontains=query)
            | Q(supervisor__first_name__icontains=query)
            | Q(supervisor__last_name__icontains=query)
            | Q(supervisor__email__icontains=query)
            | Q(coordenador__icontains=query)
            | Q(tanque__icontains=query)
            | Q(especificacao__icontains=query)
        )
    if status_filter == 'sem_planejamento':
        qs = qs.filter(planejamento_equipe__isnull=True)
    elif status_filter == 'rascunho':
        qs = qs.filter(planejamento_equipe__status=PlanejamentoEquipeOS.STATUS_RASCUNHO)
    elif status_filter == 'concluido':
        qs = qs.filter(planejamento_equipe__status=PlanejamentoEquipeOS.STATUS_CONCLUIDO)
    elif status_filter == 'cancelado':
        qs = qs.filter(planejamento_equipe__status=PlanejamentoEquipeOS.STATUS_CANCELADO)
    items = [_serialize_os(item) for item in qs]
    return JsonResponse({'success': True, 'count': len(items), 'items': items, 'filters': {'q': query, 'status': status_filter}})


@login_required(login_url='/login/')
@require_GET
def api_planejamento_os_detail(request, os_id):
    os_obj = get_object_or_404(
        OrdemServico.objects.select_related('Cliente', 'Unidade', 'supervisor', 'planejamento_equipe__supervisor').prefetch_related(
            Prefetch(
                'planejamento_equipe__membros',
                queryset=PlanejamentoEquipeMembro.objects.select_related('substitui').order_by('ordem', 'id'),
            )
        ),
        pk=os_id,
    )
    planejamento = getattr(os_obj, 'planejamento_equipe', None)
    return JsonResponse(
        {
            'success': True,
            'os': _serialize_os(os_obj),
            'tem_planejamento': bool(planejamento),
            'planejamento': _serialize_planejamento(planejamento) if planejamento else None,
        }
    )


@login_required(login_url='/login/')
@require_POST
def api_planejamento_get_or_create(request, os_id):
    os_obj = get_object_or_404(OrdemServico.objects.select_related('supervisor', 'Cliente', 'Unidade'), pk=os_id)
    if _ordem_servico_bloqueada(os_obj):
        return JsonResponse({'success': False, 'error': 'A operação desta OS está finalizada e não aceita novo planejamento.'}, status=400)
    with transaction.atomic():
        planejamento, created = PlanejamentoEquipeOS.objects.get_or_create(
            ordem_servico=os_obj,
            defaults={
                'supervisor': os_obj.supervisor,
                'criado_por': request.user,
                'atualizado_por': request.user,
            },
        )
        if not created and planejamento.atualizado_por_id != request.user.id:
            planejamento.atualizado_por = request.user
            planejamento.save(update_fields=['atualizado_por', 'atualizado_em'])
        _recalcular_status_planejamento_os(os_obj)
    planejamento = _get_planejamento_with_relations_queryset().get(pk=planejamento.pk)
    os_obj = OrdemServico.objects.select_related('Cliente', 'Unidade', 'supervisor', 'planejamento_equipe__supervisor').get(pk=os_obj.pk)
    return JsonResponse({'success': True, 'created': created, 'planejamento': _serialize_planejamento(planejamento), 'os': _serialize_os(os_obj)})


@login_required(login_url='/login/')
@require_GET
def api_planejamento_detail(request, planejamento_id):
    planejamento = get_object_or_404(_get_planejamento_with_relations_queryset(), pk=planejamento_id)
    return JsonResponse(
        {
            'success': True,
            'planejamento': _serialize_planejamento(planejamento),
            'os': _serialize_os(planejamento.ordem_servico),
        }
    )


@login_required(login_url='/login/')
@require_POST
def api_planejamento_update_cabecalho(request, planejamento_id):
    planejamento = get_object_or_404(_get_planejamento_with_relations_queryset(), pk=planejamento_id)
    block_reason = _get_planejamento_edit_block_reason(planejamento)
    if block_reason:
        return JsonResponse({'success': False, 'error': block_reason}, status=400)
    try:
        payload = _parse_json_body(request)
        justificativa = str(payload.get('justificativa') or '').strip()
        if _planejamento_requer_justificativa(planejamento) and not justificativa:
            raise ValidationError(_get_planejamento_justificativa_message())
        dados_anteriores = _snapshot_planejamento_cabecalho(planejamento)
        planejamento.titulo_planejamento = str(payload.get('titulo_planejamento') or '').strip()
        planejamento.data_prevista_subida = _parse_optional_date(payload.get('data_prevista_subida'), 'Data prevista de subida')
        planejamento.horario_previsto_subida = _parse_optional_time_text(payload.get('horario_previsto_subida'), 'HorÃ¡rio previsto de embarque')
        planejamento.local_subida = str(payload.get('local_subida') or '').strip()
        planejamento.observacao = payload.get('observacao') or ''
        planejamento.data_prevista_desembarque = _parse_optional_date(payload.get('data_prevista_desembarque'), 'Data prevista de desembarque')
        planejamento.horario_previsto_desembarque = _parse_optional_time_text(payload.get('horario_previsto_desembarque'), 'HorÃ¡rio previsto de desembarque')
        planejamento.local_desembarque = str(payload.get('local_desembarque') or '').strip()
        planejamento.observacao_desembarque = payload.get('observacao_desembarque') or ''
        planejamento.atualizado_por = request.user
        planejamento.save()
        if justificativa:
            _registrar_historico_planejamento(
                planejamento,
                PlanejamentoEquipeHistorico.ACAO_ALTERACAO_CABECALHO,
                justificativa,
                request.user,
                dados_anteriores=dados_anteriores,
                dados_novos=_snapshot_planejamento_cabecalho(planejamento),
            )
    except ValidationError as exc:
        return JsonResponse({'success': False, 'error': exc.message_dict if hasattr(exc, 'message_dict') else exc.messages[0]}, status=400)
    planejamento = _get_planejamento_with_relations_queryset().get(pk=planejamento.pk)
    return JsonResponse({'success': True, 'planejamento': _serialize_planejamento(planejamento), 'os': _serialize_os(planejamento.ordem_servico)})


@login_required(login_url='/login/')
@require_POST
def api_planejamento_add_membro(request, planejamento_id):
    planejamento = get_object_or_404(PlanejamentoEquipeOS.objects.select_related('ordem_servico'), pk=planejamento_id)
    block_reason = _get_planejamento_edit_block_reason(planejamento)
    if block_reason:
        return JsonResponse({'success': False, 'error': block_reason}, status=400)
    try:
        _, justificativa = _require_justificativa_if_needed(request, planejamento)
        primeira_alocacao = not planejamento.membros.exists()
        membro = _build_membro_from_request(request, planejamento)
        if primeira_alocacao:
            membro = _aplicar_agenda_inicial_do_planejamento(membro, planejamento)
        membro.criado_por = request.user
        membro.atualizado_por = request.user
        membro.save()
        if justificativa:
            _registrar_historico_planejamento(
                planejamento,
                PlanejamentoEquipeHistorico.ACAO_ADICAO_MEMBRO_POS_CONCLUSAO,
                justificativa,
                request.user,
                membro=membro,
                dados_anteriores=None,
                dados_novos=_snapshot_membro(membro),
            )
    except ValidationError as exc:
        return JsonResponse({'success': False, 'error': exc.message_dict if hasattr(exc, 'message_dict') else exc.messages[0]}, status=400)
    planejamento = _get_planejamento_with_relations_queryset().get(pk=planejamento.pk)
    return JsonResponse({'success': True, 'membro': _serialize_membro(membro), 'planejamento': _serialize_planejamento(planejamento), 'os': _serialize_os(planejamento.ordem_servico)})


@login_required(login_url='/login/')
@require_POST
def api_planejamento_update_membro(request, membro_id):
    membro = get_object_or_404(
        PlanejamentoEquipeMembro.objects.select_related('planejamento', 'planejamento__ordem_servico'),
        pk=membro_id,
    )
    block_reason = _get_planejamento_edit_block_reason(membro.planejamento)
    if block_reason:
        return JsonResponse({'success': False, 'error': block_reason}, status=400)
    if membro.status != PlanejamentoEquipeMembro.STATUS_ATIVO:
        return JsonResponse({'success': False, 'error': 'Membros substituídos ou cancelados não podem ser sobrescritos.'}, status=400)
    try:
        _, justificativa = _require_justificativa_if_needed(request, membro.planejamento)
        dados_anteriores = _snapshot_membro(membro)
        membro = _build_membro_from_request(request, membro.planejamento, instance=membro, allow_status_edit=True)
        membro.atualizado_por = request.user
        membro.save()
        if justificativa:
            _registrar_historico_planejamento(
                membro.planejamento,
                PlanejamentoEquipeHistorico.ACAO_EDICAO_MEMBRO_POS_CONCLUSAO,
                justificativa,
                request.user,
                membro=membro,
                dados_anteriores=dados_anteriores,
                dados_novos=_snapshot_membro(membro),
            )
    except ValidationError as exc:
        return JsonResponse({'success': False, 'error': exc.message_dict if hasattr(exc, 'message_dict') else exc.messages[0]}, status=400)
    planejamento = _get_planejamento_with_relations_queryset().get(pk=membro.planejamento_id)
    return JsonResponse({'success': True, 'membro': _serialize_membro(membro), 'planejamento': _serialize_planejamento(planejamento), 'os': _serialize_os(planejamento.ordem_servico)})


@login_required(login_url='/login/')
@require_POST
def api_planejamento_substituir_membro(request, membro_id):
    membro_antigo = get_object_or_404(
        PlanejamentoEquipeMembro.objects.select_related('planejamento', 'planejamento__ordem_servico'),
        pk=membro_id,
    )
    planejamento = membro_antigo.planejamento
    block_reason = _get_planejamento_edit_block_reason(planejamento)
    if block_reason:
        return JsonResponse({'success': False, 'error': block_reason}, status=400)
    if membro_antigo.status in (PlanejamentoEquipeMembro.STATUS_SUBSTITUIDO, PlanejamentoEquipeMembro.STATUS_CANCELADO):
        return JsonResponse({'success': False, 'error': 'Este membro não pode mais ser substituído.'}, status=400)
    try:
        _, justificativa = _require_justificativa_if_needed(request, planejamento)
        dados_anteriores = _snapshot_membro(membro_antigo)
        with transaction.atomic():
            membro_antigo.status = PlanejamentoEquipeMembro.STATUS_SUBSTITUIDO
            membro_antigo.data_fim = _parse_optional_date(request.POST.get('data_fim'), 'Data de fim') if request.POST.get('data_fim') else membro_antigo.data_fim
            membro_antigo.data_desembarque = _parse_optional_date(request.POST.get('data_desembarque_antigo'), 'Data de desembarque do membro substituído') if request.POST.get('data_desembarque_antigo') else membro_antigo.data_desembarque
            membro_antigo.horario_desembarque = _parse_optional_time_text(request.POST.get('horario_desembarque_antigo'), 'Horário de desembarque do membro substituído') or membro_antigo.horario_desembarque
            if 'local_desembarque_membro_antigo' in request.POST:
                membro_antigo.local_desembarque_membro = str(request.POST.get('local_desembarque_membro_antigo') or '').strip()
            if 'observacao_desembarque_antigo' in request.POST:
                membro_antigo.observacao_desembarque = request.POST.get('observacao_desembarque_antigo') or ''
            membro_antigo.motivo_substituicao = request.POST.get('motivo_substituicao')
            membro_antigo.atualizado_por = request.user
            membro_antigo.save()

            membro_novo = _build_membro_from_request(request, planejamento)
            membro_novo.status = PlanejamentoEquipeMembro.STATUS_ATIVO
            membro_novo.substitui = membro_antigo
            membro_novo.motivo_substituicao = request.POST.get('motivo_substituicao')
            membro_novo.ordem = membro_antigo.ordem
            membro_novo.criado_por = request.user
            membro_novo.atualizado_por = request.user
            membro_novo.save()
            if justificativa:
                _registrar_historico_planejamento(
                    planejamento,
                    PlanejamentoEquipeHistorico.ACAO_SUBSTITUICAO_MEMBRO_POS_CONCLUSAO,
                    justificativa,
                    request.user,
                    membro=membro_novo,
                    dados_anteriores=dados_anteriores,
                    dados_novos={
                        'membro_antigo': _snapshot_membro(membro_antigo),
                        'membro_novo': _snapshot_membro(membro_novo),
                    },
                )
        membro_antigo.refresh_from_db()
        membro_novo.refresh_from_db()
    except ValidationError as exc:
        return JsonResponse({'success': False, 'error': exc.message_dict if hasattr(exc, 'message_dict') else exc.messages[0]}, status=400)
    planejamento = _get_planejamento_with_relations_queryset().get(pk=planejamento.pk)
    return JsonResponse(
        {
            'success': True,
            'membro_antigo': _serialize_membro(membro_antigo),
            'membro_novo': _serialize_membro(membro_novo),
            'planejamento': _serialize_planejamento(planejamento),
            'os': _serialize_os(planejamento.ordem_servico),
        }
    )


@login_required(login_url='/login/')
@require_POST
def api_planejamento_cancelar_membro(request, membro_id):
    membro = get_object_or_404(
        PlanejamentoEquipeMembro.objects.select_related('planejamento', 'planejamento__ordem_servico'),
        pk=membro_id,
    )
    block_reason = _get_planejamento_edit_block_reason(membro.planejamento)
    if block_reason:
        return JsonResponse({'success': False, 'error': block_reason}, status=400)
    justificativa = ''
    dados_anteriores = _snapshot_membro(membro)
    try:
        _, justificativa = _require_justificativa_if_needed(request, membro.planejamento)
    except ValidationError as exc:
        return JsonResponse({'success': False, 'error': exc.message_dict if hasattr(exc, 'message_dict') else exc.messages[0]}, status=400)
    membro.status = PlanejamentoEquipeMembro.STATUS_CANCELADO
    membro.data_fim = _parse_optional_date(request.POST.get('data_fim'), 'Data de fim') if request.POST.get('data_fim') else membro.data_fim
    membro.data_desembarque = _parse_optional_date(request.POST.get('data_desembarque'), 'Data de desembarque') if request.POST.get('data_desembarque') else membro.data_desembarque
    horario_desembarque = _parse_optional_time_text(request.POST.get('horario_desembarque'), 'Horário de desembarque')
    if horario_desembarque:
        membro.horario_desembarque = horario_desembarque
    if 'local_desembarque_membro' in request.POST:
        membro.local_desembarque_membro = str(request.POST.get('local_desembarque_membro') or '').strip()
    if 'observacao_desembarque' in request.POST:
        membro.observacao_desembarque = request.POST.get('observacao_desembarque') or ''
    if 'observacao' in request.POST:
        membro.observacao = request.POST.get('observacao')
    if 'motivo_substituicao' in request.POST:
        membro.motivo_substituicao = request.POST.get('motivo_substituicao')
    membro.atualizado_por = request.user
    try:
        membro.save()
        if justificativa:
            _registrar_historico_planejamento(
                membro.planejamento,
                PlanejamentoEquipeHistorico.ACAO_CANCELAMENTO_MEMBRO_POS_CONCLUSAO,
                justificativa,
                request.user,
                membro=membro,
                dados_anteriores=dados_anteriores,
                dados_novos=_snapshot_membro(membro),
            )
    except ValidationError as exc:
        return JsonResponse({'success': False, 'error': exc.message_dict if hasattr(exc, 'message_dict') else exc.messages[0]}, status=400)
    planejamento = _get_planejamento_with_relations_queryset().get(pk=membro.planejamento_id)
    return JsonResponse({'success': True, 'membro': _serialize_membro(membro), 'planejamento': _serialize_planejamento(planejamento), 'os': _serialize_os(planejamento.ordem_servico)})


@login_required(login_url='/login/')
@require_POST
def api_planejamento_concluir(request, planejamento_id):
    planejamento = get_object_or_404(PlanejamentoEquipeOS.objects.select_related('ordem_servico'), pk=planejamento_id)
    block_reason = _get_planejamento_edit_block_reason(planejamento)
    if block_reason:
        return JsonResponse({'success': False, 'error': block_reason}, status=400)
    if planejamento.status == PlanejamentoEquipeOS.STATUS_CONCLUIDO:
        return JsonResponse({'success': False, 'error': 'Este planejamento já está concluído.'}, status=400)
    if not planejamento.membros.filter(status=PlanejamentoEquipeMembro.STATUS_ATIVO).exists():
        return JsonResponse({'success': False, 'error': 'É necessário ao menos um membro ativo para concluir.'}, status=400)
    planejamento.status = PlanejamentoEquipeOS.STATUS_CONCLUIDO
    planejamento.atualizado_por = request.user
    planejamento.save()
    _recalcular_status_planejamento_os(planejamento.ordem_servico)
    planejamento = _get_planejamento_with_relations_queryset().get(pk=planejamento.pk)
    return JsonResponse({'success': True, 'planejamento': _serialize_planejamento(planejamento), 'os': _serialize_os(planejamento.ordem_servico)})


@login_required(login_url='/login/')
@require_POST
def api_planejamento_cancelar(request, planejamento_id):
    planejamento = get_object_or_404(PlanejamentoEquipeOS.objects.select_related('ordem_servico'), pk=planejamento_id)
    if _ordem_servico_bloqueada(planejamento.ordem_servico):
        return JsonResponse({'success': False, 'error': 'A operação desta OS está finalizada e o planejamento está somente leitura.'}, status=400)
    planejamento.status = PlanejamentoEquipeOS.STATUS_CANCELADO
    planejamento.atualizado_por = request.user
    planejamento.save()
    _recalcular_status_planejamento_os(planejamento.ordem_servico)
    planejamento = _get_planejamento_with_relations_queryset().get(pk=planejamento.pk)
    return JsonResponse({'success': True, 'planejamento': _serialize_planejamento(planejamento), 'os': _serialize_os(planejamento.ordem_servico)})


@login_required(login_url='/login/')
@require_GET
def planejamento_documento(request, planejamento_id):
    planejamento = get_object_or_404(_get_planejamento_with_relations_queryset(), pk=planejamento_id)
    context = {
        'planejamento': planejamento,
        'ordem_servico': planejamento.ordem_servico,
        'membros_ativos': planejamento.membros.filter(status=PlanejamentoEquipeMembro.STATUS_ATIVO).order_by('ordem', 'id'),
        'membros_substituidos': planejamento.membros.filter(status=PlanejamentoEquipeMembro.STATUS_SUBSTITUIDO).order_by('ordem', 'id'),
        'membros_cancelados': planejamento.membros.filter(status=PlanejamentoEquipeMembro.STATUS_CANCELADO).order_by('ordem', 'id'),
        'historicos': planejamento.historicos.select_related('membro', 'criado_por').order_by('-criado_em', '-id'),
        'generated_at': timezone.localtime(timezone.now()),
        'generated_by': _get_user_display_name(request.user),
    }
    return render(request, 'planejamento_documento.html', context)
