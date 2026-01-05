from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from django.http import JsonResponse
from django.db.models import Count, Avg, Q
from django.db.models.functions import TruncDate
from django.shortcuts import render
from datetime import datetime, timedelta

from .models import OrdemServico
from django.core.cache import cache
import unicodedata
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
import logging


@login_required(login_url='/login/')
@require_GET
def ordens_por_dia(request):
    """Retorna ordens criadas por dia no intervalo solicitado.
    Parâmetros GET: start (YYYY-MM-DD), end (YYYY-MM-DD)
    Se não informados, retorna últimos 30 dias.
    """
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

        qs = OrdemServico.objects.filter(data_inicio__gte=start, data__lte=end)
        if cliente:
            qs = qs.filter(Cliente__nome__icontains=cliente)
        if unidade:
            qs = qs.filter(Unidade__nome__icontains=unidade)

        # cache básico para reduzir carga: chave baseada em parâmetros
        cache_key = f"ordens_por_dia|start={start}|end={end}|cliente={cliente or ''}|unidade={unidade or ''}"
        cached = cache.get(cache_key)
        if cached is not None:
            return JsonResponse(cached)
        # Agrupar por data no Python para evitar uso de funções SQL que
        # podem falhar em backends como SQLite (p.ex. "user-defined function raised exception").
        # Coletar datas e contar ocorrências localmente.
        dates = list(qs.values_list('data_inicio', flat=True))
        from collections import defaultdict
        counter = defaultdict(float)
        for d in dates:
            try:
                key = d.strftime('%Y-%m-%d') if d is not None else None
            except Exception:
                # caso d não seja date, tentar str()
                try:
                    key = str(d)
                except Exception:
                    key = None
            if key:
                counter[key] += 1

        # construir mapa de datas contínuas para não pular dias sem ordens
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
            }]
        }
        # salvar em cache por 60s
        try:
            cache.set(cache_key, resp, 60)
        except Exception:
            pass
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required(login_url='/login/')
@require_GET
def status_os(request):
    """Retorna a contagem de OS por status_geral (ou status_operacao se preferir).
    """
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
        # filtrar por intervalo de datas se informado
        try:
            if start_str:
                start = datetime.strptime(start_str, '%Y-%m-%d').date()
                qs = qs.filter(data_inicio__gte=start)
            if end_str:
                end = datetime.strptime(end_str, '%Y-%m-%d').date()
                qs = qs.filter(data__lte=end)
        except Exception:
            pass
        # usar status_geral se existir
        # cache simples
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
    """Retorna os serviços mais frequentes.
    Prioriza o campo `servicos` (TextField com itens separados por vírgula) quando preenchido;
    caso contrário usa o campo `servico` (choice único). Querystring: top (int) número de registros.
    """
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

        # Usar cache para respostas semelhantes (cache tempo curto)
        cache_key = f"servicos_top={top}|cliente={cliente or ''}|unidade={unidade or ''}|start={start_str or ''}|end={end_str or ''}"
        cached = cache.get(cache_key)
        if cached is not None:
            return JsonResponse(cached)

        # Normalizar os serviços: preferir `servicos` (lista separada por vírgula) e usar `servico` como fallback
        from collections import defaultdict
        counter = defaultdict(float)
        # obter tuplas (servicos, servico) para cada registro
        for servicos_field, servico_field in qs.values_list('servicos', 'servico'):
            parts = []
            try:
                if servicos_field:
                    # `servicos` armazena lista separada por vírgula
                    parts = [p.strip() for p in servicos_field.split(',') if p.strip()]
                elif servico_field:
                    parts = [servico_field.strip()]
            except Exception:
                parts = []

            if not parts:
                counter['Indefinido'] += 1
            else:
                for p in parts:
                    # normalizar: remover acentos e normalizar caixa
                    p_norm = unicodedata.normalize('NFKD', p).encode('ascii', 'ignore').decode('ascii').lower()
                    counter[p_norm] += 1

        most = counter.most_common(top)
        labels = [item[0] for item in most]
        values = [item[1] for item in most]
        # truncar labels muito longos
        labels = [lab if len(lab) <= 60 else (lab[:57] + '...') for lab in labels]
        resp = {'success': True, 'labels': labels, 'values': values}
        # armazenar por 60s
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
    """Retorna os clientes com mais ordens (Top N)."""
    try:
        top_param = request.GET.get('top')
        try:
            top = int(top_param) if top_param is not None else 10
        except Exception:
            top = 10
        # limitar valor de top para evitar consultas muito grandes
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

        # A coluna FK no modelo se chama `Cliente` (capital). Usar join para o nome.
        data = list(qs.values('Cliente__nome').annotate(count=Count('id')).order_by('-count')[:top])
        labels = [ (str(item.get('Cliente__nome')) if item.get('Cliente__nome') is not None else 'Indefinido') for item in data ]
        values = [ int(item.get('count') or 0) for item in data ]
        # truncar labels muito longos
        labels = [lab if len(lab) <= 60 else (lab[:57] + '...') for lab in labels]
        resp = {'success': True, 'labels': labels, 'values': values}
        try:
            cache.set(cache_key, resp, 60)
        except Exception:
            pass
        return JsonResponse(resp)
    except Exception as e:
        # registrar traceback no log para diagnóstico
        try:
            logger = logging.getLogger(__name__)
            logger.exception('Erro em top_clientes: %s', e)
        except Exception:
            pass
        return JsonResponse({'success': False, 'error': 'Erro interno ao gerar top clientes'}, status=500)


@login_required(login_url='/login/')
@require_GET
def metodos_mais_utilizados(request):
    """Retorna os métodos mais utilizados (Top N) a partir do campo `metodo`."""
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
    """Retorna o tempo médio (dias) por supervisor.
    Calculado a partir do campo `dias_de_operacao` (quando presente).
    """
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

        # agrupar por supervisor (objeto FK). utilizar supervisor__username quando necessário
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
    """Retorna KPIs rápidos: total OS, abertas, concluídas no mês e tempo médio de operação (dias).
    """
    try:
        # aceitar filtros opcionais (start/end/cliente/unidade) — respeitar o mesmo comportamento do demais endpoints
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
            # ignorar parsing de data e usar queryset sem filtro de data
            start = None
            end = None

        if cliente:
            qs = qs.filter(Cliente__nome__icontains=cliente)
        if unidade:
            qs = qs.filter(Unidade__nome__icontains=unidade)

        # total baseado no queryset filtrado
        total = qs.count()

        # Contagem por status operacional (usar o campo `status_operacao` definido no modelo)
        statuses = ['Programada', 'Em Andamento', 'Paralizada', 'Finalizada']
        status_counts = {s: qs.filter(status_operacao__iexact=s).count() for s in statuses}

        # 'abertas' mapeia para ordens em andamento
        abertas = status_counts.get('Em Andamento', 0)

        # concluídas no período: se start/end informados, usar esse intervalo; caso contrário, mês corrente
        if start_str or end_str:
            # já aplicamos filtros sobre data_inicio; para data_fim usamos intervalo similar quando informado
            try:
                if start_str and end_str:
                    # contar por data_fim dentro do intervalo
                    concl_qs = OrdemServico.objects.filter(status_operacao__iexact='Finalizada', data_fim__gte=start, data_fim__lte=end)
                    if cliente:
                        concl_qs = concl_qs.filter(Cliente__nome__icontains=cliente)
                    if unidade:
                        concl_qs = concl_qs.filter(Unidade__nome__icontains=unidade)
                    concluidas_mes = concl_qs.count()
                else:
                    # se apenas um bound foi informado, aproximar usando data_fim >= start ou <= end
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

        # tempo médio de operação: média de dias_de_operacao quando preenchido (ignorar nulls) sobre o queryset filtrado
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
    """Retorna o status de supervisores: quem está em embarque (com data_inicio_frente preenchida e status_geral != 'Finalizada').

    Querystring opcional: cliente, unidade, start, end (filtros aplicados sobre data_inicio_frente)
    Retorna: labels (nomes), values (contagem ativa por supervisor), colors (por supervisor), details (lista com status)
    """
    try:
        User = get_user_model()
        # tentar localizar o grupo de supervisores por nomes comuns
        group = Group.objects.filter(name__in=['supervisore', 'supervisores', 'Supervisor', 'Supervisores']).first()
        if group:
            users = group.user_set.filter(is_active=True).order_by('first_name', 'last_name', 'username')
        else:
            # fallback: usuários que já aparecem como supervisor em alguma OS
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

            # considerar embarque ativo quando existe data_inicio_frente e status_geral != 'Finalizada'
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


# ============ NOVOS ENDPOINTS PARA DASHBOARD RDO ============

@login_required(login_url='/login/')
@require_GET
def rdo_soma_hh_confinado_por_dia(request):
    """Retorna a soma de HH em espaço confinado por dia (calculado a partir de entrada_confinado_1..6 e saida_confinado_1..6)."""
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
            qs = qs.filter(ordem_servico_id=os_existente)
        if os_existente:
            qs = qs.filter(ordem_servico_id=os_existente)
        if os_existente:
            qs = qs.filter(ordem_servico_id=os_existente)
        
        from collections import Counter
        counter = Counter()
        
        for rdo in qs:
            try:
                if rdo.data:
                    d = rdo.data.strftime('%Y-%m-%d')
                    # Somar todas as horas em espaço confinado (até 6 pares de entrada/saída)
                    total_minutos = 0
                    for i in range(1, 7):
                        entrada_field = f'entrada_confinado_{i}'
                        saida_field = f'saida_confinado_{i}'
                        entrada = getattr(rdo, entrada_field, None)
                        saida = getattr(rdo, saida_field, None)
                        if entrada and saida:
                            try:
                                # Calcular diferença de minutos
                                entrada_min = entrada.hour * 60 + entrada.minute
                                saida_min = saida.hour * 60 + saida.minute
                                if saida_min >= entrada_min:
                                    total_minutos += (saida_min - entrada_min)
                                else:
                                    # Caso saída seja no dia seguinte (improvável, mas cobrir)
                                    total_minutos += ((24 * 60 - entrada_min) + saida_min)
                            except Exception:
                                pass
                    horas = round(total_minutos / 60, 2)
                    counter[d] += horas
            except Exception:
                pass
        
        # Construir série temporal completa (preenchendo dias sem dados com 0)
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
            }]
        }
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required(login_url='/login/')
@require_GET
def rdo_soma_hh_fora_confinado_por_dia(request):
    """Retorna a soma de HH fora de espaço confinado por dia (calculado a partir de entrada_confinado_1..6 e saida_confinado_1..6)."""
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
            qs = qs.filter(ordem_servico_id=os_existente)
        if os_existente:
            qs = qs.filter(ordem_servico_id=os_existente)
        
        from collections import Counter
        counter = Counter()
        
        for rdo in qs:
            try:
                if rdo.data:
                    d = rdo.data.strftime('%Y-%m-%d')
                    # Somar todas as horas fora de espaço confinado
                    # Para simplificar, assumir que HH fora = POB - HH confinado (aproximação)
                    # ou usar um cálculo direto se houver campo específico
                    # Aqui, usar ordem_servico.pob como referência
                    os = rdo.ordem_servico
                    if os:
                        pob = os.pob if os.pob else 0
                        # HH fora = POB * dias (simplificado)
                        # Se quiser mais precisão, usar entrada_confinado_1 até saida_confinado_6 para calcular o tempo
                        # Assumir que horas fora = POB
                        counter[d] += pob
            except Exception:
                pass
        
        # Construir série temporal completa (preenchendo dias sem dados com 0)
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
            }]
        }
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required(login_url='/login/')
@require_GET
def rdo_ensacamento_por_dia(request):
    """Retorna ensacamento (campo ensacamento do RDO) agregado por dia."""
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
            qs = qs.filter(ordem_servico_id=os_existente)
        if os_existente:
            qs = qs.filter(ordem_servico_id=os_existente)
        
        from collections import Counter
        counter = Counter()
        
        for rdo in qs:
            try:
                if rdo.data and hasattr(rdo, 'ensacamento'):
                    d = rdo.data.strftime('%Y-%m-%d')
                    ensacamento = getattr(rdo, 'ensacamento', 0) or 0
                    counter[d] += int(ensacamento)
            except Exception:
                pass
        
        # Construir série temporal completa (preenchendo dias sem dados com 0)
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
            }]
        }
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required(login_url='/login/')
@require_GET
def rdo_tambores_por_dia(request):
    """Retorna tambores gerados por dia (campo tambores do RDO)."""
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
            qs = qs.filter(ordem_servico_id=os_existente)
        if os_existente:
            qs = qs.filter(ordem_servico_id=os_existente)
        
        from collections import Counter
        counter = Counter()
        
        for rdo in qs:
            try:
                if rdo.data:
                    d = rdo.data.strftime('%Y-%m-%d')
                    tambores = getattr(rdo, 'tambores', 0) or 0
                    counter[d] += int(tambores)
            except Exception:
                pass
        
        # Construir série temporal completa (preenchendo dias sem dados com 0)
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
            }]
        }
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required(login_url='/login/')
@require_GET
def rdo_residuos_liquido_por_dia(request):
    """Retorna M³ de resíduo líquido removido por dia (campo total_liquido do RDO)."""
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
            qs = qs.filter(ordem_servico_id=os_existente)
        if os_existente:
            qs = qs.filter(ordem_servico_id=os_existente)
        
        from collections import Counter
        counter = Counter()
        
        for rdo in qs:
            try:
                if rdo.data:
                    d = rdo.data.strftime('%Y-%m-%d')
                    # Agregar diferentes fontes que podem conter volume líquido
                    liquido = 0.0
                    try:
                        liquido += float(getattr(rdo, 'total_liquido', 0) or 0)
                    except Exception:
                        pass
                    try:
                        liquido += float(getattr(rdo, 'quantidade_bombeada', 0) or 0)
                    except Exception:
                        pass
                    try:
                        liquido += float(getattr(rdo, 'bombeio', 0) or 0)
                    except Exception:
                        pass
                    try:
                        liquido += float(getattr(rdo, 'volume_tanque_exec', 0) or 0)
                    except Exception:
                        pass
                    # Incluir volumes declarados em RdoTanque relacionados (se houver)
                    try:
                        if hasattr(rdo, 'tanques'):
                            for rt in rdo.tanques.all():
                                try:
                                    liquido += float(getattr(rt, 'volume_tanque_exec', 0) or 0)
                                except Exception:
                                    pass
                    except Exception:
                        pass

                    counter[d] += liquido
            except Exception:
                pass
        
        # Construir série temporal completa (preenchendo dias sem dados com 0)
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
            }]
        }
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required(login_url='/login/')
@require_GET
def rdo_residuos_solido_por_dia(request):
    """Retorna M³ de resíduo sólido removido por dia (campo total_solidos do RDO)."""
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
            qs = qs.filter(ordem_servico_id=os_existente)
        if os_existente:
            qs = qs.filter(ordem_servico_id=os_existente)
        
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
        
        # Construir série temporal completa (preenchendo dias sem dados com 0)
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
            }]
        }
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required(login_url='/login/')
@require_GET
def rdo_liquido_por_supervisor(request):
    """Retorna soma de M³ líquido removido por supervisor."""
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
            qs = qs.filter(ordem_servico_id=os_existente)
        if os_existente:
            qs = qs.filter(ordem_servico_id=os_existente)
        
        User = get_user_model()
        supervisores = User.objects.filter(ordens_supervisionadas__rdos__isnull=False).distinct()
        
        labels = []
        values = []
        
        for sup in supervisores:
            # Buscar soma real agregando várias fontes possíveis de volume líquido
            rdo_list = qs.filter(ordem_servico__supervisor=sup)
            soma_liquido = 0.0
            for r in rdo_list:
                try:
                    soma_liquido += float(getattr(r, 'total_liquido', 0) or 0)
                except Exception:
                    pass
                try:
                    soma_liquido += float(getattr(r, 'quantidade_bombeada', 0) or 0)
                except Exception:
                    pass
                try:
                    soma_liquido += float(getattr(r, 'bombeio', 0) or 0)
                except Exception:
                    pass
                try:
                    soma_liquido += float(getattr(r, 'volume_tanque_exec', 0) or 0)
                except Exception:
                    pass
                try:
                    if hasattr(r, 'tanques'):
                        for rt in r.tanques.all():
                            try:
                                soma_liquido += float(getattr(rt, 'volume_tanque_exec', 0) or 0)
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
            }]
        }
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required(login_url='/login/')
@require_GET
def rdo_solido_por_supervisor(request):
    """Retorna soma de M³ sólido removido por supervisor."""
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
            qs = qs.filter(ordem_servico_id=os_existente)
        if os_existente:
            qs = qs.filter(ordem_servico_id=os_existente)
        
        User = get_user_model()
        supervisores = User.objects.filter(ordens_supervisionadas__rdos__isnull=False).distinct()
        
        labels = []
        values = []
        
        for sup in supervisores:
            # Buscar soma real de total_solidos (usar float para frações)
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
            }]
        }
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required(login_url='/login/')
@require_GET
def rdo_volume_por_tanque(request):
    """Retorna soma de M³ por tanque (último volume disponível)."""
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
            qs = qs.filter(ordem_servico_id=os_existente)
        if os_existente:
            qs = qs.filter(ordem_servico_id=os_existente)
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
                # Priorizar tanques associados (RdoTanque) por tanque_codigo
                added = False
                if hasattr(rdo, 'tanques'):
                    for rt in rdo.tanques.all():
                        try:
                            tc = getattr(rt, 'tanque_codigo', None) or None
                            if tc:
                                tc = str(tc).strip()
                                # Preferir volume declarado no RdoTanque
                                vol = 0.0
                                try:
                                    vol = float(getattr(rt, 'volume_tanque_exec', 0) or 0)
                                except Exception:
                                    vol = 0.0
                                # Fallbacks para outras fontes no RdoTanque
                                if vol == 0:
                                    try:
                                        vol = float(getattr(rt, 'bombeio', 0) or 0)
                                    except Exception:
                                        pass
                                tanques_dict[tc] += vol
                                added = True
                        except Exception:
                            pass

                # Se não houve RdoTanque com código, usar campos do próprio RDO
                if not added:
                    tc = getattr(rdo, 'tanque_codigo', None) or getattr(rdo, 'nome_tanque', None) or 'Desconhecido'
                    tc = (str(tc).strip() if tc is not None else 'Desconhecido')
                    vol = 0.0
                    try:
                        vol = float(getattr(rdo, 'volume_tanque_exec', 0) or 0)
                    except Exception:
                        pass
                    if vol == 0:
                        try:
                            vol = float(getattr(rdo, 'quantidade_bombeada', 0) or 0)
                        except Exception:
                            pass
                    if vol == 0:
                        try:
                            vol = float(getattr(rdo, 'bombeio', 0) or 0)
                        except Exception:
                            pass
                    if vol == 0:
                        try:
                            vol = float(getattr(rdo, 'total_liquido', 0) or 0)
                        except Exception:
                            pass

                    tanques_dict[tc] += vol
            except Exception:
                pass
        
        # Top 10 tanques
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
            }]
        }
        return JsonResponse(resp)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ============ VIEW PRINCIPAL DO DASHBOARD RDO ============

@login_required(login_url='/login/')
def rdo_dashboard_view(request):
    """Renderiza a página principal do dashboard de RDO com filtros e gráficos."""
    try:
        from .models import Cliente, Unidade, RDO, RdoTanque
        
        # Obter listas de clientes, unidades e supervisores para os filtros
        clientes = Cliente.objects.all().order_by('nome')
        unidades = Unidade.objects.all().order_by('nome')
        supervisores = get_user_model().objects.filter(ordens_supervisionadas__isnull=False).distinct().order_by('first_name', 'last_name', 'username')
        
        # Obter escopos únicos (tipos de tanque ou serviço do RDO)
        escopos = RDO.objects.filter(servico_exec__isnull=False).values_list('servico_exec', flat=True).distinct()
        
        # Obter tanques únicos: priorizar `tanque_codigo` vindo de `RdoTanque`,
        # mas manter `nome_tanque` do RDO como fallback para compatibilidade.
        tanques_from_rt = list(RdoTanque.objects.filter(tanque_codigo__isnull=False).values_list('tanque_codigo', flat=True).distinct())
        tanques_from_rdo = list(RDO.objects.filter(nome_tanque__isnull=False).values_list('nome_tanque', flat=True).distinct())
        # Unificar (preservar códigos não vazios) e ordenar para exibição
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
        
        context = {
            'clientes': clientes,
            'unidades': unidades,
            'supervisores': supervisores,
            'escopos': escopos,
            'tanques': tanques,
            'titulo': 'Dashboard de RDO',
        }
        
        return render(request, 'dashboard_rdo.html', context)
    except Exception as e:
        from django.http import HttpResponse
        return HttpResponse(f'Erro ao carregar dashboard: {str(e)}', status=500)
