from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.utils.dateparse import parse_date
from django.db.models import Sum, Count, Q, Max
from django.db.models.functions import Coalesce
from django.db.models import DecimalField
import datetime
import traceback
import logging

from .models import RDO, RdoTanque


@require_GET
def top_supervisores(request):
    """
    Retorna o ranking de supervisores agregando volumes reais a partir dos RDOs.

    Parâmetros (GET): start, end, supervisor, cliente, unidade, tanque

    Métrica (atual): soma das colunas relevantes do RDO que representam
    volume/quantidade (ex.: bombeio, quantidade_bombeada, volume_tanque_exec,
    total_liquido, total_solidos). A unidade resulta da soma das colunas do
    banco e será apresentada como "M³ equivalente removido" no front-end.
    """

    # Ler parâmetros
    start = request.GET.get('start')
    end = request.GET.get('end')
    supervisor_filter = request.GET.get('supervisor')
    cliente = request.GET.get('cliente')
    unidade = request.GET.get('unidade')
    tanque = request.GET.get('tanque')

    # Parse de datas com fallback para últimos 30 dias
    try:
        start_date = parse_date(start) if start else None
        end_date = parse_date(end) if end else None
    except Exception:
        start_date = None
        end_date = None

    if not end_date:
        end_date = datetime.date.today()
    if not start_date:
        start_date = end_date - datetime.timedelta(days=30)

    try:
        # Top Supervisores é um ranking global — NÃO aplicar filtros do front-end.
        # Usar todo o histórico disponível para criar o ranking (pode ser pesado
        # dependendo do volume de dados; otimizações podem ser adicionadas se necessário).
        qs = RDO.objects.select_related('ordem_servico__supervisor').all()

        # Antes de agregar por supervisor, calcular a capacidade total
        # única por `tanque_codigo` agregada por supervisor. A regra é:
        # para cada supervisor, considerar cada `tanque_codigo` apenas uma vez
        # (capacidade única por tanque) — evitar duplicação quando o mesmo
        # tanque aparece em múltiplos RDOs.
        # Construímos um sub-agrupamento em RdoTanque: (supervisor_id, tanque_codigo) -> cap
        tanque_qs = RdoTanque.objects.filter(rdo__in=qs).values(
            'rdo__ordem_servico__supervisor__id',
            'tanque_codigo'
        ).annotate(
            cap=Coalesce(Max('volume_tanque_exec'), 0, output_field=DecimalField())
        )

        # Somar capacidades únicas por supervisor
        capacities = {}
        for t in tanque_qs:
            sup_id = t.get('rdo__ordem_servico__supervisor__id')
            if not sup_id:
                continue
            cap = float(t.get('cap') or 0)
            capacities[sup_id] = capacities.get(sup_id, 0.0) + cap

        # Agrupar por supervisor e agregar somas relevantes
        agg_qs = qs.values(
            'ordem_servico__supervisor__id',
            'ordem_servico__supervisor__username',
            'ordem_servico__supervisor__first_name',
            'ordem_servico__supervisor__last_name'
        ).annotate(
            rd_count=Count('id'),
            sum_bombeio=Coalesce(Sum('bombeio'), 0, output_field=DecimalField()),
            sum_quantidade_bombeada=Coalesce(Sum('quantidade_bombeada'), 0, output_field=DecimalField()),
            sum_volume_tanque_exec=Coalesce(Sum('volume_tanque_exec'), 0, output_field=DecimalField()),
            sum_total_liquido=Coalesce(Sum('total_liquido'), 0, output_field=DecimalField()),
            sum_total_solidos=Coalesce(Sum('total_solidos'), 0, output_field=DecimalField()),
            # Capacidades devem vir da classe RdoTanque (relação 'tanques')
            sum_capacidade=Coalesce(Sum('tanques__volume_tanque_exec'), 0, output_field=DecimalField()),
        )

        items = []
        for row in agg_qs:
            sup_id = row.get('ordem_servico__supervisor__id')
            if not sup_id:
                # ignorar RDOs sem supervisor atribuído
                continue
            username = row.get('ordem_servico__supervisor__username') or ''
            fname = row.get('ordem_servico__supervisor__first_name') or ''
            lname = row.get('ordem_servico__supervisor__last_name') or ''
            name = ((fname + ' ' + lname).strip()) or username or f'ID {sup_id}'

            # Métrica composta bruta (m³ equivalente)
            raw_total = (
                float(row.get('sum_bombeio') or 0)
                + float(row.get('sum_quantidade_bombeada') or 0)
                + float(row.get('sum_volume_tanque_exec') or 0)
                + float(row.get('sum_total_liquido') or 0)
                + float(row.get('sum_total_solidos') or 0)
            )
            capacidade_total = float(row.get('sum_capacidade') or 0)
            # Normalização por capacidade: índice percentual
            if capacidade_total > 0:
                value = (raw_total / capacidade_total) * 100.0
            else:
                value = raw_total

            items.append({
                'supervisor_id': sup_id,
                'username': username,
                'name': name,
                'value': round(value, 2),
                'value_raw': round(raw_total, 2),
                'capacity_total': round(capacidade_total, 2),
                'rd_count': row.get('rd_count', 0),
            })

        # Ordenar decrescente e limitar (top 20 por padrão)
        items.sort(key=lambda x: x['value'], reverse=True)
        top_items = items[:20]

        # Preparar payload compatível com frontend
        labels = [it['name'] for it in top_items]
        data_values = [it['value'] for it in top_items]

        chart = {
            'labels': labels,
            'datasets': [
                {
                    'label': 'Índice normalizado (%)',
                    'data': data_values,
                }
            ]
        }

        return JsonResponse({'success': True, 'items': top_items, 'chart': chart})
    except Exception as e:
        logging.exception('Erro em top_supervisores')
        tb = traceback.format_exc()
        return JsonResponse({'success': False, 'error': str(e), 'traceback': tb}, status=500)
