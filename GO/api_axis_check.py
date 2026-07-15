import json
import os
import unicodedata

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import Equipamentos, OrdemServico, RdoEquipamentoRetornoPrevisto


def _texto(valor):
    if valor is None:
        return ''
    return str(valor).strip()


def _modelo_equipamento(equipamento):
    modelo = getattr(equipamento, 'modelo_fk', None) or getattr(
        equipamento,
        'modelo',
        None,
    )
    return _texto(modelo)


def _situacao_equipamento(equipamento):
    try:
        display = equipamento.get_situacao_display()
        if display:
            return display
    except Exception:
        pass
    return _texto(getattr(equipamento, 'situacao', None))


def _normalizar_texto(valor):
    texto = unicodedata.normalize('NFKD', _texto(valor))
    texto = ''.join(char for char in texto if not unicodedata.combining(char))
    return texto.lower()


def _equipamento_ja_retornou_base(equipamento):
    situacao = _normalizar_texto(_situacao_equipamento(equipamento))
    return 'retornou' in situacao and 'base' in situacao


def _equipamentos_da_os(os_obj):
    numero_os = _texto(getattr(os_obj, 'numero_os', None))
    if not numero_os:
        return Equipamentos.objects.none()

    return Equipamentos.objects.filter(numero_os=numero_os).order_by('id')


def _equipamentos_previstos_retorno_ids(os_obj):
    try:
        qs = (
            RdoEquipamentoRetornoPrevisto.objects.filter(
                os=os_obj,
                previsto_retorno=True,
            )
            .values_list('equipamento_id', flat=True)
            .distinct()
        )
        return {int(equipamento_id) for equipamento_id in qs if equipamento_id}
    except Exception:
        return set()


def _descricao_operacao(os_obj):
    return (
        _texto(getattr(os_obj, 'servicos', None))
        or _texto(getattr(os_obj, 'servico', None))
        or _texto(getattr(os_obj, 'especificacao', None))
        or _texto(getattr(os_obj, 'observacao', None))
    )


def _unidade_os(os_obj):
    return _texto(getattr(os_obj, 'unidade', None))


def _montar_payload_os(os_obj):
    equipamentos_payload = []
    equipamentos_previstos_ids = _equipamentos_previstos_retorno_ids(os_obj)

    for equipamento in _equipamentos_da_os(os_obj):
        if _equipamento_ja_retornou_base(equipamento):
            continue

        equipamentos_payload.append(
            {
                'equipamentoIdSynchro': str(equipamento.id),
                'tipoEquipamento': _texto(getattr(equipamento, 'descricao', None)),
                'modelo': _modelo_equipamento(equipamento),
                'numeroSerie': _texto(getattr(equipamento, 'numero_serie', None)),
                'tag': _texto(getattr(equipamento, 'numero_tag', None)),
                'situacaoAtual': _situacao_equipamento(equipamento),
                'previstoRetorno': getattr(equipamento, 'id', None)
                in equipamentos_previstos_ids,
            }
        )

    return {
        'osId': str(os_obj.id),
        'numeroOs': _texto(getattr(os_obj, 'numero_os', None)) or str(os_obj.id),
        'cliente': _texto(getattr(os_obj, 'cliente', None)),
        'unidade': _unidade_os(os_obj),
        'descricaoOperacao': _descricao_operacao(os_obj),
        'status': _texto(getattr(os_obj, 'status_operacao', None)) or 'Em Andamento',
        'equipamentos': equipamentos_payload,
    }


@require_GET
def os_em_andamento(request):
    os_list = (
        OrdemServico.objects.filter(
            status_operacao__in=['Em Andamento', 'Finalizada'],
        )
        .exclude(numero_os=3011)
        .select_related('Cliente')
        .order_by('-data_inicio', '-numero_os', '-id')
    )

    payload = []

    for os_obj in os_list:
        os_payload = _montar_payload_os(os_obj)
        if not os_payload['equipamentos']:
            continue
        payload.append(os_payload)

    return JsonResponse(payload, safe=False)


@require_GET
def detalhe_os_equipamentos(request, os_id):
    try:
        os_obj = OrdemServico.objects.select_related('Cliente').get(id=os_id)
    except OrdemServico.DoesNotExist:
        return JsonResponse(
            {'detail': 'OS não encontrada.'},
            status=404,
        )

    return JsonResponse(_montar_payload_os(os_obj), safe=False)


def _validar_token_axis_check(request):
    token_configurado = os.getenv('AXIS_CHECK_TOKEN')

    if not token_configurado:
        return False

    auth_header = request.headers.get('Authorization', '')

    return auth_header == f'Bearer {token_configurado}'


@csrf_exempt
@require_POST
def retorno_base_axis_check(request):
    if not _validar_token_axis_check(request):
        return JsonResponse(
            {'detail': 'Token inválido.'},
            status=401,
        )

    try:
        dados = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse(
            {'detail': 'JSON inválido.'},
            status=400,
        )

    equipamentos = dados.get('equipamentos', [])

    if not equipamentos:
        return JsonResponse(
            {'detail': 'Nenhum equipamento enviado.'},
            status=400,
        )

    atualizados = 0
    nao_encontrados = []

    for item in equipamentos:
        equipamento_id = item.get('equipamentoId')
        tag = item.get('tag')
        numero_serie = item.get('numeroSerie')

        equipamento = None

        if equipamento_id and str(equipamento_id).isdigit():
            equipamento = Equipamentos.objects.filter(id=equipamento_id).first()

        if not equipamento and tag:
            equipamento = Equipamentos.objects.filter(numero_tag__iexact=tag).first()

        if not equipamento and numero_serie:
            equipamento = Equipamentos.objects.filter(
                numero_serie__iexact=numero_serie,
            ).first()

        if not equipamento:
            nao_encontrados.append(
                {
                    'equipamentoId': equipamento_id,
                    'tag': tag,
                    'numeroSerie': numero_serie,
                }
            )
            continue

        equipamento.situacao = 'retornou_base'
        equipamento.save(update_fields=['situacao'])

        atualizados += 1

    return JsonResponse(
        {
            'mensagem': 'Retorno processado.',
            'atualizados': atualizados,
            'naoEncontrados': nao_encontrados,
        }
    )
