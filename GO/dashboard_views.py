from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from django.http import JsonResponse
from django.db.models import Count, Avg, Q, Min, Max
from django.db.models.functions import TruncDate
from django.shortcuts import render
from datetime import datetime, timedelta
from django.conf import settings

from .models import OrdemServico
from django.core.cache import cache
import unicodedata
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
import logging
from .views_dashboard_rdo import summary_operations_data

# Helpers para aceitar múltiplos valores em `os_existente` (CSV com ',' ou ';')
def _parse_os_tokens(raw):
    import re
    if not raw:
        return ([], [])
    parts = [p.strip() for p in re.split(r'[;,]+', str(raw)) if p and p.strip()]
    ids = []
    others = []
    for p in parts:
        if p.isdigit():
            try:
                ids.append(int(p))
            except Exception:
                others.append(p)
        else:
            others.append(p)
    return (ids, others)

def apply_os_filter_generic(qs, raw):
    """Aplica filtro de ordem de serviço aceitando múltiplos IDs ou números de OS.
    Funciona tanto para QuerySets de RDO (usa ordem_servico_id/ordem_servico__numero_os)
    quanto para QuerySets de OrdemServico (usa id/numero_os).
    """
    ids, others = _parse_os_tokens(raw)
    if not ids and not others:
        return qs
    from django.db.models import Q
    q = None
    # detectar se queryset é RDO (possui fk `ordem_servico`) ou OrdemServico
    model = getattr(qs, 'model', None)
    is_rdo = False
    try:
        if model is not None and hasattr(model, 'ordem_servico'):
            is_rdo = True
    except Exception:
        is_rdo = False

    if ids:
        # tentar corresponder tanto por FK `ordem_servico_id`/`id` quanto por `numero_os`
        try:
            num_q = Q(ordem_servico__numero_os__in=[str(x) for x in ids]) if is_rdo else Q(numero_os__in=[str(x) for x in ids])
        except Exception:
            num_q = Q()
        if is_rdo:
            q = Q(ordem_servico_id__in=ids) | num_q
        else:
            q = Q(id__in=ids) | num_q

    if others:
        q2 = None
        for token in others:
            if is_rdo:
                part = Q(ordem_servico__numero_os__iexact=token) | Q(ordem_servico__numero_os__icontains=token)
            else:
                part = Q(numero_os__iexact=token) | Q(numero_os__icontains=token)
            if q2 is None:
                q2 = part
            else:
                q2 |= part
        if q is None:
            q = q2
        else:
            q |= q2

    if q is not None:
        try:
            return qs.filter(q)
        except Exception:
            return qs
    return qs


def _dashboard_rdo_period(request):
    end_str = request.GET.get('end')
    start_str = request.GET.get('start')
    if end_str:
        end = datetime.strptime(end_str, '%Y-%m-%d').date()
    else:
        end = datetime.today().date()
    if start_str:
        start = datetime.strptime(start_str, '%Y-%m-%d').date()
    else:
        start = end - timedelta(days=29)
    return start, end


def _split_csv_tokens(raw):
    import re
    if not raw:
        return []
    parts = [p.strip() for p in re.split(r'[;,]+', str(raw)) if p and p.strip()]
    return parts


_DASHBOARD_RDO_COORDENADORES_EXCLUIDOS = {
    'gabriel delaia',
    'andre santiago',
    'marcos delgado',
    'ailton oliveira',
    'c-safety/locacao',
}


def _normalize_dashboard_coord_name(value):
    text = unicodedata.normalize('NFKD', str(value or '').strip())
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return ' '.join(text.casefold().split())


def _dashboard_coord_is_excluded(value):
    return _normalize_dashboard_coord_name(value) in _DASHBOARD_RDO_COORDENADORES_EXCLUIDOS


def _apply_dashboard_os_common_filters(qs, request):
    cliente = request.GET.get('cliente')
    unidade = request.GET.get('unidade')
    supervisor = request.GET.get('supervisor')
    coordenador = request.GET.get('coordenador')
    os_existente = request.GET.get('os_existente')

    if cliente:
        tokens = _split_csv_tokens(cliente)
        if tokens:
            q = Q()
            for tok in tokens:
                q |= Q(Cliente__nome__icontains=tok)
            qs = qs.filter(q)

    if unidade:
        tokens = _split_csv_tokens(unidade)
        if tokens:
            q = Q()
            for tok in tokens:
                q |= Q(Unidade__nome__icontains=tok)
            qs = qs.filter(q)

    if supervisor:
        tokens = _split_csv_tokens(supervisor)
        if tokens:
            q = Q()
            for tok in tokens:
                q |= (
                    Q(supervisor__username__icontains=tok) |
                    Q(supervisor__first_name__icontains=tok) |
                    Q(supervisor__last_name__icontains=tok)
                )
            qs = qs.filter(q)

    if coordenador:
        tokens = _split_csv_tokens(coordenador)
        if tokens:
            q = Q()
            for tok in tokens:
                q |= Q(coordenador__icontains=tok)
            qs = qs.filter(q)

    if os_existente:
        qs = apply_os_filter_generic(qs, os_existente)

    return qs


def _dashboard_filtered_rdo_qs(request):
    from .models import RDO

    start, end = _dashboard_rdo_period(request)
    supervisor = request.GET.get('supervisor')
    tanque = request.GET.get('tanque')
    cliente = request.GET.get('cliente')
    unidade = request.GET.get('unidade')
    os_existente = request.GET.get('os_existente')

    qs = RDO.objects.filter(data__gte=start, data__lte=end)
    if supervisor:
        qs = qs.filter(ordem_servico__supervisor__username=supervisor)
    if tanque:
        qs = qs.filter(
            Q(nome_tanque__icontains=tanque) |
            Q(tanque_codigo__icontains=tanque) |
            Q(tanques__tanque_codigo__icontains=tanque)
        ).distinct()
    if cliente:
        qs = qs.filter(ordem_servico__Cliente__nome__icontains=cliente)
    if unidade:
        qs = qs.filter(ordem_servico__Unidade__nome__icontains=unidade)
    if os_existente:
        qs = apply_os_filter_generic(qs, os_existente)
    return qs, start, end


def _dashboard_latest_rdo_per_os_day(qs):
    """
    Em várias bases existem múltiplos RDOs para a mesma OS no mesmo dia.
    Para evitar inflar KPIs, mantém apenas o registro mais recente (maior id)
    por par (ordem_servico, data).
    """
    try:
        latest_ids = list(
            qs.values('ordem_servico_id', 'data')
              .annotate(max_id=Max('id'))
              .values_list('max_id', flat=True)
        )
        if not latest_ids:
            return qs.none()
        return qs.model.objects.filter(id__in=latest_ids)
    except Exception:
        return qs


@login_required(login_url='/login/')
@require_GET
def rdo_kpis_totais(request):
    try:
        from .models import RdoTanque

        qs_raw, start, end = _dashboard_filtered_rdo_qs(request)
        qs = qs_raw.select_related('ordem_servico').order_by('data', 'id')
        rdo_rows = list(qs)
        raw_count = len(rdo_rows)
        dedup_count = qs.values('ordem_servico_id', 'data').distinct().count()

        def _to_int_safe(v):
            try:
                return int(v or 0)
            except Exception:
                try:
                    return int(float(v or 0))
                except Exception:
                    return 0

        def _to_float_safe(v):
            try:
                return float(v or 0)
            except Exception:
                return 0.0

        def _normalize_volume(v):
            f = _to_float_safe(v)
            if abs(f) > 100:
                try:
                    return f / 1000.0
                except Exception:
                    return f
            return f

        def _hh_confinado_h(rdo):
            total_minutos = 0.0
            for i in range(1, 7):
                entrada = getattr(rdo, f'entrada_confinado_{i}', None)
                saida = getattr(rdo, f'saida_confinado_{i}', None)
                if not entrada or not saida:
                    continue
                entrada_min = float(entrada.hour * 60 + entrada.minute) + float(getattr(entrada, 'second', 0)) / 60.0
                saida_min = float(saida.hour * 60 + saida.minute) + float(getattr(saida, 'second', 0)) / 60.0
                if saida_min >= entrada_min:
                    total_minutos += (saida_min - entrada_min)
                else:
                    total_minutos += ((24.0 * 60.0 - entrada_min) + saida_min)
            return total_minutos / 60.0

        def _hh_fora_h(rdo, presence_hours):
            efetivas_min = getattr(rdo, 'total_atividades_efetivas_min', None)
            nao_efetivas_fora_min = getattr(rdo, 'total_atividades_nao_efetivas_fora_min', None)
            total_atividade_min = getattr(rdo, 'total_atividade_min', None)
            total_confinado_min = _to_int_safe(getattr(rdo, 'total_confinado_min', 0))
            total_abertura_pt_min = _to_int_safe(getattr(rdo, 'total_abertura_pt_min', 0))
            total_n_efetivo_confinado_min = getattr(rdo, 'total_n_efetivo_confinado_min', None)
            if total_n_efetivo_confinado_min is None:
                total_n_efetivo_confinado_min = _to_int_safe(getattr(rdo, 'total_n_efetivo_confinado', 0))

            hh_fora_min = None
            if efetivas_min is not None and nao_efetivas_fora_min is not None:
                hh_fora_min = _to_int_safe(efetivas_min) + _to_int_safe(nao_efetivas_fora_min)

            if hh_fora_min is None and total_atividade_min is not None:
                hh_fora_min = _to_int_safe(total_atividade_min) - total_confinado_min - _to_int_safe(total_n_efetivo_confinado_min) - total_abertura_pt_min
                if hh_fora_min < 0:
                    hh_fora_min = 0

            if hh_fora_min is None:
                os_obj = getattr(rdo, 'ordem_servico', None)
                pob = _to_float_safe(getattr(os_obj, 'pob', 0) if os_obj is not None else 0)
                if pob > 0:
                    hh_fora_min = max(0, int(pob * float(presence_hours) * 60) - total_confinado_min)
                else:
                    hh_fora_min = 0

            return float(hh_fora_min) / 60.0

        def _rt_liquido_diario(rt):
            t_total = _to_float_safe(getattr(rt, 'total_liquido', None))
            t_bombeio = _to_float_safe(getattr(rt, 'bombeio', None))
            if t_total != 0:
                return _normalize_volume(t_total)
            if t_bombeio != 0:
                return _normalize_volume(t_bombeio)
            t_tot = _to_float_safe(getattr(rt, 'residuos_totais', None))
            t_sol = _to_float_safe(getattr(rt, 'residuos_solidos', None))
            if t_tot != 0 or t_sol != 0:
                return _normalize_volume(t_tot - t_sol)
            return 0.0

        def _rt_volume_bombeado_diario(rt):
            # Para "bomba", prioriza o volume efetivamente bombeado.
            t_bombeio = _to_float_safe(getattr(rt, 'bombeio', None))
            if t_bombeio > 0:
                return _normalize_volume(t_bombeio)
            t_total = _to_float_safe(getattr(rt, 'total_liquido', None))
            if t_total > 0:
                return _normalize_volume(t_total)
            t_tot = _to_float_safe(getattr(rt, 'residuos_totais', None))
            t_sol = _to_float_safe(getattr(rt, 'residuos_solidos', None))
            if t_tot != 0 or t_sol != 0:
                return _normalize_volume(max(0.0, t_tot - t_sol))
            return 0.0

        total_hh_confinado_h = 0.0
        total_hh_fora_h = 0.0
        presence_hours = int(getattr(settings, 'PRESENCE_HOURS', 8))

        for rdo in rdo_rows:
            try:
                total_hh_confinado_h += _hh_confinado_h(rdo)
            except Exception:
                pass
            try:
                total_hh_fora_h += _hh_fora_h(rdo, presence_hours)
            except Exception:
                pass

        rdo_ids = [r.id for r in rdo_rows if getattr(r, 'id', None)]
        rt_rows = list(RdoTanque.objects.filter(rdo_id__in=rdo_ids))

        total_ensacamento = sum(_to_int_safe(getattr(rt, 'ensacamento_dia', None)) for rt in rt_rows)
        source_ens = 'RdoTanque.ensacamento_dia'

        total_tambores = sum(_to_int_safe(getattr(rt, 'tambores_dia', None)) for rt in rt_rows)
        source_tam = 'RdoTanque.tambores_dia'

        total_volume_bombeado_m3 = sum(_rt_volume_bombeado_diario(rt) for rt in rt_rows)
        source_bom = 'RdoTanque(bombeio|total_liquido|residuos)'

        total_liquido = sum(_rt_liquido_diario(rt) for rt in rt_rows)
        source_liq = 'RdoTanque(total_liquido|bombeio|residuos)'

        return JsonResponse({
            'success': True,
            'dedupe_mode': 'none',
            'period': {
                'start': start.strftime('%Y-%m-%d'),
                'end': end.strftime('%Y-%m-%d'),
            },
            'rdo_count_raw': int(raw_count or 0),
            'rdo_count_dedup': int(dedup_count or 0),
            'hh_confinado_total': round(float(total_hh_confinado_h), 2),
            'hh_fora_total': round(float(total_hh_fora_h), 2),
            'ensacamento_total': int(total_ensacamento or 0),
            'tambores_total': int(total_tambores or 0),
            'tempo_bomba_total': round(float(total_volume_bombeado_m3), 2),
            'liquido_total': round(float(total_liquido), 3),
            'source_map': {
                'hh_confinado_total': 'RDO(ec_times)',
                'hh_fora_total': 'RDO(total_atividades...)',
                'ensacamento_total': source_ens,
                'tambores_total': source_tam,
                'tempo_bomba_total': source_bom,
                'liquido_total': source_liq,
            },
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required(login_url='/login/')
@require_GET
def ordens_por_dia(request):
    try:
        end_str = request.GET.get('end')
        start_str = request.GET.get('start')
        cliente = request.GET.get('cliente')
        unidade = request.GET.get('unidade')
        os_existente = request.GET.get('os_existente')
        os_existente = request.GET.get('os_existente')
        if end_str:
            end = datetime.strptime(end_str, '%Y-%m-%d').date()
        else:
            end = datetime.today().date()
        if start_str:
            start = datetime.strptime(start_str, '%Y-%m-%d').date()
        else:
            start = end - timedelta(days=29)

        qs = OrdemServico.objects.filter(data_inicio__gte=start, data_inicio__lte=end)
        if cliente:
            qs = qs.filter(Cliente__nome__icontains=cliente)
        if unidade:
            qs = qs.filter(Unidade__nome__icontains=unidade)

        cache_key = f"ordens_por_dia|start={start}|end={end}|cliente={cliente or ''}|unidade={unidade or ''}"
        cached = cache.get(cache_key)
        if cached is not None:
            return JsonResponse(cached)
        dates = list(qs.values_list('data_inicio', flat=True))
        from collections import defaultdict
        counter = defaultdict(float)
        for d in dates:
            try:
                key = d.strftime('%Y-%m-%d') if d is not None else None
            except Exception:
                try:
                    key = str(d)
                except Exception:
                    key = None
            if key:
                counter[key] += 1

        days = []
        values = []
        cur = start
        while cur <= end:
            ds = cur.strftime('%Y-%m-%d')
            days.append(ds)
            values.append(counter.get(ds, 0))
            cur = cur + timedelta(days=1)

        resp = {
            'success': True,
            'labels': days,
            'datasets': [{
                'label': 'Ordens criadas',
                'data': values,
                'borderColor': '#3e95cd',
                'backgroundColor': 'rgba(62,149,205,0.15)'
            }],
            'options': {
                'scales': {
                    'x': {
                        'grid': {
                            'display': True,
                            'color': 'rgba(200, 200, 200, 0.2)'
                        }
                    },
                    'y': {
                        'grid': {
                            'display': True,
                            'color': 'rgba(200, 200, 200, 0.2)'
                        }
                    }
                }
            }
        }
        try:
            cache.set(cache_key, resp, 60)
        except Exception:
            pass
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required(login_url='/login/')
@require_GET
def os_status_summary(request):
    try:
        cliente = request.GET.get('cliente')
        unidade = request.GET.get('unidade')
        start_str = request.GET.get('start')
        end_str = request.GET.get('end')

        qs = OrdemServico.objects.all()
        if cliente:
            qs = qs.filter(Cliente__nome__icontains=cliente)
        if unidade:
            qs = qs.filter(Unidade__nome__icontains=unidade)
        try:
            if start_str and end_str:
                start = datetime.strptime(start_str, '%Y-%m-%d').date()
                end = datetime.strptime(end_str, '%Y-%m-%d').date()
                from django.db.models import Q
                qs = qs.filter(
                    Q(data_inicio__gte=start, data_inicio__lte=end) |
                    Q(data__gte=start, data__lte=end)
                )
            elif start_str:
                start = datetime.strptime(start_str, '%Y-%m-%d').date()
                from django.db.models import Q
                qs = qs.filter(
                    Q(data_inicio__gte=start) |
                    Q(data__gte=start)
                )
            elif end_str:
                end = datetime.strptime(end_str, '%Y-%m-%d').date()
                from django.db.models import Q
                qs = qs.filter(
                    Q(data_inicio__lte=end) |
                    Q(data__lte=end)
                )
        except Exception:
            pass

        rep_qs = qs.values('numero_os').annotate(rep_id=Min('id'))
        rep_ids = [r['rep_id'] for r in rep_qs if r.get('rep_id')]
        base_qs = OrdemServico.objects.filter(id__in=rep_ids) if rep_ids else OrdemServico.objects.none()

        programada = base_qs.filter(status_operacao__iexact='Programada').count()
        em_andamento = base_qs.filter(status_operacao__iexact='Em Andamento').count()
        paralizada = base_qs.filter(status_operacao__iexact='Paralizada').count()
        finalizada = base_qs.filter(status_operacao__iexact='Finalizada').count()
        cancelada = base_qs.filter(status_operacao__iexact='Cancelada').count()
        total = base_qs.count()

        # Aging das OS em andamento ajustado por quantidade de serviços (dias/serviço)
        aging_labels = ['0-2 d/serv', '3-5 d/serv', '6-10 d/serv', '11+ d/serv', 'Sem inicio']
        aging_values = [0, 0, 0, 0, 0]
        aging_days = []
        aging_days_per_service = []
        oldest_os = []

        def _fallback_service_labels(os_obj):
            labels = []
            try:
                raw = getattr(os_obj, 'servicos', None)
                if raw:
                    import re
                    txt = str(raw).strip()
                    # Prioriza separadores que não colidem com nomes de serviço com vírgula.
                    if re.search(r'[;\n|]+', txt):
                        labels = [p.strip() for p in re.split(r'[;\n|]+', txt) if p and p.strip()]
                    else:
                        labels = [p.strip() for p in txt.split(',') if p and p.strip()]
                if not labels:
                    single = getattr(os_obj, 'servico', None)
                    if single:
                        labels = [str(single).strip()]
            except Exception:
                pass

            unique_labels = []
            seen = set()
            for lbl in labels:
                key = str(lbl or '').strip().casefold()
                if not key or key in seen:
                    continue
                seen.add(key)
                unique_labels.append(str(lbl).strip())
            return unique_labels

        try:
            today = datetime.today().date()
            service_counter_by_os = {}
            and_qs = base_qs.filter(status_operacao__iexact='Em Andamento').only(
                'id',
                'numero_os',
                'data_inicio_frente',
                'data_inicio',
                'dias_de_operacao_frente',
                'dias_de_operacao',
                'servico',
                'servicos',
            )
            and_ids = list(and_qs.values_list('id', flat=True))

            if and_ids:
                try:
                    from .models import RDO
                    rdo_services = RDO.objects.filter(
                        ordem_servico_id__in=and_ids
                    ).values_list('ordem_servico_id', 'servico_exec', 'servico_rdo')
                    for os_id, serv_exec, serv_rdo in rdo_services.iterator(chunk_size=1000):
                        try:
                            os_key = int(os_id or 0)
                        except Exception:
                            os_key = 0
                        if os_key <= 0:
                            continue

                        servico_nome = str(serv_exec or serv_rdo or '').strip()
                        if not servico_nome:
                            continue

                        bucket = service_counter_by_os.setdefault(os_key, {})
                        bucket[servico_nome] = int(bucket.get(servico_nome, 0)) + 1
                except Exception:
                    service_counter_by_os = {}

            for os_obj in and_qs.iterator(chunk_size=300):
                try:
                    dias = None
                    inicio = getattr(os_obj, 'data_inicio_frente', None) or getattr(os_obj, 'data_inicio', None)
                    if inicio:
                        dias = (today - inicio).days
                        if dias is not None and dias < 0:
                            dias = 0
                    if dias is None:
                        dias_fallback = getattr(os_obj, 'dias_de_operacao_frente', None) or getattr(os_obj, 'dias_de_operacao', None)
                        try:
                            dias = int(dias_fallback) if dias_fallback is not None else None
                        except Exception:
                            dias = None
                        if dias is not None and dias < 0:
                            dias = 0

                    if dias is None:
                        aging_values[4] += 1
                        continue

                    aging_days.append(int(dias))
                    os_pk = int(getattr(os_obj, 'id', 0) or 0)
                    service_counter = service_counter_by_os.get(os_pk, {})
                    service_items = sorted(
                        service_counter.items(),
                        key=lambda kv: (-int(kv[1] or 0), str(kv[0]).lower())
                    )

                    qtd_servicos = len(service_items)
                    qtd_execucoes_servico = sum(int(q or 0) for _, q in service_items)
                    if qtd_servicos > 0:
                        preview = [
                            f"{name} ({int(cnt)})" if int(cnt) > 1 else str(name)
                            for name, cnt in service_items[:3]
                        ]
                        if qtd_servicos > 3:
                            preview.append(f"+{qtd_servicos - 3}")
                        servicos_resumo = ', '.join(preview)
                    else:
                        fallback_labels = _fallback_service_labels(os_obj)
                        qtd_servicos = len(fallback_labels)
                        qtd_execucoes_servico = qtd_servicos
                        if qtd_servicos > 0:
                            preview = [str(name) for name in fallback_labels[:3]]
                            if qtd_servicos > 3:
                                preview.append(f"+{qtd_servicos - 3}")
                            servicos_resumo = ', '.join(preview)
                        else:
                            servicos_resumo = 'Servico nao informado'
                    if qtd_servicos <= 0:
                        qtd_servicos = 1
                    if qtd_execucoes_servico <= 0:
                        qtd_execucoes_servico = qtd_servicos

                    dias_por_servico = float(dias) / float(qtd_servicos)
                    aging_days_per_service.append(dias_por_servico)
                    numero_os = str(getattr(os_obj, 'numero_os', '') or getattr(os_obj, 'id', '') or '')
                    oldest_os.append({
                        'numero_os': numero_os,
                        'dias': int(dias),
                        'qtd_servicos': int(qtd_servicos),
                        'qtd_execucoes_servico': int(qtd_execucoes_servico),
                        'dias_por_servico': round(float(dias_por_servico), 2),
                        'servicos_resumo': servicos_resumo,
                    })
                    if dias_por_servico <= 2:
                        aging_values[0] += 1
                    elif dias_por_servico <= 5:
                        aging_values[1] += 1
                    elif dias_por_servico <= 10:
                        aging_values[2] += 1
                    else:
                        aging_values[3] += 1
                except Exception:
                    aging_values[4] += 1
                    continue
        except Exception:
            pass

        classified_total = int(sum(aging_values))
        avg_days = round((sum(aging_days) / float(len(aging_days))), 1) if aging_days else 0.0
        oldest_days = int(max(aging_days)) if aging_days else 0
        avg_days_per_service = round((sum(aging_days_per_service) / float(len(aging_days_per_service))), 2) if aging_days_per_service else 0.0
        worst_days_per_service = round(float(max(aging_days_per_service)), 2) if aging_days_per_service else 0.0
        labels_rank = aging_labels[:4]
        values_rank = aging_values[:4]
        leader_idx = values_rank.index(max(values_rank)) if values_rank else 0
        leader_label = labels_rank[leader_idx] if values_rank and max(values_rank) > 0 else '-'
        top_oldest_os = sorted(
            oldest_os,
            key=lambda item: (
                -(float(item.get('dias_por_servico') or 0.0)),
                -(int(item.get('dias') or 0)),
                str(item.get('numero_os') or '')
            )
        )[:8]

        # Gerar listas de OS (top 6) por status contendo numero_os e contagem de RDOs
        try:
            from django.db.models import Count as _Count
            def build_status_items(qs_base, status):
                qs_s = qs_base.filter(status_operacao__iexact=status)
                items_qs = qs_s.values('numero_os').annotate(rdos_count=_Count('rdos')).order_by('-rdos_count', '-numero_os')[:6]
                items = [{'numero_os': row.get('numero_os'), 'rdos_count': int(row.get('rdos_count') or 0)} for row in items_qs]
                return items

            programada_items = build_status_items(base_qs, 'Programada')
            em_andamento_items = build_status_items(base_qs, 'Em Andamento')
            paralizada_items = build_status_items(base_qs, 'Paralizada')
            finalizada_items = build_status_items(base_qs, 'Finalizada')
            cancelada_items = build_status_items(base_qs, 'Cancelada')
        except Exception:
            programada_items = []
            em_andamento_items = []
            paralizada_items = []
            finalizada_items = []
            cancelada_items = []

        try:
            logger = logging.getLogger(__name__)
            logger.debug('os_status_summary: filters=%s, rep_ids=%d, base_qs=%d',
                         {'cliente': cliente, 'unidade': unidade, 'start': start_str, 'end': end_str},
                         len(rep_ids),
                         total)
        except Exception:
            pass

        # Log detalhado para depuração: registrar contagens calculadas
        try:
            log = logging.getLogger(__name__)
            log.info('os_status_summary/result cliente=%s unidade=%s start=%s end=%s total=%d programada=%d em_andamento=%d paralizada=%d finalizada=%d cancelada=%d',
                     cliente or '', unidade or '', start_str or '', end_str or '', total, programada, em_andamento, paralizada, finalizada, cancelada)
        except Exception:
            pass

        resp = {
            'success': True,
            'total': total,
            'programada': programada,
            'em_andamento': em_andamento,
            'paralizada': paralizada,
            'finalizada': finalizada,
            'cancelada': cancelada,
            'programada_items': programada_items,
            'em_andamento_items': em_andamento_items,
            'paralizada_items': paralizada_items,
            'finalizada_items': finalizada_items,
            'cancelada_items': cancelada_items,
            'aging_em_andamento': {
                'labels': aging_labels,
                'values': aging_values,
                'classified_total': classified_total,
                'avg_days': avg_days,
                'oldest_days': oldest_days,
                'avg_days_per_service': avg_days_per_service,
                'worst_days_per_service': worst_days_per_service,
                'leader_bucket': leader_label,
                'sem_inicio': int(aging_values[4]),
                'top_oldest_os': top_oldest_os,
                'metric': 'dias_por_servico',
            },
            'ts': datetime.utcnow().isoformat() + 'Z'
        }
        return JsonResponse(resp)
    except Exception as e:
        logging.exception('Erro em os_status_summary')
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required(login_url='/login/')
@require_GET
def status_os(request):
    try:
        cliente = request.GET.get('cliente')
        unidade = request.GET.get('unidade')
        os_existente = request.GET.get('os_existente')
        os_existente = request.GET.get('os_existente')
        start_str = request.GET.get('start')
        end_str = request.GET.get('end')
        qs = OrdemServico.objects.all()
        if cliente:
            qs = qs.filter(Cliente__nome__icontains=cliente)
        if unidade:
            qs = qs.filter(Unidade__nome__icontains=unidade)
        try:
            if start_str:
                start = datetime.strptime(start_str, '%Y-%m-%d').date()
                qs = qs.filter(data_inicio__gte=start)
            if end_str:
                end = datetime.strptime(end_str, '%Y-%m-%d').date()
                qs = qs.filter(data__lte=end)
        except Exception:
            pass
        cache_key = f"status_os|cliente={cliente or ''}|unidade={unidade or ''}|start={start_str or ''}|end={end_str or ''}"
        cached = cache.get(cache_key)
        if cached is not None:
            return JsonResponse(cached)

        data = qs.values('status_geral').annotate(count=Count('id')).order_by('-count')
        labels = [item['status_geral'] or 'Indefinido' for item in data]
        values = [item['count'] for item in data]
        resp = {'success': True, 'labels': labels, 'values': values}
        try:
            cache.set(cache_key, resp, 60)
        except Exception:
            pass
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required(login_url='/login/')
@require_GET
def servicos_mais_frequentes(request):
    try:
        top = int(request.GET.get('top', 10))
        cliente = request.GET.get('cliente')
        unidade = request.GET.get('unidade')
        os_existente = request.GET.get('os_existente')
        os_existente = request.GET.get('os_existente')
        start_str = request.GET.get('start')
        end_str = request.GET.get('end')
        qs = OrdemServico.objects.all()
        if cliente:
            qs = qs.filter(Cliente__nome__icontains=cliente)
        if unidade:
            qs = qs.filter(Unidade__nome__icontains=unidade)
        try:
            if start_str:
                start = datetime.strptime(start_str, '%Y-%m-%d').date()
                qs = qs.filter(data_inicio__gte=start)
            if end_str:
                end = datetime.strptime(end_str, '%Y-%m-%d').date()
                qs = qs.filter(data__lte=end)
        except Exception:
            pass

        cache_key = f"servicos_top={top}|cliente={cliente or ''}|unidade={unidade or ''}|start={start_str or ''}|end={end_str or ''}"
        cached = cache.get(cache_key)
        if cached is not None:
            return JsonResponse(cached)

        from collections import defaultdict
        counter = defaultdict(float)
        for servicos_field, servico_field in qs.values_list('servicos', 'servico'):
            parts = []
            try:
                if servicos_field:
                    parts = [p.strip() for p in servicos_field.split(',') if p.strip()]
                elif servico_field:
                    parts = [servico_field.strip()]
            except Exception:
                parts = []

            if not parts:
                counter['Indefinido'] += 1
            else:
                for p in parts:
                    p_norm = unicodedata.normalize('NFKD', p).encode('ascii', 'ignore').decode('ascii').lower()
                    counter[p_norm] += 1

        most = counter.most_common(top)
        labels = [item[0] for item in most]
        values = [item[1] for item in most]
        labels = [lab if len(lab) <= 60 else (lab[:57] + '...') for lab in labels]
        resp = {'success': True, 'labels': labels, 'values': values}
        try:
            cache.set(cache_key, resp, 60)
        except Exception:
            pass
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required(login_url='/login/')
@require_GET
def top_clientes(request):
    try:
        top_param = request.GET.get('top')
        try:
            top = int(top_param) if top_param is not None else 10
        except Exception:
            top = 10
        if top < 1:
            top = 1
        if top > 200:
            top = 200
        unidade = request.GET.get('unidade')
        os_existente = request.GET.get('os_existente')
        os_existente = request.GET.get('os_existente')
        start_str = request.GET.get('start')
        end_str = request.GET.get('end')
        qs = OrdemServico.objects.all()
        if unidade:
            qs = qs.filter(Unidade__nome__icontains=unidade)
        try:
            if start_str:
                start = datetime.strptime(start_str, '%Y-%m-%d').date()
                qs = qs.filter(data_inicio__gte=start)
            if end_str:
                end = datetime.strptime(end_str, '%Y-%m-%d').date()
                qs = qs.filter(data__lte=end)
        except Exception:
            pass

        cache_key = f"top_clientes|top={top}|unidade={unidade or ''}|start={start_str or ''}|end={end_str or ''}"
        cached = cache.get(cache_key)
        if cached is not None:
            return JsonResponse(cached)

        data = list(qs.values('Cliente__nome').annotate(count=Count('id')).order_by('-count')[:top])
        labels = [ (str(item.get('Cliente__nome')) if item.get('Cliente__nome') is not None else 'Indefinido') for item in data ]
        values = [ int(item.get('count') or 0) for item in data ]
        labels = [lab if len(lab) <= 60 else (lab[:57] + '...') for lab in labels]
        resp = {'success': True, 'labels': labels, 'values': values}
        try:
            cache.set(cache_key, resp, 60)
        except Exception:
            pass
        return JsonResponse(resp)
    except Exception as e:
        try:
            logger = logging.getLogger(__name__)
            logger.exception('Erro em top_clientes: %s', e)
        except Exception:
            pass
        return JsonResponse({'success': False, 'error': 'Erro interno ao gerar top clientes'}, status=500)

@login_required(login_url='/login/')
@require_GET
def metodos_mais_utilizados(request):
    try:
        top = int(request.GET.get('top', 10))
        cliente = request.GET.get('cliente')
        unidade = request.GET.get('unidade')
        os_existente = request.GET.get('os_existente')
        os_existente = request.GET.get('os_existente')
        start_str = request.GET.get('start')
        end_str = request.GET.get('end')
        qs = OrdemServico.objects.all()
        if cliente:
            qs = qs.filter(Cliente__nome__icontains=cliente)
        if unidade:
            qs = qs.filter(Unidade__nome__icontains=unidade)
        try:
            if start_str:
                start = datetime.strptime(start_str, '%Y-%m-%d').date()
                qs = qs.filter(data_inicio__gte=start)
            if end_str:
                end = datetime.strptime(end_str, '%Y-%m-%d').date()
                qs = qs.filter(data__lte=end)
        except Exception:
            pass

        cache_key = f"metodos_top={top}|cliente={cliente or ''}|unidade={unidade or ''}|start={start_str or ''}|end={end_str or ''}"
        cached = cache.get(cache_key)
        if cached is not None:
            return JsonResponse(cached)

        data = qs.values('metodo').annotate(count=Count('id')).order_by('-count')[:top]
        labels = [item['metodo'] or 'Indefinido' for item in data]
        values = [item['count'] for item in data]
        labels = [lab if len(lab) <= 60 else (lab[:57] + '...') for lab in labels]
        resp = {'success': True, 'labels': labels, 'values': values}
        try:
            cache.set(cache_key, resp, 60)
        except Exception:
            pass
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required(login_url='/login/')
@require_GET
def supervisores_tempo_medio(request):
    try:
        unidade = request.GET.get('unidade')
        os_existente = request.GET.get('os_existente')
        os_existente = request.GET.get('os_existente')
        start_str = request.GET.get('start')
        end_str = request.GET.get('end')
        qs = OrdemServico.objects.filter(dias_de_operacao__isnull=False)
        if unidade:
            qs = qs.filter(unidade__icontains=unidade)
        try:
            if start_str:
                start = datetime.strptime(start_str, '%Y-%m-%d').date()
                qs = qs.filter(data_inicio__gte=start)
            if end_str:
                end = datetime.strptime(end_str, '%Y-%m-%d').date()
                qs = qs.filter(data__lte=end)
        except Exception:
            pass

        cache_key = f"supervisores_tempo_medio|unidade={unidade or ''}|start={start_str or ''}|end={end_str or ''}"
        cached = cache.get(cache_key)
        if cached is not None:
            return JsonResponse(cached)

        data = qs.values('supervisor').annotate(avg_days=Avg('dias_de_operacao'), cnt=Count('id')).order_by('-avg_days')
        labels = []
        values = []
        counts = []
        User = get_user_model()
        for item in data:
            sup_id = item.get('supervisor')
            try:
                u = User.objects.filter(pk=sup_id).first()
                name = (u.get_full_name() if u and getattr(u, 'get_full_name', None) else (u.username if u else 'Indefinido'))
            except Exception:
                name = 'Indefinido'
            labels.append(name)
            values.append(round(float(item.get('avg_days') or 0), 1))
            counts.append(item.get('cnt') or 0)

        resp = {'success': True, 'labels': labels, 'values': values, 'counts': counts}
        try:
            cache.set(cache_key, resp, 60)
        except Exception:
            pass
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required(login_url='/login/')
@require_GET
def dashboard_kpis(request):
    try:
        start_str = request.GET.get('start')
        end_str = request.GET.get('end')
        cliente = request.GET.get('cliente')
        unidade = request.GET.get('unidade')
        os_existente = request.GET.get('os_existente')
        os_existente = request.GET.get('os_existente')

        qs = OrdemServico.objects.all()
        try:
            if start_str:
                start = datetime.strptime(start_str, '%Y-%m-%d').date()
                qs = qs.filter(data_inicio__gte=start)
            if end_str:
                end = datetime.strptime(end_str, '%Y-%m-%d').date()
                qs = qs.filter(data__lte=end)
        except Exception:
            start = None
            end = None

        if cliente:
            qs = qs.filter(Cliente__nome__icontains=cliente)
        if unidade:
            qs = qs.filter(Unidade__nome__icontains=unidade)

        total = qs.count()

        statuses = ['Programada', 'Em Andamento', 'Paralizada', 'Finalizada', 'Cancelada']
        status_counts = {s: qs.filter(status_operacao__iexact=s).count() for s in statuses}

        abertas = status_counts.get('Em Andamento', 0)

        if start_str or end_str:
            try:
                if start_str and end_str:
                    concl_qs = OrdemServico.objects.filter(status_operacao__iexact='Finalizada', data_fim__gte=start, data_fim__lte=end)
                    if cliente:
                        concl_qs = concl_qs.filter(Cliente__nome__icontains=cliente)
                    if unidade:
                        concl_qs = concl_qs.filter(Unidade__nome__icontains=unidade)
                    concluidas_mes = concl_qs.count()
                else:
                    concl_qs = OrdemServico.objects.filter(status_operacao__iexact='Finalizada')
                    if start_str:
                        concl_qs = concl_qs.filter(data_fim__gte=start)
                    if end_str:
                        concl_qs = concl_qs.filter(data_fim__lte=end)
                    if cliente:
                        concl_qs = concl_qs.filter(Cliente__nome__icontains=cliente)
                    if unidade:
                        concl_qs = concl_qs.filter(Unidade__nome__icontains=unidade)
                    concluidas_mes = concl_qs.count()
            except Exception:
                concluidas_mes = 0
        else:
            hoje = datetime.today().date()
            inicio_mes = hoje.replace(day=1)
            concluidas_mes = OrdemServico.objects.filter(status_operacao__iexact='Finalizada', data_fim__gte=inicio_mes, data_fim__lte=hoje).count()

        try:
            avg_days = qs.filter(dias_de_operacao__isnull=False).aggregate(avg=Avg('dias_de_operacao'))['avg'] or 0
        except Exception:
            avg_days = 0

        resp = {
            'success': True,
            'total': total,
            'abertas': abertas,
            'concluidas_mes': concluidas_mes,
            'tempo_medio_operacao': float(avg_days),
            'status_breakdown': status_counts,
        }
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required(login_url='/login/')
@require_GET
def supervisores_status(request):
    try:
        User = get_user_model()
        group = Group.objects.filter(name__in=['supervisore', 'supervisores', 'Supervisor', 'Supervisores']).first()
        if group:
            users = group.user_set.filter(is_active=True).order_by('first_name', 'last_name', 'username')
        else:
            users = User.objects.filter(ordens_supervisionadas__isnull=False).distinct().order_by('first_name', 'last_name', 'username')

        cliente = request.GET.get('cliente')
        unidade = request.GET.get('unidade')
        os_existente = request.GET.get('os_existente')
        os_existente = request.GET.get('os_existente')
        start_str = request.GET.get('start')
        end_str = request.GET.get('end')

        cache_key = f"supervisores_status|cliente={cliente or ''}|unidade={unidade or ''}|start={start_str or ''}|end={end_str or ''}"
        cached = cache.get(cache_key)
        if cached is not None:
            return JsonResponse(cached)

        labels = []
        values = []
        colors = []
        details = []
        em = 0
        disponiveis = 0

        for u in users:
            qs = OrdemServico.objects.filter(supervisor=u)
            if cliente:
                qs = qs.filter(cliente__icontains=cliente)
            if unidade:
                qs = qs.filter(unidade__icontains=unidade)
            try:
                if start_str:
                    start = datetime.strptime(start_str, '%Y-%m-%d').date()
                    qs = qs.filter(data_inicio_frente__gte=start)
                if end_str:
                    end = datetime.strptime(end_str, '%Y-%m-%d').date()
                    qs = qs.filter(data_inicio_frente__lte=end)
            except Exception:
                pass

            active_count = qs.filter(data_inicio_frente__isnull=False).exclude(status_geral__iexact='Finalizada').count()
            status = 'Em Embarque' if active_count > 0 else 'Disponível'
            display_name = (getattr(u, 'get_full_name', None) and u.get_full_name()) or getattr(u, 'username', str(u))
            labels.append(display_name)
            values.append(active_count if active_count > 0 else 0)
            if active_count > 1:
                colors.append('#ffb300')
            elif active_count == 1:
                colors.append('#e53935')
            else:
                colors.append('#4caf50')

            details.append({'id': u.pk, 'name': display_name, 'active_count': active_count, 'status': status})
            if active_count > 0:
                em += 1
            else:
                disponiveis += 1

        resp = {'success': True, 'labels': labels, 'values': values, 'colors': colors, 'details': details, 'summary': {'em_embarque': em, 'disponiveis': disponiveis}}
        try:
            cache.set(cache_key, resp, 60)
        except Exception:
            pass
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required(login_url='/login/')
@require_GET
def rdo_soma_hh_confinado_por_dia(request):
    try:
        qs, start, end = _dashboard_filtered_rdo_qs(request)

        from collections import Counter
        counter = Counter()
        
        for rdo in qs.order_by('data', 'id'):
            try:
                d_date = getattr(rdo, 'data', None)
                if d_date:
                    d = d_date.strftime('%Y-%m-%d')
                    total_minutos = 0.0
                    for i in range(1, 7):
                        entrada_field = f'entrada_confinado_{i}'
                        saida_field = f'saida_confinado_{i}'
                        entrada = getattr(rdo, entrada_field, None)
                        saida = getattr(rdo, saida_field, None)
                        if entrada and saida:
                            try:
                                entrada_min = float(entrada.hour * 60 + entrada.minute) + float(getattr(entrada, 'second', 0)) / 60.0
                                saida_min = float(saida.hour * 60 + saida.minute) + float(getattr(saida, 'second', 0)) / 60.0
                                if saida_min >= entrada_min:
                                    total_minutos += (saida_min - entrada_min)
                                else:
                                    total_minutos += ((24.0 * 60.0 - entrada_min) + saida_min)
                            except Exception:
                                pass
                    horas = round(total_minutos / 60.0, 2)
                    counter[d] += horas
            except Exception:
                pass
        
        days = []
        values = []
        cur = start
        while cur <= end:
            ds = cur.strftime('%Y-%m-%d')
            days.append(ds)
            values.append(round(counter.get(ds, 0), 2))
            cur = cur + timedelta(days=1)
        
        resp = {
            'success': True,
            'labels': days,
            'datasets': [{
                'label': 'HH em espaço confinado',
                'data': values,
                'borderColor': '#e74c3c',
                'backgroundColor': 'rgba(231,76,60,0.15)',
                'fill': True
            }],
            'options': {
                'scales': {
                    'x': {
                        'grid': {
                            'display': True,
                            'color': 'rgba(200, 200, 200, 0.2)'
                        }
                    },
                    'y': {
                        'grid': {
                            'display': True,
                            'color': 'rgba(200, 200, 200, 0.2)'
                        }
                    }
                }
            }
        }
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required(login_url='/login/')
@require_GET
def rdo_soma_hh_fora_confinado_por_dia(request):
    try:
        qs, start, end = _dashboard_filtered_rdo_qs(request)

        from collections import Counter
        counter = Counter()
        presence_hours = int(getattr(settings, 'PRESENCE_HOURS', 8))

        for rdo in qs.order_by('data', 'id'):
            try:
                d_date = getattr(rdo, 'data', None)
                if not d_date:
                    continue
                d = d_date.strftime('%Y-%m-%d')

                efetivas_min = getattr(rdo, 'total_atividades_efetivas_min', None)
                nao_efetivas_fora_min = getattr(rdo, 'total_atividades_nao_efetivas_fora_min', None)
                total_atividade_min = getattr(rdo, 'total_atividade_min', None)
                total_confinado_min = int(getattr(rdo, 'total_confinado_min', 0) or 0)
                total_abertura_pt_min = int(getattr(rdo, 'total_abertura_pt_min', 0) or 0)
                total_n_efetivo_confinado_min = getattr(rdo, 'total_n_efetivo_confinado_min', None)
                if total_n_efetivo_confinado_min is None:
                    total_n_efetivo_confinado_min = int(getattr(rdo, 'total_n_efetivo_confinado', 0) or 0)

                hh_fora_min = None

                if efetivas_min is not None and nao_efetivas_fora_min is not None:
                    try:
                        hh_fora_min = int(efetivas_min or 0) + int(nao_efetivas_fora_min or 0)
                    except Exception:
                        hh_fora_min = None

                if hh_fora_min is None and total_atividade_min is not None:
                    try:
                        hh_fora_min = int(total_atividade_min) - int(total_confinado_min or 0) - int(total_n_efetivo_confinado_min or 0) - int(total_abertura_pt_min or 0)
                        if hh_fora_min < 0:
                            hh_fora_min = 0
                    except Exception:
                        hh_fora_min = 0

                if hh_fora_min is None:
                    os = getattr(rdo, 'ordem_servico', None)
                    pob = 0
                    try:
                        pob = float(getattr(os, 'pob', 0) or 0)
                    except Exception:
                        pob = 0
                    hh_confinado_min = int(getattr(rdo, 'total_confinado_min', 0) or 0)
                    if pob and pob > 0:
                        try:
                            hh_fora_min = max(0, int(pob * float(presence_hours) * 60) - int(hh_confinado_min))
                        except Exception:
                            hh_fora_min = 0
                    else:
                        continue

                try:
                    horas = round(float(hh_fora_min) / 60.0, 2)
                    counter[d] += horas
                except Exception:
                    continue
            except Exception:
                pass
        
        days = []
        values = []
        cur = start
        while cur <= end:
            ds = cur.strftime('%Y-%m-%d')
            days.append(ds)
            values.append(counter.get(ds, 0))
            cur = cur + timedelta(days=1)
        
        resp = {
            'success': True,
            'labels': days,
            'datasets': [{
                'label': 'HH fora de espaço confinado',
                'data': values,
                'borderColor': '#3498db',
                'backgroundColor': 'rgba(52,152,219,0.15)',
                'fill': True
            }],
            'options': {
                'scales': {
                    'x': {
                        'grid': {
                            'display': True,
                            'color': 'rgba(200, 200, 200, 0.2)'
                        }
                    },
                    'y': {
                        'grid': {
                            'display': True,
                            'color': 'rgba(200, 200, 200, 0.2)'
                        }
                    }
                }
            }
        }
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required(login_url='/login/')
@require_GET
def rdo_ensacamento_por_dia(request):
    try:
        from .models import RdoTanque
        from collections import Counter

        qs, start, end = _dashboard_filtered_rdo_qs(request)
        rdo_rows = list(qs.order_by('data', 'id'))
        counter = Counter()

        def _to_int_safe(x):
            try:
                return int(x or 0)
            except Exception:
                try:
                    return int(float(x or 0))
                except Exception:
                    return 0

        rdo_date_by_id = {}
        rdo_ids = []
        for rdo in rdo_rows:
            rid = getattr(rdo, 'id', None)
            d = getattr(rdo, 'data', None)
            if rid and d:
                rdo_ids.append(rid)
                rdo_date_by_id[rid] = d.strftime('%Y-%m-%d')

        rt_rows = list(
            RdoTanque.objects.filter(rdo_id__in=rdo_ids).values('rdo_id', 'ensacamento_dia')
        ) if rdo_ids else []
        for row in rt_rows:
            day = rdo_date_by_id.get(row.get('rdo_id'))
            if not day:
                continue
            counter[day] += _to_int_safe(row.get('ensacamento_dia'))
        
        days = []
        values = []
        cur = start
        while cur <= end:
            ds = cur.strftime('%Y-%m-%d')
            days.append(ds)
            values.append(counter.get(ds, 0))
            cur = cur + timedelta(days=1)
        
        resp = {
            'success': True,
            'labels': days,
            'datasets': [{
                'label': 'Ensacamento por dia',
                'data': values,
                'backgroundColor': '#9b59b6',
                'borderColor': '#8e44ad'
            }],
            'options': {
                'scales': {
                    'x': {
                        'grid': {
                            'display': True,
                            'color': 'rgba(200, 200, 200, 0.2)'
                        }
                    },
                    'y': {
                        'grid': {
                            'display': True,
                            'color': 'rgba(200, 200, 200, 0.2)'
                        }
                    }
                }
            }
        }
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required(login_url='/login/')
@require_GET
def rdo_tambores_por_dia(request):
    try:
        from .models import RdoTanque
        from collections import Counter

        qs, start, end = _dashboard_filtered_rdo_qs(request)
        rdo_rows = list(qs.order_by('data', 'id'))
        counter = Counter()

        def _to_int_safe(x):
            try:
                return int(x or 0)
            except Exception:
                try:
                    return int(float(x or 0))
                except Exception:
                    return 0

        rdo_date_by_id = {}
        rdo_ids = []
        for rdo in rdo_rows:
            rid = getattr(rdo, 'id', None)
            d = getattr(rdo, 'data', None)
            if rid and d:
                rdo_ids.append(rid)
                rdo_date_by_id[rid] = d.strftime('%Y-%m-%d')

        rt_rows = list(
            RdoTanque.objects.filter(rdo_id__in=rdo_ids).values('rdo_id', 'tambores_dia')
        ) if rdo_ids else []
        for row in rt_rows:
            day = rdo_date_by_id.get(row.get('rdo_id'))
            if not day:
                continue
            counter[day] += _to_int_safe(row.get('tambores_dia'))
        
        days = []
        values = []
        cur = start
        while cur <= end:
            ds = cur.strftime('%Y-%m-%d')
            days.append(ds)
            values.append(counter.get(ds, 0))
            cur = cur + timedelta(days=1)
        
        resp = {
            'success': True,
            'labels': days,
            'datasets': [{
                'label': 'Tambores gerados',
                'data': values,
                'backgroundColor': '#e74c3c',
                'borderColor': '#c0392b'
            }],
            'options': {
                'scales': {
                    'x': {
                        'grid': {
                            'display': True,
                            'color': 'rgba(200, 200, 200, 0.2)'
                        }
                    },
                    'y': {
                        'grid': {
                            'display': True,
                            'color': 'rgba(200, 200, 200, 0.2)'
                        }
                    }
                }
            }
        }
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required(login_url='/login/')
@require_GET
def rdo_tempo_bomba_por_dia(request):
    try:
        from .models import RDO
        from datetime import timedelta as td
        from collections import defaultdict
        import re

        start_str = request.GET.get('start')
        end_str = request.GET.get('end')
        supervisor = request.GET.get('supervisor')
        tanque = request.GET.get('tanque')
        cliente = request.GET.get('cliente')
        unidade = request.GET.get('unidade')
        os_existente = request.GET.get('os_existente')
        os_status_scope_raw = request.GET.get('os_status_scope')

        if end_str:
            end = datetime.strptime(end_str, '%Y-%m-%d').date()
        else:
            end = datetime.today().date()
        if start_str:
            start = datetime.strptime(start_str, '%Y-%m-%d').date()
        else:
            start = end - td(days=29)

        qs = RDO.objects.filter(data__gte=start, data__lte=end)
        if supervisor:
            qs = qs.filter(ordem_servico__supervisor__username=supervisor)
        if tanque:
            qs = qs.filter(
                Q(nome_tanque__icontains=tanque) |
                Q(tanque_codigo__icontains=tanque) |
                Q(tanques__tanque_codigo__icontains=tanque)
            ).distinct()
        if cliente:
            qs = qs.filter(ordem_servico__Cliente__nome__icontains=cliente)
        if unidade:
            qs = qs.filter(ordem_servico__Unidade__nome__icontains=unidade)
        if os_existente:
            qs = apply_os_filter_generic(qs, os_existente)

        def _normalize_os_status_scope(raw_scope):
            val = str(raw_scope or '').strip().lower()
            if val in {'finalizada', 'finalizadas', 'final', 'concluida', 'concluidas'}:
                return 'finalizadas'
            if val in {'todas', 'todos', 'all', 'historico', 'historico_completo'}:
                return 'todas'
            return 'em_andamento'

        os_status_scope = _normalize_os_status_scope(os_status_scope_raw)
        if os_status_scope == 'finalizadas':
            qs = qs.filter(
                Q(ordem_servico__status_operacao__iexact='Finalizada') |
                Q(ordem_servico__status_operacao__icontains='finaliz') |
                Q(ordem_servico__status_operacao__icontains='conclu')
            ).distinct()
        elif os_status_scope == 'todas':
            # Histórico operacional: inclui em andamento e finalizadas; remove canceladas.
            qs = qs.exclude(
                Q(ordem_servico__status_operacao__iexact='Cancelada') |
                Q(ordem_servico__status_operacao__icontains='cancel')
            ).distinct()
        else:
            qs = qs.filter(
                Q(ordem_servico__status_operacao__iexact='Em Andamento') |
                Q(ordem_servico__status_operacao__icontains='andamento')
            ).distinct()

        def _clean_tank_label(val):
            try:
                if val is None:
                    return None
                s = str(val).strip()
                if not s:
                    return None
                low = s.casefold()
                invalid = {
                    '-', '—', 'none', 'null', 'n/a', 'na',
                    'desconhecido', 'unknown', 'a definir',
                    'sem tanque', 'sem identificacao', 'sem identificação'
                }
                if low in invalid:
                    return None
                return s
            except Exception:
                return None

        def _canonical_tank_key(label):
            try:
                s = re.sub(r'\s+', ' ', str(label or '').strip())
                if not s:
                    return None
                return s.casefold()
            except Exception:
                return None

        def _display_tank_label(label):
            try:
                s = re.sub(r'\s+', ' ', str(label or '').strip())
                return s.upper() if s else 'SEM IDENTIFICACAO'
            except Exception:
                return 'SEM IDENTIFICACAO'

        def _pick_os_tank_label(os_obj):
            if os_obj is None:
                return None
            direct = _clean_tank_label(getattr(os_obj, 'tanque', None))
            if direct:
                return direct
            raw_multi = getattr(os_obj, 'tanques', None)
            if raw_multi not in (None, ''):
                for token in re.split(r'[;,|/]+', str(raw_multi)):
                    cleaned = _clean_tank_label(token)
                    if cleaned:
                        return cleaned
            return None

        def _resolve_tank_label(rt_obj, rdo_obj):
            if rt_obj is not None:
                for cand in (
                    getattr(rt_obj, 'tanque_codigo', None),
                    getattr(rt_obj, 'nome_tanque', None),
                ):
                    cleaned = _clean_tank_label(cand)
                    if cleaned:
                        return cleaned
            if rdo_obj is not None:
                for cand in (
                    getattr(rdo_obj, 'tanque_codigo', None),
                    getattr(rdo_obj, 'nome_tanque', None),
                ):
                    cleaned = _clean_tank_label(cand)
                    if cleaned:
                        return cleaned
                return _pick_os_tank_label(getattr(rdo_obj, 'ordem_servico', None))
            return None

        def _fallback_label_for_rdo(rdo_obj):
            os_obj = getattr(rdo_obj, 'ordem_servico', None) if rdo_obj is not None else None
            os_num = getattr(os_obj, 'numero_os', None) if os_obj is not None else None
            if os_num not in (None, ''):
                return f"OS {os_num}"
            rid = getattr(rdo_obj, 'id', None)
            if rid not in (None, ''):
                return f"RDO {rid}"
            return 'Sem identificacao'

        def _to_float_safe(value):
            try:
                return float(value or 0)
            except Exception:
                return 0.0

        def _normalize_volume(v):
            f = _to_float_safe(v)
            if abs(f) > 100:
                try:
                    return f / 1000.0
                except Exception:
                    return f
            return f

        def _to_positive_float(value):
            try:
                n = float(value or 0)
                return n if n > 0 else 0.0
            except Exception:
                return 0.0

        def _volume_bombeado_m3(rt_obj):
            # Prioridade da fonte: bombeio > total_liquido > (residuos_totais - residuos_solidos)
            t_bombeio = _to_positive_float(getattr(rt_obj, 'bombeio', None))
            if t_bombeio > 0:
                return _normalize_volume(t_bombeio)

            t_total = _to_positive_float(getattr(rt_obj, 'total_liquido', None))
            if t_total > 0:
                return _normalize_volume(t_total)

            t_tot = _to_positive_float(getattr(rt_obj, 'residuos_totais', None))
            t_sol = _to_positive_float(getattr(rt_obj, 'residuos_solidos', None))
            if t_tot > 0 or t_sol > 0:
                return _normalize_volume(max(0.0, t_tot - t_sol))
            return 0.0

        def _to_percent_value(value):
            try:
                n = float(value)
                if not (n == n):
                    return None
                if n < 0:
                    n = 0.0
                if n > 100:
                    n = 100.0
                return round(float(n), 2)
            except Exception:
                return None

        def _clean_context_text(value):
            try:
                if value is None:
                    return None
                s = str(value).strip()
                if not s:
                    return None
                return s
            except Exception:
                return None

        def _extract_os_context(rdo_obj):
            os_obj = getattr(rdo_obj, 'ordem_servico', None) if rdo_obj is not None else None
            if os_obj is None:
                return {'empresa': None, 'unidade': None, 'os': None, 'status_operacao': None}

            empresa = None
            unidade_nome = None
            os_num = _clean_context_text(getattr(os_obj, 'numero_os', None))
            status_operacao = _clean_context_text(getattr(os_obj, 'status_operacao', None))
            try:
                cliente_obj = getattr(os_obj, 'Cliente', None)
                if cliente_obj is not None:
                    empresa = _clean_context_text(getattr(cliente_obj, 'nome', None) or str(cliente_obj))
            except Exception:
                empresa = None

            try:
                unidade_obj = getattr(os_obj, 'Unidade', None)
                if unidade_obj is not None:
                    unidade_nome = _clean_context_text(getattr(unidade_obj, 'nome', None) or str(unidade_obj))
            except Exception:
                unidade_nome = None

            return {'empresa': empresa, 'unidade': unidade_nome, 'os': os_num, 'status_operacao': status_operacao}

        # Prefetch + ordenacao para evitar N+1 e manter sequencia consistente
        try:
            qs = qs.select_related('ordem_servico').prefetch_related('tanques').order_by('data', 'pk')
        except Exception:
            qs = qs.order_by('data', 'pk')

        tank_labels = {}
        tank_records = defaultdict(list)  # tank_key -> [(date, rdo_pk, day_str, reading)]
        # Mantemos duas visoes de progresso para evitar "falta 100%" inconsistente:
        # - latest_any: ultimo valor observado (inclusive 0)
        # - max_positive: maior valor positivo observado no periodo
        tank_progress_latest_any = {}     # tank_key -> {'done_percent': x, 'as_of': 'YYYY-MM-DD', _sort_*}
        tank_progress_max_positive = {}   # tank_key -> {'done_percent': x, 'as_of': 'YYYY-MM-DD', _sort_*}
        tank_context_latest = {}          # tank_key -> {'empresa': x, 'unidade': y, 'os': z, 'as_of': 'YYYY-MM-DD', _sort_*}

        for rdo in qs:
            try:
                if not getattr(rdo, 'data', None):
                    continue
                d = rdo.data.strftime('%Y-%m-%d')
                rdo_pk = int(getattr(rdo, 'pk', 0) or 0)

                # Dedup no mesmo RDO: para o mesmo tanque, manter maior leitura do dia
                rdo_tank_values = {}

                try:
                    if hasattr(rdo, 'tanques'):
                        for rt in rdo.tanques.all():
                            try:
                                raw_label = _resolve_tank_label(rt, rdo) or _fallback_label_for_rdo(rdo)
                                tank_key = _canonical_tank_key(raw_label)
                                if not tank_key:
                                    continue
                                if tank_key not in tank_labels:
                                    tank_labels[tank_key] = _display_tank_label(raw_label)

                                cur_sort = (rdo.data, rdo_pk)
                                ctx = _extract_os_context(rdo)
                                if any(ctx.get(k) for k in ('empresa', 'unidade', 'os', 'status_operacao')):
                                    prev_ctx = tank_context_latest.get(tank_key)
                                    prev_ctx_sort = (
                                        prev_ctx.get('_sort_date') if isinstance(prev_ctx, dict) else None,
                                        prev_ctx.get('_sort_pk') if isinstance(prev_ctx, dict) else None,
                                    )
                                    if not prev_ctx or cur_sort >= prev_ctx_sort:
                                        tank_context_latest[tank_key] = {
                                            'empresa': ctx.get('empresa'),
                                            'unidade': ctx.get('unidade'),
                                            'os': ctx.get('os'),
                                            'status_operacao': ctx.get('status_operacao'),
                                            'as_of': d,
                                            '_sort_date': rdo.data,
                                            '_sort_pk': rdo_pk,
                                        }

                                progress_done = _to_percent_value(getattr(rt, 'percentual_avanco_cumulativo', None))
                                if progress_done is not None:
                                    prev_any = tank_progress_latest_any.get(tank_key)
                                    prev_any_sort = (
                                        prev_any.get('_sort_date') if isinstance(prev_any, dict) else None,
                                        prev_any.get('_sort_pk') if isinstance(prev_any, dict) else None,
                                    )
                                    if not prev_any or cur_sort >= prev_any_sort:
                                        tank_progress_latest_any[tank_key] = {
                                            'done_percent': float(progress_done),
                                            'as_of': d,
                                            '_sort_date': rdo.data,
                                            '_sort_pk': rdo_pk,
                                        }

                                    if float(progress_done) > 0:
                                        prev_pos = tank_progress_max_positive.get(tank_key)
                                        prev_pos_val = float(prev_pos.get('done_percent', 0.0) or 0.0) if isinstance(prev_pos, dict) else 0.0
                                        prev_pos_sort = (
                                            prev_pos.get('_sort_date') if isinstance(prev_pos, dict) else None,
                                            prev_pos.get('_sort_pk') if isinstance(prev_pos, dict) else None,
                                        )
                                        should_replace_pos = False
                                        if not prev_pos:
                                            should_replace_pos = True
                                        elif float(progress_done) > (prev_pos_val + 1e-9):
                                            should_replace_pos = True
                                        elif abs(float(progress_done) - prev_pos_val) <= 1e-9 and cur_sort >= prev_pos_sort:
                                            should_replace_pos = True

                                        if should_replace_pos:
                                            tank_progress_max_positive[tank_key] = {
                                                'done_percent': float(progress_done),
                                                'as_of': d,
                                                '_sort_date': rdo.data,
                                                '_sort_pk': rdo_pk,
                                            }

                                reading = _volume_bombeado_m3(rt)
                                if reading <= 0:
                                    continue

                                prev_reading = rdo_tank_values.get(tank_key, 0.0)
                                if reading > prev_reading:
                                    rdo_tank_values[tank_key] = reading
                            except Exception:
                                continue
                except Exception:
                    pass

                for tank_key, reading in rdo_tank_values.items():
                    tank_records[tank_key].append((rdo.data, rdo_pk, d, float(reading)))
            except Exception:
                continue

        def _infer_series_mode(records):
            # Detecta serie cumulativa para evitar soma duplicada em leituras repetidas.
            if not records or len(records) < 2:
                return 'daily'
            vals = [float(rec[3] or 0) for rec in records]
            transitions = len(vals) - 1
            if transitions <= 0:
                return 'daily'
            non_decreasing = 0
            for idx in range(1, len(vals)):
                if vals[idx] >= (vals[idx - 1] - 1e-9):
                    non_decreasing += 1
            monotonic_ratio = float(non_decreasing) / float(transitions)
            max_val = max(vals) if vals else 0.0
            span = (max(vals) - min(vals)) if vals else 0.0
            if monotonic_ratio >= 0.8 and (max_val > 24.0 or span > 12.0):
                return 'cumulative'
            return 'daily'

        by_day_tank = defaultdict(lambda: defaultdict(float))
        tank_totals = defaultdict(float)
        total_by_day = defaultdict(float)

        for tank_key, records in tank_records.items():
            recs = sorted(records, key=lambda row: (row[0], row[1]))
            mode = _infer_series_mode(recs)
            prev_val = None
            for _, __, day_str, reading in recs:
                added = 0.0
                if mode == 'cumulative':
                    if prev_val is None:
                        added = reading
                    else:
                        delta = reading - prev_val
                        if delta > 0:
                            added = delta
                        elif delta < 0:
                            # reset do contador cumulativo
                            added = reading
                        else:
                            # leitura repetida nao deve duplicar KPI
                            added = 0.0
                    prev_val = reading
                else:
                    added = reading

                if added > 0:
                    by_day_tank[day_str][tank_key] += float(added)
                    tank_totals[tank_key] += float(added)
                    total_by_day[day_str] += float(added)

        days = []
        cur = start
        while cur <= end:
            ds = cur.strftime('%Y-%m-%d')
            days.append(ds)
            cur = cur + td(days=1)

        sorted_tanks = sorted(tank_totals.items(), key=lambda x: x[1], reverse=True)
        visible_tanks = [tk for tk, _ in sorted_tanks]
        hidden_tanks_count = 0
        hidden_tanks_total = 0.0

        datasets = []
        for tank_key in visible_tanks:
            series = [float(by_day_tank.get(ds, {}).get(tank_key, 0) or 0) for ds in days]
            datasets.append({
                'label': str(tank_labels.get(tank_key, tank_key).strip() or tank_key),
                'data': series,
                'type': 'bar'
            })

        leader_label = '--'
        leader_total = 0.0
        if sorted_tanks:
            leader_key, leader_val = sorted_tanks[0]
            leader_label = str(tank_labels.get(leader_key, leader_key).strip() or leader_key)
            leader_total = float(leader_val or 0)

        tank_progress_by_label = {}
        for tank_key in tank_labels.keys():
            progress = tank_progress_max_positive.get(tank_key) or tank_progress_latest_any.get(tank_key)
            if not isinstance(progress, dict):
                continue
            done_percent = float(progress.get('done_percent', 0.0) or 0.0)
            tank_total = float(tank_totals.get(tank_key, 0.0) or 0.0)
            # Se houve uso da bomba no periodo e o avanço ficou zerado,
            # tratamos como dado de avanço indisponivel (evita "falta 100%").
            if tank_total > 0 and done_percent <= 0:
                continue
            label = str(tank_labels.get(tank_key, tank_key).strip() or tank_key)
            tank_progress_by_label[label] = {
                'done_percent': done_percent,
                'remaining_percent': float(round(max(0.0, 100.0 - done_percent), 2)),
                'as_of': progress.get('as_of')
            }

        tank_context_by_label = {}
        for tank_key, ctx in tank_context_latest.items():
            if not isinstance(ctx, dict):
                continue
            label = str(tank_labels.get(tank_key, tank_key).strip() or tank_key)
            tank_context_by_label[label] = {
                'empresa': ctx.get('empresa'),
                'unidade': ctx.get('unidade'),
                'os': ctx.get('os'),
                'status_operacao': ctx.get('status_operacao'),
                'as_of': ctx.get('as_of'),
            }

        resp = {
            'success': True,
            'labels': days,
            'datasets': datasets,
            'meta': {
                'group_by': 'tanque',
                'selection_mode': 'all_tanks',
                'max_visible_tanks': len(visible_tanks),
                'min_visible_tanks': len(visible_tanks),
                'coverage_target': 1.0,
                'os_status_scope': os_status_scope,
                'metric_unit': 'm3',
                'metric_label': 'volume_bombeado',
                'total_tanks': len(sorted_tanks),
                'visible_tanks': len(visible_tanks),
                'hidden_tanks_count': hidden_tanks_count,
                'hidden_tanks_total': float(hidden_tanks_total),
                'has_hidden_tanks': bool(hidden_tanks_count),
                'total_series_all': [float(total_by_day.get(ds, 0) or 0) for ds in days],
                'tank_progress': tank_progress_by_label,
                'tank_context': tank_context_by_label,
                'leader': {
                    'label': leader_label,
                    'total': leader_total
                }
            },
            'options': {
                'scales': {
                    'x': {
                        'grid': {
                            'display': True,
                            'color': 'rgba(200, 200, 200, 0.2)'
                        }
                    },
                    'y': {
                        'grid': {
                            'display': True,
                            'color': 'rgba(200, 200, 200, 0.2)'
                        }
                    }
                }
            }
        }
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required(login_url='/login/')
@require_GET
def rdo_residuos_liquido_por_dia(request):
    try:
        from .models import RdoTanque
        from collections import Counter

        qs, start, end = _dashboard_filtered_rdo_qs(request)
        rdo_rows = list(qs.order_by('data', 'id'))
        counter = Counter()

        def _to_float_safe(v):
            try:
                return float(v or 0)
            except Exception:
                return 0.0

        def _normalize_volume(v):
            f = _to_float_safe(v)
            if abs(f) > 100:
                try:
                    return f / 1000.0
                except Exception:
                    return f
            return f

        def _rt_liquido_diario(row):
            t_total = _to_float_safe(row.get('total_liquido'))
            t_bombeio = _to_float_safe(row.get('bombeio'))
            if t_total != 0:
                return _normalize_volume(t_total)
            if t_bombeio != 0:
                return _normalize_volume(t_bombeio)
            t_tot = _to_float_safe(row.get('residuos_totais'))
            t_sol = _to_float_safe(row.get('residuos_solidos'))
            if t_tot != 0 or t_sol != 0:
                return _normalize_volume(t_tot - t_sol)
            return 0.0

        rdo_date_by_id = {}
        rdo_ids = []
        for rdo in rdo_rows:
            rid = getattr(rdo, 'id', None)
            d = getattr(rdo, 'data', None)
            if rid and d:
                rdo_ids.append(rid)
                rdo_date_by_id[rid] = d.strftime('%Y-%m-%d')

        rt_rows = list(
            RdoTanque.objects.filter(rdo_id__in=rdo_ids).values(
                'rdo_id',
                'total_liquido',
                'bombeio',
                'residuos_totais',
                'residuos_solidos',
            )
        ) if rdo_ids else []
        for row in rt_rows:
            day = rdo_date_by_id.get(row.get('rdo_id'))
            if not day:
                continue
            counter[day] += _rt_liquido_diario(row)
        source_used = 'RdoTanque(total_liquido|bombeio|residuos)'

        days = []
        values = []
        cur = start
        while cur <= end:
            ds = cur.strftime('%Y-%m-%d')
            days.append(ds)
            values.append(counter.get(ds, 0))
            cur = cur + timedelta(days=1)
        
        resp = {
            'success': True,
            'labels': days,
            'datasets': [{
                'label': 'M³ resíduo líquido',
                'data': values,
                'backgroundColor': '#3498db',
                'borderColor': '#2980b9'
            }],
            'debug': {
                'source_used': source_used,
                'rdo_count': len(rdo_rows),
                'rt_count': len(rt_rows),
            },
            'options': {
                'scales': {
                    'x': {
                        'grid': {
                            'display': True,
                            'color': 'rgba(200, 200, 200, 0.2)'
                        }
                    },
                    'y': {
                        'grid': {
                            'display': True,
                            'color': 'rgba(200, 200, 200, 0.2)'
                        }
                    }
                }
            }
        }
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required(login_url='/login/')
@require_GET
def rdo_residuos_solido_por_dia(request):
    try:
        from .models import RDO
        from datetime import timedelta as td
        
        start_str = request.GET.get('start')
        end_str = request.GET.get('end')
        supervisor = request.GET.get('supervisor')
        tanque = request.GET.get('tanque')
        cliente = request.GET.get('cliente')
        unidade = request.GET.get('unidade')
        os_existente = request.GET.get('os_existente')
        os_existente = request.GET.get('os_existente')
        
        if end_str:
            end = datetime.strptime(end_str, '%Y-%m-%d').date()
        else:
            end = datetime.today().date()
        if start_str:
            start = datetime.strptime(start_str, '%Y-%m-%d').date()
        else:
            start = end - td(days=29)
        
        qs = RDO.objects.filter(data__gte=start, data__lte=end)
        if supervisor:
            qs = qs.filter(ordem_servico__supervisor__username=supervisor)
        if tanque:
            qs = qs.filter(
                Q(nome_tanque__icontains=tanque) |
                Q(tanque_codigo__icontains=tanque) |
                Q(tanques__tanque_codigo__icontains=tanque)
            ).distinct()
        if cliente:
            qs = qs.filter(ordem_servico__Cliente__nome__icontains=cliente)
        if unidade:
            qs = qs.filter(ordem_servico__Unidade__nome__icontains=unidade)
        if os_existente:
            qs = apply_os_filter_generic(qs, os_existente)
        
        from collections import defaultdict
        counter = defaultdict(float)
        
        for rdo in qs:
            try:
                if rdo.data:
                    d = rdo.data.strftime('%Y-%m-%d')
                    solido = float(getattr(rdo, 'total_solidos', 0) or 0)
                    counter[d] += solido
            except Exception:
                pass
        
        days = []
        values = []
        cur = start
        while cur <= end:
            ds = cur.strftime('%Y-%m-%d')
            days.append(ds)
            values.append(counter.get(ds, 0))
            cur = cur + td(days=1)
        
        resp = {
            'success': True,
            'labels': days,
            'datasets': [{
                'label': 'M³ resíduo sólido',
                'data': values,
                'backgroundColor': '#f39c12',
                'borderColor': '#e67e22'
            }],
            'options': {
                'scales': {
                    'x': {
                        'grid': {
                            'display': True,
                            'color': 'rgba(200, 200, 200, 0.2)'
                        }
                    },
                    'y': {
                        'grid': {
                            'display': True,
                            'color': 'rgba(200, 200, 200, 0.2)'
                        }
                    }
                }
            }
        }
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required(login_url='/login/')
@require_GET
def rdo_liquido_por_supervisor(request):
    try:
        from .models import RDO
        from datetime import timedelta as td
        
        start_str = request.GET.get('start')
        end_str = request.GET.get('end')
        cliente = request.GET.get('cliente')
        unidade = request.GET.get('unidade')
        os_existente = request.GET.get('os_existente')
        os_existente = request.GET.get('os_existente')
        
        if end_str:
            end = datetime.strptime(end_str, '%Y-%m-%d').date()
        else:
            end = datetime.today().date()
        if start_str:
            start = datetime.strptime(start_str, '%Y-%m-%d').date()
        else:
            start = end - td(days=29)
        
        qs = RDO.objects.filter(data__gte=start, data__lte=end)
        if cliente:
            qs = qs.filter(ordem_servico__Cliente__nome__icontains=cliente)
        if unidade:
            qs = qs.filter(ordem_servico__Unidade__nome__icontains=unidade)
        if os_existente:
            qs = apply_os_filter_generic(qs, os_existente)
        
        User = get_user_model()
        supervisores = User.objects.filter(ordens_supervisionadas__rdos__isnull=False).distinct()
        
        labels = []
        values = []
        
        for sup in supervisores:
            rdo_list = qs.filter(ordem_servico__supervisor=sup)
            soma_liquido = 0.0
            def _to_float_safe_local(x):
                try:
                    return float(x or 0)
                except Exception:
                    return 0.0

            def _normalize_volume_local(v):
                f = _to_float_safe_local(v)
                if abs(f) > 100:
                    try:
                        return f / 1000.0
                    except Exception:
                        return f
                return f

            for r in rdo_list:
                try:
                    t_total = _to_float_safe_local(getattr(r, 'total_liquido', None))
                    t_bombeio = _to_float_safe_local(getattr(r, 'bombeio', None))
                    t_quant = _to_float_safe_local(getattr(r, 'quantidade_bombeada', None))

                    # Prioridade: total_liquido > bombeio > quantidade_bombeada
                    if t_total and t_total != 0:
                        soma_liquido += _normalize_volume_local(t_total)
                    elif t_bombeio and t_bombeio != 0:
                        soma_liquido += _normalize_volume_local(t_bombeio)
                    elif t_quant and t_quant != 0:
                        soma_liquido += _normalize_volume_local(t_quant)

                    if soma_liquido == 0:
                        try:
                            r_tot = getattr(r, 'residuos_totais', None) or getattr(r, 'total_residuos', None)
                            r_sol = getattr(r, 'residuos_solidos', None) or getattr(r, 'total_solidos', None)
                            if r_tot is not None or r_sol is not None:
                                soma_liquido += _normalize_volume_local(_to_float_safe_local(r_tot) - _to_float_safe_local(r_sol))
                        except Exception:
                            pass

                    try:
                        if hasattr(r, 'tanques'):
                            for rt in r.tanques.all():
                                rt_total = getattr(rt, 'total_liquido', None)
                                rt_bombeio = getattr(rt, 'bombeio', None)
                                added = 0.0
                                
                                # Prioridade: total_liquido > bombeio
                                if rt_total is not None and float(rt_total or 0) != 0:
                                    added = _normalize_volume_local(rt_total)
                                elif rt_bombeio is not None and float(rt_bombeio or 0) != 0:
                                    added = _normalize_volume_local(rt_bombeio)
                                
                                if added == 0.0:
                                    try:
                                        rt_tot = getattr(rt, 'residuos_totais', None)
                                        rt_sol = getattr(rt, 'residuos_solidos', None)
                                        if rt_tot is not None or rt_sol is not None:
                                            diff = _to_float_safe_local(rt_tot) - _to_float_safe_local(rt_sol)
                                            if diff > 0:
                                                added = _normalize_volume_local(diff)
                                    except Exception:
                                        pass
                                soma_liquido += added
                    except Exception:
                        pass
                except Exception:
                    pass
            
            if soma_liquido > 0:
                sup_name = (sup.get_full_name() if sup.get_full_name() else sup.username)
                labels.append(sup_name)
                values.append(soma_liquido)
        
        resp = {
            'success': True,
            'labels': labels,
            'datasets': [{
                'label': 'M³ líquido removido',
                'data': values,
                'backgroundColor': '#3498db',
                'borderColor': '#2980b9'
            }],
            'options': {
                'scales': {
                    'x': {
                        'grid': {
                            'display': True,
                            'color': 'rgba(200, 200, 200, 0.2)'
                        }
                    },
                    'y': {
                        'beginAtZero': True,
                        'ticks': {
                            'stepSize': 100
                        },
                        'grid': {
                            'display': True,
                            'color': 'rgba(200, 200, 200, 0.2)'
                        }
                    }
                }
            }
        }
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required(login_url='/login/')
@require_GET
def rdo_solido_por_supervisor(request):
    try:
        from .models import RDO
        from datetime import timedelta as td
        
        start_str = request.GET.get('start')
        end_str = request.GET.get('end')
        cliente = request.GET.get('cliente')
        unidade = request.GET.get('unidade')
        os_existente = request.GET.get('os_existente')
        os_existente = request.GET.get('os_existente')
        
        if end_str:
            end = datetime.strptime(end_str, '%Y-%m-%d').date()
        else:
            end = datetime.today().date()
        if start_str:
            start = datetime.strptime(start_str, '%Y-%m-%d').date()
        else:
            start = end - td(days=29)
        
        qs = RDO.objects.filter(data__gte=start, data__lte=end)
        if cliente:
            qs = qs.filter(ordem_servico__Cliente__nome__icontains=cliente)
        if unidade:
            qs = qs.filter(ordem_servico__Unidade__nome__icontains=unidade)
        if os_existente:
            qs = apply_os_filter_generic(qs, os_existente)
        
        User = get_user_model()
        supervisores = User.objects.filter(ordens_supervisionadas__rdos__isnull=False).distinct()
        
        labels = []
        values = []
        
        for sup in supervisores:
            rdo_list = qs.filter(ordem_servico__supervisor=sup)
            soma_solido = sum(float(getattr(r, 'total_solidos', 0) or 0) for r in rdo_list)
            
            sup_name = (sup.get_full_name() if sup.get_full_name() else sup.username)
            labels.append(sup_name)
            values.append(soma_solido)
        
        resp = {
            'success': True,
            'labels': labels,
            'datasets': [{
                'label': 'M³ sólido removido',
                'data': values,
                'backgroundColor': '#f39c12',
                'borderColor': '#e67e22'
            }],
            'options': {
                'scales': {
                    'x': {
                        'grid': {
                            'display': True,
                            'color': 'rgba(200, 200, 200, 0.2)'
                        }
                    },
                    'y': {
                        'beginAtZero': True,
                        'grid': {
                            'display': True,
                            'color': 'rgba(200, 200, 200, 0.2)'
                        }
                    }
                }
            }
        }
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required(login_url='/login/')
@require_GET
def rdo_volume_por_tanque(request):
    try:
        from .models import RDO
        from datetime import timedelta as td
        
        start_str = request.GET.get('start')
        end_str = request.GET.get('end')
        supervisor = request.GET.get('supervisor')
        cliente = request.GET.get('cliente')
        unidade = request.GET.get('unidade')
        os_existente = request.GET.get('os_existente')
        os_existente = request.GET.get('os_existente')
        tanque = request.GET.get('tanque')
        
        if end_str:
            end = datetime.strptime(end_str, '%Y-%m-%d').date()
        else:
            end = datetime.today().date()
        if start_str:
            start = datetime.strptime(start_str, '%Y-%m-%d').date()
        else:
            start = end - td(days=29)
        
        qs = RDO.objects.filter(data__gte=start, data__lte=end)
        if supervisor:
            qs = qs.filter(ordem_servico__supervisor__username=supervisor)
        if cliente:
            qs = qs.filter(ordem_servico__Cliente__nome__icontains=cliente)
        if unidade:
            qs = qs.filter(ordem_servico__Unidade__nome__icontains=unidade)
        if os_existente:
            qs = apply_os_filter_generic(qs, os_existente)
        if tanque:
            qs = qs.filter(
                Q(nome_tanque__icontains=tanque) |
                Q(tanque_codigo__icontains=tanque) |
                Q(tanques__tanque_codigo__icontains=tanque)
            ).distinct()
        
        from collections import defaultdict
        import re

        tanques_dict = defaultdict(float)

        def _clean_tank_label(val):
            try:
                if val is None:
                    return None
                s = str(val).strip()
                if not s:
                    return None
                low = s.casefold()
                invalid = {
                    '-', '—', 'none', 'null', 'n/a', 'na',
                    'desconhecido', 'unknown', 'a definir',
                    'sem tanque', 'sem identificacao', 'sem identificação'
                }
                if low in invalid:
                    return None
                return s
            except Exception:
                return None

        def _pick_os_tank_label(os_obj):
            if os_obj is None:
                return None
            direct = _clean_tank_label(getattr(os_obj, 'tanque', None))
            if direct:
                return direct
            raw_multi = getattr(os_obj, 'tanques', None)
            if raw_multi not in (None, ''):
                for token in re.split(r'[;,|/]+', str(raw_multi)):
                    cleaned = _clean_tank_label(token)
                    if cleaned:
                        return cleaned
            return None

        def _resolve_tank_label(rt_obj, rdo_obj):
            if rt_obj is not None:
                for cand in (
                    getattr(rt_obj, 'tanque_codigo', None),
                    getattr(rt_obj, 'nome_tanque', None),
                ):
                    cleaned = _clean_tank_label(cand)
                    if cleaned:
                        return cleaned
            if rdo_obj is not None:
                for cand in (
                    getattr(rdo_obj, 'tanque_codigo', None),
                    getattr(rdo_obj, 'nome_tanque', None),
                ):
                    cleaned = _clean_tank_label(cand)
                    if cleaned:
                        return cleaned
                return _pick_os_tank_label(getattr(rdo_obj, 'ordem_servico', None))
            return None

        def _fallback_label_for_rdo(rdo_obj):
            os_obj = getattr(rdo_obj, 'ordem_servico', None) if rdo_obj is not None else None
            os_num = getattr(os_obj, 'numero_os', None) if os_obj is not None else None
            if os_num not in (None, ''):
                return f"OS {os_num}"
            rid = getattr(rdo_obj, 'id', None)
            if rid not in (None, ''):
                return f"RDO {rid}"
            return 'Sem identificacao'

        for rdo in qs:
            try:
                added = False
                if hasattr(rdo, 'tanques'):
                    for rt in rdo.tanques.all():
                        try:
                            tank_label = _resolve_tank_label(rt, rdo)
                            if not tank_label:
                                continue

                            vol = 0.0
                            # Prioridade: total_liquido > bombeio
                            try:
                                vol = float(getattr(rt, 'total_liquido', None) or 0)
                                if vol == 0:
                                    vol = float(getattr(rt, 'bombeio', None) or 0)
                            except Exception:
                                vol = 0.0
                            if vol == 0:
                                try:
                                    rt_tot = getattr(rt, 'residuos_totais', None)
                                    rt_sol = getattr(rt, 'residuos_solidos', None)
                                    if rt_tot is not None or rt_sol is not None:
                                        vol = float(rt_tot or 0) - float(rt_sol or 0)
                                except Exception:
                                    pass
                            tanques_dict[tank_label] += vol
                            added = True
                        except Exception:
                            pass

                if not added:
                    tank_label = _resolve_tank_label(None, rdo) or _fallback_label_for_rdo(rdo)
                    vol = 0.0
                    # Prioridade: total_liquido > bombeio > quantidade_bombeada
                    try:
                        val = float(getattr(rdo, 'total_liquido', None) or 0)
                        if val == 0:
                            val = float(getattr(rdo, 'bombeio', None) or 0)
                        if val == 0:
                            val = float(getattr(rdo, 'quantidade_bombeada', 0) or 0)
                        vol += val
                    except Exception:
                        pass
                    if vol == 0:
                        try:
                            r_tot = getattr(rdo, 'residuos_totais', None) or getattr(rdo, 'total_residuos', None)
                            r_sol = getattr(rdo, 'residuos_solidos', None) or getattr(rdo, 'total_solidos', None)
                            if r_tot is not None or r_sol is not None:
                                vol = float(r_tot or 0) - float(r_sol or 0)
                        except Exception:
                            pass

                    tanques_dict[tank_label] += vol
            except Exception:
                pass
        
        top_tanques = sorted(tanques_dict.items(), key=lambda x: x[1], reverse=True)[:10]
        
        labels = [t[0] for t in top_tanques]
        values = [t[1] for t in top_tanques]
        
        resp = {
            'success': True,
            'labels': labels,
            'datasets': [{
                'label': 'Volume por tanque (M³)',
                'data': values,
                'backgroundColor': '#16a085',
                'borderColor': '#117a65'
            }],
            'options': {
                'scales': {
                    'x': {
                        'grid': {
                            'display': True,
                            'color': 'rgba(200, 200, 200, 0.2)'
                        }
                    },
                    'y': {
                        'grid': {
                            'display': True,
                            'color': 'rgba(200, 200, 200, 0.2)'
                        }
                    }
                }
            }
        }
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required(login_url='/login/')
@require_GET
def backlog_por_coordenador(request):
    try:
        top_n = 5

        start, end = _dashboard_rdo_period(request)
        period_q = (
            Q(data_inicio__gte=start, data_inicio__lte=end) |
            Q(data_inicio_frente__gte=start, data_inicio_frente__lte=end) |
            Q(data_fim__gte=start, data_fim__lte=end) |
            Q(data_fim_frente__gte=start, data_fim_frente__lte=end)
        )

        qs = OrdemServico.objects.all()
        qs = _apply_dashboard_os_common_filters(qs, request)
        qs = qs.filter(period_q)

        rep_ids_qs = qs.values('numero_os').annotate(rep_id=Min('id'))
        rep_ids = [r['rep_id'] for r in rep_ids_qs if r.get('rep_id')]
        base_qs = OrdemServico.objects.filter(id__in=rep_ids) if rep_ids else OrdemServico.objects.none()

        rows = list(
            base_qs.values('coordenador')
            .annotate(
                programada=Count('id', filter=Q(status_operacao__iexact='Programada')),
                em_andamento=Count('id', filter=Q(status_operacao__iexact='Em Andamento')),
                paralizada=Count('id', filter=Q(status_operacao__iexact='Paralizada')),
                finalizada=Count('id', filter=Q(status_operacao__iexact='Finalizada')),
                cancelada=Count('id', filter=Q(status_operacao__iexact='Cancelada')),
                total=Count('id'),
            )
        )

        rows = [row for row in rows if not _dashboard_coord_is_excluded(row.get('coordenador'))]
        rows = sorted(rows, key=lambda r: (-(int(r.get('total') or 0)), str(r.get('coordenador') or '').lower()))
        rows = rows[:top_n]

        labels = []
        data_programada = []
        data_andamento = []
        data_paralizada = []
        data_finalizada = []
        data_cancelada = []

        for row in rows:
            label_raw = str(row.get('coordenador') or '').strip() or 'Sem Coordenador'
            label = label_raw if len(label_raw) <= 48 else (label_raw[:45] + '...')
            labels.append(label)
            data_programada.append(int(row.get('programada') or 0))
            data_andamento.append(int(row.get('em_andamento') or 0))
            data_paralizada.append(int(row.get('paralizada') or 0))
            data_finalizada.append(int(row.get('finalizada') or 0))
            data_cancelada.append(int(row.get('cancelada') or 0))

        return JsonResponse({
            'success': True,
            'labels': labels,
            'programada': data_programada,
            'em_andamento': data_andamento,
            'paralizada': data_paralizada,
            'finalizada': data_finalizada,
            'cancelada': data_cancelada,
            'period': {
                'start': start.strftime('%Y-%m-%d'),
                'end': end.strftime('%Y-%m-%d'),
            },
            'top_n': top_n,
            'total_coordenadores': len(labels),
        })
    except Exception as e:
        logging.exception('Erro em backlog_por_coordenador')
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required(login_url='/login/')
@require_GET
def entrada_saida_semanal_coordenador(request):
    try:
        top_n = 5

        start, end = _dashboard_rdo_period(request)
        period_days = max(1, (end - start).days + 1)
        weeks_equivalent = max(1.0, float(period_days) / 7.0)

        qs = OrdemServico.objects.all()
        qs = _apply_dashboard_os_common_filters(qs, request)

        rep_ids_qs = qs.values('numero_os').annotate(rep_id=Min('id'))
        rep_ids = [r['rep_id'] for r in rep_ids_qs if r.get('rep_id')]
        base_qs = OrdemServico.objects.filter(id__in=rep_ids) if rep_ids else OrdemServico.objects.none()

        rows = list(
            base_qs.values('coordenador')
            .annotate(
                entradas=Count(
                    'id',
                    filter=(
                        Q(data_inicio__gte=start, data_inicio__lte=end) |
                        Q(data_inicio_frente__gte=start, data_inicio_frente__lte=end)
                    )
                ),
                saidas=Count(
                    'id',
                    filter=(
                        Q(status_operacao__iexact='Finalizada') &
                        (
                            Q(data_fim__gte=start, data_fim__lte=end) |
                            Q(data_fim_frente__gte=start, data_fim_frente__lte=end)
                        )
                    )
                ),
            )
        )

        items = []
        for row in rows:
            entradas = int(row.get('entradas') or 0)
            saidas = int(row.get('saidas') or 0)
            if entradas <= 0 and saidas <= 0:
                continue

            coord_raw = str(row.get('coordenador') or '').strip() or 'Sem Coordenador'
            coord_label = coord_raw if len(coord_raw) <= 48 else (coord_raw[:45] + '...')
            entradas_semanais = round(float(entradas) / weeks_equivalent, 2)
            saidas_semanais = round(float(saidas) / weeks_equivalent, 2)
            saldo_semanal = round(saidas_semanais - entradas_semanais, 2)
            items.append({
                'label': coord_label,
                'entradas': entradas,
                'saidas': saidas,
                'entradas_semanais': entradas_semanais,
                'saidas_semanais': saidas_semanais,
                'saldo_semanal': saldo_semanal,
                'mov_total': entradas + saidas,
            })

        items.sort(key=lambda it: (-int(it.get('mov_total') or 0), str(it.get('label') or '').lower()))
        items = items[:top_n]

        return JsonResponse({
            'success': True,
            'labels': [it['label'] for it in items],
            'entradas_semanais': [it['entradas_semanais'] for it in items],
            'saidas_semanais': [it['saidas_semanais'] for it in items],
            'saldo_semanal': [it['saldo_semanal'] for it in items],
            'entradas_total': [it['entradas'] for it in items],
            'saidas_total': [it['saidas'] for it in items],
            'weeks_equivalent': round(weeks_equivalent, 2),
            'period_days': int(period_days),
            'period': {
                'start': start.strftime('%Y-%m-%d'),
                'end': end.strftime('%Y-%m-%d'),
            },
            'top_n': top_n,
            'total_coordenadores': len(items),
        })
    except Exception as e:
        logging.exception('Erro em entrada_saida_semanal_coordenador')
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required(login_url='/login/')
@require_GET
def taxa_conclusao_coordenador(request):
    try:
        top_n = 5

        start, end = _dashboard_rdo_period(request)
        period_q = (
            Q(data_inicio__gte=start, data_inicio__lte=end) |
            Q(data_inicio_frente__gte=start, data_inicio_frente__lte=end) |
            Q(data_fim__gte=start, data_fim__lte=end) |
            Q(data_fim_frente__gte=start, data_fim_frente__lte=end)
        )

        qs = OrdemServico.objects.all()
        qs = _apply_dashboard_os_common_filters(qs, request)
        qs = qs.filter(period_q)

        rep_ids_qs = qs.values('numero_os').annotate(rep_id=Min('id'))
        rep_ids = [r['rep_id'] for r in rep_ids_qs if r.get('rep_id')]
        base_qs = OrdemServico.objects.filter(id__in=rep_ids) if rep_ids else OrdemServico.objects.none()

        rows = list(
            base_qs.values('coordenador')
            .annotate(
                finalizada=Count('id', filter=Q(status_operacao__iexact='Finalizada')),
                em_andamento=Count('id', filter=Q(status_operacao__iexact='Em Andamento')),
                programada=Count('id', filter=Q(status_operacao__iexact='Programada')),
                paralizada=Count('id', filter=Q(status_operacao__iexact='Paralizada')),
                cancelada=Count('id', filter=Q(status_operacao__iexact='Cancelada')),
                total=Count('id'),
            )
        )

        items = []
        for row in rows:
            if _dashboard_coord_is_excluded(row.get('coordenador')):
                continue
            fin = int(row.get('finalizada') or 0)
            andm = int(row.get('em_andamento') or 0)
            base_metric = fin + andm
            if base_metric <= 0:
                continue
            taxa = (float(fin) / float(base_metric)) * 100.0
            coord_raw = str(row.get('coordenador') or '').strip() or 'Sem Coordenador'
            coord_label = coord_raw if len(coord_raw) <= 48 else (coord_raw[:45] + '...')
            items.append({
                'label': coord_label,
                'taxa_conclusao': round(float(taxa), 2),
                'finalizada': fin,
                'em_andamento': andm,
                'base_metric': base_metric,
                'programada': int(row.get('programada') or 0),
                'paralizada': int(row.get('paralizada') or 0),
                'cancelada': int(row.get('cancelada') or 0),
                'total': int(row.get('total') or 0),
            })

        items.sort(
            key=lambda it: (
                -(float(it.get('taxa_conclusao') or 0.0)),
                -(int(it.get('base_metric') or 0)),
                str(it.get('label') or '').lower(),
            )
        )
        items = items[:top_n]

        base_total = sum(int(it.get('base_metric') or 0) for it in items)
        concl_total = sum(int(it.get('finalizada') or 0) for it in items)
        taxa_ponderada = round((float(concl_total) / float(base_total) * 100.0), 2) if base_total > 0 else 0.0

        return JsonResponse({
            'success': True,
            'labels': [it['label'] for it in items],
            'taxa_conclusao': [it['taxa_conclusao'] for it in items],
            'finalizada': [it['finalizada'] for it in items],
            'em_andamento': [it['em_andamento'] for it in items],
            'base_metric': [it['base_metric'] for it in items],
            'programada': [it['programada'] for it in items],
            'paralizada': [it['paralizada'] for it in items],
            'cancelada': [it['cancelada'] for it in items],
            'total': [it['total'] for it in items],
            'taxa_ponderada': taxa_ponderada,
            'period': {
                'start': start.strftime('%Y-%m-%d'),
                'end': end.strftime('%Y-%m-%d'),
            },
            'top_n': top_n,
            'total_coordenadores': len(items),
            'formula': 'taxa_conclusao = finalizadas / (finalizadas + em_andamento) * 100',
        })
    except Exception as e:
        logging.exception('Erro em taxa_conclusao_coordenador')
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required(login_url='/login/')
def rdo_dashboard_view(request):
    try:
        from .models import Cliente, Unidade, RDO, RdoTanque
        
        clientes = Cliente.objects.all().order_by('nome')
        unidades = Unidade.objects.all().order_by('nome')
        supervisores = (
            get_user_model()
            .objects
            .filter(ordens_supervisionadas__isnull=False)
            .exclude(
                Q(username__icontains='a definir') |
                Q(first_name__icontains='a definir') |
                Q(last_name__icontains='a definir')
            )
            .distinct()
            .order_by('first_name', 'last_name', 'username')
        )
        
        escopos = RDO.objects.filter(servico_exec__isnull=False).values_list('servico_exec', flat=True).distinct()
        
        tanques_from_rt = list(RdoTanque.objects.filter(tanque_codigo__isnull=False).values_list('tanque_codigo', flat=True).distinct())
        tanques_from_rdo = list(RDO.objects.filter(nome_tanque__isnull=False).values_list('nome_tanque', flat=True).distinct())
        tanques_set = []
        for t in tanques_from_rt + tanques_from_rdo:
            if t is None:
                continue
            t_str = str(t).strip()
            if not t_str:
                continue
            if t_str not in tanques_set:
                tanques_set.append(t_str)
        tanques = sorted(tanques_set)
        
        def remove_accents_norm(s):
            try:
                import unicodedata
                s2 = unicodedata.normalize('NFKD', s)
                return ''.join([c for c in s2 if not unicodedata.combining(c)])
            except Exception:
                return s

        def tokenize_name(s):
            s = remove_accents_norm(s).upper()
            for ch in ".,;:\/()[]{}-'\"`":
                s = s.replace(ch, ' ')
            tokens = [t.strip() for t in s.split() if t.strip()]
            fillers = {'DE','DA','DO','DOS','DAS','E','THE','LE','LA'}
            tokens = [t for t in tokens if t not in fillers]
            suffixes = {'JUNIOR','JR','FILHO','NETO','SNR','SR','II','III','IV'}
            if tokens and tokens[-1] in suffixes:
                tokens = tokens[:-1]
            return tokens

        def tokens_equivalent(a, b):
            if not a or not b:
                return False
            set_a = set(a)
            set_b = set(b)
            if set_a == set_b:
                return True
            if set_a.issubset(set_b) or set_b.issubset(set_a):
                return True
            match = 0
            total = max(len(a), len(b))
            for tok in a:
                if tok in set_b:
                    match += 1
                    continue
                if len(tok) == 1:
                    if any(bt.startswith(tok) for bt in b):
                        match += 1
                        continue
                if any(bt.startswith(tok) or tok.startswith(bt) for bt in b):
                    match += 1
            for tok in b:
                if tok in set_a:
                    continue
                if len(tok) == 1 and any(at.startswith(tok) for at in a):
                    continue
            return (match / float(total)) >= 0.6

        coordenadores_qs = OrdemServico.objects.values_list('coordenador', flat=True)

        try:
            from .models import CoordenadorCanonical
            canon_list = list(CoordenadorCanonical.objects.all())
        except Exception:
            canon_list = []

        canon_variants = []
        for c in canon_list:
            variants = []
            try:
                variants = list(c.variants or [])
            except Exception:
                variants = []
            variants.insert(0, c.canonical_name)
            toks_group = []
            for v in variants:
                try:
                    vt = tokenize_name(str(v))
                    if vt:
                        toks_group.append(vt)
                except Exception:
                    continue
            if toks_group:
                canon_variants.append((c.canonical_name, toks_group))

        raw_list = [str(x).strip() for x in coordenadores_qs if x and str(x).strip()]
        unique_raw = []
        seen_raw_ci = set()
        for r in raw_list:
            kc = r.casefold()
            if kc not in seen_raw_ci:
                seen_raw_ci.add(kc)
                unique_raw.append(r)

        clusters = []

        canon_token_groups = []
        for canonical_name, variants_tokens in canon_variants:
            toks_groups = variants_tokens
            canon_token_groups.append((canonical_name, toks_groups))

        for s in unique_raw:
            toks = tokenize_name(s)
            if not toks:
                continue

            mapped = None
            for canonical_name, toks_groups in canon_token_groups:
                matched = False
                for vt in toks_groups:
                    try:
                        if tokens_equivalent(toks, vt):
                            mapped = canonical_name
                            matched = True
                            break
                    except Exception:
                        continue
                if matched:
                    break

            if mapped:
                found = None
                for cl in clusters:
                    if cl.get('canonical') == mapped or (cl.get('leader') and cl['leader'].casefold() == mapped.casefold()):
                        found = cl
                        break
                if not found:
                    found = {'canonical': mapped, 'leader': mapped, 'tokens': tokenize_name(mapped), 'members': []}
                    clusters.append(found)
                found['members'].append(s)
                continue

            placed = False
            for cl in clusters:
                try:
                    if tokens_equivalent(toks, cl['tokens']):
                        cl['members'].append(s)
                        if len(toks) > len(cl['tokens']):
                            cl['tokens'] = toks
                            cl['leader'] = s
                        placed = True
                        break
                except Exception:
                    continue
            if placed:
                continue

            clusters.append({'leader': s, 'tokens': toks, 'members': [s]})

        result = []
        for cl in clusters:
            if cl.get('canonical'):
                display = cl['canonical']
            else:
                best = None
                best_score = (-1, -1)
                for m in cl['members']:
                    mtoks = tokenize_name(m)
                    score = (len(mtoks), len(m))
                    if score > best_score:
                        best_score = score
                        best = m
                display = best or cl.get('leader')
            if display:
                try:
                    display_norm = display.title()
                except Exception:
                    display_norm = display
                result.append(display_norm)

        try:
            field = OrdemServico._meta.get_field('coordenador')
            field_choices = getattr(field, 'choices', []) or []
            choice_values = [c[0] for c in field_choices if c and c[0]]
            if choice_values:
                coordenadores = sorted(choice_values, key=lambda x: x.casefold())
            else:
                coordenadores = sorted(result, key=lambda x: x.casefold())
        except Exception:
            coordenadores = sorted(result, key=lambda x: x.casefold())
        try:
            statuses = ['Programada', 'Em Andamento', 'Paralizada', 'Finalizada', 'Cancelada']
            rep_ids_qs = OrdemServico.objects.values('numero_os').annotate(rep_id=Min('id'))
            rep_ids = [r['rep_id'] for r in rep_ids_qs if r.get('rep_id')]
            base_qs = OrdemServico.objects.filter(id__in=rep_ids) if rep_ids else OrdemServico.objects.none()
            status_counts = {s: base_qs.filter(status_operacao__iexact=s).count() for s in statuses}
            os_total = base_qs.count()
        except Exception:
            status_counts = {}
            try:
                os_total = OrdemServico.objects.values('numero_os').distinct().count()
            except Exception:
                os_total = 0

        os_programada_count = int(status_counts.get('Programada', 0))
        os_em_andamento_count = int(status_counts.get('Em Andamento', 0))
        os_paralizada_count = int(status_counts.get('Paralizada', 0))
        os_finalizada_count = int(status_counts.get('Finalizada', 0))
        os_cancelada_count = int(status_counts.get('Cancelada', 0))

        try:
            params = {
                'cliente': request.GET.get('cliente'),
                'unidade': request.GET.get('unidade'),
                'start': request.GET.get('start'),
                'end': request.GET.get('end'),
                'os_existente': request.GET.get('os_existente'),
                'supervisor': request.GET.get('supervisor'),
            }
            summaries = summary_operations_data(params)
        except Exception:
            summaries = []

        context = {
            'clientes': clientes,
            'unidades': unidades,
            'supervisores': supervisores,
            'escopos': escopos,
            'tanques': tanques,
            'coordenadores': coordenadores,
            'titulo': 'Dashboard de RDO',
            'os_status_counts': status_counts,
            'os_total': os_total,
            'os_programada_count': os_programada_count,
            'os_em_andamento_count': os_em_andamento_count,
            'os_paralizada_count': os_paralizada_count,
            'os_finalizada_count': os_finalizada_count,
            'os_cancelada_count': os_cancelada_count,
            'summaries': summaries if 'summaries' in locals() else [],
        }
        
        return render(request, 'dashboard_rdo.html', context)
    except Exception as e:
        from django.http import HttpResponse
        return HttpResponse(f'Erro ao carregar dashboard: {str(e)}', status=500)
