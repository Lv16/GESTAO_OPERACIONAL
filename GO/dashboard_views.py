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

        # Usar o campo correto `data_inicio` para filtrar o intervalo
        qs = OrdemServico.objects.filter(data_inicio__gte=start, data_inicio__lte=end)
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
def os_status_summary(request):
    """Retorna contagens resumidas de Ordens de Serviço deduplicadas por `numero_os`.
    Retorna JSON: { success: True, total: int, programada: int, em_andamento: int, paralizada: int, finalizada: int }
    Aceita filtros opcionais: cliente, unidade, start, end (mesma semântica do dashboard).
    """
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
            # Aplicar filtro de intervalo considerando tanto `data_inicio` quanto `data`,
            # já que alguns registros podem preencher apenas um dos campos.
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
            # ignorar erros de parsing de data
            pass

        # deduplicar por numero_os: escolher representante Min(id)
        rep_qs = qs.values('numero_os').annotate(rep_id=Min('id'))
        rep_ids = [r['rep_id'] for r in rep_qs if r.get('rep_id')]
        base_qs = OrdemServico.objects.filter(id__in=rep_ids) if rep_ids else OrdemServico.objects.none()

        programada = base_qs.filter(status_operacao__iexact='Programada').count()
        em_andamento = base_qs.filter(status_operacao__iexact='Em Andamento').count()
        paralizada = base_qs.filter(status_operacao__iexact='Paralizada').count()
        finalizada = base_qs.filter(status_operacao__iexact='Finalizada').count()
        cancelada = base_qs.filter(status_operacao__iexact='Cancelada').count()
        total = base_qs.count()

        # Log para diagnóstico: quantidades antes de retornar
        try:
            logger = logging.getLogger(__name__)
            logger.debug('os_status_summary: filters=%s, rep_ids=%d, base_qs=%d',
                         {'cliente': cliente, 'unidade': unidade, 'start': start_str, 'end': end_str},
                         len(rep_ids),
                         total)
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
            'ts': datetime.utcnow().isoformat() + 'Z'
        }
        return JsonResponse(resp)
    except Exception as e:
        logging.exception('Erro em os_status_summary')
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
        statuses = ['Programada', 'Em Andamento', 'Paralizada', 'Finalizada', 'Cancelada']
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
        
        # Incluir RDOs cuja data esteja em `data_inicio` ou em `data` (algumas instâncias
        # podem preencher apenas um dos campos). Filtrar por qualquer uma das duas colunas.
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
            qs = qs.filter(ordem_servico_id=os_existente)
        if os_existente:
            qs = qs.filter(ordem_servico_id=os_existente)
        if os_existente:
            qs = qs.filter(ordem_servico_id=os_existente)
        
        from collections import Counter
        counter = Counter()
        
        for rdo in qs:
            try:
                # Agrupar por data do RDO: preferir `data`, fallback `data_inicio`
                d_date = getattr(rdo, 'data', None) or getattr(rdo, 'data_inicio', None)
                if d_date:
                    d = d_date.strftime('%Y-%m-%d')
                    # Somar todas as horas em espaço confinado (até 6 pares de entrada/saída)
                    total_minutos = 0.0
                    for i in range(1, 7):
                        entrada_field = f'entrada_confinado_{i}'
                        saida_field = f'saida_confinado_{i}'
                        entrada = getattr(rdo, entrada_field, None)
                        saida = getattr(rdo, saida_field, None)
                        if entrada and saida:
                            try:
                                # Calcular diferença em minutos considerando horas, minutos e segundos
                                entrada_min = float(entrada.hour * 60 + entrada.minute) + float(getattr(entrada, 'second', 0)) / 60.0
                                saida_min = float(saida.hour * 60 + saida.minute) + float(getattr(saida, 'second', 0)) / 60.0
                                if saida_min >= entrada_min:
                                    total_minutos += (saida_min - entrada_min)
                                else:
                                    # Caso saída seja no dia seguinte
                                    total_minutos += ((24.0 * 60.0 - entrada_min) + saida_min)
                            except Exception:
                                pass
                    horas = round(total_minutos / 60.0, 2)
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
        
        # incluir RDOs cuja `data` OU `data_inicio` esteja no intervalo
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
            qs = qs.filter(ordem_servico_id=os_existente)
        if os_existente:
            qs = qs.filter(ordem_servico_id=os_existente)
        
        from collections import Counter
        from django.conf import settings
        counter = Counter()
        # horas padrão de presença por dia (em horas) usado no fallback com POB
        presence_hours = int(getattr(settings, 'PRESENCE_HOURS', 8))

        for rdo in qs:
            try:
                # Agrupar por data do RDO: preferir `data`, fallback `data_inicio`
                d_date = getattr(rdo, 'data', None) or getattr(rdo, 'data_inicio', None)
                if not d_date:
                    continue
                d = d_date.strftime('%Y-%m-%d')

                # Coletar campos possíveis (usar getattr com defaults quando apropriado)
                efetivas_min = getattr(rdo, 'total_atividades_efetivas_min', None)
                nao_efetivas_fora_min = getattr(rdo, 'total_atividades_nao_efetivas_fora_min', None)
                total_atividade_min = getattr(rdo, 'total_atividade_min', None)
                total_confinado_min = int(getattr(rdo, 'total_confinado_min', 0) or 0)
                total_abertura_pt_min = int(getattr(rdo, 'total_abertura_pt_min', 0) or 0)
                total_n_efetivo_confinado_min = getattr(rdo, 'total_n_efetivo_confinado_min', None)
                if total_n_efetivo_confinado_min is None:
                    total_n_efetivo_confinado_min = int(getattr(rdo, 'total_n_efetivo_confinado', 0) or 0)

                hh_fora_min = None

                # 1) Se dispomos de ambos os campos explícitos, use-os diretamente
                if efetivas_min is not None and nao_efetivas_fora_min is not None:
                    try:
                        hh_fora_min = int(efetivas_min or 0) + int(nao_efetivas_fora_min or 0)
                    except Exception:
                        hh_fora_min = None

                # 2) Senão, se temos total_atividade_min, calcular como solicitado:
                #    hh_fora_min = total_atividade_min - total_confinado_min - total_n_efetivo_confinado_min - total_abertura_pt_min
                if hh_fora_min is None and total_atividade_min is not None:
                    try:
                        hh_fora_min = int(total_atividade_min) - int(total_confinado_min or 0) - int(total_n_efetivo_confinado_min or 0) - int(total_abertura_pt_min or 0)
                        if hh_fora_min < 0:
                            hh_fora_min = 0
                    except Exception:
                        hh_fora_min = 0

                # 3) Fallback final: usar POB * presence_hours - hh_confinado
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
                        # sem dados úteis; pular este RDO
                        continue

                # Acrescentar ao contador (converter para horas)
                try:
                    horas = round(float(hh_fora_min) / 60.0, 2)
                    counter[d] += horas
                except Exception:
                    continue
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

                    # Primeiro, tentar usar cumulativos por tanque (quando existir)
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
                                            # sem leitura anterior: usar valor diário por tanque se houver (ensacamento_dia), senão usar rt_cum
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
                                    # fallback para campo diário do tanque
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
                        # fallback para campo no RDO
                        try:
                            ensacamento = getattr(rdo, 'ensacamento', None) or 0
                            counter[d] += int(ensacamento)
                        except Exception:
                            pass
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

                    # Preferir cumulativos por tanque quando disponíveis
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
                                            # sem leitura anterior: usar tambores_dia se existir, senão usar rt_cum
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
def rdo_residuos_liquido_por_dia(request):
    """Retorna M³ de resíduo líquido removido por dia (campo total_liquido do RDO)."""
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
            qs = qs.filter(ordem_servico_id=os_existente)
            logger.info(f"[RESIDUO_LIQUIDO] Filtro OS: {os_existente}, RDOs: {qs.count()}")
        
        from collections import Counter
        counter = Counter()
        total_rdos = qs.count()
        rdos_with_liquido = 0
        sample_nonzero = []
        sample_all = []

        for rdo in qs:
            try:
                # Usar `data` como a referência de data do RDO (campo principal)
                rdo_date = getattr(rdo, 'data', None)
                if rdo_date:
                    d = rdo_date.strftime('%Y-%m-%d')

                    def _to_float_safe(x):
                        try:
                            return float(x or 0)
                        except Exception:
                            return 0.0

                    # CAMPOS QUE REPRESENTAM LÍQUIDO REMOVIDO (não capacidade do tanque):
                    # - vazão (`bombeio`): vazão de bombeio (m3/h) — NÃO somar como volume
                    # - quantidade_bombeada: quantidade bombeada (m³)
                    # - total_liquido: total de líquido removido (litros ou m³)
                    # IMPORTANTE: volume_tanque_exec é CAPACIDADE, não líquido removido!
                    
                    val_bombeio = getattr(rdo, 'bombeio', None)
                    val_quantidade_bombeada = getattr(rdo, 'quantidade_bombeada', None)
                    # Preferir campo cumulativo quando disponível (mais confiável)
                    val_total_liquido = getattr(rdo, 'total_liquido', None)
                    val_total_liquido_cum = getattr(rdo, 'total_liquido_cumulativo', None)
                    
                    # Normalizar volumes: campos podem estar em litros ou m3.
                    # Heurística simples: valores absolutos maiores que 100 são provavelmente litros -> converter para m3.
                    def _normalize_volume(v):
                        f = _to_float_safe(v)
                        if abs(f) > 100:
                            try:
                                return f / 1000.0
                            except Exception:
                                return f
                        return f

                    # Escolher a melhor fonte de volume para o RDO principal evitando dupla contagem.
                    # Preferir `total_liquido` quando presente; caso contrário, usar `quantidade_bombeada`.
                    liquido = 0.0
                    t_total = _to_float_safe(val_total_liquido)
                    # não usar `bombeio` (vazão) como volume
                    t_quant = _to_float_safe(val_quantidade_bombeada)

                    # Preferir cumulativo do RDO quando presente e não-zero
                    used_source_rdo = 'none'
                    t_total_cum = _to_float_safe(val_total_liquido_cum)
                    if t_total_cum and t_total_cum != 0:
                        try:
                            # tentar buscar RDO anterior no mesmo tanque para calcular delta
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
                                if delta_rdo != 0:
                                    liquido = _normalize_volume(delta_rdo)
                                    used_source_rdo = 'rdo_cumulativo_delta'
                                else:
                                    # delta zero -> fallback para campos explícitos
                                    if t_total and t_total != 0:
                                        liquido = _normalize_volume(t_total)
                                        used_source_rdo = 'rdo_total'
                                    else:
                                        liquido = _normalize_volume(t_quant)
                                        used_source_rdo = 'quantidade_bombeada'
                            except Exception:
                                # fallback em caso de erro
                                if t_total and t_total != 0:
                                    liquido = _normalize_volume(t_total)
                                    used_source_rdo = 'rdo_total'
                                else:
                                    liquido = _normalize_volume(t_quant)
                                    used_source_rdo = 'quantidade_bombeada'
                        else:
                            # sem leitura anterior: usar campo explícito se existir, senão usar cumulativo (último recurso)
                            if t_total and t_total != 0:
                                liquido = _normalize_volume(t_total)
                                used_source_rdo = 'rdo_total'
                            else:
                                liquido = _normalize_volume(t_total_cum)
                                used_source_rdo = 'rdo_total_cum_fallback'
                    elif t_total and t_total != 0:
                        liquido = _normalize_volume(t_total)
                        used_source_rdo = 'rdo_total'
                    else:
                        # usar quantidade_bombeada quando não há total_liquido
                        liquido = _normalize_volume(t_quant)
                        used_source_rdo = 'quantidade_bombeada'

                    # Se ainda zero, tentar derivar de residuos_totais - residuos_solidos
                    if liquido == 0.0:
                        r_tot = getattr(rdo, 'residuos_totais', None) or getattr(rdo, 'total_residuos', None)
                        r_sol = getattr(rdo, 'residuos_solidos', None) or getattr(rdo, 'total_solidos', None)
                        if r_tot is not None or r_sol is not None:
                            liquido = _normalize_volume(_to_float_safe(r_tot) - _to_float_safe(r_sol))

                    # Adicionar contribuições dos tanques associados (se houver). Para evitar dupla contagem,
                    # usar apenas campos explícitos por tanque (`total_liquido`) e NORMALIZAR unidades.
                    try:
                        if hasattr(rdo, 'tanques'):
                            tank_sum = 0.0
                            for rt in rdo.tanques.all():
                                rt_total = getattr(rt, 'total_liquido', None)
                                rt_total_cum = getattr(rt, 'total_liquido_cumulativo', None)
                                added = 0.0
                                used_source = 'none'
                                # Quando houver cumulativo por tanque, preferir o delta entre leituras
                                if rt_total_cum is not None and float(rt_total_cum or 0) != 0:
                                    try:
                                        # buscar registro anterior do mesmo tanque (por tanque_codigo) com data anterior ao RDO atual
                                        PrevModel = type(rt)
                                        prev = PrevModel.objects.filter(tanque_codigo=getattr(rt, 'tanque_codigo', None), rdo__data__lt=rdo_date).order_by('-rdo__data').first()
                                    except Exception:
                                        prev = None

                                    prev_cum = getattr(prev, 'total_liquido_cumulativo', None) if prev is not None else None
                                    try:
                                        if prev_cum is not None:
                                            delta = float(rt_total_cum or 0) - float(prev_cum or 0)
                                            if delta != 0:
                                                added = _normalize_volume(delta)
                                                used_source = 'cumulativo_delta'
                                            else:
                                                # delta zero -> tentar fallback em campo explícito
                                                if rt_total is not None and float(rt_total or 0) != 0:
                                                    added = _normalize_volume(rt_total)
                                                    used_source = 'rt_total'
                                        else:
                                            # não há leitura anterior: usar campo explícito se existir, senão usar cumulativo (último recurso)
                                            if rt_total is not None and float(rt_total or 0) != 0:
                                                added = _normalize_volume(rt_total)
                                                used_source = 'rt_total'
                                            else:
                                                added = _normalize_volume(rt_total_cum)
                                                used_source = 'rt_total_cum_fallback'
                                    except Exception:
                                        # Em caso de erro na comparação, fallback para campos explícitos
                                        try:
                                            if rt_total is not None and float(rt_total or 0) != 0:
                                                added = _normalize_volume(rt_total)
                                                used_source = 'rt_total'
                                        except Exception:
                                            pass
                                elif rt_total is not None and float(rt_total or 0) != 0:
                                    added = _normalize_volume(rt_total)
                                    used_source = 'rt_total'

                                # tentar derivar do diff por tanque quando não há valores explícitos
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

                                # Anotar fonte usada para debug (apenas primeiras amostras)
                                if len(sample_all) < 5:
                                    try:
                                        sample_all.append({'rt_id': getattr(rt, 'id', None), 'tanque_codigo': getattr(rt, 'tanque_codigo', None), 'used_source': used_source})
                                    except Exception:
                                        pass

                                # acumular separadamente para evitar dupla contagem com o RDO principal
                                tank_sum += added

                            # Se houver contribuições provenientes dos tanques, preferir essa soma para evitar dupla contagem
                            try:
                                if tank_sum and float(tank_sum) != 0:
                                    liquido = tank_sum
                                    used_source_rdo = 'from_tanks'
                            except Exception:
                                pass
                    except Exception:
                        pass

                    # Coletar amostra dos primeiros 5 RDOs (incluir fonte usada)
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
            # Buscar soma real agregando campos de volume líquido REMOVIDO
            # IMPORTANTE: volume_tanque_exec é CAPACIDADE, não líquido removido!
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
                    # não usar `bombeio` (vazão) como volume
                    t_quant = _to_float_safe_local(getattr(r, 'quantidade_bombeada', None))

                    if t_total and t_total != 0:
                        soma_liquido += _normalize_volume_local(t_total)
                    else:
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
                                rt_total_cum = getattr(rt, 'total_liquido_cumulativo', None)
                                added = 0.0
                                # preferir cumulativo do tanque quando disponível
                                if rt_total_cum is not None and float(rt_total_cum or 0) != 0:
                                    added = _normalize_volume_local(rt_total_cum)
                                elif rt_total is not None and float(rt_total or 0) != 0:
                                    added = _normalize_volume_local(rt_total)
                                # não usar rt.bombeio (vazão) como volume
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
                                # Usar LÍQUIDO REMOVIDO (preferir `total_liquido`), não somar `bombeio` (vazão)
                                vol = 0.0
                                try:
                                    # preferir cumulativo do tanque quando disponível
                                    vol = float(getattr(rt, 'total_liquido_cumulativo', None) or getattr(rt, 'total_liquido', 0) or 0)
                                except Exception:
                                    vol = 0.0
                                # Se não houver total_liquido, tentar derivar de residuos
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

                # Se não houve RdoTanque com código, usar campos do próprio RDO
                if not added:
                    tc = getattr(rdo, 'tanque_codigo', None) or getattr(rdo, 'nome_tanque', None) or 'Desconhecido'
                    tc = (str(tc).strip() if tc is not None else 'Desconhecido')
                    vol = 0.0
                    # não somar `bombeio` (vazão). Priorizar `total_liquido` e `quantidade_bombeada`.
                    try:
                        # preferir campo cumulativo no próprio RDO se existir
                        val = float(getattr(rdo, 'total_liquido_cumulativo', None) or getattr(rdo, 'total_liquido', 0) or 0)
                        if val == 0:
                            val = float(getattr(rdo, 'quantidade_bombeada', 0) or 0)
                        vol += val
                    except Exception:
                        pass
                    # Se não houver valores, calcular de residuos
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


# ============ VIEW PRINCIPAL DO DASHBOARD RDO ============

@login_required(login_url='/login/')
def rdo_dashboard_view(request):
    """Renderiza a página principal do dashboard de RDO com filtros e gráficos."""
    try:
        from .models import Cliente, Unidade, RDO, RdoTanque
        
        # Obter listas de clientes, unidades e supervisores para os filtros
        clientes = Cliente.objects.all().order_by('nome')
        unidades = Unidade.objects.all().order_by('nome')
        # Excluir usuários placeholder como 'A DEFINIR' do filtro de supervisores
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
        
        # Obter coordenadores únicos (campo texto em OrdemServico).
        # Deduplicação avançada: normalize (remove acentos/pontuação),
        # remover palavras de ligação (de/da/do) e sufixos (junior, filho, etc.),
        # e comparar conjuntos de tokens. Também permite que iniciais
        # (ex: 'T' em 'Ailton T de O Junior') sejam casadas com tokens
        # completos ('Teixeira'). Essa heurística agrupa variantes e evita
        # repetições causadas apenas por caixa/acento/ordenação.

        def remove_accents_norm(s):
            try:
                import unicodedata
                s2 = unicodedata.normalize('NFKD', s)
                return ''.join([c for c in s2 if not unicodedata.combining(c)])
            except Exception:
                return s

        def tokenize_name(s):
            # Upper, strip punctuation, split on whitespace
            s = remove_accents_norm(s).upper()
            # replace common punctuation with space
            for ch in ".,;:\/()[]{}-'\"`":
                s = s.replace(ch, ' ')
            tokens = [t.strip() for t in s.split() if t.strip()]
            # remove common stopwords and filler tokens
            fillers = {'DE','DA','DO','DOS','DAS','E','THE','LE','LA'}
            tokens = [t for t in tokens if t not in fillers]
            # strip common suffixes from end
            suffixes = {'JUNIOR','JR','FILHO','NETO','SNR','SR','II','III','IV'}
            if tokens and tokens[-1] in suffixes:
                tokens = tokens[:-1]
            return tokens

        def tokens_equivalent(a, b):
            # a and b are lists of tokens (already normalized uppercase, no fillers)
            if not a or not b:
                return False
            set_a = set(a)
            set_b = set(b)
            # exact token set equality
            if set_a == set_b:
                return True
            # subset/superset (one is contained in another)
            if set_a.issubset(set_b) or set_b.issubset(set_a):
                return True
            # try fuzzy matching with initials: match single-letter tokens to tokens starting with that letter
            match = 0
            total = max(len(a), len(b))
            # for each token in a try to find match in b
            for tok in a:
                if tok in set_b:
                    match += 1
                    continue
                if len(tok) == 1:
                    # token is an initial; match if any token in b starts with it
                    if any(bt.startswith(tok) for bt in b):
                        match += 1
                        continue
                # also allow tok to be prefix of any bt or vice-versa
                if any(bt.startswith(tok) or tok.startswith(bt) for bt in b):
                    match += 1
            # symmetric check to be fair
            for tok in b:
                if tok in set_a:
                    continue
                if len(tok) == 1 and any(at.startswith(tok) for at in a):
                    continue
            # decide threshold (>=60% tokens matched)
            return (match / float(total)) >= 0.6

        coordenadores_qs = OrdemServico.objects.values_list('coordenador', flat=True)

        # Carregar mapeamentos canônicos (se houver) e preparar tokens de variantes
        try:
            from .models import CoordenadorCanonical
            canon_list = list(CoordenadorCanonical.objects.all())
        except Exception:
            canon_list = []

        canon_variants = []  # list of tuples (canonical_name, [tokens_list1, tokens_list2, ...])
        for c in canon_list:
            variants = []
            try:
                variants = list(c.variants or [])
            except Exception:
                variants = []
            # sempre incluir o canonical_name como variante
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

        # Primeiro, coletar todos os nomes brutos únicos
        raw_list = [str(x).strip() for x in coordenadores_qs if x and str(x).strip()]
        unique_raw = []
        seen_raw_ci = set()
        for r in raw_list:
            kc = r.casefold()
            if kc not in seen_raw_ci:
                seen_raw_ci.add(kc)
                unique_raw.append(r)

        # Clusters: lista de dicts {leader: display_name, tokens: [...], members: [...]}
        clusters = []

        # Pre-build canon lookup tokens for faster matching
        canon_token_groups = []
        for canonical_name, variants_tokens in canon_variants:
            toks_groups = variants_tokens
            canon_token_groups.append((canonical_name, toks_groups))

        for s in unique_raw:
            toks = tokenize_name(s)
            if not toks:
                continue

            # 1) tentar mapear para um canônico conhecido
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
                # adicionar ao cluster do canônico (encontrar ou criar)
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

            # 2) heurística: tentar agrupar por tokens_equivalent com clusters existentes
            placed = False
            for cl in clusters:
                try:
                    if tokens_equivalent(toks, cl['tokens']):
                        cl['members'].append(s)
                        # atualizar tokens do líder se necessário (manter tokens mais ricos)
                        if len(toks) > len(cl['tokens']):
                            cl['tokens'] = toks
                            cl['leader'] = s
                        placed = True
                        break
                except Exception:
                    continue
            if placed:
                continue

            # 3) criar novo cluster
            clusters.append({'leader': s, 'tokens': toks, 'members': [s]})

        # Para cada cluster, escolher o nome a exibir - preferir nome canônico se houver,
        # senão escolher o membro mais descritivo (maior número de tokens / maior comprimento)
        result = []
        for cl in clusters:
            if cl.get('canonical'):
                display = cl['canonical']
            else:
                # escolher membro com mais tokens; em caso de empate escolher o mais longo
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
                    # Padronizar exibição do nome: Title Case (Primeiras letras maiúsculas)
                    display_norm = display.title()
                except Exception:
                    display_norm = display
                result.append(display_norm)

        # Preferir usar os `choices` declarados no campo `coordenador` do modelo
        # (quando a aplicação migrou para um campo com choices fixos).
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
        # Contagem resumida de OS por status (para o card de topo)
        try:
            statuses = ['Programada', 'Em Andamento', 'Paralizada', 'Finalizada', 'Cancelada']
            # Deduplicar por `numero_os`: escolher um representante por número (menor id)
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

        # Expor contagens como variáveis simples para evitar chaves com espaços
        os_programada_count = int(status_counts.get('Programada', 0))
        os_em_andamento_count = int(status_counts.get('Em Andamento', 0))
        os_paralizada_count = int(status_counts.get('Paralizada', 0))
        os_finalizada_count = int(status_counts.get('Finalizada', 0))
        os_cancelada_count = int(status_counts.get('Cancelada', 0))

        # Gerar resumo das operações (para tabela 'summary-operations') usando helper
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
