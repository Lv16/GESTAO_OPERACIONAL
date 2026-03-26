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
import math
import re
import unicodedata

from .models import RDO, RDOAtividade, RdoTanque, OrdemServico, _rdo_has_setup_activity, _canonical_tank_alias_for_os
from .views_rdo import _resolve_os_scope_ids, _tank_identity_key
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


def _report_diario_ordens_queryset():
    return (
        OrdemServico.objects
        .filter(rdos__isnull=False)
        .annotate(
            rdo_inicio=Min('rdos__data'),
            rdo_fim=Max('rdos__data'),
        )
        .order_by('-numero_os', '-rdo_fim', '-id')
    )


def _report_diario_ordem_label(ordem):
    numero_os = getattr(ordem, 'numero_os', '')
    rdo_inicio = getattr(ordem, 'rdo_inicio', None)
    rdo_fim = getattr(ordem, 'rdo_fim', None)
    if rdo_inicio and rdo_fim:
        if rdo_inicio == rdo_fim:
            periodo = rdo_inicio.strftime('%d/%m/%Y')
        else:
            periodo = f"{rdo_inicio.strftime('%d/%m/%Y')} a {rdo_fim.strftime('%d/%m/%Y')}"
    else:
        periodo = ''

    parts = [f"OS {numero_os}"]
    if periodo:
        parts.append(periodo)
    parts.append(f"ID {getattr(ordem, 'id', '')}")
    return ' • '.join(part for part in parts if part)


@require_GET
def get_ordens_servico(request):
    try:
        items = [
            {
                'id': ordem.id,
                'numero_os': ordem.numero_os,
                'label': _report_diario_ordem_label(ordem),
            }
            for ordem in _report_diario_ordens_queryset()
        ]
        return JsonResponse({'success': True, 'items': items})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def _resolve_report_os_context(os_id):
    os_obj = OrdemServico.objects.filter(id=os_id).first()
    if not os_obj:
        return None, []

    os_scope_ids = _resolve_os_scope_ids(os_obj)
    if not os_scope_ids:
        try:
            os_scope_ids = [int(os_obj.id)]
        except Exception:
            os_scope_ids = []
    return os_obj, os_scope_ids


def _normalize_report_tank_label(os_num, raw_label):
    label = str(raw_label or '').strip()
    if not label:
        return ''
    try:
        canonical = _canonical_tank_alias_for_os(os_num, label)
    except Exception:
        canonical = None
    return str(canonical or label).strip()


def _iter_declared_os_tank_labels(os_rows):
    for os_row in os_rows:
        for raw_value in (
            getattr(os_row, 'tanques', None),
            getattr(os_row, 'tanque', None),
        ):
            raw_text = str(raw_value or '').strip()
            if not raw_text:
                continue
            for piece in re.split(r'[\n,;]+', raw_text):
                label = str(piece or '').strip()
                if label:
                    yield label


def _get_tanques_disponiveis_por_os(os_id):
    """
    Retorna labels únicos de tanques para a OS.

    A lista de tanques do report deve nascer apenas de snapshots de `RdoTanque`.
    """
    os_obj, os_scope_ids = _resolve_report_os_context(os_id)
    if not os_obj or not os_scope_ids:
        return []

    os_num = getattr(os_obj, 'numero_os', None)
    labels_by_key = {}

    def register_label(raw_label, code=None, name=None):
        label = _normalize_report_tank_label(os_num, raw_label or code or name)
        if not label:
            return
        key = _tank_identity_key(code or label, name or label, os_num=os_num) or label.casefold()
        labels_by_key.setdefault(key, label)

    for tanque_codigo, nome_tanque in (
        RdoTanque.objects
        .filter(rdo__ordem_servico_id__in=os_scope_ids)
        .values_list('tanque_codigo', 'nome_tanque')
    ):
        register_label(tanque_codigo or nome_tanque, code=tanque_codigo, name=nome_tanque)

    return sorted(labels_by_key.values(), key=lambda item: item.casefold())


def _filter_tank_queryset_by_identity(qs, raw_tank, os_num=None):
    tank_label = str(raw_tank or '').strip()
    if not tank_label:
        return qs

    exact_match = Q(tanque_codigo__iexact=tank_label) | Q(nome_tanque__iexact=tank_label)
    target_key = _tank_identity_key(tank_label, tank_label, os_num=os_num)
    if not target_key:
        return qs.filter(exact_match)

    matched_ids = []
    try:
        for tank_id, code, name in qs.values_list('id', 'tanque_codigo', 'nome_tanque'):
            current_key = _tank_identity_key(code, name, os_num=os_num)
            if current_key == target_key:
                matched_ids.append(tank_id)
    except Exception:
        matched_ids = []

    if matched_ids:
        return qs.filter(id__in=matched_ids)
    return qs.filter(exact_match)


def _best_numeric_attr_value(row, attrs):
    if row is None:
        return None
    best = None
    for attr in attrs or ():
        try:
            value = getattr(row, attr, None)
        except Exception:
            value = None
        if value in (None, ''):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if best is None or number > best:
            best = number
    return best


def _best_numeric_from_rows(rows, attrs):
    best = None
    for row in rows or ():
        number = _best_numeric_attr_value(row, attrs)
        if number is None:
            continue
        if best is None or number > best:
            best = number
    return best


def _preferred_numeric_value(rows, primary_attrs, fallback_row=None, fallback_attrs=None):
    preferred = _best_numeric_from_rows(rows, primary_attrs)
    if preferred is not None:
        return preferred
    if fallback_row is None:
        return None
    return _best_numeric_attr_value(fallback_row, fallback_attrs or primary_attrs)


def _sum_numeric_from_rows(rows, attrs):
    total = 0.0
    found = False
    for row in rows or ():
        number = _best_numeric_attr_value(row, attrs)
        if number is None:
            continue
        total += number
        found = True
    if not found:
        return None
    return total


def _first_present_attr_value(row, attrs):
    if row is None:
        return None
    for attr in attrs or ():
        try:
            value = getattr(row, attr, None)
        except Exception:
            value = None
        if value not in (None, ''):
            return value
    return None


def _preferred_attr_value(primary_row, primary_attrs, fallback_row=None, fallback_attrs=None):
    preferred = _first_present_attr_value(primary_row, primary_attrs)
    if preferred not in (None, ''):
        return preferred
    if fallback_row is None:
        return None
    return _first_present_attr_value(fallback_row, fallback_attrs or primary_attrs)


def _latest_numeric_attr_value(rows, attrs, require_positive=False):
    ordered_rows = list(rows or ())
    for row in reversed(ordered_rows):
        if row is None:
            continue
        for attr in attrs or ():
            try:
                value = getattr(row, attr, None)
            except Exception:
                value = None
            if value in (None, ''):
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if require_positive and number <= 0:
                continue
            return number
    return None


def _latest_numeric_value(rows, primary_attrs, fallback_row=None, fallback_attrs=None, require_positive=False):
    preferred = _latest_numeric_attr_value(rows, primary_attrs, require_positive=require_positive)
    if preferred is not None:
        return preferred
    if fallback_row is None:
        return None
    fallback = _best_numeric_attr_value(fallback_row, fallback_attrs or primary_attrs)
    if require_positive and (fallback is None or fallback <= 0):
        return None
    return fallback


def _percent_from_cumulative_and_forecast(cumulative_value, forecast_value, round_digits=1):
    try:
        if cumulative_value in (None, '') or forecast_value in (None, ''):
            return None
        cumulative_num = float(cumulative_value)
        forecast_num = float(forecast_value)
        if forecast_num <= 0:
            return None
        percent = (cumulative_num / forecast_num) * 100.0
        if percent < 0:
            percent = 0.0
        if percent > 100:
            percent = 100.0
        return round(percent, round_digits)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _resolve_productive_percent(
    rows,
    cumulative_attrs,
    forecast_attrs,
    percent_attrs,
    fallback_row=None,
    fallback_cumulative_attrs=None,
    fallback_forecast_attrs=None,
    fallback_percent_attrs=None,
    forecast_override=None,
    round_digits=1,
):
    cumulative_value = _preferred_numeric_value(
        rows,
        cumulative_attrs,
        fallback_row=fallback_row,
        fallback_attrs=fallback_cumulative_attrs or cumulative_attrs,
    )
    forecast_value = forecast_override
    if forecast_value in (None, ''):
        forecast_value = _latest_numeric_value(
            rows,
            forecast_attrs,
            fallback_row=fallback_row,
            fallback_attrs=fallback_forecast_attrs or forecast_attrs,
            require_positive=True,
        )

    computed = _percent_from_cumulative_and_forecast(cumulative_value, forecast_value, round_digits=round_digits)
    if computed is not None:
        return computed

    return _preferred_numeric_value(
        rows,
        percent_attrs,
        fallback_row=fallback_row,
        fallback_attrs=fallback_percent_attrs or percent_attrs,
    )


def _normalize_percent_series(values, round_digits=1, monotonic=False):
    normalized = []
    last_value = None
    for raw in values or ():
        try:
            if raw in (None, ''):
                current = None
            else:
                current = round(float(raw), round_digits)
        except (TypeError, ValueError):
            current = None

        if current is not None:
            if current < 0:
                current = 0.0
            elif current > 100:
                current = 100.0

        if monotonic:
            if current is None:
                current = last_value if last_value is not None else 0.0
            elif last_value is not None and current < last_value:
                current = last_value
            last_value = current

        normalized.append(None if current is None else round(float(current), round_digits))
    return normalized


def _daily_from_cumulative_series(values, round_digits=1):
    daily = []
    previous = 0.0
    for index, raw in enumerate(values or ()):
        try:
            current = float(raw or 0)
        except (TypeError, ValueError):
            current = 0.0
        if index == 0:
            daily.append(round(current, round_digits))
        else:
            daily.append(round(max(0.0, current - previous), round_digits))
        previous = current
    return daily


@require_GET
def os_tanques_data(request):
    try:
        os_id = request.GET.get('os_id')
        if not os_id:
            return JsonResponse({'success': False, 'error': 'os_id é obrigatório'}, status=400)
        try:
            os_id = int(os_id)
        except (ValueError, TypeError):
            return JsonResponse({'success': False, 'error': 'os_id inválido'}, status=400)

        os_obj, _os_scope_ids = _resolve_report_os_context(os_id)
        if not os_obj:
            return JsonResponse({'success': False, 'error': 'OS não encontrada'}, status=404)

        tanques_disponiveis = _get_tanques_disponiveis_por_os(os_id)
        requires_tank_selection = len(tanques_disponiveis) > 1

        return JsonResponse({
            'success': True,
            'tanques_disponiveis': tanques_disponiveis,
            'total_tanques': len(tanques_disponiveis),
            'requires_tank_selection': requires_tank_selection,
            'auto_selected_tank': tanques_disponiveis[0] if len(tanques_disponiveis) == 1 else '',
        })
    except Exception as e:
        logging.exception('Erro em os_tanques_data')
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

        qs = (
            OrdemServico.objects
            .all()
            .exclude(
                Q(supervisor__username__icontains='a definir') |
                Q(supervisor__first_name__icontains='a definir') |
                Q(supervisor__last_name__icontains='a definir')
            )
        )
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

        # No resumo das operacoes, o filtro de status deve refletir o
        # andamento da movimentacao (`status_geral`). Quando esse campo nao
        # estiver preenchido, usamos `status_operacao` como fallback para nao
        # esconder OS legadas/incompletas.
        if status:
            try:
                s = str(status).strip()
                try:
                    OrdemServico._meta.get_field('status_geral')
                    status_filter = Q(status_geral__iexact=s)
                    try:
                        OrdemServico._meta.get_field('status_operacao')
                        status_filter |= (
                            (Q(status_geral__isnull=True) | Q(status_geral__exact='')) &
                            Q(status_operacao__iexact=s)
                        )
                    except Exception:
                        pass
                    qs = qs.filter(status_filter)
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
            try:
                metodo_name = o.get_metodo_display() if hasattr(o, 'get_metodo_display') else getattr(o, 'metodo', None)
            except Exception:
                metodo_name = getattr(o, 'metodo', None)
            metodo_name = str(metodo_name).strip() if metodo_name else ''
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
            operadores_validos = 0
            sum_ensacamento = 0
            sum_tambores = 0
            sum_hh_efetivo_min = 0
            sum_hh_nao_min = 0
            for r in rdo_rows:
                try:
                    op_val = int(getattr(r, 'operadores_simultaneos', 0) or 0)
                    if op_val != 0:
                        sum_operadores += op_val
                        operadores_validos += 1
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
                avg_operadores = int(round((float(sum_operadores) / float(operadores_validos)))) if operadores_validos else 0
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
                'metodo': metodo_name,
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


# ─── Curva de Conclusão da Limpeza do Tanque ─────────────────────────
from django.shortcuts import render as _render
from django.contrib.auth.decorators import login_required as _login_required


@_login_required
def curva_s_view(request):
    """Renderiza a página do Report Diário / Curva S."""
    ordens = (
        OrdemServico.objects
        .filter(rdos__isnull=False)
        .values('numero_os')
        .annotate(id=Min('id'))
        .order_by('-numero_os')
    )
    return _render(request, 'report_diario.html', {'ordens': list(ordens)})


@require_GET
def curva_s_data(request):
    """
    API JSON – retorna séries temporais para a curva de conclusão da limpeza.
    Parâmetros GET:
        os_id  – ID da Ordem de Serviço
        tanque – (opcional) código do tanque específico
    Retorna por data (do RDO):
        - percentual_limpeza_cumulativo  (limpeza mecanizada acumulada)
        - percentual_limpeza_fina_cumulativo
        - percentual_avanco_cumulativo   (avanço ponderado geral)
        - percentual_ensacamento
        - percentual_icamento
        - percentual_cambagem
    """
    try:
        os_id = request.GET.get('os_id')
        tanque = request.GET.get('tanque', '').strip()

        if not os_id:
            return JsonResponse({'success': False, 'error': 'os_id é obrigatório'}, status=400)

        try:
            os_id = int(os_id)
        except (ValueError, TypeError):
            return JsonResponse({'success': False, 'error': 'os_id inválido'}, status=400)

        os_obj, os_scope_ids = _resolve_report_os_context(os_id)
        if not os_obj:
            return JsonResponse({'success': False, 'error': 'OS não encontrada'}, status=404)

        # Buscar RDOs da OS ordenados por data
        rdo_qs = RDO.objects.filter(ordem_servico_id__in=os_scope_ids, data__isnull=False).order_by('data')

        if not rdo_qs.exists():
            return JsonResponse({'success': True, 'labels': [], 'datasets': {}})

        # Pegar tanques únicos dos RdoTanque para essa OS
        tanques_disponiveis = _get_tanques_disponiveis_por_os(os_id)
        effective_tank_filter = tanque
        if not effective_tank_filter and len(tanques_disponiveis) == 1:
            effective_tank_filter = tanques_disponiveis[0]

        tank_qs = RdoTanque.objects.filter(rdo__ordem_servico_id__in=os_scope_ids)
        if effective_tank_filter:
            tank_qs = _filter_tank_queryset_by_identity(
                tank_qs,
                effective_tank_filter,
                os_num=getattr(os_obj, 'numero_os', None),
            )

        ordered_tanks = list(tank_qs.select_related('rdo').order_by('rdo__data', 'rdo__pk', 'pk'))
        use_tank_forecast_context = bool(effective_tank_filter) or len(tanques_disponiveis) <= 1
        ensacamento_forecast = _latest_numeric_value(
            ordered_tanks if use_tank_forecast_context else [],
            ('ensacamento_prev',),
            fallback_row=ordered_rdos[-1] if ordered_rdos else None,
            fallback_attrs=('ensacamento_previsao',),
            require_positive=True,
        )
        icamento_forecast = _latest_numeric_value(
            ordered_tanks if use_tank_forecast_context else [],
            ('icamento_prev',),
            fallback_row=ordered_rdos[-1] if ordered_rdos else None,
            fallback_attrs=('icamento_previsao',),
            require_positive=True,
        )
        cambagem_forecast = _latest_numeric_value(
            ordered_tanks if use_tank_forecast_context else [],
            ('cambagem_prev',),
            fallback_row=ordered_rdos[-1] if ordered_rdos else None,
            fallback_attrs=('cambagem_previsao',),
            require_positive=True,
        )

        # Coletar dados por data
        from collections import OrderedDict

        series = OrderedDict()
        single_tank_context = len(tanques_disponiveis) <= 1

        for rdo in rdo_qs:
            dt_str = rdo.data.strftime('%d/%m/%Y') if rdo.data else None
            if not dt_str:
                continue

            tanks = list(tank_qs.filter(rdo=rdo))
            use_tank_priority = bool(effective_tank_filter) and (single_tank_context or bool(tanks))

            key = dt_str
            if key not in series:
                series[key] = {
                    'limpeza_mec_cum': None,
                    'limpeza_fina_cum': None,
                    'avanco_cum': None,
                    'ensacamento': None,
                    'icamento': None,
                    'cambagem': None,
                }
            entry = series[key]

            def _best(current, new_val):
                try:
                    nv = float(new_val) if new_val is not None else None
                except (ValueError, TypeError):
                    nv = None
                if nv is None:
                    return current
                if current is None:
                    return nv
                return max(current, nv)

            if use_tank_priority:
                limpeza_mec_cum = _preferred_numeric_value(
                    tanks,
                    ('limpeza_mecanizada_cumulativa', 'percentual_limpeza_cumulativo'),
                    fallback_row=rdo,
                    fallback_attrs=(
                        'percentual_limpeza_diario_cumulativo',
                        'limpeza_mecanizada_cumulativa',
                        'percentual_limpeza_cumulativo',
                    ),
                )
                limpeza_fina_cum = _preferred_numeric_value(
                    tanks,
                    ('limpeza_fina_cumulativa', 'percentual_limpeza_fina_cumulativo'),
                    fallback_row=rdo,
                    fallback_attrs=('percentual_limpeza_fina_cumulativo', 'limpeza_fina_cumulativa'),
                )
                avanco_cum = _preferred_numeric_value(
                    tanks,
                    ('percentual_avanco_cumulativo',),
                    fallback_row=rdo,
                    fallback_attrs=('percentual_avanco_cumulativo',),
                )
                ensacamento = _resolve_productive_percent(
                    tanks,
                    ('ensacamento_cumulativo',),
                    ('ensacamento_prev',),
                    ('percentual_ensacamento',),
                    fallback_row=rdo,
                    fallback_cumulative_attrs=('ensacamento_cumulativo',),
                    fallback_forecast_attrs=('ensacamento_previsao',),
                    fallback_percent_attrs=('percentual_ensacamento',),
                    forecast_override=ensacamento_forecast,
                    round_digits=2,
                )
                icamento = _resolve_productive_percent(
                    tanks,
                    ('icamento_cumulativo',),
                    ('icamento_prev',),
                    ('percentual_icamento',),
                    fallback_row=rdo,
                    fallback_cumulative_attrs=('icamento_cumulativo',),
                    fallback_forecast_attrs=('icamento_previsao',),
                    fallback_percent_attrs=('percentual_icamento',),
                    forecast_override=icamento_forecast,
                    round_digits=2,
                )
                cambagem = _resolve_productive_percent(
                    tanks,
                    ('cambagem_cumulativo',),
                    ('cambagem_prev',),
                    ('percentual_cambagem',),
                    fallback_row=rdo,
                    fallback_cumulative_attrs=('cambagem_cumulativo',),
                    fallback_forecast_attrs=('cambagem_previsao',),
                    fallback_percent_attrs=('percentual_cambagem',),
                    forecast_override=cambagem_forecast,
                    round_digits=2,
                )
            else:
                limpeza_mec_cum = _best_numeric_attr_value(
                    rdo,
                    (
                        'percentual_limpeza_diario_cumulativo',
                        'limpeza_mecanizada_cumulativa',
                        'percentual_limpeza_cumulativo',
                    ),
                )
                limpeza_fina_cum = _best_numeric_attr_value(
                    rdo,
                    ('percentual_limpeza_fina_cumulativo', 'limpeza_fina_cumulativa'),
                )
                avanco_cum = _best_numeric_attr_value(rdo, ('percentual_avanco_cumulativo',))
                ensacamento = _resolve_productive_percent(
                    [],
                    ('ensacamento_cumulativo',),
                    (),
                    ('percentual_ensacamento',),
                    fallback_row=rdo,
                    fallback_cumulative_attrs=('ensacamento_cumulativo',),
                    fallback_forecast_attrs=('ensacamento_previsao',),
                    fallback_percent_attrs=('percentual_ensacamento',),
                    forecast_override=ensacamento_forecast if use_tank_forecast_context else None,
                    round_digits=2,
                )
                icamento = _resolve_productive_percent(
                    [],
                    ('icamento_cumulativo',),
                    (),
                    ('percentual_icamento',),
                    fallback_row=rdo,
                    fallback_cumulative_attrs=('icamento_cumulativo',),
                    fallback_forecast_attrs=('icamento_previsao',),
                    fallback_percent_attrs=('percentual_icamento',),
                    forecast_override=icamento_forecast if use_tank_forecast_context else None,
                    round_digits=2,
                )
                cambagem = _resolve_productive_percent(
                    [],
                    ('cambagem_cumulativo',),
                    (),
                    ('percentual_cambagem',),
                    fallback_row=rdo,
                    fallback_cumulative_attrs=('cambagem_cumulativo',),
                    fallback_forecast_attrs=('cambagem_previsao',),
                    fallback_percent_attrs=('percentual_cambagem',),
                    forecast_override=cambagem_forecast if use_tank_forecast_context else None,
                    round_digits=2,
                )

            entry['limpeza_mec_cum'] = _best(entry['limpeza_mec_cum'], limpeza_mec_cum)
            entry['limpeza_fina_cum'] = _best(entry['limpeza_fina_cum'], limpeza_fina_cum)
            entry['avanco_cum'] = _best(entry['avanco_cum'], avanco_cum)
            entry['ensacamento'] = _best(entry['ensacamento'], ensacamento)
            entry['icamento'] = _best(entry['icamento'], icamento)
            entry['cambagem'] = _best(entry['cambagem'], cambagem)

        labels = list(series.keys())
        limpeza_mecanizada_values = _normalize_percent_series(
            [series[d]['limpeza_mec_cum'] for d in labels],
            round_digits=2,
            monotonic=True,
        )
        limpeza_fina_values = _normalize_percent_series(
            [series[d]['limpeza_fina_cum'] for d in labels],
            round_digits=2,
            monotonic=True,
        )
        avanco_values = _normalize_percent_series(
            [series[d]['avanco_cum'] for d in labels],
            round_digits=2,
            monotonic=True,
        )
        ensacamento_values = _normalize_percent_series(
            [series[d]['ensacamento'] for d in labels],
            round_digits=2,
            monotonic=True,
        )
        icamento_values = _normalize_percent_series(
            [series[d]['icamento'] for d in labels],
            round_digits=2,
            monotonic=True,
        )
        cambagem_values = _normalize_percent_series(
            [series[d]['cambagem'] for d in labels],
            round_digits=2,
            monotonic=True,
        )

        # Calcular contribuição diária (delta entre dias consecutivos)
        avanco_diario = _daily_from_cumulative_series(avanco_values, round_digits=2)

        datasets = {
            'limpeza_mecanizada': limpeza_mecanizada_values,
            'limpeza_fina': limpeza_fina_values,
            'avanco_geral': avanco_values,
            'avanco_diario': avanco_diario,
            'ensacamento': ensacamento_values,
            'icamento': icamento_values,
            'cambagem': cambagem_values,
        }

        return JsonResponse({
            'success': True,
            'labels': labels,
            'datasets': datasets,
            'tanques_disponiveis': tanques_disponiveis,
        })

    except Exception as e:
        logging.exception('Erro em curva_s_data')
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ─── Report Diário (Dashboard Operacional) ───────────────────────────

@_login_required
def report_diario_view(request):
    """Renderiza a página do Report Diário."""
    ordens = [
        {
            'id': ordem.id,
            'numero_os': ordem.numero_os,
            'label': _report_diario_ordem_label(ordem),
        }
        for ordem in _report_diario_ordens_queryset()
    ]
    return _render(request, 'report_diario.html', {'ordens': list(ordens)})


@require_GET
def report_diario_data(request):
    """
    API JSON – retorna todos os dados para o Report Diário.
    GET params: os_id (obrigatório), tanque (opcional)
    """
    try:
        os_id = request.GET.get('os_id')
        tanque_filter = request.GET.get('tanque', '').strip()

        if not os_id:
            return JsonResponse({'success': False, 'error': 'os_id obrigatório'}, status=400)
        try:
            os_id = int(os_id)
        except (ValueError, TypeError):
            return JsonResponse({'success': False, 'error': 'os_id inválido'}, status=400)

        os_obj, os_scope_ids = _resolve_report_os_context(os_id)
        if not os_obj:
            return JsonResponse({'success': False, 'error': 'OS não encontrada'}, status=404)

        rdo_qs = RDO.objects.filter(
            ordem_servico_id__in=os_scope_ids, data__isnull=False
        ).select_related('ordem_servico').prefetch_related(
            'atividades_rdo', 'tanques', 'membros_equipe'
        ).order_by('data')

        if not rdo_qs.exists():
            return JsonResponse({'success': True, 'empty': True})
        ordered_rdos = list(rdo_qs)

        # ── Info OS ──
        cliente_nome = ''
        unidade_nome = ''
        try:
            cliente_nome = os_obj.Cliente.nome if os_obj.Cliente else ''
        except Exception:
            pass
        try:
            unidade_nome = os_obj.Unidade.nome if os_obj.Unidade else ''
        except Exception:
            pass

        info_os = {
            'cliente': cliente_nome,
            'unidade': unidade_nome,
            'tanque': os_obj.tanque or '',
            'os': os_obj.numero_os,
            'data_inicio': os_obj.data_inicio.strftime('%d/%m/%Y') if os_obj.data_inicio else '',
            'data_fim': os_obj.data_fim.strftime('%d/%m/%Y') if os_obj.data_fim else '',
            'metodo': os_obj.metodo or '',
            'volume': float(os_obj.volume_tanque or 0),
        }

        def _normalize_operation_status(raw):
            txt = str(raw or '').strip().lower()
            if not txt:
                return ''
            txt = unicodedata.normalize('NFKD', txt).encode('ascii', 'ignore').decode('ascii')
            if 'finaliz' in txt:
                return 'finalizada'
            if 'andamento' in txt:
                return 'em_andamento'
            if 'paralis' in txt:
                return 'paralizada'
            if 'program' in txt:
                return 'programada'
            if 'cancel' in txt:
                return 'cancelada'
            return txt

        all_tank_qs = RdoTanque.objects.filter(rdo__ordem_servico_id__in=os_scope_ids)

        # ── Tanques disponíveis ──
        tanques_disponiveis = _get_tanques_disponiveis_por_os(os_id)

        effective_tank_filter = tanque_filter
        if not effective_tank_filter and len(tanques_disponiveis) == 1:
            effective_tank_filter = tanques_disponiveis[0]

        # ── Filtrar tanques se necessário ──
        tank_qs = all_tank_qs
        if effective_tank_filter:
            tank_qs = _filter_tank_queryset_by_identity(
                tank_qs,
                effective_tank_filter,
                os_num=getattr(os_obj, 'numero_os', None),
            )

        # ── Último RDO (para status dia anterior / último status) ──
        ultimo_rdo = ordered_rdos[-1] if ordered_rdos else None
        ordered_tanks = list(tank_qs.select_related('rdo').order_by('rdo__data', 'rdo__pk', 'pk'))

        # ── Percentuais % Produção (último registro) ──
        def _float(v):
            try:
                if v is None:
                    return 0
                num = round(float(v), 1)
                if num < 0:
                    return 0
                if num > 100:
                    return 100
                return num
            except (ValueError, TypeError):
                return 0

        # Sempre usar o último snapshot do tanque filtrado como referência do tanque.
        last_tank = ordered_tanks[-1] if ordered_tanks else None
        last_tank_rdo = getattr(last_tank, 'rdo', None) if last_tank else None
        use_tank_forecast_context = bool(effective_tank_filter) or len(tanques_disponiveis) <= 1
        ensacamento_forecast = _latest_numeric_value(
            ordered_tanks if use_tank_forecast_context else [],
            ('ensacamento_prev',),
            fallback_row=ultimo_rdo,
            fallback_attrs=('ensacamento_previsao',),
            require_positive=True,
        )
        icamento_forecast = _latest_numeric_value(
            ordered_tanks if use_tank_forecast_context else [],
            ('icamento_prev',),
            fallback_row=ultimo_rdo,
            fallback_attrs=('icamento_previsao',),
            require_positive=True,
        )
        cambagem_forecast = _latest_numeric_value(
            ordered_tanks if use_tank_forecast_context else [],
            ('cambagem_prev',),
            fallback_row=ultimo_rdo,
            fallback_attrs=('cambagem_previsao',),
            require_positive=True,
        )

        def _tank_label(tank_obj):
            if not tank_obj:
                return ''
            for attr in ('tanque_codigo', 'nome_tanque'):
                raw = getattr(tank_obj, attr, None)
                if raw not in (None, ''):
                    return str(raw).strip()
            return ''

        selected_tank_label = effective_tank_filter
        if not selected_tank_label and len(tanques_disponiveis) <= 1:
            selected_tank_label = _tank_label(last_tank) or (os_obj.tanque or '')
        if selected_tank_label:
            info_os['tanque'] = selected_tank_label
        setup_completed = any(_rdo_has_setup_activity(rdo) for rdo in ordered_rdos)

        producao = {
            'setup': 100.0 if setup_completed else 0.0,
            'raspagem': _float(_preferred_numeric_value(
                [last_tank] if last_tank else [],
                ('limpeza_mecanizada_cumulativa', 'percentual_limpeza_cumulativo'),
                fallback_row=ultimo_rdo,
                fallback_attrs=(
                    'limpeza_mecanizada_cumulativa',
                    'percentual_limpeza_cumulativo',
                    'percentual_limpeza_diario_cumulativo',
                ),
            )),
            'ensacamento': _float(_resolve_productive_percent(
                [last_tank] if last_tank else [],
                ('ensacamento_cumulativo',),
                ('ensacamento_prev',),
                ('percentual_ensacamento',),
                fallback_row=ultimo_rdo,
                fallback_cumulative_attrs=('ensacamento_cumulativo',),
                fallback_forecast_attrs=('ensacamento_previsao',),
                fallback_percent_attrs=('percentual_ensacamento',),
                forecast_override=ensacamento_forecast,
            )),
            'icamento': _float(_resolve_productive_percent(
                [last_tank] if last_tank else [],
                ('icamento_cumulativo',),
                ('icamento_prev',),
                ('percentual_icamento',),
                fallback_row=ultimo_rdo,
                fallback_cumulative_attrs=('icamento_cumulativo',),
                fallback_forecast_attrs=('icamento_previsao',),
                fallback_percent_attrs=('percentual_icamento',),
                forecast_override=icamento_forecast,
            )),
            'cambagem': _float(_resolve_productive_percent(
                [last_tank] if last_tank else [],
                ('cambagem_cumulativo',),
                ('cambagem_prev',),
                ('percentual_cambagem',),
                fallback_row=ultimo_rdo,
                fallback_cumulative_attrs=('cambagem_cumulativo',),
                fallback_forecast_attrs=('cambagem_previsao',),
                fallback_percent_attrs=('percentual_cambagem',),
                forecast_override=cambagem_forecast,
            )),
            'limpeza_fina': _float(_preferred_numeric_value(
                [last_tank] if last_tank else [],
                ('limpeza_fina_cumulativa', 'percentual_limpeza_fina_cumulativo'),
                fallback_row=ultimo_rdo,
                fallback_attrs=('limpeza_fina_cumulativa', 'percentual_limpeza_fina_cumulativo'),
            )),
            'avanco_total': _float(_preferred_numeric_value(
                [last_tank] if last_tank else [],
                ('percentual_avanco_cumulativo',),
                fallback_row=ultimo_rdo,
                fallback_attrs=('percentual_avanco_cumulativo',),
            )),
        }

        # ── Curva S (série temporal) ──
        def _pct_or_none(*values):
            best = None
            for value in values:
                try:
                    if value in (None, ''):
                        continue
                    num = round(float(value), 1)
                    if num < 0:
                        num = 0.0
                    if num > 100:
                        num = 100.0
                except (ValueError, TypeError):
                    continue
                if best is None or num > best:
                    best = num
            return best

        def _pct_or_zero(*values):
            picked = _pct_or_none(*values)
            return round(float(picked or 0), 1)

        def _daily_pct_from_quantity(day_value, forecast_value):
            try:
                if day_value in (None, '') or forecast_value in (None, ''):
                    return None
                forecast_num = float(forecast_value)
                if forecast_num <= 0:
                    return None
                pct = (float(day_value) / forecast_num) * 100.0
                if pct < 0:
                    pct = 0.0
                if pct > 100:
                    pct = 100.0
                return round(pct, 1)
            except (TypeError, ValueError):
                return None

        def _series_terminal(values):
            for raw in reversed(values):
                try:
                    if raw in (None, ''):
                        continue
                    num = round(float(raw), 1)
                except (ValueError, TypeError):
                    continue
                if num > 0:
                    return num
            valid_values = []
            for raw in values:
                try:
                    if raw in (None, ''):
                        continue
                    valid_values.append(round(float(raw), 1))
                except (ValueError, TypeError):
                    continue
            return max(valid_values) if valid_values else 0.0

        tank_rows_by_rdo = {}
        for tank in ordered_tanks:
            tank_rows_by_rdo.setdefault(tank.rdo_id, []).append(tank)

        single_tank_context = len(tanques_disponiveis) <= 1
        tracked_rdos = [
            rdo for rdo in ordered_rdos
            if (
                not effective_tank_filter
                or single_tank_context
                or tank_rows_by_rdo.get(rdo.id)
            )
        ]
        tracked_setup_activity_rdo_ids = set()
        tracked_setup_activity_dates = []
        for rdo in ordered_rdos:
            actual_dt = getattr(rdo, 'data', None)
            if not actual_dt or not _rdo_has_setup_activity(rdo):
                continue
            tracked_setup_activity_rdo_ids.add(rdo.id)
            tracked_setup_activity_dates.append(actual_dt)
        tracked_setup_activity_dates = sorted(set(tracked_setup_activity_dates))
        tracked_total_setup_days = len(tracked_setup_activity_dates)

        curva_labels = []
        curva_avanco_diario = []
        curva_avanco_acum = []
        curva_raspagem_acum = []
        curva_ensacamento_acum = []
        curva_icamento_acum = []
        curva_cambagem_acum = []
        curva_limpeza_fina_acum = []
        curva_actual_dates = []
        actual_avanco_by_date = {}
        actual_daily_by_date = {}
        total_avanco_weight = 5.0 + 70.0 + 7.0 + 7.0 + 5.0 + 6.0
        setup_activity_rdo_ids = set(
            RDOAtividade.objects.filter(
                rdo__ordem_servico_id__in=os_scope_ids
            ).filter(
                Q(atividade__iexact='Instalação / Preparação / Montagem / Setup ')
                | Q(atividade__iexact='Instalação / Preparação / Montagem / Setup')
                | Q(atividade__icontains='setup')
            ).values_list('rdo_id', flat=True)
        )
        setup_activity_rdo_ids = tracked_setup_activity_rdo_ids
        setup_completed = False

        def _avanco_with_setup(raspagem, ensacamento, icamento, cambagem, limpeza_fina, setup_pct):
            def _safe_pct(value):
                try:
                    number = float(value or 0)
                except Exception:
                    number = 0.0
                if number < 0:
                    return 0.0
                if number > 100:
                    return 100.0
                return number

            weighted_total = (
                (5.0 * _safe_pct(setup_pct))
                + (70.0 * _safe_pct(raspagem))
                + (7.0 * _safe_pct(ensacamento))
                + (7.0 * _safe_pct(icamento))
                + (5.0 * _safe_pct(cambagem))
                + (6.0 * _safe_pct(limpeza_fina))
            )
            return round(weighted_total / float(total_avanco_weight), 1)

        def _daily_avanco_value(tanks, fallback_row, has_setup_today):
            def _has_positive_value(raw_value):
                try:
                    return raw_value not in (None, '') and float(raw_value) > 0
                except (TypeError, ValueError):
                    return False

            limpeza_dia_raw = _preferred_numeric_value(
                tanks,
                ('percentual_limpeza_diario', 'limpeza_mecanizada_diaria'),
                fallback_row=fallback_row,
                fallback_attrs=('percentual_limpeza_diario', 'limpeza_mecanizada_diaria'),
            )
            limpeza_fina_dia_raw = _preferred_numeric_value(
                tanks,
                ('percentual_limpeza_fina_diario', 'limpeza_fina_diaria'),
                fallback_row=fallback_row,
                fallback_attrs=('percentual_limpeza_fina_diario', 'limpeza_fina_diaria'),
            )
            ensacamento_dia_raw = _preferred_numeric_value(
                tanks,
                ('ensacamento_dia',),
                fallback_row=fallback_row,
                fallback_attrs=('ensacamento_dia',),
            )
            icamento_dia_raw = _preferred_numeric_value(
                tanks,
                ('icamento_dia',),
                fallback_row=fallback_row,
                fallback_attrs=('icamento_dia',),
            )
            cambagem_dia_raw = _preferred_numeric_value(
                tanks,
                ('cambagem_dia',),
                fallback_row=fallback_row,
                fallback_attrs=('cambagem_dia',),
            )
            ensacamento_prev = _preferred_numeric_value(
                tanks,
                ('ensacamento_prev',),
                fallback_row=fallback_row,
                fallback_attrs=('ensacamento_previsao',),
            )
            icamento_prev = _preferred_numeric_value(
                tanks,
                ('icamento_prev',),
                fallback_row=fallback_row,
                fallback_attrs=('icamento_previsao',),
            )
            cambagem_prev = _preferred_numeric_value(
                tanks,
                ('cambagem_prev',),
                fallback_row=fallback_row,
                fallback_attrs=('cambagem_previsao',),
            )

            has_explicit_daily = any((
                has_setup_today,
                _has_positive_value(limpeza_dia_raw),
                _has_positive_value(limpeza_fina_dia_raw),
                _has_positive_value(ensacamento_dia_raw),
                _has_positive_value(icamento_dia_raw),
                _has_positive_value(cambagem_dia_raw),
            ))
            if has_explicit_daily:
                return _avanco_with_setup(
                    _pct_or_zero(limpeza_dia_raw),
                    _daily_pct_from_quantity(ensacamento_dia_raw, ensacamento_prev) or 0.0,
                    _daily_pct_from_quantity(icamento_dia_raw, icamento_prev) or 0.0,
                    _daily_pct_from_quantity(cambagem_dia_raw, cambagem_prev) or 0.0,
                    _pct_or_zero(limpeza_fina_dia_raw),
                    100.0 if has_setup_today else 0.0,
                )

            return None

        for rdo in tracked_rdos:
            dt_str = rdo.data.strftime('%d/%m') if rdo.data else None
            if not dt_str:
                continue

            tanks = tank_rows_by_rdo.get(rdo.id, [])
            using_tank_series = bool(effective_tank_filter) and (single_tank_context or bool(tanks))

            if using_tank_series:
                avanco = _pct_or_zero(_preferred_numeric_value(
                    tanks,
                    ('percentual_avanco_cumulativo',),
                    fallback_row=rdo,
                    fallback_attrs=('percentual_avanco_cumulativo',),
                ))
                raspagem = _pct_or_zero(_preferred_numeric_value(
                    tanks,
                    ('limpeza_mecanizada_cumulativa', 'percentual_limpeza_cumulativo'),
                    fallback_row=rdo,
                    fallback_attrs=(
                        'limpeza_mecanizada_cumulativa',
                        'percentual_limpeza_cumulativo',
                        'percentual_limpeza_diario_cumulativo',
                    ),
                ))
                ensacamento = _pct_or_zero(_resolve_productive_percent(
                    tanks,
                    ('ensacamento_cumulativo',),
                    ('ensacamento_prev',),
                    ('percentual_ensacamento',),
                    fallback_row=rdo,
                    fallback_cumulative_attrs=('ensacamento_cumulativo',),
                    fallback_forecast_attrs=('ensacamento_previsao',),
                    fallback_percent_attrs=('percentual_ensacamento',),
                    forecast_override=ensacamento_forecast,
                ))
                icamento = _pct_or_zero(_resolve_productive_percent(
                    tanks,
                    ('icamento_cumulativo',),
                    ('icamento_prev',),
                    ('percentual_icamento',),
                    fallback_row=rdo,
                    fallback_cumulative_attrs=('icamento_cumulativo',),
                    fallback_forecast_attrs=('icamento_previsao',),
                    fallback_percent_attrs=('percentual_icamento',),
                    forecast_override=icamento_forecast,
                ))
                cambagem = _pct_or_zero(_resolve_productive_percent(
                    tanks,
                    ('cambagem_cumulativo',),
                    ('cambagem_prev',),
                    ('percentual_cambagem',),
                    fallback_row=rdo,
                    fallback_cumulative_attrs=('cambagem_cumulativo',),
                    fallback_forecast_attrs=('cambagem_previsao',),
                    fallback_percent_attrs=('percentual_cambagem',),
                    forecast_override=cambagem_forecast,
                ))
                limpeza_fina = _pct_or_zero(_preferred_numeric_value(
                    tanks,
                    ('limpeza_fina_cumulativa', 'percentual_limpeza_fina_cumulativo'),
                    fallback_row=rdo,
                    fallback_attrs=('limpeza_fina_cumulativa', 'percentual_limpeza_fina_cumulativo'),
                ))
            else:
                avanco = _pct_or_zero(getattr(rdo, 'percentual_avanco_cumulativo', None))
                raspagem = _pct_or_zero(
                    getattr(rdo, 'limpeza_mecanizada_cumulativa', None),
                    getattr(rdo, 'percentual_limpeza_cumulativo', None),
                    getattr(rdo, 'percentual_limpeza_diario_cumulativo', None),
                )
                ensacamento = _pct_or_zero(_resolve_productive_percent(
                    [],
                    ('ensacamento_cumulativo',),
                    (),
                    ('percentual_ensacamento',),
                    fallback_row=rdo,
                    fallback_cumulative_attrs=('ensacamento_cumulativo',),
                    fallback_forecast_attrs=('ensacamento_previsao',),
                    fallback_percent_attrs=('percentual_ensacamento',),
                    forecast_override=ensacamento_forecast if use_tank_forecast_context else None,
                ))
                icamento = _pct_or_zero(_resolve_productive_percent(
                    [],
                    ('icamento_cumulativo',),
                    (),
                    ('percentual_icamento',),
                    fallback_row=rdo,
                    fallback_cumulative_attrs=('icamento_cumulativo',),
                    fallback_forecast_attrs=('icamento_previsao',),
                    fallback_percent_attrs=('percentual_icamento',),
                    forecast_override=icamento_forecast if use_tank_forecast_context else None,
                ))
                cambagem = _pct_or_zero(_resolve_productive_percent(
                    [],
                    ('cambagem_cumulativo',),
                    (),
                    ('percentual_cambagem',),
                    fallback_row=rdo,
                    fallback_cumulative_attrs=('cambagem_cumulativo',),
                    fallback_forecast_attrs=('cambagem_previsao',),
                    fallback_percent_attrs=('percentual_cambagem',),
                    forecast_override=cambagem_forecast if use_tank_forecast_context else None,
                ))
                limpeza_fina = _pct_or_zero(
                    getattr(rdo, 'limpeza_fina_cumulativa', None),
                    getattr(rdo, 'percentual_limpeza_fina_cumulativo', None),
                )
            has_setup_today = bool(rdo.id in setup_activity_rdo_ids and getattr(rdo, 'data', None))
            avanco_diario_real = _daily_avanco_value(tanks, rdo, has_setup_today)
            if has_setup_today:
                setup_completed = True
            setup_progress_pct = 100.0 if setup_completed else 0.0
            avanco = _avanco_with_setup(
                raspagem,
                ensacamento,
                icamento,
                cambagem,
                limpeza_fina,
                setup_progress_pct,
            )
            curva_labels.append(dt_str)
            curva_avanco_acum.append(avanco)
            curva_avanco_diario.append(avanco_diario_real)
            curva_raspagem_acum.append(raspagem)
            curva_ensacamento_acum.append(ensacamento)
            curva_icamento_acum.append(icamento)
            curva_cambagem_acum.append(cambagem)
            curva_limpeza_fina_acum.append(limpeza_fina)
            actual_dt = getattr(rdo, 'data', None)
            curva_actual_dates.append(actual_dt)
            if actual_dt:
                actual_avanco_by_date[actual_dt] = max(actual_avanco_by_date.get(actual_dt, 0), avanco)
                if avanco_diario_real not in (None, ''):
                    actual_daily_by_date[actual_dt] = max(actual_daily_by_date.get(actual_dt, 0), avanco_diario_real)

        curva_avanco_acum = _normalize_percent_series(curva_avanco_acum, round_digits=1, monotonic=True)
        curva_avanco_diario = _normalize_percent_series(curva_avanco_diario, round_digits=1, monotonic=False)
        curva_avanco_diario_fallback = _daily_from_cumulative_series(curva_avanco_acum, round_digits=1)
        curva_avanco_diario = [
            curva_avanco_diario_fallback[idx] if raw in (None, '') else raw
            for idx, raw in enumerate(curva_avanco_diario)
        ]
        actual_daily_by_date = {}
        for idx, actual_dt in enumerate(curva_actual_dates):
            if not actual_dt:
                continue
            actual_daily_by_date[actual_dt] = max(
                actual_daily_by_date.get(actual_dt, 0),
                float(curva_avanco_diario[idx] or 0),
            )
        curva_raspagem_acum = _normalize_percent_series(curva_raspagem_acum, round_digits=1, monotonic=True)
        curva_ensacamento_acum = _normalize_percent_series(curva_ensacamento_acum, round_digits=1, monotonic=True)
        curva_icamento_acum = _normalize_percent_series(curva_icamento_acum, round_digits=1, monotonic=True)
        curva_cambagem_acum = _normalize_percent_series(curva_cambagem_acum, round_digits=1, monotonic=True)
        curva_limpeza_fina_acum = _normalize_percent_series(curva_limpeza_fina_acum, round_digits=1, monotonic=True)

        producao.update({
            'raspagem': _series_terminal(curva_raspagem_acum),
            'ensacamento': _series_terminal(curva_ensacamento_acum),
            'icamento': _series_terminal(curva_icamento_acum),
            'cambagem': _series_terminal(curva_cambagem_acum),
            'limpeza_fina': _series_terminal(curva_limpeza_fina_acum),
            'avanco_total': _series_terminal(curva_avanco_acum),
        })

        if curva_avanco_acum:
            producao['avanco_total'] = _series_terminal(curva_avanco_acum)

        # Diário = delta entre dias consecutivos
        curva_avanco_diario = _normalize_percent_series(curva_avanco_diario, round_digits=1, monotonic=False)

        # ── KPI Acumulado ──
        ordered_rdos = [r for r in ordered_rdos if getattr(r, 'data', None)]

        def _pick_latest_numeric(rows, attrs, default=0.0):
            for row in reversed(list(rows or [])):
                if row is None:
                    continue
                for attr in attrs:
                    try:
                        value = getattr(row, attr, None)
                    except Exception:
                        value = None
                    if value in (None, ''):
                        continue
                    try:
                        return float(value)
                    except (TypeError, ValueError):
                        continue
            return float(default or 0.0)

        def _clamp_float(value, min_value=0.0, max_value=100.0):
            try:
                number = float(value)
            except (TypeError, ValueError):
                number = float(min_value)
            if number < min_value:
                return float(min_value)
            if number > max_value:
                return float(max_value)
            return float(number)

        def _smoothstep(value):
            x = _clamp_float(value, 0.0, 1.0)
            return (x * x) * (3.0 - (2.0 * x))

        def _smootherstep(value):
            x = _clamp_float(value, 0.0, 1.0)
            return (x * x * x) * ((x * ((x * 6.0) - 15.0)) + 10.0)

        def _sigmoidstep(value, steepness=10.0):
            x = _clamp_float(value, 0.0, 1.0)
            k = max(1.0, float(steepness or 10.0))
            start = 1.0 / (1.0 + math.exp(-k * (0.0 - 0.5)))
            end = 1.0 / (1.0 + math.exp(-k * (1.0 - 0.5)))
            raw = 1.0 / (1.0 + math.exp(-k * (x - 0.5)))
            span = end - start
            if abs(span) < 1e-9:
                return _smoothstep(x)
            normalized = (raw - start) / span
            return _clamp_float(normalized, 0.0, 1.0)

        def _phase_indices(total_days, start_fraction, end_fraction):
            total = max(1, int(total_days or 1))
            if total == 1:
                return (0, 0)
            start = _clamp_float(start_fraction, 0.0, 1.0)
            end = _clamp_float(end_fraction, start, 1.0)
            start_idx = int(round(start * float(total - 1)))
            end_idx = int(round(end * float(total - 1)))
            if end_idx < start_idx:
                end_idx = start_idx
            return (start_idx, end_idx)

        def _phase_progress(day_idx, phase_idx):
            start_idx, end_idx = phase_idx
            if day_idx < start_idx:
                return 0.0
            if day_idx >= end_idx:
                return 100.0
            span = max(1, (end_idx - start_idx) + 1)
            ratio = float(day_idx - start_idx + 1) / float(span)
            return round(100.0 * _smoothstep(ratio), 1)

        def _fit_phase_window(center, duration, min_fraction, max_fraction):
            center_val = _clamp_float(center, min_fraction, max_fraction)
            duration_val = max(0.0, float(duration or 0.0))
            start_val = center_val - (duration_val / 2.0)
            end_val = center_val + (duration_val / 2.0)
            if start_val < min_fraction:
                end_val += (min_fraction - start_val)
                start_val = min_fraction
            if end_val > max_fraction:
                start_val -= (end_val - max_fraction)
                end_val = max_fraction
            start_val = max(min_fraction, start_val)
            end_val = min(max_fraction, end_val)
            if end_val < start_val:
                end_val = start_val
            return (start_val, end_val)

        first_rdo_date = ordered_rdos[0].data if ordered_rdos else None
        last_rdo_date = ordered_rdos[-1].data if ordered_rdos else None
        total_avanco_weight = 5.0 + 70.0 + 7.0 + 7.0 + 5.0 + 6.0
        tank_planned_end_date = None
        try:
            if ordered_tanks:
                unique_tank_keys = set()
                try:
                    os_num_ref = getattr(os_obj, 'numero_os', None)
                except Exception:
                    os_num_ref = None
                for row in ordered_tanks:
                    try:
                        key = _tank_identity_key(
                            getattr(row, 'tanque_codigo', None),
                            getattr(row, 'nome_tanque', None),
                            os_num=os_num_ref,
                        )
                    except Exception:
                        key = None
                    if key:
                        unique_tank_keys.add(key)
                if effective_tank_filter or len(unique_tank_keys) == 1:
                    for row in reversed(ordered_tanks):
                        previsao = getattr(row, 'previsao_termino', None)
                        if previsao:
                            tank_planned_end_date = previsao
                            break
        except Exception:
            tank_planned_end_date = None
        planned_start_date = (
            first_rdo_date
            or getattr(os_obj, 'data_inicio_frente', None)
            or getattr(os_obj, 'data_inicio', None)
            or last_rdo_date
        )
        planned_end_date = tank_planned_end_date or getattr(os_obj, 'data_fim_frente', None) or getattr(os_obj, 'data_fim', None)
        if not planned_end_date:
            days_hint = (
                getattr(os_obj, 'dias_de_operacao_frente', 0)
                or getattr(os_obj, 'dias_de_operacao', 0)
                or 0
            )
            try:
                days_hint = int(days_hint or 0)
            except Exception:
                days_hint = 0
            if planned_start_date and days_hint > 0:
                planned_end_date = planned_start_date + datetime.timedelta(days=max(0, days_hint - 1))
            else:
                planned_end_date = last_rdo_date or planned_start_date

        if first_rdo_date and planned_start_date and first_rdo_date < planned_start_date:
            planned_start_date = first_rdo_date
        if not planned_start_date:
            planned_start_date = planned_end_date or datetime.date.today()
        if not planned_end_date or planned_end_date < planned_start_date:
            planned_end_date = planned_start_date

        calendar_end_date = planned_end_date
        if last_rdo_date and (calendar_end_date is None or last_rdo_date > calendar_end_date):
            calendar_end_date = last_rdo_date
        if not calendar_end_date or calendar_end_date < planned_start_date:
            calendar_end_date = planned_start_date

        planned_calendar_days = max(1, ((planned_end_date - planned_start_date).days + 1))
        calendar_total_days = max(1, ((calendar_end_date - planned_start_date).days + 1))

        def _build_programado_series(total_days, setup_days):
            total = max(1, int(total_days or 1))
            if total <= 1:
                return ([100.0], [100.0])

            try:
                setup_days_count = int(setup_days or 0)
            except Exception:
                setup_days_count = 0
            setup_days_count = max(0, setup_days_count)
            if setup_days_count > 0 and total > 1:
                setup_days_count = min(setup_days_count, total - 1)
            else:
                setup_days_count = 0

            daily = []
            setup_total_pct = 5 if setup_days_count > 0 else 0
            if setup_days_count > 0:
                setup_daily = [0] * setup_days_count
                for idx in range(setup_total_pct):
                    setup_daily[idx % setup_days_count] += 1
                daily.extend(float(value) for value in setup_daily)

            remaining_days = total - len(daily)
            if remaining_days <= 0:
                remaining_days = total
                daily = []
                setup_total_pct = 0

            remaining_total_pct = 100 - setup_total_pct
            if remaining_days > 0:
                if remaining_days == 1:
                    remaining_daily = [float(remaining_total_pct)]
                else:
                    remaining_accumulated = []
                    for idx in range(remaining_days):
                        ratio = float(idx + 1) / float(remaining_days)
                        target = round(float(remaining_total_pct) * _sigmoidstep(ratio, steepness=11.0), 1)
                        if remaining_accumulated and target < remaining_accumulated[-1]:
                            target = remaining_accumulated[-1]
                        remaining_accumulated.append(target)
                    if remaining_accumulated:
                        remaining_accumulated[-1] = float(remaining_total_pct)

                    remaining_daily = []
                    previous_target = 0.0
                    for target in remaining_accumulated:
                        daily_value = round(max(0.0, float(target) - previous_target), 1)
                        remaining_daily.append(daily_value)
                        previous_target = float(target)
                daily.extend(float(value) for value in remaining_daily)

            normalized_accumulated = []
            running_total = 0.0
            for value in daily:
                running_total = round(running_total + float(value or 0), 1)
                normalized_accumulated.append(min(100.0, running_total))
            if normalized_accumulated:
                normalized_accumulated[-1] = 100.0

            return (daily, normalized_accumulated)

        planned_setup_days = 1
        planned_daily_series, planned_accumulated_series = _build_programado_series(
            planned_calendar_days,
            planned_setup_days,
        )

        comparativo_avanco_labels = []
        realizado_acumulado = []
        realizado_diario = []
        programado_acumulado = []
        programado_diario = []
        running_realizado = 0.0
        last_actual_date = max(actual_avanco_by_date.keys()) if actual_avanco_by_date else None

        for offset in range(calendar_total_days):
            current_date = planned_start_date + datetime.timedelta(days=offset)
            comparativo_avanco_labels.append(current_date.strftime('%d/%m'))

            actual_today = actual_avanco_by_date.get(current_date)
            if actual_today is not None:
                running_realizado = max(running_realizado, _clamp_float(actual_today, 0.0, 100.0))
            running_realizado = _clamp_float(running_realizado, 0.0, 100.0)
            if last_actual_date is None or current_date > last_actual_date:
                realizado_acumulado.append(None)
                realizado_diario.append(None)
            else:
                realizado_acumulado.append(round(running_realizado, 1))
                realizado_diario.append(round(float(actual_daily_by_date.get(current_date, 0.0) or 0.0), 1))

            planned_day_index = min(offset, planned_calendar_days - 1)
            programado_value = float(planned_accumulated_series[planned_day_index] or 0)
            if current_date > planned_end_date:
                programado_diario.append(None)
                programado_acumulado.append(None)
            else:
                programado_diario.append(float(planned_daily_series[planned_day_index] or 0))
                programado_acumulado.append(programado_value)

        def _time_str(t):
            if t is None:
                return '0:00:00'
            try:
                if hasattr(t, 'hour'):
                    return f"{t.hour}:{t.minute:02d}:00"
                return str(t)
            except Exception:
                return '0:00:00'

        def _to_int_or_none(raw):
            try:
                if raw in (None, ''):
                    return None
                return int(raw)
            except Exception:
                try:
                    return int(float(raw))
                except Exception:
                    return None

        def _to_float_or_none(raw):
            try:
                if raw in (None, ''):
                    return None
                return float(raw)
            except Exception:
                return None

        def _latest_tanks_for_kpi(queryset):
            latest = []
            seen = set()
            for tank_obj in queryset.select_related('rdo').order_by('-rdo__data', '-rdo__pk', '-pk'):
                key = (_tank_label(tank_obj) or f'pk:{tank_obj.pk}').strip().lower()
                if key in seen:
                    continue
                seen.add(key)
                latest.append(tank_obj)
            return latest

        # POB médio
        pobs = [r.pob for r in rdo_qs if r.pob]
        pob_medio = round(sum(pobs) / len(pobs)) if pobs else 0

        # Dias a bordo
        dias_bordo = len(rdo_qs)

        # HH disponível e HH real do último RDO
        hh_disponivel = _time_str(getattr(ultimo_rdo, 'hh_disponivel_cumulativo', None))
        hh_real_value = getattr(ultimo_rdo, 'total_hh_cumulativo_real', None)
        try:
            if ultimo_rdo is not None and hasattr(ultimo_rdo, 'compute_total_hh_cumulativo_real'):
                computed_hh_real = ultimo_rdo.compute_total_hh_cumulativo_real()
                if computed_hh_real is not None:
                    hh_real_value = computed_hh_real
        except Exception:
            pass
        hh_real = _time_str(hh_real_value)

        # Total hrs abert. PT
        total_pt_min = sum(r.total_abertura_pt_min for r in rdo_qs)
        total_pt_h = total_pt_min // 60
        total_pt_m = total_pt_min % 60
        total_pt_str = f"{total_pt_h}:{total_pt_m:02d}:00"

        # Resíduos acumulados
        sacos_total = 0
        tambores_total = 0
        solidos_total = 0.0
        liquido_total = 0
        latest_kpi_tanks = _latest_tanks_for_kpi(tank_qs)
        sacos_from_tanks = _sum_numeric_from_rows(latest_kpi_tanks, ('ensacamento_cumulativo', 'ensacamento_dia'))
        tambores_from_tanks = _sum_numeric_from_rows(latest_kpi_tanks, ('tambores_cumulativo', 'tambores_dia'))
        solidos_from_tanks = _sum_numeric_from_rows(latest_kpi_tanks, ('residuos_solidos_cumulativo', 'residuos_solidos'))
        liquido_from_tanks = _sum_numeric_from_rows(latest_kpi_tanks, ('total_liquido_cumulativo', 'total_liquido'))

        if sacos_from_tanks is not None:
            sacos_total = int(round(sacos_from_tanks))
        else:
            ultimo_rdo_ens = _to_int_or_none(getattr(ultimo_rdo, 'ensacamento_cumulativo', None))
            if ultimo_rdo_ens is not None:
                sacos_total = ultimo_rdo_ens
            else:
                sacos_total = sum((_to_int_or_none(getattr(rdo, 'ensacamento', None)) or 0) for rdo in rdo_qs)

        if tambores_from_tanks is not None:
            tambores_total = int(round(tambores_from_tanks))
        else:
            tambores_total = sum((_to_int_or_none(getattr(rdo, 'tambores', None)) or 0) for rdo in rdo_qs)

        if liquido_from_tanks is not None:
            liquido_total = int(round(liquido_from_tanks))
        else:
            liquido_total = sum((_to_int_or_none(getattr(rdo, 'total_liquido', None)) or 0) for rdo in rdo_qs)

        if solidos_from_tanks is not None:
            solidos_total = float(solidos_from_tanks)
        else:
            solidos_total = sum((_to_float_or_none(getattr(rdo, 'total_solidos', None)) or 0.0) for rdo in rdo_qs)

        compartimentos = _preferred_attr_value(
            last_tank,
            ('numero_compartimentos',),
            fallback_row=ultimo_rdo,
            fallback_attrs=('numero_compartimentos',),
        )
        if compartimentos in (None, ''):
            compartimentos = 0

        gavetas = _preferred_attr_value(
            last_tank,
            ('gavetas',),
            fallback_row=ultimo_rdo,
            fallback_attrs=('gavetas',),
        )
        if gavetas in (None, ''):
            gavetas = '-'

        kpi = {
            'pob_medio': pob_medio,
            'hh_disponivel': hh_disponivel,
            'total_pt': total_pt_str,
            'dias_bordo': dias_bordo,
            'hh_real': hh_real,
            'sacos': sacos_total,
            'tambores': tambores_total,
            'solidos': round(solidos_total, 2),
            'liquido': liquido_total,
            'compartimentos': compartimentos,
            'gavetas': gavetas,
        }

        # ── Status dia anterior ──
        status_texto = getattr(ultimo_rdo, 'ultimo_status', '') or ''
        obs_pt = getattr(ultimo_rdo, 'observacoes_rdo_pt', '') or ''
        status = status_texto or obs_pt

        # ── Anotações e observações por RDO ──
        anotacoes_observacoes = []
        for rdo in rdo_qs:
            dt_str = rdo.data.strftime('%d/%m/%Y') if rdo.data else ''
            observacao = (
                getattr(rdo, 'observacoes_rdo_pt', None)
                or getattr(rdo, 'comentario_pt', None)
                or ''
            )
            anotacoes_observacoes.append({
                'data': dt_str,
                'observacao': str(observacao or '').strip(),
            })

        # ── HH por dia (espaço confinado efetivo / não efetivo / fora) ──
        hh_dia_labels = []
        hh_ec_efetivo = []
        hh_ec_nao_efetivo = []
        hh_fora_efetivo = []
        hh_fora_nao_efetivo = []
        equipe_operacional = []
        equipe_confinado = []
        total_pt_dia = []
        produtividade_hh_efetivo_total_min = 0
        produtividade_hh_total_min = 0

        for rdo in rdo_qs:
            dt_str = rdo.data.strftime('%d/%m') if rdo.data else None
            if not dt_str:
                continue
            hh_dia_labels.append(dt_str)

            confinado_min = rdo.total_confinado_min
            efetivo_min = rdo.total_atividades_efetivas_min
            nao_efetivo_min = rdo.total_atividades_nao_efetivas_fora_min
            pt_min = rdo.total_abertura_pt_min

            # EC efetivo = tempo confinado (excluindo não efetivo confinado)
            n_eff_conf = 0
            try:
                tanks = list(tank_qs.filter(rdo=rdo))
                tank_n_eff_conf = _sum_numeric_from_rows(tanks, ('total_n_efetivo_confinado',))
                if tank_n_eff_conf is not None:
                    n_eff_conf = int(round(tank_n_eff_conf))
                else:
                    n_eff_conf = int(round(float(getattr(rdo, 'total_n_efetivo_confinado', 0) or 0)))
            except Exception:
                n_eff_conf = (rdo.total_n_efetivo_confinado or 0)

            ec_eff = max(0, confinado_min - n_eff_conf)
            ec_neff = n_eff_conf

            # Fora do EC
            fora_eff = max(0, efetivo_min - confinado_min)
            fora_neff = nao_efetivo_min

            def _min_to_hhmm(m):
                h = m // 60
                r = m % 60
                return f"{h}:{r:02d}:00"

            hh_ec_efetivo.append(_min_to_hhmm(ec_eff))
            hh_ec_nao_efetivo.append(_min_to_hhmm(ec_neff))
            hh_fora_efetivo.append(_min_to_hhmm(fora_eff))
            hh_fora_nao_efetivo.append(_min_to_hhmm(fora_neff))
            total_pt_dia.append(_min_to_hhmm(pt_min))
            hh_efetivo_dia = max(0, ec_eff + fora_eff)
            hh_total_dia = max(0, hh_efetivo_dia + ec_neff + fora_neff)
            produtividade_hh_efetivo_total_min += hh_efetivo_dia
            produtividade_hh_total_min += hh_total_dia

            # Equipe
            membros = rdo.membros_equipe.all()
            equipe_operacional.append(membros.count())
            equipe_confinado.append(rdo.operadores_simultaneos or 0)

        hh_breakdown = {
            'labels': hh_dia_labels,
            'ec_efetivo': hh_ec_efetivo,
            'ec_nao_efetivo': hh_ec_nao_efetivo,
            'fora_efetivo': hh_fora_efetivo,
            'fora_nao_efetivo': hh_fora_nao_efetivo,
            'total_pt_dia': total_pt_dia,
            'equipe_operacional': equipe_operacional,
            'equipe_confinado': equipe_confinado,
        }

        # ── HH totais para pie charts ──
        total_ec_eff_min = sum(r.total_confinado_min for r in rdo_qs)
        total_ec_neff_min = 0
        for rdo in rdo_qs:
            tanks = list(tank_qs.filter(rdo=rdo))
            tank_n_eff_conf = _sum_numeric_from_rows(tanks, ('total_n_efetivo_confinado',))
            if tank_n_eff_conf is not None:
                total_ec_neff_min += int(round(tank_n_eff_conf))
            else:
                total_ec_neff_min += (rdo.total_n_efetivo_confinado or 0)

        total_fora_eff_min = sum(max(0, r.total_atividades_efetivas_min - r.total_confinado_min) for r in rdo_qs)
        total_fora_neff_min = sum(r.total_atividades_nao_efetivas_fora_min for r in rdo_qs)

        def _min_to_str(m):
            h = m // 60; r = m % 60
            return f"{h}:{r:02d}:00"

        hh_totais = {
            'ec_efetivo': _min_to_str(total_ec_eff_min),
            'ec_nao_efetivo': _min_to_str(total_ec_neff_min),
            'fora_efetivo': _min_to_str(total_fora_eff_min),
            'fora_nao_efetivo': _min_to_str(total_fora_neff_min),
        }
        total_avanco_diario = round(sum(float(v or 0) for v in curva_avanco_diario), 1)
        dias_trabalhados = len({
            getattr(row.rdo, 'data', None)
            for row in ordered_tanks
            if getattr(getattr(row, 'rdo', None), 'data', None)
        })
        produtividade_media_diaria = {
            'media_percentual': round(total_avanco_diario / dias_trabalhados, 1)
            if dias_trabalhados else 0.0,
            'ultimo_percentual': round(float(curva_avanco_diario[-1] or 0), 1)
            if dias_trabalhados else 0.0,
            'dias_considerados': dias_trabalhados,
            'total_avanco_diario': total_avanco_diario,
            'hh_efetivo_total_min': int(produtividade_hh_efetivo_total_min or 0),
            'hh_total_min': int(produtividade_hh_total_min or 0),
            'hh_efetivo_total': _min_to_str(produtividade_hh_efetivo_total_min),
            'hh_total': _min_to_str(produtividade_hh_total_min),
        }

        # ── HH por atividade (agrupado) ──
        from collections import defaultdict
        atividade_min = defaultdict(int)
        CATEGORIAS = {
            'HH Mobilização': ['mobilização de material - dentro do tanque', 'mobilização de material - fora do tanque', 'desmobilização do material - dentro do tanque', 'desmobilização do material - fora do tanque'],
            'HH Offloading': ['conferência do material e equipamento no container'],
            'HH DDS, Afer. Pressão, Abert. PT, Housekeeping, Instr. de Seg.': ['dds', 'aferição de pressão arterial', 'abertura pt', 'Renovação de PT/PET', 'limpeza da área', 'instrução de segurança'],
            'Stand-by/Setup/Apoio na Unidade/Troca de Turma': ['em espera', 'instalação/preparação/montagem', 'apoio à equipe de bordo nas atividades da unidade', 'treinamento de abandono', 'alarme real', 'reunião', 'treinamento na unidade'],
            'HH Manutenção': ['manutenção de equipamentos - dentro do tanque', 'manutenção de equipamentos - fora do tanque'],
            'HH Limpeza Manual': ['limpeza mecânica', 'acesso ao tanque', 'avaliação inicial da área de trabalho', 'Desobstrução de linhas', 'Drenagem do tanque', 'coleta e análise de ar', 'coleta de água'],
        }
        cat_inverso = {}
        for cat, ativs in CATEGORIAS.items():
            for a in ativs:
                cat_inverso[a.lower()] = cat

        for rdo in rdo_qs:
            for at in rdo.atividades_rdo.all():
                if not (at.inicio and at.fim):
                    continue
                s = at.inicio.hour * 60 + at.inicio.minute
                e = at.fim.hour * 60 + at.fim.minute
                d = e - s
                if d < 0:
                    d += 24 * 60
                nome = (at.atividade or '').strip().lower()
                cat = cat_inverso.get(nome, 'Outros')
                atividade_min[cat] += d

        hh_atividade = {}
        for cat in CATEGORIAS:
            hh_atividade[cat] = atividade_min.get(cat, 0)
        if atividade_min.get('Outros', 0) > 0:
            hh_atividade['Outros'] = atividade_min['Outros']

        # ── Tempo de drenagem / horas não efetivas por atividade ──
        import re

        def _normalize_activity_name(value):
            raw = str(value or '').strip()
            if not raw:
                return ''
            try:
                normalized = unicodedata.normalize('NFKD', raw).encode('ASCII', 'ignore').decode('ASCII').strip().lower()
            except Exception:
                normalized = raw.lower().strip()
            normalized = re.sub(r'\s*/\s*', '/', normalized)
            normalized = re.sub(r'\s+', ' ', normalized).strip()
            return normalized

        def _activity_duration_minutes(activity_obj):
            if not (getattr(activity_obj, 'inicio', None) and getattr(activity_obj, 'fim', None)):
                return 0
            s = activity_obj.inicio.hour * 60 + activity_obj.inicio.minute
            e = activity_obj.fim.hour * 60 + activity_obj.fim.minute
            d = e - s
            if d < 0:
                d += 24 * 60
            return d

        non_effective_activity_defs = [
            {
                'label': 'OFFLOADING',
                'color': '#FF1A1A',
                'aliases': {
                    'conferencia do material e equipamento no container',
                    'conferencia do material e equipamento no conteiner',
                },
            },
            {
                'label': 'SETUP',
                'color': '#F57C28',
                'aliases': {
                    'instalacao/preparacao/montagem/setup',
                    'instalacao/preparacao/montagem',
                    'instalacao/preparacao/montagem / setup',
                    'instalacao / preparacao / montagem / setup',
                    'instalacao / preparacao / montagem',
                    'setup',
                },
            },
            {
                'label': 'AFERIÇÃO PRESSÃO',
                'color': '#9E9E9E',
                'aliases': {
                    'afericao de pressao arterial',
                },
            },
            {
                'label': 'DDS',
                'color': '#1E88E5',
                'aliases': {'dds'},
            },
            {
                'label': 'ABERTURA PT',
                'color': '#6D4C41',
                'aliases': {
                    'abertura pt',
                    'renovacao de pt/pet',
                },
            },
            {
                'label': 'HOUSEKEEPING',
                'color': '#43A047',
                'aliases': {
                    'limpeza da area',
                },
            },
            {
                'label': 'INSTRUÇÃO SEG.',
                'color': '#8E24AA',
                'aliases': {
                    'instrucao de seguranca',
                },
            },
            {
                'label': 'STAND-BY',
                'color': '#546E7A',
                'aliases': {'em espera'},
            },
            {
                'label': 'APOIO UNIDADE',
                'color': '#00897B',
                'aliases': {
                    'apoio a equipe de bordo nas atividades da unidade',
                },
            },
            {
                'label': 'TREIN. ABANDONO',
                'color': '#C0CA33',
                'aliases': {'treinamento de abandono'},
            },
            {
                'label': 'ALARME REAL',
                'color': '#E53935',
                'aliases': {'alarme real'},
            },
            {
                'label': 'REUNIÃO',
                'color': '#3949AB',
                'aliases': {'reuniao'},
            },
            {
                'label': 'TREIN. UNIDADE',
                'color': '#7CB342',
                'aliases': {'treinamento na unidade'},
            },
        ]

        non_effective_group_defs = [
            {
                'label': 'OFFLOADING',
                'color': '#FF1A1A',
                'members': {'OFFLOADING'},
            },
            {
                'label': 'SETUP',
                'color': '#F57C28',
                'members': {'SETUP'},
            },
            {
                'label': 'AFERIÇÃO PRESSÃO / DDS / INSTR. SEG.',
                'color': '#6C7A89',
                'members': {'AFERIÇÃO PRESSÃO', 'DDS', 'INSTRUÇÃO SEG.'},
            },
            {
                'label': 'TREIN. ABANDONO',
                'color': '#C0CA33',
                'members': {'TREIN. ABANDONO'},
            },
            {
                'label': 'ABERTURA PT',
                'color': '#6D4C41',
                'members': {'ABERTURA PT'},
            },
            {
                'label': 'APOIO À UNIDADE',
                'color': '#00897B',
                'members': {'APOIO UNIDADE', 'ALARME REAL', 'REUNIÃO', 'TREIN. UNIDADE'},
            },
            {
                'label': 'STAND-BY / HOUSEKEEPING',
                'color': '#4E8F5A',
                'members': {'STAND-BY', 'HOUSEKEEPING'},
            },
        ]

        non_effective_activity_map = {}
        non_effective_group_map = {}
        setup_activity_names = set()
        setup_activity_meta = None
        for item in non_effective_activity_defs:
            for alias in item.get('aliases') or set():
                normalized_alias = _normalize_activity_name(alias)
                non_effective_activity_map[normalized_alias] = {
                    'label': item['label'],
                    'color': item['color'],
                }
                if item.get('label') == 'SETUP':
                    setup_activity_names.add(normalized_alias)
                    setup_activity_meta = {
                        'label': item['label'],
                        'color': item['color'],
                    }
        for item in non_effective_group_defs:
            for member in item.get('members') or set():
                non_effective_group_map[member] = {
                    'label': item['label'],
                    'color': item['color'],
                }

        def _is_setup_activity_name(normalized_name):
            normalized_name = str(normalized_name or '').strip()
            if not normalized_name:
                return False
            if normalized_name in setup_activity_names:
                return True
            probe = re.sub(r'[^a-z0-9]+', ' ', normalized_name).strip()
            if 'setup' in probe:
                return True
            return (
                'instala' in probe
                and 'prepara' in probe
                and 'montagem' in probe
            )

        def _get_non_effective_activity_meta(raw_name):
            normalized_name = _normalize_activity_name(raw_name)
            meta = non_effective_activity_map.get(normalized_name)
            if meta:
                return meta
            if setup_activity_meta and _is_setup_activity_name(normalized_name):
                return setup_activity_meta
            return None

        horas_nao_efetivas_totais = defaultdict(int)

        for rdo in rdo_qs:
            for at in rdo.atividades_rdo.all():
                meta = _get_non_effective_activity_meta(getattr(at, 'atividade', ''))
                if not meta:
                    continue
                diff = _activity_duration_minutes(at)
                if diff <= 0:
                    continue
                group_meta = non_effective_group_map.get(meta['label'])
                if not group_meta:
                    continue
                horas_nao_efetivas_totais[group_meta['label']] += diff

        horas_nao_efetivas_items = []
        for item in non_effective_group_defs:
            label = item['label']
            total_minutes = int(horas_nao_efetivas_totais.get(label) or 0)
            if total_minutes <= 0:
                continue
            horas_nao_efetivas_items.append({
                'label': label,
                'color': item['color'],
                'total_minutos': total_minutes,
            })

        tempo_setup_labels = []
        tempo_setup_minutos = []
        tempo_setup_total_min = 0

        for rdo in rdo_qs:
            dt_str = rdo.data.strftime('%d/%m') if rdo.data else None
            if not dt_str:
                continue

            setup_dia_min = 0
            for at in rdo.atividades_rdo.all():
                if not _is_setup_activity_name(_normalize_activity_name(getattr(at, 'atividade', ''))):
                    continue
                setup_dia_min += _activity_duration_minutes(at)

            tempo_setup_labels.append(dt_str)
            tempo_setup_minutos.append(setup_dia_min)
            tempo_setup_total_min += setup_dia_min

        drenagem_activity_names = {
            'drenagem do tanque',
            'drenagem inicial do tanque',
        }

        tempo_drenagem_labels = []
        tempo_drenagem_minutos = []
        tempo_drenagem_total_min = 0

        for rdo in rdo_qs:
            dt_str = rdo.data.strftime('%d/%m') if rdo.data else None
            if not dt_str:
                continue

            drenagem_dia_min = 0
            for at in rdo.atividades_rdo.all():
                if not (at.inicio and at.fim):
                    continue
                if _normalize_activity_name(getattr(at, 'atividade', '')) not in drenagem_activity_names:
                    continue
                drenagem_dia_min += _activity_duration_minutes(at)

            tempo_drenagem_labels.append(dt_str)
            tempo_drenagem_minutos.append(drenagem_dia_min)
            tempo_drenagem_total_min += drenagem_dia_min

        # ── Compartimentos avanço (barras raspagem + limpeza fina) ──
        compartimentos_avanco = {}
        compartimentos_avanco_cumulado = {}
        tanque_3d = {
            'available': False,
            'requires_specific_tank': not bool(effective_tank_filter) and len(tanques_disponiveis) > 1,
            'tank_label': selected_tank_label,
            'metric_label': 'Raspagem acumulada',
            'total_compartimentos': 0,
            'total_percent': 0,
            'sentido': '',
            'sentido_inicio': '',
            'sentido_fim': '',
            'compartimentos': [],
        }
        if last_tank:
            import json as _json

            raw = getattr(last_tank, 'compartimentos_avanco_json', None)
            if raw:
                try:
                    compartimentos_avanco = _json.loads(raw)
                except Exception:
                    compartimentos_avanco = {}

            try:
                snapshot = last_tank.build_compartimento_progress_snapshot()
            except Exception:
                snapshot = None

            if snapshot and snapshot.get('rows'):
                total_compartimentos = int(snapshot.get('total_compartimentos') or 0)

                def _sentido_labels(raw_sentido):
                    low = str(raw_sentido or '').strip().lower()
                    if 'vante' in low and ('ré' in low or 're' in low):
                        if low.index('vante') < max(low.find('ré'), low.find('re')):
                            return ('Vante', 'Ré')
                        return ('Ré', 'Vante')
                    if 'bombordo' in low and 'boreste' in low:
                        if low.index('bombordo') < low.index('boreste'):
                            return ('Bombordo', 'Boreste')
                        return ('Boreste', 'Bombordo')
                    return ('', '')

                total_display = 0.0
                chart_rows = []
                for row in snapshot.get('rows', []):
                    idx = int(row.get('index') or 0)
                    if idx <= 0:
                        continue
                    mecanizada_meta = row.get('mecanizada') or {}
                    fina_meta = row.get('fina') or {}
                    mecanizada_final = _float(mecanizada_meta.get('final'))
                    fina_final = _float(fina_meta.get('final'))
                    compartimentos_avanco_cumulado[str(idx)] = {
                        'mecanizada': mecanizada_final,
                        'fina': fina_final,
                    }
                    total_display += mecanizada_final
                    chart_rows.append({
                        'index': idx,
                        'label': f'Compartimento {idx}',
                        'display_value': mecanizada_final,
                        'mecanizada': mecanizada_final,
                        'fina': fina_final,
                    })

                sentido = getattr(last_tank, 'sentido_limpeza', None) or getattr(last_tank_rdo, 'sentido_limpeza', None) or ''
                sentido_inicio, sentido_fim = _sentido_labels(sentido)
                tanque_3d.update({
                    'available': bool(effective_tank_filter) and bool(chart_rows),
                    'requires_specific_tank': not bool(effective_tank_filter) and len(tanques_disponiveis) > 1,
                    'tank_label': selected_tank_label,
                    'metric_label': 'Raspagem acumulada',
                    'total_compartimentos': total_compartimentos,
                    'total_percent': round(total_display / float(total_compartimentos), 2) if total_compartimentos else 0,
                    'sentido': sentido,
                    'sentido_inicio': sentido_inicio,
                    'sentido_fim': sentido_fim,
                    'compartimentos': chart_rows,
                })

        # Priorizar o último JSON acumulado útil persistido no RDO; quando faltar,
        # usar o JSON do RdoTanque como fallback para alimentar os gráficos.
        def _rd_sentido_labels(raw_sentido):
            low = str(raw_sentido or '').strip().lower()
            if 'vante' in low and ('rÃ©' in low or 're' in low):
                if low.index('vante') < max(low.find('rÃ©'), low.find('re')):
                    return ('Vante', 'RÃ©')
                return ('RÃ©', 'Vante')
            if 'bombordo' in low and 'boreste' in low:
                if low.index('bombordo') < low.index('boreste'):
                    return ('Bombordo', 'Boreste')
                return ('Boreste', 'Bombordo')
            return ('', '')

        def _rd_sentido_labels_safe(raw_sentido):
            low = str(raw_sentido or '').strip().lower()
            low = low.replace('Ã©', 'e').replace('é', 'e').replace('ê', 'e').replace('ã', 'a').replace('â', 'a')
            if 'vante' in low and 're' in low:
                re_label = 'R' + chr(233)
                if low.index('vante') < low.index('re'):
                    return ('Vante', re_label)
                return (re_label, 'Vante')
            if 'bombordo' in low and 'boreste' in low:
                if low.index('bombordo') < low.index('boreste'):
                    return ('Bombordo', 'Boreste')
                return ('Boreste', 'Bombordo')
            return ('', '')

        def _rd_parse_comp_payload(raw_payload, total_hint):
            import json as _json

            if raw_payload in (None, ''):
                return None
            total = 0
            try:
                total = int(total_hint or 0)
            except Exception:
                total = 0
            parsed = raw_payload
            try:
                if isinstance(raw_payload, str):
                    parsed = _json.loads(raw_payload) if raw_payload.strip() else {}
            except Exception:
                parsed = {}
            if not isinstance(parsed, dict):
                return None
            if total <= 0:
                try:
                    total = max(int(k) for k in parsed.keys()) if parsed else 0
                except Exception:
                    total = len(parsed)
            if total <= 0:
                return None
            normalized = RdoTanque.normalize_compartimentos_payload(parsed, total)
            has_any_value = any(
                (item.get('mecanizada', 0) or item.get('fina', 0))
                for item in normalized.values()
            )
            return {
                'total': total,
                'normalized': normalized,
                'has_any_value': has_any_value,
            }

        def _rd_build_chart_source_entry(owner, source_kind, total_hint, tank_obj=None):
            parsed = _rd_parse_comp_payload(
                getattr(owner, 'compartimentos_avanco_json', None),
                total_hint,
            )
            if not parsed:
                return None
            ref_tank = tank_obj or (owner if isinstance(owner, RdoTanque) else None)
            ref_rdo = getattr(owner, 'rdo', None) if isinstance(owner, RdoTanque) else owner
            return {
                'owner': owner,
                'source_kind': source_kind,
                'tank': ref_tank,
                'rdo': ref_rdo,
                'total': parsed['total'],
                'normalized': parsed['normalized'],
                'has_any_value': parsed['has_any_value'],
            }

        def _rd_pick_latest_chart_source():
            fallback = None
            ordered_tanks = list(
                tank_qs.select_related('rdo').order_by('-rdo__data', '-rdo__pk', '-pk')
            )
            for tank_obj in ordered_tanks:
                total_hint = (
                    getattr(tank_obj, 'numero_compartimentos', None)
                    or getattr(getattr(tank_obj, 'rdo', None), 'numero_compartimentos', None)
                    or getattr(ultimo_rdo, 'numero_compartimentos', None)
                )
                for owner, source_kind in (
                    (getattr(tank_obj, 'rdo', None), 'rdo'),
                    (tank_obj, 'rdotanque'),
                ):
                    if owner is None:
                        continue
                    entry = _rd_build_chart_source_entry(owner, source_kind, total_hint, tank_obj=tank_obj)
                    if not entry:
                        continue
                    if fallback is None:
                        fallback = entry
                    if entry['has_any_value']:
                        return entry

            for rdo in rdo_qs.order_by('-data', '-pk'):
                entry = _rd_build_chart_source_entry(
                    rdo,
                    'rdo',
                    getattr(rdo, 'numero_compartimentos', None) or getattr(last_tank, 'numero_compartimentos', None),
                    tank_obj=last_tank,
                )
                if not entry:
                    continue
                if fallback is None:
                    fallback = entry
                if entry['has_any_value']:
                    return entry
            return fallback

        chart_source = _rd_pick_latest_chart_source()
        if chart_source:
            total_compartimentos = int(chart_source.get('total') or 0)
            ref_tank = chart_source.get('tank') or last_tank
            ref_rdo = chart_source.get('rdo') or ultimo_rdo
            source_owner = chart_source.get('owner')

            snapshot = None
            try:
                if (
                    chart_source.get('source_kind') == 'rdo'
                    and source_owner is not None
                    and hasattr(source_owner, '_build_compartimento_progress_snapshot')
                ):
                    if ref_tank is not None:
                        try:
                            if not getattr(source_owner, 'tanque_codigo', None) and getattr(ref_tank, 'tanque_codigo', None):
                                source_owner.tanque_codigo = ref_tank.tanque_codigo
                        except Exception:
                            pass
                        try:
                            if not getattr(source_owner, 'nome_tanque', None) and getattr(ref_tank, 'nome_tanque', None):
                                source_owner.nome_tanque = ref_tank.nome_tanque
                        except Exception:
                            pass
                    snapshot = source_owner._build_compartimento_progress_snapshot(
                        total_compartimentos=total_compartimentos or None,
                    )
                elif isinstance(source_owner, RdoTanque) and hasattr(source_owner, 'build_compartimento_progress_snapshot'):
                    snapshot = source_owner.build_compartimento_progress_snapshot(
                        total_compartimentos=total_compartimentos or None,
                    )
                elif source_owner is not None and hasattr(source_owner, '_build_compartimento_progress_snapshot'):
                    snapshot = source_owner._build_compartimento_progress_snapshot(
                        total_compartimentos=total_compartimentos or None,
                    )
            except Exception:
                snapshot = None

            if snapshot:
                try:
                    total_compartimentos = int(snapshot.get('total_compartimentos') or total_compartimentos or 0)
                except Exception:
                    total_compartimentos = int(total_compartimentos or 0)

            compartimentos_avanco = {}
            compartimentos_avanco_cumulado = {}
            chart_rows = []
            total_mecanizada = _float((snapshot or {}).get('cumulative', {}).get('mecanizada'))
            total_fina = _float((snapshot or {}).get('cumulative', {}).get('fina'))
            total_avanco = 0.0
            for idx in range(1, total_compartimentos + 1):
                key = str(idx)
                row_meta = {}
                if snapshot and snapshot.get('rows'):
                    try:
                        row_meta = snapshot['rows'][idx - 1] or {}
                    except Exception:
                        row_meta = {}
                mecanizada_meta = row_meta.get('mecanizada') or {}
                fina_meta = row_meta.get('fina') or {}
                mecanizada_val = _float(mecanizada_meta.get('final'))
                fina_val = _float(fina_meta.get('final'))
                avanco_val = _float(min(100.0, mecanizada_val + fina_val))
                sujidade_val = _float(max(0.0, 100.0 - avanco_val))
                compartimentos_avanco[key] = {
                    'mecanizada': mecanizada_val,
                    'fina': fina_val,
                    'avanco': avanco_val,
                    'sujidade': sujidade_val,
                }
                compartimentos_avanco_cumulado[key] = {
                    'mecanizada': mecanizada_val,
                    'fina': fina_val,
                    'avanco': avanco_val,
                    'sujidade': sujidade_val,
                }
                total_avanco += avanco_val
                chart_rows.append({
                    'index': idx,
                    'label': f'Compartimento {idx}',
                    'mecanizada': mecanizada_val,
                    'fina': fina_val,
                    'avanco': avanco_val,
                    'sujidade': sujidade_val,
                })

            sentido = getattr(last_tank, 'sentido_limpeza', None) or getattr(last_tank_rdo, 'sentido_limpeza', None) or ''
            sentido_inicio, sentido_fim = _rd_sentido_labels_safe(sentido)
            total_mecanizada_pct = total_mecanizada
            total_fina_pct = total_fina
            total_avanco_pct = round(total_avanco / float(total_compartimentos), 2) if total_compartimentos else 0
            tanque_3d = {
                'available': total_compartimentos > 0 and not (not bool(effective_tank_filter) and len(tanques_disponiveis) > 1),
                'requires_specific_tank': not bool(effective_tank_filter) and len(tanques_disponiveis) > 1,
                'tank_label': selected_tank_label,
                'total_compartimentos': total_compartimentos,
                'total_percent': total_avanco_pct,
                'sentido': sentido,
                'sentido_inicio': sentido_inicio,
                'sentido_fim': sentido_fim,
                'source_kind': chart_source.get('source_kind') or '',
                'source_date': ref_rdo.data.strftime('%d/%m/%Y') if getattr(ref_rdo, 'data', None) else '',
                'chart': {
                    'key': 'avanco',
                    'title': '% Avanço por compartimento',
                    'total_percent': total_avanco_pct,
                    'color': '#8BC34A',
                    'items': [
                        {
                            'index': row['index'],
                            'label': row['label'],
                            'value': row['avanco'],
                            'avanco': row['avanco'],
                            'sujidade': row['sujidade'],
                            'mecanizada': row['mecanizada'],
                            'fina': row['fina'],
                        }
                        for row in chart_rows
                    ],
                },
                'charts': [
                    {
                        'key': 'avanco',
                        'title': '% Avanço por compartimento',
                        'total_percent': total_avanco_pct,
                        'color': '#8BC34A',
                        'items': [
                            {
                                'index': row['index'],
                                'label': row['label'],
                                'value': row['avanco'],
                                'avanco': row['avanco'],
                                'sujidade': row['sujidade'],
                                'mecanizada': row['mecanizada'],
                                'fina': row['fina'],
                            }
                            for row in chart_rows
                        ],
                    }
                ],
            }

        return JsonResponse({
            'success': True,
            'empty': False,
            'info_os': info_os,
            'producao': producao,
            'curva_s': {
                'labels': curva_labels,
                'avanco_diario': curva_avanco_diario,
                'avanco_acumulado': curva_avanco_acum,
                'raspagem_acumulada': curva_raspagem_acum,
                'ensacamento_acumulado': curva_ensacamento_acum,
                'icamento_acumulado': curva_icamento_acum,
                'cambagem_acumulada': curva_cambagem_acum,
                'limpeza_fina_acumulada': curva_limpeza_fina_acum,
                'totais': {
                    'raspagem': _series_terminal(curva_raspagem_acum),
                    'ensacamento': _series_terminal(curva_ensacamento_acum),
                    'icamento': _series_terminal(curva_icamento_acum),
                    'cambagem': _series_terminal(curva_cambagem_acum),
                    'limpeza_fina': _series_terminal(curva_limpeza_fina_acum),
                },
            },
            'comparativo_avanco': {
                'labels': comparativo_avanco_labels,
                'realizado_diario': realizado_diario,
                'programado_diario': programado_diario,
                'realizado_acumulado': realizado_acumulado,
                'programado_acumulado': programado_acumulado,
            },
            'kpi': kpi,
            'status': status,
            'anotacoes_observacoes': anotacoes_observacoes,
            'hh_breakdown': hh_breakdown,
            'hh_totais': hh_totais,
            'produtividade_media_diaria': produtividade_media_diaria,
            'hh_atividade': hh_atividade,
            'horas_nao_efetivas': {
                'labels': [item['label'] for item in horas_nao_efetivas_items],
                'items': horas_nao_efetivas_items,
                'valores': [int(item['total_minutos'] or 0) for item in horas_nao_efetivas_items],
                'colors': [item['color'] for item in horas_nao_efetivas_items],
                'total_minutos': int(sum(horas_nao_efetivas_totais.values()) or 0),
            },
            'tempo_setup': {
                'labels': tempo_setup_labels,
                'minutos': tempo_setup_minutos,
                'total_minutos': tempo_setup_total_min,
            },
            'tempo_drenagem': {
                'labels': tempo_drenagem_labels,
                'minutos': tempo_drenagem_minutos,
                'total_minutos': tempo_drenagem_total_min,
            },
            'compartimentos_avanco': compartimentos_avanco,
            'compartimentos_avanco_cumulado': compartimentos_avanco_cumulado,
            'tanque_3d': tanque_3d,
            'tanques_disponiveis': tanques_disponiveis,
        })

    except Exception as e:
        logging.exception('Erro em report_diario_data')
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
