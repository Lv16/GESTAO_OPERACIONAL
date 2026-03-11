from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.utils.dateparse import parse_date
from django.db.models import Sum, Count, Q, Max, Avg, FloatField
from django.db.models import Min
from django.db.models.functions import Coalesce
from django.db.models import DecimalField
import datetime
import traceback
import logging

from .models import RDO, RdoTanque, OrdemServico
from django.db.models import IntegerField
from django.db.models.functions import Coalesce
from django.core.cache import cache


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


def _apply_os_filter_to_rdo_qs(qs, raw):
    """Aplica filtro aceitando múltiplos IDs ou número_os em QuerySet de RDOs."""
    ids, others = _parse_os_tokens(raw)
    if not ids and not others:
        return qs
    from django.db.models import Q
    q = None
    if ids:
        # tentar corresponder tanto por FK `ordem_servico_id` (id da OS)
        # quanto por `ordem_servico__numero_os` (número/label da OS que o frontend envia)
        q_id = Q(ordem_servico_id__in=ids)
        q_num = Q()
        try:
            # comparar numero_os como string (algumas bases usam texto)
            q_num = Q(ordem_servico__numero_os__in=[str(x) for x in ids])
        except Exception:
            q_num = Q()
        q = q_id | q_num
    if others:
        q2 = None
        for token in others:
            part = Q(ordem_servico__numero_os__iexact=token) | Q(ordem_servico__numero_os__icontains=token)
            if q2 is None:
                q2 = part
            else:
                q2 |= part
        if q is None:
            q = q2
        else:
            q |= q2
    try:
        return qs.filter(q)
    except Exception:
        return qs


@require_GET
def get_ordens_servico(request):
    try:
        ordens = OrdemServico.objects.all().values('id', 'numero_os').order_by('-numero_os')
        items = [{'id': os['id'], 'numero_os': os['numero_os']} for os in ordens]
        ordens = (
            OrdemServico.objects
            .values('numero_os')
            .annotate(id=Min('id'))
            .order_by('-numero_os')
        )
        items = [{'id': o['id'], 'numero_os': o['numero_os']} for o in ordens]
        return JsonResponse({'success': True, 'items': items})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def summary_operations_data(params=None):
    try:
        logging.debug('summary_operations_data called with params: %s', params)
        import re

        cliente = params.get('cliente') if params else None
        unidade = params.get('unidade') if params else None
        start = params.get('start') if params else None
        end = params.get('end') if params else None
        os_existente = params.get('os_existente') if params else None
        coordenador = params.get('coordenador') if params else None
        status = params.get('status') if params else None
        tanque = params.get('tanque') if params else None
        supervisor = params.get('supervisor') if params else None

        def _split_tokens(raw):
            if not raw:
                return []
            parts = re.split(r'[;,]+', str(raw))
            return [p.strip() for p in parts if p and p.strip()]

        qs = OrdemServico.objects.all()
        if coordenador:
            try:
                field = OrdemServico._meta.get_field('coordenador')
                field_choices = getattr(field, 'choices', []) or []
                match = None
                for c in field_choices:
                    try:
                        if str(c[0]).lower() == str(coordenador).strip().lower():
                            match = c[0]
                            break
                    except Exception:
                        continue

                if match:
                    exact_qs = qs.filter(coordenador__iexact=match)
                    if exact_qs.exists():
                        qs = exact_qs
                    else:
                        try:
                            from .models import CoordenadorCanonical
                            canon_list = list(CoordenadorCanonical.objects.all())
                        except Exception:
                            canon_list = []

                        variants = []
                        for c in canon_list:
                            try:
                                if c.canonical_name.lower() == str(coordenador).strip().lower():
                                    variants = [c.canonical_name] + list(c.variants or [])
                                    break
                                for v in (c.variants or []):
                                    if str(v).lower() == str(coordenador).strip().lower():
                                        variants = [c.canonical_name] + list(c.variants or [])
                                        break
                            except Exception:
                                continue

                        if variants:
                            q = None
                            for v in variants:
                                if q is None:
                                    q = Q(coordenador__icontains=v)
                                else:
                                    q |= Q(coordenador__icontains=v)
                            if q is not None:
                                qs = qs.filter(q)
                        else:
                            qs = qs.filter(coordenador__icontains=match)
                else:
                    try:
                        from .models import CoordenadorCanonical
                        canon_list = list(CoordenadorCanonical.objects.all())
                    except Exception:
                        canon_list = []

                    variants = []
                    for c in canon_list:
                        try:
                            if c.canonical_name.lower() == str(coordenador).strip().lower():
                                variants = [c.canonical_name] + list(c.variants or [])
                                break
                            for v in (c.variants or []):
                                if str(v).lower() == str(coordenador).strip().lower():
                                    variants = [c.canonical_name] + list(c.variants or [])
                                    break
                        except Exception:
                            continue

                    if variants:
                        q = None
                        for v in variants:
                            if q is None:
                                q = Q(coordenador__icontains=v)
                            else:
                                q |= Q(coordenador__icontains=v)
                        if q is not None:
                            qs = qs.filter(q)
                    else:
                        qs = qs.filter(coordenador__icontains=coordenador.strip())
            except Exception:
                qs = qs.filter(coordenador__icontains=coordenador.strip())
        if cliente:
            tokens = _split_tokens(cliente)
            if tokens:
                q = None
                for t in tokens:
                    if q is None:
                        q = Q(Cliente__nome__icontains=t)
                    else:
                        q |= Q(Cliente__nome__icontains=t)
                if q is not None:
                    qs = qs.filter(q)
        if unidade:
            tokens = _split_tokens(unidade)
            if tokens:
                q = None
                for t in tokens:
                    if q is None:
                        q = Q(Unidade__nome__icontains=t)
                    else:
                        q |= Q(Unidade__nome__icontains=t)
                if q is not None:
                    qs = qs.filter(q)
        if tanque:
            try:
                tokens = _split_tokens(tanque)
                q_all = None
                for raw_t in tokens:
                    t = str(raw_t).strip()
                    from django.db.models import Q as _Q
                    t_q = None
                    if t.isdigit():
                        try:
                            t_q = _Q(rdos__tanques__id=int(t)) | _Q(tanque__icontains=t) | _Q(tanques__icontains=t)
                        except Exception:
                            t_q = _Q(rdos__tanques__tanque_codigo__icontains=t) | _Q(tanque__icontains=t) | _Q(tanques__icontains=t)
                    else:
                        # prefer exact code matches, else icontains
                        exact_qs = qs.filter(rdos__tanques__tanque_codigo__iexact=t)
                        if exact_qs.exists():
                            t_q = _Q(id__in=[o.id for o in exact_qs])
                        else:
                            t_q = _Q(rdos__tanques__tanque_codigo__icontains=t) | _Q(tanque__icontains=t) | _Q(tanques__icontains=t)
                    if t_q is not None:
                        if q_all is None:
                            q_all = t_q
                        else:
                            q_all |= t_q
                if q_all is not None:
                    qs = qs.filter(q_all)
            except Exception:
                try:
                    qs = qs.filter(rdos__tanques__tanque_codigo__icontains=str(tanque))
                except Exception:
                    pass
        if os_existente:
            tokens = _split_tokens(os_existente)
            if tokens:
                q_os = None
                ids = [int(t) for t in tokens if t.isdigit()]
                others = [t for t in tokens if not t.isdigit()]
                if ids:
                    try:
                        q_os = Q(id__in=ids) | Q(numero_os__in=[str(x) for x in ids])
                    except Exception:
                        q_os = Q(id__in=ids)
                for o in others:
                    part = Q(numero_os__iexact=o) | Q(numero_os__icontains=o)
                    if q_os is None:
                        q_os = part
                    else:
                        q_os |= part
                if q_os is not None:
                    qs = qs.filter(q_os)
        if supervisor:
            tokens = _split_tokens(supervisor)
            if tokens:
                q_sup = None
                for t in tokens:
                    part = Q(supervisor__username__icontains=t) | Q(supervisor__first_name__icontains=t) | Q(supervisor__last_name__icontains=t)
                    if q_sup is None:
                        q_sup = part
                    else:
                        q_sup |= part
                if q_sup is not None:
                    qs = qs.filter(q_sup)

        # Filtrar apenas por `status_operacao` conforme solicitado
        if status:
            try:
                s = str(status).strip()
                try:
                    OrdemServico._meta.get_field('status_operacao')
                    qs = qs.filter(status_operacao__iexact=s)
                except Exception:
                    # fallback: tentar por campo `rdos__ultimo_status` se existir
                    try:
                        qs = qs.filter(rdos__ultimo_status__icontains=s)
                    except Exception:
                        pass
            except Exception:
                pass
            except Exception:
                pass

            try:
                if start and end:
                    s = datetime.datetime.strptime(start, '%Y-%m-%d').date()
                    e = datetime.datetime.strptime(end, '%Y-%m-%d').date()
                    # Quando filtramos por `status` ou por `os_existente` explícito,
                    # aplicamos a janela de datas sobre a OS (data_inicio/data_fim)
                    # para permitir retornar OS mesmo sem RDOs na janela.
                    if status or os_existente:
                        qs = qs.filter(
                            Q(data_inicio__gte=s, data_inicio__lte=e) |
                            Q(data_fim__gte=s, data_fim__lte=e) |
                            Q(data_inicio__lte=s, data_fim__gte=e)
                        )
                    else:
                        qs = qs.filter(rdos__data__gte=s, rdos__data__lte=e)
                elif start:
                    s = datetime.datetime.strptime(start, '%Y-%m-%d').date()
                    if status or os_existente:
                        qs = qs.filter(Q(data_inicio__gte=s) | Q(data_fim__gte=s) | Q(data_inicio__lte=s, data_fim__gte=s))
                    else:
                        qs = qs.filter(rdos__data__gte=s)
                elif end:
                    e = datetime.datetime.strptime(end, '%Y-%m-%d').date()
                    if status or os_existente:
                        qs = qs.filter(Q(data_inicio__lte=e) | Q(data_fim__lte=e) | Q(data_inicio__lte=e, data_fim__gte=e))
                    else:
                        qs = qs.filter(rdos__data__lte=e)
            except Exception:
                pass

        qs = qs.distinct()

        # Por padrão, exibimos apenas OS que possuam RDOs associados para evitar linhas vazias.
        # Porém, quando o usuário está filtrando por `coordenador`, por `status` ou por
        # `os_existente` explícito, queremos permitir que sejam retornadas OS mesmo sem
        # RDOs na janela de pesquisa (ex.: buscar uma OS específica que não tem RDOs).
        # Portanto aplicamos a restrição somente quando não há filtro de coordenador,
        # nem filtro de status, e nem filtro explícito de OS.
        if not coordenador and not status and not os_existente:
            qs = qs.filter(rdos__isnull=False)

        agg_qs = qs.annotate(
            rdos_count=Coalesce(Count('rdos', distinct=True), 0, output_field=IntegerField()),
            avg_pob=Coalesce(Avg('pob'), 0, output_field=FloatField()),
            total_volume_tanque=Coalesce(Sum('rdos__tanques__volume_tanque_exec'), 0, output_field=DecimalField()),
        )

        ordered_ops = list(agg_qs.order_by('-numero_os')[:200])

        s_date = None
        e_date = None
        try:
            if start:
                s_date = datetime.datetime.strptime(start, '%Y-%m-%d').date()
            if end:
                e_date = datetime.datetime.strptime(end, '%Y-%m-%d').date()
        except Exception:
            s_date = None
            e_date = None

        op_ids = [getattr(o, 'id', None) for o in ordered_ops if getattr(o, 'id', None)]
        rdo_scope_qs = RDO.objects.filter(ordem_servico_id__in=op_ids)
        if s_date and e_date:
            rdo_scope_qs = rdo_scope_qs.filter(data__gte=s_date, data__lte=e_date)
        elif s_date:
            rdo_scope_qs = rdo_scope_qs.filter(data__gte=s_date)
        elif e_date:
            rdo_scope_qs = rdo_scope_qs.filter(data__lte=e_date)

        rdos_by_os = {}
        rdo_id_scope = []
        for r in rdo_scope_qs.order_by('ordem_servico_id', 'data', 'id'):
            try:
                os_id = getattr(r, 'ordem_servico_id', None)
                if os_id is None:
                    continue
                rdos_by_os.setdefault(os_id, []).append(r)
                rid = getattr(r, 'id', None)
                if rid:
                    rdo_id_scope.append(rid)
            except Exception:
                continue

        def _to_int_safe_local(v):
            try:
                return int(v or 0)
            except Exception:
                try:
                    return int(float(v or 0))
                except Exception:
                    return 0

        rt_totals_by_os = {}
        if rdo_id_scope:
            rt_scope_rows = RdoTanque.objects.filter(rdo_id__in=rdo_id_scope).values(
                'rdo__ordem_servico_id',
                'ensacamento_dia',
                'tambores_dia',
            )
            for row in rt_scope_rows:
                os_id = row.get('rdo__ordem_servico_id')
                if not os_id:
                    continue
                ens = _to_int_safe_local(row.get('ensacamento_dia'))
                tam = _to_int_safe_local(row.get('tambores_dia'))
                cur = rt_totals_by_os.setdefault(os_id, {'ens': 0, 'tam': 0})
                cur['ens'] += ens
                cur['tam'] += tam

        out = []
        for o in ordered_ops:
            sup = getattr(o, 'supervisor', None)
            cliente_obj = getattr(o, 'Cliente', None) or getattr(o, 'cliente', None)
            if cliente_obj:
                cliente_name = getattr(cliente_obj, 'nome', None) or str(cliente_obj)
            else:
                cliente_name = ''

            unidade_obj = getattr(o, 'Unidade', None) or getattr(o, 'unidade', None)
            if unidade_obj:
                unidade_name = getattr(unidade_obj, 'nome', None) or str(unidade_obj)
            else:
                unidade_name = ''

            supervisor_name = ''
            if sup:
                try:
                    full = sup.get_full_name() if hasattr(sup, 'get_full_name') else ''
                except Exception:
                    full = ''
                if full and str(full).strip():
                    supervisor_name = str(full).strip()
                else:
                    supervisor_name = getattr(sup, 'username', None) or str(sup)

            rdo_rows = list(rdos_by_os.get(getattr(o, 'id', None), []))

            sum_operadores = 0
            max_operadores = 0
            operadores_count = 0
            sum_ensacamento = 0
            sum_tambores = 0
            sum_hh_efetivo_min = 0
            sum_hh_nao_min = 0
            for r in rdo_rows:
                try:
                    op_val = int(getattr(r, 'operadores_simultaneos', 0) or 0)
                    sum_operadores += op_val
                    operadores_count += 1
                    if op_val > max_operadores:
                        max_operadores = op_val
                except Exception:
                    pass
                try:
                    # Sum daily ensacamento (not the per-rdo cumulative) to avoid double-counting
                    sum_ensacamento += int(getattr(r, 'ensacamento', 0) or 0)
                except Exception:
                    pass
                try:
                    sum_tambores += int(getattr(r, 'tambores', 0) or 0)
                except Exception:
                    pass
                try:
                    sum_hh_efetivo_min += int(getattr(r, 'total_atividades_efetivas_min', 0) or 0)
                except Exception:
                    pass
                try:
                    nao_fora = getattr(r, 'total_atividades_nao_efetivas_fora_min', None)
                except Exception:
                    nao_fora = None
                if nao_fora is None:
                    try:
                        nao_fora = getattr(r, 'total_nao_efetivas_fora_min', None)
                    except Exception:
                        nao_fora = None
                try:
                    nao_fora = int(nao_fora or 0)
                except Exception:
                    nao_fora = 0
                try:
                    sum_hh_nao_min += int(nao_fora)
                except Exception:
                    pass

            sum_ensacamento = int(rt_totals_by_os.get(getattr(o, 'id', None), {}).get('ens') or 0)
            sum_tambores = int(rt_totals_by_os.get(getattr(o, 'id', None), {}).get('tam') or 0)

            try:
                sum_hh_efetivo = int(round(sum_hh_efetivo_min / 60.0))
            except Exception:
                sum_hh_efetivo = 0
            try:
                sum_hh_nao_efetivo = int(sum_hh_nao_min // 60)
            except Exception:
                sum_hh_nao_efetivo = 0
            try:
                avg_operadores = int(round((float(sum_operadores) / float(operadores_count)))) if operadores_count else 0
            except Exception:
                avg_operadores = 0

            # Calcular dias de movimentação
            dias_movimentacao = 0
            try:
                # Priorizar dias_de_operacao_frente se disponível, senão usar dias_de_operacao
                dias_frente = getattr(o, 'dias_de_operacao_frente', 0) or 0
                dias_normal = getattr(o, 'dias_de_operacao', 0) or 0
                dias_movimentacao = dias_frente if dias_frente > 0 else dias_normal
                
                # Se não houver dados salvos, calcular a partir das datas
                # Não conta o dia atual: dias = hoje - data_inicio (sem +1)
                if dias_movimentacao <= 0:
                    data_inicio = getattr(o, 'data_inicio_frente', None) or getattr(o, 'data_inicio', None)
                    data_fim = getattr(o, 'data_fim_frente', None) or getattr(o, 'data_fim', None)
                    
                    if data_inicio and data_fim:
                        delta_days = (data_fim - data_inicio).days
                        dias_movimentacao = delta_days if delta_days > 0 else 1
                    elif data_inicio and not data_fim:
                        # Se só tem data de início, calcular até hoje (sem contar hoje)
                        from datetime import date
                        hoje = date.today()
                        delta_days = (hoje - data_inicio).days
                        dias_movimentacao = delta_days if delta_days > 0 else 1
                    
                # Garantir que sempre tenha pelo menos 1 dia
                if dias_movimentacao <= 0:
                    dias_movimentacao = 1
            except Exception:
                # Em caso de erro, usar 1 como padrão
                dias_movimentacao = 1

            out.append({
                'id': o.id,
                'numero_os': getattr(o, 'numero_os', None),
                'cliente': cliente_name,
                'unidade': unidade_name,
                'supervisor': supervisor_name,
                'rdos_count': int(len(rdo_rows)),
                'total_ensacamento': int(sum_ensacamento or 0),
                'total_tambores': int(sum_tambores or 0),
                'sum_operadores_simultaneos': avg_operadores,
                'max_operadores_simultaneos': int(max_operadores or 0),
                'sum_hh_nao_efetivo': sum_hh_nao_efetivo,
                'sum_hh_efetivo': int(sum_hh_efetivo),
                'avg_pob': float(getattr(o, 'avg_pob', 0) or 0),
                'total_volume_tanque': float(getattr(o, 'total_volume_tanque', 0) or 0),
                'dias_movimentacao': int(dias_movimentacao),
            })

        return out
    except Exception:
        # Log full traceback to help debugging of filters returning empty results
        logging.exception('Erro em summary_operations_data')
        try:
            import traceback as _tb
            print(_tb.format_exc())
        except Exception:
            pass
        return []

@require_GET
def summary_operations_json(request):
    try:
        params = {
            'cliente': request.GET.get('cliente'),
            'unidade': request.GET.get('unidade'),
            'start': request.GET.get('start'),
            'end': request.GET.get('end'),
            'os_existente': request.GET.get('os_existente') or request.GET.get('ordem_servico'),
            'supervisor': request.GET.get('supervisor'),
            'tanque': request.GET.get('tanque'),
            'coordenador': request.GET.get('coordenador'),
            'status': request.GET.get('status'),
        }
        # debug logging removed
        data = summary_operations_data(params)
        return JsonResponse({'success': True, 'items': data})
    except Exception as e:
        logging.exception('Erro em summary_operations_json')
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@require_GET
def get_os_movimentacoes_count(request):
    try:
        cliente = request.GET.get('cliente')
        unidade = request.GET.get('unidade')

        qs = OrdemServico.objects.all()

        if cliente:
            c = cliente.strip()
            if c.isdigit():
                try:
                    qs = qs.filter(Cliente__id=int(c))
                except Exception:
                    qs = qs.filter(Cliente__nome__icontains=c)
            else:
                qs = qs.filter(Cliente__nome__icontains=c)

        if unidade:
            u = unidade.strip()
            if u.isdigit():
                try:
                    qs = qs.filter(Unidade__id=int(u))
                except Exception:
                    qs = qs.filter(Unidade__nome__icontains=u)
            else:
                qs = qs.filter(Unidade__nome__icontains=u)

        agg = (
            qs.values('numero_os')
            .annotate(count=Coalesce(Count('id'), 0))
            .order_by('-numero_os')
        )

        items = []
        for row in agg:
            numero = row.get('numero_os')
            items.append({
                'numero_os': numero,
                'count': int(row.get('count') or 0)
            })

        return JsonResponse({'success': True, 'items': items})
    except Exception as e:
        logging.exception('Erro em get_os_movimentacoes_count')
        tb = traceback.format_exc()
        return JsonResponse({'success': False, 'error': str(e), 'traceback': tb}, status=500)

@require_GET
def top_supervisores(request):
    start = request.GET.get('start')
    end = request.GET.get('end')
    supervisor_filter = request.GET.get('supervisor')
    cliente = request.GET.get('cliente')
    unidade = request.GET.get('unidade')
    tanque = request.GET.get('tanque')
    ordem_servico = request.GET.get('ordem_servico')

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
        qs = RDO.objects.select_related('ordem_servico__supervisor').filter(
            data__gte=start_date,
            data__lte=end_date
        )

        os_selecionada = request.GET.get('os_existente') or ordem_servico
        coordenador = request.GET.get('coordenador')

        def _split_tokens(raw):
            import re
            if not raw:
                return []
            parts = re.split(r'[;,]+', str(raw))
            return [p.strip() for p in parts if p and p.strip()]

        def remove_accents_norm(s):
            try:
                import unicodedata
                s2 = unicodedata.normalize('NFKD', s)
                return ''.join([c for c in s2 if not unicodedata.combining(c)])
            except Exception:
                return s

        def tokenize_name(s):
            s = remove_accents_norm(s).upper()
            for ch in ".,;:\\/()[]{}-'\"`":
                s = s.replace(ch, ' ')
            tokens = [t.strip() for t in s.split() if t.strip()]
            fillers = {'DE', 'DA', 'DO', 'DOS', 'DAS', 'E', 'THE', 'LE', 'LA'}
            tokens = [t for t in tokens if t not in fillers]
            suffixes = {'JUNIOR', 'JR', 'FILHO', 'NETO', 'SNR', 'SR', 'II', 'III', 'IV'}
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
            return (match / float(total)) >= 0.6

        def get_coordenador_variants(raw_name):
            try:
                if not raw_name:
                    return []
                inp = str(raw_name).strip()
                if not inp:
                    return []
                try:
                    from .models import CoordenadorCanonical
                    canon_list = list(CoordenadorCanonical.objects.all())
                except Exception:
                    canon_list = []
                for c in canon_list:
                    try:
                        if c.canonical_name.lower() == inp.lower():
                            return [c.canonical_name] + list(c.variants or [])
                        for v in (c.variants or []):
                            if str(v).lower() == inp.lower():
                                return [c.canonical_name] + list(c.variants or [])
                    except Exception:
                        continue
                toks = tokenize_name(inp)
                if not toks:
                    return []
                for c in canon_list:
                    try:
                        variants = [c.canonical_name] + list(c.variants or [])
                        for v in variants:
                            vt = tokenize_name(str(v))
                            if vt and tokens_equivalent(toks, vt):
                                return [c.canonical_name] + list(c.variants or [])
                    except Exception:
                        continue
            except Exception:
                return []
            return []

        if supervisor_filter:
            sup_tokens = _split_tokens(supervisor_filter)
            if sup_tokens:
                q_sup = None
                for tok in sup_tokens:
                    part = (
                        Q(ordem_servico__supervisor__username__icontains=tok)
                        | Q(ordem_servico__supervisor__first_name__icontains=tok)
                        | Q(ordem_servico__supervisor__last_name__icontains=tok)
                    )
                    q_sup = part if q_sup is None else (q_sup | part)
                if q_sup is not None:
                    qs = qs.filter(q_sup)

        if cliente:
            c_tokens = _split_tokens(cliente)
            if c_tokens:
                q_cli = None
                for tok in c_tokens:
                    part = Q(ordem_servico__Cliente__nome__icontains=tok)
                    q_cli = part if q_cli is None else (q_cli | part)
                if q_cli is not None:
                    qs = qs.filter(q_cli)

        if unidade:
            u_tokens = _split_tokens(unidade)
            if u_tokens:
                q_uni = None
                for tok in u_tokens:
                    part = Q(ordem_servico__Unidade__nome__icontains=tok)
                    q_uni = part if q_uni is None else (q_uni | part)
                if q_uni is not None:
                    qs = qs.filter(q_uni)

        if tanque:
            t_tokens = _split_tokens(tanque)
            if t_tokens:
                q_tanque = None
                for tok in t_tokens:
                    part = (
                        Q(tanque_codigo__icontains=tok)
                        | Q(nome_tanque__icontains=tok)
                        | Q(tanques__tanque_codigo__icontains=tok)
                    )
                    q_tanque = part if q_tanque is None else (q_tanque | part)
                if q_tanque is not None:
                    qs = qs.filter(q_tanque)

        if os_selecionada:
            qs = _apply_os_filter_to_rdo_qs(qs, os_selecionada)

        if coordenador:
            variants = get_coordenador_variants(coordenador)
            if variants:
                q = None
                for v in variants:
                    part = Q(ordem_servico__coordenador__icontains=v)
                    q = part if q is None else (q | part)
                if q is not None:
                    qs = qs.filter(q)
            else:
                qs = qs.filter(ordem_servico__coordenador__icontains=coordenador)

        qs = qs.distinct()

        sup_rows = qs.values(
            'ordem_servico__supervisor__id',
            'ordem_servico__supervisor__username',
            'ordem_servico__supervisor__first_name',
            'ordem_servico__supervisor__last_name',
        ).annotate(
            rd_count=Count('id', distinct=True)
        )

        supervisors = {}
        for row in sup_rows:
            sup_id = row.get('ordem_servico__supervisor__id')
            if not sup_id:
                continue
            username = row.get('ordem_servico__supervisor__username') or ''
            fname = row.get('ordem_servico__supervisor__first_name') or ''
            lname = row.get('ordem_servico__supervisor__last_name') or ''
            name = ((fname + ' ' + lname).strip()) or username or f'ID {sup_id}'
            supervisors[sup_id] = {
                'supervisor_id': sup_id,
                'username': username,
                'name': name,
                'rd_count': int(row.get('rd_count') or 0),
                'value_raw': 0.0,
                'capacity_by_tank': {},
            }

        if not supervisors:
            chart = {
                'labels': [],
                'datasets': [{'label': 'Índice normalizado (%)', 'data': []}],
                'options': {'scales': {'x': {'grid': {'display': True, 'color': 'rgba(200, 200, 200, 0.2)'}}, 'y': {'grid': {'display': True, 'color': 'rgba(200, 200, 200, 0.2)'}}}},
            }
            return JsonResponse({'success': True, 'items': [], 'chart': chart})

        rt_rows = RdoTanque.objects.filter(rdo__in=qs).values(
            'id',
            'rdo_id',
            'rdo__ordem_servico_id',
            'rdo__ordem_servico__supervisor__id',
            'tanque_codigo',
            'nome_tanque',
            'volume_tanque_exec',
            'total_liquido',
            'bombeio',
            'residuos_totais',
            'residuos_solidos',
        )

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

        def _liquido_from_rt(row):
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

        def _tank_group_key(row):
            import re
            os_id = row.get('rdo__ordem_servico_id') or 0
            raw = row.get('tanque_codigo') or row.get('nome_tanque') or f"rt-{row.get('id')}"
            token = re.sub(r'\s+', ' ', str(raw or '').strip()).casefold()
            if not token:
                token = f"rt-{row.get('id')}"
            return (os_id, token)

        for row in rt_rows:
            sup_id = row.get('rdo__ordem_servico__supervisor__id')
            if not sup_id:
                continue
            st = supervisors.get(sup_id)
            if st is None:
                continue

            st['value_raw'] += _liquido_from_rt(row)

            cap = _to_float_safe(row.get('volume_tanque_exec'))
            if cap > 0:
                key = _tank_group_key(row)
                prev = st['capacity_by_tank'].get(key, 0.0)
                if cap > prev:
                    st['capacity_by_tank'][key] = cap

        items = []
        for sup_id, st in supervisors.items():
            raw_total = float(st.get('value_raw') or 0.0)
            capacity_total = float(sum(st.get('capacity_by_tank', {}).values()) or 0.0)
            if capacity_total > 0:
                value = (raw_total / capacity_total) * 100.0
            else:
                # Mantém compatibilidade com a UI atual quando capacidade não está disponível.
                value = raw_total

            items.append({
                'supervisor_id': sup_id,
                'username': st.get('username') or '',
                'name': st.get('name') or st.get('username') or f'ID {sup_id}',
                'value': round(value, 2),
                'value_raw': round(raw_total, 3),
                'capacity_total': round(capacity_total, 3),
                'rd_count': int(st.get('rd_count') or 0),
            })

        items.sort(key=lambda x: x['value'], reverse=True)
        top_items = items[:20]

        labels = [it['name'] for it in top_items]
        data_values = [it['value'] for it in top_items]

        chart = {
            'labels': labels,
            'datasets': [
                {
                    'label': 'Índice normalizado (%)',
                    'data': data_values,
                }
            ],
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

        return JsonResponse({'success': True, 'items': top_items, 'chart': chart})
    except Exception as e:
        logging.exception('Erro em top_supervisores')
        tb = traceback.format_exc()
        return JsonResponse({'success': False, 'error': str(e), 'traceback': tb}, status=500)


@require_GET
def metodos_eficacia_por_dias(request):
    """Calcula eficácia por método considerando status Finalizada/Em Andamento.

    Regras:
    - Usa apenas OS com status de operação em Finalizada ou Em Andamento.
    - "Finaliza primeiro" é modelado por menor média de dias das finalizadas.
    - Índice de eficácia combina taxa de conclusão e velocidade de finalização.
    """
    try:
        start = request.GET.get('start')
        end = request.GET.get('end')
        cliente = request.GET.get('cliente')
        unidade = request.GET.get('unidade')
        os_existente = request.GET.get('os_existente')

        try:
            start_date = parse_date(start) if start else None
            end_date = parse_date(end) if end else None
        except Exception:
            start_date = None
            end_date = None

        qs = OrdemServico.objects.all()
        if cliente:
            qs = qs.filter(Cliente__nome__icontains=cliente)
        if unidade:
            qs = qs.filter(Unidade__nome__icontains=unidade)

        # filtro temporal será aplicado em Python para considerar também
        # data_inicio_frente/data_fim_frente e OS em andamento (data_fim nula)

        # filtrar por OSs explicitamente informadas (aceita CSV com ',' ou ';')
        if os_existente:
            import re
            parts = [p.strip() for p in re.split(r'[;,]+', str(os_existente)) if p and p.strip()]
            if parts:
                q_or = Q()
                ids = [int(p) for p in parts if p.isdigit()]
                if ids:
                    q_or |= Q(id__in=ids)
                for token in [p for p in parts if not p.isdigit()]:
                    q_or |= Q(numero_os__icontains=token) | Q(numero_os__iexact=token)
                try:
                    qs = qs.filter(q_or)
                except Exception:
                    pass

        from datetime import date
        hoje = date.today()

        def _normalize_status(raw):
            try:
                import unicodedata
                txt = str(raw or '').strip().lower()
                txt = ''.join(c for c in unicodedata.normalize('NFKD', txt) if not unicodedata.combining(c))
                txt = txt.replace('_', ' ').replace('-', ' ')
            except Exception:
                txt = str(raw or '').strip().lower()

            if 'finaliz' in txt:
                return 'finalizada'
            if ('andamento' in txt) or ('em andamento' in txt):
                return 'em_andamento'
            return None

        def _in_period(os_obj):
            if not start_date and not end_date:
                return True

            inicio = getattr(os_obj, 'data_inicio_frente', None) or getattr(os_obj, 'data_inicio', None)
            fim = getattr(os_obj, 'data_fim_frente', None) or getattr(os_obj, 'data_fim', None)

            # sem datas suficientes: não excluir para não perder operações válidas
            if not inicio and not fim:
                return True
            if not inicio and fim:
                inicio = fim
            if inicio and not fim:
                fim = hoje

            try:
                if start_date and end_date:
                    return (inicio <= end_date) and (fim >= start_date)
                if start_date:
                    return fim >= start_date
                if end_date:
                    return inicio <= end_date
                return True
            except Exception:
                return True

        def _collect_by_method(only_period=True):
            out = {}
            for o in qs:
                try:
                    if only_period and not _in_period(o):
                        continue

                    st = _normalize_status(getattr(o, 'status_operacao', None))
                    if st not in ('finalizada', 'em_andamento'):
                        continue

                    metodo = getattr(o, 'metodo', None) or 'Indefinido'
                    data_inicio = getattr(o, 'data_inicio_frente', None) or getattr(o, 'data_inicio', None)
                    data_fim = getattr(o, 'data_fim_frente', None) or getattr(o, 'data_fim', None)

                    dias = 0
                    if st == 'finalizada':
                        if data_inicio and data_fim:
                            delta = (data_fim - data_inicio).days
                            dias = delta if delta > 0 else 1
                    else:
                        if data_inicio:
                            delta = (hoje - data_inicio).days
                            dias = delta if delta > 0 else 1

                    if not dias or dias <= 0:
                        dias = getattr(o, 'dias_de_operacao_frente', None) or getattr(o, 'dias_de_operacao', None) or 0
                    if not dias or dias <= 0:
                        dias = 1

                    try:
                        dias = int(dias)
                    except Exception:
                        dias = 1

                    bucket = out.setdefault(metodo, {
                        'finalizadas_dias': [],
                        'andamento_dias': [],
                    })
                    if st == 'finalizada':
                        bucket['finalizadas_dias'].append(dias)
                    else:
                        bucket['andamento_dias'].append(dias)
                except Exception:
                    continue
            return out

        by_method = _collect_by_method(only_period=True)
        period_fallback = False
        if not by_method and (start_date or end_date):
            by_method = _collect_by_method(only_period=False)
            period_fallback = bool(by_method)

        metrics = []
        best_avg_final = None
        for metodo, vals in by_method.items():
            fin = vals.get('finalizadas_dias', [])
            andam = vals.get('andamento_dias', [])
            if not fin and not andam:
                continue

            fin_count = len(fin)
            and_count = len(andam)
            total_count = fin_count + and_count

            avg_fin = (float(sum(fin)) / float(fin_count)) if fin_count else None
            avg_and = (float(sum(andam)) / float(and_count)) if and_count else None

            if avg_fin is not None:
                if best_avg_final is None or avg_fin < best_avg_final:
                    best_avg_final = avg_fin

            metrics.append({
                'metodo': metodo,
                'finalizadas_count': fin_count,
                'andamento_count': and_count,
                'total_count': total_count,
                'avg_days_finalizadas': avg_fin,
                'avg_days_andamento': avg_and,
            })

        labels = []
        efficacy_index = []
        finalizadas_counts = []
        andamento_counts = []
        avg_days_finalizadas = []
        avg_days_andamento = []

        for row in metrics:
            fin_count = row['finalizadas_count']
            and_count = row['andamento_count']
            total_count = row['total_count']
            avg_fin = row['avg_days_finalizadas']

            # Taxa de conclusão no período
            completion_rate = (float(fin_count) / float(total_count)) if total_count else 0.0

            # Fator de velocidade: método mais rápido entre os finalizados recebe 1.0
            if avg_fin is not None and best_avg_final and avg_fin > 0:
                speed_factor = float(best_avg_final) / float(avg_fin)
            else:
                speed_factor = 0.0

            # Índice 0..100 (quanto maior, mais eficaz)
            score = completion_rate * speed_factor * 100.0
            row['efficacy_index'] = score

        metrics.sort(key=lambda r: r.get('efficacy_index', 0.0), reverse=True)

        for row in metrics:
            m = row['metodo']
            labels.append(m if len(str(m)) <= 80 else (str(m)[:77] + '...'))
            efficacy_index.append(round(float(row.get('efficacy_index') or 0.0), 2))
            finalizadas_counts.append(int(row.get('finalizadas_count') or 0))
            andamento_counts.append(int(row.get('andamento_count') or 0))
            avg_days_finalizadas.append(round(float(row.get('avg_days_finalizadas') or 0.0), 2) if row.get('avg_days_finalizadas') is not None else None)
            avg_days_andamento.append(round(float(row.get('avg_days_andamento') or 0.0), 2) if row.get('avg_days_andamento') is not None else None)

        resp = {
            'success': True,
            'labels': labels,
            'efficacy_index': efficacy_index,
            'finalizadas_counts': finalizadas_counts,
            'andamento_counts': andamento_counts,
            'avg_days_finalizadas': avg_days_finalizadas,
            'avg_days_andamento': avg_days_andamento,
            'period_fallback': period_fallback,
            'score_formula': 'indice = taxa_conclusao * (melhor_media_finalizadas / media_finalizadas_metodo) * 100',
        }
        try:
            cache_key = f"metodos_eficacia|cliente={cliente or ''}|unidade={unidade or ''}|start={start or ''}|end={end or ''}"
            cache.set(cache_key, resp, 60)
        except Exception:
            pass
        return JsonResponse(resp)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        try:
            logger = logging.getLogger(__name__)
            logger.exception('Erro em metodos_eficacia_por_dias: %s', e)
        except Exception:
            pass
        return JsonResponse({'success': False, 'error': str(e), 'traceback': tb}, status=500)

@require_GET
def heatmap_metodo_supervisor(request):
    """Retorna matriz de eficacia por Supervisor x Metodo."""
    try:
        import re
        import unicodedata
        from datetime import date

        start = request.GET.get('start')
        end = request.GET.get('end')
        cliente = request.GET.get('cliente')
        unidade = request.GET.get('unidade')
        supervisor = request.GET.get('supervisor')
        coordenador = request.GET.get('coordenador')
        tanque = request.GET.get('tanque')
        os_existente = request.GET.get('os_existente')

        try:
            start_date = parse_date(start) if start else None
            end_date = parse_date(end) if end else None
        except Exception:
            start_date = None
            end_date = None

        def _split_tokens(raw):
            if not raw:
                return []
            parts = re.split(r'[;,]+', str(raw))
            return [p.strip() for p in parts if p and p.strip()]

        def _normalize_status(raw):
            try:
                txt = str(raw or '').strip().lower()
                txt = ''.join(
                    c for c in unicodedata.normalize('NFKD', txt)
                    if not unicodedata.combining(c)
                )
                txt = txt.replace('_', ' ').replace('-', ' ')
            except Exception:
                txt = str(raw or '').strip().lower()

            if 'finaliz' in txt:
                return 'finalizada'
            if 'andamento' in txt:
                return 'em_andamento'
            return None

        def _normalize_method(raw):
            label = str(raw or '').strip()
            if not label:
                return ''
            key = ''.join(
                c for c in unicodedata.normalize('NFKD', label.lower())
                if not unicodedata.combining(c)
            )
            key = re.sub(r'[^a-z0-9]+', '', key)
            if key in {'na', 'nd', 'null', 'none', 'indefinido', 'desconhecido', 'naoseaplica', 'semmetodo'}:
                return ''
            return label

        hoje = date.today()

        def _in_period(os_obj):
            if not start_date and not end_date:
                return True

            inicio = getattr(os_obj, 'data_inicio_frente', None) or getattr(os_obj, 'data_inicio', None)
            fim = getattr(os_obj, 'data_fim_frente', None) or getattr(os_obj, 'data_fim', None)

            if not inicio and not fim:
                return True
            if not inicio and fim:
                inicio = fim
            if inicio and not fim:
                fim = hoje

            try:
                if start_date and end_date:
                    return (inicio <= end_date) and (fim >= start_date)
                if start_date:
                    return fim >= start_date
                if end_date:
                    return inicio <= end_date
                return True
            except Exception:
                return True

        qs = OrdemServico.objects.select_related('supervisor').all()

        if cliente:
            tokens = _split_tokens(cliente)
            if tokens:
                q = Q()
                for tok in tokens:
                    q |= Q(Cliente__nome__icontains=tok)
                qs = qs.filter(q)

        if unidade:
            tokens = _split_tokens(unidade)
            if tokens:
                q = Q()
                for tok in tokens:
                    q |= Q(Unidade__nome__icontains=tok)
                qs = qs.filter(q)

        if supervisor:
            tokens = _split_tokens(supervisor)
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
            qs = qs.filter(coordenador__icontains=str(coordenador).strip())

        if tanque:
            tokens = _split_tokens(tanque)
            if tokens:
                q = Q()
                for tok in tokens:
                    q |= (
                        Q(rdos__tanques__tanque_codigo__icontains=tok) |
                        Q(tanque__icontains=tok) |
                        Q(tanques__icontains=tok)
                    )
                qs = qs.filter(q)

        if os_existente:
            ids, others = _parse_os_tokens(os_existente)
            if ids or others:
                q = Q()
                if ids:
                    q |= Q(id__in=ids) | Q(numero_os__in=[str(i) for i in ids])
                for token in others:
                    q |= Q(numero_os__iexact=token) | Q(numero_os__icontains=token)
                qs = qs.filter(q)

        qs = qs.distinct()

        def _collect_buckets(only_period=True):
            out = {}
            for os_obj in qs.iterator(chunk_size=500):
                try:
                    if only_period and not _in_period(os_obj):
                        continue

                    status_norm = _normalize_status(getattr(os_obj, 'status_operacao', None))
                    if status_norm not in ('finalizada', 'em_andamento'):
                        continue

                    metodo = _normalize_method(getattr(os_obj, 'metodo', None))
                    if not metodo:
                        continue

                    sup = getattr(os_obj, 'supervisor', None)
                    if sup:
                        try:
                            full = sup.get_full_name() if hasattr(sup, 'get_full_name') else ''
                        except Exception:
                            full = ''
                        supervisor_name = (str(full).strip() if full else '') or getattr(sup, 'username', None) or 'Sem supervisor'
                    else:
                        supervisor_name = 'Sem supervisor'

                    data_inicio = getattr(os_obj, 'data_inicio_frente', None) or getattr(os_obj, 'data_inicio', None)
                    data_fim = getattr(os_obj, 'data_fim_frente', None) or getattr(os_obj, 'data_fim', None)

                    dias = 0
                    if status_norm == 'finalizada':
                        if data_inicio and data_fim:
                            delta = (data_fim - data_inicio).days
                            dias = delta if delta > 0 else 1
                    else:
                        if data_inicio:
                            delta = (hoje - data_inicio).days
                            dias = delta if delta > 0 else 1

                    if not dias or dias <= 0:
                        dias = getattr(os_obj, 'dias_de_operacao_frente', None) or getattr(os_obj, 'dias_de_operacao', None) or 0
                    if not dias or dias <= 0:
                        dias = 1

                    try:
                        dias = int(dias)
                    except Exception:
                        dias = 1

                    key = (supervisor_name, metodo)
                    state = out.setdefault(key, {
                        'finalizadas_dias': [],
                        'andamento_dias': [],
                        'finalizadas': 0,
                        'andamento': 0,
                    })
                    if status_norm == 'finalizada':
                        state['finalizadas_dias'].append(dias)
                        state['finalizadas'] += 1
                    else:
                        state['andamento_dias'].append(dias)
                        state['andamento'] += 1
                except Exception:
                    continue
            return out

        buckets = _collect_buckets(only_period=True)
        period_fallback = False
        if not buckets and (start_date or end_date):
            buckets = _collect_buckets(only_period=False)
            period_fallback = bool(buckets)

        method_totals = {}
        supervisor_totals = {}

        best_avg_final = None
        metrics = {}

        for (sup_name, metodo), state in buckets.items():
            fin = int(state.get('finalizadas') or 0)
            andm = int(state.get('andamento') or 0)
            total = fin + andm
            if total <= 0:
                continue

            fin_days = state.get('finalizadas_dias') or []
            and_days = state.get('andamento_dias') or []
            avg_fin = (float(sum(fin_days)) / float(len(fin_days))) if fin_days else None
            avg_and = (float(sum(and_days)) / float(len(and_days))) if and_days else None

            if avg_fin is not None:
                if best_avg_final is None or avg_fin < best_avg_final:
                    best_avg_final = avg_fin

            completion_rate = (float(fin) / float(total)) if total > 0 else 0.0
            metrics[(sup_name, metodo)] = {
                'finalizadas': fin,
                'andamento': andm,
                'total': total,
                'avg_days_finalizadas': avg_fin,
                'avg_days_andamento': avg_and,
                'completion_rate': completion_rate,
            }
            method_totals[metodo] = method_totals.get(metodo, 0) + total
            supervisor_totals[sup_name] = supervisor_totals.get(sup_name, 0) + total

        for key, info in metrics.items():
            avg_fin = info.get('avg_days_finalizadas')
            if avg_fin is not None and best_avg_final and avg_fin > 0:
                speed_factor = float(best_avg_final) / float(avg_fin)
            else:
                speed_factor = 0.0
            info['speed_factor'] = speed_factor
            info['score'] = (info.get('completion_rate', 0.0) or 0.0) * speed_factor * 100.0

        preferred = {'Manual': 0, 'Mecanizada': 1, 'Robotizada': 2}
        methods = sorted(
            method_totals.keys(),
            key=lambda m: (preferred.get(m, 99), -method_totals.get(m, 0), str(m).lower())
        )
        supervisors = sorted(
            supervisor_totals.keys(),
            key=lambda s: (-supervisor_totals.get(s, 0), str(s).lower())
        )[:20]

        scores = []
        details = []
        flat_scores = []

        for sup_name in supervisors:
            row_scores = []
            row_details = []
            for metodo in methods:
                info = metrics.get((sup_name, metodo))
                if not info:
                    row_scores.append(0.0)
                    row_details.append({
                        'has_data': False,
                        'score': 0.0,
                        'completion_rate': 0.0,
                        'finalizadas': 0,
                        'andamento': 0,
                        'total': 0,
                        'avg_days_finalizadas': None,
                        'avg_days_andamento': None,
                    })
                    continue

                score = round(float(info.get('score') or 0.0), 2)
                completion_rate = round(float(info.get('completion_rate') or 0.0) * 100.0, 2)
                row_scores.append(score)
                flat_scores.append(score)
                row_details.append({
                    'has_data': True,
                    'score': score,
                    'completion_rate': completion_rate,
                    'finalizadas': int(info.get('finalizadas') or 0),
                    'andamento': int(info.get('andamento') or 0),
                    'total': int(info.get('total') or 0),
                    'avg_days_finalizadas': round(float(info.get('avg_days_finalizadas') or 0.0), 2) if info.get('avg_days_finalizadas') is not None else None,
                    'avg_days_andamento': round(float(info.get('avg_days_andamento') or 0.0), 2) if info.get('avg_days_andamento') is not None else None,
                })
            scores.append(row_scores)
            details.append(row_details)

        max_score = max(flat_scores) if flat_scores else 0.0
        min_score = min(flat_scores) if flat_scores else 0.0

        return JsonResponse({
            'success': True,
            'methods': methods,
            'supervisors': supervisors,
            'scores': scores,
            'details': details,
            'period_fallback': period_fallback,
            'max_score': round(float(max_score or 0.0), 2),
            'min_score': round(float(min_score or 0.0), 2),
            'best_avg_final': round(float(best_avg_final or 0.0), 2) if best_avg_final is not None else None,
            'totals_by_method': {k: int(v) for k, v in method_totals.items()},
            'totals_by_supervisor': {k: int(v) for k, v in supervisor_totals.items()},
            'filtered_start': start_date.isoformat() if start_date else None,
            'filtered_end': end_date.isoformat() if end_date else None,
            'score_formula': 'indice = taxa_conclusao * (melhor_media_finalizadas / media_finalizadas_celula) * 100',
        })
    except Exception as e:
        logging.exception('Erro em heatmap_metodo_supervisor')
        return JsonResponse({'success': False, 'error': str(e), 'traceback': traceback.format_exc()}, status=500)


@require_GET
def pob_comparativo(request):
    start = request.GET.get('start')
    end = request.GET.get('end')
    os_existente = request.GET.get('os_existente')
    coordenador = request.GET.get('coordenador')

    def remove_accents_norm(s):
        try:
            import unicodedata
            s2 = unicodedata.normalize('NFKD', s)
            return ''.join([c for c in s2 if not unicodedata.combining(c)])
        except Exception:
            return s

    def tokenize_name(s):
        s = remove_accents_norm(s).upper()
        for ch in ".,;:\\/()[]{}-'\"`":
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

    def get_coordenador_variants(raw_name):
        try:
            if not raw_name:
                return []
            inp = str(raw_name).strip()
            if not inp:
                return []
            try:
                from .models import CoordenadorCanonical
                canon_list = list(CoordenadorCanonical.objects.all())
            except Exception:
                canon_list = []
            for c in canon_list:
                try:
                    if c.canonical_name.lower() == inp.lower():
                        return [c.canonical_name] + list(c.variants or [])
                    for v in (c.variants or []):
                        if str(v).lower() == inp.lower():
                            return [c.canonical_name] + list(c.variants or [])
                except Exception:
                    continue
            toks = tokenize_name(inp)
            if not toks:
                return []
            try:
                from .models import CoordenadorCanonical
                canon_list = list(CoordenadorCanonical.objects.all())
            except Exception:
                canon_list = []
            for c in canon_list:
                try:
                    variants = [c.canonical_name] + list(c.variants or [])
                    for v in variants:
                        vt = tokenize_name(str(v))
                        if vt and tokens_equivalent(toks, vt):
                            return [c.canonical_name] + list(c.variants or [])
                except Exception:
                    continue
        except Exception:
            return []
        return []

    try:
        start_date = parse_date(start) if start else None
        end_date = parse_date(end) if end else None
    except Exception:
        start_date = None
        end_date = None

    if not end_date:
        end_date = datetime.date.today()
    if not start_date:
        start_date = end_date.replace(day=1)

    try:
        date_field = None
        date_field_type = None
        for f in RDO._meta.fields:
            t = f.get_internal_type()
            if t in ('DateField', 'DateTimeField') and 'data' in f.name:
                date_field = f.name
                date_field_type = t
                break
        if not date_field:
            for f in RDO._meta.fields:
                t = f.get_internal_type()
                if t in ('DateField', 'DateTimeField'):
                    date_field = f.name
                    date_field_type = t
                    break

        if not date_field:
            return JsonResponse({'success': False, 'error': 'Modelo RDO sem campo de data detectável.'}, status=400)

        unidade = request.GET.get('unidade')
        group_by = request.GET.get('group', 'day')

        labels = []
        data_alocado = []
        data_confinado = []
        data_count_rdo = []
        data_count_os = []

        if group_by == 'month':
            cur = start_date.replace(day=1)
            while cur <= end_date:
                year = cur.year
                month = cur.month
                month_start = cur
                if month == 12:
                    next_month = cur.replace(year=year+1, month=1, day=1)
                else:
                    next_month = cur.replace(month=month+1, day=1)
                month_end = next_month - datetime.timedelta(days=1)

                labels.append(cur.strftime('%Y-%m-01'))

                if date_field_type == 'DateField':
                    filters = {f"{date_field}__gte": month_start, f"{date_field}__lte": month_end}
                else:
                    filters = {f"{date_field}__date__gte": month_start, f"{date_field}__date__lte": month_end}

                month_qs = RDO.objects.filter(**filters)
                if unidade:
                    month_qs = month_qs.filter(ordem_servico__unidade__icontains=unidade)
                if os_existente:
                    month_qs = _apply_os_filter_to_rdo_qs(month_qs, os_existente)
                if coordenador:
                    variants = get_coordenador_variants(coordenador)
                    if variants:
                        q = None
                        for v in variants:
                            if q is None:
                                q = Q(ordem_servico__coordenador__icontains=v)
                            else:
                                q |= Q(ordem_servico__coordenador__icontains=v)
                        if q is not None:
                            month_qs = month_qs.filter(q)
                    else:
                        month_qs = month_qs.filter(ordem_servico__coordenador__icontains=coordenador)

                agg_alocado = month_qs.aggregate(v=Coalesce(Avg('ordem_servico__pob'), 0, output_field=DecimalField()))
                agg_confinado = month_qs.aggregate(v=Coalesce(Avg('operadores_simultaneos'), 0, output_field=DecimalField()))
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

                cur = next_month
        else:
            delta = end_date - start_date
            for i in range(delta.days + 1):
                day = start_date + datetime.timedelta(days=i)
                labels.append(day.strftime('%Y-%m-%d'))

                if date_field_type == 'DateField':
                    filters = {f"{date_field}__gte": day, f"{date_field}__lte": day}
                else:
                    filters = {f"{date_field}__date__gte": day, f"{date_field}__date__lte": day}

                day_qs = RDO.objects.filter(**filters)
                if unidade:
                    day_qs = day_qs.filter(ordem_servico__unidade__icontains=unidade)
                if os_existente:
                    day_qs = _apply_os_filter_to_rdo_qs(day_qs, os_existente)
                if coordenador:
                    variants = get_coordenador_variants(coordenador)
                    if variants:
                        q = None
                        for v in variants:
                            if q is None:
                                q = Q(ordem_servico__coordenador__icontains=v)
                            else:
                                q |= Q(ordem_servico__coordenador__icontains=v)
                        if q is not None:
                            day_qs = day_qs.filter(q)
                    else:
                        day_qs = day_qs.filter(ordem_servico__coordenador__icontains=coordenador)

                agg_alocado = day_qs.aggregate(v=Coalesce(Avg('ordem_servico__pob'), 0, output_field=DecimalField()))
                agg_confinado = day_qs.aggregate(v=Coalesce(Avg('operadores_simultaneos'), 0, output_field=DecimalField()))
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

        data_ratio = []
        for a, c in zip(data_alocado, data_confinado):
            try:
                a_val = float(a or 0)
                c_val = float(c or 0)
                if a_val > 0:
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
            ],
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
