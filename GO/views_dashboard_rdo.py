from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.utils.dateparse import parse_date
from django.db.models import Sum, Count, Q, Max, Avg
from django.db.models.functions import Coalesce
from django.db.models import DecimalField
import datetime
import traceback
import logging

from .models import RDO, RdoTanque, OrdemServico


@require_GET
def get_ordens_servico(request):
    """
    Retorna lista de Ordens de Serviço abertas em formato JSON para popular o select
    """
    try:
        ordens = OrdemServico.objects.filter(status_operacao='Programada').values('id', 'numero_os').order_by('-numero_os')
        items = [{'id': os['id'], 'numero_os': os['numero_os']} for os in ordens]
        return JsonResponse({'success': True, 'items': items})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


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
    ordem_servico = request.GET.get('ordem_servico')


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

        # Adicionando lógica para capturar o filtro de OS selecionada
        os_selecionada = request.GET.get('os_existente')
        if os_selecionada:
            qs = qs.filter(ordem_servico_id=os_selecionada)

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


@require_GET
def pob_comparativo(request):
    """
    Retorna média diária de POB alocado na atividade vs POB em espaço confinado
    dentro do intervalo solicitado. Payload compatível com Chart.js:
    { labels: [...], datasets: [{label, data: [...]}, ...] }

    Detecta automaticamente campos plausíveis no modelo `RDO` para POB.
    """
    start = request.GET.get('start')
    end = request.GET.get('end')

    try:
        start_date = parse_date(start) if start else None
        end_date = parse_date(end) if end else None
    except Exception:
        start_date = None
        end_date = None

    if not end_date:
        end_date = datetime.date.today()
    if not start_date:
        # default para o mês corrente (do primeiro ao último dia)
        start_date = end_date.replace(day=1)

    try:
        # Detectar campo de data no modelo RDO (DateField/DateTimeField)
        date_field = None
        date_field_type = None
        for f in RDO._meta.fields:
            t = f.get_internal_type()
            if t in ('DateField', 'DateTimeField') and 'data' in f.name:
                date_field = f.name
                date_field_type = t
                break
        if not date_field:
            # fallback: primeiro DateField/DateTimeField disponível
            for f in RDO._meta.fields:
                t = f.get_internal_type()
                if t in ('DateField', 'DateTimeField'):
                    date_field = f.name
                    date_field_type = t
                    break

        if not date_field:
            return JsonResponse({'success': False, 'error': 'Modelo RDO sem campo de data detectável.'}, status=400)

        # Neste projeto: POB alocado vem de OrdemServico.pob (form em home.html)
        # e POB em espaço confinado corresponde a RDO.operadores_simultaneos.
        # Podemos filtrar por `unidade` (nome da embarcação/unidade) para comparar
        # apenas RDOs daquela unidade/embarcação.
        unidade = request.GET.get('unidade')
        group_by = request.GET.get('group', 'day')  # 'day' or 'month'

        # Preparar arrays de saída
        labels = []
        data_alocado = []
        data_confinado = []
        data_count_rdo = []
        data_count_os = []

        if group_by == 'month':
            # construir lista de meses entre start_date e end_date
            cur = start_date.replace(day=1)
            while cur <= end_date:
                year = cur.year
                month = cur.month
                # primeiro dia do mês
                month_start = cur
                # último dia do mês: avançar para próximo mês e subtrair 1 dia
                if month == 12:
                    next_month = cur.replace(year=year+1, month=1, day=1)
                else:
                    next_month = cur.replace(month=month+1, day=1)
                month_end = next_month - datetime.timedelta(days=1)

                labels.append(cur.strftime('%m/%Y'))

                # filtros por mês (usar range para compatibilidade DateField/DateTimeField)
                if date_field_type == 'DateField':
                    filters = {f"{date_field}__gte": month_start, f"{date_field}__lte": month_end}
                else:
                    filters = {f"{date_field}__date__gte": month_start, f"{date_field}__date__lte": month_end}

                month_qs = RDO.objects.filter(**filters)
                if unidade:
                    month_qs = month_qs.filter(ordem_servico__unidade__icontains=unidade)

                agg_alocado = month_qs.aggregate(v=Coalesce(Avg('ordem_servico__pob'), 0, output_field=DecimalField()))
                agg_confinado = month_qs.aggregate(v=Coalesce(Avg('operadores_simultaneos'), 0, output_field=DecimalField()))
                # POB é inteiro — arredondar para inteiro mais próximo
                try:
                    val_a = int(round(float(agg_alocado.get('v') or 0)))
                except Exception:
                    val_a = int(float(agg_alocado.get('v') or 0) or 0)
                try:
                    val_c = int(round(float(agg_confinado.get('v') or 0)))
                except Exception:
                    val_c = int(float(agg_confinado.get('v') or 0) or 0)
                data_alocado.append(val_a)
                data_confinado.append(val_c)
                data_count_rdo.append(month_qs.count())
                try:
                    data_count_os.append(month_qs.values('ordem_servico').distinct().count())
                except Exception:
                    data_count_os.append(0)

                # avançar para próximo mês
                cur = next_month
        else:
            delta = end_date - start_date
            for i in range(delta.days + 1):
                day = start_date + datetime.timedelta(days=i)
                labels.append(day.strftime('%d/%m'))

                # lookup compatível: DateField -> exact, DateTimeField -> __date
                if date_field_type == 'DateField':
                    filters = {f"{date_field}__gte": day, f"{date_field}__lte": day}
                else:
                    filters = {f"{date_field}__date__gte": day, f"{date_field}__date__lte": day}

                day_qs = RDO.objects.filter(**filters)
                if unidade:
                    day_qs = day_qs.filter(ordem_servico__unidade__icontains=unidade)

                agg_alocado = day_qs.aggregate(v=Coalesce(Avg('ordem_servico__pob'), 0, output_field=DecimalField()))
                agg_confinado = day_qs.aggregate(v=Coalesce(Avg('operadores_simultaneos'), 0, output_field=DecimalField()))
                # POB é inteiro — arredondar para inteiro mais próximo
                try:
                    val_a = int(round(float(agg_alocado.get('v') or 0)))
                except Exception:
                    val_a = int(float(agg_alocado.get('v') or 0) or 0)
                try:
                    val_c = int(round(float(agg_confinado.get('v') or 0)))
                except Exception:
                    val_c = int(float(agg_confinado.get('v') or 0) or 0)
                data_alocado.append(val_a)
                data_confinado.append(val_c)
                data_count_rdo.append(day_qs.count())
                try:
                    data_count_os.append(day_qs.values('ordem_servico').distinct().count())
                except Exception:
                    data_count_os.append(0)

        # calcular razão percentual (POB confinado / POB alocado) * 100
        data_ratio = []
        for a, c in zip(data_alocado, data_confinado):
            try:
                a_val = float(a or 0)
                c_val = float(c or 0)
                if a_val > 0:
                    # armazenar percentual como inteiro (aproximação)
                    data_ratio.append(int(round((c_val / a_val) * 100.0)))
                else:
                    data_ratio.append(0)
            except Exception:
                data_ratio.append(0)

        chart = {
            'labels': labels,
            'datasets': [
                {'label': 'POB Alocado (média/dia)', 'data': data_alocado},
                {'label': 'POB em Espaço Confinado (média/dia)', 'data': data_confinado}
            ]
        }

        meta = {
            'fields': ['ordem_servico__pob', 'operadores_simultaneos'],
            'counts': {'rdos_per_day': data_count_rdo, 'distinct_os_per_day': data_count_os},
            'filtered_unidade': unidade or None,
            'group_by': group_by,
            'ratio_percent': data_ratio,
        }

        return JsonResponse({'success': True, 'chart': chart, 'meta': meta})

    except Exception as e:
        logging.exception('Erro em pob_comparativo')
        tb = traceback.format_exc()
        return JsonResponse({'success': False, 'error': str(e), 'traceback': tb}, status=500)
