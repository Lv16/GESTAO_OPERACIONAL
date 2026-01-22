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
        cliente = params.get('cliente') if params else None
        unidade = params.get('unidade') if params else None
        start = params.get('start') if params else None
        end = params.get('end') if params else None
        os_existente = params.get('os_existente') if params else None
        coordenador = params.get('coordenador') if params else None
        status = params.get('status') if params else None
        tanque = params.get('tanque') if params else None
        supervisor = params.get('supervisor') if params else None

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
                            from django.db.models import Q
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
                        from django.db.models import Q
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
            qs = qs.filter(Cliente__nome__icontains=cliente)
        if unidade:
            qs = qs.filter(Unidade__nome__icontains=unidade)
        if tanque:
            try:
                t = str(tanque).strip()
                from django.db.models import Q
                if t.isdigit():
                    try:
                        qs = qs.filter(Q(rdos__tanques__id=int(t)) | Q(tanque__icontains=t) | Q(tanques__icontains=t))
                    except Exception:
                        qs = qs.filter(Q(rdos__tanques__tanque_codigo__icontains=t) | Q(tanque__icontains=t) | Q(tanques__icontains=t))
                else:
                    exact_qs = qs.filter(rdos__tanques__tanque_codigo__iexact=t)
                    if exact_qs.exists():
                        qs = exact_qs
                    else:
                        qs = qs.filter(Q(rdos__tanques__tanque_codigo__icontains=t) | Q(tanque__icontains=t) | Q(tanques__icontains=t))
            except Exception:
                try:
                    qs = qs.filter(rdos__tanques__tanque_codigo__icontains=str(tanque))
                except Exception:
                    pass
        if os_existente:
            qs = qs.filter(id=os_existente)
        if supervisor:
            qs = qs.filter(supervisor__username__icontains=supervisor) | qs.filter(supervisor__first_name__icontains=supervisor) | qs.filter(supervisor__last_name__icontains=supervisor)

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

        try:
            from datetime import datetime
            from django.db.models import Q
            if start and end:
                s = datetime.strptime(start, '%Y-%m-%d').date()
                e = datetime.strptime(end, '%Y-%m-%d').date()
                if status:
                    # quando filtramos por status, aplicar a janela de datas sobre a OS
                    # (data_inicio/data_fim) para incluir OS finalizadas mesmo sem RDOs
                    qs = qs.filter(
                        Q(data_inicio__gte=s, data_inicio__lte=e) |
                        Q(data_fim__gte=s, data_fim__lte=e) |
                        Q(data_inicio__lte=s, data_fim__gte=e)
                    )
                else:
                    qs = qs.filter(rdos__data__gte=s, rdos__data__lte=e)
            elif start:
                s = datetime.strptime(start, '%Y-%m-%d').date()
                if status:
                    qs = qs.filter(Q(data_inicio__gte=s) | Q(data_fim__gte=s) | Q(data_inicio__lte=s, data_fim__gte=s))
                else:
                    qs = qs.filter(rdos__data__gte=s)
            elif end:
                e = datetime.strptime(end, '%Y-%m-%d').date()
                if status:
                    qs = qs.filter(Q(data_inicio__lte=e) | Q(data_fim__lte=e) | Q(data_inicio__lte=e, data_fim__gte=e))
                else:
                    qs = qs.filter(rdos__data__lte=e)
        except Exception:
            pass

        qs = qs.distinct()

        # Por padrão, quando não filtramos por coordenador, exibimos apenas OS que
        # possuam RDOs associados para evitar linhas vazias. Porém, se o usuário
        # estiver filtrando por `status`, devemos mostrar também OS sem RDOs que
        # atendam ao status selecionado. Portanto aplicamos a restrição somente
        # quando não há filtro de coordenador e nem filtro de status.
        if not coordenador and not status:
            qs = qs.filter(rdos__isnull=False)

        agg_qs = qs.annotate(
            rdos_count=Coalesce(Count('rdos', distinct=True), 0, output_field=IntegerField()),
            total_ensacamento=Coalesce(Sum('rdos__ensacamento'), 0, output_field=IntegerField()),
            total_tambores=Coalesce(Sum('rdos__tanques__tambores_cumulativo'), 0, output_field=IntegerField()),
            sum_operadores_simultaneos=Coalesce(Sum('rdos__operadores_simultaneos'), 0, output_field=IntegerField()),
            avg_pob=Coalesce(Avg('pob'), 0, output_field=FloatField()),
            total_volume_tanque=Coalesce(Sum('rdos__tanques__volume_tanque_exec'), 0, output_field=DecimalField()),
        )

        out = []
        for o in agg_qs.order_by('-numero_os')[:200]:
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

            rdo_qs = RDO.objects.filter(ordem_servico=o)
            try:
                if start and end:
                    s = datetime.datetime.strptime(start, '%Y-%m-%d').date()
                    e = datetime.datetime.strptime(end, '%Y-%m-%d').date()
                    rdo_qs = rdo_qs.filter(data__gte=s, data__lte=e)
                elif start:
                    s = datetime.datetime.strptime(start, '%Y-%m-%d').date()
                    rdo_qs = rdo_qs.filter(data__gte=s)
                elif end:
                    e = datetime.datetime.strptime(end, '%Y-%m-%d').date()
                    rdo_qs = rdo_qs.filter(data__lte=e)
            except Exception:
                pass

            sum_operadores = 0
            sum_ensacamento = 0
            sum_tambores = 0
            sum_hh_efetivo_min = 0
            sum_hh_nao_min = 0
            for r in rdo_qs:
                try:
                    sum_operadores += int(getattr(r, 'operadores_simultaneos', 0) or 0)
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
                    confinado = int(getattr(r, 'total_n_efetivo_confinado', 0) or 0)
                except Exception:
                    confinado = 0
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
                    sum_hh_nao_min += int(confinado + nao_fora)
                except Exception:
                    pass

            try:
                sum_hh_efetivo = int(round(sum_hh_efetivo_min / 60.0))
            except Exception:
                sum_hh_efetivo = 0
            try:
                sum_hh_nao_efetivo = int(sum_hh_nao_min // 60)
            except Exception:
                sum_hh_nao_efetivo = 0

            out.append({
                'id': o.id,
                'numero_os': getattr(o, 'numero_os', None),
                'cliente': cliente_name,
                'unidade': unidade_name,
                'supervisor': supervisor_name,
                'rdos_count': int(getattr(o, 'rdos_count', 0) or 0),
                'total_ensacamento': int(sum_ensacamento or int(getattr(o, 'total_ensacamento', 0) or 0)),
                'total_tambores': int(sum_tambores or int(getattr(o, 'total_tambores', 0) or 0)),
                'sum_operadores_simultaneos': int(sum_operadores or int(getattr(o, 'sum_operadores_simultaneos', 0) or 0)),
                'sum_hh_nao_efetivo': sum_hh_nao_efetivo,
                'sum_hh_efetivo': int(sum_hh_efetivo),
                'avg_pob': float(getattr(o, 'avg_pob', 0) or 0),
                'total_volume_tanque': float(getattr(o, 'total_volume_tanque', 0) or 0),
            })

        return out
    except Exception:
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
        qs = RDO.objects.select_related('ordem_servico__supervisor').all()

        os_selecionada = request.GET.get('os_existente')
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
        if os_selecionada:
            qs = qs.filter(ordem_servico_id=os_selecionada)
        if coordenador:
            variants = get_coordenador_variants(coordenador)
            if variants:
                q = None
                from django.db.models import Q
                for v in variants:
                    if q is None:
                        q = Q(ordem_servico__coordenador__icontains=v)
                    else:
                        q |= Q(ordem_servico__coordenador__icontains=v)
                if q is not None:
                    qs = qs.filter(q)
            else:
                qs = qs.filter(ordem_servico__coordenador__icontains=coordenador)

        tanque_qs = RdoTanque.objects.filter(rdo__in=qs).values(
            'rdo__ordem_servico__supervisor__id',
            'tanque_codigo'
        ).annotate(
            cap=Coalesce(Max('volume_tanque_exec'), 0, output_field=DecimalField())
        )

        capacities = {}
        for t in tanque_qs:
            sup_id = t.get('rdo__ordem_servico__supervisor__id')
            if not sup_id:
                continue
            cap = float(t.get('cap') or 0)
            capacities[sup_id] = capacities.get(sup_id, 0.0) + cap

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
            sum_capacidade=Coalesce(Sum('tanques__volume_tanque_exec'), 0, output_field=DecimalField()),
        )

        items = []
        for row in agg_qs:
            sup_id = row.get('ordem_servico__supervisor__id')
            if not sup_id:
                continue
            username = row.get('ordem_servico__supervisor__username') or ''
            fname = row.get('ordem_servico__supervisor__first_name') or ''
            lname = row.get('ordem_servico__supervisor__last_name') or ''
            name = ((fname + ' ' + lname).strip()) or username or f'ID {sup_id}'

            raw_total = (
                float(row.get('sum_bombeio') or 0)
                + float(row.get('sum_quantidade_bombeada') or 0)
                + float(row.get('sum_volume_tanque_exec') or 0)
                + float(row.get('sum_total_liquido') or 0)
                + float(row.get('sum_total_solidos') or 0)
            )
            capacidade_total = float(row.get('sum_capacidade') or 0)
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
                    month_qs = month_qs.filter(ordem_servico_id=os_existente)
                if coordenador:
                    variants = get_coordenador_variants(coordenador)
                    if variants:
                        q = None
                        from django.db.models import Q
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
                    day_qs = day_qs.filter(ordem_servico_id=os_existente)
                if coordenador:
                    variants = get_coordenador_variants(coordenador)
                    if variants:
                        q = None
                        from django.db.models import Q
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