from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from django.http import JsonResponse
from django.db.models import Count, Avg
from django.db.models.functions import TruncDate
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
            qs = qs.filter(cliente__icontains=cliente)
        if unidade:
            qs = qs.filter(unidade__icontains=unidade)

        # cache básico para reduzir carga: chave baseada em parâmetros
        cache_key = f"ordens_por_dia|start={start}|end={end}|cliente={cliente or ''}|unidade={unidade or ''}"
        cached = cache.get(cache_key)
        if cached is not None:
            return JsonResponse(cached)
        qs = qs.annotate(day=TruncDate('data_inicio')).values('day').annotate(count=Count('id')).order_by('day')

        # construir mapa de datas contínuas para não pular dias sem ordens
        days = []
        values = []
        cur = start
        data_map = {item['day'].strftime('%Y-%m-%d'): item['count'] for item in qs}
        while cur <= end:
            ds = cur.strftime('%Y-%m-%d')
            days.append(ds)
            values.append(data_map.get(ds, 0))
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
        start_str = request.GET.get('start')
        end_str = request.GET.get('end')
        qs = OrdemServico.objects.all()
        if cliente:
            qs = qs.filter(cliente__icontains=cliente)
        if unidade:
            qs = qs.filter(unidade__icontains=unidade)
        # filtrar por intervalo de datas se informado
        try:
            if start_str:
                start = datetime.strptime(start_str, '%Y-%m-%d').date()
                qs = qs.filter(data_inicio__gte=start)
            if end_str:
                end = datetime.strptime(end_str, '%Y-%m-%d').date()
                qs = qs.filter(data_inicio__lte=end)
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
        start_str = request.GET.get('start')
        end_str = request.GET.get('end')
        qs = OrdemServico.objects.all()
        if cliente:
            qs = qs.filter(cliente__icontains=cliente)
        if unidade:
            qs = qs.filter(unidade__icontains=unidade)
        try:
            if start_str:
                start = datetime.strptime(start_str, '%Y-%m-%d').date()
                qs = qs.filter(data_inicio__gte=start)
            if end_str:
                end = datetime.strptime(end_str, '%Y-%m-%d').date()
                qs = qs.filter(data_inicio__lte=end)
        except Exception:
            pass

        # Usar cache para respostas semelhantes (cache tempo curto)
        cache_key = f"servicos_top={top}|cliente={cliente or ''}|unidade={unidade or ''}|start={start_str or ''}|end={end_str or ''}"
        cached = cache.get(cache_key)
        if cached is not None:
            return JsonResponse(cached)

        # Normalizar os serviços: preferir `servicos` (lista separada por vírgula) e usar `servico` como fallback
        from collections import Counter
        counter = Counter()
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
        start_str = request.GET.get('start')
        end_str = request.GET.get('end')
        qs = OrdemServico.objects.all()
        if unidade:
            qs = qs.filter(unidade__icontains=unidade)
        try:
            if start_str:
                start = datetime.strptime(start_str, '%Y-%m-%d').date()
                qs = qs.filter(data_inicio__gte=start)
            if end_str:
                end = datetime.strptime(end_str, '%Y-%m-%d').date()
                qs = qs.filter(data_inicio__lte=end)
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
        start_str = request.GET.get('start')
        end_str = request.GET.get('end')
        qs = OrdemServico.objects.all()
        if cliente:
            qs = qs.filter(cliente__icontains=cliente)
        if unidade:
            qs = qs.filter(unidade__icontains=unidade)
        try:
            if start_str:
                start = datetime.strptime(start_str, '%Y-%m-%d').date()
                qs = qs.filter(data_inicio__gte=start)
            if end_str:
                end = datetime.strptime(end_str, '%Y-%m-%d').date()
                qs = qs.filter(data_inicio__lte=end)
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
                qs = qs.filter(data_inicio__lte=end)
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
        # total geral
        total = OrdemServico.objects.count()

        # Contagem por status operacional (usar o campo `status_operacao` definido no modelo)
        # As categorias esperadas: 'Programada', 'Em Andamento', 'Paralizada', 'Finalizada'
        statuses = ['Programada', 'Em Andamento', 'Paralizada', 'Finalizada']
        status_counts = {s: OrdemServico.objects.filter(status_operacao__iexact=s).count() for s in statuses}

        # 'abertas' mapeia para ordens em andamento
        abertas = status_counts.get('Em Andamento', 0)

        # concluídas no mês: preferimos contar por status_operacao='Finalizada' e data_fim dentro do mês corrente
        hoje = datetime.today().date()
        inicio_mes = hoje.replace(day=1)
        concluidas_mes = OrdemServico.objects.filter(status_operacao__iexact='Finalizada', data_fim__gte=inicio_mes, data_fim__lte=hoje).count()

        # tempo médio de operação: média de dias_de_operacao quando preenchido (ignorar nulls)
        avg_days = OrdemServico.objects.filter(dias_de_operacao__isnull=False).aggregate(avg=Avg('dias_de_operacao'))['avg'] or 0

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
