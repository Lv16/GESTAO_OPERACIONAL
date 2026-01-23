from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from django.http import JsonResponse
from django.db.models import Count, Avg, Q, Min
from django.db.models.functions import TruncDate
from django.shortcuts import render
from datetime import datetime, timedelta

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
        os_existente = request.GET.get('os_existente')
        
        if end_str:
            end = datetime.strptime(end_str, '%Y-%m-%d').date()
        else:
            end = datetime.today().date()
        if start_str:
            start = datetime.strptime(start_str, '%Y-%m-%d').date()
        else:
            start = end - td(days=29)
        
        from django.db.models import Q
        qs = RDO.objects.filter(
            Q(data_inicio__gte=start, data_inicio__lte=end) |
            Q(data__gte=start, data__lte=end)
        )
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
        
        from collections import Counter
        counter = Counter()
        
        for rdo in qs:
            try:
                d_date = getattr(rdo, 'data', None) or getattr(rdo, 'data_inicio', None)
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
            cur = cur + td(days=1)
        
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
        
        qs = RDO.objects.filter(
            Q(data__gte=start, data__lte=end) | Q(data_inicio__gte=start, data_inicio__lte=end)
        ).distinct()
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
        
        from collections import Counter
        from django.conf import settings
        counter = Counter()
        presence_hours = int(getattr(settings, 'PRESENCE_HOURS', 8))

        for rdo in qs:
            try:
                d_date = getattr(rdo, 'data', None) or getattr(rdo, 'data_inicio', None)
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
            cur = cur + td(days=1)
        
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
        
        from collections import Counter
        counter = Counter()

        def _to_int_safe(x):
            try:
                return int(x or 0)
            except Exception:
                try:
                    return int(float(x or 0))
                except Exception:
                    return 0

        for rdo in qs:
            try:
                if rdo.data:
                    d = rdo.data.strftime('%Y-%m-%d')

                    tank_sum = 0
                    try:
                        if hasattr(rdo, 'tanques'):
                            for rt in rdo.tanques.all():
                                rt_cum = getattr(rt, 'ensacamento_cumulativo', None)
                                added = 0
                                if rt_cum is not None and float(rt_cum or 0) != 0:
                                    try:
                                        PrevModel = type(rt)
                                        prev = PrevModel.objects.filter(tanque_codigo=getattr(rt, 'tanque_codigo', None), rdo__data__lt=rdo.data).order_by('-rdo__data').first()
                                    except Exception:
                                        prev = None
                                    prev_cum = getattr(prev, 'ensacamento_cumulativo', None) if prev is not None else None
                                    try:
                                        if prev_cum is not None:
                                            delta = _to_int_safe(rt_cum) - _to_int_safe(prev_cum)
                                            if delta > 0:
                                                added = delta
                                        else:
                                            rt_day = getattr(rt, 'ensacamento_dia', None)
                                            if rt_day is not None and int(rt_day or 0) != 0:
                                                added = int(rt_day or 0)
                                            else:
                                                added = _to_int_safe(rt_cum)
                                    except Exception:
                                        try:
                                            rt_day = getattr(rt, 'ensacamento_dia', None)
                                            if rt_day is not None and int(rt_day or 0) != 0:
                                                added = int(rt_day or 0)
                                        except Exception:
                                            pass
                                else:
                                    try:
                                        rt_day = getattr(rt, 'ensacamento_dia', None)
                                        if rt_day is not None and int(rt_day or 0) != 0:
                                            added = int(rt_day or 0)
                                    except Exception:
                                        added = 0

                                tank_sum += added
                    except Exception:
                        tank_sum = 0

                    if tank_sum and int(tank_sum) != 0:
                        counter[d] += int(tank_sum)
                    else:
                        try:
                            ensacamento = getattr(rdo, 'ensacamento', None) or 0
                            counter[d] += int(ensacamento)
                        except Exception:
                            pass
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
        
        from collections import Counter
        counter = Counter()

        def _to_int_safe(x):
            try:
                return int(x or 0)
            except Exception:
                try:
                    return int(float(x or 0))
                except Exception:
                    return 0

        for rdo in qs:
            try:
                if rdo.data:
                    d = rdo.data.strftime('%Y-%m-%d')

                    tank_sum = 0
                    try:
                        if hasattr(rdo, 'tanques'):
                            for rt in rdo.tanques.all():
                                rt_cum = getattr(rt, 'tambores_cumulativo', None)
                                added = 0
                                if rt_cum is not None and float(rt_cum or 0) != 0:
                                    try:
                                        PrevModel = type(rt)
                                        prev = PrevModel.objects.filter(tanque_codigo=getattr(rt, 'tanque_codigo', None), rdo__data__lt=rdo.data).order_by('-rdo__data').first()
                                    except Exception:
                                        prev = None
                                    prev_cum = getattr(prev, 'tambores_cumulativo', None) if prev is not None else None
                                    try:
                                        if prev_cum is not None:
                                            delta = _to_int_safe(rt_cum) - _to_int_safe(prev_cum)
                                            if delta > 0:
                                                added = delta
                                        else:
                                            rt_day = getattr(rt, 'tambores_dia', None)
                                            if rt_day is not None and int(rt_day or 0) != 0:
                                                added = int(rt_day or 0)
                                            else:
                                                added = _to_int_safe(rt_cum)
                                    except Exception:
                                        try:
                                            rt_day = getattr(rt, 'tambores_dia', None)
                                            if rt_day is not None and int(rt_day or 0) != 0:
                                                added = int(rt_day or 0)
                                        except Exception:
                                            pass
                                else:
                                    try:
                                        rt_day = getattr(rt, 'tambores_dia', None)
                                        if rt_day is not None and int(rt_day or 0) != 0:
                                            added = int(rt_day or 0)
                                    except Exception:
                                        added = 0

                                tank_sum += added
                    except Exception:
                        tank_sum = 0

                    if tank_sum and int(tank_sum) != 0:
                        counter[d] += int(tank_sum)
                    else:
                        try:
                            tambores = getattr(rdo, 'tambores', 0) or 0
                            counter[d] += int(tambores)
                        except Exception:
                            pass
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
        by_day_tank = defaultdict(lambda: defaultdict(float))
        tank_totals = defaultdict(float)

        # Prefetch tanques para reduzir N+1
        try:
            qs = qs.prefetch_related('tanques')
        except Exception:
            pass

        for rdo in qs:
            try:
                if rdo.data:
                    d = rdo.data.strftime('%Y-%m-%d')

                    # Soma por tanque (não somar tudo junto)
                    any_tank_value = False
                    try:
                        if hasattr(rdo, 'tanques'):
                            for rt in rdo.tanques.all():
                                added = 0.0
                                rt_val = getattr(rt, 'tempo_bomba', None)
                                tank_key = None
                                try:
                                    tank_key = getattr(rt, 'tanque_codigo', None)
                                except Exception:
                                    tank_key = None
                                if tank_key is None:
                                    tank_key = getattr(rdo, 'tanque_codigo', None) or getattr(rdo, 'nome_tanque', None)
                                tank_key = (str(tank_key).strip() if tank_key is not None else '')
                                if not tank_key:
                                    tank_key = 'Desconhecido'
                                try:
                                    if rt_val is not None and float(rt_val or 0) != 0:
                                        PrevModel = type(rt)
                                        try:
                                            prev = PrevModel.objects.filter(tanque_codigo=getattr(rt, 'tanque_codigo', None), rdo__data__lt=rdo.data).order_by('-rdo__data').first()
                                        except Exception:
                                            prev = None
                                        prev_val = getattr(prev, 'tempo_bomba', None) if prev is not None else None
                                        try:
                                            if prev_val is not None:
                                                delta = float(rt_val or 0) - float(prev_val or 0)
                                                if delta > 0:
                                                    added = delta
                                                else:
                                                    added = float(rt_val or 0)
                                            else:
                                                added = float(rt_val or 0)
                                        except Exception:
                                            try:
                                                added = float(rt_val or 0)
                                            except Exception:
                                                added = 0.0
                                    else:
                                        rt_day = getattr(rt, 'tempo_bomba', None)
                                        try:
                                            added = float(rt_day or 0)
                                        except Exception:
                                            added = 0.0
                                except Exception:
                                    added = 0.0

                                if added and float(added) != 0.0:
                                    any_tank_value = True
                                    by_day_tank[d][tank_key] += float(added)
                                    tank_totals[tank_key] += float(added)
                    except Exception:
                        any_tank_value = False

                    # Fallback: se não houver itens de tanque, usar o RDO (associando a um tanque do RDO)
                    if not any_tank_value:
                        try:
                            tank_key = getattr(rdo, 'tanque_codigo', None) or getattr(rdo, 'nome_tanque', None)
                            tank_key = (str(tank_key).strip() if tank_key is not None else '')
                            if not tank_key:
                                tank_key = 'Desconhecido'
                            tempo = getattr(rdo, 'tempo_bomba', None) or 0
                            added = float(tempo or 0)
                            if added and float(added) != 0.0:
                                by_day_tank[d][tank_key] += added
                                tank_totals[tank_key] += added
                        except Exception:
                            pass
            except Exception:
                pass

        days = []
        cur = start
        while cur <= end:
            ds = cur.strftime('%Y-%m-%d')
            days.append(ds)
            cur = cur + td(days=1)

        # Selecionar top tanques por total no período (para não poluir o gráfico)
        top_n = 8
        sorted_tanks = sorted(tank_totals.items(), key=lambda x: x[1], reverse=True)
        top_tanks = [t[0] for t in sorted_tanks[:top_n] if t and t[0]]
        top_set = set(top_tanks)
        has_others = len(sorted_tanks) > len(top_tanks)

        datasets = []
        # Montar séries por tanque
        for tank_key in top_tanks:
            series = [float(by_day_tank.get(ds, {}).get(tank_key, 0) or 0) for ds in days]
            datasets.append({
                'label': str(tank_key),
                'data': series,
                'type': 'bar'
            })

        # Agrupar o restante em 'Outros'
        if has_others:
            others_series = []
            for ds in days:
                total_other = 0.0
                day_map = by_day_tank.get(ds, {})
                for tk, v in day_map.items():
                    if tk not in top_set:
                        try:
                            total_other += float(v or 0)
                        except Exception:
                            pass
                others_series.append(total_other)
            datasets.append({
                'label': 'Outros',
                'data': others_series,
                'type': 'bar'
            })

        resp = {
            'success': True,
            'labels': days,
            'datasets': datasets,
            'meta': {
                'group_by': 'tanque',
                'top_n': top_n,
                'has_others': bool(has_others)
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
        from .models import RDO
        from datetime import timedelta as td
        import logging
        
        logger = logging.getLogger(__name__)
        
        start_str = request.GET.get('start')
        end_str = request.GET.get('end')
        supervisor = request.GET.get('supervisor')
        tanque = request.GET.get('tanque')
        cliente = request.GET.get('cliente')
        unidade = request.GET.get('unidade')
        os_existente = request.GET.get('os_existente')
        
        if end_str:
            end = datetime.strptime(end_str, '%Y-%m-%d').date()
        else:
            end = datetime.today().date()
        if start_str:
            start = datetime.strptime(start_str, '%Y-%m-%d').date()
        else:
            start = end - td(days=29)
        
        logger.info(f"[RESIDUO_LIQUIDO] Período: {start} até {end}")
        
        qs = RDO.objects.filter(data__gte=start, data__lte=end)
        logger.info(f"[RESIDUO_LIQUIDO] Total RDOs no período: {qs.count()}")
        
        if supervisor:
            qs = qs.filter(ordem_servico__supervisor__username=supervisor)
            logger.info(f"[RESIDUO_LIQUIDO] Filtro supervisor: {supervisor}, RDOs: {qs.count()}")
        if tanque:
            qs = qs.filter(
                Q(nome_tanque__icontains=tanque) |
                Q(tanque_codigo__icontains=tanque) |
                Q(tanques__tanque_codigo__icontains=tanque)
            ).distinct()
            logger.info(f"[RESIDUO_LIQUIDO] Filtro tanque: {tanque}, RDOs: {qs.count()}")
        if cliente:
            qs = qs.filter(ordem_servico__Cliente__nome__icontains=cliente)
            logger.info(f"[RESIDUO_LIQUIDO] Filtro cliente: {cliente}, RDOs: {qs.count()}")
        if unidade:
            qs = qs.filter(ordem_servico__Unidade__nome__icontains=unidade)
            logger.info(f"[RESIDUO_LIQUIDO] Filtro unidade: {unidade}, RDOs: {qs.count()}")
        if os_existente:
            qs = apply_os_filter_generic(qs, os_existente)
            logger.info(f"[RESIDUO_LIQUIDO] Filtro OS: {os_existente}, RDOs: {qs.count()}")
        
        from collections import Counter
        counter = Counter()
        total_rdos = qs.count()
        rdos_with_liquido = 0
        sample_nonzero = []
        sample_all = []

        for rdo in qs:
            try:
                rdo_date = getattr(rdo, 'data', None)
                if rdo_date:
                    d = rdo_date.strftime('%Y-%m-%d')

                    def _to_float_safe(x):
                        try:
                            return float(x or 0)
                        except Exception:
                            return 0.0

                    val_bombeio = getattr(rdo, 'bombeio', None)
                    val_quantidade_bombeada = getattr(rdo, 'quantidade_bombeada', None)
                    val_total_liquido = getattr(rdo, 'total_liquido', None)
                    val_total_liquido_cum = getattr(rdo, 'total_liquido_cumulativo', None)
                    
                    def _normalize_volume(v):
                        f = _to_float_safe(v)
                        if abs(f) > 100:
                            try:
                                return f / 1000.0
                            except Exception:
                                return f
                        return f

                    liquido = 0.0
                    t_total = _to_float_safe(val_total_liquido)
                    t_quant = _to_float_safe(val_quantidade_bombeada)
                    t_bombeio = _to_float_safe(val_bombeio)

                    used_source_rdo = 'none'
                    
                    # Prioridade: usar valores diretos do dia antes de calcular delta
                    if t_total and t_total != 0:
                        liquido = _normalize_volume(t_total)
                        used_source_rdo = 'rdo_total'
                    elif t_bombeio and t_bombeio != 0:
                        liquido = _normalize_volume(t_bombeio)
                        used_source_rdo = 'rdo_bombeio'
                    elif t_quant and t_quant != 0:
                        liquido = _normalize_volume(t_quant)
                        used_source_rdo = 'quantidade_bombeada'
                    else:
                        # Só usar delta de cumulativo se não houver valor do dia
                        t_total_cum = _to_float_safe(val_total_liquido_cum)
                        if t_total_cum and t_total_cum != 0:
                            try:
                                prev_rdo = RDO.objects.filter(
                                    Q(tanque_codigo=getattr(rdo, 'tanque_codigo', None)) | Q(nome_tanque=getattr(rdo, 'nome_tanque', None)),
                                    data__lt=rdo_date
                                ).order_by('-data').first()
                            except Exception:
                                prev_rdo = None

                            prev_cum_rdo = getattr(prev_rdo, 'total_liquido_cumulativo', None) if prev_rdo is not None else None
                            if prev_cum_rdo is not None:
                                try:
                                    delta_rdo = float(t_total_cum or 0) - float(prev_cum_rdo or 0)
                                    # Só usar delta se for positivo (evita valores negativos)
                                    if delta_rdo > 0:
                                        liquido = _normalize_volume(delta_rdo)
                                        used_source_rdo = 'rdo_cumulativo_delta'
                                except Exception:
                                    pass
                            else:
                                # Primeiro cumulativo registrado
                                liquido = _normalize_volume(t_total_cum)
                                used_source_rdo = 'rdo_total_cum_first'

                    if liquido == 0.0:
                        r_tot = getattr(rdo, 'residuos_totais', None) or getattr(rdo, 'total_residuos', None)
                        r_sol = getattr(rdo, 'residuos_solidos', None) or getattr(rdo, 'total_solidos', None)
                        if r_tot is not None or r_sol is not None:
                            liquido = _normalize_volume(_to_float_safe(r_tot) - _to_float_safe(r_sol))

                    try:
                        if hasattr(rdo, 'tanques'):
                            tank_sum = 0.0
                            for rt in rdo.tanques.all():
                                rt_total = getattr(rt, 'total_liquido', None)
                                rt_bombeio = getattr(rt, 'bombeio', None)
                                rt_total_cum = getattr(rt, 'total_liquido_cumulativo', None)
                                added = 0.0
                                used_source = 'none'
                                
                                # Prioridade: usar valores diretos do dia antes de calcular delta
                                if rt_total is not None and float(rt_total or 0) != 0:
                                    added = _normalize_volume(rt_total)
                                    used_source = 'rt_total'
                                elif rt_bombeio is not None and float(rt_bombeio or 0) != 0:
                                    added = _normalize_volume(rt_bombeio)
                                    used_source = 'rt_bombeio'
                                elif rt_total_cum is not None and float(rt_total_cum or 0) != 0:
                                    # Só usar delta de cumulativo se não houver valor do dia
                                    try:
                                        PrevModel = type(rt)
                                        prev = PrevModel.objects.filter(tanque_codigo=getattr(rt, 'tanque_codigo', None), rdo__data__lt=rdo_date).order_by('-rdo__data').first()
                                    except Exception:
                                        prev = None

                                    prev_cum = getattr(prev, 'total_liquido_cumulativo', None) if prev is not None else None
                                    try:
                                        if prev_cum is not None:
                                            delta = float(rt_total_cum or 0) - float(prev_cum or 0)
                                            # Só usar delta se for positivo (evita valores negativos)
                                            if delta > 0:
                                                added = _normalize_volume(delta)
                                                used_source = 'cumulativo_delta'
                                        else:
                                            # Primeiro cumulativo registrado
                                            added = _normalize_volume(rt_total_cum)
                                            used_source = 'rt_total_cum_first'
                                    except Exception:
                                        pass

                                if added == 0.0:
                                    try:
                                        rt_tot = getattr(rt, 'residuos_totais', None)
                                        rt_sol = getattr(rt, 'residuos_solidos', None)
                                        if rt_tot is not None or rt_sol is not None:
                                            diff = _to_float_safe(rt_tot) - _to_float_safe(rt_sol)
                                            if diff > 0:
                                                added = _normalize_volume(diff)
                                                used_source = 'residuos_diff'
                                    except Exception:
                                        pass

                                if len(sample_all) < 5:
                                    try:
                                        sample_all.append({'rt_id': getattr(rt, 'id', None), 'tanque_codigo': getattr(rt, 'tanque_codigo', None), 'used_source': used_source})
                                    except Exception:
                                        pass

                                tank_sum += added

                            try:
                                if tank_sum and float(tank_sum) != 0:
                                    liquido = tank_sum
                                    used_source_rdo = 'from_tanks'
                            except Exception:
                                pass
                    except Exception:
                        pass

                    if len(sample_all) < 5:
                        sample_all.append({
                            'id': getattr(rdo, 'id', None),
                            'date': d,
                            'bombeio': val_bombeio,
                            'quantidade_bombeada': val_quantidade_bombeada,
                            'total_liquido': val_total_liquido,
                            'total_liquido_cumulativo': val_total_liquido_cum,
                            'liquido_calculado': liquido,
                            'used_source_rdo': used_source_rdo
                        })

                    if liquido and float(liquido) != 0.0:
                        rdos_with_liquido += 1
                        if len(sample_nonzero) < 5:
                            sample_nonzero.append({
                                'id': getattr(rdo, 'id', None),
                                'date': d,
                                'liquido': liquido
                            })

                    counter[d] += liquido
            except Exception as ex:
                if len(sample_all) < 10:
                    sample_all.append({'error': str(ex)})
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
                'label': 'M³ resíduo líquido',
                'data': values,
                'backgroundColor': '#3498db',
                'borderColor': '#2980b9'
            }],
            'debug': {
                'total_rdos': total_rdos,
                'rdos_with_liquido': rdos_with_liquido,
                'sample_nonzero': sample_nonzero,
                'sample_all': sample_all,
                'date_range': f'{start} até {end}'
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
        tanques_dict = defaultdict(float)

        for rdo in qs:
            try:
                added = False
                if hasattr(rdo, 'tanques'):
                    for rt in rdo.tanques.all():
                        try:
                            tc = getattr(rt, 'tanque_codigo', None) or None
                            if tc:
                                tc = str(tc).strip()
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
                                tanques_dict[tc] += vol
                                added = True
                        except Exception:
                            pass

                if not added:
                    tc = getattr(rdo, 'tanque_codigo', None) or getattr(rdo, 'nome_tanque', None) or 'Desconhecido'
                    tc = (str(tc).strip() if tc is not None else 'Desconhecido')
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

                    tanques_dict[tc] += vol
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