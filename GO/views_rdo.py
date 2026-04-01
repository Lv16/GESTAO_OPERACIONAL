from django.views.decorators.http import require_POST, require_GET
from django.http import JsonResponse, HttpResponse
from django.conf import settings
import os
import glob
import traceback
import re
from io import BytesIO
from datetime import datetime, time as dt_time
from decimal import Decimal, ROUND_HALF_UP
import json
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
import unicodedata
from .models import (
    OrdemServico,
    RDO,
    RDOAtividade,
    Pessoa,
    Funcao,
    RDOMembroEquipe,
    RdoTanque,
    _canonical_tank_alias_for_os,
    _rdo_has_setup_activity,
    _OFFLOADING_ACTIVITY_VALUES,
)
from .mobile_release import request_is_mobile, resolve_mobile_release_context
from .rdo_access import (
    build_read_only_json_response as _build_read_only_json_response,
    user_can_delete_rdo as _user_can_delete_rdo,
    user_has_read_only_access as _user_has_read_only_access,
)
import logging
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import transaction, connections, close_old_connections
from django.db.models import Max, Q, Sum
from django.db.utils import OperationalError as DjangoOperationalError
import json as _json
from urllib.parse import urlparse
from django.template.loader import render_to_string
from types import SimpleNamespace


def _guard_read_only_json(request, action):
    if _user_has_read_only_access(getattr(request, 'user', None)):
        return _build_read_only_json_response(action)
    return None


def _get_rdo_inline_css():
    try:
        css = render_to_string('css/page_rdo.inline.css')
        css = css.strip()
        if not css:
            return ''
        return f'<style type="text/css">{css}</style>'
    except Exception:
        return ''


def _normalize_rdo_status_text(value):
    try:
        return str(value or '').strip().lower()
    except Exception:
        return ''


def _rdo_status_is_allowed_for_pending(value):
    low = _normalize_rdo_status_text(value)
    if not low:
        return False
    return ('programad' in low) or ('andamento' in low)


def _rdo_status_is_blocked_for_pending(value):
    low = _normalize_rdo_status_text(value)
    if not low:
        return False
    blocked_keywords = (
        'paraliz',
        'finaliz',
        'encerrad',
        'fechad',
        'conclu',
        'retorn',
        'cancelad',
    )
    return any(keyword in low for keyword in blocked_keywords)


def _os_matches_rdo_pending_rule(os_obj):
    try:
        if os_obj is None:
            return False
        status_operacao = _normalize_rdo_status_text(getattr(os_obj, 'status_operacao', ''))
        if _rdo_status_is_blocked_for_pending(status_operacao):
            return False
        return _rdo_status_is_allowed_for_pending(status_operacao)
    except Exception:
        return False


def _os_pending_dedupe_key(os_obj=None, fallback=None):
    try:
        numero_os = getattr(os_obj, 'numero_os', None) if os_obj is not None else None
    except Exception:
        numero_os = None
    if numero_os not in (None, ''):
        return f'numero:{numero_os}'
    try:
        os_id = getattr(os_obj, 'id', None) if os_obj is not None else None
    except Exception:
        os_id = None
    if os_id not in (None, ''):
        return f'id:{os_id}'
    if fallback not in (None, ''):
        return f'fallback:{fallback}'
    return None


def _resolve_latest_os_for_numero(numero_os, supervisor=None):
    try:
        if numero_os in (None, ''):
            return None
        qs = OrdemServico.objects.filter(numero_os=numero_os)
        if supervisor is not None:
            qs = qs.filter(supervisor=supervisor)
        return qs.order_by('-id').first()
    except Exception:
        return None


def _build_supervisor_card_row(os_obj):
    try:
        if os_obj is None:
            return None
        numero_os = getattr(os_obj, 'numero_os', None)
        latest_rdo = None
        try:
            if numero_os not in (None, ''):
                latest_rdo = (
                    RDO.objects
                    .select_related('ordem_servico')
                    .filter(ordem_servico__numero_os=numero_os)
                    .order_by('-id')
                    .first()
                )
        except Exception:
            latest_rdo = None

        row = SimpleNamespace()
        row.id = getattr(latest_rdo, 'id', '') if latest_rdo is not None else ''
        row.rdo_id = getattr(latest_rdo, 'id', '') if latest_rdo is not None else ''
        row.rdo = getattr(latest_rdo, 'rdo', '') if latest_rdo is not None else ''
        row.data = (
            getattr(latest_rdo, 'data', None)
            if latest_rdo is not None else None
        ) or getattr(os_obj, 'data_inicio', None)
        row.data_inicio = (
            (getattr(latest_rdo, 'data_inicio', None) or getattr(latest_rdo, 'data', None))
            if latest_rdo is not None else None
        ) or getattr(os_obj, 'data_inicio', None)
        row.previsao_termino = getattr(latest_rdo, 'previsao_termino', None) if latest_rdo is not None else None
        row.ordem_servico = os_obj
        row.contrato_po = (
            getattr(latest_rdo, 'contrato_po', None)
            if latest_rdo is not None else None
        ) or getattr(os_obj, 'po', None)
        row.turno = (
            getattr(latest_rdo, 'turno', None)
            if latest_rdo is not None else None
        ) or getattr(os_obj, 'turno', None)
        return row
    except Exception:
        return None

def _canonicalize_sentido(raw):
    try:
        if raw is None:
            return None
        if isinstance(raw, bool):
            return 'vante > ré' if raw else 'ré > vante'
        try:
            if isinstance(raw, (int, float)):
                if int(raw) == 1:
                    return 'vante > ré'
                if int(raw) == 0:
                    return 'ré > vante'
        except Exception:
            pass
        s = str(raw).strip()
        if not s:
            return None
        low = s.lower()
        variants = {
            'vante > ré': ['vante > ré', 'vante > re', 'vante > ré'],
            'ré > vante': ['ré > vante', 're > vante', 're > vante'],
            'bombordo > boreste': ['bombordo > boreste', 'bombordo > boreste'],
            'boreste < bombordo': ['boreste < bombordo', 'boreste < bombordo'],
        }
        for canon, opts in variants.items():
            for opt in opts:
                if low == opt:
                    return canon
        if 'bombordo' in low and 'boreste' in low:
            if low.index('boreste') < low.index('bombordo'):
                return 'boreste < bombordo'
            return 'bombordo > boreste'
        if 'vante' in low and ('ré' in low or 're' in low):
            return 'vante > ré'
        if ('ré' in low or 're' in low) and 'vante' in low:
            return 'ré > vante'
        if '>' in low or '<' in low or '->' in low:
            if 'vante' in low:
                return 'vante > ré'
            if 'ré' in low or 're' in low:
                return 'ré > vante'
        return None
    except Exception:
        return None

def _coerce_decimal_value(raw):
    try:
        if raw is None:
            return None
        if isinstance(raw, bool):
            return None
        if isinstance(raw, Decimal):
            dec = raw
        elif isinstance(raw, (int, float)):
            try:
                if isinstance(raw, float) and (raw != raw or raw in (float('inf'), float('-inf'))):
                    return None
            except Exception:
                return None
            dec = Decimal(str(raw))
        else:
            s = str(raw).strip()
            if not s:
                return None
            if s.endswith('%'):
                s = s[:-1].strip()
            s = s.replace(',', '.')
            low = s.lower()
            if low in ('nan', '+nan', '-nan', 'inf', '+inf', '-inf', 'infinity', '+infinity', '-infinity'):
                return None
            dec = Decimal(str(s))
        try:
            if hasattr(dec, 'is_finite') and not dec.is_finite():
                return None
        except Exception:
            return None
        return dec
    except Exception:
        return None

def _coerce_decimal_for_model(model_cls, field_name, raw):
    dec = _coerce_decimal_value(raw)
    if dec is None:
        return None
    try:
        from django.db import models as dj_models
        fld = model_cls._meta.get_field(field_name)
        if not isinstance(fld, dj_models.DecimalField):
            return dec

        places = int(getattr(fld, 'decimal_places', 0) or 0)
        quant = Decimal('1').scaleb(-places)
        try:
            dec = dec.quantize(quant, rounding=ROUND_HALF_UP)
        except Exception:
            return None

        try:
            connections['default'].ops.adapt_decimalfield_value(dec, fld.max_digits, fld.decimal_places)
        except Exception:
            return None
        return dec
    except Exception:
        return dec

def _sanitize_model_decimal_payload(model_cls, payload, logger=None, context=''):
    try:
        if not isinstance(payload, dict) or not payload:
            return payload
        from django.db import models as dj_models
        for k in list(payload.keys()):
            try:
                v = payload.get(k)
                if v is None:
                    continue
                fld = model_cls._meta.get_field(k)
            except Exception:
                continue
            if not isinstance(fld, dj_models.DecimalField):
                continue
            parsed = _coerce_decimal_for_model(model_cls, k, v)
            if parsed is None:
                try:
                    payload.pop(k, None)
                except Exception:
                    pass
                if logger is not None:
                    try:
                        logger.warning('Ignorando decimal inválido em %s.%s=%r (%s)', model_cls.__name__, k, v, context)
                    except Exception:
                        pass
                continue
            payload[k] = parsed
        return payload
    except Exception:
        return payload

_TANK_PREDICTION_FIELDS = (
    'ensacamento_prev',
    'icamento_prev',
    'cambagem_prev',
    'previsao_termino',
)

_TANK_SHARED_PREDICTION_FIELDS = (
    'ensacamento_prev',
    'icamento_prev',
    'cambagem_prev',
)

_TANK_LOCKED_PREDICTION_FIELDS = (
    'previsao_termino',
)

_TANK_SHARED_STRUCTURE_FIELDS = (
    'numero_compartimentos',
)


def _has_defined_prediction_value(value):
    try:
        if value is None:
            return False
        if isinstance(value, str):
            return value.strip() != ''
        return True
    except Exception:
        return False


def _parse_iso_date_value(raw_value):
    try:
        if raw_value in (None, ''):
            return None
        if hasattr(raw_value, 'year') and hasattr(raw_value, 'month') and hasattr(raw_value, 'day'):
            return raw_value
        text = str(raw_value).strip()
        if not text:
            return None
        return datetime.strptime(text[:10], '%Y-%m-%d').date()
    except Exception:
        return None


def _get_tank_prediction_group_queryset(tank_obj):
    try:
        if tank_obj is None:
            return RdoTanque.objects.none()
        rdo_obj = getattr(tank_obj, 'rdo', None)
        os_obj = getattr(rdo_obj, 'ordem_servico', None)
        os_ids = _resolve_os_scope_ids(os_obj)
        if not os_ids:
            if getattr(tank_obj, 'pk', None):
                return RdoTanque.objects.filter(pk=tank_obj.pk)
            return RdoTanque.objects.none()
        try:
            os_num_ref = getattr(os_obj, 'numero_os', None)
        except Exception:
            os_num_ref = None
        try:
            target_key = _tank_identity_key(
                getattr(tank_obj, 'tanque_codigo', None),
                getattr(tank_obj, 'nome_tanque', None),
                os_num=os_num_ref,
            )
        except Exception:
            target_key = None
        qs = RdoTanque.objects.select_related('rdo__ordem_servico').filter(rdo__ordem_servico_id__in=os_ids)
        if not target_key:
            if getattr(tank_obj, 'pk', None):
                return qs.filter(pk=tank_obj.pk)
            return RdoTanque.objects.none()
        matched_ids = []
        try:
            for obj_id, code, name in qs.values_list('id', 'tanque_codigo', 'nome_tanque'):
                try:
                    obj_key = _tank_identity_key(code, name, os_num=os_num_ref)
                except Exception:
                    obj_key = None
                if obj_key == target_key:
                    matched_ids.append(obj_id)
        except Exception:
            matched_ids = []
        if matched_ids:
            return RdoTanque.objects.filter(pk__in=matched_ids)
        if getattr(tank_obj, 'pk', None):
            return RdoTanque.objects.filter(pk=tank_obj.pk)
        return RdoTanque.objects.none()
    except Exception:
        return RdoTanque.objects.none()


def _get_tank_prediction_group_value(tank_obj, field_name):
    try:
        if tank_obj is None or field_name not in _TANK_PREDICTION_FIELDS or not hasattr(tank_obj, field_name):
            return None
        current = getattr(tank_obj, field_name, None)
        if _has_defined_prediction_value(current):
            return current
        qs = _get_tank_prediction_group_queryset(tank_obj)
        if qs is None:
            return None
        for value in qs.exclude(pk=getattr(tank_obj, 'pk', None)).values_list(field_name, flat=True):
            if _has_defined_prediction_value(value):
                return value
        return None
    except Exception:
        return None


def _sync_tank_prediction_group_metrics(tank_obj, field_name):
    try:
        if tank_obj is None:
            return
        if field_name not in _TANK_SHARED_PREDICTION_FIELDS:
            return
        qs = _get_tank_prediction_group_queryset(tank_obj)
        if qs is None:
            return
        for sibling in qs.select_related('rdo'):
            try:
                if hasattr(sibling, 'recompute_metrics') and callable(sibling.recompute_metrics):
                    sibling.recompute_metrics(only_when_missing=False)
                sibling.save()
            except Exception:
                continue
    except Exception:
        return


def _set_tank_shared_field_value(tank_obj, field_name, incoming_value):
    try:
        if tank_obj is None:
            return False
        if field_name not in _TANK_SHARED_STRUCTURE_FIELDS:
            return False
        if not hasattr(tank_obj, field_name):
            return False
        if incoming_value in (None, ''):
            return False
        try:
            qs = _get_tank_prediction_group_queryset(tank_obj)
        except Exception:
            qs = None
        updated = False
        try:
            if qs is not None and qs.exists():
                qs.update(**{field_name: incoming_value})
                updated = True
        except Exception:
            updated = False
        try:
            setattr(tank_obj, field_name, incoming_value)
            updated = True
        except Exception:
            pass
        return updated
    except Exception:
        return False


def _set_tank_prediction_value(tank_obj, field_name, incoming_value, allow_overwrite=False):
    try:
        if tank_obj is None:
            return False
        if field_name not in _TANK_PREDICTION_FIELDS:
            return False
        if not hasattr(tank_obj, field_name):
            return False
        def _normalize_prediction_value(value):
            try:
                if field_name == 'previsao_termino':
                    return _parse_iso_date_value(value)
                if value in (None, ''):
                    return None
                if field_name in _TANK_SHARED_PREDICTION_FIELDS:
                    text = str(value).strip().replace(',', '.')
                    if not text:
                        return None
                    try:
                        return int(text)
                    except Exception:
                        return int(float(text))
                return str(value).strip()
            except Exception:
                return value

        if field_name == 'previsao_termino':
            incoming_value = _parse_iso_date_value(incoming_value)
        if incoming_value is None:
            return False
        existing_value = _get_tank_prediction_group_value(tank_obj, field_name)
        normalized_existing = _normalize_prediction_value(existing_value)
        normalized_incoming = _normalize_prediction_value(incoming_value)
        if _has_defined_prediction_value(existing_value) and not allow_overwrite:
            try:
                current = getattr(tank_obj, field_name, None)
            except Exception:
                current = None
            if not _has_defined_prediction_value(current) and getattr(tank_obj, 'pk', None):
                try:
                    RdoTanque.objects.filter(pk=tank_obj.pk).update(**{field_name: existing_value})
                except Exception:
                    pass
                try:
                    setattr(tank_obj, field_name, existing_value)
                except Exception:
                    pass
            return False
        if _has_defined_prediction_value(existing_value):
            try:
                current = getattr(tank_obj, field_name, None)
            except Exception:
                current = None
            if not _has_defined_prediction_value(current) and getattr(tank_obj, 'pk', None):
                try:
                    RdoTanque.objects.filter(pk=tank_obj.pk).update(**{field_name: existing_value})
                except Exception:
                    pass
                try:
                    setattr(tank_obj, field_name, existing_value)
                except Exception:
                    pass
            # Shared predictions are defined only once for the tank group.
            # Replaying the same mobile payload must be a no-op; changing it later
            # is also blocked by business rule.
            if normalized_existing == normalized_incoming or allow_overwrite:
                return False
        try:
            qs = _get_tank_prediction_group_queryset(tank_obj)
        except Exception:
            qs = None
        updated = False
        try:
            if qs is not None and qs.exists():
                qs.update(**{field_name: incoming_value})
                updated = True
        except Exception:
            updated = False
        try:
            setattr(tank_obj, field_name, incoming_value)
            updated = True
        except Exception:
            pass
        try:
            if updated:
                _sync_tank_prediction_group_metrics(tank_obj, field_name)
        except Exception:
            pass
        return updated
    except Exception:
        return False


def _is_tank_prediction_locked(tank_obj, field_name):
    try:
        if tank_obj is None:
            return False
        if field_name not in _TANK_LOCKED_PREDICTION_FIELDS:
            return False
        if not hasattr(tank_obj, field_name):
            return False
        current = _get_tank_prediction_group_value(tank_obj, field_name)
        return _has_defined_prediction_value(current)
    except Exception:
        return False


def _apply_tank_prediction_once(tank_obj, field_name, incoming_value):
    try:
        return _set_tank_prediction_value(
            tank_obj,
            field_name,
            incoming_value,
            allow_overwrite=(field_name in _TANK_SHARED_PREDICTION_FIELDS),
        )
    except Exception:
        return False


def _extract_compartimentos_payload_from_request(get_value, get_list=None, total_compartimentos=None):
    try:
        raw_json = get_value('compartimentos_avanco_json') if callable(get_value) else None
    except Exception:
        raw_json = None
    if raw_json not in (None, ''):
        return raw_json

    try:
        total = int(total_compartimentos or 0)
    except Exception:
        total = 0
    if total <= 0:
        return None

    selected = set()
    try:
        if callable(get_list):
            selected = {
                int(v) for v in (get_list('compartimentos_avanco') or [])
                if str(v or '').strip()
            }
    except Exception:
        selected = set()

    payload = {}
    has_any_value = False
    for i in range(1, total + 1):
        try:
            m_raw = get_value(f'compartimento_avanco_mecanizada_{i}') if callable(get_value) else None
        except Exception:
            m_raw = None
        try:
            f_raw = get_value(f'compartimento_avanco_fina_{i}') if callable(get_value) else None
        except Exception:
            f_raw = None

        if m_raw not in (None, '') or f_raw not in (None, '') or i in selected:
            has_any_value = True

        # Selecionar o compartimento apenas habilita seus controles na UI;
        # não pode implicar avanço automático.
        m_val = RdoTanque._coerce_compartimento_percent(m_raw)
        f_val = RdoTanque._coerce_compartimento_percent(f_raw)
        payload[str(i)] = {'mecanizada': m_val, 'fina': f_val}

    if not has_any_value:
        return None
    return payload


def _validate_compartimentos_payload_for_tank(tank_obj, get_value, get_list=None, total_compartimentos=None):
    if tank_obj is None:
        return None
    raw_payload = _extract_compartimentos_payload_from_request(
        get_value,
        get_list=get_list,
        total_compartimentos=total_compartimentos,
    )
    if raw_payload is None:
        return None
    return tank_obj.validate_compartimentos_payload(
        raw_payload,
        total_compartimentos=total_compartimentos,
    )


_TANK_PROGRESS_WEIGHTED_FIELDS = (
    ('percentual_setup', 5, ()),
    ('percentual_limpeza_diario', 70, ('percentual_limpeza_diario', 'limpeza_mecanizada_diaria')),
    ('percentual_ensacamento', 7, ('percentual_ensacamento',)),
    ('percentual_icamento', 7, ('percentual_icamento',)),
    ('percentual_cambagem', 5, ('percentual_cambagem',)),
    ('percentual_limpeza_fina', 6, ('percentual_limpeza_fina_diario', 'percentual_limpeza_fina', 'limpeza_fina_diaria')),
)

_TANK_PROGRESS_WEIGHTED_FIELDS_CUMULATIVE = (
    ('percentual_setup_cumulativo', 5, ()),
    ('percentual_limpeza_cumulativo', 70, ('percentual_limpeza_cumulativo', 'limpeza_mecanizada_cumulativa')),
    ('percentual_ensacamento', 7, ('percentual_ensacamento',)),
    ('percentual_icamento', 7, ('percentual_icamento',)),
    ('percentual_cambagem', 5, ('percentual_cambagem',)),
    ('percentual_limpeza_fina_cumulativo', 6, ('percentual_limpeza_fina_cumulativo', 'limpeza_fina_cumulativa')),
)


def _compute_tank_setup_progress(tank_obj, cumulative=False):
    try:
        if tank_obj is None or getattr(tank_obj, 'rdo', None) is None:
            return None
        if _rdo_has_setup_activity(tank_obj.rdo):
            return Decimal('100')
        if not cumulative:
            return Decimal('0')
        for prior in tank_obj.get_prior_tank_snapshots():
            if _rdo_has_setup_activity(getattr(prior, 'rdo', None)):
                return Decimal('100')
        return Decimal('0')
    except Exception:
        return None


def _compute_weighted_tank_progress(tank_obj, cumulative=False):
    try:
        if tank_obj is None:
            return None
        spec = _TANK_PROGRESS_WEIGHTED_FIELDS_CUMULATIVE if cumulative else _TANK_PROGRESS_WEIGHTED_FIELDS
        total_weight = Decimal('0')
        weighted_sum = Decimal('0')
        has_any = False
        for metric_name, weight, field_names in spec:
            component_has_value = False
            if metric_name in ('percentual_setup', 'percentual_setup_cumulativo'):
                value = _compute_tank_setup_progress(
                    tank_obj,
                    cumulative=(metric_name == 'percentual_setup_cumulativo'),
                )
                component_has_value = value is not None and value > 0
            else:
                value = None
                for field_name in field_names:
                    try:
                        raw = getattr(tank_obj, field_name, None)
                    except Exception:
                        raw = None
                    value = _coerce_decimal_value(raw)
                    if value is not None:
                        component_has_value = True
                        break
            if component_has_value:
                has_any = True
            if value is None:
                value = Decimal('0')
            weight_dec = Decimal(str(weight))
            weighted_sum += (value * weight_dec)
            total_weight += weight_dec
        if not has_any or total_weight <= 0:
            return None
        result = weighted_sum / total_weight
        if result < 0:
            result = Decimal('0')
        if result > 100:
            result = Decimal('100')
        return result.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except Exception:
        return None


def _tank_metric_signature(tank_obj):
    try:
        if tank_obj is None:
            return None
        fields = (
            'percentual_limpeza_diario',
            'percentual_limpeza_cumulativo',
            'percentual_limpeza_fina_diario',
            'percentual_limpeza_fina',
            'percentual_limpeza_fina_cumulativo',
            'limpeza_mecanizada_diaria',
            'limpeza_mecanizada_cumulativa',
            'limpeza_fina_diaria',
            'limpeza_fina_cumulativa',
            'percentual_ensacamento',
            'percentual_icamento',
            'percentual_cambagem',
            'percentual_avanco',
            'percentual_avanco_cumulativo',
            'compartimentos_avanco_json',
        )
        return tuple(getattr(tank_obj, field, None) for field in fields)
    except Exception:
        return None


def _refresh_tank_metrics_for_display(tank_obj):
    try:
        if tank_obj is None:
            return None
        before = _tank_metric_signature(tank_obj)
        try:
            tank_obj.recompute_metrics(only_when_missing=False)
        except Exception:
            logging.getLogger(__name__).debug('Falha ao recomputar tanque %s para exibição', getattr(tank_obj, 'id', None), exc_info=True)
        authoritative_day = _compute_weighted_tank_progress(tank_obj, cumulative=False)
        authoritative_cum = _compute_weighted_tank_progress(tank_obj, cumulative=True)
        try:
            if authoritative_day is not None:
                tank_obj.percentual_avanco = authoritative_day
        except Exception:
            pass
        try:
            if authoritative_cum is not None:
                tank_obj.percentual_avanco_cumulativo = authoritative_cum
        except Exception:
            pass
        after = _tank_metric_signature(tank_obj)
        if after != before:
            try:
                _safe_save_global(tank_obj)
            except Exception:
                try:
                    tank_obj.save()
                except Exception:
                    logging.getLogger(__name__).debug('Falha ao salvar tanque %s após refresh', getattr(tank_obj, 'id', None), exc_info=True)
        return tank_obj
    except Exception:
        return tank_obj


def _sync_tank_payload_from_instance(target, tank_obj):
    try:
        if not isinstance(target, dict) or tank_obj is None:
            return target
        fields = (
            'id',
            'tanque_codigo',
            'nome_tanque',
            'tipo_tanque',
            'numero_compartimentos',
            'gavetas',
            'patamares',
            'volume_tanque_exec',
            'servico_exec',
            'metodo_exec',
            'espaco_confinado',
            'operadores_simultaneos',
            'h2s_ppm',
            'lel',
            'co_ppm',
            'o2_percent',
            'tempo_bomba',
            'ensacamento_dia',
            'ensacamento_cumulativo',
            'icamento_dia',
            'icamento_cumulativo',
            'cambagem_dia',
            'cambagem_cumulativo',
            'previsao_termino',
            'tambores_dia',
            'tambores_cumulativo',
            'residuos_solidos',
            'residuos_totais',
            'total_liquido',
            'total_liquido_cumulativo',
            'residuos_solidos_cumulativo',
            'avanco_limpeza',
            'avanco_limpeza_fina',
            'compartimentos_avanco_json',
            'percentual_limpeza_diario',
            'percentual_limpeza_cumulativo',
            'percentual_limpeza_fina_diario',
            'percentual_limpeza_fina',
            'percentual_limpeza_fina_cumulativo',
            'percentual_ensacamento',
            'percentual_icamento',
            'percentual_cambagem',
            'percentual_avanco',
            'percentual_avanco_cumulativo',
        )
        for field in fields:
            try:
                target[field] = getattr(tank_obj, field, None)
            except Exception:
                continue
        try:
            target['tanque_nome'] = getattr(tank_obj, 'nome_tanque', None)
        except Exception:
            pass
        try:
            target['numero_compartimento'] = getattr(tank_obj, 'numero_compartimentos', None)
        except Exception:
            pass
        try:
            target['patamar'] = getattr(tank_obj, 'patamares', None)
        except Exception:
            pass
        try:
            target['tambores_acu'] = getattr(tank_obj, 'tambores_cumulativo', None)
        except Exception:
            pass
        try:
            target['total_liquido_acu'] = getattr(tank_obj, 'total_liquido_cumulativo', None)
        except Exception:
            pass
        try:
            target['residuos_solidos_acu'] = getattr(tank_obj, 'residuos_solidos_cumulativo', None)
        except Exception:
            pass
        for prediction_field in ('ensacamento_prev', 'icamento_prev', 'cambagem_prev'):
            try:
                prediction_value = _get_tank_prediction_group_value(tank_obj, prediction_field)
                if not _has_defined_prediction_value(prediction_value):
                    prediction_value = getattr(tank_obj, prediction_field, None)
                target[prediction_field] = prediction_value
            except Exception:
                continue
        try:
            previsao = _get_tank_prediction_group_value(tank_obj, 'previsao_termino')
            if not _has_defined_prediction_value(previsao):
                previsao = getattr(tank_obj, 'previsao_termino', None)
            target['previsao_termino'] = previsao.isoformat() if hasattr(previsao, 'isoformat') and previsao else previsao
        except Exception:
            pass
        try:
            target['previsao_termino_locked'] = _is_tank_prediction_locked(tank_obj, 'previsao_termino')
        except Exception:
            target['previsao_termino_locked'] = False
        return target
    except Exception:
        return target


def _format_active_tank_label(tank_payload):
    try:
        if not isinstance(tank_payload, dict):
            return ''
        code = str(tank_payload.get('tanque_codigo') or '').strip()
        name = str(tank_payload.get('nome_tanque') or tank_payload.get('tanque_nome') or '').strip()
        total = tank_payload.get('numero_compartimentos')
        parts = []
        if code:
            parts.append(f'Código: {code}')
        if name:
            parts.append(f'Nome: {name}')
        try:
            total_int = int(total or 0)
        except Exception:
            total_int = 0
        if total_int > 0:
            parts.append(f'Compartimentos: {total_int}')
        if not parts:
            return ''
        return 'Tanque ativo: ' + ' | '.join(parts)
    except Exception:
        return ''


def _normalize_service_token(raw):
    try:
        if raw is None:
            return ''
        # Se o valor for uma estrutura não-textual (ex: dict/list resultante de
        # migração/erro), ignorar — somente aceitar strings/números simples.
        if isinstance(raw, (list, tuple, set, dict)):
            return ''
        s = str(raw).strip().strip("'\"")
        if not s:
            return ''
        low = s.lower()
        if low in ('-', '--', 'na', 'n/a', 'none', 'null', 'não aplicável', 'nao aplicavel'):
            return ''
        return s
    except Exception:
        return ''


def _split_services_raw(raw):
    try:
        if raw is None:
            return []
        if isinstance(raw, (list, tuple, set)):
            out = []
            for item in raw:
                out.extend(_split_services_raw(item))
            return out
        s = str(raw).strip()
        if not s:
            return []
        if s.startswith('[') and s.endswith(']'):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return _split_services_raw(parsed)
            except Exception:
                pass
        s = s.replace('\r\n', '\n').replace(';', '\n').replace('|', '\n')
        parts = []
        for ln in s.split('\n'):
            if not ln:
                continue
            if ',' in ln:
                parts.extend([p.strip() for p in ln.split(',') if p and p.strip()])
            else:
                parts.append(ln.strip())
        return parts
    except Exception:
        return []


def _extract_os_services(os_obj):
    try:
        if os_obj is None:
            return []
        raw_multi = getattr(os_obj, 'servicos', None)
        raw_legacy = getattr(os_obj, 'servico', None)

        multi_values = []
        for v in _split_services_raw(raw_multi):
            norm = _normalize_service_token(v)
            if norm:
                multi_values.append(norm)

        legacy_values = []
        for v in _split_services_raw(raw_legacy):
            norm = _normalize_service_token(v)
            if norm:
                legacy_values.append(norm)

        if not multi_values:
            return legacy_values

        return multi_values
    except Exception:
        return []


def _resolve_os_service_limit(os_obj):
    try:
        if os_obj is None:
            return 0, []
        target_os = os_obj
        try:
            num_os = getattr(os_obj, 'numero_os', None)
            if num_os not in (None, ''):
                siblings = list(
                    OrdemServico.objects
                    .filter(numero_os=num_os)
                    .only('id', 'numero_os', 'servicos', 'servico')
                    .order_by('-id')
                )
                for candidate in siblings:
                    candidate_services = _extract_os_services(candidate)
                    if candidate_services:
                        target_os = candidate
                        break
                else:
                    if siblings:
                        target_os = siblings[0]
        except Exception:
            target_os = os_obj

        services = _extract_os_services(target_os)
        return len(services), services
    except Exception:
        return 0, []


def _resolve_os_scope_ids(os_obj):
    try:
        if os_obj is None:
            return []
        out = []
        try:
            oid = int(getattr(os_obj, 'id', None) or 0)
            if oid > 0:
                out.append(oid)
        except Exception:
            pass
        try:
            num_os = getattr(os_obj, 'numero_os', None)
            if num_os not in (None, ''):
                sibling_ids = [int(v) for v in OrdemServico.objects.filter(numero_os=num_os).values_list('id', flat=True)]
                if sibling_ids:
                    out.extend(sibling_ids)
        except Exception:
            pass
        out = sorted(set([int(v) for v in out if v not in (None, 0)]))
        return out
    except Exception:
        return []


def _normalize_tank_identity_token(raw):
    try:
        if raw is None:
            return ''
        s = str(raw).strip().strip("'\"")
        if not s:
            return ''
        low = s.lower()
        if low in ('-', '--', 'na', 'n/a', 'none', 'null', 'não aplicável', 'nao aplicavel'):
            return ''
        return s
    except Exception:
        return ''


def _strip_tank_identity_numeric_padding(raw):
    try:
        text = str(raw or '').strip()
        if not text:
            return ''

        def _normalize_part(part):
            if not part:
                return ''
            part = re.sub(r'^0+(\d+)(?=[a-z])', r'\1', part, flags=re.IGNORECASE)
            part = re.sub(r'(?<=[a-z])0+(\d+)$', r'\1', part, flags=re.IGNORECASE)
            part = re.sub(r'^0+(\d+)$', r'\1', part)
            return part

        return ' '.join(_normalize_part(part) for part in text.split())
    except Exception:
        return str(raw or '').strip()


def _canonicalize_tank_identity_token(raw, os_num=None):
    try:
        token = _normalize_tank_identity_token(raw)
        if not token:
            return ''
        try:
            canon = _canonical_tank_alias_for_os(os_num, token)
        except Exception:
            canon = None
        if not canon:
            try:
                low = token.casefold().replace('_', ' ').replace('-', ' ')
                low = ''.join(ch for ch in low if (ch.isalnum() or ch.isspace()))
                for marker in ('tank', 'tanque', 'cot'):
                    low = low.replace(marker, ' ')
                low = ' '.join(low.split())
                simplified = low.replace(' ', '')
            except Exception:
                low = ''
                simplified = ''

            if low:
                try:
                    canon = _canonical_tank_alias_for_os(os_num, low)
                except Exception:
                    canon = None
            if not canon and simplified:
                try:
                    canon = _canonical_tank_alias_for_os(os_num, simplified)
                except Exception:
                    canon = None
            if not canon:
                token = simplified or low or token
        if canon:
            token = _normalize_tank_identity_token(canon)
        token = _strip_tank_identity_numeric_padding(token)
        return token
    except Exception:
        return ''


def _tank_identity_key(code, name, os_num=None):
    try:
        code_norm = _canonicalize_tank_identity_token(code, os_num=os_num)
        name_norm = _canonicalize_tank_identity_token(name, os_num=os_num)
        if code_norm:
            return f'code:{code_norm.casefold()}'
        if name_norm:
            return f'name:{name_norm.casefold()}'
        return None
    except Exception:
        return None


def _resolve_os_tank_progress(os_obj):
    try:
        os_ids = _resolve_os_scope_ids(os_obj)
        if not os_ids:
            return 0, set()
        try:
            os_num_ref = getattr(os_obj, 'numero_os', None)
        except Exception:
            os_num_ref = None
        keys = set()
        for code, name in RdoTanque.objects.filter(rdo__ordem_servico_id__in=os_ids).values_list('tanque_codigo', 'nome_tanque'):
            key = _tank_identity_key(code, name, os_num=os_num_ref)
            if not key:
                continue
            keys.add(key)
        return len(keys), keys
    except Exception:
        return 0, set()


def _safe_save_global(obj, max_attempts=6, initial_delay=0.05):
    import time
    from django.db.utils import OperationalError as DjangoOperationalError, ProgrammingError as DjangoProgrammingError
    logger = logging.getLogger(__name__)
    attempt = 0
    delay = initial_delay
    last_exc = None
    while attempt < max_attempts:
        try:
            try:
                alias = getattr(getattr(obj, '_state', None), 'db', None) or 'default'
            except Exception:
                alias = 'default'

            try:
                from django.db import connections
                conn = connections[alias]
            except Exception:
                conn = None

            try:
                rolled_back = False
                try:
                    if conn is not None and hasattr(conn, 'get_rollback'):
                        rolled_back = conn.get_rollback()
                except Exception:
                    rolled_back = False

                if not rolled_back:
                    try:
                        rolled_back = transaction.get_rollback(using=alias)
                    except Exception:
                        try:
                            rolled_back = transaction.get_rollback()
                        except Exception:
                            rolled_back = False

                if rolled_back:
                    logger.error('Current DB transaction marked for rollback; aborting save for %s (alias=%s)', getattr(obj, '__class__', obj), alias)
                    raise transaction.TransactionManagementError('Current transaction marked for rollback; aborting save')
            except transaction.TransactionManagementError:
                raise
            except Exception:
                pass

            obj.save()
            return True
        except Exception as e:
            last_exc = e
            try:
                msg = str(e).lower()
                if isinstance(e, DjangoOperationalError) and 'locked' in msg:
                    try:
                        in_atomic = False
                        if conn is not None and hasattr(conn, 'in_atomic_block'):
                            in_atomic = bool(getattr(conn, 'in_atomic_block'))
                        else:
                            try:
                                in_atomic = bool(transaction.get_connection(using=alias).in_atomic_block)
                            except Exception:
                                in_atomic = False
                    except Exception:
                        in_atomic = False

                    if in_atomic:
                        logger.error('Database locked while in atomic block for %s; aborting save instead of retry to avoid marking transaction for rollback (alias=%s)', getattr(obj, '__class__', obj), alias)
                        raise

                    attempt += 1
                    logger.warning('Database locked when saving %s; retry %s/%s after %.2fs (alias=%s)', getattr(obj, '__class__', obj), attempt, max_attempts, delay, alias)
                    try:
                        from django.db import connections
                        try:
                            if alias in connections:
                                connections[alias].close()
                        except Exception:
                            try:
                                close_old_connections()
                            except Exception:
                                pass
                    except Exception:
                        try:
                            close_old_connections()
                        except Exception:
                            pass
                    time.sleep(delay)
                    delay = min(delay * 2, 1.0)
                    continue

                if isinstance(e, DjangoProgrammingError) and 'closed' in msg:
                    logger.exception('ProgrammingError while saving (closed DB) for %s; attempting single reconnect (alias=%s)', getattr(obj, '__class__', obj), alias)
                    try:
                        from django.db import connections
                        try:
                            if alias in connections:
                                connections[alias].close()
                        except Exception:
                            try:
                                close_old_connections()
                            except Exception:
                                logger.exception('close_old_connections() failed while handling closed DB')
                    except Exception:
                        try:
                            close_old_connections()
                        except Exception:
                            logger.exception('close_old_connections() failed while handling closed DB')

                    try:
                        rolled_back = False
                        try:
                            if conn is not None and hasattr(conn, 'get_rollback'):
                                rolled_back = conn.get_rollback()
                        except Exception:
                            rolled_back = False
                        if not rolled_back:
                            try:
                                rolled_back = transaction.get_rollback(using=alias)
                            except Exception:
                                try:
                                    rolled_back = transaction.get_rollback()
                                except Exception:
                                    rolled_back = False
                        if rolled_back:
                            logger.error('Current DB transaction marked for rollback after closed DB; aborting save for %s (alias=%s)', getattr(obj, '__class__', obj), alias)
                            raise transaction.TransactionManagementError('Current transaction marked for rollback; aborting save')
                    except Exception:
                        logger.exception('Failed checking transaction state after closed DB')
                        raise

                    try:
                        obj.save()
                        return True
                    except Exception as final_e:
                        logger.exception('Retry after reconnect failed for %s; aborting', getattr(obj, '__class__', obj))
                        raise final_e
            except Exception:
                pass
            raise
    try:
        try:
            if transaction.get_rollback():
                logger.error('Current DB transaction marked for rollback; aborting final save for %s', getattr(obj, '__class__', obj))
                raise transaction.TransactionManagementError('Current transaction marked for rollback; aborting save')
        except Exception:
            pass
        obj.save()
        return True
    except Exception:
        logger.exception('Final save attempt failed for object %s', getattr(obj, '__class__', obj))
        raise last_exc

@login_required(login_url='/login/')
@require_GET
def rdo_print(request, rdo_id):
    rdo_payload = {}
    try:
        jr = rdo_detail(request, rdo_id)
        if getattr(jr, 'status_code', 500) == 200:
            data = _json.loads(jr.content.decode('utf-8'))
            if data.get('success'):
                rdo_payload = data.get('rdo', {}) or {}
    except Exception:
        rdo_payload = {}

    try:
        if rdo_payload.get('data'):
            from datetime import datetime
            dt = datetime.fromisoformat(str(rdo_payload['data']).replace('Z','').replace('z',''))
            rdo_payload['data_fmt'] = dt.strftime('%d/%m/%Y')
        else:
            rdo_payload['data_fmt'] = ''
    except Exception:
        rdo_payload['data_fmt'] = rdo_payload.get('data', '')

    try:
        if rdo_payload.get('data_inicio'):
            from datetime import datetime
            raw = str(rdo_payload.get('data_inicio'))
            try:
                dt = datetime.fromisoformat(raw.replace('Z','').replace('z',''))
                rdo_payload['data_inicio_fmt'] = dt.strftime('%d/%m/%Y')
            except Exception:
                try:
                    dt = datetime.strptime(raw, '%Y-%m-%d')
                    rdo_payload['data_inicio_fmt'] = dt.strftime('%d/%m/%Y')
                except Exception:
                    rdo_payload['data_inicio_fmt'] = raw
        else:
            rdo_payload['data_inicio_fmt'] = rdo_payload.get('data_inicio', '')
    except Exception:
        rdo_payload['data_inicio_fmt'] = rdo_payload.get('data_inicio', '')

    try:
        for k in list(rdo_payload.keys()):
            lk = k.lower()
            if lk not in rdo_payload:
                rdo_payload[lk] = rdo_payload.get(k)
    except Exception:
        pass

    equipe_rows, ec_entradas, ec_saidas, fotos_padded = [], [], [], []
    try:
        equipe = rdo_payload.get('equipe') or []
        if isinstance(equipe, list):
            for m in equipe:
                if not isinstance(m, dict):
                    continue
                m['nome_completo'] = m.get('nome_completo') or m.get('nome') or m.get('display_name') or ''
                m['funcao'] = m.get('funcao') or m.get('funcao_label') or m.get('role') or m.get('funcao_nome') or ''
                m['funcao_label'] = m.get('funcao_label') or m.get('funcao') or m.get('funcao_nome') or ''
                m['funcao_nome'] = m.get('funcao_nome') or m.get('funcao') or m.get('funcao_label') or ''
                m['role'] = m.get('role') or m.get('funcao') or m.get('funcao_label') or m.get('funcao_nome') or ''
                m['name'] = m.get('name') or m.get('nome') or m.get('nome_completo') or ''
                m['display_name'] = m.get('display_name') or m.get('nome_completo') or m.get('name') or ''
                if 'em_servico' not in m:
                    m['em_servico'] = bool(m.get('ativo') or m.get('emServico'))
            for i in range(0, len(equipe), 3):
                chunk = equipe[i:i+3]
                any_active = any(bool(m.get('em_servico') or m.get('ativo') or m.get('emServico')) for m in chunk)
                while len(chunk) < 3:
                    chunk.append({})
                equipe_rows.append({ 'members': chunk, 'em_servico': any_active })
        ec = rdo_payload.get('ec_times') or {}
        for idx in range(1, 7):
            ec_entradas.append(ec.get(f'entrada_{idx}', ''))
            ec_saidas.append(ec.get(f'saida_{idx}', ''))
        fotos = rdo_payload.get('fotos') or []
        try:
            resolved = []
            media_root = getattr(settings, 'MEDIA_ROOT', None) or ''
            media_url = getattr(settings, 'MEDIA_URL', '/media/')
            for f in (fotos if isinstance(fotos, list) else []):
                try:
                    if not f:
                        resolved.append(None)
                        continue
                    f_str = str(f).strip()
                    rel = f_str
                    try:
                        dup_prefix = (media_url.rstrip('/') + '/fotos_rdo/').replace('///', '/').replace('//', '/')
                    except Exception:
                        dup_prefix = media_url + 'fotos_rdo/'

                    if f_str.startswith(dup_prefix):
                        rel = f_str[len(dup_prefix):].lstrip('/')
                    elif f_str.startswith(media_url):
                        rel = f_str[len(media_url):].lstrip('/')
                    elif f_str.startswith('/'):
                        rel = f_str.lstrip('/')

                    rel_path = os.path.join(media_root, rel)

                    if os.path.exists(rel_path) and os.path.getsize(rel_path) > 0:
                        url = os.path.join('/fotos_rdo'.rstrip('/'), rel).replace('\\', '/')
                        resolved.append(url)
                        continue

                    try:
                        basename = os.path.basename(rel)
                        parts = basename.split('_')
                        suffix = '_'.join(parts[1:]) if len(parts) > 1 else basename
                        candidates = []
                        try:
                            search_dir = os.path.dirname(rel_path) or os.path.join(media_root, 'rdos')
                            pattern_local = os.path.join(search_dir, '*' + suffix)
                            candidates = glob.glob(pattern_local)
                        except Exception:
                            candidates = []
                        if not candidates:
                            pattern_recursive = os.path.join(media_root, '**', '*' + suffix)
                            candidates = glob.glob(pattern_recursive, recursive=True)
                        candidates = [c for c in candidates if os.path.exists(c) and os.path.getsize(c) > 0]
                        if candidates:
                            candidates.sort(key=lambda p: (os.path.getsize(p), os.path.getmtime(p)), reverse=True)
                            pick = candidates[0]
                            rel_pick = os.path.relpath(pick, media_root)
                            url = os.path.join('/fotos_rdo'.rstrip('/'), rel_pick).replace('\\', '/')
                            logging.getLogger(__name__).warning('Photo missing, using alternative %s for requested %s', rel_pick, rel)
                            resolved.append(url)
                            continue
                    except Exception:
                        pass

                    resolved.append(None)
                except Exception:
                    resolved.append(None)

            fotos_padded = resolved[:5]
            while len(fotos_padded) < 5:
                fotos_padded.append(None)
        except Exception:
            fotos_padded = [None, None, None, None, None]
    except Exception:
        fotos_padded = [None, None, None, None, None]

    try:
        for _k in (
            'total_liquido_cumulativo',
            'total_liquido_acu',
            'residuos_solidos_cumulativo',
            'residuos_solidos_acu',
            'ensacamento_cumulativo',
            'icamento_cumulativo',
            'cambagem_cumulativo',
            'tambores_cumulativo',
            'tambores_acu',
        ):
            rdo_payload.setdefault(_k, rdo_payload.get(_k, ''))
    except Exception:
        pass

    context = {
        'rdo': rdo_payload,
        'equipe_rows': equipe_rows,
        'ec_entradas': ec_entradas,
        'ec_saidas': ec_saidas,
        'fotos_padded': fotos_padded,
        'inline_css': _get_rdo_inline_css(),
    }

    try:
        if (
            not rdo_payload.get('total_hh_frente_real')
            or not rdo_payload.get('total_hh_cumulativo_real')
            or not rdo_payload.get('hh_disponivel_cumulativo')
        ):
            try:
                ro = RDO.objects.select_related('ordem_servico').get(pk=rdo_id)
            except Exception:
                ro = None

            if ro is not None:
                try:
                    if not rdo_payload.get('total_hh_frente_real') and hasattr(ro, 'compute_total_hh_frente_real'):
                        hh_diario = ro.compute_total_hh_frente_real()
                        if hh_diario:
                            rdo_payload['total_hh_frente_real'] = hh_diario
                except Exception:
                    pass

                try:
                    if not rdo_payload.get('total_hh_cumulativo_real') and hasattr(ro, 'compute_total_hh_cumulativo_real'):
                        hh_cumulativo = ro.compute_total_hh_cumulativo_real()
                        if hh_cumulativo:
                            rdo_payload['total_hh_cumulativo_real'] = hh_cumulativo
                except Exception:
                    pass

                try:
                    if not rdo_payload.get('hh_disponivel_cumulativo'):
                        if hasattr(ro, 'calc_hh_disponivel_cumulativo_time'):
                            hh_time = ro.calc_hh_disponivel_cumulativo_time()
                            if hh_time:
                                rdo_payload['hh_disponivel_cumulativo'] = hh_time
                        else:
                            hh_field = getattr(ro, 'hh_disponivel_cumulativo', None)
                            if hh_field:
                                rdo_payload['hh_disponivel_cumulativo'] = hh_field
                except Exception:
                    pass
    except Exception:
        pass

    try:
        from datetime import time as _dt_time
        def _time_to_hhmm(v):
            try:
                if v is None:
                    return None
                if isinstance(v, _dt_time):
                    return v.strftime('%H:%M')
                s = str(v)
                if not s:
                    return None
                if ':' in s:
                    parts = s.split(':')
                    try:
                        h = int(parts[0]); m = int(parts[1]) if len(parts) > 1 else 0
                        return f"{h:02d}:{m:02d}"
                    except Exception:
                        return s
                return s
            except Exception:
                return None

        rdo_payload['total_hh_cumulativo_real_hhmm'] = _time_to_hhmm(rdo_payload.get('total_hh_cumulativo_real'))
        rdo_payload['hh_disponivel_cumulativo_hhmm'] = _time_to_hhmm(rdo_payload.get('hh_disponivel_cumulativo'))
        rdo_payload['total_hh_frente_real_hhmm'] = _time_to_hhmm(rdo_payload.get('total_hh_frente_real'))
    except Exception:
        pass

    return render(request, 'rdo_page.html', context)

def _build_rdo_page_context(request, rdo_id):
    rdo_payload = {}
    try:
        jr = rdo_detail(request, rdo_id)
        if getattr(jr, 'status_code', 500) == 200:
            data = _json.loads(jr.content.decode('utf-8'))
            if data.get('success'):
                rdo_payload = data.get('rdo', {}) or {}
    except Exception:
        rdo_payload = {}
    try:
        if rdo_payload.get('data_inicio'):
            from datetime import datetime
            raw = str(rdo_payload.get('data_inicio'))
            try:
                dt = datetime.fromisoformat(raw.replace('Z','').replace('z',''))
                rdo_payload['data_inicio_fmt'] = dt.strftime('%d/%m/%Y')
            except Exception:
                try:
                    dt = datetime.strptime(raw, '%Y-%m-%d')
                    rdo_payload['data_inicio_fmt'] = dt.strftime('%d/%m/%Y')
                except Exception:
                    rdo_payload['data_inicio_fmt'] = raw
        else:
            rdo_payload['data_inicio_fmt'] = rdo_payload.get('data_inicio', '')
    except Exception:
        rdo_payload['data_inicio_fmt'] = rdo_payload.get('data_inicio', '')

    try:
        fotos = rdo_payload.get('fotos') or []
        if not isinstance(fotos, (list, tuple)):
            if isinstance(fotos, str):
                fotos = [ln for ln in fotos.splitlines() if ln.strip()]
            else:
                fotos = []

        resolved = []
        media_root = getattr(settings, 'MEDIA_ROOT', '') or ''
        media_url = getattr(settings, 'MEDIA_URL', '/media/')
        try:
            dup_prefix = (media_url.rstrip('/') + '/fotos_rdo/').replace('///', '/').replace('//', '/')
        except Exception:
            dup_prefix = media_url + 'fotos_rdo/'

        for f in fotos:
            try:
                if not f:
                    resolved.append(None)
                    continue
                f_str = str(f).strip()
                rel = f_str
                if f_str.startswith(dup_prefix):
                    rel = f_str[len(dup_prefix):].lstrip('/')
                elif f_str.startswith(media_url):
                    rel = f_str[len(media_url):].lstrip('/')
                elif f_str.startswith('/'):
                    rel = f_str.lstrip('/')
                rel_path = os.path.join(media_root, rel)

                if os.path.exists(rel_path) and os.path.getsize(rel_path) > 0:
                    url = os.path.join('/fotos_rdo'.rstrip('/'), rel).replace('\\', '/')
                    resolved.append(url)
                    continue

                try:
                    basename = os.path.basename(rel)
                    parts = basename.split('_')
                    suffix = '_'.join(parts[1:]) if len(parts) > 1 else basename
                    candidates = []
                    try:
                        search_dir = os.path.dirname(rel_path) or os.path.join(media_root, 'rdos')
                        pattern_local = os.path.join(search_dir, '*' + suffix)
                        candidates = glob.glob(pattern_local)
                    except Exception:
                        candidates = []
                    if not candidates:
                        pattern_recursive = os.path.join(media_root, '**', '*' + suffix)
                        candidates = glob.glob(pattern_recursive, recursive=True)
                    candidates = [c for c in candidates if os.path.exists(c) and os.path.getsize(c) > 0]
                    if candidates:
                        candidates.sort(key=lambda p: (os.path.getsize(p), os.path.getmtime(p)), reverse=True)
                        pick = candidates[0]
                        rel_pick = os.path.relpath(pick, media_root)
                        url = os.path.join('/fotos_rdo'.rstrip('/'), rel_pick).replace('\\', '/')
                        logging.getLogger(__name__).warning('Photo missing (page), using alternative %s for requested %s', rel_pick, rel)
                        resolved.append(url)
                        continue
                except Exception:
                    pass

                resolved.append(None)
            except Exception:
                resolved.append(None)

        fotos_padded = resolved[:5]
        while len(fotos_padded) < 5:
            fotos_padded.append(None)
    except Exception:
        fotos_padded = [None, None, None, None, None]

    ec_entradas, ec_saidas = [], []
    try:
        ec = rdo_payload.get('ec_times') or {}
        for idx in range(1, 7):
            ec_entradas.append(ec.get(f'entrada_{idx}', ''))
            ec_saidas.append(ec.get(f'saida_{idx}', ''))
    except Exception:
        ec_entradas = [''] * 6
        ec_saidas = [''] * 6

    equipe_rows = []
    try:
        equipe = rdo_payload.get('equipe') or []
        if isinstance(equipe, list):
            for m in equipe:
                if not isinstance(m, dict):
                    continue
                m['nome_completo'] = m.get('nome_completo') or m.get('nome') or m.get('display_name') or ''
                m['funcao'] = m.get('funcao') or m.get('funcao_label') or m.get('role') or m.get('funcao_nome') or ''
                m['funcao_label'] = m.get('funcao_label') or m.get('funcao') or m.get('funcao_nome') or ''
                m['funcao_nome'] = m.get('funcao_nome') or m.get('funcao') or m.get('funcao_label') or ''
                m['role'] = m.get('role') or m.get('funcao') or m.get('funcao_label') or m.get('funcao_nome') or ''
                m['name'] = m.get('name') or m.get('nome') or m.get('nome_completo') or ''
                m['display_name'] = m.get('display_name') or m.get('nome_completo') or m.get('name') or ''
                if 'em_servico' not in m:
                    m['em_servico'] = bool(m.get('ativo') or m.get('emServico'))

            if equipe:
                for i in range(0, len(equipe), 3):
                    chunk = equipe[i:i+3]
                    while len(chunk) < 3:
                        chunk.append({})
                    any_active = any(bool(m.get('em_servico')) for m in chunk if isinstance(m, dict))
                    equipe_rows.append({'members': chunk, 'em_servico': any_active})
    except Exception:
        equipe_rows = []

    try:
        atividades = rdo_payload.get('atividades') or []
        if isinstance(atividades, list) and atividades:
            try:
                from deep_translator import GoogleTranslator
                _translator = GoogleTranslator(source='pt', target='en')
            except Exception:
                _translator = None
            for a in atividades:
                if not isinstance(a, dict):
                    continue
                pt = (a.get('comentario_pt') or '')
                en = (a.get('comentario_en') or '')
                if (not en) and pt:
                    if _translator is not None:
                        try:
                            tr = _translator.translate(pt)
                            a['comentario_en'] = tr or pt
                        except Exception:
                            a['comentario_en'] = pt
                    else:
                        a['comentario_en'] = pt
            rdo_payload['atividades'] = atividades
    except Exception:
        pass

    try:
        ec_entradas = [ ('' if (t is None or (isinstance(t, str) and t.strip().lower() == 'none')) else t) for t in ec_entradas ]
        ec_saidas = [ ('' if (t is None or (isinstance(t, str) and t.strip().lower() == 'none')) else t) for t in ec_saidas ]
    except Exception:
        ec_entradas = [''] * 6
        ec_saidas = [''] * 6

    try:
        conf_raw = None
        for key in ('confinado', 'espaco_confinado', 'espaco_confinado_bool', 'confinado_bool', 'espacoConfinado'):
            if key in rdo_payload and rdo_payload.get(key) is not None:
                conf_raw = rdo_payload.get(key)
                break

        def _to_sim_nao(v):
            if v is None:
                return ''
            if isinstance(v, bool):
                return 'Sim' if v else 'Não'
            s = str(v).strip()
            if not s:
                return ''
            low = s.lower()
            if low in ('1', 'true', 'sim', 's', 'yes', 'y'):
                return 'Sim'
            if low in ('0', 'false', 'nao', 'não', 'n', 'no'):
                return 'Não'
            return s

        if 'confinado' not in rdo_payload or rdo_payload.get('confinado') in (None, ''):
            rdo_payload['confinado'] = _to_sim_nao(conf_raw)
        else:
            rdo_payload['confinado'] = _to_sim_nao(rdo_payload.get('confinado'))
    except Exception:
        try:
            if 'confinado' not in rdo_payload:
                rdo_payload['confinado'] = ''
        except Exception:
            pass

    try:
        ciente_pt = rdo_payload.get('ciente_observacoes_pt') or rdo_payload.get('ciente_observacoes') or rdo_payload.get('ciente') or ''
        ciente_en = rdo_payload.get('ciente_observacoes_en') or ''
        if (not ciente_en) and ciente_pt:
            try:
                from deep_translator import GoogleTranslator
                try:
                    tr = GoogleTranslator(source='pt', target='en').translate(str(ciente_pt))
                    if tr:
                        rdo_payload['ciente_observacoes_en'] = tr
                    else:
                        rdo_payload['ciente_observacoes_en'] = str(ciente_pt)
                except Exception:
                    rdo_payload['ciente_observacoes_en'] = str(ciente_pt)
            except Exception:
                rdo_payload['ciente_observacoes_en'] = str(ciente_pt)
    except Exception:
        pass

    try:
        for k in list(rdo_payload.keys()):
            lk = k.lower()
            if lk not in rdo_payload:
                rdo_payload[lk] = rdo_payload.get(k)
    except Exception:
        pass

    try:
        if 'exist_pt' in rdo_payload:
            val = rdo_payload.get('exist_pt')
            if isinstance(val, bool):
                rdo_payload['exist_pt'] = 'Sim' if val else 'Não'
            else:
                s = str(val).strip()
                if s.lower() in ('1', 'true', 'sim', 's', 'yes', 'y'):
                    rdo_payload['exist_pt'] = 'Sim'
                elif s.lower() in ('0', 'false', 'nao', 'não', 'n', 'no'):
                    rdo_payload['exist_pt'] = 'Não'
                else:
                    rdo_payload['exist_pt'] = s
    except Exception:
        pass

    try:
        st = rdo_payload.get('select_turnos')
        def _uniq_preserve(seq):
            seen = set()
            out = []
            for it in seq:
                try:
                    s = ('' if it is None else str(it)).strip()
                except Exception:
                    s = str(it)
                if not s:
                    continue
                if s in seen:
                    continue
                seen.add(s)
                out.append(s)
            return out

        if isinstance(st, (list, tuple)):
            parts = _uniq_preserve(st)
            rdo_payload['select_turnos'] = ', '.join(parts)
        elif isinstance(st, str):
            s = st.strip()
            if s.startswith('[') and s.endswith(']'):
                inner = s[1:-1].strip()
                if inner:
                    parts = [p.strip().strip("'\"") for p in inner.split(',') if p.strip()]
                    parts = _uniq_preserve(parts)
                    rdo_payload['select_turnos'] = ', '.join(parts)
                else:
                    rdo_payload['select_turnos'] = ''
            elif ',' in s:
                parts = [p.strip() for p in s.split(',') if p.strip()]
                parts = _uniq_preserve(parts)
                rdo_payload['select_turnos'] = ', '.join(parts)
            else:
                rdo_payload['select_turnos'] = s
        else:
            rdo_payload['select_turnos'] = rdo_payload.get('select_turnos') or ''
    except Exception:
        try:
            rdo_payload['select_turnos'] = rdo_payload.get('select_turnos') or ''
        except Exception:
            pass

    def _clean_none_values(obj):
        try:
            if obj is None:
                return ''
            if isinstance(obj, str):
                s = obj.strip()
                if s.lower() == 'none':
                    return ''
                return obj
            if isinstance(obj, dict):
                out = {}
                for kk, vv in obj.items():
                    out[kk] = _clean_none_values(vv)
                return out
            if isinstance(obj, (list, tuple)):
                out_list = []
                for vv in obj:
                    out_list.append(_clean_none_values(vv))
                return out_list
            return obj
        except Exception:
            return obj

    try:
        rdo_payload = _clean_none_values(rdo_payload)
        ec_entradas = [ ('' if (t is None or (isinstance(t, str) and str(t).strip().lower() == 'none')) else t) for t in ec_entradas ]
        ec_saidas = [ ('' if (t is None or (isinstance(t, str) and str(t).strip().lower() == 'none')) else t) for t in ec_saidas ]
        if 'atividades' in rdo_payload and isinstance(rdo_payload.get('atividades'), list):
            rdo_payload['atividades'] = _clean_none_values(rdo_payload.get('atividades'))
        try:
            cleaned_rows = []
            for row in equipe_rows:
                if isinstance(row, dict):
                    members = row.get('members', [])
                    cleaned_members = []
                    for m in members:
                        if isinstance(m, dict):
                            cleaned_members.append(_clean_none_values(m))
                        else:
                            cleaned_members.append(m)
                    cleaned_rows.append({'members': cleaned_members, 'em_servico': row.get('em_servico')})
                else:
                    cleaned_rows.append(row)
            equipe_rows = cleaned_rows
        except Exception:
            pass
        try:
            fotos_padded = [ ('' if (f is None or (isinstance(f, str) and str(f).strip().lower() == 'none')) else f) for f in fotos_padded ]
        except Exception:
            pass
    except Exception:
        pass

    try:
        try:
            ro = locals().get('ro', None)
        except Exception:
            ro = None
        if ro is None:
            try:
                ro = RDO.objects.select_related('ordem_servico').get(pk=rdo_id)
            except Exception:
                ro = None

        if ro is not None:
            ordem_obj = getattr(ro, 'ordem_servico', None)
            rdo_date = getattr(ro, 'data', None)
            if ordem_obj is not None and rdo_date is not None:
                try:
                    prev_rdos = RDO.objects.filter(ordem_servico=ordem_obj, data__lte=rdo_date)
                    agg_r = prev_rdos.aggregate(sum_ens=Sum('ensacamento'), sum_ica=Sum('icamento'), sum_camba=Sum('cambagem'))
                    if agg_r:
                        if agg_r.get('sum_ens') is not None and (not rdo_payload.get('ensacamento_cumulativo')):
                            rdo_payload['ensacamento_cumulativo'] = int(agg_r.get('sum_ens') or 0)
                        if agg_r.get('sum_ica') is not None and (not rdo_payload.get('icamento_cumulativo')):
                            rdo_payload['icamento_cumulativo'] = int(agg_r.get('sum_ica') or 0)
                        if agg_r.get('sum_camba') is not None and (not rdo_payload.get('cambagem_cumulativo')):
                            rdo_payload['cambagem_cumulativo'] = int(agg_r.get('sum_camba') or 0)
                except Exception:
                    pass

                try:
                    qs_t = RdoTanque.objects.filter(rdo__ordem_servico=ordem_obj, rdo__data__lte=rdo_date)
                    agg_t = qs_t.aggregate(sum_total=Sum('total_liquido'), sum_res=Sum('residuos_solidos'))
                    if agg_t:
                        if agg_t.get('sum_total') is not None and (not rdo_payload.get('total_liquido_acu') and not rdo_payload.get('total_liquido_cumulativo')):
                            rdo_payload['total_liquido_acu'] = agg_t.get('sum_total')
                            rdo_payload['total_liquido_cumulativo'] = agg_t.get('sum_total')
                        if agg_t.get('sum_res') is not None and (not rdo_payload.get('residuos_solidos_acu') and not rdo_payload.get('residuos_solidos_cumulativo')):
                            rdo_payload['residuos_solidos_acu'] = agg_t.get('sum_res')
                            rdo_payload['residuos_solidos_cumulativo'] = agg_t.get('sum_res')
                except Exception:
                    pass

                # Somatório de tambores de todos os RDOs da mesma OS (até a data atual do RDO)
                try:
                    sum_tambores_os = RDO.objects.filter(ordem_servico=ordem_obj, data__lte=rdo_date).aggregate(total=Sum('tambores')).get('total')
                    rdo_payload['total_tambores_os'] = int(sum_tambores_os or 0)
                except Exception:
                    try:
                        rdo_payload['total_tambores_os'] = int(rdo_payload.get('total_tambores_os') or 0)
                    except Exception:
                        pass
    except Exception:
        pass

    try:
        for _k in (
            'total_liquido_cumulativo',
            'total_liquido_acu',
            'residuos_solidos_cumulativo',
            'residuos_solidos_acu',
            'ensacamento_cumulativo',
            'icamento_cumulativo',
            'cambagem_cumulativo',
            'tambores_cumulativo',
            'tambores_acu',
        ):
            rdo_payload.setdefault(_k, rdo_payload.get(_k, ''))
    except Exception:
        pass

    context = {
        'rdo': rdo_payload,
        'equipe_rows': equipe_rows,
        'fotos_padded': fotos_padded,
        'ec_entradas': ec_entradas,
        'ec_saidas': ec_saidas,
        'inline_css': _get_rdo_inline_css(),
    }
    try:
        tanques_list = rdo_payload.get('tanques') or []
        if isinstance(tanques_list, dict):
            try:
                tanques_list = list(tanques_list.values())
            except Exception:
                tanques_list = []
        if tanques_list and rdo_id:
            try:
                qs = RdoTanque.objects.filter(rdo_id=rdo_id)
                by_id = {getattr(t, 'id', None): t for t in qs}
                by_code = {}
                for t in qs:
                    code = getattr(t, 'tanque_codigo', None)
                    if code and code not in by_code:
                        by_code[code] = t

                def _is_placeholder(val):
                    try:
                        if val is None:
                            return True
                        if isinstance(val, str):
                            s = val.strip().lower()
                            return s in ('', '-', '—', 'none', 'null')
                        return False
                    except Exception:
                        return False
                def pick(*vals):
                    for v in vals:
                        if not _is_placeholder(v):
                            return v
                    return None

                enriched = []
                for d in tanques_list:
                    if not isinstance(d, dict):
                        enriched.append(d)
                        continue
                    did = d.get('id')
                    dcode = d.get('tanque_codigo') or d.get('codigo')
                    mt = by_id.get(did) if did in by_id else by_code.get(dcode)
                    def mget(attr):
                        return getattr(mt, attr, None) if mt else None

                    codigo = pick(d.get('codigo'), d.get('tanque_codigo'), mget('tanque_codigo'))
                    volume = pick(d.get('volume'), d.get('volume_tanque_exec'), mget('volume_tanque_exec'), mget('volume'))
                    patamar = pick(d.get('patamar'), d.get('patamares'), mget('patamar'), mget('patamares'))
                    tipo = pick(d.get('tipo_tanque'), d.get('tipo'), mget('tipo_tanque'), mget('tipo'))
                    ncomp = pick(d.get('numero_compartimentos'), d.get('numero_compartimento'), mget('numero_compartimentos'), mget('numero_compartimento'))
                    gavetas = pick(d.get('gavetas'), mget('gavetas'))
                    nome = pick(d.get('nome'), d.get('nome_tanque'), mget('nome'), mget('tanque_nome'))

                    nd = dict(d)
                    if codigo is not None:
                        nd.setdefault('codigo', codigo)
                        nd.setdefault('tanque_codigo', codigo)
                    if volume is not None:
                        nd.setdefault('volume', volume)
                        nd.setdefault('volume_tanque_exec', volume)
                    if patamar is not None:
                        nd.setdefault('patamar', patamar)
                        nd.setdefault('patamares', patamar)
                    if tipo is not None:
                        nd.setdefault('tipo_tanque', tipo)
                        nd.setdefault('tipo', tipo)
                    if ncomp is not None:
                        nd.setdefault('numero_compartimentos', ncomp)
                        nd.setdefault('numero_compartimento', ncomp)
                    if gavetas is not None:
                        nd.setdefault('gavetas', gavetas)
                    if nome is not None:
                        nd.setdefault('nome', nome)
                        nd.setdefault('tanque_nome', nome)
                    try:
                        def pick_tank(*names):
                            for n in names:
                                v = d.get(n) if isinstance(d, dict) else None
                                if v is None:
                                    try:
                                        v = mget(n)
                                    except Exception:
                                        v = None
                                if not _is_placeholder(v):
                                    return v
                            return None

                        bval = pick_tank('bombeio', 'quantidade_bombeada', 'quantidade_bombeio', 'bombeio_dia', 'bombeado')
                        if bval is not None:
                            if ('bombeio' not in nd) or _is_placeholder(nd.get('bombeio')):
                                nd['bombeio'] = bval

                        tlq = pick_tank('total_liquido', 'total_liquidos', 'total_liquido_dia', 'residuo_liquido')
                        if tlq is not None:
                            if ('total_liquido' not in nd) or _is_placeholder(nd.get('total_liquido')):
                                nd['total_liquido'] = tlq

                        sraw = pick_tank('sentido_limpeza', 'sentido', 'direcao', 'direcao_limpeza', 'sentido_exec')
                        if sraw is not None:
                            try:
                                token = _canonicalize_sentido(sraw)
                                if token:
                                    nd.setdefault('sentido_limpeza', token)
                                    if token == 'vante > ré':
                                        nd['sentido_label'] = nd.get('sentido_label') or 'Vante > Ré'
                                    elif token == 'ré > vante':
                                        nd['sentido_label'] = nd.get('sentido_label') or 'Ré > Vante'
                                    elif token == 'bombordo > boreste':
                                        nd['sentido_label'] = nd.get('sentido_label') or 'Bombordo > Boreste'
                                    elif token == 'boreste < bombordo':
                                        nd['sentido_label'] = nd.get('sentido_label') or 'Boreste < Bombordo'
                                else:
                                    sval = sraw
                                    if isinstance(sval, str) and not _is_placeholder(sval):
                                        nd.setdefault('sentido_limpeza', None)
                                        nd['sentido_label'] = nd.get('sentido_label') or sval
                                    else:
                                        nd.setdefault('sentido_limpeza', None)
                            except Exception:
                                try:
                                    nd.setdefault('sentido_limpeza', None)
                                except Exception:
                                    pass

                    except Exception:
                        pass
                    enriched.append(nd)
                tanques_list = enriched
                try:
                    present_ids = set([x.get('id') for x in enriched if isinstance(x, dict) and x.get('id') is not None])
                    present_codes = set([ (x.get('tanque_codigo') or x.get('codigo')) for x in enriched if isinstance(x, dict) and (x.get('tanque_codigo') or x.get('codigo')) ])
                    for t in qs:
                        tid = getattr(t, 'id', None)
                        tcode = getattr(t, 'tanque_codigo', None)
                        if (tid in present_ids) or (tcode and tcode in present_codes):
                            continue
                        tanques_list.append({
                            'id': tid,
                            'codigo': getattr(t, 'tanque_codigo', None),
                            'tanque_codigo': getattr(t, 'tanque_codigo', None),
                            'volume': getattr(t, 'volume_tanque_exec', None) or getattr(t, 'volume', None),
                            'volume_tanque_exec': getattr(t, 'volume_tanque_exec', None),
                            'patamar': getattr(t, 'patamar', None) or getattr(t, 'patamares', None),
                            'patamares': getattr(t, 'patamar', None) or getattr(t, 'patamares', None),
                            'tipo_tanque': getattr(t, 'tipo_tanque', None) or getattr(t, 'tipo', None),
                            'tipo': getattr(t, 'tipo_tanque', None) or getattr(t, 'tipo', None),
                            'numero_compartimentos': getattr(t, 'numero_compartimentos', None) or getattr(t, 'numero_compartimento', None),
                            'numero_compartimento': getattr(t, 'numero_compartimento', None) or getattr(t, 'numero_compartimentos', None),
                            'gavetas': getattr(t, 'gavetas', None) or None,
                            'nome': getattr(t, 'nome', None) or getattr(t, 'tanque_nome', None),
                            'tanque_nome': getattr(t, 'tanque_nome', None) or getattr(t, 'nome', None),
                        })
                except Exception:
                    pass
            except Exception:
                pass

        if (not tanques_list) and rdo_id:
            try:
                qs = RdoTanque.objects.filter(rdo_id=rdo_id).order_by('tanque_codigo')
                tl = []
                for t in qs:
                        tl.append({
                        'id': getattr(t, 'id', None),
                        'codigo': getattr(t, 'tanque_codigo', None),
                        'tanque_codigo': getattr(t, 'tanque_codigo', None),
                        'volume': getattr(t, 'volume_tanque_exec', None) or getattr(t, 'volume', None),
                        'volume_tanque_exec': getattr(t, 'volume_tanque_exec', None),
                        'patamar': getattr(t, 'patamar', None) or getattr(t, 'patamares', None),
                        'patamares': getattr(t, 'patamar', None) or getattr(t, 'patamares', None),
                        'tipo_tanque': getattr(t, 'tipo_tanque', None) or getattr(t, 'tipo', None),
                        'tipo': getattr(t, 'tipo_tanque', None) or getattr(t, 'tipo', None),
                        'numero_compartimentos': getattr(t, 'numero_compartimento', None) or getattr(t, 'numero_compartimentos', None),
                        'numero_compartimento': getattr(t, 'numero_compartimento', None),
                        'gavetas': getattr(t, 'gavetas', None) or None,
                        'nome': getattr(t, 'nome', None) or getattr(t, 'tanque_nome', None),
                        'bombeio': getattr(t, 'bombeio', None),
                        'total_liquido': getattr(t, 'total_liquido', None),
                        'ensacamento_cumulativo': getattr(t, 'ensacamento_cumulativo', None) or getattr(t, 'ensacamento_acu', None) or '',
                        'icamento_cumulativo': getattr(t, 'icamento_cumulativo', None) or getattr(t, 'icamento_acu', None) or '',
                        'cambagem_cumulativo': getattr(t, 'cambagem_cumulativo', None) or getattr(t, 'cambagem_acu', None) or '',
                        'tambores_cumulativo': getattr(t, 'tambores_cumulativo', None) or getattr(t, 'tambores_acu', None) or '',
                        'tambores_acu': getattr(t, 'tambores_cumulativo', None) or getattr(t, 'tambores_acu', None) or '',
                        'total_liquido_cumulativo': getattr(t, 'total_liquido_cumulativo', None) or getattr(t, 'total_liquido_acu', None) or '',
                        'total_liquido_acu': getattr(t, 'total_liquido_acu', None) or getattr(t, 'total_liquido', None) or '',
                        'residuos_solidos_cumulativo': getattr(t, 'residuos_solidos_cumulativo', None) or getattr(t, 'residuos_solidos_acu', None) or '',
                        'residuos_solidos_acu': getattr(t, 'residuos_solidos_acu', None) or getattr(t, 'residuos_solidos', None) or '',
                        'sentido_limpeza': getattr(t, 'sentido_limpeza', None),
                        'sentido_label': (lambda v: ('Vante > Ré' if _canonicalize_sentido(v) == 'vante > ré' else ('Ré > Vante' if _canonicalize_sentido(v) == 'ré > vante' else ('Bombordo > Boreste' if _canonicalize_sentido(v) == 'bombordo > boreste' else ('Boreste < Bombordo' if _canonicalize_sentido(v) == 'boreste < bombordo' else None)))))(getattr(t, 'sentido_limpeza', None)),
                        'sentido': (lambda v: (_canonicalize_sentido(v) or getattr(t, 'sentido_limpeza', None)))(getattr(t, 'sentido_limpeza', None)),
                    })
                if tl:
                    tanques_list = tl
            except Exception:
                tanques_list = tanques_list or []
        context['tanques'] = tanques_list
        try:
            rdo_payload['tanques'] = tanques_list
        except Exception:
            pass

        # Se houver tanques, preferir leitura dos acumulados vindos de RdoTanque
        try:
            if tanques_list and rdo_id:
                try:
                    qs_t = RdoTanque.objects.filter(rdo_id=rdo_id)
                    agg_t = qs_t.aggregate(
                        sum_ens=Sum('ensacamento_dia'), sum_ens_cum=Sum('ensacamento_cumulativo'),
                        sum_ic=Sum('icamento_dia'), sum_ic_cum=Sum('icamento_cumulativo'),
                        sum_camba=Sum('cambagem_dia'), sum_camba_cum=Sum('cambagem_cumulativo'),
                        sum_total=Sum('total_liquido'), sum_total_cum=Sum('total_liquido_cumulativo'),
                        sum_res=Sum('residuos_solidos'), sum_res_cum=Sum('residuos_solidos_cumulativo'),
                        sum_tambores=Sum('tambores_dia'),
                        sum_tambores_cum=Sum('tambores_cumulativo'),
                    )
                    if agg_t:
                        # dia (valores do dia agregados por tanque)
                        if agg_t.get('sum_ens') is not None:
                            rdo_payload['ensacamento_dia'] = agg_t.get('sum_ens')
                        if agg_t.get('sum_tambores') is not None:
                            rdo_payload['tambores_dia'] = agg_t.get('sum_tambores')
                        rdo_payload['tambores_cumulativo'] = (
                            agg_t.get('sum_tambores_cum')
                            if agg_t.get('sum_tambores_cum') is not None
                            else (agg_t.get('sum_tambores') or rdo_payload.get('tambores_cumulativo'))
                        )
                        rdo_payload['tambores_acu'] = rdo_payload.get('tambores_cumulativo')

                        # cumulativos preferenciais (usar cumulativo se disponível, senão usar soma do dia)
                        rdo_payload['ensacamento_cumulativo'] = agg_t.get('sum_ens_cum') if agg_t.get('sum_ens_cum') is not None else (agg_t.get('sum_ens') or rdo_payload.get('ensacamento_cumulativo'))
                        rdo_payload['icamento_cumulativo'] = agg_t.get('sum_ic_cum') if agg_t.get('sum_ic_cum') is not None else (agg_t.get('sum_ic') or rdo_payload.get('icamento_cumulativo'))
                        rdo_payload['cambagem_cumulativo'] = agg_t.get('sum_camba_cum') if agg_t.get('sum_camba_cum') is not None else (agg_t.get('sum_camba') or rdo_payload.get('cambagem_cumulativo'))

                        # Preferir soma dos totais do dia (`sum_total`) quando disponível;
                        # caso contrário, usar os cumulativos já preenchidos (`sum_total_cum`).
                        rdo_payload['total_liquido_cumulativo'] = (agg_t.get('sum_total') if agg_t.get('sum_total') is not None else (agg_t.get('sum_total_cum') if agg_t.get('sum_total_cum') is not None else rdo_payload.get('total_liquido_cumulativo')))
                        rdo_payload['total_liquido_acu'] = (agg_t.get('sum_total') if agg_t.get('sum_total') is not None else (agg_t.get('sum_total_cum') if agg_t.get('sum_total_cum') is not None else rdo_payload.get('total_liquido_acu')))

                        rdo_payload['residuos_solidos_cumulativo'] = agg_t.get('sum_res_cum') if agg_t.get('sum_res_cum') is not None else (agg_t.get('sum_res') or rdo_payload.get('residuos_solidos_cumulativo'))
                        rdo_payload['residuos_solidos_acu'] = agg_t.get('sum_res_cum') if agg_t.get('sum_res_cum') is not None else (agg_t.get('sum_res') or rdo_payload.get('residuos_solidos_acu'))
                except Exception:
                    pass
                # Agregar percentuais de limpeza a partir dos tanques (por-tanque)
                try:
                    try:
                        from decimal import Decimal
                    except Exception:
                        Decimal = None
                    qs_pct = RdoTanque.objects.filter(rdo_id=rdo_id)
                    agg_pct = qs_pct.aggregate(sum_pct=Sum('percentual_limpeza_diario'), sum_pct_fina=Sum('percentual_limpeza_fina_diario'), sum_mech=Sum('limpeza_mecanizada_diaria'))
                    if agg_pct:
                        def _to_int_clamped(v):
                            try:
                                iv = int(round(float(v or 0)))
                            except Exception:
                                try:
                                    iv = int(float(v or 0))
                                except Exception:
                                    iv = 0
                            return max(0, min(100, iv))

                        if agg_pct.get('sum_pct') is not None:
                            rdo_payload['percentual_limpeza_diario'] = _to_int_clamped(agg_pct.get('sum_pct'))
                        if agg_pct.get('sum_pct_fina') is not None:
                            rdo_payload['percentual_limpeza_fina'] = _to_int_clamped(agg_pct.get('sum_pct_fina'))
                        if agg_pct.get('sum_mech') is not None:
                            rdo_payload['limpeza_mecanizada_diaria'] = _to_int_clamped(agg_pct.get('sum_mech'))

                    # cumulativos por OS/data (somar historico de tanques)
                    try:
                        ordem_obj = rdo_payload.get('ordem_servico') or None
                        rdo_date = None
                        try:
                            # tentar obter data do payload/ro se disponível
                            rdo_date = rdo_payload.get('data') if isinstance(rdo_payload.get('data'), (str,)) else None
                        except Exception:
                            rdo_date = None
                        if ordem_obj is not None:
                            qs_prev_t = RdoTanque.objects.filter(rdo__ordem_servico=ordem_obj)
                            agg_prev = qs_prev_t.aggregate(sum_prev_pct=Sum('percentual_limpeza_diario'), sum_prev_fina=Sum('percentual_limpeza_fina_diario'), sum_prev_mech=Sum('limpeza_mecanizada_diaria'))
                            if agg_prev:
                                if agg_prev.get('sum_prev_pct') is not None:
                                    rdo_payload['percentual_limpeza_diario_cumulativo'] = _to_int_clamped(agg_prev.get('sum_prev_pct'))
                                if agg_prev.get('sum_prev_fina') is not None:
                                    rdo_payload['percentual_limpeza_fina_cumulativo'] = _to_int_clamped(agg_prev.get('sum_prev_fina'))
                                if agg_prev.get('sum_prev_mech') is not None:
                                    rdo_payload['limpeza_mecanizada_cumulativa'] = _to_int_clamped(agg_prev.get('sum_prev_mech'))
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception:
            pass
    except Exception:
        context['tanques'] = rdo_payload.get('tanques') or []
    try:
        logger = logging.getLogger(__name__)
        try:
            logger.debug('rdo_page - rdo_payload keys: %s', list(rdo_payload.keys()))
        except Exception:
            logger.debug('rdo_page - unable to list rdo_payload keys')
        try:
            tanks_json = _json.dumps(context.get('tanques', []), ensure_ascii=False)
        except Exception:
            try:
                import json as _tmp_json
                tanks_json = _tmp_json.dumps(context.get('tanques', []), ensure_ascii=False)
            except Exception:
                tanks_json = str(context.get('tanques', []))
        logger.debug('rdo_page - tanques payload: %s', tanks_json)
    except Exception:
        pass

    return context

@login_required(login_url='/login/')
@require_GET
def rdo_page(request, rdo_id):
    context = _build_rdo_page_context(request, rdo_id)
    return render(request, 'rdo_page.html', context)

@login_required(login_url='/login/')
@require_GET
def rdo_pdf(request, rdo_id):
    try:
        from weasyprint import HTML
    except Exception:
        return HttpResponse(
            'Exportação para PDF indisponível (WeasyPrint não instalado).',
            status=501,
            content_type='text/plain; charset=utf-8'
        )

    rdo_payload = {}
    try:
        jr = rdo_detail(request, rdo_id)
        if getattr(jr, 'status_code', 500) == 200:
            data = _json.loads(jr.content.decode('utf-8'))
            if data.get('success'):
                rdo_payload = data.get('rdo', {}) or {}
    except Exception:
        rdo_payload = {}

    try:
        if rdo_payload.get('data'):
            from datetime import datetime
            dt = datetime.fromisoformat(str(rdo_payload['data']).replace('Z','').replace('z',''))
            rdo_payload['data_fmt'] = dt.strftime('%d/%m/%Y')
        else:
            rdo_payload['data_fmt'] = ''
    except Exception:
        rdo_payload['data_fmt'] = rdo_payload.get('data', '')

    try:
        if rdo_payload.get('data_inicio'):
            from datetime import datetime
            raw = str(rdo_payload.get('data_inicio'))
            try:
                dt = datetime.fromisoformat(raw.replace('Z','').replace('z',''))
                rdo_payload['data_inicio_fmt'] = dt.strftime('%d/%m/%Y')
            except Exception:
                try:
                    dt = datetime.strptime(raw, '%Y-%m-%d')
                    rdo_payload['data_inicio_fmt'] = dt.strftime('%d/%m/%Y')
                except Exception:
                    rdo_payload['data_inicio_fmt'] = raw
        else:
            rdo_payload['data_inicio_fmt'] = rdo_payload.get('data_inicio', '')
    except Exception:
        rdo_payload['data_inicio_fmt'] = rdo_payload.get('data_inicio', '')

    try:
        for k in list(rdo_payload.keys()):
            lk = k.lower()
            if lk not in rdo_payload:
                rdo_payload[lk] = rdo_payload.get(k)
    except Exception:
        pass

    equipe_rows, ec_entradas, ec_saidas, fotos_padded = [], [], [], []
    try:
        equipe = rdo_payload.get('equipe') or []
        if isinstance(equipe, list):
            for m in equipe:
                if not isinstance(m, dict):
                    continue
                m['nome_completo'] = m.get('nome_completo') or m.get('nome') or m.get('display_name') or ''
                m['funcao'] = m.get('funcao') or m.get('funcao_label') or m.get('role') or m.get('funcao_nome') or ''
                m['funcao_label'] = m.get('funcao_label') or m.get('funcao') or m.get('funcao_nome') or ''
                m['funcao_nome'] = m.get('funcao_nome') or m.get('funcao') or m.get('funcao_label') or ''
                m['role'] = m.get('role') or m.get('funcao') or m.get('funcao_label') or m.get('funcao_nome') or ''
                m['name'] = m.get('name') or m.get('nome') or m.get('nome_completo') or ''
                m['display_name'] = m.get('display_name') or m.get('nome_completo') or m.get('name') or ''
                if 'em_servico' not in m:
                    m['em_servico'] = bool(m.get('ativo') or m.get('emServico'))
            for i in range(0, len(equipe), 3):
                chunk = equipe[i:i+3]
                any_active = any(bool(m.get('em_servico') or m.get('ativo') or m.get('emServico')) for m in chunk)
                while len(chunk) < 3:
                    chunk.append({})
                equipe_rows.append({ 'members': chunk, 'em_servico': any_active })
        ec = rdo_payload.get('ec_times') or {}
        for idx in range(1, 7):
            ec_entradas.append(ec.get(f'entrada_{idx}', ''))
            ec_saidas.append(ec.get(f'saida_{idx}', ''))
        fotos = rdo_payload.get('fotos') or []
        if isinstance(fotos, list):
            fotos_padded = fotos[:5]
            while len(fotos_padded) < 5:
                fotos_padded.append(None)
        else:
            fotos_padded = [None, None, None, None, None]
    except Exception:
        fotos_padded = [None, None, None, None, None]

    context = {
        'rdo': rdo_payload,
        'equipe_rows': equipe_rows,
        'ec_entradas': ec_entradas,
        'ec_saidas': ec_saidas,
        'fotos_padded': fotos_padded,
        'inline_css': _get_rdo_inline_css(),
    }

    html_str = render_to_string('rdo_page.html', context)

    base_url = request.build_absolute_uri('/')
    try:
        pdf_bytes = HTML(string=html_str, base_url=base_url).write_pdf()
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.exception('Falha ao gerar PDF via WeasyPrint')
        return HttpResponse(
            'Falha ao gerar PDF. Verifique os logs do servidor para mais detalhes.',
            status=500,
            content_type='text/plain; charset=utf-8'
        )

    filename = f"RDO_{rdo_payload.get('rdo') or rdo_id}.pdf"
    resp = HttpResponse(pdf_bytes, content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp

def _format_ec_time_value(value):
    try:
        if value is None:
            return None
        if isinstance(value, dt_time):
            return value.strftime('%H:%M')
        if isinstance(value, datetime):
            return value.strftime('%H:%M')
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return None
            for fmt in ('%H:%M', '%H:%M:%S'):
                try:
                    parsed = datetime.strptime(s, fmt)
                    return parsed.strftime('%H:%M')
                except Exception:
                    continue
            return s
        return str(value)
    except Exception:
        return None

def _normalize_ec_field_to_list(val):
    try:
        if val is None:
            return []
        if isinstance(val, (list, tuple)):
            return [v for v in (_format_ec_time_value(item) for item in val) if v]
        if isinstance(val, str):
            s = val.strip()
            if not s:
                return []
            if s.startswith('['):
                try:
                    parsed = json.loads(s)
                    return [v for v in (_format_ec_time_value(item) for item in parsed) if v]
                except Exception:
                    pass
            segments = [seg.strip() for seg in s.replace(';', '\n').splitlines() if seg.strip()]
            return [v for v in (_format_ec_time_value(seg) for seg in segments) if v]
        formatted = _format_ec_time_value(val)
        return [formatted] if formatted else []
    except Exception:
        return []

def _parse_time_to_minutes(t):
    if t is None:
        return None
    try:
        if isinstance(t, str):
            s = t.strip()
            if not s:
                return None
            parts = s.split(':')
            if len(parts) >= 2:
                h = int(parts[0]); m = int(parts[1]); return h * 60 + m
            return None
        try:
            h = t.hour; m = t.minute; return h * 60 + m
        except Exception:
            return None
    except Exception:
        return None

def compute_rdo_aggregates(rdo_obj, atividades_payload, ec_times):
    total_atividade = 0
    for at in (atividades_payload or []):
        try:
            ini = _parse_time_to_minutes(at.get('inicio'))
            fim = _parse_time_to_minutes(at.get('fim'))
            if ini is not None and fim is not None and fim >= ini:
                total_atividade += (fim - ini)
        except Exception:
            continue

    total_confinado = 0
    try:
        ent = getattr(rdo_obj, 'entrada_confinado', None)
        sai = getattr(rdo_obj, 'saida_confinado', None)
        ent_m = _parse_time_to_minutes(ent)
        sai_m = _parse_time_to_minutes(sai)
        if ent_m is not None and sai_m is not None and sai_m >= ent_m:
            total_confinado = sai_m - ent_m
        else:
            if isinstance(ec_times, dict):
                e1 = _parse_time_to_minutes(ec_times.get('entrada_1'))
                s1 = _parse_time_to_minutes(ec_times.get('saida_1'))
                if e1 is not None and s1 is not None and s1 >= e1:
                    total_confinado = s1 - e1
    except Exception:
        total_confinado = 0

    total_abertura_pt = 0
    for at in (atividades_payload or []):
        try:
            raw = (at.get('atividade') or '')
            act_norm = ''
            try:
                act_norm = unicodedata.normalize('NFKD', str(raw)).encode('ASCII', 'ignore').decode('ASCII').strip().lower()
            except Exception:
                act_norm = str(raw).strip().lower()

            if act_norm == 'abertura pt' or ('renov' in act_norm and 'pt' in act_norm):
                ini = _parse_time_to_minutes(at.get('inicio'))
                fim = _parse_time_to_minutes(at.get('fim'))
                if ini is not None and fim is not None and fim >= ini:
                    total_abertura_pt += (fim - ini)
        except Exception:
            continue

    ATIVIDADES_EFETIVAS = [
        *_OFFLOADING_ACTIVITY_VALUES,
        'desobstrução de linhas', 'desobstrucao de linhas',
        'drenagem do tanque',
        'acesso ao tanque',
        'instalação / preparação / montagem', 'instalacao / preparacao / montagem', 'instalação/preparação/montagem', 'instalacao/preparacao/montagem', 'instalação', 'preparação', 'montagem', 'setup',
        'mobilização dentro do tanque', 'mobilizacao dentro do tanque',
        'mobilização fora do tanque', 'mobilizacao fora do tanque',
        'desmobilização dentro do tanque', 'desmobilizacao dentro do tanque',
        'desmobilização fora do tanque', 'desmobilizacao fora do tanque',
        'avaliação inicial da área de trabalho', 'avaliacao inicial da area de trabalho',
        'teste tubo a tubo', 'teste tubo-a-tubo',
        'teste hidrostatico', 'teste hidrostático',
        'limpeza mecânica', 'limpeza mecanica',
        'limpeza bebedouro', 'limpeza caixa d\'água', 'limpeza caixa dagua', 'limpeza caixa d\'agua',
        'operação com robô', 'operacao com robo', 'operacao com robô', 'operação com robo',
        'coleta e análise de ar', 'coleta e analise de ar', 'coleta de ar',
        'limpeza de dutos',
        'coleta de água', 'coleta de agua'
    ]

    efetivas_set = set([t.strip().lower() for t in ATIVIDADES_EFETIVAS if t])

    total_atividades_efetivas = 0
    for at in (atividades_payload or []):
        try:
            act = (at.get('atividade') or '').strip().lower()
            if act in efetivas_set:
                ini = _parse_time_to_minutes(at.get('inicio'))
                fim = _parse_time_to_minutes(at.get('fim'))
                if ini is not None and fim is not None:
                    if fim >= ini:
                        diff = fim - ini
                    else:
                        diff = (fim + 24 * 60) - ini
                    total_atividades_efetivas += diff
        except Exception:
            continue

    total_n_efetivo_confinado = 0
    try:
        val = getattr(rdo_obj, 'total_n_efetivo_confinado', None)
        if isinstance(val, int):
            total_n_efetivo_confinado = val
        else:
           
            try:
                total_n_efetivo_confinado = int(val) if val is not None else 0
            except Exception:
                total_n_efetivo_confinado = 0
    except Exception:
        total_n_efetivo_confinado = 0

    total_atividades_nao_efetivas_fora = max(0, total_atividade - total_atividades_efetivas - (total_n_efetivo_confinado or 0))
    try:
        lunch_names = set(['almoço', 'almoco', 'jantar'])
        lunch_min = 0
        for at in (atividades_payload or []):
            try:
                act = (at.get('atividade') or '').strip().lower()
                if act in lunch_names:
                    ini = _parse_time_to_minutes(at.get('inicio'))
                    fim = _parse_time_to_minutes(at.get('fim'))
                    if ini is not None and fim is not None:
                        if fim >= ini:
                            diff = fim - ini
                        else:
                            diff = (fim + 24 * 60) - ini
                        lunch_min += diff
            except Exception:
                continue
        total_atividades_nao_efetivas_fora = max(0, int(total_atividades_nao_efetivas_fora) - int(lunch_min))
    except Exception:
        pass

    return {
        'total_atividade_min': total_atividade,
        'total_confinado_min': total_confinado,
        'total_abertura_pt_min': total_abertura_pt,
        'total_atividades_efetivas_min': total_atividades_efetivas,
        'total_atividades_nao_efetivas_fora_min': total_atividades_nao_efetivas_fora,
        'total_n_efetivo_confinado_min': total_n_efetivo_confinado,
    }
    
    try:
        import json
        entrada_list_final = entrada_list or []
        saida_list_final = saida_list or []
        entrada_norm = [_format_ec_time_value(v) for v in entrada_list_final if _format_ec_time_value(v) is not None]
        saida_norm = [_format_ec_time_value(v) for v in saida_list_final if _format_ec_time_value(v) is not None]
        ec_payload_obj = {'entrada': entrada_norm, 'saida': saida_norm}
        if hasattr(rdo_obj, 'ec_times_json'):
            try:
                rdo_obj.ec_times_json = json.dumps(ec_payload_obj, ensure_ascii=False)
                _safe_save_global(rdo_obj)
            except Exception:
                pass
    except Exception:
        pass
    
@login_required(login_url='/login/')
@require_POST
def translate_preview(request):
    text = None

    if 'text' in request.POST:
        text = request.POST.get('text')
    else:
        import json
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
            text = payload.get('text')
        except Exception:
            text = None

    if text is None:
        return JsonResponse({'success': True, 'en': ''})
    clean = text.strip()
    if len(clean) < 3:
        return JsonResponse({'success': True, 'en': ''})
    try:
        from deep_translator import GoogleTranslator
        en = GoogleTranslator(source='pt', target='en').translate(clean)
    except Exception:
        logger = logging.getLogger(__name__)
        logger.exception('Erro ao traduzir texto no translate_preview')
        return JsonResponse({'success': False, 'en': '', 'error': 'Falha tradução'} , status=200)
    return JsonResponse({'success': True, 'en': en})

@login_required(login_url='/login/')
@require_GET
def find_rdo_by_number(request):
    try:
        rdo_val = request.GET.get('rdo') or request.GET.get('rdo_contagem')
        if not rdo_val:
            return JsonResponse({'success': False, 'error': 'missing rdo param'}, status=400)
        qs = RDO.objects.filter(rdo_contagem=str(rdo_val))
        if not qs.exists():
            try:
                nid = int(rdo_val)
                qs = RDO.objects.filter(id=nid)
            except Exception:
                qs = RDO.objects.none()
        rdo_obj = qs.order_by('-id').first()
        if not rdo_obj:
            return JsonResponse({'success': False, 'id': None})
        os_num = None
        try:
            os_num = getattr(rdo_obj.ordem_servico, 'numero_os', None)
        except Exception:
            os_num = None
        return JsonResponse({'success': True, 'id': rdo_obj.id, 'rdo': getattr(rdo_obj, 'rdo_contagem', None), 'os': os_num})
    except Exception:
        import logging
        logging.exception('find_rdo_by_number failed')
        return JsonResponse({'success': False, 'error': 'internal error'}, status=500)

@login_required(login_url='/login/')
@require_POST
def gerar_atividade(request):
    return JsonResponse({'success': False, 'error': 'Endpoint desativado. Use a nova API para criar RDOs.'}, status=410)

@login_required(login_url='/login/')
@require_GET
def lookup_os(request, os_id):
    try:
        os_obj = OrdemServico.objects.get(pk=os_id)
    except OrdemServico.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'OS não encontrada.'}, status=404)
    try:
        is_supervisor_user = (
            hasattr(request, 'user')
            and request.user.is_authenticated
            and request.user.groups.filter(name='Supervisor').exists()
        )
    except Exception:
        is_supervisor_user = False
    if is_supervisor_user and getattr(os_obj, 'supervisor', None) != request.user:
        return JsonResponse({'success': False, 'error': 'OS não encontrada.'}, status=404)

    try:
        servicos_count, servicos_list = _resolve_os_service_limit(os_obj)
    except Exception:
        servicos_count, servicos_list = (0, [])
    try:
        total_tanques_os, _tank_keys = _resolve_os_tank_progress(os_obj)
    except Exception:
        total_tanques_os = 0

    try:
        sup_obj = getattr(os_obj, 'supervisor', None)
        if sup_obj is None:
            sup_label = None
        else:
            sup_label = (sup_obj.get_full_name() or getattr(sup_obj, 'username', None) or str(sup_obj))
    except Exception:
        try:
            sup_label = str(getattr(os_obj, 'supervisor', None))
        except Exception:
            sup_label = None

    return JsonResponse({
        'success': True,
        'data': {
            'id': os_obj.id,
            'numero_os': os_obj.numero_os,
            'empresa': os_obj.cliente,
            'unidade': os_obj.unidade,
            'supervisor': sup_label,
            'servicos': servicos_list,
            'servicos_count': servicos_count,
            'max_tanques_servicos': (servicos_count if servicos_count > 0 else None),
            'total_tanques_os': int(total_tanques_os or 0),
        }
    })

@login_required(login_url='/login/')
@require_GET
def tanks_for_os(request, os_id):
    logger = logging.getLogger(__name__)
    try:
        try:
            os_obj = OrdemServico.objects.select_related('supervisor').get(pk=os_id)
        except OrdemServico.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'OS não encontrada.'}, status=404)
        try:
            is_supervisor_user = (
                hasattr(request, 'user')
                and request.user.is_authenticated
                and request.user.groups.filter(name='Supervisor').exists()
            )
        except Exception:
            is_supervisor_user = False
        if is_supervisor_user and getattr(os_obj, 'supervisor', None) != request.user:
            return JsonResponse({'success': False, 'error': 'OS não encontrada.'}, status=404)

        # Algumas bases possuem OS duplicadas por `numero_os` em IDs diferentes.
        # Para não perder tanques quando o card aponta para um ID "irmão",
        # ampliamos o escopo para todos os IDs do mesmo número.
        # Regra de negócio solicitada: os tanques devem ser vistos por número
        # de OS mesmo que tenham sido lançados em outro registro/ID da OS.
        candidate_os_ids = [int(os_obj.id)]
        try:
            numero_os = getattr(os_obj, 'numero_os', None)
            siblings_qs = OrdemServico.objects.filter(numero_os=numero_os)
            sibling_ids = [int(v) for v in siblings_qs.values_list('id', flat=True)]
            if sibling_ids:
                candidate_os_ids = sorted(set(sibling_ids))
        except Exception:
            pass

        q = (request.GET.get('q') or '').strip()
        rdo_id_filter = (request.GET.get('rdo_id') or '').strip()
        all_flag = (request.GET.get('all') or '').strip().lower() in ('1', 'true', 'yes', 'on')
        try:
            page = int(request.GET.get('page', 1))
        except Exception:
            page = 1
        try:
            page_size = int(request.GET.get('page_size', 5))
        except Exception:
            page_size = 5
        if page_size < 1:
            page_size = 1
        max_page_size = 200 if all_flag else 5
        if page_size > max_page_size:
            page_size = max_page_size

        tanks_qs = (
            RdoTanque.objects
            .filter(rdo__ordem_servico_id__in=candidate_os_ids)
            .select_related('rdo')
        )
        if rdo_id_filter:
            try:
                tanks_qs = tanks_qs.filter(rdo_id=int(rdo_id_filter))
            except Exception:
                return JsonResponse({'success': False, 'error': 'rdo_id inválido'}, status=400)
        if q:
            tanks_qs = tanks_qs.filter(
                Q(tanque_codigo__icontains=q) |
                Q(nome_tanque__icontains=q)
            )

        tanks_qs = tanks_qs.order_by('-rdo__data', '-id')

        unique = []
        seen = set()
        for t in tanks_qs:
            code = (getattr(t, 'tanque_codigo', None) or '').strip()
            name = (getattr(t, 'nome', None) or getattr(t, 'nome_tanque', None) or '').strip()
            key = (code.lower() if code else name.lower())
            if not key:
                continue
            if key in seen:
                continue
            seen.add(key)
            unique.append(t)

        try:
            unique.sort(key=lambda x: ((getattr(x, 'tanque_codigo', None) or getattr(x, 'nome_tanque', None) or getattr(x, 'nome', None) or '').strip().lower()))
        except Exception:
            pass

        paginator = Paginator(unique, page_size)
        try:
            page_obj = paginator.page(page)
        except Exception:
            page_obj = paginator.page(1)

        results = []
        for t in page_obj.object_list:
            results.append({
                'id': getattr(t, 'id', None),
                'tanque_codigo': getattr(t, 'tanque_codigo', None),
                'numero_compartimentos': getattr(t, 'numero_compartimentos', None),
                'nome': getattr(t, 'nome', None) or getattr(t, 'nome_tanque', None) or None,
                'rdo_id': getattr(getattr(t, 'rdo', None), 'id', None),
                'rdo_data': (getattr(getattr(t, 'rdo', None), 'data', None).isoformat() if getattr(getattr(t, 'rdo', None), 'data', None) else None),
            })

        return JsonResponse({
            'success': True,
            'results': results,
            'page': page_obj.number,
            'page_size': page_size,
            'total': paginator.count,
            'total_pages': paginator.num_pages,
        })
    except Exception:
        logger.exception('Falha em tanks_for_os')
        return JsonResponse({'success': False, 'error': 'internal error'}, status=500)

@login_required(login_url='/login/')
@require_GET
def rdo_tank_detail(request, codigo):
    logger = logging.getLogger(__name__)
    try:
        codigo_q = (codigo or '').strip()
        if not codigo_q:
            return JsonResponse({'success': False, 'error': 'missing codigo'}, status=400)

        def _snapshot_rows_as_previous(snapshot):
            rows = []
            try:
                for row in (snapshot or {}).get('rows', []):
                    mec = row.get('mecanizada') or {}
                    fina = row.get('fina') or {}
                    mec_final = int(mec.get('final') or 0)
                    fina_final = int(fina.get('final') or 0)
                    mec_remaining = int(mec.get('saldo_apos') or 0)
                    fina_remaining = int(fina.get('saldo_apos') or 0)
                    rows.append({
                        'index': row.get('index'),
                        'mecanizada': mec_final,
                        'fina': fina_final,
                        'mecanizada_restante': mec_remaining,
                        'fina_restante': fina_remaining,
                        'mecanizada_final': mec_final,
                        'fina_final': fina_final,
                        'mecanizada_saldo_apos': mec_remaining,
                        'fina_saldo_apos': fina_remaining,
                        'mecanizada_bloqueado': mec_final >= 100,
                        'fina_bloqueado': fina_final >= 100,
                    })
            except Exception:
                return []
            return rows

        tanq_model = None
        tanq_obj = None
        try:
            from django.apps import apps as _apps
            tanq_model = _apps.get_model('GO', 'Tanque')
        except Exception:
            tanq_model = None
        if tanq_model is not None:
            try:
                tanq_obj = tanq_model.objects.filter(codigo__iexact=codigo_q).first()
            except Exception:
                tanq_obj = None

        tank_rt = None
        tank_rt_current = None
        current_rdo = None
        current_rdo_id = None
        try:
            os_id_q = (request.GET.get('os_id') or '').strip()
            rdo_id_q = (request.GET.get('rdo_id') or '').strip()
            os_id_eff = None
            is_supervisor_user = False
            try:
                is_supervisor_user = (
                    hasattr(request, 'user')
                    and request.user.is_authenticated
                    and request.user.groups.filter(name='Supervisor').exists()
                )
            except Exception:
                is_supervisor_user = False
            if rdo_id_q:
                try:
                    current_rdo_id = int(rdo_id_q)
                    current_rdo = RDO.objects.select_related('ordem_servico').filter(pk=current_rdo_id).first()
                    rdo_os = getattr(current_rdo, 'ordem_servico_id', None)
                    if rdo_os:
                        os_id_eff = int(rdo_os)
                except Exception:
                    current_rdo = None
                    current_rdo_id = None
                    os_id_eff = None
            if os_id_eff is None and os_id_q:
                try:
                    os_id_eff = int(os_id_q)
                except Exception:
                    os_id_eff = None

            rt_qs = RdoTanque.objects.filter(tanque_codigo__iexact=codigo_q)
            if os_id_eff is not None:
                os_scope_ids = [int(os_id_eff)]
                try:
                    os_base = OrdemServico.objects.select_related('supervisor').get(pk=os_id_eff)
                    if is_supervisor_user and getattr(os_base, 'supervisor', None) != request.user:
                        return JsonResponse({'success': False, 'error': 'OS não encontrada.'}, status=404)
                    siblings_qs = OrdemServico.objects.filter(numero_os=getattr(os_base, 'numero_os', None))
                    sibling_ids = [int(v) for v in siblings_qs.values_list('id', flat=True)]
                    if sibling_ids:
                        os_scope_ids = sorted(set(sibling_ids))
                except OrdemServico.DoesNotExist:
                    pass
                except Exception:
                    pass
                rt_qs = rt_qs.filter(rdo__ordem_servico_id__in=os_scope_ids)

            if current_rdo_id is not None:
                tank_rt_current = rt_qs.filter(rdo_id=current_rdo_id).order_by('-id').first()
            tank_rt = tank_rt_current or rt_qs.order_by('-rdo__data', '-rdo__pk', '-id').first()
        except Exception:
            current_rdo = None
            current_rdo_id = None
            tank_rt_current = None
            tank_rt = None

        try:
            if tank_rt is not None:
                before_tuple = (
                    getattr(tank_rt, 'ensacamento_cumulativo', None),
                    getattr(tank_rt, 'icamento_cumulativo', None),
                    getattr(tank_rt, 'cambagem_cumulativo', None),
                    getattr(tank_rt, 'tambores_cumulativo', None),
                    getattr(tank_rt, 'percentual_limpeza_cumulativo', None),
                    getattr(tank_rt, 'percentual_limpeza_fina_cumulativo', None),
                    getattr(tank_rt, 'limpeza_fina_cumulativa', None),
                    getattr(tank_rt, 'limpeza_mecanizada_cumulativa', None),
                )
                try:
                    _refresh_tank_metrics_for_display(tank_rt)
                except Exception:
                    pass
                after_tuple = (
                    getattr(tank_rt, 'ensacamento_cumulativo', None),
                    getattr(tank_rt, 'icamento_cumulativo', None),
                    getattr(tank_rt, 'cambagem_cumulativo', None),
                    getattr(tank_rt, 'tambores_cumulativo', None),
                    getattr(tank_rt, 'percentual_limpeza_cumulativo', None),
                    getattr(tank_rt, 'percentual_limpeza_fina_cumulativo', None),
                    getattr(tank_rt, 'limpeza_fina_cumulativa', None),
                    getattr(tank_rt, 'limpeza_mecanizada_cumulativa', None),
                )
                if after_tuple != before_tuple:
                    try:
                        _safe_save_global(tank_rt)
                    except Exception:
                        try:
                            tank_rt.save()
                        except Exception:
                            pass
        except Exception:
            pass

        if not tanq_obj and not tank_rt:
            return JsonResponse({'success': False, 'error': 'tank not found'}, status=404)

        total_compartimentos = None
        current_compartimentos_json = None
        previous_compartimentos = []
        try:
            total_compartimentos = (
                getattr(tank_rt_current, 'numero_compartimentos', None)
                or getattr(tank_rt, 'numero_compartimentos', None)
                or getattr(tanq_obj, 'numero_compartimentos', None)
            )
        except Exception:
            total_compartimentos = None
        try:
            total_compartimentos = int(total_compartimentos or 0)
        except Exception:
            total_compartimentos = 0

        if tank_rt_current is not None:
            current_compartimentos_json = getattr(tank_rt_current, 'compartimentos_avanco_json', None)
            try:
                previous_compartimentos = tank_rt_current.get_previous_compartimentos_payload() or []
            except Exception:
                previous_compartimentos = []
        elif current_rdo is not None:
            try:
                temp_tank = RdoTanque(
                    rdo=current_rdo,
                    tanque_codigo=(getattr(tank_rt, 'tanque_codigo', None) if tank_rt else None) or getattr(tanq_obj, 'codigo', None) or codigo_q,
                    nome_tanque=(getattr(tank_rt, 'nome_tanque', None) if tank_rt else None) or getattr(tanq_obj, 'nome', None),
                    numero_compartimentos=total_compartimentos or None,
                )
                previous_compartimentos = temp_tank.get_previous_compartimentos_payload() or []
            except Exception:
                previous_compartimentos = []
            try:
                if total_compartimentos > 0:
                    current_compartimentos_json = json.dumps(
                        RdoTanque.normalize_compartimentos_payload({}, total_compartimentos),
                        ensure_ascii=False,
                    )
            except Exception:
                current_compartimentos_json = None
        else:
            try:
                if tank_rt is not None and total_compartimentos > 0:
                    current_compartimentos_json = json.dumps(
                        RdoTanque.normalize_compartimentos_payload({}, total_compartimentos),
                        ensure_ascii=False,
                    )
                else:
                    current_compartimentos_json = getattr(tank_rt, 'compartimentos_avanco_json', None) if tank_rt else None
            except Exception:
                current_compartimentos_json = getattr(tank_rt, 'compartimentos_avanco_json', None) if tank_rt else None
            try:
                previous_compartimentos = _snapshot_rows_as_previous(
                    tank_rt.build_compartimento_progress_snapshot()
                ) if tank_rt else []
            except Exception:
                previous_compartimentos = []

        payload = {
            'id': getattr(tanq_obj, 'id', None) or (getattr(tank_rt, 'id', None) if tank_rt else None),
            'tanque_codigo': getattr(tanq_obj, 'codigo', None) or (getattr(tank_rt, 'tanque_codigo', None) if tank_rt else None),
            'nome_tanque': getattr(tanq_obj, 'nome', None) or (getattr(tank_rt, 'nome_tanque', None) if tank_rt else None),
            'tipo_tanque': getattr(tanq_obj, 'tipo', None) or (getattr(tank_rt, 'tipo_tanque', None) if tank_rt else None),
            'numero_compartimentos': getattr(tanq_obj, 'numero_compartimentos', None) or (getattr(tank_rt, 'numero_compartimentos', None) if tank_rt else None),
            'gavetas': getattr(tanq_obj, 'gavetas', None) or (getattr(tank_rt, 'gavetas', None) if tank_rt else None),
            'patamares': getattr(tanq_obj, 'patamares', None) or (getattr(tank_rt, 'patamares', None) if tank_rt else None),
            'volume_tanque_exec': (str(getattr(tanq_obj, 'volume', None)) if getattr(tanq_obj, 'volume', None) is not None else (str(getattr(tank_rt, 'volume_tanque_exec', None)) if tank_rt and getattr(tank_rt, 'volume_tanque_exec', None) is not None else None)),
            'servico_exec': getattr(tank_rt, 'servico_exec', None) if tank_rt else None,
            'metodo_exec': getattr(tank_rt, 'metodo_exec', None) if tank_rt else None,
            'espaco_confinado': getattr(tank_rt, 'espaco_confinado', None) if tank_rt else None,
            'unidade_id': getattr(tanq_obj, 'unidade_id', None) if tanq_obj is not None else None,
        }

        acumulados = {
            'percentual_limpeza_cumulativo': getattr(tank_rt, 'percentual_limpeza_cumulativo', None) if tank_rt else None,
            'percentual_limpeza_fina_cumulativo': getattr(tank_rt, 'percentual_limpeza_fina_cumulativo', None) if tank_rt else None,
            'percentual_ensacamento': getattr(tank_rt, 'percentual_ensacamento', None) if tank_rt else None,
            'percentual_icamento': getattr(tank_rt, 'percentual_icamento', None) if tank_rt else None,
            'percentual_cambagem': getattr(tank_rt, 'percentual_cambagem', None) if tank_rt else None,
            'percentual_avanco': getattr(tank_rt, 'percentual_avanco', None) if tank_rt else None,
        }

        payload.update({
            'acumulados': acumulados,
            'ensacamento_prev': getattr(tank_rt, 'ensacamento_prev', None) if tank_rt else None,
            'icamento_prev': getattr(tank_rt, 'icamento_prev', None) if tank_rt else None,
            'cambagem_prev': getattr(tank_rt, 'cambagem_prev', None) if tank_rt else None,
            'previsao_termino': (getattr(tank_rt, 'previsao_termino', None).isoformat() if tank_rt and getattr(tank_rt, 'previsao_termino', None) else None),
            'ensacamento_cumulativo': getattr(tank_rt, 'ensacamento_cumulativo', None) if tank_rt else None,
            'icamento_cumulativo': getattr(tank_rt, 'icamento_cumulativo', None) if tank_rt else None,
            'cambagem_cumulativo': getattr(tank_rt, 'cambagem_cumulativo', None) if tank_rt else None,
            'tambores_cumulativo': getattr(tank_rt, 'tambores_cumulativo', None) if tank_rt else None,
            'tambores_acu': getattr(tank_rt, 'tambores_cumulativo', None) if tank_rt else None,
            'total_liquido_cumulativo': getattr(tank_rt, 'total_liquido_cumulativo', None) if tank_rt else None,
            'residuos_solidos_cumulativo': getattr(tank_rt, 'residuos_solidos_cumulativo', None) if tank_rt else None,
            'total_liquido_acu': getattr(tank_rt, 'total_liquido_cumulativo', None) if tank_rt else None,
            'residuos_solidos_acu': getattr(tank_rt, 'residuos_solidos_cumulativo', None) if tank_rt else None,
            'limpeza_fina_cumulativa': getattr(tank_rt, 'limpeza_fina_cumulativa', None) if tank_rt else None,
            'limpeza_mecanizada_diaria': getattr(tank_rt, 'limpeza_mecanizada_diaria', None) if tank_rt else None,
            'limpeza_mecanizada_cumulativa': getattr(tank_rt, 'limpeza_mecanizada_cumulativa', None) if tank_rt else None,
            'percentual_limpeza_fina': getattr(tank_rt, 'percentual_limpeza_fina', None) if tank_rt else None,
            'percentual_limpeza_fina_cumulativo': getattr(tank_rt, 'percentual_limpeza_fina_cumulativo', None) if tank_rt else None,
            'limpeza_fina_diaria': getattr(tank_rt, 'limpeza_fina_diaria', None) if tank_rt else None,
            'compartimentos_avanco_json': current_compartimentos_json,
            'previous_compartimentos': previous_compartimentos,
            'created_at': (tank_rt.created_at.isoformat() if tank_rt and getattr(tank_rt, 'created_at', None) else None),
            'updated_at': (tank_rt.updated_at.isoformat() if tank_rt and getattr(tank_rt, 'updated_at', None) else None),
        })

        return JsonResponse({'success': True, 'tank': payload})
    except Exception:
        logger.exception('Falha em rdo_tank_detail')
        return JsonResponse({'success': False, 'error': 'internal error'}, status=500)

@login_required(login_url='/login/')
@require_GET
def rdo_detail(request, rdo_id):
    try:
        rdo_obj = RDO.objects.select_related('ordem_servico').get(pk=rdo_id)
    except RDO.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'RDO não encontrado.'}, status=404)

    try:
        is_supervisor_user = (hasattr(request, 'user') and request.user.is_authenticated and request.user.groups.filter(name='Supervisor').exists())
        if is_supervisor_user:
            ordem = getattr(rdo_obj, 'ordem_servico', None)
            sup = getattr(ordem, 'supervisor', None) if ordem else None
            if sup is None or sup != request.user:
                try:
                    from django.conf import settings as _settings
                    allowed_override = False
                    if getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False):
                        allowed_override = True
                    else:
                        try:
                            grp_names = getattr(_settings, 'RDO_DETAIL_OVERRIDE_GROUPS', []) or []
                            for g in grp_names:
                                if request.user.groups.filter(name=g).exists():
                                    allowed_override = True
                                    break
                        except Exception:
                            allowed_override = False
                    if not allowed_override:
                        return JsonResponse({'success': False, 'error': 'RDO não encontrado.'}, status=404)
                except Exception:
                    return JsonResponse({'success': False, 'error': 'RDO não encontrado.'}, status=404)
    except Exception:
        return JsonResponse({'success': False, 'error': 'RDO não encontrado.'}, status=404)

    try:
        if not getattr(rdo_obj, 'data', None):
            rdo_obj.data = datetime.today().date()
            try:
                rdo_obj.save(update_fields=['data'])
            except Exception:
                _safe_save_global(rdo_obj)
    except Exception:
        pass

    ordem = getattr(rdo_obj, 'ordem_servico', None)
    atividades_payload = []
    for atv in rdo_obj.atividades_rdo.all():
        atividades_payload.append({
            'ordem': atv.ordem,
            'atividade': atv.atividade,
            'atividade_label': atv.get_atividade_display(),
            'inicio': atv.inicio.strftime('%H:%M') if atv.inicio else None,
            'fim': atv.fim.strftime('%H:%M') if atv.fim else None,
            'comentario_pt': atv.comentario_pt,
            'comentario_en': atv.comentario_en,
        })
    fotos_list = []
    try:
        fotos_field = getattr(rdo_obj, 'fotos', None)

        def _coerce_fotos(value):
            if value is None:
                return []
            if isinstance(value, (list, tuple)):
                out = []
                for it in value:
                    if isinstance(it, dict):
                        for k in ('url','src','path','name','file','arquivo'):
                            if it.get(k):
                                out.append(str(it.get(k)))
                                break
                    else:
                        out.append(it)
                return out
            if hasattr(value, 'name'):
                return _coerce_fotos(getattr(value, 'name', None))
            if isinstance(value, str):
                s = value.strip()
                if not s:
                    return []
                if s.startswith('['):
                    try:
                        parsed = json.loads(s)
                        if isinstance(parsed, (list, tuple)):
                            return _coerce_fotos(list(parsed))
                    except Exception:
                        return [ln for ln in s.splitlines() if ln.strip()]
                return [ln for ln in s.splitlines() if ln.strip()]
            return []

        fotos_list = _coerce_fotos(fotos_field)
    except Exception:
        fotos_list = []

    fotos_urls = []

    def _absolute_from_relative(rel_value):
        rel_clean = ('/' + rel_value.lstrip('/')) if rel_value else ''
        candidate = rel_clean or ''
        if not candidate:
            return ''
        try:
            return request.build_absolute_uri(candidate)
        except Exception:
            try:
                origin = request.build_absolute_uri('/')
                origin = origin[:-1] if origin.endswith('/') else origin
                return origin + candidate
            except Exception:
                return candidate

    for item in fotos_list:
        try:
            if not item:
                continue
            raw = str(item).strip()
            if not raw:
                continue

            if raw.startswith('http://') or raw.startswith('https://'):
                fotos_urls.append(raw)
                continue
            if raw.startswith('//'):
                scheme = 'https:' if request.is_secure() else 'http:'
                fotos_urls.append(f'{scheme}{raw}')
                continue

            try:
                media_root = getattr(settings, 'MEDIA_ROOT', '') or ''
            except Exception:
                media_root = ''

            val = raw
            try:
                if val.startswith('/media/'):
                    val = val[len('/media/'):]
                elif val.startswith('/fotos_rdo/'):
                    val = val[len('/fotos_rdo/'):]
                if media_root and val.startswith(media_root):
                    val = val[len(media_root):].lstrip('/')
            except Exception:
                pass

            rel_candidate = val.lstrip('/')
            abs_candidate = os.path.join(media_root, rel_candidate) if media_root else None
            try:
                if media_root and (not abs_candidate or not os.path.exists(abs_candidate)):
                    dirname = os.path.dirname(rel_candidate)
                    basename = os.path.basename(rel_candidate)
                    matches = []
                    try:
                        if dirname:
                            matches = glob.glob(os.path.join(media_root, dirname, f'*{basename}'))
                    except Exception:
                        matches = []
                    if not matches:
                        try:
                            matches = glob.glob(os.path.join(media_root, '**', f'*{basename}'), recursive=True)
                        except Exception:
                            matches = []
                    if matches:
                        try:
                            matches = sorted(matches, key=lambda p: (os.path.getsize(p) > 0, os.path.getmtime(p)), reverse=True)
                        except Exception:
                            pass
                        chosen = matches[0]
                        rel_candidate = os.path.relpath(chosen, media_root).replace(os.path.sep, '/')
            except Exception:
                pass

            public_path = '/fotos_rdo/' + rel_candidate.lstrip('/')
            fotos_urls.append(_absolute_from_relative(public_path))
        except Exception:
            fotos_urls.append(str(item))

    equipe_list = []
    try:
        try:
            rel_members = list(rdo_obj.membros_equipe.all().order_by('ordem', 'id'))
        except Exception:
            rel_members = []
        if rel_members:
            for em in rel_members:
                try:
                    nome = getattr(em.pessoa, 'nome', None) if getattr(em, 'pessoa', None) else getattr(em, 'nome', None)
                except Exception:
                    nome = getattr(em, 'nome', None)
                try:
                    pessoa_id = getattr(em, 'pessoa_id', None) or (getattr(em.pessoa, 'id', None) if getattr(em, 'pessoa', None) else None)
                except Exception:
                    pessoa_id = None
                try:
                    raw_f = getattr(em, 'funcao', None)
                    def _funcao_to_name(val):
                        try:
                            if val is None:
                                return None
                            if hasattr(val, 'nome'):
                                return getattr(val, 'nome')
                            if isinstance(val, dict):
                                return val.get('nome') or val.get('funcao') or None
                            s = str(val).strip()
                            if not s:
                                return None
                            if '|' in s:
                                parts = s.split('|', 1)
                                return parts[1].strip() or parts[0].strip()
                            if s.isdigit():
                                try:
                                    fobj = Funcao.objects.filter(pk=int(s)).first()
                                    return getattr(fobj, 'nome', s) if fobj else s
                                except Exception:
                                    return s
                            return s
                        except Exception:
                            return None

                    funcao_name = _funcao_to_name(raw_f)
                except Exception:
                    funcao_name = getattr(em, 'funcao', None)

                equipe_list.append({
                    'nome': nome,
                    'funcao': funcao_name,
                    'em_servico': bool(getattr(em, 'em_servico', True)),
                    'pessoa_id': pessoa_id,
                })
        else:
            membros_field = getattr(rdo_obj, 'membros', None)
            funcoes_field = getattr(rdo_obj, 'funcoes_list', None) or getattr(rdo_obj, 'funcoes', None)
            def _resolve_nome(val):
                try:
                    if val is None:
                        return None
                    if isinstance(val, dict):
                        return val.get('nome') or val.get('nome_completo') or val.get('name') or val.get('display_name') or None
                    s = str(val).strip()
                    if not s:
                        return None
                    if '|' in s:
                        parts = s.split('|', 1)
                        left, right = parts[0].strip(), parts[1].strip()
                        if left.isdigit():
                            try:
                                p = Pessoa.objects.filter(pk=int(left)).first()
                                return p.nome if p and hasattr(p, 'nome') else (right or s)
                            except Exception:
                                return right or s
                        return right or s
                    if s.isdigit():
                        try:
                            p = Pessoa.objects.filter(pk=int(s)).first()
                            return p.nome if p and hasattr(p, 'nome') else s
                        except Exception:
                            return s
                    return s
                except Exception:
                    return None

            def _resolve_funcao(val):
                try:
                    if val is None:
                        return None
                    if isinstance(val, dict):
                        return val.get('funcao') or val.get('nome') or val.get('label') or None
                    s = str(val).strip()
                    if not s:
                        return None
                    if '|' in s:
                        parts = s.split('|', 1)
                        left, right = parts[0].strip(), parts[1].strip()
                        if left.isdigit():
                            try:
                                f = Funcao.objects.filter(pk=int(left)).first()
                                return f.nome if f and hasattr(f, 'nome') else (right or s)
                            except Exception:
                                return right or s
                        return right or s
                    if s.isdigit():
                        try:
                            f = Funcao.objects.filter(pk=int(s)).first()
                            return f.nome if f and hasattr(f, 'nome') else s
                        except Exception:
                            return s
                    return s
                except Exception:
                    return None
            if membros_field is None:
                mlist = []
            elif isinstance(membros_field, (list, tuple)):
                mlist = list(membros_field)
            elif isinstance(membros_field, str):
                s = membros_field.strip()
                if s.startswith('['):
                    try:
                        mlist = json.loads(s)
                    except Exception:
                        mlist = [ln for ln in s.splitlines() if ln.strip()]
                else:
                    mlist = [ln for ln in s.splitlines() if ln.strip()]
            else:
                mlist = []

            if funcoes_field is None:
                flist = []
            elif isinstance(funcoes_field, (list, tuple)):
                flist = list(funcoes_field)
            elif isinstance(funcoes_field, str):
                s2 = funcoes_field.strip()
                if s2.startswith('['):
                    try:
                        flist = json.loads(s2)
                    except Exception:
                        flist = [ln for ln in s2.splitlines() if ln.strip()]
                else:
                    flist = [ln for ln in s2.splitlines() if ln.strip()]
            else:
                flist = []

            maxlen = max(len(mlist), len(flist))
            def _resolve_pessoa_id(val):
                try:
                    if val is None:
                        return None
                    if isinstance(val, dict):
                        for k in ('id', 'pk', 'pessoa_id'):
                            if k in val:
                                try:
                                    return int(val[k])
                                except Exception:
                                    pass
                        candidate = val.get('nome') or val.get('name')
                        if candidate and isinstance(candidate, str) and '|' in candidate:
                            left = candidate.split('|', 1)[0].strip()
                            if left.isdigit():
                                return int(left)
                        return None
                    s = str(val).strip()
                    if not s:
                        return None
                    if '|' in s:
                        left = s.split('|', 1)[0].strip()
                        if left.isdigit():
                            return int(left)
                    if s.isdigit():
                        return int(s)
                    return None
                except Exception:
                    return None

            for i in range(maxlen):
                raw_nome = (mlist[i] if i < len(mlist) else None)
                raw_func = (flist[i] if i < len(flist) else None)
                equipe_list.append({
                    'nome': _resolve_nome(raw_nome),
                    'funcao': _resolve_funcao(raw_func),
                    'pessoa_id': _resolve_pessoa_id(raw_nome),
                    'em_servico': None,
                })

            try:
                from collections import defaultdict
                import unicodedata as _unic

                def _norm_func_label(label):
                    try:
                        if not label:
                            return ''
                        s = str(label)
                        s = _unic.normalize('NFKD', s)
                        s = ''.join([c for c in s if not _unic.combining(c)])
                        s = s.lower().strip()
                        s = s.replace('  ', ' ')
                        return s
                    except Exception:
                        return str(label or '').lower().strip()
                pessoas_by_func = defaultdict(list)
                try:
                    pessoas_qs = Pessoa.objects.all().only('nome', 'funcao')
                except Exception:
                    pessoas_qs = []
                for p in pessoas_qs:
                    try:
                        fn = (getattr(p, 'funcao', '') or '').strip()
                        if fn:
                            pessoas_by_func[_norm_func_label(fn)].append(p)
                    except Exception:
                        continue

                usados = set()
                try:
                    vinc = getattr(rdo_obj, 'pessoas', None)
                    if vinc is not None:
                        nome_vinc = getattr(vinc, 'nome', None)
                        func_vinc = (getattr(vinc, 'funcao', '') or '').strip()
                        if nome_vinc:
                            usados.add(str(nome_vinc))
                            for item in equipe_list:
                                if (not item.get('nome')) and (_norm_func_label(item.get('funcao')) == _norm_func_label(func_vinc) if func_vinc else False):
                                    item['nome'] = nome_vinc
                                    break
                except Exception:
                    pass

                for item in equipe_list:
                    if item.get('nome'):
                        usados.add(str(item['nome']))
                        continue
                    funcao_label = (str(item.get('funcao') or '').strip())
                    if not funcao_label:
                        continue
                    candidates = pessoas_by_func.get(_norm_func_label(funcao_label), [])
                    chosen = None
                    for cand in candidates:
                        try:
                            nm = getattr(cand, 'nome', None)
                        except Exception:
                            nm = None
                        if nm and nm not in usados:
                            chosen = nm
                            break
                    if not chosen and candidates:
                        try:
                            chosen = getattr(candidates[0], 'nome', None)
                        except Exception:
                            chosen = None
                    if chosen:
                        item['nome'] = chosen
                        usados.add(chosen)

                try:
                    for item in equipe_list:
                        if item.get('nome'):
                            continue
                        if _norm_func_label(item.get('funcao')) != _norm_func_label('Supervisor'):
                            continue
                        if pessoas_by_func.get(_norm_func_label('Supervisor')):
                            continue
                        ordem_obj = getattr(rdo_obj, 'ordem_servico', None)
                        supervisor_user = getattr(ordem_obj, 'supervisor', None) if ordem_obj else None
                        if supervisor_user:
                            try:
                                sup_name = supervisor_user.get_full_name() or supervisor_user.username or str(supervisor_user)
                            except Exception:
                                sup_name = str(supervisor_user)
                            if sup_name:
                                item['nome'] = sup_name
                                usados.add(sup_name)
                                break
                except Exception:
                    pass
            except Exception:
                pass
    except Exception:
        equipe_list = equipe_list
    ec_times = {}
    try:
        entradas = []
        saidas = []
        try:
            tmp_e = []; tmp_s = []
            for i in range(6):
                tmp_e.append(_format_ec_time_value(getattr(rdo_obj, f'entrada_confinado_{i+1}', None)))
                tmp_s.append(_format_ec_time_value(getattr(rdo_obj, f'saida_confinado_{i+1}', None)))
            if any(tmp_e) or any(tmp_s):
                entradas = tmp_e
                saidas = tmp_s
        except Exception:
            entradas = []
            saidas = []
        if not entradas and not saidas:
            try:
                if getattr(rdo_obj, 'ec_times_json', None):
                    import json
                    parsed = json.loads(rdo_obj.ec_times_json)
                    if isinstance(parsed, dict):
                        entradas = parsed.get('entrada') if isinstance(parsed.get('entrada'), list) else []
                        saidas = parsed.get('saida') if isinstance(parsed.get('saida'), list) else []
            except Exception:
                entradas = []
                saidas = []
        if not entradas and not saidas:
            entrada_field = getattr(rdo_obj, 'entrada_confinado', None)
            saida_field = getattr(rdo_obj, 'saida_confinado', None)
            entradas = _normalize_ec_field_to_list(entrada_field)
            saidas = _normalize_ec_field_to_list(saida_field)

        for i in range(6):
            ec_times[f'entrada_{i+1}'] = entradas[i] if i < len(entradas) else None
            ec_times[f'saida_{i+1}'] = saidas[i] if i < len(saidas) else None
    except Exception:
        ec_times = {}

    try:
        aggregates = compute_rdo_aggregates(rdo_obj, atividades_payload, ec_times)
    except Exception:
        logging.getLogger(__name__).exception('Falha ao calcular agregados para rdo_detail; retornando payload parcial')
        aggregates = {}
    payload = {
        'id': rdo_obj.id,
        'data': rdo_obj.data.isoformat() if rdo_obj.data else None,
        'data_inicio': rdo_obj.data_inicio.isoformat() if getattr(rdo_obj, 'data_inicio', None) else None,
        'rdo_data_inicio': rdo_obj.data_inicio.isoformat() if getattr(rdo_obj, 'data_inicio', None) else None,
        'previsao_termino': rdo_obj.previsao_termino.isoformat() if getattr(rdo_obj, 'previsao_termino', None) else None,
        'rdo_previsao_termino': rdo_obj.previsao_termino.isoformat() if getattr(rdo_obj, 'previsao_termino', None) else None,
        'numero_os': ordem.numero_os if ordem else None,
        'max_tanques_servicos': None,
        'servicos_count': 0,
        'servicos_os': [],
        'total_tanques': 0,
        'total_tanques_os': 0,
        'empresa': ordem.cliente if ordem else None,
        'unidade': ordem.unidade if ordem else None,
        'embarcacao': getattr(ordem, 'embarcacao', None),
        'rdo': rdo_obj.rdo,
        'turno': rdo_obj.turno,
        'nome_tanque': rdo_obj.nome_tanque,
        'tanque_codigo': rdo_obj.tanque_codigo,
        'tipo_tanque': rdo_obj.tipo_tanque,
        'numero_compartimentos': rdo_obj.numero_compartimentos,
        'volume_tanque_exec': str(rdo_obj.volume_tanque_exec) if rdo_obj.volume_tanque_exec is not None else None,
        'servico_exec': rdo_obj.servico_exec,
        'metodo_exec': rdo_obj.metodo_exec,
        'gavetas': rdo_obj.gavetas,
        'patamares': rdo_obj.patamares,
        'operadores_simultaneos': rdo_obj.operadores_simultaneos,
        'H2S_ppm': str(getattr(rdo_obj, 'h2s_ppm', None)) if getattr(rdo_obj, 'h2s_ppm', None) is not None else None,
        'LEL': str(getattr(rdo_obj, 'lel', None)) if getattr(rdo_obj, 'lel', None) is not None else None,
        'CO_ppm': str(getattr(rdo_obj, 'co_ppm', None)) if getattr(rdo_obj, 'co_ppm', None) is not None else None,
        'O2_percent': str(getattr(rdo_obj, 'o2_percent', None)) if getattr(rdo_obj, 'o2_percent', None) is not None else None,
        'bombeio': (lambda v: (str(v) if v is not None and not isinstance(v, (int, float)) else v))(getattr(rdo_obj, 'bombeio', getattr(rdo_obj, 'quantidade_bombeada', None))),
        'total_liquido': getattr(rdo_obj, 'total_liquido', None),
        'vazao_bombeio': (None if getattr(rdo_obj, 'vazao_bombeio', None) is None else (str(rdo_obj.vazao_bombeio) if not isinstance(getattr(rdo_obj, 'vazao_bombeio', None), (int, float)) else getattr(rdo_obj, 'vazao_bombeio'))),
        'residuo_liquido': getattr(rdo_obj, 'residuo_liquido', getattr(rdo_obj, 'total_liquido', None)),
        'ensacamento': (lambda: getattr(rdo_obj.tanques.first(), 'ensacamento_dia', None) if rdo_obj.tanques.exists() else getattr(rdo_obj, 'ensacamento', None))(),
        'ensacamento_dia': (lambda: getattr(rdo_obj.tanques.first(), 'ensacamento_dia', None) if rdo_obj.tanques.exists() else getattr(rdo_obj, 'ensacamento', None))(),
        'tambores': getattr(rdo_obj, 'tambores', None),
        'tambores_dia': getattr(rdo_obj, 'tambores', None),
        'tambores_cumulativo': (lambda: getattr(rdo_obj.tanques.first(), 'tambores_cumulativo', None) if rdo_obj.tanques.exists() else None)(),
        'tambores_acu': (lambda: getattr(rdo_obj.tanques.first(), 'tambores_cumulativo', None) if rdo_obj.tanques.exists() else None)(),
        'total_solidos': getattr(rdo_obj, 'total_solidos', None),
        'residuos_solidos': getattr(rdo_obj, 'residuos_solidos', getattr(rdo_obj, 'total_solidos', None)),
        'total_residuos': getattr(rdo_obj, 'total_residuos', None),
        'residuos_totais': getattr(rdo_obj, 'residuos_totais', getattr(rdo_obj, 'total_residuos', None)),
        'percentual_avanco': getattr(rdo_obj, 'percentual_avanco', None),
        'percentual_avanco_cumulativo': getattr(rdo_obj, 'percentual_avanco_cumulativo', None),
        'percentual_limpeza': getattr(rdo_obj, 'percentual_limpeza', None),
        'percentual_limpeza_cumulativo': getattr(rdo_obj, 'percentual_limpeza_cumulativo', None),
        'percentual_limpeza_diario': getattr(rdo_obj, 'percentual_limpeza_diario', None),
        'limpeza_mecanizada_diaria': getattr(rdo_obj, 'limpeza_mecanizada_diaria', None),
        'percentual_limpeza_diario_cumulativo': getattr(rdo_obj, 'percentual_limpeza_diario_cumulativo', getattr(rdo_obj, 'percentual_limpeza_cumulativo', None)),
        'limpeza_mecanizada_cumulativa': getattr(rdo_obj, 'limpeza_mecanizada_cumulativa', getattr(rdo_obj, 'limpeza_mecanizada_cumulativa', None)),
        'percentual_limpeza_fina': getattr(rdo_obj, 'percentual_limpeza_fina', None),
        'percentual_limpeza_fina_cumulativo': getattr(rdo_obj, 'percentual_limpeza_fina_cumulativo', None),
        'ensacamento_cumulativo': getattr(rdo_obj, 'ensacamento_cumulativo', None),
        'ensacamento_previsao': getattr(rdo_obj, 'ensacamento_previsao', None),
        'percentual_ensacamento': getattr(rdo_obj, 'percentual_ensacamento', None),
        'icamento': getattr(rdo_obj, 'icamento', None),
        'icamento_cumulativo': getattr(rdo_obj, 'icamento_cumulativo', None),
        'icamento_previsao': getattr(rdo_obj, 'icamento_previsao', None),
        'percentual_icamento': getattr(rdo_obj, 'percentual_icamento', None),
        'cambagem': getattr(rdo_obj, 'cambagem', None),
        'cambagem_cumulativo': getattr(rdo_obj, 'cambagem_cumulativo', None),
        'cambagem_previsao': getattr(rdo_obj, 'cambagem_previsao', None),
        'percentual_cambagem': getattr(rdo_obj, 'percentual_cambagem', None),
        'pob': getattr(rdo_obj, 'pob', None),
        'total_hh_cumulativo_real': getattr(rdo_obj, 'total_hh_cumulativo_real', None),
        'hh_disponivel_cumulativo': getattr(rdo_obj, 'hh_disponivel_cumulativo', None),
        'total_hh_frente_real': getattr(rdo_obj, 'total_hh_frente_real', None),
        'ultimo_status': getattr(rdo_obj, 'ultimo_status', None),
        'percentual_avanco': getattr(rdo_obj, 'percentual_avanco', None),
        'percentual_avanco_cumulativo': getattr(rdo_obj, 'percentual_avanco_cumulativo', None),
        'total_hh_cumulativo_real': getattr(rdo_obj, 'total_hh_cumulativo_real', None),
        'hh_disponivel_cumulativo': getattr(rdo_obj, 'hh_disponivel_cumulativo', None),
        'total_hh_frente_real': getattr(rdo_obj, 'total_hh_frente_real', None),
        'ultimo_status': getattr(rdo_obj, 'ultimo_status', None),
        'po': getattr(rdo_obj, 'po', None) or getattr(rdo_obj, 'contrato_po', None) or (rdo_obj.ordem_servico.po if getattr(rdo_obj, 'ordem_servico', None) else None),
        'exist_pt': rdo_obj.exist_pt,
        'select_turnos': rdo_obj.select_turnos,
        'pt_manha': rdo_obj.pt_manha,
        'pt_tarde': rdo_obj.pt_tarde,
        'pt_noite': rdo_obj.pt_noite,
        'ciente_observacoes_pt': getattr(rdo_obj, 'ciente_observacoes_pt', None),
        'ciente_observacoes_en': getattr(rdo_obj, 'ciente_observacoes_en', None),
        'observacoes_pt': rdo_obj.observacoes_rdo_pt,
        'observacoes_en': getattr(rdo_obj, 'observacoes_rdo_en', None),
        'planejamento_pt': rdo_obj.planejamento_pt,
        'planejamento_en': getattr(rdo_obj, 'planejamento_en', None),
        'comentario_pt': getattr(rdo_obj, 'comentario_pt', None),
        'comentario_en': getattr(rdo_obj, 'comentario_en', None),
        'atividades': atividades_payload,
        
        'tempo_bomba': (None if not getattr(rdo_obj, 'tempo_uso_bomba', None) else round(rdo_obj.tempo_uso_bomba.total_seconds()/3600, 1)),
        'fotos': fotos_urls,
        'fotos_raw': fotos_list,
        'equipe': equipe_list,
        'espaco_confinado': getattr(rdo_obj, 'confinado', None),
        'entrada_confinado': _format_ec_time_value(getattr(rdo_obj, 'entrada_confinado', None)),
        'saida_confinado': _format_ec_time_value(getattr(rdo_obj, 'saida_confinado', None)),
        'entrada_confinado_1': _format_ec_time_value(getattr(rdo_obj, 'entrada_confinado_1', None)),
        'saida_confinado_1': _format_ec_time_value(getattr(rdo_obj, 'saida_confinado_1', None)),
        'entrada_confinado_2': _format_ec_time_value(getattr(rdo_obj, 'entrada_confinado_2', None)),
        'saida_confinado_2': _format_ec_time_value(getattr(rdo_obj, 'saida_confinado_2', None)),
        'entrada_confinado_3': _format_ec_time_value(getattr(rdo_obj, 'entrada_confinado_3', None)),
        'saida_confinado_3': _format_ec_time_value(getattr(rdo_obj, 'saida_confinado_3', None)),
        'entrada_confinado_4': _format_ec_time_value(getattr(rdo_obj, 'entrada_confinado_4', None)),
        'saida_confinado_4': _format_ec_time_value(getattr(rdo_obj, 'saida_confinado_4', None)),
        'entrada_confinado_5': _format_ec_time_value(getattr(rdo_obj, 'entrada_confinado_5', None)),
        'saida_confinado_5': _format_ec_time_value(getattr(rdo_obj, 'saida_confinado_5', None)),
        'entrada_confinado_6': _format_ec_time_value(getattr(rdo_obj, 'entrada_confinado_6', None)),
        'saida_confinado_6': _format_ec_time_value(getattr(rdo_obj, 'saida_confinado_6', None)),
        'ec_times': ec_times,
        'total_atividade_min': getattr(rdo_obj, 'total_atividade_min', aggregates.get('total_atividade_min')),
        'total_confinado_min': getattr(rdo_obj, 'total_confinado_min', aggregates.get('total_confinado_min')),
        'total_abertura_pt_min': getattr(rdo_obj, 'total_abertura_pt_min', aggregates.get('total_abertura_pt_min')),
        'total_atividades_efetivas_min': getattr(rdo_obj, 'total_atividades_efetivas_min', aggregates.get('total_atividades_efetivas_min')),
        'total_atividades_nao_efetivas_fora_min': getattr(rdo_obj, 'total_atividades_nao_efetivas_fora_min', aggregates.get('total_atividades_nao_efetivas_fora_min')),
        'total_n_efetivo_confinado_min': getattr(rdo_obj, 'total_n_efetivo_confinado_min', aggregates.get('total_n_efetivo_confinado_min')),
    }

    try:
        os_services_count, os_services_list = _resolve_os_service_limit(ordem)
        payload['servicos_os'] = os_services_list
        payload['servicos_count'] = os_services_count
        payload['max_tanques_servicos'] = os_services_count if os_services_count > 0 else None
        try:
            total_tanques_os, _os_tank_keys = _resolve_os_tank_progress(ordem)
            payload['total_tanques_os'] = int(total_tanques_os or 0)
        except Exception:
            payload['total_tanques_os'] = 0
    except Exception:
        pass

    try:
        tanques_payload = []
        for t in rdo_obj.tanques.all():
            try:
                def _to_str_or_none(val):
                    try:
                        if val is None:
                            return None
                        return str(val)
                    except Exception:
                        return None

                _id = getattr(t, 'id', None)
                _codigo = getattr(t, 'tanque_codigo', None)
                _nome = getattr(t, 'nome_tanque', None)
                _num_comp = getattr(t, 'numero_compartimentos', getattr(t, 'numero_compartimento', None))
                _tipo = getattr(t, 'tipo_tanque', getattr(t, 'tipo', None))
                _gavetas = getattr(t, 'gavetas', None)
                _pats = getattr(t, 'patamares', getattr(t, 'patamar', None))
                _vol = getattr(t, 'volume_tanque_exec', getattr(t, 'volume', None))

                _pld = getattr(t, 'percentual_limpeza_diario', None)
                _plfd = getattr(t, 'percentual_limpeza_fina_diario', None)
                _plc = getattr(t, 'percentual_limpeza_cumulativo', None)
                _plfc = getattr(t, 'percentual_limpeza_fina_cumulativo', None)

                _sent_raw = None
                for cand in ('sentido_limpeza', 'sentido', 'direcao', 'direcao_limpeza', 'sentido_exec'):
                    try:
                        _val = getattr(t, cand, None)
                        if _val is not None:
                            _sent_raw = _val
                            break
                    except Exception:
                        continue
                if isinstance(_sent_raw, bool):
                    _sent_label = ('Vante para Ré' if _sent_raw else 'Ré para Vante')
                else:
                    _sent_label = _sent_raw

                _bombeio_val = None
                for cand in ('bombeio', 'quantidade_bombeada', 'quantidade_bombeio', 'bombeio_dia', 'bombeado'):
                    try:
                        v = getattr(t, cand, None)
                        if v is not None:
                            _bombeio_val = v
                            break
                    except Exception:
                        continue

                _total_liq = None
                for cand in ('total_liquido', 'total_liquidos', 'total_liquido_dia', 'residuo_liquido'):
                    try:
                        v = getattr(t, cand, None)
                        if v is not None:
                            _total_liq = v
                            break
                    except Exception:
                        continue

                if _pld is not None and _plfd is not None:
                    _percentuais_txt = f"Mec: {int(_pld)}% | Fina: {int(_plfd)}%" if isinstance(_pld, (int,float)) and isinstance(_plfd, (int,float)) else f"{_to_str_or_none(_pld)} | {_to_str_or_none(_plfd)}"
                elif _pld is not None:
                    _percentuais_txt = f"{int(_pld)}%" if isinstance(_pld, (int,float)) else _to_str_or_none(_pld)
                elif _plfd is not None:
                    _percentuais_txt = f"{int(_plfd)}%" if isinstance(_plfd, (int,float)) else _to_str_or_none(_plfd)
                else:
                    _percentuais_txt = None

                item = {
                    'id': _id,
                    'tanque_codigo': _codigo,
                    'codigo': _codigo,
                    'nome_tanque': _nome,
                    'numero_compartimentos': _num_comp,
                    'numero_compartimento': _num_comp,
                    'tipo_tanque': _tipo,
                    'tipo': _tipo,
                    'gavetas': _gavetas,
                    'patamares': _pats,
                    'patamar': _pats,
                    'volume_tanque_exec': _to_str_or_none(_vol),
                    'volume': _to_str_or_none(_vol),
                    'servico_exec': getattr(t, 'servico_exec', None),
                    'metodo_exec': getattr(t, 'metodo_exec', None),
                    'espaco_confinado': getattr(t, 'espaco_confinado', None),
                    'operadores_simultaneos': getattr(t, 'operadores_simultaneos', None),
                    'percentual_limpeza_diario': (_to_str_or_none(_pld) if _pld is not None else None),
                    'percentual_limpeza_fina_diario': (_to_str_or_none(_plfd) if _plfd is not None else None),
                    'percentual_limpeza_cumulativo': _plc,
                    'percentual_limpeza_fina_cumulativo': _plfc,
                    'limpeza_mecanizada_diaria': getattr(t, 'limpeza_mecanizada_diaria', None),
                    'limpeza_mecanizada_cumulativa': getattr(t, 'limpeza_mecanizada_cumulativa', None),
                    'limpeza_fina_diaria': getattr(t, 'limpeza_fina_diaria', None),
                    'limpeza_fina_cumulativa': getattr(t, 'limpeza_fina_cumulativa', None),
                    'percentual_limpeza_fina': getattr(t, 'percentual_limpeza_fina', None),
                    'percentuais': _percentuais_txt,
                    'percentual': _percentuais_txt,
                    'sentido_limpeza': (lambda v: _canonicalize_sentido(v))( _sent_raw ),
                    'sentido_label': (lambda v: ('Vante > Ré' if _canonicalize_sentido(v) == 'vante > ré' else ('Ré > Vante' if _canonicalize_sentido(v) == 'ré > vante' else ('Bombordo > Boreste' if _canonicalize_sentido(v) == 'bombordo > boreste' else ('Boreste < Bombordo' if _canonicalize_sentido(v) == 'boreste < bombordo' else v)) )))(_sent_raw),
                    'sentido': (lambda v: (_canonicalize_sentido(v) or v))(_sent_raw),
                    'tempo_bomba': getattr(t, 'tempo_bomba', None),
                    'ensacamento_dia': getattr(t, 'ensacamento_dia', None),
                    'ensacamento_prev': getattr(t, 'ensacamento_prev', None),
                    'icamento_dia': getattr(t, 'icamento_dia', None),
                    'cambagem_dia': getattr(t, 'cambagem_dia', None),
                    'icamento_prev': getattr(t, 'icamento_prev', None),
                    'cambagem_prev': getattr(t, 'cambagem_prev', None),
                    'previsao_termino': (getattr(t, 'previsao_termino', None).isoformat() if getattr(t, 'previsao_termino', None) else None),
                    'tambores_dia': getattr(t, 'tambores_dia', None),
                    'tambores_cumulativo': getattr(t, 'tambores_cumulativo', None),
                    'tambores_acu': getattr(t, 'tambores_cumulativo', None),
                    'residuos_solidos': getattr(t, 'residuos_solidos', None),
                    'residuos_totais': getattr(t, 'residuos_totais', None),
                    'bombeio': (_bombeio_val if _bombeio_val is not None else None),
                    'total_liquido': (_total_liq if _total_liq is not None else None),
                    'avanco_limpeza': getattr(t, 'avanco_limpeza', None),
                    'avanco_limpeza_fina': getattr(t, 'avanco_limpeza_fina', None),
                    'percentual_avanco': getattr(t, 'percentual_avanco', None),
                    'percentual_avanco_cumulativo': getattr(t, 'percentual_avanco_cumulativo', None),
                    'h2s_ppm': _to_str_or_none(getattr(t, 'h2s_ppm', None)),
                    'lel': _to_str_or_none(getattr(t, 'lel', None)),
                    'co_ppm': _to_str_or_none(getattr(t, 'co_ppm', None)),
                    'o2_percent': _to_str_or_none(getattr(t, 'o2_percent', None)),
                    'ensacamento_cumulativo': getattr(t, 'ensacamento_cumulativo', None),
                    'icamento_cumulativo': getattr(t, 'icamento_cumulativo', None),
                    'cambagem_cumulativo': getattr(t, 'cambagem_cumulativo', None),
                    'percentual_ensacamento': getattr(t, 'percentual_ensacamento', None),
                    'percentual_icamento': getattr(t, 'percentual_icamento', None),
                    'percentual_cambagem': getattr(t, 'percentual_cambagem', None),
                    'total_liquido_acu': getattr(t, 'total_liquido_cumulativo', None),
                    'residuos_solidos_acu': getattr(t, 'residuos_solidos_cumulativo', None),
                    'total_liquido_cumulativo': getattr(t, 'total_liquido_cumulativo', None),
                    'residuos_solidos_cumulativo': getattr(t, 'residuos_solidos_cumulativo', None),
                }

                try:
                    ordem_obj = getattr(rdo_obj, 'ordem_servico', None)
                    code = item.get('tanque_codigo') or item.get('codigo')
                    def _to_int_or_none(v):
                        try:
                            if v in (None, ''):
                                return None
                            return int(v)
                        except Exception:
                            try:
                                return int(float(v))
                            except Exception:
                                return None

                    ens_day = _to_int_or_none(item.get('ensacamento_dia'))
                    ica_day = _to_int_or_none(item.get('icamento_dia'))
                    cam_day = _to_int_or_none(item.get('cambagem_dia'))
                    ens_cum = _to_int_or_none(item.get('ensacamento_cumulativo'))
                    ica_cum = _to_int_or_none(item.get('icamento_cumulativo'))
                    cam_cum = _to_int_or_none(item.get('cambagem_cumulativo'))

                    # Recalcular quando faltando OU quando cumulativo veio inconsistente
                    # (valor menor que o dia atual, sintoma de legado "somente anteriores").
                    need_ens = (item.get('ensacamento_cumulativo') in (None, '')) or (
                        ens_day is not None and ens_day >= 0 and ens_cum is not None and ens_cum < ens_day
                    )
                    need_ica = (item.get('icamento_cumulativo') in (None, '')) or (
                        ica_day is not None and ica_day >= 0 and ica_cum is not None and ica_cum < ica_day
                    )
                    need_cam = (item.get('cambagem_cumulativo') in (None, '')) or (
                        cam_day is not None and cam_day >= 0 and cam_cum is not None and cam_cum < cam_day
                    )
                    need_tamb = item.get('tambores_cumulativo') in (None, '')
                    need_tl = item.get('total_liquido_cumulativo') in (None, '')
                    need_rs = item.get('residuos_solidos_cumulativo') in (None, '')
                    if code and ordem_obj is not None and (need_ens or need_ica or need_cam or need_tamb or need_tl or need_rs):
                        try:
                            from django.db.models import Q

                            qs_sum = RdoTanque.objects.filter(
                                tanque_codigo__iexact=str(code).strip(),
                                rdo__ordem_servico=ordem_obj
                            )
                            if getattr(rdo_obj, 'data', None) and getattr(rdo_obj, 'pk', None):
                                qs_sum = qs_sum.filter(
                                    Q(rdo__data__lt=rdo_obj.data) |
                                    (Q(rdo__data=rdo_obj.data) & Q(rdo__pk__lt=rdo_obj.pk))
                                )
                            elif getattr(rdo_obj, 'data', None):
                                qs_sum = qs_sum.filter(rdo__data__lt=rdo_obj.data)
                            else:
                                qs_sum = qs_sum.exclude(rdo_id=getattr(rdo_obj, 'id', None))

                            agg_t = qs_sum.aggregate(
                                sum_total=Sum('total_liquido'),
                                sum_res=Sum('residuos_solidos'),
                                sum_ens=Sum('ensacamento_dia'),
                                sum_ica=Sum('icamento_dia'),
                                sum_camba=Sum('cambagem_dia'),
                                sum_tamb=Sum('tambores_dia'),
                            )
                            if agg_t:
                                # Sempre atualizar o acumulado líquido do tanque somando
                                # o total dos dias anteriores com o valor do dia atual.
                                try:
                                    prev_total = int(agg_t.get('sum_total') or 0)
                                except Exception:
                                    prev_total = 0
                                try:
                                    cur_total = int(item.get('total_liquido') or 0)
                                except Exception:
                                    cur_total = 0
                                item['total_liquido_cumulativo'] = prev_total + cur_total
                                item['total_liquido_acu'] = item['total_liquido_cumulativo']
                                if need_rs:
                                    try:
                                        from decimal import Decimal as _D
                                        prev_res = _D(str(agg_t.get('sum_res') or 0))
                                    except Exception:
                                        prev_res = 0
                                    try:
                                        from decimal import Decimal as _D
                                        cur_res = _D(str(item.get('residuos_solidos') or 0))
                                    except Exception:
                                        cur_res = 0
                                    item['residuos_solidos_cumulativo'] = prev_res + cur_res
                                    item['residuos_solidos_acu'] = item['residuos_solidos_cumulativo']
                                if need_ens:
                                    try:
                                        prev_ens = int(agg_t.get('sum_ens') or 0)
                                    except Exception:
                                        prev_ens = 0
                                    try:
                                        cur_ens = int(item.get('ensacamento_dia') or 0)
                                    except Exception:
                                        cur_ens = 0
                                    item['ensacamento_cumulativo'] = prev_ens + cur_ens
                                if need_ica:
                                    try:
                                        prev_ica = int(agg_t.get('sum_ica') or 0)
                                    except Exception:
                                        prev_ica = 0
                                    try:
                                        cur_ica = int(item.get('icamento_dia') or 0)
                                    except Exception:
                                        cur_ica = 0
                                    item['icamento_cumulativo'] = prev_ica + cur_ica
                                if need_cam:
                                    try:
                                        prev_camb = int(agg_t.get('sum_camba') or 0)
                                    except Exception:
                                        prev_camb = 0
                                    try:
                                        cur_camb = int(item.get('cambagem_dia') or 0)
                                    except Exception:
                                        cur_camb = 0
                                    item['cambagem_cumulativo'] = prev_camb + cur_camb
                                if need_tamb:
                                    try:
                                        prev_tamb = int(agg_t.get('sum_tamb') or 0)
                                    except Exception:
                                        prev_tamb = 0
                                    try:
                                        cur_tamb = int(item.get('tambores_dia') or 0)
                                    except Exception:
                                        cur_tamb = 0
                                    item['tambores_cumulativo'] = prev_tamb + cur_tamb
                                    item['tambores_acu'] = item['tambores_cumulativo']
                        except Exception:
                            pass
                except Exception:
                    pass

                tanques_payload.append(item)
            except Exception:
                continue
        payload['tanques'] = tanques_payload
        payload['total_tanques'] = len(tanques_payload)
    except Exception:
        payload['tanques'] = []
        payload['total_tanques'] = 0

    active_tank_obj = None
    try:
        tank_q = request.GET.get('tank_id') or request.GET.get('tanque_id') or None
        if not tank_q and payload.get('tanques'):
            try:
                tank_q = str(payload['tanques'][0].get('id'))
            except Exception:
                tank_q = None

        if tank_q:
            try:
                tid = int(tank_q)
            except Exception:
                tid = None

            active = None
            try:
                for x in payload.get('tanques', []):
                    if tid is not None and x.get('id') == tid:
                        active = x
                        break
            except Exception:
                active = None

            if active is None and payload.get('tanques'):
                try:
                    active = payload['tanques'][0]
                except Exception:
                    active = None

            if active:
                payload['active_tanque_id'] = active.get('id')
                try:
                    t_obj = rdo_obj.tanques.filter(pk=active.get('id')).first()
                except Exception:
                    t_obj = None
                active_tank_obj = t_obj
                if t_obj is not None:
                    try:
                        _refresh_tank_metrics_for_display(t_obj)
                    except Exception:
                        pass
                    try:
                        active = dict(active or {})
                    except Exception:
                        active = {}
                    try:
                        _sync_tank_payload_from_instance(active, t_obj)
                    except Exception:
                        pass
                    try:
                        for idx, item in enumerate(payload.get('tanques', []) or []):
                            if isinstance(item, dict) and item.get('id') == getattr(t_obj, 'id', None):
                                payload['tanques'][idx] = _sync_tank_payload_from_instance(dict(item), t_obj)
                                break
                    except Exception:
                        pass
                    try:
                        payload['active_tanque'] = active
                    except Exception:
                        payload['active_tanque'] = None
                    payload['tanque_codigo'] = active.get('tanque_codigo')
                    payload['nome_tanque'] = active.get('nome_tanque')
                    payload['numero_compartimentos'] = active.get('numero_compartimentos')
                    payload['previsao_termino'] = active.get('previsao_termino')
                    payload['rdo_previsao_termino'] = active.get('previsao_termino')
                    payload['previsao_termino_locked'] = bool(active.get('previsao_termino_locked'))
                    try:
                        payload['active_tanque_label'] = _format_active_tank_label(active)
                    except Exception:
                        payload['active_tanque_label'] = ''
                    try: payload['tipo_tanque'] = getattr(t_obj, 'tipo_tanque', None)
                    except Exception: pass
                    try: payload['gavetas'] = getattr(t_obj, 'gavetas', None)
                    except Exception: pass
                    try: payload['patamares'] = getattr(t_obj, 'patamares', None)
                    except Exception: pass
                    try:
                        vtx = getattr(t_obj, 'volume_tanque_exec', None)
                        payload['volume_tanque_exec'] = (str(vtx) if vtx is not None else None)
                    except Exception: pass
                    try:
                        payload['total_liquido_acu'] = getattr(t_obj, 'total_liquido_cumulativo', None)
                    except Exception:
                        pass
                    try:
                        payload['residuos_solidos_acu'] = getattr(t_obj, 'residuos_solidos_cumulativo', None)
                    except Exception:
                        pass
                    try: payload['servico_exec'] = getattr(t_obj, 'servico_exec', None)
                    except Exception: pass
                    try: payload['metodo_exec'] = getattr(t_obj, 'metodo_exec', None)
                    except Exception: pass
                    try: payload['espaco_confinado'] = getattr(t_obj, 'espaco_confinado', None)
                    except Exception: pass
                    try: payload['operadores_simultaneos'] = getattr(t_obj, 'operadores_simultaneos', None)
                    except Exception: pass
                    try:
                        h = getattr(t_obj, 'h2s_ppm', None)
                        payload['H2S_ppm'] = (str(h) if h is not None else None)
                    except Exception: pass
                    try:
                        l = getattr(t_obj, 'lel', None)
                        payload['LEL'] = (str(l) if l is not None else None)
                    except Exception: pass
                    try:
                        c = getattr(t_obj, 'co_ppm', None)
                        payload['CO_ppm'] = (str(c) if c is not None else None)
                    except Exception: pass
                    try:
                        o = getattr(t_obj, 'o2_percent', None)
                        payload['O2_percent'] = (str(o) if o is not None else None)
                    except Exception: pass
                    try: payload['tempo_bomba'] = getattr(t_obj, 'tempo_bomba', None)
                    except Exception: pass
                    try: payload['ensacamento_dia'] = getattr(t_obj, 'ensacamento_dia', None)
                    except Exception: pass
                    try: payload['tambores_dia'] = getattr(t_obj, 'tambores_dia', None)
                    except Exception: pass
                    try:
                        payload['tambores_cumulativo'] = getattr(t_obj, 'tambores_cumulativo', None)
                        payload['tambores_acu'] = getattr(t_obj, 'tambores_cumulativo', None)
                    except Exception:
                        pass
                    try: payload['residuos_solidos'] = getattr(t_obj, 'residuos_solidos', None)
                    except Exception: pass
                    try: payload['residuos_totais'] = getattr(t_obj, 'residuos_totais', None)
                    except Exception: pass
                    try: payload['avanco_limpeza'] = getattr(t_obj, 'avanco_limpeza', None)
                    except Exception: pass
                    try: payload['avanco_limpeza_fina'] = getattr(t_obj, 'avanco_limpeza_fina', None)
                    except Exception: pass
                    try: payload['compartimentos_avanco_json'] = getattr(t_obj, 'compartimentos_avanco_json', None)
                    except Exception: pass
                    try:
                        payload['percentual_limpeza_diario'] = (
                            active.get('percentual_limpeza_diario') if active.get('percentual_limpeza_diario') is not None else getattr(t_obj, 'percentual_limpeza_diario', None)
                        )
                    except Exception: pass
                    try:
                        payload['percentual_limpeza_fina'] = (
                            active.get('percentual_limpeza_fina_diario') if active.get('percentual_limpeza_fina_diario') is not None else getattr(t_obj, 'percentual_limpeza_fina_diario', None)
                        )
                    except Exception: pass
                    try: payload['percentual_limpeza_cumulativo'] = getattr(t_obj, 'percentual_limpeza_cumulativo', None)
                    except Exception: pass
                    try: payload['percentual_limpeza_fina_cumulativo'] = getattr(t_obj, 'percentual_limpeza_fina_cumulativo', None)
                    except Exception: pass
                    try: payload['percentual_ensacamento'] = getattr(t_obj, 'percentual_ensacamento', None)
                    except Exception: pass
                    try: payload['percentual_icamento'] = getattr(t_obj, 'percentual_icamento', None)
                    except Exception: pass
                    try: payload['percentual_cambagem'] = getattr(t_obj, 'percentual_cambagem', None)
                    except Exception: pass
                    try:
                        authoritative_day = _compute_weighted_tank_progress(t_obj, cumulative=False)
                    except Exception:
                        authoritative_day = None
                    try:
                        authoritative_cum = _compute_weighted_tank_progress(t_obj, cumulative=True)
                    except Exception:
                        authoritative_cum = None
                    try:
                        payload['percentual_avanco'] = authoritative_day if authoritative_day is not None else getattr(t_obj, 'percentual_avanco', None)
                    except Exception:
                        pass
                    try:
                        payload['percentual_avanco_cumulativo'] = authoritative_cum if authoritative_cum is not None else getattr(t_obj, 'percentual_avanco_cumulativo', None)
                    except Exception:
                        payload['percentual_avanco_cumulativo'] = payload.get('percentual_avanco_cumulativo')
                    try:
                        if isinstance(payload.get('active_tanque'), dict):
                            payload['active_tanque']['percentual_avanco'] = payload.get('percentual_avanco')
                            payload['active_tanque']['percentual_avanco_cumulativo'] = payload.get('percentual_avanco_cumulativo')
                    except Exception:
                        pass
                    try:
                        sl = getattr(t_obj, 'sentido_limpeza', None)
                        token = _canonicalize_sentido(sl)
                        if token:
                            payload['sentido_limpeza'] = token
                            if token == 'vante > ré':
                                payload['sentido_label'] = 'Vante > Ré'
                                payload['sentido_limpeza_bool'] = True
                            elif token == 'ré > vante':
                                payload['sentido_label'] = 'Ré > Vante'
                                payload['sentido_limpeza_bool'] = False
                            elif token == 'bombordo > boreste':
                                payload['sentido_label'] = 'Bombordo > Boreste'
                                payload['sentido_limpeza_bool'] = None
                            elif token == 'boreste < bombordo':
                                payload['sentido_label'] = 'Boreste < Bombordo'
                                payload['sentido_limpeza_bool'] = None
                        else:
                            payload['sentido_limpeza'] = sl
                            payload['sentido_limpeza_bool'] = None
                    except Exception:
                        pass
                else:
                    try:
                        payload['active_tanque'] = active
                    except Exception:
                        payload['active_tanque'] = None
                    try:
                        payload['active_tanque_label'] = _format_active_tank_label(active)
                    except Exception:
                        payload['active_tanque_label'] = ''
                    payload['tanque_codigo'] = active.get('tanque_codigo')
                    payload['nome_tanque'] = active.get('nome_tanque')
                    payload['numero_compartimentos'] = active.get('numero_compartimentos')
                    payload['previsao_termino'] = active.get('previsao_termino')
                    payload['rdo_previsao_termino'] = active.get('previsao_termino')
                    payload['percentual_limpeza_diario'] = active.get('percentual_limpeza_diario')
                    payload['percentual_limpeza_fina'] = active.get('percentual_limpeza_fina_diario')
                    payload['percentual_limpeza_cumulativo'] = active.get('percentual_limpeza_cumulativo')
                    payload['percentual_limpeza_fina_cumulativo'] = active.get('percentual_limpeza_fina_cumulativo')
                    try:
                        ac = active.get('sentido_limpeza') if isinstance(active, dict) else None
                        token = _canonicalize_sentido(ac)
                        if token:
                            payload['sentido_limpeza'] = token
                            if token == 'vante > ré':
                                payload['sentido_label'] = 'Vante > Ré'
                                payload['sentido_limpeza_bool'] = True
                            elif token == 'ré > vante':
                                payload['sentido_label'] = 'Ré > Vante'
                                payload['sentido_limpeza_bool'] = False
                            elif token == 'bombordo > boreste':
                                payload['sentido_label'] = 'Bombordo > Boreste'
                                payload['sentido_limpeza_bool'] = None
                            elif token == 'boreste < bombordo':
                                payload['sentido_label'] = 'Boreste < Bombordo'
                                payload['sentido_limpeza_bool'] = None
                        else:
                            payload['sentido_limpeza'] = ac
                            payload['sentido_limpeza_bool'] = (True if ac in (True, 'Vante para Ré', 'Vante', 'vante') else (False if ac in (False, 'Ré para Vante', 're') else None))
                    except Exception:
                        payload['sentido_limpeza'] = active.get('sentido_limpeza')
                        payload['sentido_limpeza_bool'] = (True if active.get('sentido_limpeza') in (True, 'Vante para Ré', 'Vante', 'vante') else (False if active.get('sentido_limpeza') in (False, 'Ré para Vante', 're') else None))
                    try:
                        payload['ensacamento_cumulativo'] = active.get('ensacamento_cumulativo')
                        payload['icamento_cumulativo'] = active.get('icamento_cumulativo')
                        payload['cambagem_cumulativo'] = active.get('cambagem_cumulativo')
                        payload['tambores_cumulativo'] = active.get('tambores_cumulativo') or active.get('tambores_acu')
                        payload['tambores_acu'] = active.get('tambores_acu') or active.get('tambores_cumulativo')
                        payload['total_liquido_acu'] = active.get('total_liquido_acu') or active.get('total_liquido_cumulativo')
                        payload['residuos_solidos_acu'] = active.get('residuos_solidos_acu') or active.get('residuos_solidos_cumulativo')
                    except Exception:
                        pass
                    payload['sentido_limpeza_bool'] = (True if active.get('sentido_limpeza') in (True, 'Vante para Ré', 'Vante', 'vante') else (False if active.get('sentido_limpeza') in (False, 'Ré para Vante', 're') else None))

                try:
                    enriched = dict(active) if isinstance(active, dict) else {}
                    fallback_keys = [
                        'ensacamento_prev', 'ensacamento_previsao', 'ensacamento',
                        'ensacamento_cumulativo',
                        'icamento', 'icamento_previsao', 'icamento_cumulativo',
                        'cambagem', 'cambagem_previsao', 'cambagem_cumulativo',
                        'tambores_dia', 'tambores_cumulativo', 'tambores_acu',
                        'espaco_confinado', 'operadores_simultaneos',
                        'percentual_ensacamento', 'percentual_icamento', 'percentual_cambagem',
                        'percentual_avanco', 'percentual_avanco_cumulativo',
                        'percentual_limpeza_diario', 'percentual_limpeza_fina_diario',
                        'percentual_limpeza_cumulativo', 'percentual_limpeza_fina_cumulativo',
                        'percentuais', 'percentual',
                        'compartimentos_avanco_json',
                        'total_liquido_acu', 'residuos_solidos_acu',
                        'total_liquido_cumulativo', 'residuos_solidos_cumulativo',
                        'previsao_termino',
                    ]
                    for k in fallback_keys:
                        if k not in enriched:
                            try:
                                enriched[k] = (active.get(k) if isinstance(active, dict) else None) or payload.get(k)
                            except Exception:
                                enriched[k] = payload.get(k)

                    if 'nome_tanque' not in enriched:
                        enriched['nome_tanque'] = active.get('nome_tanque') or payload.get('nome_tanque')
                    if 'tanque_codigo' not in enriched:
                        enriched['tanque_codigo'] = active.get('tanque_codigo') or payload.get('tanque_codigo')

                    try:
                        if 'limpeza_mecanizada_diaria' not in enriched:
                            enriched['limpeza_mecanizada_diaria'] = (
                                (active.get('limpeza_mecanizada_diaria') if isinstance(active, dict) else None)
                                or (active.get('percentual_limpeza_diario') if isinstance(active, dict) else None)
                                or payload.get('percentual_limpeza_diario')
                                or payload.get('limpeza_mecanizada_diaria')
                            )
                    except Exception:
                        enriched['limpeza_mecanizada_diaria'] = payload.get('percentual_limpeza_diario')

                    try:
                        if 'limpeza_mecanizada_cumulativa' not in enriched:
                            enriched['limpeza_mecanizada_cumulativa'] = (
                                (active.get('limpeza_mecanizada_cumulativa') if isinstance(active, dict) else None)
                                or (active.get('percentual_limpeza_cumulativo') if isinstance(active, dict) else None)
                                or payload.get('percentual_limpeza_cumulativo')
                            )
                    except Exception:
                        enriched['limpeza_mecanizada_cumulativa'] = payload.get('percentual_limpeza_cumulativo')

                    payload['active_tanque'] = enriched
                except Exception:
                    try:
                        payload['active_tanque'] = active
                    except Exception:
                        pass
    except Exception:
        pass

    try:
        if not payload.get('total_hh_frente_real') and hasattr(rdo_obj, 'compute_total_hh_frente_real'):
            try:
                hh_diario = rdo_obj.compute_total_hh_frente_real()
                if hh_diario:
                    payload['total_hh_frente_real'] = hh_diario
            except Exception:
                pass

        if not payload.get('total_hh_cumulativo_real') and hasattr(rdo_obj, 'compute_total_hh_cumulativo_real'):
            try:
                hh_cumulativo = rdo_obj.compute_total_hh_cumulativo_real()
                if hh_cumulativo:
                    payload['total_hh_cumulativo_real'] = hh_cumulativo
            except Exception:
                pass

        if not payload.get('hh_disponivel_cumulativo') and ordem is not None:
            try:
                if hasattr(ordem, 'calc_hh_disponivel_cumulativo_time'):
                    hh_disponivel = ordem.calc_hh_disponivel_cumulativo_time()
                    if hh_disponivel:
                        payload['hh_disponivel_cumulativo'] = hh_disponivel
                if not payload.get('hh_disponivel_cumulativo') and hasattr(ordem, 'calc_hh_disponivel_cumulativo'):
                    td = ordem.calc_hh_disponivel_cumulativo()
                    if td:
                        total_seconds = int(td.total_seconds())
                        hours = total_seconds // 3600
                        minutes = (total_seconds % 3600) // 60
                        hours_mod = hours % 24
                        payload['hh_disponivel_cumulativo'] = dt_time(hour=hours_mod, minute=minutes)
            except Exception:
                pass
    except Exception:
        pass

    try:
        prev_compartimentos = []
        if active_tank_obj is None:
            try:
                active_tank_obj = rdo_obj.tanques.order_by('id').first()
            except Exception:
                active_tank_obj = None
        if active_tank_obj is not None and hasattr(active_tank_obj, 'get_previous_compartimentos_payload'):
            try:
                prev_compartimentos = active_tank_obj.get_previous_compartimentos_payload() or []
            except Exception:
                prev_compartimentos = []
        payload['previous_compartimentos'] = prev_compartimentos
        try:
            payload['previous_compartimentos_json'] = json.dumps(prev_compartimentos, ensure_ascii=False)
        except Exception:
            payload['previous_compartimentos_json'] = '[]'
    except Exception:
        logging.getLogger(__name__).exception('Falha ao calcular previous_compartimentos para rdo_detail')
        payload['previous_compartimentos'] = []
        payload['previous_compartimentos_json'] = '[]'

    try:
        prev_payload = payload.get('previous_compartimentos') or []
        if not isinstance(prev_payload, (list, tuple)):
            prev_payload = []
        payload['previous_compartimentos_json'] = _json.dumps(list(prev_payload), ensure_ascii=False)
    except Exception:
        payload['previous_compartimentos_json'] = '[]'

    try:
        from datetime import time as _dt_time
        def _time_to_hhmm(v):
            try:
                if v is None:
                    return None
                if isinstance(v, _dt_time):
                    return v.strftime('%H:%M')
                s = str(v)
                if not s:
                    return None
                if ':' in s:
                    parts = s.split(':')
                    try:
                        h = int(parts[0]); m = int(parts[1]) if len(parts) > 1 else 0
                        return f"{h:02d}:{m:02d}"
                    except Exception:
                        return s
                return s
            except Exception:
                return None

        payload['total_hh_cumulativo_real_hhmm'] = _time_to_hhmm(payload.get('total_hh_cumulativo_real'))
        payload['hh_disponivel_cumulativo_hhmm'] = _time_to_hhmm(payload.get('hh_disponivel_cumulativo'))
        payload['total_hh_frente_real_hhmm'] = _time_to_hhmm(payload.get('total_hh_frente_real'))
    except Exception:
        pass

    try:
        if request.GET.get('render') in ('editor', 'html'):
            from django.template.loader import render_to_string
            logger = logging.getLogger(__name__)
            try:
                tank_q = request.GET.get('tank_id') or request.GET.get('tanque_id') or None
                logger.debug('rdo_detail(render=editor) rdo_id=%s tank_q=%s tanques_count=%s active_tanque_id=%s',
                             getattr(rdo_obj, 'id', None),
                             tank_q,
                             len(payload.get('tanques', [])),
                             payload.get('active_tanque_id', None))
            except Exception:
                logger.exception('Falha ao montar debug log para rdo_detail(render=editor)')
            try:
                try:
                    from types import SimpleNamespace
                    db_funcoes_qs = Funcao.objects.order_by('nome').all() if hasattr(Funcao, 'objects') else []
                    db_funcoes_names = [getattr(f, 'nome', None) for f in db_funcoes_qs]
                    const_funcoes = [t[0] for t in getattr(OrdemServico, 'FUNCOES', [])]
                    const_only = [SimpleNamespace(nome=name) for name in const_funcoes if name not in db_funcoes_names]
                    db_funcoes_objs = [SimpleNamespace(nome=getattr(f, 'nome', None)) for f in db_funcoes_qs]
                    get_funcoes_ctx = const_only + db_funcoes_objs
                except Exception:
                    try:
                        get_funcoes_ctx = Funcao.objects.order_by('nome').all() if hasattr(Funcao, 'objects') else []
                    except Exception:
                        get_funcoes_ctx = []

                try:
                    payload.setdefault('active_tanque', None)
                except Exception:
                    payload['active_tanque'] = None

                def _normalize_tank_payload_fields(target):
                    if not isinstance(target, dict):
                        return
                    mirror_keys = (
                        ('total_liquido_cumulativo', 'total_liquido_acu'),
                        ('residuos_solidos_cumulativo', 'residuos_solidos_acu'),
                        ('tambores_cumulativo', 'tambores_acu'),
                    )
                    for key_a, key_b in mirror_keys:
                        val_a = target.get(key_a)
                        val_b = target.get(key_b)
                        if val_a in (None, '') and val_b not in (None, ''):
                            target[key_a] = val_b
                            val_a = val_b
                        if val_b in (None, '') and val_a not in (None, ''):
                            target[key_b] = val_a

                    for key in (
                        'ensacamento_cumulativo',
                        'icamento_cumulativo',
                        'cambagem_cumulativo',
                        'total_liquido_cumulativo',
                        'total_liquido_acu',
                        'residuos_solidos_cumulativo',
                        'residuos_solidos_acu',
                        'tambores_cumulativo',
                        'tambores_acu',
                    ):
                        target.setdefault(key, None)
                    try:
                        previsao = target.get('previsao_termino')
                        if hasattr(previsao, 'isoformat') and previsao:
                            target['previsao_termino'] = previsao.isoformat()
                    except Exception:
                        pass

                try:
                    _normalize_tank_payload_fields(payload)
                    tanques = payload.get('tanques') or []
                    for t in tanques:
                        _normalize_tank_payload_fields(t)
                    _normalize_tank_payload_fields(payload.get('active_tanque'))
                except Exception:
                    logger = logging.getLogger(__name__)
                    logger.debug('Falha ao normalizar campos de tanques para template', exc_info=True)

                html = render_to_string('rdo_editor_fragment.html', {
                    'r': payload,
                    'atividades_choices': getattr(RDO, 'ATIVIDADES_CHOICES', []),
                    'servico_choices': getattr(OrdemServico, 'SERVICO_CHOICES', []),
                    'metodo_choices': [ ('Manual','Manual'), ('Mecanizada','Mecanizada'), ('Robotizada','Robotizada') ],
                    'get_pessoas': Pessoa.objects.order_by('nome').all() if hasattr(Pessoa, 'objects') else [],
                    'get_funcoes': get_funcoes_ctx,
                }, request=request)
                return JsonResponse({
                    'success': True,
                    'html': html,
                    'previsao_termino_locked': bool(payload.get('previsao_termino_locked')),
                    'previsao_termino': payload.get('previsao_termino'),
                })
            except Exception:
                logger.exception('Falha renderizando fragmento do editor')
                pass
    except Exception:
        pass

    return JsonResponse({
        'success': True,
        'rdo': payload
    })

@login_required(login_url='/login/')
@require_GET
def rdo_os_rdos(request, os_id):
    try:
        os_obj = OrdemServico.objects.select_related('supervisor').get(pk=os_id)
    except OrdemServico.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'OS não encontrada.'}, status=404)

    try:
        is_supervisor_user = (hasattr(request, 'user') and request.user.is_authenticated and request.user.groups.filter(name='Supervisor').exists())
        if is_supervisor_user:
            sup = getattr(os_obj, 'supervisor', None)
            if sup is None or sup != request.user:
                try:
                    from django.conf import settings as _settings
                    allowed_override = False
                    if getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False):
                        allowed_override = True
                    else:
                        try:
                            grp_names = getattr(_settings, 'RDO_DETAIL_OVERRIDE_GROUPS', []) or []
                            for g in grp_names:
                                if request.user.groups.filter(name=g).exists():
                                    allowed_override = True
                                    break
                        except Exception:
                            allowed_override = False
                    if not allowed_override:
                        return JsonResponse({'success': False, 'error': 'OS não encontrada.'}, status=404)
                except Exception:
                    return JsonResponse({'success': False, 'error': 'OS não encontrada.'}, status=404)
    except Exception:
        return JsonResponse({'success': False, 'error': 'OS não encontrada.'}, status=404)

    try:
        rdo_qs = list(RDO.objects.filter(ordem_servico=os_obj))
    except Exception:
        rdo_qs = []

    def _rdo_sort_key(obj):
        raw = getattr(obj, 'rdo', None)
        num = None
        try:
            num = int(str(raw).strip())
        except Exception:
            num = None
        dt_val = getattr(obj, 'data', None) or getattr(obj, 'data_inicio', None)
        try:
            if not dt_val:
                dt_val = datetime.min.date()
        except Exception:
            dt_val = dt_val or None
        return (0 if num is not None else 1, num or 0, dt_val or datetime.min.date(), getattr(obj, 'id', 0) or 0)

    try:
        rdo_qs.sort(key=_rdo_sort_key)
    except Exception:
        pass

    rdos_payload = []
    for r in rdo_qs:
        try:
            dt_val = getattr(r, 'data', None) or getattr(r, 'data_inicio', None)
            dt_str = dt_val.isoformat() if hasattr(dt_val, 'isoformat') else (str(dt_val) if dt_val else '')
        except Exception:
            dt_str = ''
        rdos_payload.append({
            'id': getattr(r, 'id', None),
            'rdo': getattr(r, 'rdo', None),
            'data': dt_str,
        })

    return JsonResponse({
        'success': True,
        'os': {'id': getattr(os_obj, 'id', None), 'numero_os': getattr(os_obj, 'numero_os', None)},
        'rdos': rdos_payload,
    })


def salvar_supervisor(request):
    read_only_response = _guard_read_only_json(request, 'salvar RDO')
    if read_only_response is not None:
        return read_only_response

    import json
    import logging
    from decimal import Decimal, ROUND_HALF_UP
    from django.db import transaction

    logger = logging.getLogger(__name__)

    body_json = {}
    try:
        ctype = (request.META.get('CONTENT_TYPE') or request.META.get('HTTP_CONTENT_TYPE') or '')
        if (not request.POST) or ('application/json' in ctype.lower()):
            try:
                raw = request.body.decode('utf-8') if hasattr(request, 'body') else ''
                body_json = json.loads(raw) if raw else {}
            except Exception:
                body_json = {}
    except Exception:
        body_json = {}

    def get_in(name, default=None):
        if hasattr(request, 'POST') and name in request.POST:
            return request.POST.get(name)
        try:
            return body_json.get(name, default) if isinstance(body_json, dict) else default
        except Exception:
            return default

    def get_list(name):
        try:
            if hasattr(request, 'POST') and hasattr(request.POST, 'getlist'):
                vals = request.POST.getlist(name)
                if vals:
                    return vals
        except Exception:
            pass
        try:
            if isinstance(body_json, dict):
                v = body_json.get(name)
                if isinstance(v, list):
                    return v
        except Exception:
            pass
        return []

    def _clean(val):
        return val if val not in (None, '') else None

    def _to_int(v):
        try:
            if v is None or v == '':
                return None
            return int(float(v))
        except Exception:
            return None

    def _to_dec_2(v):
        try:
            if v is None or v == '':
                return None
            d = Decimal(str(v))
            return d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except Exception:
            return None

    def _norm_number_like(v):
        try:
            if v is None:
                return None
            s = str(v).strip()
            if s == '':
                return None
            if s.endswith('%'):
                s = s[:-1].strip()
            s = s.replace(',', '.')
            if s == '':
                return None
            return s
        except Exception:
            return None

    safe_body_snip = ''
    try:
        if hasattr(request, 'body') and request.body:
            try:
                safe_body_snip = request.body.decode('utf-8')[:400]
            except Exception:
                safe_body_snip = ''
        logger.info('salvar_supervisor: CONTENT_TYPE=%s POST_keys=%s JSON_keys=%s body_snip=%s',
                    ctype,
                    (list(request.POST.keys()) if hasattr(request, 'POST') else None),
                    (list(body_json.keys()) if isinstance(body_json, dict) else None),
                    safe_body_snip)
    except Exception:
        pass

    CANONICAL_MAP = {
        'limpeza_mecanizada_diaria': [
            'limpeza_mecanizada_diaria',
            'sup-limp',
            'percentual_limpeza_diario',
            'avanco_limpeza',
        ],
        'limpeza_mecanizada_cumulativa': [
            'limpeza_mecanizada_cumulativa',
            'sup-limp-acu',
            'limpeza_acu',
            'percentual_limpeza_cumulativo',
        ],
        'percentual_limpeza_fina': [
            'percentual_limpeza_fina',
            'sup-limp-fina',
            'avanco_limpeza_fina',
            'percentual_limpeza_fina_diario',
        ],
        'percentual_limpeza_fina_cumulativo': [
            'percentual_limpeza_fina_cumulativo',
            'sup-limp-fina-acu',
            'limpeza_fina_acu',
        ],
    }

    rdo_id = _clean(get_in('rdo_id') or get_in('id') or get_in('rdo'))
    if not rdo_id:
        return JsonResponse({'success': False, 'error': 'rdo_id não informado.'}, status=400)
    try:
        rdo_obj = RDO.objects.select_related('ordem_servico').get(pk=int(rdo_id))
    except Exception:
        return JsonResponse({'success': False, 'error': 'RDO não encontrado.'}, status=404)

    tank_id_raw = _clean(get_in('tanque_id') or get_in('tank_id') or get_in('tanqueId'))
    try:
        tank_id = int(tank_id_raw) if tank_id_raw is not None else None
    except Exception:
        tank_id = None

    if tank_id is None:
        try:
            tank_code_fallback = _clean(get_in('tanque_id_text') or get_in('tanque_codigo') or get_in('tanque_code') or get_in('tanque'))
            if tank_code_fallback:
                try:
                    tmatch = rdo_obj.tanques.filter(tanque_codigo__iexact=str(tank_code_fallback).strip()).order_by('-id').first()
                    if tmatch:
                        tank_id = tmatch.id
                except Exception:
                    pass
            if tank_id is None:
                try:
                    if hasattr(rdo_obj, 'tanques') and rdo_obj.tanques.count() == 1:
                        tank_id = rdo_obj.tanques.first().id
                except Exception:
                    pass
        except Exception:
            pass

    def pick_cleaning_values():
        vals = {}
        for canon, names in CANONICAL_MAP.items():
            raw = None
            for nm in names:
                raw_candidate = _clean(get_in(nm))
                if raw_candidate is not None:
                    raw = _norm_number_like(raw_candidate)
                    if raw is None:
                        raw = _clean(raw_candidate)
                    break
            vals[canon] = raw
        return vals

    cleaning_raw = pick_cleaning_values()

    def _apply_cleaning_to_rdo(lm_d_val, lm_c_val, pf_d_val, pf_c_val):
        try:
            changed = False
            if lm_d_val is not None and hasattr(rdo_obj, 'limpeza_mecanizada_diaria'):
                rdo_obj.limpeza_mecanizada_diaria = lm_d_val
                changed = True
            if pf_d_val is not None and hasattr(rdo_obj, 'percentual_limpeza_fina'):
                rdo_obj.percentual_limpeza_fina = pf_d_val
                changed = True
            # NOTA: não atribuir valores cumulativos em `RDO` aqui; origem única será `RdoTanque`.
            if changed:
                try:
                    _safe_save_global(rdo_obj)
                except Exception:
                    rdo_obj.save()
        except Exception:
            logging.getLogger(__name__).exception('Falha ao aplicar valores de limpeza no RDO %s', getattr(rdo_obj, 'id', None))

    if tank_id is not None:
        try:
            tank = RdoTanque.objects.get(pk=tank_id)
        except RdoTanque.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Tanque não encontrado.'}, status=404)
        try:
            if getattr(tank, 'rdo_id', None) != getattr(rdo_obj, 'id', None):
                logger.warning('salvar_supervisor: tank_id=%s não pertence ao rdo_id=%s', tank_id, rdo_obj.id)
        except Exception:
            pass

        

        ens_prev = _to_int(get_in('ensacamento_prev'))
        ica_prev = _to_int(get_in('icamento_prev'))
        cam_prev = _to_int(get_in('cambagem_prev'))
        previsao_tank = _parse_iso_date_value(get_in('previsao_termino') or get_in('rdo_previsao_termino'))
        _apply_tank_prediction_once(tank, 'ensacamento_prev', ens_prev)
        _apply_tank_prediction_once(tank, 'icamento_prev', ica_prev)
        _apply_tank_prediction_once(tank, 'cambagem_prev', cam_prev)
        _apply_tank_prediction_once(tank, 'previsao_termino', previsao_tank)

        n_comp_val = None
        try:
            n_comp_val = _to_int(get_in('numero_compartimentos') or get_in('numero_compartimento'))
            if n_comp_val is not None:
                _set_tank_shared_field_value(tank, 'numero_compartimentos', n_comp_val)
        except Exception:
            pass

        comp_validation = None
        try:
            n_total = n_comp_val
            if n_total is None:
                try:
                    n_total = int(getattr(tank, 'numero_compartimentos', None) or 0)
                except Exception:
                    n_total = None
            if not n_total:
                try:
                    n_total = int(getattr(rdo_obj, 'numero_compartimentos', None) or 0)
                except Exception:
                    n_total = None

            comp_validation = _validate_compartimentos_payload_for_tank(
                tank,
                get_in,
                get_list=get_list,
                total_compartimentos=n_total,
            )
        except Exception:
            comp_validation = None

        if comp_validation is not None:
            if not comp_validation.get('is_valid'):
                return JsonResponse({
                    'success': False,
                    'error': (comp_validation.get('errors') or [{}])[0].get('message') or 'Avanço inválido para o compartimento.',
                    'errors': comp_validation.get('errors') or [],
                }, status=400)
            try:
                tank.compartimentos_avanco_json = comp_validation.get('json')
                tank.compute_limpeza_from_compartimentos()
            except Exception:
                logger.exception('Falha ao aplicar avanço por compartimento no tanque %s', tank_id)

        lm_d = _to_dec_2(cleaning_raw.get('limpeza_mecanizada_diaria'))
        lm_c = _to_int(cleaning_raw.get('limpeza_mecanizada_cumulativa'))
        pf_d = _to_int(cleaning_raw.get('percentual_limpeza_fina'))
        pf_c = _to_int(cleaning_raw.get('percentual_limpeza_fina_cumulativo'))

        def _normalize_prev_cumulativo(day_val, cum_val, legacy_total_val):
            if cum_val is not None:
                return cum_val
            if legacy_total_val is None:
                return None
            try:
                return int(legacy_total_val)
            except Exception:
                return legacy_total_val

        ens_day = _to_int(get_in('ensacamento_dia') or cleaning_raw.get('ensacamento_dia') or getattr(tank, 'ensacamento_dia', None))
        ic_day = _to_int(get_in('icamento_dia') or cleaning_raw.get('icamento_dia') or getattr(tank, 'icamento_dia', None))
        camb_day = _to_int(get_in('cambagem_dia') or cleaning_raw.get('cambagem_dia') or getattr(tank, 'cambagem_dia', None))
        tamb_day = _to_int(get_in('tambores_dia') or cleaning_raw.get('tambores_dia') or getattr(tank, 'tambores_dia', None))

        ens_cum_direct = _to_int(get_in('ensacamento_cumulativo') or cleaning_raw.get('ensacamento_cumulativo'))
        ic_cum_direct = _to_int(get_in('icamento_cumulativo') or cleaning_raw.get('icamento_cumulativo'))
        camb_cum_direct = _to_int(get_in('cambagem_cumulativo') or cleaning_raw.get('cambagem_cumulativo'))
        ens_cum_legacy = _to_int(get_in('ensacamento_acu'))
        ic_cum_legacy = _to_int(get_in('icamento_acu'))
        camb_cum_legacy = _to_int(get_in('cambagem_acu'))
        tamb_cum_direct = _to_int(get_in('tambores_cumulativo') or cleaning_raw.get('tambores_cumulativo'))
        tamb_cum_legacy = _to_int(get_in('tambores_acu'))

        ensac_cum = _normalize_prev_cumulativo(ens_day, ens_cum_direct, ens_cum_legacy)
        ic_cum = _normalize_prev_cumulativo(ic_day, ic_cum_direct, ic_cum_legacy)
        camb_cum = _normalize_prev_cumulativo(camb_day, camb_cum_direct, camb_cum_legacy)
        tamb_cum = _normalize_prev_cumulativo(tamb_day, tamb_cum_direct, tamb_cum_legacy)
        tlq_cum = _to_int(get_in('total_liquido_cumulativo') or get_in('total_liquido_acu') or cleaning_raw.get('total_liquido_cumulativo') or cleaning_raw.get('total_liquido_acu'))
        rss_cum = _to_dec_2(get_in('residuos_solidos_cumulativo') or get_in('residuos_solidos_acu') or cleaning_raw.get('residuos_solidos_cumulativo') or cleaning_raw.get('residuos_solidos_acu'))

        # adiar aplicação/salvamento dos valores de limpeza no RDO
        # até que o RdoTanque tenha sido salvo para evitar validação prematura

        if lm_d is not None:
            tank.limpeza_mecanizada_diaria = lm_d
        if lm_c is not None:
            tank.limpeza_mecanizada_cumulativa = lm_c
        if pf_d is not None:
            tank.percentual_limpeza_fina = pf_d
        if pf_c is not None:
            tank.percentual_limpeza_fina_cumulativo = pf_c

        if ensac_cum is not None:
            tank.ensacamento_cumulativo = ensac_cum
        if ic_cum is not None:
            tank.icamento_cumulativo = ic_cum
        if camb_cum is not None:
            tank.cambagem_cumulativo = camb_cum
        if tamb_cum is not None and hasattr(tank, 'tambores_cumulativo'):
            tank.tambores_cumulativo = tamb_cum
        if tlq_cum is not None and hasattr(tank, 'total_liquido_cumulativo'):
            tank.total_liquido_cumulativo = tlq_cum
        if rss_cum is not None and hasattr(tank, 'residuos_solidos_cumulativo'):
            tank.residuos_solidos_cumulativo = rss_cum

        tank_code_in = _clean(get_in('tanque_codigo') or get_in('tanque_code'))
        if tank_code_in is not None:
            tank.tanque_codigo = tank_code_in

        try:
            sentido_raw_tank = _clean(get_in('sentido') or get_in('sentido_limpeza'))
        except Exception:
            sentido_raw_tank = None
        if sentido_raw_tank is not None:
            try:
                try:
                    token_tank = _canonicalize_sentido(sentido_raw_tank)
                except Exception:
                    token_tank = None
                if token_tank is not None and hasattr(tank, 'sentido_limpeza'):
                    tank.sentido_limpeza = token_tank
                else:
                    if hasattr(tank, 'sentido_limpeza'):
                        try:
                            tank.sentido_limpeza = str(sentido_raw_tank)
                        except Exception:
                            pass
            except Exception:
                pass

        try:
            with transaction.atomic():
                tank.save()
        except Exception:
            logger.exception('Falha ao salvar RdoTanque %s', tank_id)
            return JsonResponse({'success': False, 'error': 'Falha ao salvar tanque.'}, status=500)

        try:
            if hasattr(tank, 'recompute_metrics') and callable(tank.recompute_metrics):
                tank.recompute_metrics(only_when_missing=False)
                with transaction.atomic():
                    tank.save()
        except Exception:
            logger.exception('Falha ao recomputar cumulativos por tanque (id=%s)', getattr(tank, 'id', None))

        try:
            _apply_cleaning_to_rdo(lm_d, lm_c, pf_d, pf_c)
        except Exception:
            logger.exception('Erro aplicando limpeza no RDO apos salvar tanque (id=%s)', getattr(tank, 'id', None))

        tank_payload = {
            'id': tank.id,
            'tanque_codigo': getattr(tank, 'tanque_codigo', None),
            'limpeza_mecanizada_diaria': getattr(tank, 'limpeza_mecanizada_diaria', None),
            'limpeza_mecanizada_cumulativa': getattr(tank, 'limpeza_mecanizada_cumulativa', None),
            'percentual_limpeza_fina': getattr(tank, 'percentual_limpeza_fina', None),
            'percentual_limpeza_fina_cumulativo': getattr(tank, 'percentual_limpeza_fina_cumulativo', None),
            'ensacamento_prev': getattr(tank, 'ensacamento_prev', None),
            'icamento_prev': getattr(tank, 'icamento_prev', None),
            'cambagem_prev': getattr(tank, 'cambagem_prev', None),
            'previsao_termino': (getattr(tank, 'previsao_termino', None).isoformat() if getattr(tank, 'previsao_termino', None) else None),
            'tambores_cumulativo': getattr(tank, 'tambores_cumulativo', None),
            'tambores_acu': getattr(tank, 'tambores_cumulativo', None),
            'total_liquido_acu': getattr(tank, 'total_liquido_cumulativo', None),
            'residuos_solidos_acu': getattr(tank, 'residuos_solidos_cumulativo', None),
            'compartimentos_avanco_json': getattr(tank, 'compartimentos_avanco_json', None),
        }
        return JsonResponse({'success': True, 'updated': {'rdo_id': rdo_obj.id, 'tank_id': tank.id}, 'tank': tank_payload})

    if not any(v is not None and str(v) != '' for v in cleaning_raw.values()):
        return JsonResponse({'success': False, 'error': 'Nenhum campo de limpeza informado para replicação.'}, status=400)

    lm_d = _to_dec_2(cleaning_raw.get('limpeza_mecanizada_diaria'))
    lm_c = _to_int(cleaning_raw.get('limpeza_mecanizada_cumulativa'))
    pf_d = _to_int(cleaning_raw.get('percentual_limpeza_fina'))
    pf_c = _to_int(cleaning_raw.get('percentual_limpeza_fina_cumulativo'))

    ensac_cum = _to_int(cleaning_raw.get('ensacamento_cumulativo') or cleaning_raw.get('ensacamento_acu'))
    ic_cum = _to_int(cleaning_raw.get('icamento_cumulativo') or cleaning_raw.get('icamento_acu'))
    camb_cum = _to_int(cleaning_raw.get('cambagem_cumulativo') or cleaning_raw.get('cambagem_acu'))
    tamb_cum = _to_int(cleaning_raw.get('tambores_cumulativo') or cleaning_raw.get('tambores_acu'))
    tlq_cum = _to_int(cleaning_raw.get('total_liquido_cumulativo') or cleaning_raw.get('total_liquido_acu'))
    rss_cum = _to_dec_2(cleaning_raw.get('residuos_solidos_cumulativo') or cleaning_raw.get('residuos_solidos_acu'))

    # adiar aplicação/salvamento dos valores de limpeza no RDO
    # até que todos os RdoTanque(s) tenham sido salvos

    updated = 0
    try:
        with transaction.atomic():
            for t in rdo_obj.tanques.all():
                if lm_d is not None:
                    t.limpeza_mecanizada_diaria = lm_d
                if lm_c is not None:
                    t.limpeza_mecanizada_cumulativa = lm_c
                if pf_d is not None:
                    t.percentual_limpeza_fina = pf_d
                if pf_c is not None:
                    t.percentual_limpeza_fina_cumulativo = pf_c
                if ensac_cum is not None:
                    t.ensacamento_cumulativo = ensac_cum
                if ic_cum is not None:
                    t.icamento_cumulativo = ic_cum
                if camb_cum is not None:
                    t.cambagem_cumulativo = camb_cum
                if tamb_cum is not None and hasattr(t, 'tambores_cumulativo'):
                    t.tambores_cumulativo = tamb_cum
                if tlq_cum is not None and hasattr(t, 'total_liquido_cumulativo'):
                    t.total_liquido_cumulativo = tlq_cum
                if rss_cum is not None and hasattr(t, 'residuos_solidos_cumulativo'):
                    t.residuos_solidos_cumulativo = rss_cum
                t.save()
            if (lm_c is None) or (pf_c is None):
                for t in rdo_obj.tanques.all():
                    try:
                        t.recompute_metrics(only_when_missing=False)
                        t.save()
                    except Exception:
                        logger.exception('Falha ao recomputar cumulativos por tanque na replicação (id=%s)', getattr(t,'id',None))
                updated = rdo_obj.tanques.count()
                updated += 1
    except Exception:
        logger.exception('Falha ao replicar campos de limpeza para tanques do RDO %s', rdo_obj.id)
        return JsonResponse({'success': False, 'error': 'Falha ao replicar para tanques.'}, status=500)

    # Após salvar/replicar tanques, aplicar/salvar valores de limpeza no RDO
    try:
        _apply_cleaning_to_rdo(lm_d, lm_c, pf_d, pf_c)
    except Exception:
        logger.exception('Erro aplicando limpeza no RDO apos replicacao (rdo_id=%s)', getattr(rdo_obj, 'id', None))

    return JsonResponse({'success': True, 'updated': {'rdo_id': rdo_obj.id, 'count': updated}})

@require_POST
def debug_parse_supervisor(request):
    try:
        if not getattr(settings, 'DEBUG', False):
            return JsonResponse({'success': False, 'error': 'Not available'}, status=404)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Not available'}, status=404)

    body_json = {}
    try:
        ctype = (request.META.get('CONTENT_TYPE') or request.META.get('HTTP_CONTENT_TYPE') or '')
        if (not request.POST) or ('application/json' in ctype.lower()):
            try:
                raw = request.body.decode('utf-8') if hasattr(request, 'body') else ''
                body_json = json.loads(raw) if raw else {}
            except Exception:
                body_json = {}
    except Exception:
        body_json = {}

    def get_in(name, default=None):
        if hasattr(request, 'POST') and name in request.POST:
            return request.POST.get(name)
        try:
            return body_json.get(name, default) if isinstance(body_json, dict) else default
        except Exception:
            return default

    def _clean(val):
        return val if val not in (None, '') else None

    def _norm_number_like(v):
        try:
            if v is None:
                return None
            s = str(v).strip()
            if s == '':
                return None
            if s.endswith('%'):
                s = s[:-1].strip()
            s = s.replace(',', '.')
            if s == '':
                return None
            return s
        except Exception:
            return None

    def _to_int(v):
        try:
            if v is None or v == '':
                return None
            return int(float(v))
        except Exception:
            return None

    def _to_dec_2(v):
        try:
            if v is None or v == '':
                return None
            d = Decimal(str(v))
            return d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except Exception:
            return None

    CANONICAL_MAP = {
        'limpeza_mecanizada_diaria': [
            'limpeza_mecanizada_diaria', 'sup-limp', 'percentual_limpeza_diario', 'avanco_limpeza',
        ],
        'limpeza_mecanizada_cumulativa': [
            'limpeza_mecanizada_cumulativa', 'sup-limp-acu', 'limpeza_acu', 'percentual_limpeza_cumulativo',
        ],
        'percentual_limpeza_fina': [
            'percentual_limpeza_fina', 'sup-limp-fina', 'avanco_limpeza_fina', 'percentual_limpeza_fina_diario',
        ],
        'percentual_limpeza_fina_cumulativo': [
            'percentual_limpeza_fina_cumulativo', 'sup-limp-fina-acu', 'limpeza_fina_acu',
        ],
    }

    vals = {}
    for canon, names in CANONICAL_MAP.items():
        raw = None
        for nm in names:
            raw_candidate = _clean(get_in(nm))
            if raw_candidate is not None:
                raw = _norm_number_like(raw_candidate)
                if raw is None:
                    raw = _clean(raw_candidate)
                break
        vals[canon] = raw

    converted = {
        'limpeza_mecanizada_diaria': _to_dec_2(vals.get('limpeza_mecanizada_diaria')),
        'limpeza_mecanizada_cumulativa': _to_int(vals.get('limpeza_mecanizada_cumulativa')),
        'percentual_limpeza_fina': _to_int(vals.get('percentual_limpeza_fina')),
        'percentual_limpeza_fina_cumulativo': _to_int(vals.get('percentual_limpeza_fina_cumulativo')),
    }

    resp = {
        'success': True,
        'POST_keys': list(request.POST.keys()),
        'JSON_keys': (list(body_json.keys()) if isinstance(body_json, dict) else None),
        'cleaning_raw': vals,
        'converted': {k: (str(v) if isinstance(v, Decimal) else v) for k, v in converted.items()},
    }

    return JsonResponse(resp)

def _apply_post_to_rdo(request, rdo_obj):
    logger = logging.getLogger(__name__)
    try:
        logger.info('_apply_post_to_rdo start user=%s rdo_id=%s POST_keys=%s', getattr(request, 'user', None), getattr(rdo_obj, 'id', None), list(request.POST.keys()))
        try:
            try:
                post_lists = {}
                if hasattr(request.POST, 'lists'):
                    for k, vals in request.POST.lists():
                        post_lists[k] = vals
                else:
                    for k in list(request.POST.keys()):
                        post_lists[k] = request.POST.getlist(k) if hasattr(request.POST, 'getlist') else [request.POST.get(k)]
                logger.info('_apply_post_to_rdo full POST lists: %s', post_lists)
            except Exception:
                logger.exception('Could not enumerate POST lists')
            try:
                files_info = []
                if hasattr(request, 'FILES') and request.FILES:
                    for k in list(request.FILES.keys()):
                        try:
                            objs = request.FILES.getlist(k) if hasattr(request.FILES, 'getlist') else [request.FILES.get(k)]
                            for f in objs:
                                try:
                                    files_info.append({'field': k, 'name': getattr(f, 'name', None), 'size': getattr(f, 'size', None)})
                                except Exception:
                                    files_info.append({'field': k, 'name': str(f), 'size': None})
                        except Exception:
                            files_info.append({'field': k, 'error': 'could not inspect'})
                logger.info('_apply_post_to_rdo FILES info: %s', files_info)
            except Exception:
                logger.exception('Could not enumerate FILES')
        except Exception:
            logger.exception('Debug dump of POST/FILES failed')
        try:
            limp_keys = ['sup-limp', 'sup-limp-acu', 'sup-limp-fina', 'sup-limp-fina-acu', 'avanco_limpeza', 'percentual_limpeza', 'percentual_limpeza_cumulativo', 'limpeza_acu', 'limpeza_fina_acu']
            limp_vals = {k: request.POST.get(k) for k in limp_keys}
            logger.info('_apply_post_to_rdo limpeza POST values: %s', limp_vals)
        except Exception:
            logger.exception('Falha ao logar campos de limpeza do POST')
        def _clean(val):
            return val if (val not in (None, '')) else None

        body_json = {}
        try:
            try:
                ctype = (request.META.get('CONTENT_TYPE') or request.META.get('HTTP_CONTENT_TYPE') or '')
            except Exception:
                ctype = ''
            if (not request.POST) or ('application/json' in ctype):
                try:
                    raw_body = (request.body.decode('utf-8') if getattr(request, 'body', None) else '') or ''
                    if raw_body:
                        parsed = json.loads(raw_body)
                        if isinstance(parsed, dict):
                            body_json = parsed
                except Exception:
                    body_json = {}
        except Exception:
            body_json = {}

        def _get_post_or_json(name):
            try:
                if hasattr(request, 'POST') and (name in request.POST):
                    return request.POST.get(name)
                if isinstance(body_json, dict) and body_json.get(name) is not None:
                    return body_json.get(name)
            except Exception:
                pass
            return None

        

        def _normalize_contrato(val):
            if val is None:
                return None
            s = str(val).strip()
            if s == '':
                return None
            return s[:30]
        
        ordem_servico_id = _get_post_or_json('ordem_servico_id')
        data_str = _get_post_or_json('data')
        data_inicio_str = _get_post_or_json('rdo_data_inicio') or _get_post_or_json('data_inicio')
        previsao_termino_str = _get_post_or_json('rdo_previsao_termino') or _get_post_or_json('previsao_termino')
        turno_str = _get_post_or_json('turno')
        contrato_po_str = _get_post_or_json('contrato_po')

        def _parse_date_yyyy_mm_dd(raw_value):
            try:
                text = str(raw_value or '').strip()
                if not text:
                    return None
                return datetime.strptime(text, '%Y-%m-%d').date()
            except Exception:
                return None

        parsed_data = _parse_date_yyyy_mm_dd(data_str)
        parsed_data_inicio = _parse_date_yyyy_mm_dd(data_inicio_str)
        if parsed_data_inicio is None and parsed_data is not None:
            parsed_data_inicio = parsed_data
        if parsed_data is None and parsed_data_inicio is not None:
            parsed_data = parsed_data_inicio
        parsed_previsao_termino = _parse_date_yyyy_mm_dd(previsao_termino_str)

        if rdo_obj is None:
            ordem_servico = OrdemServico.objects.get(id=ordem_servico_id)
            data = parsed_data
            if data is None:
                try:
                    data = datetime.today().date()
                except Exception:
                    data = None
            data_inicio = parsed_data_inicio
            previsao_termino = parsed_previsao_termino
            turno = turno_str
            contrato_po = contrato_po_str
            rdo_obj = RDO(ordem_servico=ordem_servico, data=data, data_inicio=data_inicio, previsao_termino=previsao_termino, turno=turno, contrato_po=contrato_po)
        else:
            if parsed_data is not None:
                rdo_obj.data = parsed_data
            if parsed_data_inicio is not None:
                rdo_obj.data_inicio = parsed_data_inicio
            if parsed_data is None and parsed_data_inicio is not None:
                rdo_obj.data = parsed_data_inicio
            if parsed_data_inicio is None and parsed_data is not None:
                rdo_obj.data_inicio = parsed_data
            if parsed_previsao_termino is not None:
                rdo_obj.previsao_termino = parsed_previsao_termino
            if not getattr(rdo_obj, 'turno', None) and turno_str:
                rdo_obj.turno = turno_str
            if not getattr(rdo_obj, 'contrato_po', None) and contrato_po_str:
                rdo_obj.contrato_po = contrato_po_str

        rdo_num = _clean(request.POST.get('rdo_contagem'))
        if rdo_num and not getattr(rdo_obj, 'rdo', None):
            rdo_obj.rdo = rdo_num
        turno_in = _clean(request.POST.get('turno'))
        if turno_in:
            if turno_in.lower() == 'diurno':
                rdo_obj.turno = 'Diurno'
            elif turno_in.lower() == 'noturno':
                rdo_obj.turno = 'Noturno'

        contrato_in = _clean(request.POST.get('contrato_po'))
        contrato_in = _normalize_contrato(contrato_in)
        if contrato_in is not None:
            if hasattr(rdo_obj, 'contrato_po'):
                try:
                    rdo_obj.contrato_po = contrato_in
                except Exception:
                    pass
            elif hasattr(rdo_obj, 'po'):
                try:
                    rdo_obj.po = contrato_in
                except Exception:
                    pass
            else:
                try:
                    if getattr(rdo_obj, 'ordem_servico', None):
                        ordem = rdo_obj.ordem_servico
                        ordem.po = contrato_in
                        ordem.save()
                except Exception:
                    pass

        is_update = getattr(rdo_obj, 'id', None) is not None
        if not is_update:
            rdo_obj.nome_tanque = _clean(request.POST.get('tanque_nome')) or rdo_obj.nome_tanque
            rdo_obj.tanque_codigo = _clean(request.POST.get('tanque_codigo')) or rdo_obj.tanque_codigo
            rdo_obj.tipo_tanque = _clean(request.POST.get('tipo_tanque')) or rdo_obj.tipo_tanque
        try:
            try:
                post_keys = list(request.POST.keys()) if hasattr(request, 'POST') else []
            except Exception:
                post_keys = []
            logger.info('DEBUG _apply_post_to_rdo incoming POST keys: %s', post_keys)
            try:
                if request.content_type and 'json' in (request.content_type or '').lower():
                    import json as _json
                    try:
                        body = request.body.decode('utf-8') if hasattr(request, 'body') else None
                        jb = _json.loads(body) if body else None
                        if isinstance(jb, dict):
                            logger.info('DEBUG _apply_post_to_rdo incoming JSON keys: %s', list(jb.keys()))
                        else:
                            logger.info('DEBUG _apply_post_to_rdo incoming JSON payload (non-dict)')
                    except Exception:
                        logger.info('DEBUG _apply_post_to_rdo could not parse request.body as JSON')
            except Exception:
                pass
        except Exception:
            try:
                logger.exception('DEBUG failed to log incoming POST keys')
            except Exception:
                pass

        num_comp = _clean(request.POST.get('numero_compartimento'))
        parsed_num = None
        if num_comp is not None:
            try:
                parsed_num = int(num_comp)
            except Exception:
                parsed_num = None

        if parsed_num is not None:
            try:
                cur = getattr(rdo_obj, 'numero_compartimentos', None)
                if not cur:
                    rdo_obj.numero_compartimentos = parsed_num
            except Exception:
                pass

        try:
            total_n = 0
            try:
                total_n = int(getattr(rdo_obj, 'numero_compartimentos') or parsed_num or 0)
            except Exception:
                total_n = 0
            comps = {}
            for i in range(1, (total_n or 0) + 1):
                keyM = f'compartimento_avanco_mecanizada_{i}'
                keyF = f'compartimento_avanco_fina_{i}'
                vM = request.POST.get(keyM)
                vF = request.POST.get(keyF)
                try:
                    logger.info('DEBUG compartment %s received: %s=%s ; %s=%s', i, keyM, repr(vM), keyF, repr(vF))
                except Exception:
                    pass
                try:
                    mval = int(float(vM)) if (vM not in (None, '')) else 0
                except Exception:
                    mval = 0
                try:
                    fval = int(float(vF)) if (vF not in (None, '')) else 0
                except Exception:
                    fval = 0
                try:
                    mval = max(0, min(100, int(mval)))
                except Exception:
                    mval = 0
                try:
                    fval = max(0, min(100, int(fval)))
                except Exception:
                    fval = 0
                comps[str(i)] = {'mecanizada': mval, 'fina': fval}
            if comps:
                try:
                    rdo_obj.compartimentos_avanco_json = json.dumps(comps, ensure_ascii=False)
                    logger.info('DEBUG serialized compartimentos_avanco_json: %s', rdo_obj.compartimentos_avanco_json)
                except Exception:
                    logger.exception('Falha serializando compartimentos_avanco_json')
                try:
                    sum_mec = 0
                    total_slots = 0
                    for k, v in (comps or {}).items():
                        try:
                            mv = int(v.get('mecanizada', 0) if isinstance(v, dict) else 0)
                        except Exception:
                            try:
                                mv = int(float(v))
                            except Exception:
                                mv = 0
                        total_slots += 1
                        sum_mec += max(0, min(100, mv))
                    mirror_val = (float(sum_mec) / float(total_slots)) if total_slots > 0 else 0.0
                    mirror_val = round(mirror_val, 2)
                    mirror_str = f"{mirror_val:.2f}"
                    logger.info('DEBUG computed mirror_val=%s total_slots=%s sum_mec=%s mirror_str=%s', mirror_val, total_slots, sum_mec, mirror_str)
                    try:
                        if hasattr(rdo_obj, 'avanco_limpeza'):
                            rdo_obj.avanco_limpeza = mirror_str
                    except Exception:
                        pass
                    try:
                        if hasattr(rdo_obj, 'percentual_limpeza_diario'):
                            rdo_obj.percentual_limpeza_diario = Decimal(str(mirror_val))
                        elif hasattr(rdo_obj, 'limpeza_mecanizada_diaria'):
                            rdo_obj.limpeza_mecanizada_diaria = Decimal(str(mirror_val))
                    except Exception:
                        pass
                except Exception:
                    logger.exception('Erro calculando avanco_limpeza server-side')
        except Exception:
            logger.exception('Erro processando compartimentos_avanco do POST')

        vol_exec = _clean(request.POST.get('volume_tanque_exec'))
        if vol_exec is not None:
            rdo_obj.volume_tanque_exec = vol_exec
        rdo_obj.servico_exec = _clean(request.POST.get('servico_exec')) or rdo_obj.servico_exec
        rdo_obj.metodo_exec = _clean(request.POST.get('metodo_exec')) or rdo_obj.metodo_exec
        try:
            conf_raw = _get_post_or_json('espaco_confinado')
            if conf_raw is None:
                conf_raw = _get_post_or_json('confinado')
            if conf_raw is not None and conf_raw != '' and hasattr(rdo_obj, 'confinado'):
                if isinstance(conf_raw, bool):
                    rdo_obj.confinado = conf_raw
                else:
                    s = str(conf_raw).strip().lower()
                    if s in ('1', 'true', 't', 'yes', 'y', 'sim'):
                        rdo_obj.confinado = True
                    elif s in ('0', 'false', 'f', 'no', 'n', 'nao', 'não'):
                        rdo_obj.confinado = False
        except Exception:
            pass

        gav = _clean(request.POST.get('gavetas'))
        if gav is not None:
            try:
                rdo_obj.gavetas = int(gav)
            except Exception:
                pass
        pat = _clean(request.POST.get('patamar'))
        if pat is not None:
            try:
                rdo_obj.patamares = int(pat)
            except Exception:
                pass

        op_sim = _clean(request.POST.get('operadores_simultaneos'))
        if op_sim is not None:
            try:
                rdo_obj.operadores_simultaneos = int(op_sim)
            except Exception:
                pass

        try:
            tanque_id_raw = _clean(_get_post_or_json('tanque_id') or _get_post_or_json('tank_id') or _get_post_or_json('tanqueId'))
            if tanque_id_raw is not None:
                try:
                    tanque_id_int = int(tanque_id_raw)
                except Exception:
                    tanque_id_int = None
                if tanque_id_int:
                    try:
                        tank_obj = RdoTanque.objects.get(pk=tanque_id_int)

                        def _to_int_or_none(val):
                            if val in (None, ''):
                                return None
                            try:
                                return int(val)
                            except Exception:
                                try:
                                    return int(float(val))
                                except Exception:
                                    return None

                        ens_val = _get_post_or_json('ensacamento_prev') or request.POST.get('ensacamento_prev')
                        ic_val = _get_post_or_json('icamento_prev') or request.POST.get('icamento_prev')
                        camb_val = _get_post_or_json('cambagem_prev') or request.POST.get('cambagem_prev')
                        previsao_val = _get_post_or_json('previsao_termino') or _get_post_or_json('rdo_previsao_termino') or request.POST.get('previsao_termino')

                        ens_i = _to_int_or_none(ens_val)
                        ic_i = _to_int_or_none(ic_val)
                        camb_i = _to_int_or_none(camb_val)
                        previsao_dt = _parse_iso_date_value(previsao_val)

                        updated = False
                        locked_predictions = []
                        if _apply_tank_prediction_once(tank_obj, 'ensacamento_prev', ens_i):
                            updated = True
                        elif ens_i is not None and _is_tank_prediction_locked(tank_obj, 'ensacamento_prev'):
                            locked_predictions.append('ensacamento_prev')
                        if _apply_tank_prediction_once(tank_obj, 'icamento_prev', ic_i):
                            updated = True
                        elif ic_i is not None and _is_tank_prediction_locked(tank_obj, 'icamento_prev'):
                            locked_predictions.append('icamento_prev')
                        if _apply_tank_prediction_once(tank_obj, 'cambagem_prev', camb_i):
                            updated = True
                        elif camb_i is not None and _is_tank_prediction_locked(tank_obj, 'cambagem_prev'):
                            locked_predictions.append('cambagem_prev')
                        if _apply_tank_prediction_once(tank_obj, 'previsao_termino', previsao_dt):
                            updated = True
                        elif previsao_dt is not None and _is_tank_prediction_locked(tank_obj, 'previsao_termino'):
                            locked_predictions.append('previsao_termino')

                        if updated:
                            try:
                                _safe_save_global(tank_obj)
                                logger.info(
                                    'Updated RdoTanque(id=%s) predictions ens=%s ic=%s camb=%s locked=%s',
                                    tank_obj.id,
                                    ens_i,
                                    ic_i,
                                    camb_i,
                                    ','.join(locked_predictions) if locked_predictions else '-'
                                )
                            except Exception:
                                try:
                                    tank_obj.save()
                                except Exception:
                                    logger.exception('Failed to save RdoTanque predictions for id=%s', tanque_id_int)

                        try:
                            def _to_decimal_or_none(val):
                                if val in (None, ''):
                                    return None
                                try:
                                    return Decimal(str(float(val)))
                                except Exception:
                                    try:
                                        return Decimal(str(val))
                                    except Exception:
                                        return None

                            raw_mec_daily = _get_post_or_json('limpeza_mecanizada_diaria') or _get_post_or_json('percentual_limpeza_diario') or _get_post_or_json('sup-limp') or _get_post_or_json('percentual_limpeza')
                            parsed_mec_daily = _to_decimal_or_none(raw_mec_daily)

                            raw_mec_acu = _get_post_or_json('limpeza_mecanizada_cumulativa') or _get_post_or_json('sup-limp-acu') or _get_post_or_json('percentual_limpeza_cumulativo')
                            try:
                                parsed_mec_acu = int(float(raw_mec_acu)) if raw_mec_acu not in (None, '') else None
                            except Exception:
                                parsed_mec_acu = None

                            raw_fina_daily = _get_post_or_json('percentual_limpeza_fina') or _get_post_or_json('percentual_limpeza_fina_diario') or _get_post_or_json('sup-limp-fina') or _get_post_or_json('limpeza_fina_diaria')
                            parsed_fina_daily = _to_decimal_or_none(raw_fina_daily)

                            raw_fina_acu = _get_post_or_json('limpeza_fina_cumulativa') or _get_post_or_json('sup-limp-fina-acu') or _get_post_or_json('percentual_limpeza_fina_cumulativo')
                            try:
                                parsed_fina_acu = int(float(raw_fina_acu)) if raw_fina_acu not in (None, '') else None
                            except Exception:
                                parsed_fina_acu = None

                            cleaning_updated = False
                            if parsed_mec_daily is not None and hasattr(tank_obj, 'limpeza_mecanizada_diaria'):
                                try:
                                    try:
                                        tank_obj.limpeza_mecanizada_diaria = parsed_mec_daily.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                    except Exception:
                                        try:
                                            tank_obj.limpeza_mecanizada_diaria = Decimal(str(float(parsed_mec_daily))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                        except Exception:
                                            tank_obj.limpeza_mecanizada_diaria = parsed_mec_daily
                                    cleaning_updated = True
                                except Exception:
                                    logger.exception('Falha ao atribuir limpeza_mecanizada_diaria ao RdoTanque %s', tanque_id_int)
                            if parsed_mec_acu is not None and hasattr(tank_obj, 'limpeza_mecanizada_cumulativa'):
                                try:
                                    tank_obj.limpeza_mecanizada_cumulativa = max(0, min(100, int(parsed_mec_acu)))
                                    cleaning_updated = True
                                except Exception:
                                    logger.exception('Falha ao atribuir limpeza_mecanizada_cumulativa ao RdoTanque %s', tanque_id_int)
                            if parsed_fina_daily is not None and hasattr(tank_obj, 'percentual_limpeza_fina'):
                                try:
                                    tank_obj.percentual_limpeza_fina = max(0, min(100, int(round(float(parsed_fina_daily)))))
                                    cleaning_updated = True
                                except Exception:
                                    logger.exception('Falha ao atribuir percentual_limpeza_fina ao RdoTanque %s', tanque_id_int)
                            if parsed_fina_daily is not None and hasattr(tank_obj, 'limpeza_fina_diaria'):
                                try:
                                    try:
                                        tank_obj.limpeza_fina_diaria = parsed_fina_daily.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                    except Exception:
                                        try:
                                            tank_obj.limpeza_fina_diaria = Decimal(str(float(parsed_fina_daily))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                        except Exception:
                                            tank_obj.limpeza_fina_diaria = parsed_fina_daily
                                    cleaning_updated = True
                                except Exception:
                                    logger.exception('Falha ao atribuir limpeza_fina_diaria ao RdoTanque %s', tanque_id_int)
                            if parsed_fina_acu is not None and hasattr(tank_obj, 'percentual_limpeza_fina_cumulativo'):
                                try:
                                    tank_obj.percentual_limpeza_fina_cumulativo = max(0, min(100, int(parsed_fina_acu)))
                                    cleaning_updated = True
                                except Exception:
                                    logger.exception('Falha ao atribuir percentual_limpeza_fina_cumulativo ao RdoTanque %s', tanque_id_int)

                            if parsed_mec_daily is not None and hasattr(tank_obj, 'percentual_limpeza_diario'):
                                try:
                                    try:
                                        tank_obj.percentual_limpeza_diario = parsed_mec_daily.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                    except Exception:
                                        try:
                                            tank_obj.percentual_limpeza_diario = Decimal(str(float(parsed_mec_daily))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                        except Exception:
                                            tank_obj.percentual_limpeza_diario = parsed_mec_daily
                                    cleaning_updated = True
                                except Exception:
                                    logger.exception('Falha ao atribuir percentual_limpeza_diario ao RdoTanque %s', tanque_id_int)
                            if parsed_mec_acu is not None and hasattr(tank_obj, 'percentual_limpeza_cumulativo'):
                                try:
                                    tank_obj.percentual_limpeza_cumulativo = max(0, min(100, int(parsed_mec_acu)))
                                    cleaning_updated = True
                                except Exception:
                                    logger.exception('Falha ao atribuir percentual_limpeza_cumulativo ao RdoTanque %s', tanque_id_int)
                            if parsed_fina_daily is not None and hasattr(tank_obj, 'percentual_limpeza_fina_diario'):
                                try:
                                    try:
                                        tank_obj.percentual_limpeza_fina_diario = parsed_fina_daily.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                    except Exception:
                                        try:
                                            tank_obj.percentual_limpeza_fina_diario = Decimal(str(float(parsed_fina_daily))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                        except Exception:
                                            tank_obj.percentual_limpeza_fina_diario = parsed_fina_daily
                                    cleaning_updated = True
                                except Exception:
                                    logger.exception('Falha ao atribuir percentual_limpeza_fina_diario ao RdoTanque %s', tanque_id_int)
                            if parsed_fina_acu is not None and hasattr(tank_obj, 'percentual_limpeza_fina_cumulativo'):
                                try:
                                    tank_obj.percentual_limpeza_fina_cumulativo = max(0, min(100, int(parsed_fina_acu)))
                                    cleaning_updated = True
                                except Exception:
                                    logger.exception('Falha ao atribuir percentual_limpeza_fina_cumulativo ao RdoTanque %s', tanque_id_int)

                            raw_avanco = _get_post_or_json('avanco_limpeza') or _get_post_or_json('sup-limp') or request.POST.get('avanco_limpeza')
                            if raw_avanco not in (None, '') and hasattr(tank_obj, 'avanco_limpeza'):
                                try:
                                    tank_obj.avanco_limpeza = str(raw_avanco)
                                    cleaning_updated = True
                                except Exception:
                                    pass
                            raw_avanco_fina = _get_post_or_json('avanco_limpeza_fina') or _get_post_or_json('sup-limp-fina') or request.POST.get('avanco_limpeza_fina')
                            if raw_avanco_fina not in (None, '') and hasattr(tank_obj, 'avanco_limpeza_fina'):
                                try:
                                    tank_obj.avanco_limpeza_fina = str(raw_avanco_fina)
                                    cleaning_updated = True
                                except Exception:
                                    pass

                            if cleaning_updated:
                                try:
                                    _safe_save_global(tank_obj)
                                    logger.info('Updated RdoTanque(id=%s) cleaning fields: mec_daily=%s mec_acu=%s fina=%s fina_acu=%s', tank_obj.id, parsed_mec_daily, parsed_mec_acu, parsed_fina_daily, parsed_fina_acu)
                                except Exception:
                                    try:
                                        tank_obj.save()
                                    except Exception:
                                        logger.exception('Failed to save RdoTanque cleaning fields for id=%s', tanque_id_int)
                            try:
                                update_values = {}
                                raw_mec = _get_post_or_json('limpeza_mecanizada_diaria') or _get_post_or_json('percentual_limpeza_diario') or _get_post_or_json('sup-limp')
                                if raw_mec not in (None, '') and hasattr(tank_obj, 'limpeza_mecanizada_diaria'):
                                    try:
                                        v = Decimal(str(float(raw_mec)))
                                        update_values['limpeza_mecanizada_diaria'] = v.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                    except Exception:
                                        pass
                                raw_fina = _get_post_or_json('limpeza_fina_diaria') or _get_post_or_json('percentual_limpeza_fina') or _get_post_or_json('sup-limp-fina')
                                if raw_fina not in (None, '') and hasattr(tank_obj, 'limpeza_fina_diaria'):
                                    try:
                                        v = Decimal(str(float(raw_fina)))
                                        update_values['limpeza_fina_diaria'] = v.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                    except Exception:
                                        pass
                                if update_values:
                                    try:
                                        RdoTanque.objects.filter(pk=tank_obj.pk).update(**update_values)
                                        try:
                                            tank_obj.refresh_from_db()
                                        except Exception:
                                            pass
                                    except Exception:
                                        logger.exception('DB-level update failed for limpeza daily fields on tank_id=%s', tanque_id_int)
                            except Exception:
                                logger.exception('Fallback DB update for daily cleaning fields failed for tank_id=%s', tanque_id_int)
                        except Exception:
                            logger.exception('Erro ao persistir campos de limpeza por-tanque para tanque_id=%s', tanque_id_raw)
                    except RdoTanque.DoesNotExist:
                        logger.info('tanque_id provided but RdoTanque not found: %s', tanque_id_int)
        except Exception:
            logger.exception('Erro ao persistir previsoes por-tanque a partir do POST')

        h2s_val = _coerce_decimal_for_model(RDO, 'h2s_ppm', _clean(_get_post_or_json('h2s_ppm')))
        try:
            if hasattr(rdo_obj, 'h2s_ppm'):
                setattr(rdo_obj, 'h2s_ppm', h2s_val if h2s_val is not None else getattr(rdo_obj, 'h2s_ppm', None))
            elif hasattr(rdo_obj, 'H2S_ppm'):
                setattr(rdo_obj, 'H2S_ppm', h2s_val if h2s_val is not None else getattr(rdo_obj, 'H2S_ppm', None))
        except Exception:
            pass

        lel_val = _coerce_decimal_for_model(RDO, 'lel', _clean(_get_post_or_json('lel')))
        try:
            if hasattr(rdo_obj, 'lel'):
                setattr(rdo_obj, 'lel', lel_val if lel_val is not None else getattr(rdo_obj, 'lel', None))
            elif hasattr(rdo_obj, 'LEL'):
                setattr(rdo_obj, 'LEL', lel_val if lel_val is not None else getattr(rdo_obj, 'LEL', None))
        except Exception:
            pass

        co_val = _coerce_decimal_for_model(RDO, 'co_ppm', _clean(_get_post_or_json('co_ppm')))
        try:
            if hasattr(rdo_obj, 'co_ppm'):
                setattr(rdo_obj, 'co_ppm', co_val if co_val is not None else getattr(rdo_obj, 'co_ppm', None))
            elif hasattr(rdo_obj, 'CO_ppm'):
                setattr(rdo_obj, 'CO_ppm', co_val if co_val is not None else getattr(rdo_obj, 'CO_ppm', None))
        except Exception:
            pass

        o2_val = _coerce_decimal_for_model(RDO, 'o2_percent', _clean(_get_post_or_json('o2_percent')))
        try:
            if hasattr(rdo_obj, 'o2_percent'):
                setattr(rdo_obj, 'o2_percent', o2_val if o2_val is not None else getattr(rdo_obj, 'o2_percent', None))
            elif hasattr(rdo_obj, 'O2_percent'):
                setattr(rdo_obj, 'O2_percent', o2_val if o2_val is not None else getattr(rdo_obj, 'O2_percent', None))
        except Exception:
            pass

        total_liq = _clean(request.POST.get('residuo_liquido'))
        if total_liq is not None:
            try:
                rdo_obj.total_liquido = int(float(total_liq))
            except ValueError:
                pass
        ensac = _clean(request.POST.get('ensacamento_dia'))
        if ensac is not None:
            try:
                rdo_obj.ensacamento = int(ensac)
            except ValueError:
                pass
        tamb = _clean(request.POST.get('tambores_dia'))
        if tamb is not None:
            try:
                rdo_obj.tambores = int(tamb)
            except ValueError:
                pass
        def _parse_percent(val, as_int=False, clamp=True):
            if val is None:
                return None
            s = str(val).strip()
            if not s:
                return None
            if s.endswith('%'):
                s = s[:-1].strip()
            s = s.replace(',', '.')
            try:
                if as_int:
                    v = int(float(s))
                    if clamp:
                        if v < 0:
                            v = 0
                        if v > 100:
                            v = 100
                    return v
                else:
                    d = Decimal(str(float(s)))
                    return d
            except Exception:
                return None

        percent_map = [
            ('avanco_limpeza', 'percentual_limpeza_diario', 'decimal'),
            ('sup-limp', 'percentual_limpeza_diario', 'decimal'),
            ('sup-limp-acu', 'limpeza_mecanizada_cumulativa', 'int'),
            ('sup-limp-fina', 'limpeza_fina_diaria', 'decimal'),
            ('sup-limp-fina-acu', 'limpeza_fina_cumulativa', 'int'),
            ('avanco_limpeza_fina', 'percentual_limpeza_fina', 'int'),
            ('limpeza_acu', 'percentual_limpeza_cumulativo', 'int'),
            ('limpeza_fina_acu', 'percentual_limpeza_fina_cumulativo', 'int'),
            ('ensacamento_prev', 'ensacamento_previsao', 'int'),
            ('ensacamento_acu', 'ensacamento_cumulativo', 'int'),
            ('percentual_ensacamento', 'percentual_ensacamento', 'decimal'),
            ('icamento_dia', 'icamento', 'int'),
            ('icamento_prev', 'icamento_previsao', 'int'),
            ('icamento_acu', 'icamento_cumulativo', 'int'),
            ('percentual_icamento', 'percentual_icamento', 'decimal'),
            ('cambagem_dia', 'cambagem', 'int'),
            ('cambagem_prev', 'cambagem_previsao', 'int'),
            ('cambagem_acu', 'cambagem_cumulativo', 'int'),
            ('percentual_cambagem', 'percentual_cambagem', 'decimal'),
            ('pob', 'pob', 'int'),
            ('percentual_avanco', 'percentual_avanco', 'int'),
            ('percentual_avanco_cumulativo', 'percentual_avanco_cumulativo', 'int'),
            ('percentual_limpeza', 'percentual_limpeza_diario', 'decimal'),
            ('percentual_limpeza_diario', 'percentual_limpeza_diario', 'decimal'),
            ('percentual_limpeza_fina_diario', 'percentual_limpeza_fina_diario', 'decimal'),
            ('percentual_limpeza_cumulativo', 'limpeza_mecanizada_cumulativa', 'int'),
            ('percentual_limpeza_fina', 'percentual_limpeza_fina', 'int'),
            ('percentual_limpeza_fina_cumulativo', 'percentual_limpeza_fina_cumulativo', 'int'),
            ('ensacamento_cumulativo', 'ensacamento_cumulativo', 'int'),
            ('ensacamento_previsao', 'ensacamento_previsao', 'int'),
            ('icamento', 'icamento', 'int'),
            ('icamento_cumulativo', 'icamento_cumulativo', 'int'),
            ('icamento_previsao', 'icamento_previsao', 'int'),
            ('cambagem', 'cambagem', 'int'),
            ('cambagem_cumulativo', 'cambagem_cumulativo', 'int'),
            ('cambagem_previsao', 'cambagem_previsao', 'int'),
            ('percentual_ensacamento', 'percentual_ensacamento', 'decimal'),
            ('percentual_icamento', 'percentual_icamento', 'decimal'),
            ('percentual_cambagem', 'percentual_cambagem', 'decimal'),
        ]

        _UNCLAMPED_INT_POST_NAMES = set([
            'ensacamento_prev', 'ensacamento_previsao',
            'icamento_prev', 'icamento_previsao',
            'cambagem_prev', 'cambagem_previsao',
        ])

        for post_name, model_name, typ in percent_map:
            try:
                raw = _clean(_get_post_or_json(post_name))
                if raw is None:
                    continue
                if typ == 'int':
                    clamp_flag = False if (post_name in _UNCLAMPED_INT_POST_NAMES or model_name in _UNCLAMPED_INT_POST_NAMES) else True
                    parsed = _parse_percent(raw, as_int=True, clamp=clamp_flag)
                else:
                    parsed = _parse_percent(raw, as_int=False)
                if parsed is None:
                    continue
                if hasattr(rdo_obj, model_name):
                    try:
                        setattr(rdo_obj, model_name, parsed)
                    except Exception:
                        try:
                            if typ == 'decimal':
                                setattr(rdo_obj, model_name, Decimal(str(parsed)))
                            else:
                                setattr(rdo_obj, model_name, int(parsed))
                        except Exception:
                            logging.getLogger(__name__).exception('Falha atribuindo %s=%s ao RDO', model_name, parsed)
            except Exception:
                logging.getLogger(__name__).exception('Erro ao processar campo %s', post_name)

            try:
                logger.info('_apply_post_to_rdo after percent_map - current limpeza values: percentual_limpeza=%s, percentual_limpeza_diario=%s, percentual_limpeza_fina=%s, limpeza_fina_diaria=%s',
                            getattr(rdo_obj, 'percentual_limpeza', None), getattr(rdo_obj, 'percentual_limpeza_diario', None), getattr(rdo_obj, 'percentual_limpeza_fina', None), getattr(rdo_obj, 'limpeza_fina_diaria', None))
            except Exception:
                logger.exception('Falha ao logar valores de limpeza após percent_map')

        try:
            def _normalize_prev_cumulativo(day_val, cum_val, legacy_total_val):
                if cum_val is not None:
                    return cum_val
                if legacy_total_val is None:
                    return None
                try:
                    return int(legacy_total_val)
                except Exception:
                    return legacy_total_val

            ens_day = _parse_percent(_clean(_get_post_or_json('ensacamento_dia')), as_int=True, clamp=False)
            ic_day = _parse_percent(_clean(_get_post_or_json('icamento_dia')), as_int=True, clamp=False)
            camb_day = _parse_percent(_clean(_get_post_or_json('cambagem_dia')), as_int=True, clamp=False)

            ens_cum_direct = _parse_percent(_clean(_get_post_or_json('ensacamento_cumulativo')), as_int=True, clamp=False)
            ic_cum_direct = _parse_percent(_clean(_get_post_or_json('icamento_cumulativo')), as_int=True, clamp=False)
            camb_cum_direct = _parse_percent(_clean(_get_post_or_json('cambagem_cumulativo')), as_int=True, clamp=False)

            ens_cum_legacy = _parse_percent(_clean(_get_post_or_json('ensacamento_acu')), as_int=True, clamp=False)
            ic_cum_legacy = _parse_percent(_clean(_get_post_or_json('icamento_acu')), as_int=True, clamp=False)
            camb_cum_legacy = _parse_percent(_clean(_get_post_or_json('cambagem_acu')), as_int=True, clamp=False)

            norm_ens = _normalize_prev_cumulativo(ens_day, ens_cum_direct, ens_cum_legacy)
            norm_ic = _normalize_prev_cumulativo(ic_day, ic_cum_direct, ic_cum_legacy)
            norm_camb = _normalize_prev_cumulativo(camb_day, camb_cum_direct, camb_cum_legacy)

            if norm_ens is not None and hasattr(rdo_obj, 'ensacamento_cumulativo'):
                rdo_obj.ensacamento_cumulativo = norm_ens
            if norm_ic is not None and hasattr(rdo_obj, 'icamento_cumulativo'):
                rdo_obj.icamento_cumulativo = norm_ic
            if norm_camb is not None and hasattr(rdo_obj, 'cambagem_cumulativo'):
                rdo_obj.cambagem_cumulativo = norm_camb
        except Exception:
            logger.exception('Falha ao normalizar cumulativos de ensacamento/içamento/cambagem no payload do RDO')

        try:
            raw_sup_limp = _clean(_get_post_or_json('sup-limp') or _get_post_or_json('percentual_limpeza') or _get_post_or_json('avanco_limpeza'))
            if raw_sup_limp is not None:
                parsed_sup_limp = _parse_percent(raw_sup_limp, as_int=False)
                if parsed_sup_limp is not None:
                    try:
                        if hasattr(rdo_obj, 'percentual_limpeza_diario'):
                            try:
                                rdo_obj.percentual_limpeza_diario = parsed_sup_limp
                                logger.info('_apply_post_to_rdo assigned percentual_limpeza_diario from sup-limp: %s', parsed_sup_limp)
                            except Exception:
                                logger.exception('Falha atribuindo percentual_limpeza_diario a partir de sup-limp')
                        if hasattr(rdo_obj, 'limpeza_mecanizada_diaria') and getattr(rdo_obj, 'limpeza_mecanizada_diaria', None) in (None, ''):
                            try:
                                rdo_obj.limpeza_mecanizada_diaria = parsed_sup_limp
                            except Exception:
                                pass
                    except Exception:
                        logger.exception('Erro tratando sup-limp')

            raw_sup_limp_f = _clean(_get_post_or_json('sup-limp-fina') or _get_post_or_json('percentual_limpeza_fina') or _get_post_or_json('avanco_limpeza_fina'))
            if raw_sup_limp_f is not None:
                parsed_sup_limp_f = _parse_percent(raw_sup_limp_f, as_int=False)
                if parsed_sup_limp_f is not None:
                    try:
                        if hasattr(rdo_obj, 'percentual_limpeza_fina_diario'):
                            try:
                                rdo_obj.percentual_limpeza_fina_diario = parsed_sup_limp_f
                                logger.info('_apply_post_to_rdo assigned percentual_limpeza_fina_diario from sup-limp-fina: %s', parsed_sup_limp_f)
                            except Exception:
                                logger.exception('Falha atribuindo percentual_limpeza_fina_diario a partir de sup-limp-fina')
                        if hasattr(rdo_obj, 'limpeza_fina_diaria') and getattr(rdo_obj, 'limpeza_fina_diaria', None) in (None, ''):
                            try:
                                rdo_obj.limpeza_fina_diaria = parsed_sup_limp_f
                            except Exception:
                                pass
                    except Exception:
                        logger.exception('Erro tratando sup-limp-fina')
        except Exception:
            logger.exception('Erro sincronizando campos sup-limp para percentuais principais')
        try:
            logger.info('_apply_post_to_rdo after sup-limp compatibility assignments: percentual_limpeza=%s (type=%s), percentual_limpeza_diario=%s, percentual_limpeza_fina=%s, limpeza_fina_diaria=%s',
                        getattr(rdo_obj, 'percentual_limpeza', None), type(getattr(rdo_obj, 'percentual_limpeza', None)).__name__ if getattr(rdo_obj, 'percentual_limpeza', None) is not None else 'None',
                        getattr(rdo_obj, 'percentual_limpeza_diario', None), getattr(rdo_obj, 'percentual_limpeza_fina', None), getattr(rdo_obj, 'limpeza_fina_diaria', None))
        except Exception:
            logger.exception('Falha ao logar valores de limpeza apos compatibilidade sup-limp')

        try:
            copy_post_names = [
                'sup-limp', 'sup-limp-acu', 'sup-limp-fina', 'sup-limp-fina-acu',
                'avanco_limpeza', 'avanco_limpeza_fina',
                'percentual_limpeza_diario', 'limpeza_mecanizada_diaria', 'limpeza_mecanizada_cumulativa',
                'limpeza_fina_diaria', 'limpeza_fina_cumulativa'
            ]
            should_copy = False
            for pn in copy_post_names:
                try:
                    if _get_post_or_json(pn) is not None or (hasattr(request, 'POST') and pn in request.POST):
                        should_copy = True
                        break
                except Exception:
                    continue

            if should_copy and getattr(rdo_obj, 'tanques', None) is not None:
                logger.info('_apply_post_to_rdo: copying limpeza fields from RDO to RdoTanque for rdo_id=%s', getattr(rdo_obj, 'id', None))
                from decimal import Decimal, ROUND_HALF_UP
                try:
                    explicit_tank_id = None
                    raw_tid = _clean(request.POST.get('tanque_id') or request.POST.get('tank_id') or request.POST.get('tanqueId'))
                    if raw_tid is not None:
                        try:
                            explicit_tank_id = int(str(raw_tid))
                        except Exception:
                            explicit_tank_id = None
                except Exception:
                    explicit_tank_id = None
                fields_to_copy = [
                    'limpeza_mecanizada_diaria', 'limpeza_mecanizada_cumulativa',
                    'limpeza_fina_diaria', 'limpeza_fina_cumulativa',
                    'percentual_limpeza_diario', 'percentual_limpeza_fina_diario',
                    'percentual_limpeza_cumulativo', 'percentual_limpeza_fina_cumulativo',
                    'percentual_limpeza_fina',
                    'avanco_limpeza', 'avanco_limpeza_fina'
                ]
                try:
                    tank_qs = rdo_obj.tanques.all()
                except Exception:
                    tank_qs = []

                for tank in (tank_qs or []):
                    try:
                        if explicit_tank_id and getattr(tank, 'id', None) == explicit_tank_id:
                            continue
                        updated = False
                        def _to_decimal_or_none_local(v):
                            if v in (None, ''):
                                return None
                            try:
                                s = str(v).strip().replace(',', '.')
                                d = Decimal(str(float(s)))
                                return d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                            except Exception:
                                try:
                                    d = Decimal(str(v))
                                    return d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                except Exception:
                                    return None

                        def _to_int_or_none_local(v):
                            if v in (None, ''):
                                return None
                            try:
                                return int(float(v))
                            except Exception:
                                try:
                                    return int(v)
                                except Exception:
                                    return None

                        try:
                            raw_mec_daily = _get_post_or_json('limpeza_mecanizada_diaria') or _get_post_or_json('percentual_limpeza_diario') or _get_post_or_json('sup-limp')
                            val_mec_daily = _to_decimal_or_none_local(raw_mec_daily) if raw_mec_daily is not None else getattr(rdo_obj, 'limpeza_mecanizada_diaria', None)
                            if val_mec_daily is not None and hasattr(tank, 'limpeza_mecanizada_diaria'):
                                try:
                                    tank.limpeza_mecanizada_diaria = val_mec_daily
                                    updated = True
                                except Exception:
                                    logger.exception('Falha atribuindo limpeza_mecanizada_diaria ao RdoTanque id=%s', getattr(tank, 'id', None))

                            raw_mec_acu = _get_post_or_json('limpeza_mecanizada_cumulativa') or _get_post_or_json('sup-limp-acu') or _get_post_or_json('percentual_limpeza_cumulativo')
                            val_mec_acu = _to_int_or_none_local(raw_mec_acu) if raw_mec_acu is not None else getattr(rdo_obj, 'limpeza_mecanizada_cumulativa', None)
                            if val_mec_acu is not None and hasattr(tank, 'limpeza_mecanizada_cumulativa'):
                                try:
                                    tank.limpeza_mecanizada_cumulativa = max(0, min(100, int(val_mec_acu)))
                                    updated = True
                                except Exception:
                                    logger.exception('Falha atribuindo limpeza_mecanizada_cumulativa ao RdoTanque id=%s', getattr(tank, 'id', None))

                            raw_fina_daily = _get_post_or_json('limpeza_fina_diaria') or _get_post_or_json('percentual_limpeza_fina') or _get_post_or_json('sup-limp-fina')
                            val_fina_daily = _to_decimal_or_none_local(raw_fina_daily) if raw_fina_daily is not None else getattr(rdo_obj, 'limpeza_fina_diaria', None)
                            if val_fina_daily is not None and hasattr(tank, 'percentual_limpeza_fina'):
                                try:
                                    tank.percentual_limpeza_fina = max(0, min(100, int(round(float(val_fina_daily)))))
                                    updated = True
                                except Exception:
                                    logger.exception('Falha atribuindo percentual_limpeza_fina ao RdoTanque id=%s', getattr(tank, 'id', None))
                            if val_fina_daily is not None and hasattr(tank, 'limpeza_fina_diaria'):
                                try:
                                    tank.limpeza_fina_diaria = val_fina_daily
                                    updated = True
                                except Exception:
                                    logger.exception('Falha atribuindo limpeza_fina_diaria ao RdoTanque id=%s', getattr(tank, 'id', None))

                            raw_fina_acu = _get_post_or_json('limpeza_fina_cumulativa') or _get_post_or_json('sup-limp-fina-acu') or _get_post_or_json('percentual_limpeza_fina_cumulativo')
                            val_fina_acu = _to_int_or_none_local(raw_fina_acu) if raw_fina_acu is not None else getattr(rdo_obj, 'limpeza_fina_cumulativa', None)
                            if val_fina_acu is not None and hasattr(tank, 'percentual_limpeza_fina_cumulativo'):
                                try:
                                    tank.percentual_limpeza_fina_cumulativo = max(0, min(100, int(val_fina_acu)))
                                    updated = True
                                except Exception:
                                    logger.exception('Falha atribuindo percentual_limpeza_fina_cumulativo ao RdoTanque id=%s', getattr(tank, 'id', None))
                        except Exception:
                            logger.exception('Erro mapeando valores POST->RdoTanque durante replicacao')
                        try:
                            if hasattr(tank, 'percentual_limpeza_diario'):
                                src = getattr(rdo_obj, 'percentual_limpeza_diario', None)
                                if src is None:
                                    src = getattr(rdo_obj, 'limpeza_mecanizada_diaria', None)
                                if src is not None:
                                    try:
                                        if not isinstance(src, Decimal):
                                            try:
                                                tank.percentual_limpeza_diario = Decimal(str(src)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                            except Exception:
                                                tank.percentual_limpeza_diario = Decimal(str(src))
                                        else:
                                            tank.percentual_limpeza_diario = src
                                        updated = True
                                    except Exception:
                                        pass
                            if hasattr(tank, 'percentual_limpeza_cumulativo'):
                                ac = getattr(rdo_obj, 'limpeza_mecanizada_cumulativa', None)
                                if ac is None:
                                    try:
                                        ac_dec = getattr(rdo_obj, 'percentual_limpeza_diario_cumulativo', None)
                                        ac = int(round(float(ac_dec))) if ac_dec is not None else None
                                    except Exception:
                                        ac = None
                                if ac is not None:
                                    try:
                                        tank.percentual_limpeza_cumulativo = int(ac)
                                        updated = True
                                    except Exception:
                                        pass
                            if hasattr(tank, 'percentual_limpeza_fina_diario'):
                                srcf = getattr(rdo_obj, 'percentual_limpeza_fina_diario', None)
                                if srcf is None:
                                    srcf = getattr(rdo_obj, 'limpeza_fina_diaria', None)
                                if srcf is None:
                                    srcf = getattr(rdo_obj, 'percentual_limpeza_fina', None)
                                if srcf is not None:
                                    try:
                                        if not isinstance(srcf, Decimal):
                                            try:
                                                tank.percentual_limpeza_fina_diario = Decimal(str(srcf)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                            except Exception:
                                                tank.percentual_limpeza_fina_diario = Decimal(str(srcf))
                                        else:
                                            tank.percentual_limpeza_fina_diario = srcf
                                        updated = True
                                    except Exception:
                                        pass
                            if hasattr(tank, 'percentual_limpeza_fina'):
                                srci = getattr(rdo_obj, 'percentual_limpeza_fina', None)
                                if srci is None:
                                    srci = getattr(rdo_obj, 'percentual_limpeza_fina_diario', None)
                                if srci is None:
                                    srci = getattr(rdo_obj, 'limpeza_fina_diaria', None)
                                if srci is not None:
                                    try:
                                        tank.percentual_limpeza_fina = int(round(float(srci)))
                                        updated = True
                                    except Exception:
                                        pass
                            if hasattr(tank, 'percentual_limpeza_fina_cumulativo'):
                                acf = getattr(rdo_obj, 'limpeza_fina_cumulativa', None)
                                if acf is None:
                                    acf = getattr(rdo_obj, 'percentual_limpeza_fina_cumulativo', None)
                                if acf is not None:
                                    try:
                                        tank.percentual_limpeza_fina_cumulativo = int(acf)
                                        updated = True
                                    except Exception:
                                        pass
                        except Exception:
                            logger.exception('Falha nas derivações de campos RDO->RdoTanque')
                        if updated:
                            try:
                                _safe_save_global(tank)
                            except Exception:
                                try:
                                    tank.save()
                                except Exception:
                                    logger.exception('Falha ao salvar RdoTanque id=%s ao copiar campos de limpeza', getattr(tank, 'id', None))
                    except Exception:
                        logger.exception('Erro ao copiar campos de limpeza para RdoTanque do RDO id=%s', getattr(rdo_obj, 'id', None))
        except Exception:
            logger.exception('Erro ao replicar campos de limpeza do RDO para RdoTanque')

        try:
            candidate_fields = ['total_hh_cumulativo_real', 'hh_disponivel_cumulativo', 'total_hh_frente_real', 'total_n_efetivo_confinado']
            time_fields = set(['total_hh_cumulativo_real', 'hh_disponivel_cumulativo', 'total_hh_frente_real'])

            def _parse_to_time(val):
                if val is None:
                    return None
                try:
                    if isinstance(val, str):
                        s = val.strip()
                        if not s:
                            return None
                        if ':' in s:
                            try:
                                return datetime.strptime(s, '%H:%M').time()
                            except Exception:
                                parts = s.split(':')
                                if len(parts) >= 2:
                                    try:
                                        h = int(parts[0]); m = int(parts[1])
                                        h = h % 24
                                        m = max(0, min(59, m))
                                        return dt_time(hour=h, minute=m)
                                    except Exception:
                                        return None
                    try:
                        mins = int(float(str(val)))
                        if mins < 0:
                            return None
                        h = (mins // 60) % 24
                        m = mins % 60
                        return dt_time(hour=int(h), minute=int(m))
                    except Exception:
                        return None
                except Exception:
                    return None

            for f in candidate_fields:
                try:
                    raw = _clean(request.POST.get(f))
                    if raw is None:
                        continue
                    if f in time_fields:
                        tval = _parse_to_time(raw)
                        if tval is None:
                            continue
                        if hasattr(rdo_obj, f):
                            try:
                                setattr(rdo_obj, f, tval)
                            except Exception:
                                logging.getLogger(__name__).exception('Falha atribuindo campo time %s', f)
                    else:
                        try:
                            parsed = int(float(str(raw)))
                        except Exception:
                            parsed = None
                        if parsed is None:
                            continue
                        if hasattr(rdo_obj, f):
                            try:
                                setattr(rdo_obj, f, parsed)
                            except Exception:
                                logging.getLogger(__name__).exception('Falha atribuindo campo inteiro %s', f)
                except Exception:
                    continue
        except Exception:
            logging.getLogger(__name__).exception('Erro processando extra_int_fields')

        try:
            us = _clean(request.POST.get('ultimo_status'))
            if us is not None and hasattr(rdo_obj, 'ultimo_status'):
                try:
                    setattr(rdo_obj, 'ultimo_status', str(us)[:255])
                except Exception:
                    logging.getLogger(__name__).exception('Falha atribuindo ultimo_status')
        except Exception:
            pass

        try:
            ep_raw = _clean(request.POST.get('ensacamento_prev'))
            if ep_raw is not None:
                ep_parsed = _parse_percent(ep_raw, as_int=True)
                if ep_parsed is not None and hasattr(rdo_obj, 'icamento_previsao'):
                    cur = getattr(rdo_obj, 'icamento_previsao', None)
                    if cur in (None, ''):
                        try:
                            setattr(rdo_obj, 'icamento_previsao', ep_parsed)
                        except Exception:
                            logging.getLogger(__name__).exception('Falha ao replicar ensacamento_previsao para icamento_previsao')
        except Exception:
            logging.getLogger(__name__).exception('Erro ao replicar ensacamento_prev -> icamento_previsao')
        tot_sol = _clean(request.POST.get('residuos_solidos'))
        assigned_total_solidos = False
        if tot_sol is not None:
            try:
                valf = float(tot_sol)
                try:
                    rdo_obj.total_solidos = Decimal(str(round(valf, 2)))
                except Exception:
                    try:
                        rdo_obj.total_solidos = int(valf)
                    except Exception:
                        rdo_obj.total_solidos = Decimal(str(round(valf, 2)))
                assigned_total_solidos = True
            except Exception:
                assigned_total_solidos = False

        if not assigned_total_solidos:
            try:
                ens_val = None
                if getattr(rdo_obj, 'ensacamento', None) is not None:
                    try:
                        ens_val = float(getattr(rdo_obj, 'ensacamento'))
                    except Exception:
                        ens_val = None
                elif ensac is not None:
                    try:
                        ens_val = float(ensac)
                    except Exception:
                        ens_val = None

                if ens_val is not None:
                    computed = round(ens_val * 0.008, 2)
                    try:
                        rdo_obj.total_solidos = Decimal(str(computed))
                    except Exception:
                        try:
                            rdo_obj.total_solidos = int(computed) if float(computed).is_integer() else Decimal(str(computed))
                        except Exception:
                            try:
                                rdo_obj.total_solidos = float(computed)
                            except Exception:
                                pass
            except Exception:
                pass
        tot_res = _clean(request.POST.get('residuos_totais'))
        if tot_res is not None:
            try:
                rdo_obj.total_residuos = int(float(tot_res))
            except ValueError:
                pass

        try:
            sentido_raw = _clean(_get_post_or_json('sentido') or _get_post_or_json('sentido_limpeza'))
        except Exception:
            sentido_raw = _clean(request.POST.get('sentido') or request.POST.get('sentido_limpeza'))
        if sentido_raw is not None:
            try:
                token = _canonicalize_sentido(sentido_raw)
            except Exception:
                token = None
            try:
                if token is not None:
                    if hasattr(rdo_obj, 'sentido_limpeza'):
                        setattr(rdo_obj, 'sentido_limpeza', token)
                    elif hasattr(rdo_obj, 'sent_limpeza'):
                        setattr(rdo_obj, 'sent_limpeza', token)
                else:
                    if hasattr(rdo_obj, 'sentido_limpeza'):
                        try:
                            setattr(rdo_obj, 'sentido_limpeza', str(sentido_raw))
                        except Exception:
                            pass
                    elif hasattr(rdo_obj, 'sent_limpeza'):
                        try:
                            setattr(rdo_obj, 'sent_limpeza', str(sentido_raw))
                        except Exception:
                            pass
            except Exception:
                pass

        obs_pt = _clean(request.POST.get('observacoes'))
        if obs_pt is not None:
            rdo_obj.observacoes_rdo_pt = obs_pt
            try:
                from deep_translator import GoogleTranslator
                try:
                    translated = GoogleTranslator(source='pt', target='en').translate(obs_pt)
                    rdo_obj.observacoes_rdo_en = translated
                except Exception:
                    pass
            except Exception:
                pass
        plan_pt = _clean(request.POST.get('planejamento') or request.POST.get('planejamento_pt'))
        if plan_pt is not None:
            rdo_obj.planejamento_pt = plan_pt
            try:
                from deep_translator import GoogleTranslator
                try:
                    translated_plan = GoogleTranslator(source='pt', target='en').translate(plan_pt)
                    if translated_plan:
                        rdo_obj.planejamento_en = translated_plan
                except Exception:
                    pass
            except Exception:
                pass

        try:
            ciente_pt = _clean(request.POST.get('ciente_observacoes') or request.POST.get('ciente_observacoes_pt') or request.POST.get('ciente') or request.POST.get('ciente_pt'))
            if ciente_pt is not None:
                rdo_obj.ciente_observacoes_pt = ciente_pt
                try:
                    from deep_translator import GoogleTranslator
                    try:
                        translated = GoogleTranslator(source='pt', target='en').translate(ciente_pt)
                        if translated:
                            rdo_obj.ciente_observacoes_en = translated
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception:
            logging.getLogger(__name__).exception('Erro processando campo ciente_observacoes')

        if not getattr(rdo_obj, 'pk', None):
                try:
                    if not getattr(rdo_obj, 'ordem_servico_id', None):
                        try:
                            ordem_servico_id = request.POST.get('ordem_servico_id') or request.POST.get('ordem_id')
                            if ordem_servico_id:
                                rdo_obj.ordem_servico = OrdemServico.objects.get(id=ordem_servico_id)
                        except Exception:
                            pass
                    if not getattr(rdo_obj, 'data', None):
                        try:
                            d = request.POST.get('data')
                            if d:
                                rdo_obj.data = datetime.strptime(d, '%Y-%m-%d').date()
                        except Exception:
                            pass
                        if not getattr(rdo_obj, 'data', None):
                            try:
                                rdo_obj.data = datetime.today().date()
                            except Exception:
                                pass
                    try:
                        _safe_save_global(rdo_obj)
                    except Exception as e:
                        try:
                            from django.db import IntegrityError as DjangoIntegrityError
                        except Exception:
                            DjangoIntegrityError = None
                        if DjangoIntegrityError is not None and isinstance(e, DjangoIntegrityError):
                            try:
                                logger = logging.getLogger(__name__)
                                logger.warning('IntegrityError when saving RDO initial save: %s. Attempting to load existing RDO.', e)
                                existing = None
                                try:
                                    if getattr(rdo_obj, 'ordem_servico', None) is not None and getattr(rdo_obj, 'rdo', None) is not None:
                                        existing = RDO.objects.filter(ordem_servico=getattr(rdo_obj, 'ordem_servico'), rdo=getattr(rdo_obj, 'rdo')).first()
                                except Exception:
                                    existing = None
                                if existing:
                                    logger.info('Found existing RDO (pk=%s) during initial save; reusing it.', getattr(existing, 'pk', None))
                                    rdo_obj = existing
                                else:
                                    logger.exception('IntegrityError saving initial RDO but no existing record found')
                                    raise
                            except Exception:
                                logger = logging.getLogger(__name__)
                                logger.exception('Error handling IntegrityError during initial RDO save')
                                raise
                        else:
                            logging.getLogger(__name__).exception('Falha ao salvar RDO antes de manipular atividades')
                            raise
                except Exception:
                    logging.getLogger(__name__).exception('Falha ao salvar RDO antes de manipular atividades')
                    raise

        try:
            ordem_obj = getattr(rdo_obj, 'ordem_servico', None)
            if ordem_obj is not None:
                prev_qs = RDO.objects.filter(ordem_servico=ordem_obj).exclude(pk=rdo_obj.pk)
                agg = prev_qs.aggregate(sum_ensac=Sum('ensacamento'), sum_ica=Sum('icamento'), sum_camba=Sum('cambagem'))
                prev_ens = int(agg.get('sum_ensac') or 0)
                prev_ica = int(agg.get('sum_ica') or 0)
                prev_camba = int(agg.get('sum_camba') or 0)

                cur_ens = 0
                try:
                    cur_ens = int(getattr(rdo_obj, 'ensacamento') or 0)
                except Exception:
                    cur_ens = 0
                cur_ica = 0
                try:
                    cur_ica = int(getattr(rdo_obj, 'icamento') or 0)
                except Exception:
                    cur_ica = 0
                cur_camba = 0
                try:
                    cur_camba = int(getattr(rdo_obj, 'cambagem') or 0)
                except Exception:
                    cur_camba = 0

                    # Removido: atribuição de totais cumulativos em `RDO`.
                    # Origem única dos acumulados agora é `RdoTanque` e o payload é preenchido
                    # a partir das agregações de `RdoTanque` mais acima.
        except Exception:
            logging.getLogger(__name__).exception('Erro ao calcular totais acumulados para RDO')

        try:
            ordem_obj = getattr(rdo_obj, 'ordem_servico', None)
            if ordem_obj is not None:
                raw_limpeza_acu = _clean(_get_post_or_json('limpeza_acu') or _get_post_or_json('percentual_limpeza_cumulativo'))
                raw_limpeza_fina_acu = _clean(_get_post_or_json('limpeza_fina_acu') or _get_post_or_json('percentual_limpeza_fina_cumulativo'))

                def _try_parse_int(v):
                    try:
                        if v is None:
                            return None
                        return int(float(str(v)))
                    except Exception:
                        return None

                provided_limpeza_acu = _try_parse_int(raw_limpeza_acu)
                provided_limpeza_fina_acu = _try_parse_int(raw_limpeza_fina_acu)

                if provided_limpeza_acu is not None or provided_limpeza_fina_acu is not None:
                    # Recebido override de acumulados, mas NÃO escrevemos em `RDO`.
                    # Se necessário, esses overrides devem ser aplicados/destinados a `RdoTanque`.
                    pass
                else:
                    prev_qs = RDO.objects.filter(ordem_servico=ordem_obj).exclude(pk=rdo_obj.pk)
                    agg = prev_qs.aggregate(sum_prev_limpeza=Sum('percentual_limpeza_diario'), sum_prev_limpeza_fina=Sum('percentual_limpeza_fina'))
                    prev_sum_limpeza = float(agg.get('sum_prev_limpeza') or 0)
                    prev_sum_limpeza_fina = float(agg.get('sum_prev_limpeza_fina') or 0)

                    try:
                        cur_daily_limpeza = float(getattr(rdo_obj, 'percentual_limpeza_diario') or getattr(rdo_obj, 'limpeza_mecanizada_diaria', 0) or 0)
                    except Exception:
                        cur_daily_limpeza = 0.0
                    try:
                        cur_daily_limpeza_fina = float(getattr(rdo_obj, 'percentual_limpeza_fina') or 0)
                    except Exception:
                        cur_daily_limpeza_fina = 0.0

                    total_limpeza_pct = prev_sum_limpeza + cur_daily_limpeza
                    total_limpeza_fina_pct = prev_sum_limpeza_fina + cur_daily_limpeza_fina

                    try:
                        total_limpeza_pct_i = int(round(total_limpeza_pct))
                    except Exception:
                        total_limpeza_pct_i = 0
                    try:
                        total_limpeza_fina_pct_i = int(round(total_limpeza_fina_pct))
                    except Exception:
                        total_limpeza_fina_pct_i = 0
                    total_limpeza_pct_i = max(0, min(100, total_limpeza_pct_i))
                    total_limpeza_fina_pct_i = max(0, min(100, total_limpeza_fina_pct_i))

                    # Não atribuir cumulativos em `RDO` — cálculo mantido apenas para referência.
        except Exception:
            logging.getLogger(__name__).exception('Erro ao calcular acumulados de limpeza para RDO')
        try:
            from decimal import Decimal, ROUND_HALF_UP
            def _to_decimal_safe(v):
                try:
                    if v is None:
                        return Decimal('0')
                    return Decimal(str(v))
                except Exception:
                    try:
                        return Decimal(float(v))
                    except Exception:
                        return Decimal('0')

            ensac_cum = _to_decimal_safe(getattr(rdo_obj, 'ensacamento_cumulativo', None) or getattr(rdo_obj, 'ensacamento', None) or 0)
            ensac_prev = _to_decimal_safe(getattr(rdo_obj, 'ensacamento_previsao', None) or 0)

            ic_cum = _to_decimal_safe(getattr(rdo_obj, 'icamento_cumulativo', None) or getattr(rdo_obj, 'icamento', None) or 0)
            ic_prev = _to_decimal_safe(getattr(rdo_obj, 'icamento_previsao', None) or 0)

            camb_cum = _to_decimal_safe(getattr(rdo_obj, 'cambagem_cumulativo', None) or getattr(rdo_obj, 'cambagem', None) or 0)
            camb_prev = _to_decimal_safe(getattr(rdo_obj, 'cambagem_previsao', None) or 0)

            def _clamp_pct(d):
                try:
                    if d is None:
                        return Decimal('0')
                    if d < 0:
                        return Decimal('0')
                    if d > 100:
                        return Decimal('100')
                    return d
                except Exception:
                    return Decimal('0')

            perc_ens = Decimal('0')
            if ensac_prev > 0:
                try:
                    perc_ens = (ensac_cum / ensac_prev) * Decimal('100')
                except Exception:
                    perc_ens = Decimal('0')
            perc_ens = _clamp_pct(perc_ens)

            perc_ic = Decimal('0')
            if ic_prev > 0:
                try:
                    perc_ic = (ic_cum / ic_prev) * Decimal('100')
                except Exception:
                    perc_ic = Decimal('0')
            perc_ic = _clamp_pct(perc_ic)

            perc_camb = Decimal('0')
            if camb_prev > 0:
                try:
                    perc_camb = (camb_cum / camb_prev) * Decimal('100')
                except Exception:
                    perc_camb = Decimal('0')
            perc_camb = _clamp_pct(perc_camb)

            try:
                perc_ens_q = perc_ens.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            except Exception:
                perc_ens_q = perc_ens
            try:
                perc_ic_q = perc_ic.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            except Exception:
                perc_ic_q = perc_ic
            try:
                perc_camb_q = perc_camb.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            except Exception:
                perc_camb_q = perc_camb

            try:
                if hasattr(rdo_obj, 'percentual_ensacamento'):
                    rdo_obj.percentual_ensacamento = perc_ens_q
            except Exception:
                logging.getLogger(__name__).exception('Falha atribuindo percentual_ensacamento')
            try:
                if hasattr(rdo_obj, 'percentual_icamento'):
                    rdo_obj.percentual_icamento = perc_ic_q
            except Exception:
                logging.getLogger(__name__).exception('Falha atribuindo percentual_icamento')
            try:
                if hasattr(rdo_obj, 'percentual_cambagem'):
                    rdo_obj.percentual_cambagem = perc_camb_q
            except Exception:
                logging.getLogger(__name__).exception('Falha atribuindo percentual_cambagem')

            try:
                ensac_prev = _to_decimal_safe(getattr(rdo_obj, 'ensacamento_previsao', None) or 0)
                ic_prev = _to_decimal_safe(getattr(rdo_obj, 'icamento_previsao', None) or 0)
                camb_prev = _to_decimal_safe(getattr(rdo_obj, 'cambagem_previsao', None) or 0)

                try:
                    cur_ens = _to_decimal_safe(getattr(rdo_obj, 'ensacamento', None) or 0)
                except Exception:
                    cur_ens = Decimal('0')
                try:
                    cur_ic = _to_decimal_safe(getattr(rdo_obj, 'icamento', None) or 0)
                except Exception:
                    cur_ic = Decimal('0')
                try:
                    cur_camb = _to_decimal_safe(getattr(rdo_obj, 'cambagem', None) or 0)
                except Exception:
                    cur_camb = Decimal('0')

                ensac_cum = _to_decimal_safe(getattr(rdo_obj, 'ensacamento_cumulativo', None) or cur_ens)
                ic_cum = _to_decimal_safe(getattr(rdo_obj, 'icamento_cumulativo', None) or cur_ic)
                camb_cum = _to_decimal_safe(getattr(rdo_obj, 'cambagem_cumulativo', None) or cur_camb)

                def _pct_from(dividend, divisor):
                    try:
                        if divisor is None or divisor == 0:
                            return Decimal('0')
                        return _clamp_pct((dividend / divisor) * Decimal('100'))
                    except Exception:
                        return Decimal('0')

                perc_ens_day = _pct_from(cur_ens, ensac_prev)
                perc_ic_day = _pct_from(cur_ic, ic_prev)
                perc_camb_day = _pct_from(cur_camb, camb_prev)

                perc_ens_cum = _pct_from(ensac_cum, ensac_prev)
                perc_ic_cum = _pct_from(ic_cum, ic_prev)
                perc_camb_cum = _pct_from(camb_cum, camb_prev)

                try:
                    perc_ens_day_q = perc_ens_day.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                except Exception:
                    perc_ens_day_q = perc_ens_day
                try:
                    perc_ic_day_q = perc_ic_day.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                except Exception:
                    perc_ic_day_q = perc_ic_day
                try:
                    perc_camb_day_q = perc_camb_day.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                except Exception:
                    perc_camb_day_q = perc_camb_day

                try:
                    perc_ens_cum_q = perc_ens_cum.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                except Exception:
                    perc_ens_cum_q = perc_ens_cum
                try:
                    perc_ic_cum_q = perc_ic_cum.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                except Exception:
                    perc_ic_cum_q = perc_ic_cum
                try:
                    perc_camb_cum_q = perc_camb_cum.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                except Exception:
                    perc_camb_cum_q = perc_camb_cum

                try:
                    if hasattr(rdo_obj, 'percentual_ensacamento'):
                        rdo_obj.percentual_ensacamento = perc_ens_day_q
                except Exception:
                    logging.getLogger(__name__).exception('Falha atribuindo percentual_ensacamento (diário)')
                try:
                    if hasattr(rdo_obj, 'percentual_icamento'):
                        rdo_obj.percentual_icamento = perc_ic_day_q
                except Exception:
                    logging.getLogger(__name__).exception('Falha atribuindo percentual_icamento (diário)')
                try:
                    if hasattr(rdo_obj, 'percentual_cambagem'):
                        rdo_obj.percentual_cambagem = perc_camb_day_q
                except Exception:
                    logging.getLogger(__name__).exception('Falha atribuindo percentual_cambagem (diário)')

                # NOTA: não atribuir percentuais cumulativos em `RDO` aqui; usar `RdoTanque` como fonte.

                pesos = {
                    'percentual_limpeza': Decimal('70'),
                    'percentual_ensacamento': Decimal('7'),
                    'percentual_icamento': Decimal('7'),
                    'percentual_cambagem': Decimal('5'),
                    'percentual_limpeza_fina': Decimal('6'),
                }

                try:
                    lim_day = _to_decimal_safe(getattr(rdo_obj, 'percentual_limpeza', None) or 0)
                except Exception:
                    lim_day = Decimal('0')
                try:
                    lim_fina_day = _to_decimal_safe(getattr(rdo_obj, 'percentual_limpeza_fina', None) or 0)
                except Exception:
                    lim_fina_day = Decimal('0')

                vals_day = {
                    'percentual_limpeza': lim_day,
                    'percentual_ensacamento': perc_ens_day_q,
                    'percentual_icamento': perc_ic_day_q,
                    'percentual_cambagem': perc_camb_day_q,
                    'percentual_limpeza_fina': lim_fina_day,
                }

                weighted_day = Decimal('0')
                total_w = Decimal('0')
                for k,w in pesos.items():
                    try:
                        v = vals_day.get(k, Decimal('0')) or Decimal('0')
                        weighted_day += (v * w)
                        total_w += w
                    except Exception:
                        continue
                perc_avanco_day = Decimal('0')
                if total_w > 0:
                    try:
                        perc_avanco_day = (weighted_day / total_w)
                    except Exception:
                        perc_avanco_day = Decimal('0')
                perc_avanco_day = _clamp_pct(perc_avanco_day)

                try:
                    perc_avanco_day_i = int(perc_avanco_day.to_integral_value(rounding=ROUND_HALF_UP))
                except Exception:
                    try:
                        perc_avanco_day_i = int(round(float(perc_avanco_day)))
                    except Exception:
                        perc_avanco_day_i = 0

                try:
                    if hasattr(rdo_obj, 'percentual_avanco'):
                        rdo_obj.percentual_avanco = perc_avanco_day_i
                except Exception:
                    logging.getLogger(__name__).exception('Falha atribuindo percentual_avanco (diário)')

                try:
                    lim_cum = _to_decimal_safe(getattr(rdo_obj, 'percentual_limpeza_cumulativo', None) or 0)
                except Exception:
                    lim_cum = Decimal('0')
                try:
                    lim_fina_cum = _to_decimal_safe(getattr(rdo_obj, 'percentual_limpeza_fina_cumulativo', None) or 0)
                except Exception:
                    lim_fina_cum = Decimal('0')

                vals_cum = {
                    'percentual_limpeza': lim_cum,
                    'percentual_ensacamento': perc_ens_cum_q,
                    'percentual_icamento': perc_ic_cum_q,
                    'percentual_cambagem': perc_camb_cum_q,
                    'percentual_limpeza_fina': lim_fina_cum,
                }

                weighted_cum = Decimal('0')
                total_w2 = Decimal('0')
                for k,w in pesos.items():
                    try:
                        v = vals_cum.get(k, Decimal('0')) or Decimal('0')
                        weighted_cum += (v * w)
                        total_w2 += w
                    except Exception:
                        continue
                perc_avanco_cum = Decimal('0')
                if total_w2 > 0:
                    try:
                        perc_avanco_cum = (weighted_cum / total_w2)
                    except Exception:
                        perc_avanco_cum = Decimal('0')
                perc_avanco_cum = _clamp_pct(perc_avanco_cum)

                try:
                    perc_avanco_cum_i = int(perc_avanco_cum.to_integral_value(rounding=ROUND_HALF_UP))
                except Exception:
                    try:
                        perc_avanco_cum_i = int(round(float(perc_avanco_cum)))
                    except Exception:
                        perc_avanco_cum_i = 0

                # NOTA: não atribuir `percentual_avanco_cumulativo` em `RDO`.
            except Exception:
                logging.getLogger(__name__).exception('Erro calculando percentuais derivados server-side')

            try:
                logger.info('_apply_post_to_rdo before saving derived percent fields: percentual_limpeza=%s, percentual_limpeza_cumulativo=%s, percentual_limpeza_fina=%s, percentual_limpeza_fina_cumulativo=%s, percentual_avanco=%s, percentual_avanco_cumulativo=%s',
                            getattr(rdo_obj, 'percentual_limpeza', None), getattr(rdo_obj, 'percentual_limpeza_cumulativo', None), getattr(rdo_obj, 'percentual_limpeza_fina', None), getattr(rdo_obj, 'percentual_limpeza_fina_cumulativo', None), getattr(rdo_obj, 'percentual_avanco', None), getattr(rdo_obj, 'percentual_avanco_cumulativo', None))
                _safe_save_global(rdo_obj)
            except Exception:
                logging.getLogger(__name__).exception('Falha ao salvar RDO após calcular percentuais')
        except Exception:
            logging.getLogger(__name__).exception('Erro ao calcular percentuais server-side')

        try:
            atividades_nome = request.POST.getlist('atividade_nome[]') if hasattr(request.POST,'getlist') else []
            atividades_inicio = request.POST.getlist('atividade_inicio[]') if hasattr(request.POST,'getlist') else []
            atividades_fim = request.POST.getlist('atividade_fim[]') if hasattr(request.POST,'getlist') else []
            comentarios_pt = request.POST.getlist('atividade_comentario_pt[]') if hasattr(request.POST,'getlist') else []
        except Exception:
            atividades_nome, atividades_inicio, atividades_fim, comentarios_pt = [], [], [], []

        rdo_obj.atividades_rdo.all().delete()
        MAX_ATIV = 20
        for idx, nome in enumerate(atividades_nome[:MAX_ATIV]):
            nome_clean = _clean(nome)
            if nome_clean is not None:
                try:
                    nome_clean = str(nome_clean).strip()
                except Exception:
                    pass
            if not nome_clean:
                continue
            def parse_time(val):
                if not val:
                    return None
                try:
                    return datetime.strptime(val, '%H:%M').time()
                except Exception:
                    return None
            inicio_val = parse_time(atividades_inicio[idx] if idx < len(atividades_inicio) else None)
            fim_val = parse_time(atividades_fim[idx] if idx < len(atividades_fim) else None)
            comentario_val = _clean(comentarios_pt[idx]) if idx < len(comentarios_pt) else None
            RDOAtividade.objects.create(
                rdo=rdo_obj,
                ordem=idx,
                atividade=nome_clean,
                inicio=inicio_val,
                fim=fim_val,
                comentario_pt=comentario_val
            )

        if comentarios_pt:
            first_com_pt = _clean(comentarios_pt[0])
            if first_com_pt is not None:
                rdo_obj.comentario_pt = first_com_pt

        pt_abertura_raw = request.POST.get('pt_abertura')
        if pt_abertura_raw in ('sim', 'nao'):
            rdo_obj.exist_pt = True if pt_abertura_raw == 'sim' else False

        turnos_raw = request.POST.getlist('pt_turnos[]') if hasattr(request.POST, 'getlist') else []
        turno_map = {'manha': 'Manhã','tarde': 'Tarde','noite': 'Noite'}
        mapped_turnos = [turno_map[t] for t in turnos_raw if t in turno_map]
        if mapped_turnos:
            rdo_obj.select_turnos = mapped_turnos
        elif pt_abertura_raw in ('sim', 'nao') and not mapped_turnos:
            rdo_obj.select_turnos = []

        pt_manha = _clean(request.POST.get('pt_num_manha'))
        pt_tarde = _clean(request.POST.get('pt_num_tarde'))
        pt_noite = _clean(request.POST.get('pt_num_noite'))
        if pt_manha is not None:
            rdo_obj.pt_manha = pt_manha
        if pt_tarde is not None:
            rdo_obj.pt_tarde = pt_tarde
        if pt_noite is not None:
            rdo_obj.pt_noite = pt_noite
        if pt_abertura_raw == 'nao':
            rdo_obj.pt_manha = None
            rdo_obj.pt_tarde = None
            rdo_obj.pt_noite = None
            rdo_obj.select_turnos = []

        try:
            equipe_nomes = request.POST.getlist('equipe_nome[]') if hasattr(request.POST, 'getlist') else []
            equipe_funcoes = request.POST.getlist('equipe_funcao[]') if hasattr(request.POST, 'getlist') else []
            equipe_em_servico = request.POST.getlist('equipe_em_servico[]') if hasattr(request.POST, 'getlist') else []
            equipe_pessoa_ids = request.POST.getlist('equipe_pessoa_id[]') if hasattr(request.POST, 'getlist') else []
        except Exception:
            equipe_nomes, equipe_funcoes, equipe_em_servico, equipe_pessoa_ids = [], [], [], []

        def _norm_nome(n):
            if n is None: return None
            s = str(n).strip()
            return s if s != '' else None
        def _norm_func(f):
            if f is None: return None
            s = str(f).strip()
            if s == '': return None
            return s[:50]

        membros_clean = []
        funcoes_clean = []
        for idx in range(len(equipe_nomes)):
            n = _norm_nome(equipe_nomes[idx])
            f = _norm_func(equipe_funcoes[idx]) if idx < len(equipe_funcoes) else None
            if n is None and f is None:
                continue
            membros_clean.append(n)
            funcoes_clean.append(f)

        # POB é derivado automaticamente da quantidade de membros informados na equipe.
        try:
            if hasattr(rdo_obj, 'pob'):
                rdo_obj.pob = len(membros_clean)
        except Exception:
            pass

        try:
            if hasattr(rdo_obj, 'membros'):
                try:
                    current = getattr(rdo_obj, 'membros')
                    setattr(rdo_obj, 'membros', membros_clean if isinstance(current, (list, tuple)) or membros_clean == [] else json.dumps(membros_clean))
                except Exception:
                    setattr(rdo_obj, 'membros', json.dumps(membros_clean))
        except Exception:
            pass

        try:
            if hasattr(rdo_obj, 'membros_equipe'):
                rdo_obj.membros_equipe.all().delete()
                total = max(len(equipe_nomes), len(equipe_funcoes))
                def _parse_bool(v):
                    s = str(v).strip().lower()
                    return s in ('1','true','on','yes','sim','y','t')
                def _cmp_nome(a, b):
                    try:
                        sa = str(a).strip().lower() if a is not None else ''
                        sb = str(b).strip().lower() if b is not None else ''
                        return sa == sb and sa != ''
                    except Exception:
                        return False
                for i in range(total):
                    n = _norm_nome(equipe_nomes[i]) if i < len(equipe_nomes) else None
                    f = _norm_func(equipe_funcoes[i]) if i < len(equipe_funcoes) else None
                    es = _parse_bool(equipe_em_servico[i]) if i < len(equipe_em_servico) else True
                    pessoa = None
                    try:
                        pid = equipe_pessoa_ids[i] if i < len(equipe_pessoa_ids) else None
                        if pid and str(pid).isdigit():
                            pessoa = Pessoa.objects.filter(pk=int(pid)).first()
                    except Exception:
                        pessoa = None
                    # Se o nome foi alterado no formulário e não bate com o ID enviado,
                    # ignorar o ID antigo e preferir resolver pelo novo nome.
                    try:
                        if pessoa is not None and n and not _cmp_nome(n, getattr(pessoa, 'nome', None)):
                            pessoa = None
                    except Exception:
                        pass
                    if pessoa is None and n:
                        try:
                            pessoa = Pessoa.objects.filter(nome__iexact=n).first()
                        except Exception:
                            pessoa = None
                    RDOMembroEquipe.objects.create(
                        rdo=rdo_obj,
                        pessoa=pessoa,
                        nome=None if pessoa else n,
                        funcao=f,
                        em_servico=bool(es),
                        ordem=i,
                    )
        except Exception:
            logging.getLogger(__name__).exception('Falha ao persistir equipe relacional do RDO')

        try:
            if hasattr(rdo_obj, 'funcoes'):
                try:
                    current2 = getattr(rdo_obj, 'funcoes')
                    setattr(rdo_obj, 'funcoes', funcoes_clean if isinstance(current2, (list, tuple)) or funcoes_clean == [] else json.dumps(funcoes_clean))
                except Exception:
                    setattr(rdo_obj, 'funcoes', json.dumps(funcoes_clean))
        except Exception:
            pass

        try:
            if hasattr(rdo_obj, 'funcoes_list'):
                try:
                    rdo_obj.funcoes_list = json.dumps(funcoes_clean)
                except Exception:
                    rdo_obj.funcoes_list = None
        except Exception:
            pass

        fotos_saved = []
        files = []
        try:
            candidate_keys = ['fotos', 'fotos[]']
            for i in range(0, 10):
                candidate_keys.append(f'fotos[{i}]')
            if hasattr(request.FILES, 'getlist'):
                for k in candidate_keys:
                    try:
                        lst = request.FILES.getlist(k)
                    except Exception:
                        lst = []
                    if lst:
                        files.extend(list(lst))
            if not files:
                try:
                    single = request.FILES.get('fotos') if hasattr(request, 'FILES') else None
                    if single:
                        files.append(single)
                except Exception:
                    pass
            if not files:
                for i in range(1, 6):
                    try:
                        f = request.FILES.get(f'foto{i}') if hasattr(request, 'FILES') else None
                    except Exception:
                        f = None
                    if f:
                        files.append(f)
        except Exception:
            files = []

        try:
            unique_files = []
            seen = set()
            for f in (files or []):
                try:
                    fname = getattr(f, 'name', None)
                    fsize = getattr(f, 'size', None)
                    key = (fname, fsize)
                except Exception:
                    key = None
                if key is None:
                    if f not in unique_files:
                        unique_files.append(f)
                else:
                    if key in seen:
                        continue
                    seen.add(key)
                    unique_files.append(f)
            files = unique_files
        except Exception:
            pass

        is_file_field = False
        try:
            fld = None
            try:
                fld = rdo_obj._meta.get_field('fotos')
            except Exception:
                fld = None
            from django.db.models import FileField, ImageField
            if fld is not None and isinstance(fld, (FileField, ImageField)):
                is_file_field = True
        except Exception:
            is_file_field = False

        fotos_to_remove = []
        try:
            if hasattr(request.POST, 'getlist'):
                fotos_to_remove = request.POST.getlist('fotos_remove[]') or request.POST.getlist('fotos_remove') or []
            else:
                v = request.POST.get('fotos_remove') if hasattr(request, 'POST') else None
                if v:
                    fotos_to_remove = [x.strip() for x in v.split(',') if x.strip()]
        except Exception:
            fotos_to_remove = []

        try:
            slot_names = [f'fotos_{i}' for i in range(1, 6)]
            normalized_remove = [str(x).strip() for x in fotos_to_remove if x is not None]
            for rem in normalized_remove:
                if not rem:
                    continue
                s = rem.lower()
                import re
                m = re.search(r'(?:fotos?_?|-?)(\d{1,2})$', s)
                if m:
                    try:
                        idx = int(m.group(1))
                        if 1 <= idx <= 5:
                            fname = f'fotos_{idx}'
                            try:
                                cur_field = getattr(rdo_obj, fname, None)
                                if cur_field:
                                    try:
                                        cur_field.delete(save=False)
                                    except Exception:
                                        try:
                                            name = getattr(cur_field, 'name', None)
                                            if name:
                                                default_storage.delete(name)
                                        except Exception:
                                            pass
                                try:
                                    setattr(rdo_obj, fname, None)
                                except Exception:
                                    pass
                            except Exception:
                                pass
                    except Exception:
                        pass
        except Exception:
            pass

        try:
            use_rdofoto = hasattr(rdo_obj, 'fotos_rdo')
            if fotos_to_remove and use_rdofoto:
                _logger = logging.getLogger(__name__)

                def _parse_int(v):
                    try:
                        return int(v)
                    except Exception:
                        return None

                def _parse_decimal(v):
                    return _coerce_decimal_value(v)

                post = request.POST
                attrs = {}

                mapping = {
                    'tanque_codigo': 'tanque_codigo',
                    'tanque_nome': 'nome_tanque',
                    'tipo_tanque': 'tipo_tanque',
                    'numero_compartimento': 'numero_compartimentos',
                    'gavetas': 'gavetas',
                    'patamar': 'patamares',
                    'volume_tanque_exec': 'volume_tanque_exec',
                    'servico_exec': 'servico_exec',
                    'metodo_exec': 'metodo_exec',
                    'espaco_confinado': 'espaco_confinado',
                    'operadores_simultaneos': 'operadores_simultaneos',
                    'h2s_ppm': 'h2s_ppm',
                    'lel': 'lel',
                    'co_ppm': 'co_ppm',
                    'o2_percent': 'o2_percent',
                    'total_n_efetivo_confinado': 'total_n_efetivo_confinado',
                    'tempo_bomba': 'tempo_bomba',
                    'ensacamento_prev': 'ensacamento_prev',
                    'icamento_prev': 'icamento_prev',
                    'cambagem_prev': 'cambagem_prev',
                    'ensacamento_dia': 'ensacamento_dia',
                    'icamento_dia': 'icamento_dia',
                    'cambagem_dia': 'cambagem_dia',
                    'tambores_dia': 'tambores_dia',
                    'tambores_acu': 'tambores_cumulativo',
                    'tambores_cumulativo': 'tambores_cumulativo',
                    'residuos_solidos': 'residuos_solidos',
                    'residuos_totais': 'residuos_totais',
                    'bombeio': 'bombeio',
                    'total_liquido': 'total_liquido',
                    'avanco_limpeza': 'avanco_limpeza',
                    'avanco_limpeza_fina': 'avanco_limpeza_fina',
                    'sentido_limpeza': 'sentido_limpeza',
                    'percentual_limpeza_diario': 'percentual_limpeza_diario',
                    'percentual_limpeza_cumulativo': 'percentual_limpeza_cumulativo',
                    'percentual_limpeza_fina': 'percentual_limpeza_fina',
                    'percentual_limpeza_fina_diario': 'percentual_limpeza_fina_diario',
                    'percentual_limpeza_fina_cumulativo': 'percentual_limpeza_fina_cumulativo',
                    'percentual_ensacamento': 'percentual_ensacamento',
                    'percentual_icamento': 'percentual_icamento',
                    'percentual_cambagem': 'percentual_cambagem',
                    'percentual_avanco': 'percentual_avanco',
                    'compartimentos_avanco_json': 'compartimentos_avanco_json',
                }

                int_fields = set([
                    'numero_compartimentos', 'gavetas', 'patamares',
                    'operadores_simultaneos', 'total_n_efetivo_confinado',
                    'ensacamento_dia', 'icamento_dia', 'cambagem_dia', 'tambores_dia', 'tambores_cumulativo',
                    'total_liquido',
                    'limpeza_mecanizada_cumulativa', 'limpeza_fina_cumulativa',
                    'percentual_limpeza_fina', 'percentual_limpeza_fina_cumulativo',
                    'percentual_limpeza_cumulativo',
                    'ensacamento_prev', 'icamento_prev', 'cambagem_prev',
                ])
                decimal_fields = set([
                    'volume_tanque_exec', 'h2s_ppm', 'lel', 'co_ppm', 'o2_percent', 'tempo_bomba',
                    'residuos_solidos', 'residuos_totais', 'bombeio',
                    'limpeza_mecanizada_diaria', 'limpeza_fina_diaria',
                    'percentual_limpeza_diario', 'percentual_limpeza_fina_diario',
                    'percentual_ensacamento', 'percentual_icamento', 'percentual_cambagem',
                    'percentual_avanco',
                ])

                for post_key, model_key in mapping.items():
                    if post_key in post:
                        val = post.get(post_key)
                        if val is None or val == '':
                            continue
                        if model_key in int_fields:
                            parsed = _parse_int(val)
                            if parsed is not None:
                                attrs[model_key] = parsed
                        elif model_key in decimal_fields:
                            parsed = _parse_decimal(val)
                            if parsed is not None:
                                attrs[model_key] = parsed
                        else:
                            attrs[model_key] = val

                try:
                    if 'sentido_limpeza' in attrs and attrs.get('sentido_limpeza') is not None:
                        try:
                            canon = _canonicalize_sentido(attrs.get('sentido_limpeza'))
                            if canon:
                                attrs['sentido_limpeza'] = canon
                        except Exception:
                            pass

                    try:
                        # Checar duplicidade apenas dentro do mesmo RDO (antes checava por Ordem de Serviço inteira).
                        codigo_check = (attrs.get('tanque_codigo') or '')
                        nome_check = (attrs.get('nome_tanque') or '')
                        codigo_check = codigo_check.strip() if isinstance(codigo_check, str) else ''
                        nome_check = nome_check.strip() if isinstance(nome_check, str) else ''
                        if (codigo_check or nome_check) and getattr(rdo_obj, 'id', None) is not None:
                            from django.db.models import Q
                            dup_q = Q()
                            if codigo_check:
                                dup_q |= Q(rdo=rdo_obj, tanque_codigo__iexact=codigo_check)
                            if nome_check:
                                dup_q |= Q(rdo=rdo_obj, nome_tanque__iexact=nome_check)
                            if dup_q and RdoTanque.objects.filter(dup_q).exists():
                                return JsonResponse({'success': False, 'error': 'Já existe um tanque com o mesmo código ou nome neste RDO.'}, status=400)
                    except Exception:
                        logging.getLogger(__name__).exception('Erro ao checar duplicidade de tanque antes de criar via _apply_post_to_rdo')

                    tank = RdoTanque.objects.create(rdo=rdo_obj, **attrs)
                    logger.info('Created RdoTanque %s for RDO %s', tank.id, rdo_obj.id)
                    return JsonResponse({'success': True, 'id': tank.id, 'tanque': {
                        'id': tank.id,
                        'tanque_codigo': tank.tanque_codigo,
                        'nome_tanque': tank.nome_tanque,
                    }})
                except Exception as e:
                    logger.exception('Error creating RdoTanque for RDO %s: %s', getattr(rdo_obj, 'id', None), e)
                    return JsonResponse({'success': False, 'error': 'Could not create tank'}, status=500)
                except Exception:
                    _logger.exception('Error processing fotos_to_remove for RDOFoto')
        except Exception:
            pass

        try:
            has_slot = any(hasattr(rdo_obj, f'fotos_{i}') for i in range(1, 6))
            if has_slot and files:
                slot_fields = [f'fotos_{i}' for i in range(1, 6)]
                empty_slots = []
                for idx, fname in enumerate(slot_fields):
                    try:
                        cur = getattr(rdo_obj, fname, None)
                        cur_name = getattr(cur, 'name', None) if cur is not None else None
                        if not cur_name:
                            empty_slots.append((idx, fname))
                    except Exception:
                        empty_slots.append((idx, fname))

                fi = 0
                for slot_idx, slot_name in empty_slots:
                    if fi >= len(files):
                        break
                    f = files[fi]
                    try:
                        try:
                            field_obj = getattr(rdo_obj.__class__, slot_name)
                        except Exception:
                            field_obj = None
                        save_name = f'rdos/{datetime.now().strftime("%Y%m%d%H%M%S%f")}_{f.name}'
                        try:
                            dest_field = getattr(rdo_obj, slot_name)
                            try:
                                dest_field.save(save_name, ContentFile(f.read()), save=False)
                            except Exception:
                                try:
                                    saved_name = default_storage.save(save_name, ContentFile(f.read()))
                                    setattr(rdo_obj, slot_name, saved_name)
                                except Exception:
                                    pass
                        except Exception:
                            try:
                                saved_name = default_storage.save(save_name, ContentFile(f.read()))
                                try:
                                    setattr(rdo_obj, slot_name, saved_name)
                                except Exception:
                                    pass
                            except Exception:
                                pass
                    except Exception:
                        pass
                    finally:
                        fi += 1
        except Exception:
            pass

        try:
            if is_file_field:
                try:
                    cur = getattr(rdo_obj, 'fotos')
                except Exception:
                    cur = None
                try:
                    cur_name = getattr(cur, 'name', None) if cur else None
                except Exception:
                    cur_name = None
                if fotos_to_remove and cur_name:
                    try:
                        cur_name_str = str(cur_name)
                    except Exception:
                        cur_name_str = ''
                    try:
                        cur_basename = cur_name_str.split('/')[-1] if cur_name_str else ''
                    except Exception:
                        cur_basename = ''
                    for rem in fotos_to_remove:
                        try:
                            srem = str(rem or '').strip()
                            if not srem:
                                continue
                            matched = False
                            if srem == cur_name_str:
                                matched = True
                            if not matched and cur_basename and (srem == cur_basename or srem.endswith('/' + cur_basename) or srem.endswith(cur_basename)):
                                matched = True
                            if not matched and srem.startswith('http'):
                                try:
                                    if '/media/' in srem:
                                        after = srem.split('/media/', 1)[1]
                                        if after == cur_name_str or after == cur_basename or after.endswith('/' + cur_basename):
                                            matched = True
                                    if not matched and cur_basename and srem.split('?')[0].endswith('/' + cur_basename):
                                        matched = True
                                except Exception:
                                    pass
                            if not matched and srem in (str(0), str(1)):
                                matched = True
                            if matched:
                                try:
                                    rdo_obj.fotos.delete(save=False)
                                except Exception:
                                    pass
                                try:
                                    rdo_obj.fotos = None
                                except Exception:
                                    pass
                                break
                        except Exception:
                            continue
                if files:
                    try:
                        f = files[0]
                        name = f'rdos/{datetime.now().strftime("%Y%m%d%H%M%S%f")}_{f.name}'
                        try:
                            rdo_obj.fotos.save(name, ContentFile(f.read()), save=False)
                        except Exception:
                            try:
                                saved_name = default_storage.save(name, ContentFile(f.read()))
                                rdo_obj.fotos = saved_name
                            except Exception:
                                pass
                    except Exception:
                        pass
            else:
                fotos_saved = []
                try:
                    for f in files:
                        try:
                            name = default_storage.save(f'rdos/{datetime.now().strftime("%Y%m%d%H%M%S%f")}_{f.name}', ContentFile(f.read()))
                            fotos_saved.append(default_storage.url(name) if hasattr(default_storage, 'url') else name)
                        except Exception:
                            logging.getLogger(__name__).exception('Falha salvando foto do RDO')
                except Exception:
                    fotos_saved = []

                cur = getattr(rdo_obj, 'fotos', None)
                existing = []
                try:
                    if isinstance(cur, (list, tuple)):
                        existing = list(cur)
                    elif isinstance(cur, str) and cur.strip().startswith('['):
                        existing = json.loads(cur)
                    elif isinstance(cur, str) and cur.strip():
                        existing = [ln for ln in cur.splitlines() if ln.strip()]
                except Exception:
                    existing = []

                if fotos_to_remove:
                    normalized_remove = [str(x).strip() for x in fotos_to_remove if x is not None]
                    filtered = []
                    for idx, item in enumerate(existing):
                        try:
                            if str(item) in normalized_remove:
                                continue
                            if any((str(i) == str(idx) or str(i) == str(idx+1)) for i in normalized_remove):
                                continue
                        except Exception:
                            pass
                        filtered.append(item)
                    existing = filtered

                combined = list(existing) + list(fotos_saved)
                deduped = []
                seen_urls = set()
                for it in combined:
                    try:
                        s = str(it)
                    except Exception:
                        s = None
                    if not s:
                        continue
                    if s in seen_urls:
                        continue
                    seen_urls.add(s)
                    deduped.append(s)
                existing = deduped

                try:
                    if isinstance(cur, str) and cur.strip().startswith('['):
                        setattr(rdo_obj, 'fotos', json.dumps(existing))
                    else:
                        setattr(rdo_obj, 'fotos', existing)
                except Exception:
                    setattr(rdo_obj, 'fotos', existing)
        except Exception:
            pass

        try:
            fotos_new = []
            try:
                for i in range(1, 6):
                    try:
                        f = getattr(rdo_obj, f'fotos_{i}', None)
                    except Exception:
                        f = None
                    if not f:
                        continue
                    url = None
                    try:
                        url = getattr(f, 'url', None)
                    except Exception:
                        url = None
                    if not url:
                        try:
                            name = getattr(f, 'name', None)
                            if name and hasattr(default_storage, 'url'):
                                try:
                                    url = default_storage.url(name)
                                except Exception:
                                    url = name
                            else:
                                url = name or str(f)
                        except Exception:
                            url = str(f)
                    if url:
                        fotos_new.append(url)
            except Exception:
                fotos_new = []

            if not fotos_new:
                try:
                    fotos_field = getattr(rdo_obj, 'fotos', None)
                    if fotos_field is None:
                        fotos_new = []
                    elif isinstance(fotos_field, (list, tuple)):
                        fotos_new = list(fotos_field)
                    elif isinstance(fotos_field, str):
                        s = fotos_field.strip()
                        if s.startswith('['):
                            try:
                                fotos_new = json.loads(s)
                            except Exception:
                                fotos_new = [ln for ln in s.splitlines() if ln.strip()]
                        else:
                            fotos_new = [ln for ln in s.splitlines() if ln.strip()]
                    else:
                        try:
                            url = getattr(fotos_field, 'url', None)
                        except Exception:
                            url = None
                        if url:
                            fotos_new = [url]
                        else:
                            fotos_new = []
                except Exception:
                    fotos_new = []

            try:
                deduped = []
                seen_urls = set()
                for it in (fotos_new or []):
                    try:
                        s = str(it)
                    except Exception:
                        s = None
                    if not s:
                        continue
                    if s in seen_urls:
                        continue
                    seen_urls.add(s)
                    deduped.append(s)
                fotos_new = deduped
                if hasattr(rdo_obj, 'fotos_json'):
                    try:
                        rdo_obj.fotos_json = json.dumps(fotos_new)
                    except Exception:
                        try:
                            setattr(rdo_obj, 'fotos_json', json.dumps(fotos_new))
                        except Exception:
                            pass
            except Exception:
                pass
        except Exception:
            pass

        entrada_list = []
        saida_list = []
        try:
            try:
                _logger = logging.getLogger(__name__)
                if hasattr(request, 'POST'):
                    try:
                        post_keys = list(request.POST.keys())
                        _logger.info('DEBUG _apply_post_to_rdo POST keys: %s', post_keys)
                    except Exception:
                        _logger.info('DEBUG _apply_post_to_rdo could not list POST keys')
                    try:
                        _logger.info('DEBUG entrada_confinado[] getlist: %s', request.POST.getlist('entrada_confinado[]') if hasattr(request.POST, 'getlist') else 'no-getlist')
                        _logger.info('DEBUG entrada_confinado getlist: %s', request.POST.getlist('entrada_confinado') if hasattr(request.POST, 'getlist') else 'no-getlist')
                        _logger.info('DEBUG saida_confinado[] getlist: %s', request.POST.getlist('saida_confinado[]') if hasattr(request.POST, 'getlist') else 'no-getlist')
                        _logger.info('DEBUG saida_confinado getlist: %s', request.POST.getlist('saida_confinado') if hasattr(request.POST, 'getlist') else 'no-getlist')
                    except Exception:
                        _logger.exception('DEBUG failed reading entrada/saida lists from POST')
            except Exception:
                try:
                    logging.getLogger(__name__).exception('DEBUG logger setup failed inside _apply_post_to_rdo')
                except Exception:
                    pass
            if hasattr(request.POST, 'getlist'):
                entrada_list = request.POST.getlist('entrada_confinado[]') or request.POST.getlist('entrada_confinado') or []
                saida_list = request.POST.getlist('saida_confinado[]') or request.POST.getlist('saida_confinado') or []
            else:
                v1 = request.POST.get('entrada_confinado')
                v2 = request.POST.get('saida_confinado')
                if v1: entrada_list = [v1]
                if v2: saida_list = [v2]
        except Exception:
            entrada_list, saida_list = [], []

        def _first_valid_time(lst):
            for val in lst:
                if not val:
                    continue
                s = str(val).strip()
                if not s:
                    continue
                try:
                    return datetime.strptime(s, '%H:%M').time()
                except Exception:
                    try:
                        return datetime.strptime(s, '%H:%M:%S').time()
                    except Exception:
                        continue
            return None

        ent_time = _first_valid_time(entrada_list)
        sai_time = _first_valid_time(saida_list)
        # Somente aplicar alterações se o POST contiver ao menos um horário válido.
        has_any_ec = False
        try:
            for v in (entrada_list or []) + (saida_list or []):
                try:
                    if v and str(v).strip():
                        has_any_ec = True
                        break
                except Exception:
                    continue
        except Exception:
            has_any_ec = False

        if has_any_ec:
            try:
                if hasattr(rdo_obj, 'entrada_confinado'):
                    rdo_obj.entrada_confinado = ent_time
            except Exception:
                pass
            try:
                if hasattr(rdo_obj, 'saida_confinado'):
                    rdo_obj.saida_confinado = sai_time
            except Exception:
                pass
            try:
                for i in range(6):
                    e = None; s = None
                    try:
                        e = _first_valid_time([entrada_list[i]]) if i < len(entrada_list) else None
                    except Exception:
                        e = None
                    try:
                        s = _first_valid_time([saida_list[i]]) if i < len(saida_list) else None
                    except Exception:
                        s = None
                    try:
                        setattr(rdo_obj, f'entrada_confinado_{i+1}', e)
                    except Exception:
                        pass
                    try:
                        setattr(rdo_obj, f'saida_confinado_{i+1}', s)
                    except Exception:
                        pass
            except Exception:
                pass

        _safe_save_global(rdo_obj)

        try:
            if getattr(rdo_obj, 'data_inicio', None) is None and getattr(rdo_obj, 'data', None) is not None:
                rdo_obj.data_inicio = rdo_obj.data
                _safe_save_global(rdo_obj)
        except Exception:
            pass

        try:
            ordem = getattr(rdo_obj, 'ordem_servico', None)
            contrato_val = getattr(rdo_obj, 'contrato_po', None) or getattr(rdo_obj, 'po', None)
            if ordem and contrato_val is not None:
                try:
                    ordem.po = contrato_val if contrato_val != '' else None
                    ordem.save(update_fields=['po'])
                except Exception:
                    pass
        except Exception:
            pass

        atividades_payload = []
        for atv in rdo_obj.atividades_rdo.all():
            atividades_payload.append({
                'ordem': atv.ordem,
                'atividade': atv.atividade,
                'atividade_label': atv.get_atividade_display(),
                'inicio': atv.inicio.strftime('%H:%M') if atv.inicio else None,
                'fim': atv.fim.strftime('%H:%M') if atv.fim else None,
                'comentario_pt': atv.comentario_pt,
                'comentario_en': atv.comentario_en,
            })

        fotos_list = []
        try:
            try:
                for i in range(1, 6):
                    try:
                        f = getattr(rdo_obj, f'fotos_{i}', None)
                    except Exception:
                        f = None
                    if not f:
                        continue
                    url = None
                    try:
                        url = getattr(f, 'url', None)
                    except Exception:
                        url = None
                    if not url:
                        try:
                            name = getattr(f, 'name', None)
                            if name and hasattr(default_storage, 'url'):
                                try:
                                    url = default_storage.url(name)
                                except Exception:
                                    url = name
                            else:
                                url = name or str(f)
                        except Exception:
                            url = str(f)
                    if url:
                        fotos_list.append(url)
            except Exception:
                fotos_list = []

            if not fotos_list:
                fotos_field = getattr(rdo_obj, 'fotos', None)
                if fotos_field is None:
                    fotos_list = []
                elif isinstance(fotos_field, (list, tuple)):
                    fotos_list = list(fotos_field)
                elif isinstance(fotos_field, str):
                    s = fotos_field.strip()
                    if s.startswith('['):
                        try:
                            fotos_list = json.loads(s)
                        except Exception:
                            fotos_list = [ln for ln in s.splitlines() if ln.strip()]
                    else:
                        fotos_list = [ln for ln in s.splitlines() if ln.strip()]
                else:
                    try:
                        url = getattr(fotos_field, 'url', None)
                    except Exception:
                        url = None
                    if url:
                        fotos_list = [url]
                    else:
                        fotos_list = []
        except Exception:
            fotos_list = []

        equipe_list = []
        try:
            rel_members = list(rdo_obj.membros_equipe.all().order_by('ordem', 'id'))
        except Exception:
            rel_members = []
        if rel_members:
            for em in rel_members:
                try:
                    nome = getattr(em.pessoa, 'nome', None) if getattr(em, 'pessoa', None) else getattr(em, 'nome', None)
                except Exception:
                    nome = getattr(em, 'nome', None)
                equipe_list.append({
                    'nome': nome,
                    'funcao': getattr(em, 'funcao', None),
                    'em_servico': bool(getattr(em, 'em_servico', True)),
                })
        else:
            try:
                membros_field = getattr(rdo_obj, 'membros', None)
                funcoes_field = getattr(rdo_obj, 'funcoes_list', None) or getattr(rdo_obj, 'funcoes', None)
                if membros_field is None:
                    mlist = []
                elif isinstance(membros_field, (list, tuple)):
                    mlist = list(membros_field)
                elif isinstance(membros_field, str):
                    s = membros_field.strip()
                    if s.startswith('['):
                        try:
                            mlist = json.loads(s)
                        except Exception:
                            mlist = [ln for ln in s.splitlines() if ln.strip()]
                    else:
                        mlist = [ln for ln in s.splitlines() if ln.strip()]
                else:
                    mlist = []

                if funcoes_field is None:
                    flist = []
                elif isinstance(funcoes_field, (list, tuple)):
                    flist = list(funcoes_field)
                elif isinstance(funcoes_field, str):
                    s2 = funcoes_field.strip()
                    if s2.startswith('['):
                        try:
                            flist = json.loads(s2)
                        except Exception:
                            flist = [ln for ln in s2.splitlines() if ln.strip()]
                    else:
                        flist = [ln for ln in s2.splitlines() if ln.strip()]
                else:
                    flist = []

                maxlen = max(len(mlist), len(flist))
                for i in range(maxlen):
                    equipe_list.append({'nome': (mlist[i] if i < len(mlist) else None), 'funcao': (flist[i] if i < len(flist) else None)})
            except Exception:
                equipe_list = []

        def _fmt(v):
            return str(v) if v is not None else None

        payload = {
            'id': rdo_obj.id,
            'rdo': rdo_obj.rdo,
            'data': rdo_obj.data.isoformat() if rdo_obj.data else None,
            'data_inicio': (getattr(rdo_obj, 'data_inicio', None) or getattr(rdo_obj, 'data', None)).isoformat() if (getattr(rdo_obj, 'data_inicio', None) or getattr(rdo_obj, 'data', None)) else None,
            'rdo_data_inicio': (getattr(rdo_obj, 'data_inicio', None) or getattr(rdo_obj, 'data', None)).isoformat() if (getattr(rdo_obj, 'data_inicio', None) or getattr(rdo_obj, 'data', None)) else None,
            'previsao_termino': rdo_obj.previsao_termino.isoformat() if getattr(rdo_obj, 'previsao_termino', None) else None,
            'rdo_previsao_termino': rdo_obj.previsao_termino.isoformat() if getattr(rdo_obj, 'previsao_termino', None) else None,
            'numero_os': getattr(rdo_obj.ordem_servico, 'numero_os', None) if getattr(rdo_obj, 'ordem_servico', None) else None,
            'empresa': getattr(rdo_obj.ordem_servico, 'cliente', None) if getattr(rdo_obj, 'ordem_servico', None) else None,
            'unidade': getattr(rdo_obj.ordem_servico, 'unidade', None) if getattr(rdo_obj, 'ordem_servico', None) else None,
            'turno': rdo_obj.turno,
            'nome_tanque': rdo_obj.nome_tanque,
            'tanque_codigo': rdo_obj.tanque_codigo,
            'tipo_tanque': rdo_obj.tipo_tanque,
            'numero_compartimentos': rdo_obj.numero_compartimentos,
            'volume_tanque_exec': str(rdo_obj.volume_tanque_exec) if rdo_obj.volume_tanque_exec is not None else None,
            'servico_exec': rdo_obj.servico_exec,
            'metodo_exec': rdo_obj.metodo_exec,
            'gavetas': rdo_obj.gavetas,
            'patamares': rdo_obj.patamares,
            'operadores_simultaneos': rdo_obj.operadores_simultaneos,
            'H2S_ppm': str(getattr(rdo_obj, 'h2s_ppm', None)) if getattr(rdo_obj, 'h2s_ppm', None) is not None else None,
            'LEL': str(getattr(rdo_obj, 'lel', None)) if getattr(rdo_obj, 'lel', None) is not None else None,
            'CO_ppm': str(getattr(rdo_obj, 'co_ppm', None)) if getattr(rdo_obj, 'co_ppm', None) is not None else None,
            'O2_percent': str(getattr(rdo_obj, 'o2_percent', None)) if getattr(rdo_obj, 'o2_percent', None) is not None else None,
            'bombeio': (lambda v: (str(v) if v is not None and not isinstance(v, (int, float)) else v))(getattr(rdo_obj, 'bombeio', getattr(rdo_obj, 'quantidade_bombeada', None))),
            'total_liquido': rdo_obj.total_liquido,
            'ensacamento': rdo_obj.ensacamento,
            'tambores': rdo_obj.tambores,
            'tambores_cumulativo': (lambda: getattr(rdo_obj.tanques.first(), 'tambores_cumulativo', None) if rdo_obj.tanques.exists() else None)(),
            'tambores_acu': (lambda: getattr(rdo_obj.tanques.first(), 'tambores_cumulativo', None) if rdo_obj.tanques.exists() else None)(),
            'total_solidos': rdo_obj.total_solidos,
            'total_residuos': rdo_obj.total_residuos,
            'po': getattr(rdo_obj, 'po', None) or getattr(rdo_obj, 'contrato_po', None) or (rdo_obj.ordem_servico.po if getattr(rdo_obj, 'ordem_servico', None) else None),
            'exist_pt': rdo_obj.exist_pt,
            'select_turnos': rdo_obj.select_turnos,
            'pt_manha': rdo_obj.pt_manha,
            'pt_tarde': rdo_obj.pt_tarde,
            'pt_noite': rdo_obj.pt_noite,
            'observacoes_pt': rdo_obj.observacoes_rdo_pt,
            'observacoes_en': getattr(rdo_obj, 'observacoes_rdo_en', None),
            'planejamento_pt': rdo_obj.planejamento_pt,
            'planejamento_en': getattr(rdo_obj, 'planejamento_en', None),
            'comentario_pt': getattr(rdo_obj, 'comentario_pt', None),
            'comentario_en': getattr(rdo_obj, 'comentario_en', None),
            'atividades': atividades_payload,
            'sentido_limpeza': (lambda v: (_canonicalize_sentido(v)))(getattr(rdo_obj, 'sentido_limpeza', getattr(rdo_obj, 'sent_limpeza', None))),
            'sentido_label': (lambda v: ('Vante > Ré' if _canonicalize_sentido(v) == 'vante > ré' else ('Ré > Vante' if _canonicalize_sentido(v) == 'ré > vante' else ( 'Bombordo > Boreste' if _canonicalize_sentido(v) == 'bombordo > boreste' else ( 'Boreste < Bombordo' if _canonicalize_sentido(v) == 'boreste < bombordo' else None)) )))(getattr(rdo_obj, 'sentido_limpeza', getattr(rdo_obj, 'sent_limpeza', None))),
            'sentido_limpeza_bool': (lambda v: (True if _canonicalize_sentido(v) == 'vante > ré' else (False if _canonicalize_sentido(v) == 'ré > vante' else None)))(getattr(rdo_obj, 'sentido_limpeza', getattr(rdo_obj, 'sent_limpeza', None))),
            'tempo_bomba': (None if not getattr(rdo_obj, 'tempo_uso_bomba', None) else round(rdo_obj.tempo_uso_bomba.total_seconds()/3600, 1)),
            'fotos': fotos_list,
            'equipe': equipe_list,
            'percentual_limpeza_fina': _fmt(getattr(rdo_obj, 'percentual_limpeza_fina', None)),
            'percentual_limpeza_cumulativo': _fmt(getattr(rdo_obj, 'percentual_limpeza_cumulativo', None)),
            'percentual_limpeza_fina_cumulativo': _fmt(getattr(rdo_obj, 'percentual_limpeza_fina_cumulativo', None)),
            'percentual_limpeza_diario': _fmt(getattr(rdo_obj, 'percentual_limpeza_diario', None)),
            'percentual_limpeza_fina_diario': _fmt(getattr(rdo_obj, 'percentual_limpeza_fina_diario', None)),
            'limpeza_mecanizada_diaria': _fmt(getattr(rdo_obj, 'limpeza_mecanizada_diaria', None)),
            'limpeza_fina_diaria': _fmt(getattr(rdo_obj, 'limpeza_fina_diaria', None)),
            'limpeza_mecanizada_cumulativa': _fmt(getattr(rdo_obj, 'limpeza_mecanizada_cumulativa', None)),
            'limpeza_fina_cumulativa': _fmt(getattr(rdo_obj, 'limpeza_fina_cumulativa', None)),
            'limpeza_acu': _fmt(getattr(rdo_obj, 'percentual_limpeza_cumulativo', None)),
            'limpeza_fina_acu': _fmt(getattr(rdo_obj, 'percentual_limpeza_fina_cumulativo', None)),
            'avanco_limpeza': _fmt(getattr(rdo_obj, 'percentual_limpeza', None)),
            'ensacamento_cumulativo': (getattr(rdo_obj, 'ensacamento_cumulativo', None) if getattr(rdo_obj, 'ensacamento_cumulativo', None) is not None else getattr(rdo_obj, 'ensacamento', None)),
            'ensacamento_previsao': (getattr(rdo_obj, 'ensacamento_previsao', None) if getattr(rdo_obj, 'ensacamento_previsao', None) is not None else None),
            'icamento_cumulativo': (getattr(rdo_obj, 'icamento_cumulativo', None) if getattr(rdo_obj, 'icamento_cumulativo', None) is not None else getattr(rdo_obj, 'icamento', None)),
            'icamento_previsao': (getattr(rdo_obj, 'icamento_previsao', None) if getattr(rdo_obj, 'icamento_previsao', None) is not None else None),
            'cambagem_cumulativo': (getattr(rdo_obj, 'cambagem_cumulativo', None) if getattr(rdo_obj, 'cambagem_cumulativo', None) is not None else getattr(rdo_obj, 'cambagem', None)),
            'cambagem_previsao': (getattr(rdo_obj, 'cambagem_previsao', None) if getattr(rdo_obj, 'cambagem_previsao', None) is not None else None),
            'percentual_ensacamento': _fmt(getattr(rdo_obj, 'percentual_ensacamento', None)),
            'percentual_icamento': _fmt(getattr(rdo_obj, 'percentual_icamento', None)),
            'percentual_cambagem': _fmt(getattr(rdo_obj, 'percentual_cambagem', None)),
            'percentual_avanco': _fmt(getattr(rdo_obj, 'percentual_avanco', None)),
            'total_atividade_min': None,
            'total_confinado_min': None,
            'total_abertura_pt_min': None,
            'total_atividades_efetivas_min': None,
            'total_atividades_nao_efetivas_fora_min': None,
            'total_n_efetivo_confinado_min': None,
        }
        try:
            ec_times_local = {}
            try:
                if isinstance(entrada_list, (list, tuple)) and any(str(x).strip() for x in entrada_list or []):
                    entradas = [_format_ec_time_value(v) for v in entrada_list]
                else:
                    entradas = []
                    try:
                        for i in range(6):
                            entradas.append(_format_ec_time_value(getattr(rdo_obj, f'entrada_confinado_{i+1}', None)))
                    except Exception:
                        entradas = []
                    if not any(entradas):
                        entrada_field = getattr(rdo_obj, 'entrada_confinado', None)
                        entradas = _normalize_ec_field_to_list(entrada_field)

                if isinstance(saida_list, (list, tuple)) and any(str(x).strip() for x in saida_list or []):
                    saidas = [_format_ec_time_value(v) for v in saida_list]
                else:
                    saidas = []
                    try:
                        for i in range(6):
                            saidas.append(_format_ec_time_value(getattr(rdo_obj, f'saida_confinado_{i+1}', None)))
                    except Exception:
                        saidas = []
                    if not any(saidas):
                        saida_field = getattr(rdo_obj, 'saida_confinado', None)
                        saidas = _normalize_ec_field_to_list(saida_field)

                for i in range(6):
                    ec_times_local[f'entrada_{i+1}'] = entradas[i] if i < len(entradas) else None
                    ec_times_local[f'saida_{i+1}'] = saidas[i] if i < len(saidas) else None
            except Exception:
                ec_times_local = {}
            ag = compute_rdo_aggregates(rdo_obj, atividades_payload, ec_times_local)
            payload['total_atividade_min'] = ag.get('total_atividade_min')
            payload['total_confinado_min'] = ag.get('total_confinado_min')
            payload['total_abertura_pt_min'] = ag.get('total_abertura_pt_min')
            payload['total_atividades_efetivas_min'] = ag.get('total_atividades_efetivas_min')
            payload['total_atividades_nao_efetivas_fora_min'] = ag.get('total_atividades_nao_efetivas_fora_min')
            payload['total_n_efetivo_confinado_min'] = ag.get('total_n_efetivo_confinado_min')
            try:
                payload['ec_times'] = ec_times_local
            except Exception:
                payload['ec_times'] = {}
            try:
                payload['ec_raw'] = {
                    'entrada_list': entrada_list,
                    'saida_list': saida_list,
                }
            except Exception:
                payload['ec_raw'] = {'entrada_list': [], 'saida_list': []}
        except Exception:
            pass

        logger.info('_apply_post_to_rdo about to return payload for rdo_id=%s', getattr(rdo_obj, 'id', None))
        return True, payload
    except Exception as e:
        logger = logging.getLogger(__name__)
        try:
            post_snapshot = {}
            try:
                post_snapshot['post_keys'] = list(request.POST.keys()) if hasattr(request, 'POST') else []
            except Exception:
                post_snapshot['post_keys'] = []
            try:
                interesting_keys = [
                    'rdo_id', 'ordem_servico_id', 'data', 'data_inicio', 'rdo_data_inicio', 'previsao_termino',
                    'turno', 'contrato_po', 'volume_tanque_exec', 'numero_compartimento',
                    'tanque_id', 'tank_id', 'tanqueId',
                    'sup-limp', 'sup-limp-acu', 'sup-limp-fina', 'sup-limp-fina-acu',
                    'avanco_limpeza', 'percentual_limpeza', 'percentual_limpeza_cumulativo',
                    'percentual_limpeza_fina', 'percentual_limpeza_fina_cumulativo',
                ]
                post_snapshot['interesting'] = {}
                for k in interesting_keys:
                    try:
                        v = request.POST.get(k) if hasattr(request, 'POST') else None
                        if v not in (None, ''):
                            post_snapshot['interesting'][k] = v
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                # Captura apenas presença/nome de arquivos (sem conteúdo)
                files = {}
                if hasattr(request, 'FILES') and request.FILES:
                    for k in list(request.FILES.keys()):
                        try:
                            objs = request.FILES.getlist(k) if hasattr(request.FILES, 'getlist') else [request.FILES.get(k)]
                            files[k] = [getattr(f, 'name', None) for f in objs]
                        except Exception:
                            files[k] = ['<erro_inspecao>']
                if files:
                    post_snapshot['files'] = files
            except Exception:
                pass
        except Exception:
            post_snapshot = {'post_keys': ['<snapshot_failed>']}

        try:
            os_num = None
            try:
                os_num = getattr(getattr(rdo_obj, 'ordem_servico', None), 'numero_os', None)
            except Exception:
                os_num = None
            logger.exception(
                'Erro aplicando POST ao RDO (rdo_id=%s os=%s): %s | snapshot=%s',
                getattr(rdo_obj, 'id', None),
                os_num,
                f'{type(e).__name__}: {e}',
                post_snapshot,
            )
        except Exception:
            logger.exception('Erro aplicando POST ao RDO (falha ao logar snapshot)')

        return False, {'exception_type': type(e).__name__, 'exception': str(e)}


def _promote_programada_os_with_rdo_to_em_andamento(ordem_servico):
    try:
        numero_os = getattr(ordem_servico, 'numero_os', None)
        if numero_os in (None, ''):
            return 0

        if not RDO.objects.filter(ordem_servico__numero_os=numero_os).exists():
            return 0

        protected_statuses_q = (
            Q(status_operacao__iexact='Paralizada') |
            Q(status_operacao__iexact='Finalizada') |
            Q(status_operacao__iexact='Cancelada') |
            Q(status_geral__iexact='Paralizada') |
            Q(status_geral__iexact='Finalizada') |
            Q(status_geral__iexact='Cancelada')
        )

        eligible_rows = (
            OrdemServico.objects
            .filter(numero_os=numero_os)
            .exclude(protected_statuses_q)
        )

        rows_to_update = eligible_rows.exclude(
            status_operacao__iexact='Em Andamento',
            status_geral__iexact='Em Andamento',
        )

        return rows_to_update.update(
            status_operacao='Em Andamento',
            status_geral='Em Andamento',
        )
    except Exception:
        logging.getLogger(__name__).exception(
            'Falha ao promover OS com RDO para Em Andamento. ordem_servico_id=%s',
            getattr(ordem_servico, 'id', None),
        )
        return 0

@login_required(login_url='/login/')
@require_POST
def create_rdo_ajax(request):
    logger = logging.getLogger(__name__)
    read_only_response = _guard_read_only_json(request, 'criar RDO')
    if read_only_response is not None:
        return read_only_response

    try:
        logger.info('create_rdo_ajax called by user=%s, POST_keys=%s', getattr(request, 'user', None), list(request.POST.keys()))
        try:
            content_type = request.META.get('CONTENT_TYPE') or request.content_type if hasattr(request, 'content_type') else None
        except Exception:
            content_type = None
        try:
            body_len = len(getattr(request, 'body', b''))
        except Exception:
            body_len = None
        logger.debug('create_rdo_ajax debug content_type=%s body_len=%s', content_type, body_len)
        try:
            if not list(request.POST.keys()):
                try:
                    raw = request.body
                    logger.debug('create_rdo_ajax raw body (truncated 2000 chars): %s', raw[:2000])
                except Exception:
                    logger.exception('create_rdo_ajax failed reading raw body')
        except Exception:
            pass
        try:
            if hasattr(request, 'POST') and hasattr(request.POST, 'getlist'):
                logger.debug('create_rdo_ajax cleaned keys: sup-limp=%s sup-limp-fina=%s percentual_limpeza_diario=%s percentual_limpeza_fina_diario=%s',
                             request.POST.getlist('sup-limp') or request.POST.get('sup-limp'),
                             request.POST.getlist('sup-limp-fina') or request.POST.get('sup-limp-fina'),
                             request.POST.getlist('percentual_limpeza_diario') or request.POST.get('percentual_limpeza_diario'),
                             request.POST.getlist('percentual_limpeza_fina_diario') or request.POST.get('percentual_limpeza_fina_diario'))
            else:
                logger.debug('create_rdo_ajax quick keys: sup-limp=%s sup-limp-fina=%s percentual_limpeza_diario=%s percentual_limpeza_fina_diario=%s',
                             request.POST.get('sup-limp'), request.POST.get('sup-limp-fina'), request.POST.get('percentual_limpeza_diario'), request.POST.get('percentual_limpeza_fina_diario'))
        except Exception:
            logger.exception('create_rdo_ajax failed logging specific limpeza keys')
        ordem_id = request.POST.get('ordem_servico_id') or request.POST.get('ordem_id') or request.POST.get('rdo_id')
        rdo_obj = RDO()
        if ordem_id:
            try:
                with transaction.atomic():
                    os_obj = None
                    try:
                        os_obj = OrdemServico.objects.select_for_update().get(pk=ordem_id)
                    except OrdemServico.DoesNotExist:
                        try:
                            numero_val = int(str(ordem_id).strip())
                        except Exception:
                            numero_val = None
                        try:
                            if numero_val is not None:
                                os_obj = OrdemServico.objects.select_for_update().filter(numero_os=numero_val).first()
                            else:
                                os_obj = OrdemServico.objects.select_for_update().filter(numero_os__iexact=str(ordem_id).strip()).first()
                        except Exception:
                            os_obj = None
                    if not os_obj:
                        return JsonResponse({'success': False, 'error': 'Ordem de Serviço não encontrada.'}, status=404)
                    try:
                        is_supervisor_user = (hasattr(request, 'user') and request.user.is_authenticated and request.user.groups.filter(name='Supervisor').exists())
                    except Exception:
                        is_supervisor_user = False
                    if is_supervisor_user and getattr(os_obj, 'supervisor', None) != request.user:
                        return JsonResponse({'success': False, 'error': 'Sem permissão para criar RDO para esta OS.'}, status=403)

                    max_val = None
                    rdo_override_raw = None
                    try:
                        rdo_override_raw = (request.POST.get('rdo_contagem') or request.POST.get('rdo') or request.POST.get('rdo_override'))
                        if rdo_override_raw is not None:
                            rdo_override_raw = str(rdo_override_raw).strip()
                            if rdo_override_raw == '':
                                rdo_override_raw = None
                    except Exception:
                        rdo_override_raw = None
                    try:
                        numero_lookup = getattr(os_obj, 'numero_os', None)
                        if numero_lookup is not None:
                            qs_for_max = RDO.objects.filter(ordem_servico__numero_os=numero_lookup)
                        else:
                            qs_for_max = RDO.objects.filter(ordem_servico=os_obj)

                        try:
                            agg = qs_for_max.aggregate(max_rdo=Max('rdo'))
                            max_rdo_raw = agg.get('max_rdo')
                            if max_rdo_raw is not None:
                                try:
                                    max_val = int(str(max_rdo_raw))
                                except Exception:
                                    max_val = None
                        except Exception:
                            max_val = None
                    except Exception:
                        max_val = None

                    if max_val is None:
                        try:
                            for r in qs_for_max.only('rdo'):
                                try:
                                    v = int(str(r.rdo))
                                    if max_val is None or v > max_val:
                                        max_val = v
                                except Exception:
                                    continue
                        except Exception:
                            max_val = None

                    used_rdo = None
                    try:
                        if rdo_override_raw is not None:
                            try:
                                cand = int(rdo_override_raw)
                            except Exception:
                                cand = None
                            if cand is not None:
                                try:
                                    exists_same = qs_for_max.filter(rdo=str(cand)).exists()
                                except Exception:
                                    exists_same = False
                                if not exists_same:
                                    used_rdo = cand
                    except Exception:
                        used_rdo = None

                    if used_rdo is None:
                        next_num = (max_val or 0) + 1
                        used_rdo = next_num

                    try:
                        cur_try = int(used_rdo) if used_rdo is not None else None
                    except Exception:
                        cur_try = None
                    try:
                        if cur_try is None:
                            exists_once = False
                            try:
                                exists_once = qs_for_max.filter(rdo=str(used_rdo)).exists()
                            except Exception:
                                exists_once = False
                            if exists_once:
                                try:
                                    cur_try = (max_val or 0) + 1
                                except Exception:
                                    cur_try = None
                        if cur_try is not None:
                            attempts = 0
                            while True:
                                try:
                                    if not qs_for_max.filter(rdo=str(cur_try)).exists():
                                        used_rdo = cur_try
                                        break
                                except Exception:
                                    break
                                cur_try = cur_try + 1
                                attempts += 1
                                if attempts > 10000:
                                    break
                    except Exception:
                        pass

                    final_rdo = str(used_rdo)
                    attempts_final = 0
                    while qs_for_max.filter(rdo=final_rdo).exists():
                        try:
                            final_rdo = str(int(final_rdo) + 1)
                        except Exception:
                            final_rdo = f"{final_rdo}_{attempts_final+1}"
                        attempts_final += 1
                        if attempts_final > 10000:
                            logger.error("Loop de proteção final_rdo excedeu 10000 tentativas!")
                            break
                    rdo_obj.rdo = final_rdo
                    rdo_obj.ordem_servico = os_obj

                    save_placeholder_failed = False
                    try:
                        from django.db.utils import OperationalError as DjangoOperationalError
                    except Exception:
                        DjangoOperationalError = None
                    try:
                        _safe_save_global(rdo_obj)
                    except Exception as e:
                        msg = str(e).lower()
                        handled = False
                        try:
                            from django.db import IntegrityError as DjangoIntegrityError
                        except Exception:
                            DjangoIntegrityError = None

                        if DjangoOperationalError is not None and isinstance(e, DjangoOperationalError) and 'locked' in msg:
                            logger.warning('SQLite locked while saving placeholder RDO inside atomic; will retry outside atomic: %s', e)
                            save_placeholder_failed = True
                            handled = True

                        if not handled and DjangoIntegrityError is not None and isinstance(e, DjangoIntegrityError):
                            try:
                                logger.warning('IntegrityError when saving placeholder RDO: %s. Attempting to load existing RDO.', e)
                                existing = None
                                try:
                                    if getattr(rdo_obj, 'ordem_servico', None) is not None and getattr(rdo_obj, 'rdo', None) is not None:
                                        existing = RDO.objects.filter(ordem_servico=getattr(rdo_obj, 'ordem_servico'), rdo=getattr(rdo_obj, 'rdo')).first()
                                except Exception:
                                    existing = None
                                if existing:
                                    logger.info('Found existing RDO (pk=%s) with same ordem_servico and rdo; reusing it.', getattr(existing, 'pk', None))
                                    rdo_obj = existing
                                    save_placeholder_failed = False
                                    handled = True
                                else:
                                    logger.exception('IntegrityError saving placeholder but no existing RDO found.')
                            except Exception:
                                logger.exception('Error handling IntegrityError for placeholder save')

                        if not handled:
                            logger.exception('Falha ao salvar RDO de reserva dentro da transação')
                            raise

                try:
                    if save_placeholder_failed:
                        try:
                            logger.info('Retrying placeholder save for RDO outside atomic (possible prior SQLite lock)')
                            _safe_save_global(rdo_obj)
                            save_placeholder_failed = False
                        except Exception as e:
                            try:
                                from django.db import IntegrityError as DjangoIntegrityError
                            except Exception:
                                DjangoIntegrityError = None
                            if DjangoIntegrityError is not None and isinstance(e, DjangoIntegrityError):
                                try:
                                    logger.warning('IntegrityError on retrying placeholder save outside atomic: %s. Attempting to load existing RDO.', e)
                                    existing = None
                                    try:
                                        if getattr(rdo_obj, 'ordem_servico', None) is not None and getattr(rdo_obj, 'rdo', None) is not None:
                                            existing = RDO.objects.filter(ordem_servico=getattr(rdo_obj, 'ordem_servico'), rdo=getattr(rdo_obj, 'rdo')).first()
                                    except Exception:
                                        existing = None
                                    if existing:
                                        logger.info('Found existing RDO (pk=%s) after retry; reusing it.', getattr(existing, 'pk', None))
                                        rdo_obj = existing
                                        save_placeholder_failed = False
                                    else:
                                        logger.exception('Retry to save placeholder RDO outside atomic failed and no existing RDO found')
                                except Exception:
                                    logger.exception('Error handling IntegrityError on retry placeholder save')
                            else:
                                logger.exception('Retry to save placeholder RDO outside atomic failed')
                            pass
                except NameError:
                    pass

                logger.debug('About to call _apply_post_to_rdo (outside atomic) for RDO rdo=%s ordem=%s', getattr(rdo_obj, 'rdo', None), getattr(rdo_obj, 'ordem_servico', None))
                import time as _time
                _t0 = _time.time()
                created, payload = _apply_post_to_rdo(request, rdo_obj)
                _t1 = _time.time()
                logger.info('Finished _apply_post_to_rdo (created=%s) elapsed=%.3fs', bool(created), (_t1 - _t0))
                if not created:
                    try:
                        if getattr(rdo_obj, 'pk', None):
                            rdo_obj.delete()
                    except Exception:
                        logger.exception('Falha ao remover RDO reservado após falha em _apply_post_to_rdo')
                    
                    return JsonResponse({'success': False, 'error': 'Falha ao criar RDO.'}, status=400)

                same_os_status_updates = _promote_programada_os_with_rdo_to_em_andamento(
                    getattr(rdo_obj, 'ordem_servico', None),
                )

                try:
                    rdo_pk = payload.get('id') if payload is not None else getattr(rdo_obj, 'id', None)
                    try:
                        rdo_pk = int(rdo_pk) if rdo_pk is not None else None
                    except Exception:
                        rdo_pk = None
                    resp_debug = {
                        'success': True,
                        'message': 'RDO criado',
                        'id': rdo_pk,
                        'pk': rdo_pk,
                        'rdo': payload,
                        'used_rdo': str(final_rdo),
                        'computed_max': (max_val if max_val is not None else None),
                        'status_promovido_em_andamento': bool(same_os_status_updates),
                        'same_os_status_updates': same_os_status_updates,
                    }
                except Exception:
                    resp_debug = {
                        'success': True,
                        'message': 'RDO criado',
                        'id': None,
                        'rdo': payload,
                        'status_promovido_em_andamento': bool(same_os_status_updates),
                        'same_os_status_updates': same_os_status_updates,
                    }
                return JsonResponse(resp_debug)
            except OrdemServico.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Ordem de Serviço não encontrada.'}, status=404)
        else:
            created, payload = _apply_post_to_rdo(request, rdo_obj)
            if not created:
                return JsonResponse({'success': False, 'error': 'Falha ao criar RDO.'}, status=400)
            same_os_status_updates = _promote_programada_os_with_rdo_to_em_andamento(
                getattr(rdo_obj, 'ordem_servico', None),
            )
            return JsonResponse({
                'success': True,
                'message': 'RDO criado',
                'id': payload.get('id'),
                'rdo': payload,
                'status_promovido_em_andamento': bool(same_os_status_updates),
                'same_os_status_updates': same_os_status_updates,
            })
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.exception('Erro create_rdo_ajax')
        try:
            if getattr(settings, 'DEBUG', False):
                return JsonResponse({
                    'success': False,
                    'error': 'Erro interno',
                    'exception': str(e),
                    'traceback': traceback.format_exc(),
                }, status=500)
        except Exception:
            pass
        return JsonResponse({'success': False, 'error': 'Erro interno'}, status=500)

    try:
        logging.getLogger(__name__).error('create_rdo_ajax reached end of function without explicit return - returning generic error')
    except Exception:
        pass
    return JsonResponse({'success': False, 'error': 'Erro interno (no response path)'}, status=500)

@login_required(login_url='/login/')
@require_POST
def update_rdo_ajax(request):
    logger = logging.getLogger(__name__)
    read_only_response = _guard_read_only_json(request, 'atualizar RDO')
    if read_only_response is not None:
        return read_only_response

    try:
        logger.info('update_rdo_ajax called by user=%s POST_keys=%s', getattr(request, 'user', None), list(request.POST.keys()))
        rdo_id = request.POST.get('rdo_id')
        if not rdo_id:
            return JsonResponse({'success': False, 'error': 'ID do RDO não informado.'}, status=400)
        try:
            rdo_obj = RDO.objects.get(pk=rdo_id)
        except RDO.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'RDO não encontrado.'}, status=404)
        try:
            is_supervisor_user = (hasattr(request, 'user') and request.user.is_authenticated and request.user.groups.filter(name='Supervisor').exists())
        except Exception:
            is_supervisor_user = False
        if is_supervisor_user:
            ordem = getattr(rdo_obj, 'ordem_servico', None)
            if ordem is not None and getattr(ordem, 'supervisor', None) != request.user:
                return JsonResponse({'success': False, 'error': 'Sem permissão para atualizar este RDO.'}, status=403)
        updated, payload = _apply_post_to_rdo(request, rdo_obj)
        if not updated:
            resp = {'success': False, 'error': 'Falha ao atualizar RDO.'}
            try:
                # Se o payload contém informação de exceção (ex.: ValidationError),
                # retornar a mensagem para o cliente para facilitar diagnóstico.
                if isinstance(payload, dict):
                    exc_msg = payload.get('exception') or payload.get('error') or ''
                    exc_type = payload.get('exception_type') or ''
                    try:
                        if exc_type and 'ValidationError' in str(exc_type):
                            if exc_msg:
                                resp['error'] = str(exc_msg)
                        elif isinstance(exc_msg, str) and 'Inconsist' in exc_msg:
                            resp['error'] = str(exc_msg)
                    except Exception:
                        pass

                is_superuser = bool(getattr(getattr(request, 'user', None), 'is_superuser', False))
                if getattr(settings, 'DEBUG', False) or is_superuser:
                    if isinstance(payload, dict) and payload:
                        resp['debug'] = payload
            except Exception:
                pass
            return JsonResponse(resp, status=400)
        same_os_status_updates = _promote_programada_os_with_rdo_to_em_andamento(
            getattr(rdo_obj, 'ordem_servico', None),
        )
        return JsonResponse({
            'success': True,
            'message': 'RDO atualizado',
            'rdo': payload,
            'status_promovido_em_andamento': bool(same_os_status_updates),
            'same_os_status_updates': same_os_status_updates,
        })
    except Exception:
        logging.getLogger(__name__).exception('Erro update_rdo_ajax')
        return JsonResponse({'success': False, 'error': 'Erro interno'}, status=500)

@login_required(login_url='/login/')
@require_POST
def delete_rdo_ajax(request, rdo_id):
    logger = logging.getLogger(__name__)
    read_only_response = _guard_read_only_json(request, 'excluir RDO')
    if read_only_response is not None:
        return read_only_response

    try:
        from django.db.models.deletion import ProtectedError
        from urllib.parse import urlparse as _urlparse

        if not _user_can_delete_rdo(getattr(request, 'user', None)):
            return JsonResponse({'success': False, 'error': 'Sem permissão para excluir RDO.'}, status=403)

        with transaction.atomic():
            try:
                rdo_obj = (
                    RDO.objects
                    .select_related('ordem_servico')
                    .select_for_update()
                    .get(pk=rdo_id)
                )
            except RDO.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'RDO não encontrado.'}, status=404)

            try:
                is_supervisor_user = (
                    hasattr(request, 'user')
                    and request.user.is_authenticated
                    and request.user.groups.filter(name='Supervisor').exists()
                )
            except Exception:
                is_supervisor_user = False

            if is_supervisor_user:
                ordem = getattr(rdo_obj, 'ordem_servico', None)
                if ordem is not None and getattr(ordem, 'supervisor', None) != request.user:
                    return JsonResponse({'success': False, 'error': 'Sem permissão para excluir este RDO.'}, status=403)

            def _normalize_storage_name(raw_value):
                try:
                    if raw_value in (None, ''):
                        return None
                    value = str(raw_value).strip()
                    if not value:
                        return None
                    if '?' in value:
                        value = value.split('?', 1)[0]
                    try:
                        parsed = _urlparse(value)
                        if getattr(parsed, 'path', None):
                            value = parsed.path
                    except Exception:
                        pass
                    value = value.replace('\\', '/')
                    media_url = str(getattr(settings, 'MEDIA_URL', '') or '').strip()
                    if media_url and value.startswith(media_url):
                        value = value[len(media_url):]
                    value = value.lstrip('/')
                    return value or None
                except Exception:
                    return None

            photo_paths = set()
            for attr in ('fotos_img', 'fotos_1', 'fotos_2', 'fotos_3', 'fotos_4', 'fotos_5'):
                try:
                    file_field = getattr(rdo_obj, attr, None)
                    file_name = getattr(file_field, 'name', None)
                except Exception:
                    file_name = None
                normalized = _normalize_storage_name(file_name)
                if normalized:
                    photo_paths.add(normalized)

            try:
                raw_fotos_json = getattr(rdo_obj, 'fotos_json', None)
                if raw_fotos_json:
                    parsed = json.loads(raw_fotos_json)
                    if isinstance(parsed, (list, tuple)):
                        for item in parsed:
                            normalized = _normalize_storage_name(item)
                            if normalized:
                                photo_paths.add(normalized)
            except Exception:
                logger.debug('Falha ao ler fotos_json do RDO %s para exclusão', rdo_id, exc_info=True)

            deleted_counts = {
                'tanques': rdo_obj.tanques.count(),
                'atividades': rdo_obj.atividades_rdo.count(),
                'membros_equipe': rdo_obj.membros_equipe.count(),
            }
            rdo_number = getattr(rdo_obj, 'rdo', None)
            rdo_date = None
            try:
                dt_ref = getattr(rdo_obj, 'data_inicio', None) or getattr(rdo_obj, 'data', None)
                if dt_ref is not None:
                    rdo_date = dt_ref.isoformat()
            except Exception:
                rdo_date = None

            try:
                deleted_total, _deleted_map = rdo_obj.delete()
            except ProtectedError:
                return JsonResponse({
                    'success': False,
                    'error': 'Não foi possível excluir este RDO porque existem registros protegidos relacionados.'
                }, status=409)

            def _delete_files(paths):
                for path_name in sorted(set(paths or [])):
                    try:
                        default_storage.delete(path_name)
                    except Exception:
                        logger.warning('Falha ao remover arquivo órfão do RDO excluído: %s', path_name, exc_info=True)

            transaction.on_commit(lambda paths=tuple(photo_paths): _delete_files(paths))

        return JsonResponse({
            'success': True,
            'ok': True,
            'deleted_id': int(rdo_id),
            'deleted_total': int(deleted_total or 0),
            'deleted_counts': deleted_counts,
            'rdo': {
                'id': int(rdo_id),
                'numero': rdo_number,
                'data': rdo_date,
            },
        })
    except Exception:
        logger.exception('delete_rdo_ajax error')
        return JsonResponse({'success': False, 'error': 'Erro interno'}, status=500)

@login_required(login_url='/login/')
@require_POST
def add_tank_ajax(request, rdo_id):
    logger = logging.getLogger(__name__)
    read_only_response = _guard_read_only_json(request, 'adicionar tanques ao RDO')
    if read_only_response is not None:
        return read_only_response

    try:
        logger.info('add_tank_ajax called by user=%s for rdo_id=%s POST_keys=%s', getattr(request, 'user', None), rdo_id, list(request.POST.keys()))
        try:
            rdo_obj = RDO.objects.get(pk=rdo_id)
        except RDO.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'RDO não encontrado.'}, status=404)

        tank_id_raw = None
        try:
            tank_id_raw = request.POST.get('tanque_id') or request.POST.get('tank_id') or request.POST.get('tanqueId')
        except Exception:
            tank_id_raw = None
        try:
            tanque_id_int = int(tank_id_raw) if tank_id_raw not in (None, '') else None
        except Exception:
            tanque_id_int = None

        if tanque_id_int is None:
            try:
                posted_code = (request.POST.get('tanque_codigo') or '').strip()
            except Exception:
                posted_code = ''
            try:
                posted_name = (request.POST.get('tanque_nome') or request.POST.get('nome_tanque') or '').strip()
            except Exception:
                posted_name = ''
            try:
                if posted_code or posted_name:
                    os_ids_guess = _resolve_os_scope_ids(getattr(rdo_obj, 'ordem_servico', None))
                    if os_ids_guess:
                        match_guess = Q()
                        if posted_code:
                            match_guess |= Q(tanque_codigo__iexact=posted_code)
                        if posted_name:
                            match_guess |= Q(nome_tanque__iexact=posted_name)
                        if match_guess:
                            guessed = (
                                RdoTanque.objects
                                .filter(rdo__ordem_servico_id__in=os_ids_guess)
                                .filter(match_guess)
                                .order_by('-id')
                                .first()
                            )
                            if guessed is not None:
                                tanque_id_int = int(getattr(guessed, 'id', 0) or 0) or None
                                if tanque_id_int:
                                    logger.info(
                                        'add_tank_ajax inferred tanque_id=%s by code/name for rdo_id=%s (code=%s name=%s)',
                                        tanque_id_int,
                                        rdo_id,
                                        posted_code,
                                        posted_name,
                                    )
            except Exception:
                pass

        try:
            is_supervisor_user = (hasattr(request, 'user') and request.user.is_authenticated and request.user.groups.filter(name='Supervisor').exists())
        except Exception:
            is_supervisor_user = False
        if is_supervisor_user:
            ordem = getattr(rdo_obj, 'ordem_servico', None)
            if ordem is not None and getattr(ordem, 'supervisor', None) != request.user:
                return JsonResponse({'success': False, 'error': 'Sem permissão para adicionar tanque neste RDO.'}, status=403)

        try:
            service_limit_count, service_labels = _resolve_os_service_limit(getattr(rdo_obj, 'ordem_servico', None))
        except Exception:
            service_limit_count, service_labels = (0, [])
        if not isinstance(service_limit_count, int):
            try:
                service_limit_count = int(service_limit_count or 0)
            except Exception:
                service_limit_count = 0
        if service_limit_count <= 0:
            service_limit_count = None

        try:
            os_tank_count, os_tank_keys = _resolve_os_tank_progress(getattr(rdo_obj, 'ordem_servico', None))
        except Exception:
            os_tank_count, os_tank_keys = (0, set())

        def _refresh_os_tank_progress():
            try:
                nonlocal os_tank_count, os_tank_keys
                os_tank_count, os_tank_keys = _resolve_os_tank_progress(getattr(rdo_obj, 'ordem_servico', None))
            except Exception:
                os_tank_count, os_tank_keys = (0, set())
            return os_tank_count, os_tank_keys

        def _tank_limit_payload(current_override=None):
            try:
                if current_override is None:
                    current_count, _keys = _refresh_os_tank_progress()
                else:
                    try:
                        current_count = int(current_override)
                    except Exception:
                        current_count = 0
                enabled = bool(service_limit_count and service_limit_count > 0)
                if enabled:
                    remaining = max(0, int(service_limit_count) - current_count)
                else:
                    remaining = None
                return {
                    'enabled': enabled,
                    'allowed': (int(service_limit_count) if enabled else None),
                    'current': current_count,
                    'remaining': remaining,
                    'servicos_count': (int(service_limit_count) if enabled else 0),
                    'servicos': service_labels or [],
                }
            except Exception:
                return {
                    'enabled': False,
                    'allowed': None,
                    'current': 0,
                    'remaining': None,
                    'servicos_count': 0,
                    'servicos': [],
                }

        from decimal import Decimal

        def _norm_num(val):
            try:
                if val is None:
                    return None
                s = str(val).strip()
                if s == '':
                    return None
                if s.endswith('%'):
                    s = s[:-1].strip()
                s = s.replace(',', '.')
                return s if s != '' else None
            except Exception:
                return None

        def _get_int(name):
            raw = request.POST.get(name)
            s = _norm_num(raw)
            if s is None:
                return None
            try:
                return int(float(s))
            except Exception:
                return None

        def _get_decimal(name, model_key=None):
            raw = request.POST.get(name)
            s = _norm_num(raw)
            if s is None:
                return None
            if model_key:
                return _coerce_decimal_for_model(RdoTanque, model_key, s)
            return _coerce_decimal_value(s)

        def _get_date(name):
            try:
                return _parse_iso_date_value(request.POST.get(name))
            except Exception:
                return None

        def _get_bool(name):
            v = request.POST.get(name)
            if v is None or v == '':
                return None
            s = str(v).strip().lower()
            if s in ('1', 'true', 't', 'yes', 'y', 'on', 'sim'):
                return True
            if s in ('0', 'false', 'f', 'no', 'n', 'off', 'nao', 'não'):
                return False
            return None

        def _parse_sentido():
            raw = None
            for k in ('sentido_limpeza', 'sentido', 'sent', 'sent_limpeza'):
                if k in request.POST and request.POST.get(k) not in (None, ''):
                    raw = request.POST.get(k)
                    break
            if raw is None:
                return None
            try:
                canon = _canonicalize_sentido(raw)
                return canon
            except Exception:
                return None

        def _normalize_prev_cumulativo(day_val, cum_val, legacy_total_val):
            if cum_val is not None:
                return cum_val
            if legacy_total_val is None:
                return None
            try:
                return int(legacy_total_val)
            except Exception:
                return legacy_total_val

        ens_day = _get_int('ensacamento_dia')
        ic_day = _get_int('icamento_dia')
        camb_day = _get_int('cambagem_dia')
        tamb_day = _get_int('tambores_dia')
        ens_cum_direct = _get_int('ensacamento_cumulativo')
        ic_cum_direct = _get_int('icamento_cumulativo')
        camb_cum_direct = _get_int('cambagem_cumulativo')
        tamb_cum_direct = _get_int('tambores_cumulativo')
        ens_cum_legacy = _get_int('ensacamento_acu')
        ic_cum_legacy = _get_int('icamento_acu')
        camb_cum_legacy = _get_int('cambagem_acu')
        tamb_cum_legacy = _get_int('tambores_acu')

        tanque_data = {
            'tanque_codigo': request.POST.get('tanque_codigo') or None,
            'nome_tanque': request.POST.get('tanque_nome') or request.POST.get('nome_tanque') or None,
            'tipo_tanque': request.POST.get('tipo_tanque') or None,
            'numero_compartimentos': _get_int('numero_compartimento') or _get_int('numero_compartimentos'),
            'gavetas': _get_int('gavetas'),
            'patamares': _get_int('patamar') or _get_int('patamares'),
            'volume_tanque_exec': _get_decimal('volume_tanque_exec', model_key='volume_tanque_exec'),
            'servico_exec': request.POST.get('servico_exec') or None,
            'metodo_exec': request.POST.get('metodo_exec') or None,
            'espaco_confinado': request.POST.get('espaco_confinado') or None,
            'operadores_simultaneos': _get_int('operadores_simultaneos'),
            'h2s_ppm': _get_decimal('h2s_ppm', model_key='h2s_ppm'),
            'lel': _get_decimal('lel', model_key='lel'),
            'co_ppm': _get_decimal('co_ppm', model_key='co_ppm'),
            'o2_percent': _get_decimal('o2_percent', model_key='o2_percent'),
            'total_n_efetivo_confinado': _get_int('total_n_efetivo_confinado'),
            'tempo_bomba': _get_decimal('tempo_bomba', model_key='tempo_bomba'),
            'ensacamento_dia': ens_day,
            'icamento_dia': ic_day,
            'cambagem_dia': camb_day,
            'tambores_dia': tamb_day,
            'ensacamento_cumulativo': _normalize_prev_cumulativo(ens_day, ens_cum_direct, ens_cum_legacy),
            'icamento_cumulativo': _normalize_prev_cumulativo(ic_day, ic_cum_direct, ic_cum_legacy),
            'cambagem_cumulativo': _normalize_prev_cumulativo(camb_day, camb_cum_direct, camb_cum_legacy),
            'previsao_termino': _get_date('previsao_termino') or _get_date('rdo_previsao_termino'),
            'tambores_cumulativo': _normalize_prev_cumulativo(tamb_day, tamb_cum_direct, tamb_cum_legacy),
            'total_liquido_cumulativo': _get_int('total_liquido_cumulativo') or _get_int('total_liquido_acu'),
            'residuos_solidos_cumulativo': _get_decimal('residuos_solidos_cumulativo', model_key='residuos_solidos_cumulativo') or _get_decimal('residuos_solidos_acu', model_key='residuos_solidos_cumulativo'),
            'ensacamento_prev': _get_int('ensacamento_prev') or _get_int('ensacamento_previsao') or getattr(rdo_obj, 'ensacamento_previsao', None) or getattr(rdo_obj, 'ensacamento', None),
            'icamento_prev': _get_int('icamento_prev') or _get_int('icamento_previsao') or getattr(rdo_obj, 'icamento_previsao', None) or getattr(rdo_obj, 'icamento', None),
            'cambagem_prev': _get_int('cambagem_prev') or _get_int('cambagem_previsao') or getattr(rdo_obj, 'cambagem_previsao', None) or getattr(rdo_obj, 'cambagem', None),
            'residuos_solidos': _get_decimal('residuos_solidos', model_key='residuos_solidos'),
            'residuos_totais': _get_decimal('residuos_totais', model_key='residuos_totais'),
            'bombeio': _get_decimal('bombeio', model_key='bombeio'),
            'total_liquido': _get_int('total_liquido') or _get_int('residuo_liquido') or _get_int('residuo'),
            'avanco_limpeza': request.POST.get('avanco_limpeza') or None,
            'avanco_limpeza_fina': request.POST.get('avanco_limpeza_fina') or None,
            'percentual_limpeza_diario': _get_decimal('percentual_limpeza_diario', model_key='percentual_limpeza_diario') or _get_decimal('percentual_limpeza', model_key='percentual_limpeza_diario') or None,
            'percentual_limpeza_fina_diario': _get_decimal('percentual_limpeza_fina_diario', model_key='percentual_limpeza_fina_diario') or _get_decimal('percentual_limpeza_fina', model_key='percentual_limpeza_fina_diario') or None,
            'percentual_limpeza_cumulativo': _get_decimal('percentual_limpeza_cumulativo', model_key='percentual_limpeza_cumulativo') or _get_decimal('limpeza_acu', model_key='percentual_limpeza_cumulativo') or None,
            'percentual_limpeza_fina_cumulativo': _get_decimal('percentual_limpeza_fina_cumulativo', model_key='percentual_limpeza_fina_cumulativo') or _get_decimal('limpeza_fina_acu', model_key='percentual_limpeza_fina_cumulativo') or None,
            'percentual_ensacamento': _get_decimal('percentual_ensacamento', model_key='percentual_ensacamento') or None,
            'percentual_icamento': _get_decimal('percentual_icamento', model_key='percentual_icamento') or None,
            'percentual_cambagem': _get_decimal('percentual_cambagem', model_key='percentual_cambagem') or None,
            'percentual_avanco': _get_decimal('percentual_avanco', model_key='percentual_avanco') or None,
            'sentido_limpeza': _parse_sentido(),
        }

        try:
            _sanitize_model_decimal_payload(RdoTanque, tanque_data, logger=logger, context=f'add_tank_ajax rdo_id={rdo_id}')
        except Exception:
            pass

        def _incoming_tank_identity_key(data_obj=None, tank_obj=None):
            try:
                os_num_ref = None
                try:
                    os_num_ref = getattr(getattr(rdo_obj, 'ordem_servico', None), 'numero_os', None)
                except Exception:
                    os_num_ref = None
                if tank_obj is not None:
                    return _tank_identity_key(
                        getattr(tank_obj, 'tanque_codigo', None),
                        getattr(tank_obj, 'nome_tanque', None),
                        os_num=os_num_ref,
                    )
                src = data_obj if isinstance(data_obj, dict) else tanque_data
                return _tank_identity_key(src.get('tanque_codigo'), src.get('nome_tanque'), os_num=os_num_ref)
            except Exception:
                return None

        try:
            date_keys = ('tanque_data', 'data', 'snapshot_date', 'tanque_date')
            for dk in date_keys:
                if dk in request.POST and request.POST.get(dk):
                    raw = request.POST.get(dk)
                    posted_date = None
                    try:
                        posted_date = datetime.fromisoformat(raw).date()
                    except Exception:
                        try:
                            posted_date = datetime.strptime(raw, '%d/%m/%Y').date()
                        except Exception:
                            try:
                                posted_date = datetime.strptime(raw, '%Y-%m-%d').date()
                            except Exception:
                                posted_date = None
                    if posted_date is not None and getattr(rdo_obj, 'data', None) is not None:
                        if posted_date != rdo_obj.data:
                            return JsonResponse({'success': False, 'error': 'A data do tanque deve ser a mesma do RDO.'}, status=400)
        except Exception:
            logging.getLogger(__name__).exception('Erro ao validar data do tanque enviada pelo cliente')

        def _build_tank_payload(obj):
            ensac_prev = _get_tank_prediction_group_value(obj, 'ensacamento_prev')
            if not _has_defined_prediction_value(ensac_prev):
                ensac_prev = getattr(obj, 'ensacamento_prev', None)
            ic_prev = _get_tank_prediction_group_value(obj, 'icamento_prev')
            if not _has_defined_prediction_value(ic_prev):
                ic_prev = getattr(obj, 'icamento_prev', None)
            camb_prev = _get_tank_prediction_group_value(obj, 'cambagem_prev')
            if not _has_defined_prediction_value(camb_prev):
                camb_prev = getattr(obj, 'cambagem_prev', None)
            previsao = _get_tank_prediction_group_value(obj, 'previsao_termino')
            if not _has_defined_prediction_value(previsao):
                previsao = getattr(obj, 'previsao_termino', None)
            return {
                'id': obj.id,
                'tanque_codigo': obj.tanque_codigo,
                'nome_tanque': obj.nome_tanque,
                'tipo_tanque': obj.tipo_tanque,
                'numero_compartimentos': obj.numero_compartimentos,
                'gavetas': obj.gavetas,
                'patamares': obj.patamares,
                'volume_tanque_exec': str(obj.volume_tanque_exec) if obj.volume_tanque_exec is not None else None,
                'servico_exec': obj.servico_exec,
                'metodo_exec': obj.metodo_exec,
                'ensacamento_dia': getattr(obj, 'ensacamento_dia', None),
                'icamento_dia': getattr(obj, 'icamento_dia', None),
                'cambagem_dia': getattr(obj, 'cambagem_dia', None),
                'tambores_dia': getattr(obj, 'tambores_dia', None),
                'tambores_cumulativo': getattr(obj, 'tambores_cumulativo', None),
                'tambores_acu': getattr(obj, 'tambores_cumulativo', None),
                'sentido_limpeza': getattr(obj, 'sentido_limpeza', None),
                'bombeio': getattr(obj, 'bombeio', None),
                'total_liquido': getattr(obj, 'total_liquido', None),
                'ensacamento_cumulativo': getattr(obj, 'ensacamento_cumulativo', None),
                'icamento_cumulativo': getattr(obj, 'icamento_cumulativo', None),
                'cambagem_cumulativo': getattr(obj, 'cambagem_cumulativo', None),
                'ensacamento_prev': ensac_prev,
                'icamento_prev': ic_prev,
                'cambagem_prev': camb_prev,
                'previsao_termino': (previsao.isoformat() if hasattr(previsao, 'isoformat') and previsao else previsao),
                'previsao_termino_locked': _is_tank_prediction_locked(obj, 'previsao_termino'),
                'total_liquido_acu': getattr(obj, 'total_liquido_cumulativo', None),
                'residuos_solidos_acu': getattr(obj, 'residuos_solidos_cumulativo', None),
                'compartimentos_avanco_json': getattr(obj, 'compartimentos_avanco_json', None),
            }

        def _clone_rdotanque_to_rdo(source_obj, target_rdo):
            clone = RdoTanque()
            for f in source_obj._meta.fields:
                try:
                    if getattr(f, 'primary_key', False):
                        continue
                    if f.name in ('id', 'pk', 'rdo'):
                        continue
                    if getattr(f, 'auto_now', False) or getattr(f, 'auto_now_add', False):
                        continue
                    setattr(clone, f.name, getattr(source_obj, f.name))
                except Exception:
                    continue
            clone.rdo = target_rdo

            try:
                for fname in (
                    # Campos diários/operacionais NÃO devem ser carregados do RDO anterior
                    'espaco_confinado',
                    'operadores_simultaneos',
                    'h2s_ppm', 'lel', 'co_ppm', 'o2_percent',
                    'total_n_efetivo_confinado',
                    'sentido_limpeza',
                    'tempo_bomba',
                    'ensacamento_dia', 'icamento_dia', 'cambagem_dia',
                    'tambores_dia',
                    'residuos_solidos', 'residuos_totais',
                    'bombeio', 'total_liquido',
                    'avanco_limpeza', 'avanco_limpeza_fina',
                    'limpeza_mecanizada_diaria', 'limpeza_fina_diaria',
                    'percentual_limpeza_diario', 'percentual_limpeza_fina_diario',
                    'percentual_limpeza_fina',
                    'percentual_avanco',
                    'percentual_ensacamento', 'percentual_icamento', 'percentual_cambagem',
                    'compartimentos_avanco_json',

                    'ensacamento_cumulativo', 'icamento_cumulativo', 'cambagem_cumulativo',
                    'tambores_cumulativo',
                    'total_liquido_cumulativo', 'residuos_solidos_cumulativo',
                    'limpeza_mecanizada_cumulativa', 'percentual_limpeza_cumulativo',
                    'limpeza_fina_cumulativa', 'percentual_limpeza_fina_cumulativo',
                    'percentual_avanco_cumulativo',
                ):
                    if hasattr(clone, fname):
                        setattr(clone, fname, None)
            except Exception:
                pass

            clone.save()
            return clone

        def _copy_fixed_tank_fields(source_obj, target_obj):
            fixed_fields = (
                'tanque_codigo', 'nome_tanque', 'tipo_tanque',
                'numero_compartimentos', 'gavetas', 'patamares',
                'volume_tanque_exec', 'servico_exec', 'metodo_exec',
                'ensacamento_prev', 'icamento_prev', 'cambagem_prev', 'previsao_termino',
            )
            for fname in fixed_fields:
                try:
                    if not hasattr(target_obj, fname):
                        continue
                    if fname in _TANK_PREDICTION_FIELDS and _is_tank_prediction_locked(target_obj, fname):
                        continue
                    val = getattr(source_obj, fname, None)
                    if val is None:
                        continue
                    setattr(target_obj, fname, val)
                except Exception:
                    continue

        def _norm_blank_identifier(val):
            try:
                s = str(val or '').strip()
            except Exception:
                s = ''
            if not s:
                return ''
            if s.lower() in ('-', '--', 'na', 'n/a', 'nenhum', 'none', 'null'):
                return ''
            return s

        def _is_unidentified_tank(obj):
            try:
                code = _norm_blank_identifier(getattr(obj, 'tanque_codigo', None))
            except Exception:
                code = ''
            try:
                name = _norm_blank_identifier(getattr(obj, 'nome_tanque', None))
            except Exception:
                name = ''
            return (not code) and (not name)

        def _tank_content_score(obj):
            # Prioriza reaproveitar a linha "errada" que já recebeu preenchimento de KPI diário.
            score_fields = (
                'tipo_tanque', 'numero_compartimentos', 'gavetas', 'patamares',
                'volume_tanque_exec', 'servico_exec', 'metodo_exec',
                'espaco_confinado', 'operadores_simultaneos',
                'h2s_ppm', 'lel', 'co_ppm', 'o2_percent',
                'total_n_efetivo_confinado', 'sentido_limpeza', 'tempo_bomba',
                'ensacamento_dia', 'icamento_dia', 'cambagem_dia', 'tambores_dia',
                'residuos_solidos', 'residuos_totais', 'bombeio', 'total_liquido',
                'avanco_limpeza', 'avanco_limpeza_fina',
                'limpeza_mecanizada_diaria', 'limpeza_fina_diaria',
                'percentual_limpeza_diario', 'percentual_limpeza_fina_diario',
                'percentual_ensacamento', 'percentual_icamento', 'percentual_cambagem',
                'percentual_avanco',
                'ensacamento_cumulativo', 'icamento_cumulativo', 'cambagem_cumulativo',
                'tambores_cumulativo', 'total_liquido_cumulativo', 'residuos_solidos_cumulativo',
                'limpeza_mecanizada_cumulativa', 'percentual_limpeza_cumulativo',
                'limpeza_fina_cumulativa', 'percentual_limpeza_fina_cumulativo',
                'percentual_avanco_cumulativo',
                'compartimentos_avanco_json',
            )
            score = 0
            for fname in score_fields:
                try:
                    v = getattr(obj, fname, None)
                except Exception:
                    v = None
                if v not in (None, ''):
                    score += 1
            return score

        if tanque_id_int is not None:
            try:
                tank_obj = RdoTanque.objects.select_related('rdo__ordem_servico').get(pk=tanque_id_int)
            except RdoTanque.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Tanque não encontrado.'}, status=404)

            try:
                ordem_rdo = getattr(rdo_obj, 'ordem_servico', None)
                ordem_tank = getattr(getattr(tank_obj, 'rdo', None), 'ordem_servico', None)
                if ordem_rdo is not None and ordem_tank is not None:
                    same_os = False
                    try:
                        same_os = (getattr(ordem_rdo, 'id', None) == getattr(ordem_tank, 'id', None))
                    except Exception:
                        same_os = False
                    if not same_os:
                        try:
                            num_rdo = getattr(ordem_rdo, 'numero_os', None)
                            num_tank = getattr(ordem_tank, 'numero_os', None)
                            same_os = (num_rdo not in (None, '') and num_tank not in (None, '') and str(num_rdo) == str(num_tank))
                        except Exception:
                            same_os = False
                    if not same_os:
                        return JsonResponse({'success': False, 'error': 'Tanque não pertence a esta OS.'}, status=400)
            except Exception:
                pass

            target_obj = tank_obj
            association_mode = 'same_rdo'
            duplicate_existing_to_delete = None
            try:
                if getattr(tank_obj, 'rdo_id', None) != getattr(rdo_obj, 'id', None):
                    placeholder = None
                    placeholder_score = -1
                    try:
                        reuse_candidates = []
                        for cand in RdoTanque.objects.filter(rdo=rdo_obj).order_by('-id'):
                            if not _is_unidentified_tank(cand):
                                continue
                            try:
                                score = _tank_content_score(cand)
                            except Exception:
                                score = 0
                            try:
                                cid = int(getattr(cand, 'id', 0) or 0)
                            except Exception:
                                cid = 0
                            reuse_candidates.append((score, cid, cand))
                        if reuse_candidates:
                            reuse_candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
                            placeholder_score, _, placeholder = reuse_candidates[0]
                    except Exception:
                        placeholder = None
                        placeholder_score = -1

                    try:
                        codigo_src = (getattr(tank_obj, 'tanque_codigo', None) or '').strip()
                        nome_src = (getattr(tank_obj, 'nome_tanque', None) or '').strip()
                        q = Q(rdo=rdo_obj)
                        match = Q()
                        if codigo_src:
                            match |= Q(tanque_codigo__iexact=codigo_src)
                        if nome_src:
                            match |= Q(nome_tanque__iexact=nome_src)
                        if match:
                            existing = RdoTanque.objects.filter(q).filter(match).first()
                        else:
                            existing = None
                    except Exception:
                        existing = None

                    if existing is not None and placeholder is not None and getattr(existing, 'id', None) != getattr(placeholder, 'id', None) and placeholder_score > 0:
                        target_obj = placeholder
                        association_mode = 'reused_placeholder'
                        duplicate_existing_to_delete = existing
                    elif existing is not None:
                        target_obj = existing
                        association_mode = 'matched_existing'
                    elif placeholder is not None:
                        target_obj = placeholder
                        association_mode = 'reused_placeholder'
                    else:
                        # Associação por tanque_id selecionado não deve ser bloqueada por limite:
                        # é um tanque já existente da OS e não uma criação nova.
                        target_obj = _clone_rdotanque_to_rdo(tank_obj, rdo_obj)
                        association_mode = 'cloned'

                    try:
                        if getattr(target_obj, 'id', None) != getattr(tank_obj, 'id', None):
                            _copy_fixed_tank_fields(tank_obj, target_obj)
                    except Exception:
                        pass
            except Exception:
                target_obj = tank_obj
                association_mode = 'same_rdo'

            for k, v in tanque_data.items():
                if v is None:
                    continue
                if k in _TANK_PREDICTION_FIELDS and _is_tank_prediction_locked(target_obj, k):
                    continue
                try:
                    setattr(target_obj, k, v)
                except Exception:
                    pass

            comp_validation = None
            try:
                total_comp = tanque_data.get('numero_compartimentos') or getattr(target_obj, 'numero_compartimentos', None) or getattr(rdo_obj, 'numero_compartimentos', None)
                comp_validation = _validate_compartimentos_payload_for_tank(
                    target_obj,
                    request.POST.get,
                    get_list=request.POST.getlist if hasattr(request.POST, 'getlist') else None,
                    total_compartimentos=total_comp,
                )
            except Exception:
                comp_validation = None
            if comp_validation is not None:
                if not comp_validation.get('is_valid'):
                    return JsonResponse({
                        'success': False,
                        'error': (comp_validation.get('errors') or [{}])[0].get('message') or 'Avanço inválido para o compartimento.',
                        'errors': comp_validation.get('errors') or [],
                    }, status=400)
                try:
                    target_obj.compartimentos_avanco_json = comp_validation.get('json')
                    target_obj.compute_limpeza_from_compartimentos()
                except Exception:
                    logger.exception('Falha ao aplicar avanço por compartimento no tanque %s', getattr(target_obj, 'id', None))
            _safe_save_global(target_obj)

            try:
                if hasattr(target_obj, 'recompute_metrics') and callable(target_obj.recompute_metrics):
                    target_obj.recompute_metrics(only_when_missing=False)
                    _safe_save_global(target_obj)
            except Exception:
                logger.exception('Falha ao recomputar cumulativos por tanque (id=%s)', getattr(target_obj, 'id', None))

            try:
                if duplicate_existing_to_delete is not None:
                    dup_id = getattr(duplicate_existing_to_delete, 'id', None)
                    tgt_id = getattr(target_obj, 'id', None)
                    if dup_id is not None and tgt_id is not None and int(dup_id) != int(tgt_id):
                        try:
                            duplicate_existing_to_delete.delete()
                        except Exception:
                            logger.exception(
                                'Falha ao remover tanque duplicado após associação (rdo_id=%s dup_id=%s target_id=%s)',
                                getattr(rdo_obj, 'id', None), dup_id, tgt_id
                            )
            except Exception:
                pass

            # Ao associar um tanque existente ao RDO, garantir que os campos fixos do RDO
            # (código, nome, tipo, compartimentos, gavetas, patamares, volume, serviço, método)
            # sigam os valores já definidos no objeto do tanque. Isso evita inconsistências
            # quando o RDO foi criado sem selecionar um tanque e tem valores diferentes.
            try:
                # Campos fixos que devem seguir o tanque selecionado, incluindo
                # campos de previsão/prev suffixes que podem existir em modelos
                rdo_fields_to_inherit = (
                    'tanque_codigo', 'nome_tanque', 'tipo_tanque',
                    'numero_compartimentos', 'gavetas', 'patamares',
                    'volume_tanque_exec', 'servico_exec', 'metodo_exec',
                    # campos de previsão — manter iguais ao primeiro tanque preenchido
                    'ensacamento_prev', 'icamento_prev', 'cambagem_prev',
                    'ensacamento_previsao', 'icamento_previsao', 'cambagem_previsao',
                    'tambores_prev', 'tambores_previsao'
                )
                rdo_changed = False
                for fld in rdo_fields_to_inherit:
                    try:
                        # obter valor do tanque (pode ter nomes ligeiramente diferentes)
                        val = getattr(target_obj, fld, None)
                    except Exception:
                        val = None
                    try:
                        # verificar se o campo existe no modelo RDO antes de sobrescrever
                        try:
                            rdo_obj._meta.get_field(fld)
                            field_exists = True
                        except Exception:
                            field_exists = False
                        if not field_exists:
                            continue
                        # Apenas sobrescrever quando o tanque tem valor não nulo
                        # e for diferente do atual no RDO.
                        if val is not None and getattr(rdo_obj, fld, None) != val:
                            setattr(rdo_obj, fld, val)
                            rdo_changed = True
                    except Exception:
                        continue
                if rdo_changed:
                    _safe_save_global(rdo_obj)
            except Exception:
                logger.exception('Falha ao propagar campos fixos do tanque para o RDO (rdo_id=%s tank_id=%s)', getattr(rdo_obj, 'id', None), getattr(target_obj, 'id', None))

            msg = 'Tanque atualizado'
            try:
                if association_mode == 'cloned':
                    msg = 'Tanque copiado para este RDO'
                elif association_mode in ('matched_existing', 'reused_placeholder'):
                    msg = 'Tanque associado neste RDO'
            except Exception:
                pass
            try:
                rdo_payload_min = {
                    'id': getattr(rdo_obj, 'id', None),
                    'ordem_servico_id': (getattr(getattr(rdo_obj, 'ordem_servico', None), 'id', None) or getattr(rdo_obj, 'ordem_servico_id', None)),
                    'tanque_codigo': getattr(rdo_obj, 'tanque_codigo', None),
                    'nome_tanque': getattr(rdo_obj, 'nome_tanque', None),
                    'tipo_tanque': getattr(rdo_obj, 'tipo_tanque', None),
                    'volume_tanque_exec': (str(getattr(rdo_obj, 'volume_tanque_exec')) if getattr(rdo_obj, 'volume_tanque_exec', None) is not None else None),
                }
            except Exception:
                rdo_payload_min = None

            # Remover RDOs vazios (mesma OS) quando seguro
            deleted = []
            try:
                ordem = getattr(rdo_obj, 'ordem_servico', None)
                if ordem is not None:
                    def _is_placeholder_rdo(cand):
                        """Considera deletável apenas o RDO realmente vazio/placeholder.

                        Regra: sem tanques, sem atividades, sem membros, e sem conteúdo relevante
                        (fotos/observações/planejamento/ec_times/avanco).
                        """
                        try:
                            has_tanks = getattr(cand, 'tanques', None) and cand.tanques.exists()
                        except Exception:
                            has_tanks = False
                        try:
                            has_ativ = RDOAtividade.objects.filter(rdo=cand).exists()
                        except Exception:
                            has_ativ = False
                        try:
                            has_memb = RDOMembroEquipe.objects.filter(rdo=cand).exists()
                        except Exception:
                            has_memb = False
                        if has_tanks or has_ativ or has_memb:
                            return False

                        # se já tem tanque preenchido no próprio RDO, não é placeholder
                        try:
                            if (getattr(cand, 'tanque_codigo', None) or '').strip():
                                return False
                        except Exception:
                            pass
                        try:
                            if (getattr(cand, 'nome_tanque', None) or '').strip():
                                return False
                        except Exception:
                            pass

                        # conteúdo relevante que impede exclusão automática
                        try:
                            text_fields = (
                                'observacoes_rdo_pt', 'observacoes_rdo_en',
                                'ciente_observacoes_pt', 'ciente_observacoes_en',
                                'planejamento_pt', 'planejamento_en',
                                'ec_times_json', 'fotos_json',
                                'compartimentos_avanco_json',
                            )
                            for f in text_fields:
                                try:
                                    v = getattr(cand, f, None)
                                except Exception:
                                    v = None
                                if isinstance(v, str) and v.strip():
                                    return False
                        except Exception:
                            # se falhar a verificação, não deletar
                            return False

                        try:
                            photo_fields = ('fotos_img', 'fotos_1', 'fotos_2', 'fotos_3', 'fotos_4', 'fotos_5')
                            for f in photo_fields:
                                try:
                                    if getattr(cand, f, None):
                                        return False
                                except Exception:
                                    # se não conseguir checar, ser conservador
                                    return False
                        except Exception:
                            return False

                        return True

                    candidates = RDO.objects.filter(ordem_servico=ordem).exclude(pk=getattr(rdo_obj, 'id', None))
                    for cand in candidates:
                        try:
                            if _is_placeholder_rdo(cand):
                                deleted.append(getattr(cand, 'id', None))
                                cand.delete()
                        except Exception:
                            continue
            except Exception:
                logger.exception('Falha ao tentar limpar RDOs vazios após associação de tanque (rdo_id=%s)', getattr(rdo_obj, 'id', None))

            try:
                current_after_assoc, _keys_after_assoc = _refresh_os_tank_progress()
            except Exception:
                current_after_assoc = None
            return JsonResponse({
                'success': True,
                'message': msg,
                'tank': _build_tank_payload(target_obj),
                'rdo': rdo_payload_min,
                'deleted_rdos': deleted,
                'tank_limit': _tank_limit_payload(current_after_assoc),
            })

        try:
            if tanque_data.get('sentido_limpeza') is None and getattr(rdo_obj, 'sentido_limpeza', None) is not None:
                inherited = getattr(rdo_obj, 'sentido_limpeza', None)
                try:
                    tanque_data['sentido_limpeza'] = _canonicalize_sentido(inherited) or inherited
                except Exception:
                    tanque_data['sentido_limpeza'] = inherited
        except Exception:
            pass

        if service_limit_count is not None:
            try:
                current_count_for_limit, current_keys_for_limit = _refresh_os_tank_progress()
            except Exception:
                current_count_for_limit, current_keys_for_limit = (0, set())
            incoming_key = _incoming_tank_identity_key(data_obj=tanque_data)
            introduces_new_tank = bool(incoming_key and incoming_key not in (current_keys_for_limit or set()))
            if introduces_new_tank and current_count_for_limit >= int(service_limit_count):
                return JsonResponse({
                    'success': False,
                    'error': f'Limite de tanques atingido para esta OS ({service_limit_count}). Ajuste os serviços na Home para permitir novos tanques.',
                    'tank_limit': _tank_limit_payload(current_count_for_limit),
                }, status=400)

        try:
            codigo_check = (tanque_data.get('tanque_codigo') or '')
            nome_check = (tanque_data.get('nome_tanque') or '')
            codigo_check = codigo_check.strip() if isinstance(codigo_check, str) else ''
            nome_check = nome_check.strip() if isinstance(nome_check, str) else ''
            if codigo_check or nome_check:
                match = Q()
                if codigo_check:
                    match |= Q(tanque_codigo__iexact=codigo_check)
                if nome_check:
                    match |= Q(nome_tanque__iexact=nome_check)
                if match and RdoTanque.objects.filter(rdo=rdo_obj).filter(match).exists():
                    return JsonResponse({'success': False, 'error': 'Já existe um tanque com o mesmo código ou nome neste RDO.'}, status=400)
        except Exception:
            logging.getLogger(__name__).exception('Erro ao checar duplicidade de tanque')

        tank = RdoTanque(rdo=rdo_obj, **{k: v for k, v in tanque_data.items() if v is not None})
        try:
            total_comp = tanque_data.get('numero_compartimentos') or getattr(rdo_obj, 'numero_compartimentos', None)
            comp_validation = _validate_compartimentos_payload_for_tank(
                tank,
                request.POST.get,
                get_list=request.POST.getlist if hasattr(request.POST, 'getlist') else None,
                total_compartimentos=total_comp,
            )
        except Exception:
            comp_validation = None
        if comp_validation is not None:
            if not comp_validation.get('is_valid'):
                return JsonResponse({
                    'success': False,
                    'error': (comp_validation.get('errors') or [{}])[0].get('message') or 'Avanço inválido para o compartimento.',
                    'errors': comp_validation.get('errors') or [],
                }, status=400)
            try:
                tank.compartimentos_avanco_json = comp_validation.get('json')
                tank.compute_limpeza_from_compartimentos()
            except Exception:
                logger.exception('Falha ao aplicar avanço por compartimento no tanque novo do RDO %s', rdo_id)
        _safe_save_global(tank)

        try:
            if hasattr(tank, 'recompute_metrics') and callable(tank.recompute_metrics):
                tank.recompute_metrics(only_when_missing=False)
                _safe_save_global(tank)
        except Exception:
            pass

        # Garantir que o RDO herde os campos fixos do tanque recém-criado.
        # A tabela do RDO renderiza `tanque_codigo`/`nome_tanque` diretamente do RDO,
        # então se isso ficar nulo o usuário vê '-' mesmo com tanque criado.
        try:
            rdo_fields_to_inherit = (
                'tanque_codigo', 'nome_tanque', 'tipo_tanque',
                'numero_compartimentos', 'gavetas', 'patamares',
                'volume_tanque_exec', 'servico_exec', 'metodo_exec',
                'ensacamento_prev', 'icamento_prev', 'cambagem_prev',
                'ensacamento_previsao', 'icamento_previsao', 'cambagem_previsao',
                'tambores_prev', 'tambores_previsao'
            )
            rdo_changed = False
            for fld in rdo_fields_to_inherit:
                try:
                    val = getattr(tank, fld, None)
                except Exception:
                    val = None

                try:
                    try:
                        rdo_obj._meta.get_field(fld)
                        field_exists = True
                    except Exception:
                        field_exists = False
                    if not field_exists:
                        continue

                    if val is not None and getattr(rdo_obj, fld, None) != val:
                        setattr(rdo_obj, fld, val)
                        rdo_changed = True
                except Exception:
                    continue

            if rdo_changed:
                _safe_save_global(rdo_obj)
        except Exception:
            logger.exception('Falha ao propagar campos fixos do tanque criado para o RDO (rdo_id=%s tank_id=%s)', getattr(rdo_obj, 'id', None), getattr(tank, 'id', None))

        tank_payload = {
            'id': tank.id,
            'tanque_codigo': tank.tanque_codigo,
            'nome_tanque': tank.nome_tanque,
            'tipo_tanque': tank.tipo_tanque,
            'numero_compartimentos': tank.numero_compartimentos,
            'gavetas': tank.gavetas,
            'patamares': tank.patamares,
            'volume_tanque_exec': str(tank.volume_tanque_exec) if tank.volume_tanque_exec is not None else None,
            'servico_exec': tank.servico_exec,
            'metodo_exec': tank.metodo_exec,
            'ensacamento_dia': getattr(tank, 'ensacamento_dia', None),
            'icamento_dia': getattr(tank, 'icamento_dia', None),
            'cambagem_dia': getattr(tank, 'cambagem_dia', None),
            'tambores_dia': getattr(tank, 'tambores_dia', None),
            'tambores_cumulativo': getattr(tank, 'tambores_cumulativo', None),
            'tambores_acu': getattr(tank, 'tambores_cumulativo', None),
            'sentido_limpeza': getattr(tank, 'sentido_limpeza', None),
            'bombeio': getattr(tank, 'bombeio', None),
            'total_liquido': getattr(tank, 'total_liquido', None),
            'ensacamento_cumulativo': getattr(tank, 'ensacamento_cumulativo', None),
            'icamento_cumulativo': getattr(tank, 'icamento_cumulativo', None),
            'cambagem_cumulativo': getattr(tank, 'cambagem_cumulativo', None),
            'previsao_termino': (getattr(tank, 'previsao_termino', None).isoformat() if getattr(tank, 'previsao_termino', None) else None),
            'total_liquido_acu': getattr(tank, 'total_liquido_cumulativo', None),
            'residuos_solidos_acu': getattr(tank, 'residuos_solidos_cumulativo', None),
            'compartimentos_avanco_json': getattr(tank, 'compartimentos_avanco_json', None),
        }

        try:
            rdo_payload_min = {
                'id': getattr(rdo_obj, 'id', None),
                'ordem_servico_id': (getattr(getattr(rdo_obj, 'ordem_servico', None), 'id', None) or getattr(rdo_obj, 'ordem_servico_id', None)),
                'tanque_codigo': getattr(rdo_obj, 'tanque_codigo', None),
                'nome_tanque': getattr(rdo_obj, 'nome_tanque', None),
                'tipo_tanque': getattr(rdo_obj, 'tipo_tanque', None),
                'volume_tanque_exec': (str(getattr(rdo_obj, 'volume_tanque_exec')) if getattr(rdo_obj, 'volume_tanque_exec', None) is not None else None),
            }
        except Exception:
            rdo_payload_min = None

        deleted = []
        try:
            ordem = getattr(rdo_obj, 'ordem_servico', None)
            if ordem is not None:
                def _is_placeholder_rdo(cand):
                    try:
                        has_tanks = getattr(cand, 'tanques', None) and cand.tanques.exists()
                    except Exception:
                        has_tanks = False
                    try:
                        has_ativ = RDOAtividade.objects.filter(rdo=cand).exists()
                    except Exception:
                        has_ativ = False
                    try:
                        has_memb = RDOMembroEquipe.objects.filter(rdo=cand).exists()
                    except Exception:
                        has_memb = False
                    if has_tanks or has_ativ or has_memb:
                        return False

                    try:
                        if (getattr(cand, 'tanque_codigo', None) or '').strip():
                            return False
                    except Exception:
                        pass
                    try:
                        if (getattr(cand, 'nome_tanque', None) or '').strip():
                            return False
                    except Exception:
                        pass

                    try:
                        text_fields = (
                            'observacoes_rdo_pt', 'observacoes_rdo_en',
                            'ciente_observacoes_pt', 'ciente_observacoes_en',
                            'planejamento_pt', 'planejamento_en',
                            'ec_times_json', 'fotos_json',
                            'compartimentos_avanco_json',
                        )
                        for f in text_fields:
                            try:
                                v = getattr(cand, f, None)
                            except Exception:
                                v = None
                            if isinstance(v, str) and v.strip():
                                return False
                    except Exception:
                        return False

                    try:
                        photo_fields = ('fotos_img', 'fotos_1', 'fotos_2', 'fotos_3', 'fotos_4', 'fotos_5')
                        for f in photo_fields:
                            try:
                                if getattr(cand, f, None):
                                    return False
                            except Exception:
                                return False
                    except Exception:
                        return False

                    return True

                candidates = RDO.objects.filter(ordem_servico=ordem).exclude(pk=getattr(rdo_obj, 'id', None))
                for cand in candidates:
                    try:
                        if _is_placeholder_rdo(cand):
                            deleted.append(getattr(cand, 'id', None))
                            cand.delete()
                    except Exception:
                        continue
        except Exception:
            logger.exception('Falha ao tentar limpar RDOs vazios após criação de tanque (rdo_id=%s)', getattr(rdo_obj, 'id', None))

        try:
            current_after_create, _keys_after_create = _refresh_os_tank_progress()
        except Exception:
            current_after_create = None
        return JsonResponse({
            'success': True,
            'message': 'Tanque criado',
            'tank': tank_payload,
            'rdo': rdo_payload_min,
            'deleted_rdos': deleted,
            'tank_limit': _tank_limit_payload(current_after_create),
        })
    except DjangoOperationalError as e:
        try:
            if 'locked' in str(e).lower():
                logger.exception('Banco ocupado (database is locked) em add_tank_ajax')
                return JsonResponse({'success': False, 'error': 'Banco de dados ocupado no momento. Tente novamente em alguns segundos.'}, status=503)
        except Exception:
            pass
        logger.exception('Erro operacional em add_tank_ajax')
        return JsonResponse({'success': False, 'error': 'Erro operacional no banco de dados.'}, status=500)
    except Exception:
        logger.exception('Erro em add_tank_ajax')
        return JsonResponse({'success': False, 'error': 'Erro interno'}, status=500)

@login_required(login_url='/login/')
@require_POST
def upload_rdo_photos(request, rdo_id):
    logger = logging.getLogger(__name__)
    read_only_response = _guard_read_only_json(request, 'anexar fotos ao RDO')
    if read_only_response is not None:
        return read_only_response

    try:
        logger.info(
            'upload_rdo_photos called by user=%s for rdo_id=%s POST_keys=%s',
            getattr(request, 'user', None),
            rdo_id,
            list(request.POST.keys()),
        )
        try:
            rdo_obj = RDO.objects.get(pk=rdo_id)
        except RDO.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'RDO não encontrado.'}, status=404)

        files = []
        try:
            candidate_keys = ['fotos', 'fotos[]']
            for i in range(0, 20):
                candidate_keys.append(f'fotos[{i}]')
            if hasattr(request.FILES, 'getlist'):
                for k in candidate_keys:
                    try:
                        lst = request.FILES.getlist(k)
                    except Exception:
                        lst = []
                    if lst:
                        files.extend(list(lst))
            if not files:
                try:
                    single = request.FILES.get('fotos') if hasattr(request, 'FILES') else None
                    if single:
                        files.append(single)
                except Exception:
                    pass
            if not files:
                for i in range(1, 6):
                    try:
                        f = request.FILES.get(f'foto{i}') if hasattr(request, 'FILES') else None
                    except Exception:
                        f = None
                    if f:
                        files.append(f)
        except Exception:
            files = []

        if not files:
            return JsonResponse({'success': False, 'error': 'Nenhuma foto enviada.'}, status=400)

        try:
            deduped_files = []
            seen = set()
            for f in files:
                try:
                    key = (str(getattr(f, 'name', '') or '').strip(), int(getattr(f, 'size', 0) or 0))
                except Exception:
                    key = None
                if key is None:
                    deduped_files.append(f)
                    continue
                if key in seen:
                    continue
                seen.add(key)
                deduped_files.append(f)
            files = deduped_files
        except Exception:
            pass

        slot_fields = [f'fotos_{i}' for i in range(1, 6)]
        empty_slots = []
        for slot in slot_fields:
            try:
                current = getattr(rdo_obj, slot, None)
                current_name = getattr(current, 'name', None) if current is not None else None
                if not current_name:
                    empty_slots.append(slot)
            except Exception:
                empty_slots.append(slot)

        if not empty_slots:
            return JsonResponse(
                {
                    'success': False,
                    'error': 'Limite de 5 fotos já atingido neste RDO.',
                },
                status=400,
            )

        fotos_saved = []
        skipped_count = 0
        try:
            from django.core.files.base import ContentFile
            from django.core.files.storage import default_storage

            for f in files:
                if not empty_slots:
                    skipped_count += 1
                    continue

                slot_name = empty_slots.pop(0)
                try:
                    original_name = os.path.basename(str(getattr(f, 'name', '') or '').strip()) or 'foto.jpg'
                    safe_name = original_name.replace(' ', '_')
                    name = f'rdos/{datetime.now().strftime("%Y%m%d%H%M%S%f")}_{safe_name}'
                    try:
                        if hasattr(f, 'seek'):
                            f.seek(0)
                    except Exception:
                        pass

                    try:
                        target_field = getattr(rdo_obj, slot_name, None)
                        if target_field is not None and hasattr(target_field, 'save'):
                            target_field.save(name, ContentFile(f.read()), save=False)
                            saved_name = getattr(getattr(rdo_obj, slot_name, None), 'name', None) or name
                        else:
                            saved_name = default_storage.save(name, ContentFile(f.read()))
                    except Exception:
                        try:
                            if hasattr(f, 'seek'):
                                f.seek(0)
                        except Exception:
                            pass
                        try:
                            saved_name = default_storage.save(name, ContentFile(f.read()))
                        except Exception:
                            skipped_count += 1
                            logger.exception('Falha salvando uma foto enviada')
                            continue

                    try:
                        public_url = default_storage.url(saved_name) if hasattr(default_storage, 'url') else saved_name
                    except Exception:
                        public_url = saved_name
                    if public_url:
                        fotos_saved.append(public_url)
                except Exception:
                    skipped_count += 1
                    logger.exception('Erro processando arquivo enviado')

            try:
                fotos_paths = []
                for slot in slot_fields:
                    try:
                        ff = getattr(rdo_obj, slot, None)
                        saved_path = getattr(ff, 'name', None) if ff is not None else None
                    except Exception:
                        saved_path = None
                    if not saved_path:
                        continue
                    normalized = str(saved_path).replace('\\', '/').lstrip('/')
                    if normalized not in fotos_paths:
                        fotos_paths.append(normalized)
                try:
                    rdo_obj.fotos_json = json.dumps(fotos_paths, ensure_ascii=False)
                except Exception:
                    rdo_obj.fotos_json = json.dumps(fotos_paths)
            except Exception:
                logger.exception('Falha ao preparar fotos_json no upload_rdo_photos')

            try:
                rdo_obj.save(
                    update_fields=[
                        *slot_fields,
                        'fotos_json',
                    ]
                )
            except Exception:
                logger.exception('Falha ao salvar RDO após anexar fotos')
                rdo_obj.save()
        except Exception:
            logger.exception('Erro salvando fotos no upload_rdo_photos')

        if not fotos_saved:
            return JsonResponse(
                {
                    'success': False,
                    'error': 'Falha ao salvar foto(s) enviada(s).',
                },
                status=500,
            )

        msg = 'Fotos anexadas ao RDO.'
        if skipped_count > 0:
            msg = f'Fotos anexadas ao RDO. {skipped_count} arquivo(s) não foram anexados.'

        return JsonResponse(
            {
                'success': True,
                'saved': fotos_saved,
                'saved_count': len(fotos_saved),
                'skipped_count': skipped_count,
                'message': msg,
            }
        )
    except Exception:
        logger.exception('Erro em upload_rdo_photos')
        return JsonResponse({'success': False, 'error': 'Erro interno'}, status=500)

@login_required(login_url='/login/')
@require_POST
def update_rdo_tank_ajax(request, tank_id):
    logger = logging.getLogger(__name__)
    read_only_response = _guard_read_only_json(request, 'atualizar tanques do RDO')
    if read_only_response is not None:
        return read_only_response

    try:
        try:
            tank = RdoTanque.objects.select_related('rdo').get(pk=tank_id)
        except RdoTanque.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Tanque não encontrado.'}, status=404)

        # Para manter KPIs consistentes: se o código do tanque for alterado, replicar a alteração
        # para todos os snapshots (RdoTanque) que ainda estão com o mesmo código.
        old_code = None
        try:
            old_code = (tank.tanque_codigo or '').strip()
        except Exception:
            old_code = None

        try:
            is_supervisor_user = (hasattr(request, 'user') and request.user.is_authenticated and request.user.groups.filter(name='Supervisor').exists())
        except Exception:
            is_supervisor_user = False
        if is_supervisor_user:
            ordem = getattr(tank.rdo, 'ordem_servico', None)
            if getattr(ordem, 'supervisor', None) != request.user:
                return JsonResponse({'success': False, 'error': 'Sem permissão para atualizar este tanque.'}, status=403)

        from decimal import Decimal

        def _norm_num(val):
            try:
                if val is None:
                    return None
                s = str(val).strip()
                if s == '':
                    return None
                if s.endswith('%'):
                    s = s[:-1].strip()
                s = s.replace(',', '.')
                return s if s != '' else None
            except Exception:
                return None

        def _get_int(name):
            raw = request.POST.get(name)
            s = _norm_num(raw)
            if s is None:
                return None
            try:
                return int(float(s))
            except Exception:
                return None

        def _get_decimal(name, model_key=None):
            raw = request.POST.get(name)
            s = _norm_num(raw)
            if s is None:
                return None
            if model_key:
                return _coerce_decimal_for_model(RdoTanque, model_key, s)
            return _coerce_decimal_value(s)

        def _get_date(name):
            try:
                return _parse_iso_date_value(request.POST.get(name))
            except Exception:
                return None

        def _get_bool(name):
            v = request.POST.get(name)
            if v is None or v == '':
                return None
            s = str(v).strip().lower()
            if s in ('1', 'true', 't', 'yes', 'y', 'on', 'sim'):
                return True
            if s in ('0', 'false', 'f', 'no', 'n', 'off', 'nao', 'não'):
                return False
            return None

        def _parse_sentido():
            raw = None
            for k in ('sentido_limpeza', 'sentido', 'sent', 'sent_limpeza'):
                if k in request.POST and request.POST.get(k) not in (None, ''):
                    raw = request.POST.get(k)
                    break
            if raw is None:
                return None
            try:
                canon = _canonicalize_sentido(raw)
                return canon
            except Exception:
                return None

        attrs = {}
        mapping = {
            'tanque_codigo': 'tanque_codigo',
            'tanque_nome': 'nome_tanque',
            'nome_tanque': 'nome_tanque',
            'tipo_tanque': 'tipo_tanque',
            'numero_compartimento': 'numero_compartimentos',
            'numero_compartimentos': 'numero_compartimentos',
            'gavetas': 'gavetas',
            'patamar': 'patamares',
            'patamares': 'patamares',
            'volume_tanque_exec': 'volume_tanque_exec',
            'servico_exec': 'servico_exec',
            'metodo_exec': 'metodo_exec',
            'espaco_confinado': 'espaco_confinado',
            'operadores_simultaneos': 'operadores_simultaneos',
            'h2s_ppm': 'h2s_ppm',
            'lel': 'lel',
            'co_ppm': 'co_ppm',
            'o2_percent': 'o2_percent',
            'total_n_efetivo_confinado': 'total_n_efetivo_confinado',
            'tempo_bomba': 'tempo_bomba',
            'ensacamento_dia': 'ensacamento_dia',
            'icamento_dia': 'icamento_dia',
            'cambagem_dia': 'cambagem_dia',
            'previsao_termino': 'previsao_termino',
            'rdo_previsao_termino': 'previsao_termino',
            'ensacamento_prev': 'ensacamento_prev',
            'icamento_prev': 'icamento_prev',
            'cambagem_prev': 'cambagem_prev',
            'tambores_dia': 'tambores_dia',
            'tambores_acu': 'tambores_cumulativo',
            'tambores_cumulativo': 'tambores_cumulativo',
            'residuos_solidos': 'residuos_solidos',
            'residuos_totais': 'residuos_totais',
            'bombeio': 'bombeio',
            'total_liquido': 'total_liquido',
            'ensacamento_acu': 'ensacamento_cumulativo',
            'icamento_acu': 'icamento_cumulativo',
            'cambagem_acu': 'cambagem_cumulativo',
            'ensacamento_cumulativo': 'ensacamento_cumulativo',
            'icamento_cumulativo': 'icamento_cumulativo',
            'cambagem_cumulativo': 'cambagem_cumulativo',
            'total_liquido_acu': 'total_liquido_cumulativo',
            'total_liquido_cumulativo': 'total_liquido_cumulativo',
            'residuos_solidos_acu': 'residuos_solidos_cumulativo',
            'residuos_solidos_cumulativo': 'residuos_solidos_cumulativo',
            'avanco_limpeza': 'avanco_limpeza',
            'avanco_limpeza_fina': 'avanco_limpeza_fina',
            'percentual_limpeza_diario': 'percentual_limpeza_diario',
            'percentual_limpeza_cumulativo': 'percentual_limpeza_cumulativo',
            'percentual_limpeza_fina': 'percentual_limpeza_fina',
            'percentual_limpeza_fina_diario': 'percentual_limpeza_fina_diario',
            'percentual_limpeza_fina_cumulativo': 'percentual_limpeza_fina_cumulativo',
            'percentual_ensacamento': 'percentual_ensacamento',
            'percentual_icamento': 'percentual_icamento',
            'percentual_cambagem': 'percentual_cambagem',
            'percentual_avanco': 'percentual_avanco',
            'compartimentos_avanco_json': 'compartimentos_avanco_json',
            'sentido_limpeza': 'sentido_limpeza',
        }

        int_fields = set([
            'numero_compartimentos', 'gavetas', 'patamares', 'operadores_simultaneos', 'total_n_efetivo_confinado',
            'ensacamento_dia', 'icamento_dia', 'cambagem_dia', 'tambores_dia', 'total_liquido', 'ensacamento_prev', 'icamento_prev', 'cambagem_prev',
            'ensacamento_cumulativo', 'icamento_cumulativo', 'cambagem_cumulativo',
            'tambores_cumulativo',
            'total_liquido_cumulativo',
        ])
        decimal_fields = set([
            'volume_tanque_exec', 'h2s_ppm', 'lel', 'co_ppm', 'o2_percent', 'tempo_bomba', 'residuos_solidos', 'residuos_totais', 'bombeio',
            'percentual_limpeza_diario', 'percentual_limpeza_fina_diario', 'percentual_ensacamento', 'percentual_icamento', 'percentual_cambagem', 'percentual_avanco',
            'residuos_solidos_cumulativo',
        ])
        date_fields = set([
            'previsao_termino',
        ])

        post = request.POST
        for post_key, model_key in mapping.items():
            if post_key in post:
                val = post.get(post_key)
                if val is None or val == '':
                    continue
                if model_key in int_fields:
                    parsed = _get_int(post_key)
                    if parsed is not None:
                        attrs[model_key] = parsed
                elif model_key in decimal_fields:
                    parsed = _get_decimal(post_key, model_key=model_key)
                    if parsed is not None:
                        attrs[model_key] = parsed
                elif model_key in date_fields:
                    parsed = _get_date(post_key)
                    if parsed is not None:
                        attrs[model_key] = parsed
                else:
                    if model_key == 'sentido_limpeza':
                        canon = _parse_sentido()
                        if canon:
                            attrs['sentido_limpeza'] = canon
                        else:
                            attrs['sentido_limpeza'] = val
                    else:
                        attrs[model_key] = val

        try:
            def _normalize_prev_cumulativo(day_val, cum_val, legacy_total_val):
                if cum_val is not None:
                    return cum_val
                if legacy_total_val is None:
                    return None
                try:
                    return int(legacy_total_val)
                except Exception:
                    return legacy_total_val

            ens_day = attrs.get('ensacamento_dia')
            if ens_day is None:
                ens_day = _get_int('ensacamento_dia')
            ic_day = attrs.get('icamento_dia')
            if ic_day is None:
                ic_day = _get_int('icamento_dia')
            camb_day = attrs.get('cambagem_dia')
            if camb_day is None:
                camb_day = _get_int('cambagem_dia')

            ens_cum_direct = _get_int('ensacamento_cumulativo')
            ic_cum_direct = _get_int('icamento_cumulativo')
            camb_cum_direct = _get_int('cambagem_cumulativo')
            tamb_cum_direct = _get_int('tambores_cumulativo')
            ens_cum_legacy = _get_int('ensacamento_acu')
            ic_cum_legacy = _get_int('icamento_acu')
            camb_cum_legacy = _get_int('cambagem_acu')
            tamb_cum_legacy = _get_int('tambores_acu')
            tamb_day = attrs.get('tambores_dia')
            if tamb_day is None:
                tamb_day = _get_int('tambores_dia')

            normalized_ens = _normalize_prev_cumulativo(ens_day, ens_cum_direct, ens_cum_legacy)
            normalized_ic = _normalize_prev_cumulativo(ic_day, ic_cum_direct, ic_cum_legacy)
            normalized_camb = _normalize_prev_cumulativo(camb_day, camb_cum_direct, camb_cum_legacy)
            normalized_tamb = _normalize_prev_cumulativo(tamb_day, tamb_cum_direct, tamb_cum_legacy)
            if normalized_ens is not None:
                attrs['ensacamento_cumulativo'] = normalized_ens
            if normalized_ic is not None:
                attrs['icamento_cumulativo'] = normalized_ic
            if normalized_camb is not None:
                attrs['cambagem_cumulativo'] = normalized_camb
            if normalized_tamb is not None:
                attrs['tambores_cumulativo'] = normalized_tamb
        except Exception:
            pass

        try:
            _sanitize_model_decimal_payload(RdoTanque, attrs, logger=logger, context=f'update_rdo_tank_ajax tank_id={tank_id}')
        except Exception:
            pass

        incoming_predictions = {}
        for prediction_field in _TANK_PREDICTION_FIELDS:
            try:
                if prediction_field in attrs:
                    incoming_predictions[prediction_field] = attrs.pop(prediction_field)
            except Exception:
                continue

        # Validar e preparar replicação de mudança de código (se houver)
        new_code = None
        os_id = None
        try:
            if 'tanque_codigo' in attrs and attrs.get('tanque_codigo') is not None:
                new_code = str(attrs.get('tanque_codigo')).strip()
        except Exception:
            new_code = None
        try:
            os_id = getattr(tank.rdo, 'ordem_servico_id', None)
        except Exception:
            os_id = None

        replicate_code_change = bool(old_code and new_code and new_code != old_code)
        if replicate_code_change:
            try:
                conflicts = RdoTanque.objects.filter(tanque_codigo=new_code)
                # Se houver OS, limitar para evitar colisões entre operações diferentes
                if os_id:
                    conflicts = conflicts.filter(rdo__ordem_servico_id=os_id)
                if conflicts.exclude(pk=tank.id).exists():
                    return JsonResponse({'success': False, 'error': f'Já existe um tanque com o código {new_code} nesta OS.'}, status=400)
            except Exception:
                logger.exception('Falha ao validar conflito de tanque_codigo=%s', new_code)

        try:
            total_comp = attrs.get('numero_compartimentos') or getattr(tank, 'numero_compartimentos', None) or getattr(getattr(tank, 'rdo', None), 'numero_compartimentos', None)
            comp_validation = _validate_compartimentos_payload_for_tank(
                tank,
                request.POST.get,
                get_list=request.POST.getlist if hasattr(request.POST, 'getlist') else None,
                total_compartimentos=total_comp,
            )
        except Exception:
            comp_validation = None
        if comp_validation is not None and not comp_validation.get('is_valid'):
            return JsonResponse({
                'success': False,
                'error': (comp_validation.get('errors') or [{}])[0].get('message') or 'Avanço inválido para o compartimento.',
                'errors': comp_validation.get('errors') or [],
            }, status=400)

        incoming_shared_fields = {}
        for shared_field in _TANK_SHARED_STRUCTURE_FIELDS:
            try:
                if shared_field in attrs:
                    incoming_shared_fields[shared_field] = attrs.pop(shared_field)
            except Exception:
                continue

        locked_predictions = []
        try:
            for k, v in attrs.items():
                try:
                    setattr(tank, k, v)
                except Exception:
                    logger.exception('Falha ao atribuir %s=%s ao tanque %s', k, v, tank_id)
            if comp_validation is not None:
                try:
                    tank.compartimentos_avanco_json = comp_validation.get('json')
                    tank.compute_limpeza_from_compartimentos()
                except Exception:
                    logger.exception('Falha ao aplicar avanço por compartimento no tanque %s', tank_id)
            with transaction.atomic():
                tank.save()

                for field_name in _TANK_PREDICTION_FIELDS:
                    if field_name not in incoming_predictions:
                        continue
                    incoming_value = incoming_predictions.get(field_name)
                    try:
                        if _apply_tank_prediction_once(tank, field_name, incoming_value):
                            continue
                        if incoming_value is not None and _is_tank_prediction_locked(tank, field_name):
                            locked_predictions.append(field_name)
                    except Exception:
                        logger.exception(
                            'Falha ao sincronizar previsao %s=%s no tanque %s',
                            field_name,
                            incoming_value,
                            tank_id,
                        )
                for field_name in _TANK_SHARED_STRUCTURE_FIELDS:
                    if field_name not in incoming_shared_fields:
                        continue
                    incoming_value = incoming_shared_fields.get(field_name)
                    try:
                        _set_tank_shared_field_value(tank, field_name, incoming_value)
                    except Exception:
                        logger.exception(
                            'Falha ao sincronizar campo estrutural %s=%s no tanque %s',
                            field_name,
                            incoming_value,
                            tank_id,
                        )
                # Replicar mudança de código para todos os snapshots com o código antigo
                if replicate_code_change:
                    try:
                        qs = RdoTanque.objects.filter(tanque_codigo=old_code)
                        if os_id:
                            qs = qs.filter(rdo__ordem_servico_id=os_id)
                        qs = qs.exclude(pk=tank.id)
                        qs.update(tanque_codigo=new_code)
                    except Exception:
                        logger.exception('Falha ao replicar tanque_codigo %s -> %s (tank=%s)', old_code, new_code, tank_id)
        except Exception:
            logger.exception('Falha ao salvar tanque %s', tank_id)
            return JsonResponse({'success': False, 'error': 'Erro ao salvar tanque'}, status=500)

        try:
            if hasattr(tank, 'recompute_metrics') and callable(tank.recompute_metrics):
                try:
                    tank.recompute_metrics(only_when_missing=False)
                    with transaction.atomic():
                        tank.save()
                except Exception:
                    logger.exception('Falha ao recomputar métricas para tanque %s', tank_id)
        except Exception:
            pass

        effective_previsao = _get_tank_prediction_group_value(tank, 'previsao_termino')
        if not _has_defined_prediction_value(effective_previsao):
            effective_previsao = getattr(tank, 'previsao_termino', None)
        effective_ensac_prev = _get_tank_prediction_group_value(tank, 'ensacamento_prev')
        if not _has_defined_prediction_value(effective_ensac_prev):
            effective_ensac_prev = getattr(tank, 'ensacamento_prev', None)
        effective_icamento_prev = _get_tank_prediction_group_value(tank, 'icamento_prev')
        if not _has_defined_prediction_value(effective_icamento_prev):
            effective_icamento_prev = getattr(tank, 'icamento_prev', None)
        effective_cambagem_prev = _get_tank_prediction_group_value(tank, 'cambagem_prev')
        if not _has_defined_prediction_value(effective_cambagem_prev):
            effective_cambagem_prev = getattr(tank, 'cambagem_prev', None)
        payload = {
            'id': tank.id,
            'tanque_codigo': tank.tanque_codigo,
            'nome_tanque': tank.nome_tanque,
            'tipo_tanque': tank.tipo_tanque,
            'numero_compartimentos': tank.numero_compartimentos,
            'gavetas': tank.gavetas,
            'patamares': tank.patamares,
            'volume_tanque_exec': str(tank.volume_tanque_exec) if tank.volume_tanque_exec is not None else None,
            'servico_exec': tank.servico_exec,
            'metodo_exec': tank.metodo_exec,
            'ensacamento_dia': getattr(tank, 'ensacamento_dia', None),
            'icamento_dia': getattr(tank, 'icamento_dia', None),
            'cambagem_dia': getattr(tank, 'cambagem_dia', None),
            'tambores_dia': getattr(tank, 'tambores_dia', None),
            'tambores_cumulativo': getattr(tank, 'tambores_cumulativo', None),
            'tambores_acu': getattr(tank, 'tambores_cumulativo', None),
            'sentido_limpeza': getattr(tank, 'sentido_limpeza', None),
            'bombeio': getattr(tank, 'bombeio', None),
            'total_liquido': getattr(tank, 'total_liquido', None),
            'ensacamento_cumulativo': getattr(tank, 'ensacamento_cumulativo', None),
            'icamento_cumulativo': getattr(tank, 'icamento_cumulativo', None),
            'cambagem_cumulativo': getattr(tank, 'cambagem_cumulativo', None),
            'ensacamento_prev': effective_ensac_prev,
            'icamento_prev': effective_icamento_prev,
            'cambagem_prev': effective_cambagem_prev,
            'previsao_termino': (effective_previsao.isoformat() if hasattr(effective_previsao, 'isoformat') and effective_previsao else effective_previsao),
            'previsao_termino_locked': _is_tank_prediction_locked(tank, 'previsao_termino'),
            'total_liquido_acu': getattr(tank, 'total_liquido_cumulativo', None),
            'residuos_solidos_acu': getattr(tank, 'residuos_solidos_cumulativo', None),
            'locked_predictions': locked_predictions,
        }
        return JsonResponse({'success': True, 'message': 'Tanque atualizado', 'tank': payload})
    except Exception:
        logger.exception('Erro em update_rdo_tank_ajax')
        return JsonResponse({'success': False, 'error': 'Erro interno'}, status=500)

@login_required(login_url='/login/')
@require_POST
def delete_photo_basename_ajax(request):
    logger = logging.getLogger(__name__)
    read_only_response = _guard_read_only_json(request, 'remover fotos do RDO')
    if read_only_response is not None:
        return read_only_response

    try:
        rdo_id = request.POST.get('rdo_id') or request.POST.get('id')
        name = next((request.POST.get(k) for k in ('foto_basename','foto_name','basename','foto') if request.POST.get(k)), None)
        if not rdo_id or not name:
            return JsonResponse({'success': False, 'error': 'rdo_id ou foto_basename não informados.'}, status=400)

        try:
            rdo_obj = RDO.objects.get(pk=rdo_id)
        except RDO.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'RDO não encontrado.'}, status=404)

        basename = str(name).strip().split('/')[-1].split('?')[0]
        if not basename:
            return JsonResponse({'success': False, 'error': 'Nome da foto inválido.'}, status=400)

        removed = []

        def safe_delete(file_field, path_name):
            try:
                if file_field:
                    file_field.delete(save=False)
                elif path_name:
                    default_storage.delete(path_name)
            except Exception:
                logger.warning('Falha ao deletar arquivo: %s', path_name, exc_info=True)

        for i in range(1, 6):
            slot = f'fotos_{i}'
            field = getattr(rdo_obj, slot, None)
            fname = getattr(field, 'name', None)
            if fname and fname.endswith('/' + basename):
                safe_delete(field, fname)
                try: setattr(rdo_obj, slot, None)
                except Exception: pass
                removed.append({'slot': slot, 'name': fname})

        try:
            for rel in list(getattr(rdo_obj, 'fotos_rdo').all()):
                foto_field = getattr(rel, 'foto', None)
                foto_name = getattr(foto_field, 'name', None)
                if foto_name and foto_name.endswith('/' + basename):
                    safe_delete(foto_field, foto_name)
                    rel_id = getattr(rel, 'id', None)
                    try: rel.delete()
                    except Exception: logger.exception('Falha ao deletar RDOFoto id=%s', rel_id)
                    removed.append({'rdofoto_id': rel_id, 'name': foto_name})
        except Exception:
            pass

        try:
            single_field = getattr(rdo_obj, 'fotos', None)
            single_name = getattr(single_field, 'name', None)
            if single_name and single_name.endswith('/' + basename):
                safe_delete(single_field, single_name)
                try: rdo_obj.fotos = None
                except Exception: pass
                removed.append({'single': True, 'name': single_name})
        except Exception:
            pass

        try:
            cur = getattr(rdo_obj, 'fotos', None)
            if not hasattr(cur, 'url'):
                def _basename_from_entry(entry):
                    try:
                        if not entry: return ''
                        val = str(entry).strip()
                        if '?' in val: val = val.split('?',1)[0]
                        from urllib.parse import urlparse as _u
                        try:
                            p = _u(val)
                            path = p.path if (p.scheme and p.netloc) else val
                        except Exception:
                            path = val
                        return path.rsplit('/',1)[-1] if '/' in path else path
                    except Exception:
                        return ''
                lst = []
                if isinstance(cur, (list, tuple)):
                    lst = list(cur)
                elif isinstance(cur, str):
                    s = cur.strip()
                    if s.startswith('['):
                        try:
                            lst = json.loads(s)
                        except Exception:
                            lst = [ln for ln in s.splitlines() if ln.strip()]
                    elif s:
                        lst = [ln for ln in s.splitlines() if ln.strip()]
                if lst:
                    new_list = [it for it in lst if _basename_from_entry(it) != basename]
                    if len(new_list) != len(lst):
                        try:
                            if isinstance(cur, (list, tuple)):
                                setattr(rdo_obj, 'fotos', new_list)
                            else:
                                setattr(rdo_obj, 'fotos', json.dumps(new_list))
                        except Exception:
                            try:
                                setattr(rdo_obj, 'fotos', json.dumps(new_list))
                            except Exception:
                                pass
                        removed.append({'consolidated': True, 'removed_count': (len(lst)-len(new_list))})
        except Exception:
            pass

        if removed:
            try:
                _safe_save_global(rdo_obj)
            except Exception:
                logger.exception('Falha ao salvar RDO após remoção de foto')
            return JsonResponse({'success': True, 'removed': removed})
        return JsonResponse({'success': False, 'error': 'Foto não encontrada no RDO.'}, status=404)
    except Exception:
        logger.exception('Erro em delete_photo_basename_ajax')
        return JsonResponse({'success': False, 'error': 'Erro interno'}, status=500)

@login_required(login_url='/login/')
@require_POST
def merge_tanks_ajax(request):
    logger = logging.getLogger(__name__)
    read_only_response = _guard_read_only_json(request, 'juntar tanques')
    if read_only_response is not None:
        return read_only_response

    try:
        source_id = request.POST.get('source_tank_id') or request.POST.get('source')
        target_id = request.POST.get('target_tank_id') or request.POST.get('target')
        final_nome = (request.POST.get('final_tanque_nome') or request.POST.get('tanque_nome_final') or '').strip()
        final_codigo = (request.POST.get('final_tanque_codigo') or request.POST.get('tanque_codigo_final') or '').strip()

        if not source_id or not target_id:
            return JsonResponse({'success': False, 'error': 'source_tank_id e target_tank_id são obrigatórios.'}, status=400)
        try:
            source_id = int(source_id)
            target_id = int(target_id)
        except Exception:
            return JsonResponse({'success': False, 'error': 'ID de tanque inválido.'}, status=400)
        if source_id == target_id:
            return JsonResponse({'success': False, 'error': 'Selecione tanques diferentes para juntar.'}, status=400)

        def _is_blank(v):
            try:
                if v is None:
                    return True
                if isinstance(v, str):
                    return v.strip() == ''
                return False
            except Exception:
                return True

        def _to_decimal(v):
            try:
                if v is None or v == '':
                    return None
                if isinstance(v, Decimal):
                    return v
                return Decimal(str(v))
            except Exception:
                return None

        def _merge_compartimentos_json(dst_raw, src_raw):
            import json as _json

            def _parse(raw):
                if raw is None or raw == '':
                    return {}
                if isinstance(raw, dict):
                    return raw
                if isinstance(raw, str):
                    try:
                        v = _json.loads(raw)
                        return v if isinstance(v, dict) else {}
                    except Exception:
                        return {}
                return {}

            def _to_num(x):
                try:
                    if x is None or x == '':
                        return None
                    if isinstance(x, (int, float)):
                        return float(x)
                    s = str(x).strip().replace('%', '').replace(',', '.')
                    if s == '':
                        return None
                    return float(s)
                except Exception:
                    return None

            dst = _parse(dst_raw)
            src = _parse(src_raw)
            out = {}
            for k in set(list(dst.keys()) + list(src.keys())):
                dv = dst.get(k)
                sv = src.get(k)
                if not isinstance(dv, dict) and not isinstance(sv, dict):
                    out[k] = dv if dv is not None else sv
                    continue
                dv = dv if isinstance(dv, dict) else {}
                sv = sv if isinstance(sv, dict) else {}
                m = max([x for x in [_to_num(dv.get('mecanizada')), _to_num(sv.get('mecanizada'))] if x is not None], default=None)
                f = max([x for x in [_to_num(dv.get('fina')), _to_num(sv.get('fina'))] if x is not None], default=None)
                item = {}
                if m is not None:
                    item['mecanizada'] = round(float(m), 4)
                if f is not None:
                    item['fina'] = round(float(f), 4)
                out[k] = item
            return _json.dumps(out, ensure_ascii=False)

        from django.db import models as dj_models

        with transaction.atomic():
            # lock dentro da transação
            try:
                source = RdoTanque.objects.select_related('rdo__ordem_servico').select_for_update().get(pk=source_id)
            except RdoTanque.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Tanque origem não encontrado.'}, status=404)
            try:
                target = RdoTanque.objects.select_related('rdo__ordem_servico').select_for_update().get(pk=target_id)
            except RdoTanque.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Tanque destino não encontrado.'}, status=404)

            # Segurança: mesmo RDO (mesmo dia) e mesma OS
            try:
                if getattr(source, 'rdo_id', None) != getattr(target, 'rdo_id', None):
                    return JsonResponse({'success': False, 'error': 'Os tanques devem pertencer ao mesmo RDO.'}, status=400)
            except Exception:
                pass
            try:
                s_os = getattr(getattr(source, 'rdo', None), 'ordem_servico_id', None)
                t_os = getattr(getattr(target, 'rdo', None), 'ordem_servico_id', None)
                if s_os and t_os and int(s_os) != int(t_os):
                    return JsonResponse({'success': False, 'error': 'Os tanques devem pertencer à mesma OS.'}, status=400)
            except Exception:
                pass

            # aplica nome/código final escolhidos
            if final_nome:
                try:
                    target.nome_tanque = final_nome
                except Exception:
                    pass
            elif _is_blank(getattr(target, 'nome_tanque', None)):
                try:
                    target.nome_tanque = getattr(source, 'nome_tanque', None)
                except Exception:
                    pass

            if final_codigo:
                try:
                    target.tanque_codigo = final_codigo
                except Exception:
                    pass
            elif _is_blank(getattr(target, 'tanque_codigo', None)):
                try:
                    target.tanque_codigo = getattr(source, 'tanque_codigo', None)
                except Exception:
                    pass

            # merge dos campos KPI (RdoTanque)
            for f in target._meta.fields:
                fname = getattr(f, 'name', None)
                if not fname:
                    continue
                if fname in ('id', 'pk', 'rdo', 'created_at', 'updated_at'):
                    continue
                if fname in ('tanque_codigo', 'nome_tanque'):
                    continue

                dst_val = getattr(target, fname, None)
                src_val = getattr(source, fname, None)

                if fname == 'compartimentos_avanco_json':
                    try:
                        setattr(target, fname, _merge_compartimentos_json(dst_val, src_val))
                    except Exception:
                        pass
                    continue

                # numéricos: soma (Decimal/Float/Int)
                if isinstance(f, (dj_models.IntegerField, dj_models.FloatField, dj_models.DecimalField)):
                    if src_val is None or src_val == '':
                        continue
                    if dst_val is None or dst_val == '':
                        try:
                            setattr(target, fname, src_val)
                        except Exception:
                            pass
                        continue

                    try:
                        if isinstance(f, dj_models.DecimalField):
                            a = _to_decimal(dst_val)
                            b = _to_decimal(src_val)
                            if a is None:
                                setattr(target, fname, src_val)
                            elif b is None:
                                pass
                            else:
                                setattr(target, fname, a + b)
                        else:
                            setattr(target, fname, (dst_val or 0) + (src_val or 0))
                    except Exception:
                        pass
                    continue

                # texto: copia só se destino vazio
                if isinstance(f, (dj_models.CharField, dj_models.TextField)):
                    if _is_blank(dst_val) and not _is_blank(src_val):
                        try:
                            setattr(target, fname, src_val)
                        except Exception:
                            pass
                    continue

                # demais: se destino None, copia
                if dst_val is None and src_val is not None:
                    try:
                        setattr(target, fname, src_val)
                    except Exception:
                        pass

            # salva KPI consolidado antes de mover relações
            try:
                target.save()
            except Exception:
                logger.exception('Falha ao salvar tanque destino durante merge')
                raise

            # reatribui FKs de objetos relacionados (source -> target)
            for rel in list(source._meta.related_objects):
                try:
                    related_model = rel.related_model
                    fk_field_name = rel.field.name
                    related_model.objects.filter(**{fk_field_name: source}).update(**{fk_field_name: target})
                except Exception:
                    logger.exception('Falha ao reatribuir relação %s', getattr(rel, 'related_model', None))

            # move M2M (se houver)
            try:
                for m2m in source._meta.many_to_many:
                    try:
                        vals = list(getattr(source, m2m.name).all())
                        if vals:
                            getattr(target, m2m.name).add(*vals)
                            getattr(source, m2m.name).remove(*vals)
                    except Exception:
                        logger.exception('Falha ao mover m2m %s', m2m.name)
            except Exception:
                pass

            # remove o tanque origem
            source.delete()

            # Recalcula métricas após remoção (evita dupla contagem)
            try:
                if hasattr(target, 'recompute_metrics') and callable(target.recompute_metrics):
                    target.recompute_metrics(only_when_missing=False)
            except Exception:
                logger.exception('Falha ao recomputar métricas após merge')
            try:
                target.save()
            except Exception:
                logger.exception('Falha ao salvar tanque destino após recompute')
                raise

        return JsonResponse({'success': True, 'ok': True, 'merged_into': target_id, 'merged_from': source_id})
    except Exception:
        logger.exception('merge_tanks_ajax error')
        return JsonResponse({'success': False, 'error': 'Erro interno'}, status=500)


@login_required(login_url='/login/')
@require_POST
def delete_tank_ajax(request):
    logger = logging.getLogger(__name__)
    read_only_response = _guard_read_only_json(request, 'excluir tanques')
    if read_only_response is not None:
        return read_only_response

    try:
        tank_id = request.POST.get('tank_id') or request.POST.get('tanque_id')
        os_id = request.POST.get('os_id') or request.POST.get('ordem_servico_id')
        rdo_id = request.POST.get('rdo_id')
        scope = (request.POST.get('scope') or request.POST.get('delete_scope') or 'rdo').strip().lower()

        if not tank_id:
            return JsonResponse({'success': False, 'error': 'tank_id é obrigatório.'}, status=400)
        try:
            tank_id = int(tank_id)
        except Exception:
            return JsonResponse({'success': False, 'error': 'ID de tanque inválido.'}, status=400)

        if scope not in ('rdo', 'os'):
            return JsonResponse({'success': False, 'error': 'Escopo inválido. Use scope=rdo ou scope=os.'}, status=400)
        try:
            if os_id is not None and str(os_id).strip() != '':
                os_id = int(os_id)
            else:
                os_id = None
        except Exception:
            os_id = None
        try:
            if rdo_id is not None and str(rdo_id).strip() != '':
                rdo_id = int(rdo_id)
            else:
                rdo_id = None
        except Exception:
            rdo_id = None

        from django.db.models.deletion import ProtectedError

        with transaction.atomic():
            try:
                tank = RdoTanque.objects.select_related('rdo__ordem_servico').select_for_update().get(pk=tank_id)
            except RdoTanque.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Tanque não encontrado.'}, status=404)

            # validações de contexto (quando fornecidas)
            try:
                if rdo_id is not None and getattr(tank, 'rdo_id', None) and int(tank.rdo_id) != int(rdo_id):
                    return JsonResponse({'success': False, 'error': 'Tanque não pertence ao RDO atual.'}, status=400)
            except Exception:
                pass
            try:
                tank_os_id = getattr(getattr(tank, 'rdo', None), 'ordem_servico_id', None)
                if os_id is not None and tank_os_id is not None and int(tank_os_id) != int(os_id):
                    return JsonResponse({'success': False, 'error': 'Tanque não pertence à OS atual.'}, status=400)
            except Exception:
                pass

            # Derivar OS do próprio tanque (quando não veio no request)
            try:
                tank_os_id = getattr(getattr(tank, 'rdo', None), 'ordem_servico_id', None)
                if tank_os_id is None and os_id is not None:
                    tank_os_id = os_id
            except Exception:
                tank_os_id = os_id

            deleted_count = 0
            deleted_ids = []

            if scope == 'rdo':
                try:
                    tank.delete()
                    deleted_count = 1
                    deleted_ids = [tank_id]
                except ProtectedError:
                    return JsonResponse({
                        'success': False,
                        'error': 'Não foi possível excluir este tanque porque existem registros relacionados. Use “Juntar Tanques” para consolidar e remover o duplicado.'
                    }, status=409)
            else:
                # scope == 'os': remover o tanque em todos os RDOs da mesma OS
                if tank_os_id is None:
                    return JsonResponse({'success': False, 'error': 'Não foi possível determinar a OS do tanque.'}, status=400)

                try:
                    codigo = (getattr(tank, 'tanque_codigo', None) or '').strip()
                except Exception:
                    codigo = ''
                try:
                    nome = (getattr(tank, 'nome_tanque', None) or '').strip()
                except Exception:
                    nome = ''

                qs = RdoTanque.objects.select_related('rdo').select_for_update().filter(rdo__ordem_servico_id=tank_os_id)
                if codigo:
                    qs = qs.filter(tanque_codigo__iexact=codigo)
                elif nome:
                    qs = qs.filter(nome_tanque__iexact=nome)
                else:
                    qs = qs.filter(pk=tank_id)

                try:
                    deleted_ids = list(qs.values_list('id', flat=True))
                except Exception:
                    deleted_ids = []

                try:
                    # deletar um a um para dar erro amigável caso exista proteção
                    for obj in qs.iterator():
                        obj.delete()
                        deleted_count += 1
                except ProtectedError:
                    return JsonResponse({
                        'success': False,
                        'error': 'Não foi possível excluir todos os registros deste tanque na OS porque existem registros relacionados. Considere usar “Juntar Tanques” antes, ou remova as relações vinculadas.'
                    }, status=409)

        return JsonResponse({'success': True, 'ok': True, 'scope': scope, 'deleted_count': deleted_count, 'deleted_ids': deleted_ids, 'deleted_id': tank_id})
    except Exception:
        logger.exception('delete_tank_ajax error')
        return JsonResponse({'success': False, 'error': 'Erro interno'}, status=500)

@login_required(login_url='/login/')
def rdo(request):
    is_supervisor_user = (hasattr(request, 'user') and request.user.is_authenticated and request.user.groups.filter(name='Supervisor').exists())
    supervisor_current_os_numero = None
    mobile_release_context = resolve_mobile_release_context(request)
    show_mobile_app_notice = (
        is_supervisor_user
        and request_is_mobile(request)
        and bool(mobile_release_context.get('mobile_app_android_url'))
    )

    base_qs = RDO.objects.select_related('ordem_servico').all()
    if is_supervisor_user:
        try:
            # Supervisor sempre vê somente seus RDOs.
            base_qs = base_qs.filter(ordem_servico__supervisor=request.user)

            latest_active_rdo_os_numero = None
            try:
                for rdo_obj in base_qs.order_by('-id').iterator():
                    os_obj = getattr(rdo_obj, 'ordem_servico', None)
                    if not _os_matches_rdo_pending_rule(os_obj):
                        continue
                    latest_active_rdo_os_numero = getattr(os_obj, 'numero_os', None)
                    if latest_active_rdo_os_numero not in (None, ''):
                        break
            except Exception:
                latest_active_rdo_os_numero = None

            latest_active_home_os_numero = None
            try:
                home_qs = (
                    OrdemServico.objects
                    .filter(supervisor=request.user)
                    .order_by('-id')
                )
                for os_obj in home_qs.iterator():
                    if not _os_matches_rdo_pending_rule(os_obj):
                        continue
                    latest_active_home_os_numero = getattr(os_obj, 'numero_os', None)
                    if latest_active_home_os_numero not in (None, ''):
                        break
            except Exception:
                latest_active_home_os_numero = None

            # Exibir somente a OS mais recente permitida pela regra da Home/RDO.
            supervisor_current_os_numero = (
                latest_active_home_os_numero
                or latest_active_rdo_os_numero
            )
            if supervisor_current_os_numero is not None:
                try:
                    supervisor_current_os_numero = int(supervisor_current_os_numero)
                except Exception:
                    pass
                base_qs = base_qs.filter(ordem_servico__numero_os=supervisor_current_os_numero)
            else:
                base_qs = base_qs.none()
        except Exception:
            supervisor_current_os_numero = None
            base_qs = base_qs.none()

    try:
        def _g(name):
            v = request.GET.get(name)
            if v is None:
                return None
            s = str(v).strip()
            return s if s != '' else None

        contrato = _g('contrato')
        os_q = _g('os')
        empresa = _g('empresa')
        unidade = _g('unidade')
        turno = _g('turno')
        servico = _g('servico')
        metodo = _g('metodo')
        date_start = _g('date_start')
        date_end = _g('date_end')
        tanque = _g('tanque')
        supervisor = _g('supervisor')
        rdo = _g('rdo')
        status_geral = _g('status_geral')
        status_operacao = _g('status_operacao')

        q_filters = Q()
        active_filters = 0

        if contrato:
            active_filters += 1
            q_filters &= (Q(contrato_po__icontains=contrato) | Q(po__icontains=contrato))
        if os_q:
            active_filters += 1
            q_filters &= Q(ordem_servico__numero_os__icontains=os_q)
        if empresa:
            active_filters += 1
            q_filters &= Q(ordem_servico__Cliente__nome__icontains=empresa)
        if unidade:
            active_filters += 1
            q_filters &= Q(ordem_servico__Unidade__nome__icontains=unidade)
        if turno:
            active_filters += 1
            q_filters &= Q(turno__icontains=turno)
        if servico:
            active_filters += 1
            q_filters &= (Q(servico_exec__icontains=servico) | Q(tanques__servico_exec__icontains=servico) | Q(ordem_servico__servico__icontains=servico))
        if metodo:
            active_filters += 1
            q_filters &= (Q(metodo_exec__icontains=metodo) | Q(tanques__metodo_exec__icontains=metodo) | Q(ordem_servico__metodo__icontains=metodo))
        if tanque:
            active_filters += 1
            q_filters &= (Q(nome_tanque__icontains=tanque) | Q(tanques__nome_tanque__icontains=tanque) | Q(tanque_codigo__icontains=tanque) | Q(tanques__tanque_codigo__icontains=tanque))
        if supervisor:
            active_filters += 1
            def _supervisor_search_q(val):
                import unicodedata
                def _strip_accents(s):
                    if not s:
                        return s
                    try:
                        nkfd = unicodedata.normalize('NFKD', s)
                        return ''.join([c for c in nkfd if not unicodedata.combining(c)])
                    except Exception:
                        return s

                raw = (val or '').strip()
                if not raw:
                    return Q()

                raw_noaccent = _strip_accents(raw).lower()
                parts = [p for p in raw_noaccent.split() if p]

                q = Q(ordem_servico__supervisor__username__icontains=raw) | Q(ordem_servico__supervisor__first_name__icontains=raw) | Q(ordem_servico__supervisor__last_name__icontains=raw)
                q |= Q(ordem_servico__supervisor__username__icontains=raw_noaccent) | Q(ordem_servico__supervisor__first_name__icontains=raw_noaccent) | Q(ordem_servico__supervisor__last_name__icontains=raw_noaccent)

                if len(parts) >= 2:
                    first = parts[0]
                    last = parts[-1]
                    q |= (Q(ordem_servico__supervisor__first_name__icontains=first) & Q(ordem_servico__supervisor__last_name__icontains=last))
                    q |= (Q(ordem_servico__supervisor__first_name__icontains=last) & Q(ordem_servico__supervisor__last_name__icontains=first))

                    try:
                        uname_dot = '.'.join(parts)
                        uname_nospace = ''.join(parts)
                        q |= Q(ordem_servico__supervisor__username__icontains=uname_dot) | Q(ordem_servico__supervisor__username__icontains=uname_nospace)
                    except Exception:
                        pass
                else:
                    try:
                        p = parts[0] if parts else ''
                        if p:
                            q |= Q(ordem_servico__supervisor__username__icontains=p)
                    except Exception:
                        pass

                return q

            try:
                q_filters &= _supervisor_search_q(supervisor)
            except Exception:
                q_filters &= (Q(ordem_servico__supervisor__username__icontains=supervisor) | Q(ordem_servico__supervisor__first_name__icontains=supervisor) | Q(ordem_servico__supervisor__last_name__icontains=supervisor))
        if rdo:
            try:
                active_filters += 1
                q_filters &= (Q(rdo__icontains=rdo) | Q(rdo__iexact=rdo))
            except Exception:
                pass
        if status_geral:
            active_filters += 1
            q_filters &= Q(ordem_servico__status_geral__icontains=status_geral)
        if status_operacao:
            active_filters += 1
            q_filters &= Q(ordem_servico__status_operacao__icontains=status_operacao)
        def _parse_date_flexible(s):
            if not s:
                return None
            s = str(s).strip()
            if not s:
                return None
            from datetime import datetime
            try:
                return datetime.fromisoformat(s).date()
            except Exception:
                pass
            try:
                return datetime.strptime(s, '%d/%m/%Y').date()
            except Exception:
                pass
            try:
                return datetime.strptime(s, '%Y-%m-%d').date()
            except Exception:
                return None

        try:
            d = _parse_date_flexible(date_start) if date_start else None
            d2 = _parse_date_flexible(date_end) if date_end else None
            if d:
                active_filters += 1
            if d2:
                active_filters += 1

            if d or d2:
                try:
                    from django.db.models.functions import Coalesce
                    eff_qs = base_qs.annotate(_eff_date=Coalesce('data_inicio', 'data'))
                    if d and d2:
                        try:
                            if d > d2:
                                d, d2 = d2, d
                        except Exception:
                            pass
                        eff_qs = eff_qs.filter(_eff_date__gte=d, _eff_date__lte=d2)
                    else:
                        if d:
                            eff_qs = eff_qs.filter(_eff_date__gte=d)
                        if d2:
                            eff_qs = eff_qs.filter(_eff_date__lte=d2)
                    date_filtered_qs = eff_qs
                except Exception:
                    date_filtered_qs = None
            else:
                date_filtered_qs = None
        except Exception:
            pass

        try:
            try:
                import logging
                logger = logging.getLogger(__name__)
                do_log = (getattr(settings, 'DEBUG', False) or (hasattr(request, 'user') and getattr(request.user, 'is_staff', False)))
            except Exception:
                logger = None
                do_log = False
            if do_log and logger:
                try:
                    before_count = base_qs.count()
                except Exception:
                    before_count = None
            if 'date_filtered_qs' in locals() and date_filtered_qs is not None:
                try:
                    filtered_qs = date_filtered_qs.filter(q_filters).distinct()
                except Exception:
                    filtered_qs = date_filtered_qs.distinct()
            else:
                try:
                    filtered_qs = base_qs.filter(q_filters).distinct()
                except Exception:
                    filtered_qs = base_qs.distinct()
            if do_log and logger:
                try:
                    after_count = filtered_qs.count()
                except Exception:
                    after_count = None
                try:
                    logger.debug('RDO filters: date_start=%r date_end=%r parsed_start=%r parsed_end=%r before_count=%r after_count=%r SQL=%s',
                                 date_start, date_end, (locals().get('d') if 'd' in locals() else None), (locals().get('d2') if 'd2' in locals() else None),
                                 before_count, after_count, getattr(filtered_qs, 'query', None))
                except Exception:
                    try:
                        logger.debug('RDO filters applied (counts): before=%r after=%r', before_count, after_count)
                    except Exception:
                        pass
            base_qs = filtered_qs
        except Exception:
            pass
    except Exception:
        active_filters = 0

    try:
        request._rdo_active_filters = int(active_filters)
    except Exception:
        request._rdo_active_filters = 0

    # Garantir que o RDO mais recente fique sempre no topo da lista
    rdos = base_qs.order_by('-id')
    _os_tank_limit_cache = {}

    def _attach_os_tank_limit(os_obj):
        try:
            if os_obj is None:
                return 0
            oid = getattr(os_obj, 'id', None)
            if oid in _os_tank_limit_cache:
                cached = _os_tank_limit_cache.get(oid, (0, 0))
                if isinstance(cached, (tuple, list)) and len(cached) >= 2:
                    try:
                        limit_val = int(cached[0] or 0)
                    except Exception:
                        limit_val = 0
                    try:
                        current_os_tanks = int(cached[1] or 0)
                    except Exception:
                        current_os_tanks = 0
                else:
                    try:
                        limit_val = int(cached or 0)
                    except Exception:
                        limit_val = 0
                    current_os_tanks = 0
            else:
                limit_val, _labels = _resolve_os_service_limit(os_obj)
                try:
                    limit_val = int(limit_val or 0)
                except Exception:
                    limit_val = 0
                try:
                    current_os_tanks, _tank_keys = _resolve_os_tank_progress(os_obj)
                    current_os_tanks = int(current_os_tanks or 0)
                except Exception:
                    current_os_tanks = 0
                _os_tank_limit_cache[oid] = (limit_val, current_os_tanks)
            try:
                setattr(os_obj, 'max_tanques_servicos', limit_val)
                setattr(os_obj, 'total_tanques_os', current_os_tanks)
            except Exception:
                pass
            return limit_val
        except Exception:
            return 0

    page = request.GET.get('page', 1)
    if is_supervisor_user:
        unique = []
        current_os_obj = None
        try:
            if supervisor_current_os_numero not in (None, ''):
                current_os_obj = _resolve_latest_os_for_numero(
                    supervisor_current_os_numero,
                    supervisor=request.user
                )
        except Exception:
            current_os_obj = None

        if current_os_obj is not None and _os_matches_rdo_pending_rule(current_os_obj):
            try:
                _attach_os_tank_limit(current_os_obj)
            except Exception:
                pass
            try:
                synthetic_row = _build_supervisor_card_row(current_os_obj)
            except Exception:
                synthetic_row = None
            if synthetic_row is not None:
                unique.append(synthetic_row)
        else:
            seen = set()
            for r in rdos:
                try:
                    os_obj = getattr(r, 'ordem_servico', None)
                    if os_obj is not None:
                        latest_os_obj = _resolve_latest_os_for_numero(
                            getattr(os_obj, 'numero_os', None),
                            supervisor=request.user
                        )
                        if latest_os_obj is not None:
                            os_obj = latest_os_obj
                    try:
                        _attach_os_tank_limit(os_obj)
                    except Exception:
                        pass
                except Exception:
                    os_obj = getattr(r, 'ordem_servico', None)
                if not _os_matches_rdo_pending_rule(os_obj):
                    continue
                key = _os_pending_dedupe_key(os_obj, fallback=getattr(r, 'id', None))
                if key is None:
                    key = ('no-os', getattr(r, 'id', None))
                if key in seen:
                    continue
                seen.add(key)
                synthetic_row = _build_supervisor_card_row(os_obj)
                if synthetic_row is not None:
                    unique.append(synthetic_row)
        try:
            per_page = int(request.GET.get('per_page') or request.GET.get('perpage') or 6)
        except Exception:
            per_page = 6
        try:
            if per_page <= 0 or per_page > 500:
                per_page = 6
        except Exception:
            per_page = 6

        paginator = Paginator(unique, per_page)
        try:
            servicos = paginator.page(1)
        except Exception:
            servicos = paginator.page(1)
    else:
        try:
            from types import SimpleNamespace
        except Exception:
            SimpleNamespace = None

        flat_rows = []
        for r in rdos:
            try:
                try:
                    _attach_os_tank_limit(getattr(r, 'ordem_servico', None))
                except Exception:
                    pass
                tanks = []
                try:
                    manager = getattr(r, 'tanques', None) or getattr(r, 'rdotanque_set', None)
                    if manager is not None:
                        tanks = list(manager.all())
                    else:
                        tanks = []
                except Exception:
                    tanks = []

                if tanks:
                    for t in tanks:
                        try:
                            row = SimpleNamespace() if SimpleNamespace else type('Row', (), {})()
                            row.id = r.id
                            row.rdo = getattr(r, 'rdo', None)
                            row.data = getattr(r, 'data', None)
                            row.data_inicio = getattr(r, 'data_inicio', None) or getattr(r, 'data', None)
                            row.previsao_termino = getattr(r, 'previsao_termino', None)
                            row.ordem_servico = getattr(r, 'ordem_servico', None)
                            row.contrato_po = getattr(r, 'contrato_po', None)
                            row.turno = getattr(r, 'turno', None)
                            row.tanque_codigo = getattr(t, 'tanque_codigo', None)
                            row.nome_tanque = getattr(t, 'nome_tanque', None)
                            row.tipo_tanque = getattr(t, 'tipo_tanque', None)
                            row.numero_compartimentos = getattr(t, 'numero_compartimentos', getattr(t, 'numero_compartimento', None))
                            row.gavetas = getattr(t, 'gavetas', None)
                            row.patamares = getattr(t, 'patamares', getattr(t, 'patamar', None))
                            row.volume_tanque_exec = getattr(t, 'volume_tanque_exec', None)
                            row.servico_exec = getattr(t, 'servico_exec', None)
                            row.metodo_exec = getattr(t, 'metodo_exec', None)
                            row.operadores_simultaneos = getattr(t, 'operadores_simultaneos', None)
                            row.h2s_ppm = getattr(t, 'h2s_ppm', None)
                            row.lel = getattr(t, 'lel', None)
                            row.co_ppm = getattr(t, 'co_ppm', None)
                            row.o2_percent = getattr(t, 'o2_percent', None)
                            row.tambores = getattr(t, 'tambores_dia', None)
                            row.total_solidos = getattr(t, 'residuos_solidos', None)
                            row.total_residuos = getattr(t, 'residuos_totais', None)
                            flat_rows.append(row)
                        except Exception:
                            pass
                else:
                    row = SimpleNamespace() if SimpleNamespace else type('Row', (), {})()
                    row.id = r.id
                    row.rdo = getattr(r, 'rdo', None)
                    row.data = getattr(r, 'data', None)
                    row.data_inicio = getattr(r, 'data_inicio', None) or getattr(r, 'data', None)
                    row.previsao_termino = getattr(r, 'previsao_termino', None)
                    row.ordem_servico = getattr(r, 'ordem_servico', None)
                    row.contrato_po = getattr(r, 'contrato_po', None)
                    row.turno = getattr(r, 'turno', None)
                    row.tanque_codigo = getattr(r, 'tanque_codigo', None)
                    row.nome_tanque = getattr(r, 'nome_tanque', None)
                    row.tipo_tanque = getattr(r, 'tipo_tanque', None)
                    row.numero_compartimentos = getattr(r, 'numero_compartimentos', None)
                    row.gavetas = getattr(r, 'gavetas', None)
                    row.patamares = getattr(r, 'patamares', None)
                    row.volume_tanque_exec = getattr(r, 'volume_tanque_exec', None)
                    row.servico_exec = getattr(r, 'servico_exec', None)
                    row.metodo_exec = getattr(r, 'metodo_exec', None)
                    row.operadores_simultaneos = getattr(r, 'operadores_simultaneos', None)
                    row.h2s_ppm = getattr(r, 'h2s_ppm', None)
                    row.lel = getattr(r, 'lel', None)
                    row.co_ppm = getattr(r, 'co_ppm', None)
                    row.o2_percent = getattr(r, 'o2_percent', None)
                    row.tambores = getattr(r, 'tambores', None)
                    row.total_solidos = getattr(r, 'total_solidos', None)
                    row.total_residuos = getattr(r, 'total_residuos', None)
                    flat_rows.append(row)
            except Exception:
                row = SimpleNamespace() if SimpleNamespace else type('Row', (), {})()
                row.id = getattr(r, 'id', None)
                row.rdo = getattr(r, 'rdo', None)
                row.data = getattr(r, 'data', None)
                row.data_inicio = getattr(r, 'data_inicio', None) or getattr(r, 'data', None)
                row.previsao_termino = getattr(r, 'previsao_termino', None)
                row.ordem_servico = getattr(r, 'ordem_servico', None)
                row.contrato_po = getattr(r, 'contrato_po', None)
                row.turno = getattr(r, 'turno', None)
                row.tanque_codigo = getattr(r, 'tanque_codigo', None)
                row.nome_tanque = getattr(r, 'nome_tanque', None)
                row.tipo_tanque = getattr(r, 'tipo_tanque', None)
                row.numero_compartimentos = getattr(r, 'numero_compartimentos', None)
                row.gavetas = getattr(r, 'gavetas', None)
                row.patamares = getattr(r, 'patamares', None)
                row.volume_tanque_exec = getattr(r, 'volume_tanque_exec', None)
                row.servico_exec = getattr(r, 'servico_exec', None)
                row.metodo_exec = getattr(r, 'metodo_exec', None)
                row.operadores_simultaneos = getattr(r, 'operadores_simultaneos', None)
                row.h2s_ppm = getattr(r, 'h2s_ppm', None)
                row.lel = getattr(r, 'lel', None)
                row.co_ppm = getattr(r, 'co_ppm', None)
                row.o2_percent = getattr(r, 'o2_percent', None)
                row.tambores = getattr(r, 'tambores', None)
                row.total_solidos = getattr(r, 'total_solidos', None)
                row.total_residuos = getattr(r, 'total_residuos', None)
                flat_rows.append(row)
        try:
            per_page = int(request.GET.get('per_page') or request.GET.get('perpage') or 6)
        except Exception:
            per_page = 6
        try:
            if per_page <= 0 or per_page > 500:
                per_page = 6
        except Exception:
            per_page = 6

        paginator = Paginator(flat_rows, per_page)
        try:
            servicos = paginator.page(page)
        except PageNotAnInteger:
            servicos = paginator.page(1)
        except EmptyPage:
            servicos = paginator.page(paginator.num_pages)
    servico_choices = OrdemServico.SERVICO_CHOICES
    status_choices = OrdemServico.STATUS_CHOICES
    metodo_choices = [
        ('Manual', 'Manual'),
        ('Mecanizada', 'Mecanizada'),
        ('Robotizada', 'Robotizada'),
    ]
    try:
        get_pessoas = Pessoa.objects.order_by('nome').all()
    except Exception:
        get_pessoas = []
    try:
        from types import SimpleNamespace
        db_funcoes_qs = Funcao.objects.order_by('nome').all()
        db_funcoes_names = [f.nome for f in db_funcoes_qs]
        const_funcoes = [t[0] for t in getattr(OrdemServico, 'FUNCOES', [])]
        const_only = [SimpleNamespace(nome=name) for name in const_funcoes if name not in db_funcoes_names]
        db_funcoes_objs = [SimpleNamespace(nome=f.nome) for f in db_funcoes_qs]
        get_funcoes = const_only + db_funcoes_objs
    except Exception:
        get_funcoes = []
    try:
        def _canonical_login_from_name(name):
            if not name:
                return ''
            s = unicodedata.normalize('NFKD', str(name))
            s = ''.join([c for c in s if not unicodedata.combining(c)])
            s = s.lower()
            import re
            s = re.sub(r'[^a-z0-9]+', '.', s)
            s = re.sub(r'\.+', '.', s)
            s = s.strip('.')
            return s

        pessoas_map = {}
        try:
            for p in (get_pessoas or []):
                nome = getattr(p, 'nome', None) or ''
                key = _canonical_login_from_name(nome)
                if key:
                    pessoas_map[key] = nome
        except Exception:
            pessoas_map = {}
        try:
            for r in rdos:
                ordem_obj = getattr(r, 'ordem_servico', None)
                sup = getattr(ordem_obj, 'supervisor', None) if ordem_obj else None
                if sup is None:
                    continue
                try:
                    uname = getattr(sup, 'username', None)
                    full = sup.get_full_name() if hasattr(sup, 'get_full_name') else str(sup)
                except Exception:
                    uname = None
                    full = str(sup)
                if uname:
                    pessoas_map.setdefault(str(uname).lower(), full or uname)
        except Exception:
            pass

        import json as _json
        pessoas_map_json = _json.dumps(pessoas_map)
    except Exception:
        pessoas_map_json = '{}'

    try:
        obj_list = list(getattr(servicos, 'object_list', [])) if servicos is not None else []
        count_on_page = len(obj_list)
    except Exception:
        count_on_page = 0
    try:
        if servicos is not None and hasattr(servicos, 'start_index') and callable(servicos.start_index):
            start_idx = servicos.start_index()
        else:
            start_idx = 1 if count_on_page > 0 else 0
    except Exception:
        start_idx = 1 if count_on_page > 0 else 0

    if count_on_page <= 0:
        page_start = 0
        page_end = 0
    else:
        page_start = start_idx
        page_end = start_idx + count_on_page - 1

    context = {
        'rdos': rdos,
        'servicos': servicos,
        'supervisor_current_os_numero': supervisor_current_os_numero,
        'can_delete_rdo': _user_can_delete_rdo(getattr(request, 'user', None)),
        'active_filters_count': getattr(request, '_rdo_active_filters', 0),
        'no_results': (getattr(paginator, 'count', 0) == 0),
        'show_pagination': (hasattr(paginator, 'num_pages') and getattr(paginator, 'num_pages', 0) > 1),
        'servico_choices': servico_choices,
        'metodo_choices': metodo_choices,
        'status_choices': status_choices,
        'atividades_choices': getattr(RDO, 'ATIVIDADES_CHOICES', []),
        'activity_slots': list(range(9)),
        'force_mobile': True if request.GET.get('mobile') == '1' else False,
        'is_supervisor': is_supervisor_user,
        'per_page_current': int(request.GET.get('per_page') or request.GET.get('perpage') or 6),
        'get_pessoas': get_pessoas,
        'total_count': getattr(paginator, 'count', 0),
        'page_start': page_start,
        'page_end': page_end,
        'get_funcoes': get_funcoes,
        'pessoas_map_json': pessoas_map_json,
        'show_mobile_app_notice': show_mobile_app_notice,
    }
    context.update(mobile_release_context)
    return render(request, 'rdo.html', context)


@login_required(login_url='/login/')
@require_GET
def exportar_rdo_excel(request):
    try:
        import pandas as pd
    except Exception:
        return HttpResponse('Dependência ausente: instale pandas para exportar Excel.', status=500)

    def _g(name):
        v = request.GET.get(name)
        if v is None:
            return None
        s = str(v).strip()
        return s if s != '' else None

    def _fmt_date(v):
        try:
            if v is None:
                return ''
            return v.isoformat() if hasattr(v, 'isoformat') else str(v)
        except Exception:
            return ''

    def _fmt_time(v):
        try:
            if v is None:
                return ''
            if isinstance(v, dt_time):
                return v.strftime('%H:%M')
            if isinstance(v, datetime):
                return v.strftime('%H:%M')
            s = str(v).strip()
            return s
        except Exception:
            return ''

    def _fmt_supervisor(user_obj):
        try:
            if not user_obj:
                return ''
            full = user_obj.get_full_name() if hasattr(user_obj, 'get_full_name') else ''
            if full:
                return full
            return getattr(user_obj, 'username', '') or str(user_obj)
        except Exception:
            return ''

    def _parse_date_flexible(s):
        if not s:
            return None
        s = str(s).strip()
        if not s:
            return None
        try:
            return datetime.fromisoformat(s).date()
        except Exception:
            pass
        try:
            return datetime.strptime(s, '%d/%m/%Y').date()
        except Exception:
            pass
        try:
            return datetime.strptime(s, '%Y-%m-%d').date()
        except Exception:
            return None

    try:
        is_supervisor_user = (
            hasattr(request, 'user')
            and request.user.is_authenticated
            and request.user.groups.filter(name='Supervisor').exists()
        )
    except Exception:
        is_supervisor_user = False

    base_qs = (
        RDO.objects
        .select_related('ordem_servico', 'ordem_servico__Cliente', 'ordem_servico__Unidade', 'ordem_servico__supervisor')
        .prefetch_related('tanques', 'atividades_rdo', 'membros_equipe')
        .all()
    )

    if is_supervisor_user:
        base_qs = base_qs.filter(ordem_servico__supervisor=request.user)

    contrato = _g('contrato')
    os_q = _g('os')
    empresa = _g('empresa')
    unidade = _g('unidade')
    turno = _g('turno')
    servico = _g('servico')
    metodo = _g('metodo')
    date_start = _g('date_start')
    date_end = _g('date_end')
    tanque = _g('tanque')
    supervisor = _g('supervisor')
    rdo_num = _g('rdo')
    status_geral = _g('status_geral')
    status_operacao = _g('status_operacao')

    q_filters = Q()

    if contrato:
        q_filters &= (Q(contrato_po__icontains=contrato) | Q(po__icontains=contrato))
    if os_q:
        q_filters &= Q(ordem_servico__numero_os__icontains=os_q)
    if empresa:
        q_filters &= Q(ordem_servico__Cliente__nome__icontains=empresa)
    if unidade:
        q_filters &= Q(ordem_servico__Unidade__nome__icontains=unidade)
    if turno:
        q_filters &= Q(turno__icontains=turno)
    if servico:
        q_filters &= (Q(servico_exec__icontains=servico) | Q(tanques__servico_exec__icontains=servico) | Q(ordem_servico__servico__icontains=servico))
    if metodo:
        q_filters &= (Q(metodo_exec__icontains=metodo) | Q(tanques__metodo_exec__icontains=metodo) | Q(ordem_servico__metodo__icontains=metodo))
    if tanque:
        q_filters &= (Q(nome_tanque__icontains=tanque) | Q(tanques__nome_tanque__icontains=tanque) | Q(tanque_codigo__icontains=tanque) | Q(tanques__tanque_codigo__icontains=tanque))
    if supervisor:
        q_filters &= (
            Q(ordem_servico__supervisor__username__icontains=supervisor)
            | Q(ordem_servico__supervisor__first_name__icontains=supervisor)
            | Q(ordem_servico__supervisor__last_name__icontains=supervisor)
        )
    if rdo_num:
        q_filters &= (Q(rdo__icontains=rdo_num) | Q(rdo__iexact=rdo_num))
    if status_geral:
        q_filters &= Q(ordem_servico__status_geral__icontains=status_geral)
    if status_operacao:
        q_filters &= Q(ordem_servico__status_operacao__icontains=status_operacao)

    try:
        from django.db.models.functions import Coalesce
        d1 = _parse_date_flexible(date_start)
        d2 = _parse_date_flexible(date_end)
        if d1 or d2:
            qs_eff = base_qs.annotate(_eff_date=Coalesce('data_inicio', 'data'))
            if d1 and d2:
                if d1 > d2:
                    d1, d2 = d2, d1
                qs_eff = qs_eff.filter(_eff_date__gte=d1, _eff_date__lte=d2)
            else:
                if d1:
                    qs_eff = qs_eff.filter(_eff_date__gte=d1)
                if d2:
                    qs_eff = qs_eff.filter(_eff_date__lte=d2)
            queryset = qs_eff.filter(q_filters).distinct().order_by('-id')
        else:
            queryset = base_qs.filter(q_filters).distinct().order_by('-id')
    except Exception:
        queryset = base_qs.filter(q_filters).distinct().order_by('-id')

    rows = []
    atividades_rows = []
    equipe_rows = []

    for r in queryset:
        os_obj = getattr(r, 'ordem_servico', None)
        os_num = getattr(os_obj, 'numero_os', '') if os_obj else ''
        cliente_nome = getattr(getattr(os_obj, 'Cliente', None), 'nome', '') if os_obj else ''
        unidade_nome = getattr(getattr(os_obj, 'Unidade', None), 'nome', '') if os_obj else ''
        supervisor_nome = _fmt_supervisor(getattr(os_obj, 'supervisor', None) if os_obj else None)

        atividades = []
        try:
            for at in r.atividades_rdo.all():
                atividades.append(
                    f"{(at.atividade or '').strip()} [{_fmt_time(getattr(at, 'inicio', None))}-{_fmt_time(getattr(at, 'fim', None))}]"
                )
                atividades_rows.append({
                    'RDO_ID': r.id,
                    'RDO': r.rdo or '',
                    'OS': os_num,
                    'Atividade': at.atividade or '',
                    'Início': _fmt_time(getattr(at, 'inicio', None)),
                    'Fim': _fmt_time(getattr(at, 'fim', None)),
                    'Comentário PT': getattr(at, 'comentario_pt', '') or '',
                    'Comentário EN': getattr(at, 'comentario_en', '') or '',
                })
        except Exception:
            atividades = []

        try:
            for mem in r.membros_equipe.all():
                nome_m = ''
                try:
                    nome_m = getattr(getattr(mem, 'pessoa', None), 'nome', '') or getattr(mem, 'nome', '') or ''
                except Exception:
                    nome_m = getattr(mem, 'nome', '') or ''
                equipe_rows.append({
                    'RDO_ID': r.id,
                    'RDO': r.rdo or '',
                    'OS': os_num,
                    'Nome': nome_m,
                    'Função': getattr(mem, 'funcao', '') or '',
                    'Em Serviço': 'Sim' if bool(getattr(mem, 'em_servico', False)) else 'Não',
                    'Ordem': getattr(mem, 'ordem', '') or '',
                })
        except Exception:
            pass

        atividades_texto = ' | '.join([a for a in atividades if a])
        tanks = []
        try:
            tanks = list(r.tanques.all())
        except Exception:
            tanks = []
        if not tanks:
            tanks = [None]

        for t in tanks:
            row = {
                'OS': os_num,
                'RDO_ID': r.id,
                'RDO': r.rdo or '',
                'Data': _fmt_date(getattr(r, 'data', None)),
                'Data Início': _fmt_date(getattr(r, 'data_inicio', None) or getattr(r, 'data', None)),
                'Contrato/PO': getattr(r, 'contrato_po', '') or '',
                'Turno': getattr(r, 'turno', '') or '',
                'Cliente': cliente_nome,
                'Unidade': unidade_nome,
                'Supervisor': supervisor_nome,
                'Status Geral OS': getattr(os_obj, 'status_geral', '') if os_obj else '',
                'Status Operação OS': getattr(os_obj, 'status_operacao', '') if os_obj else '',
                'Atividades': atividades_texto,
                'Tanque Código': getattr(t, 'tanque_codigo', '') if t is not None else '',
                'Nome Tanque': getattr(t, 'nome_tanque', '') if t is not None else '',
                'Tipo Tanque': getattr(t, 'tipo_tanque', '') if t is not None else '',
                'Número Compartimentos': getattr(t, 'numero_compartimentos', '') if t is not None else '',
                'Gavetas': getattr(t, 'gavetas', '') if t is not None else '',
                'Patamares': getattr(t, 'patamares', '') if t is not None else '',
                'Volume Tanque Executado': getattr(t, 'volume_tanque_exec', '') if t is not None else '',
                'Serviço Executado': getattr(t, 'servico_exec', '') if t is not None else '',
                'Método Executado': getattr(t, 'metodo_exec', '') if t is not None else '',
                'Espaço Confinado': getattr(t, 'espaco_confinado', '') if t is not None else '',
                'Operadores Simultâneos': getattr(t, 'operadores_simultaneos', '') if t is not None else '',
                'H2S (ppm)': getattr(t, 'h2s_ppm', '') if t is not None else '',
                'LEL': getattr(t, 'lel', '') if t is not None else '',
                'CO (ppm)': getattr(t, 'co_ppm', '') if t is not None else '',
                'O2 (%)': getattr(t, 'o2_percent', '') if t is not None else '',
                'N Efetivo Confinado': getattr(t, 'total_n_efetivo_confinado', '') if t is not None else '',
                'Sentido Limpeza': getattr(t, 'sentido_limpeza', '') if t is not None else '',
                'Tempo Bomba': getattr(t, 'tempo_bomba', '') if t is not None else '',
                'Ensacamento Dia': getattr(t, 'ensacamento_dia', '') if t is not None else '',
                'Ensacamento Cumulativo': getattr(t, 'ensacamento_cumulativo', '') if t is not None else '',
                'Ensacamento Previsão': getattr(t, 'ensacamento_prev', '') if t is not None else '',
                'Içamento Dia': getattr(t, 'icamento_dia', '') if t is not None else '',
                'Içamento Cumulativo': getattr(t, 'icamento_cumulativo', '') if t is not None else '',
                'Içamento Previsão': getattr(t, 'icamento_prev', '') if t is not None else '',
                'Cambagem Dia': getattr(t, 'cambagem_dia', '') if t is not None else '',
                'Cambagem Cumulativo': getattr(t, 'cambagem_cumulativo', '') if t is not None else '',
                'Cambagem Previsão': getattr(t, 'cambagem_prev', '') if t is not None else '',
                'Tambores Dia': getattr(t, 'tambores_dia', '') if t is not None else '',
                'Tambores Cumulativo': getattr(t, 'tambores_cumulativo', '') if t is not None else '',
                'Resíduos Sólidos': getattr(t, 'residuos_solidos', '') if t is not None else '',
                'Resíduos Totais': getattr(t, 'residuos_totais', '') if t is not None else '',
                'Resíduos Sólidos Cumulativo': getattr(t, 'residuos_solidos_cumulativo', '') if t is not None else '',
                'Bombeio': getattr(t, 'bombeio', '') if t is not None else '',
                'Total Líquido': getattr(t, 'total_liquido', '') if t is not None else '',
                'Total Líquido Cumulativo': getattr(t, 'total_liquido_cumulativo', '') if t is not None else '',
                'Avanço Limpeza': getattr(t, 'avanco_limpeza', '') if t is not None else '',
                'Avanço Limpeza Fina': getattr(t, 'avanco_limpeza_fina', '') if t is not None else '',
                'Limpeza Mecanizada Cumulativa (%)': getattr(t, 'limpeza_mecanizada_cumulativa', '') if t is not None else '',
                'Limpeza Fina Cumulativa (%)': getattr(t, 'limpeza_fina_cumulativa', '') if t is not None else '',
                'Percentual Ensacamento (%)': getattr(t, 'percentual_ensacamento', '') if t is not None else '',
                'Percentual Içamento (%)': getattr(t, 'percentual_icamento', '') if t is not None else '',
                'Percentual Cambagem (%)': getattr(t, 'percentual_cambagem', '') if t is not None else '',
                'Percentual Avanço (%)': getattr(t, 'percentual_avanco', '') if t is not None else '',
                'Percentual Avanço Cumulativo (%)': getattr(t, 'percentual_avanco_cumulativo', '') if t is not None else '',
                'Observações RDO PT': getattr(r, 'observacoes_rdo_pt', '') or '',
                'Observações RDO EN': getattr(r, 'observacoes_rdo_en', '') or '',
                'Ciente Observações PT': getattr(r, 'ciente_observacoes_pt', '') or '',
                'Ciente Observações EN': getattr(r, 'ciente_observacoes_en', '') or '',
            }
            rows.append(row)

    df_main = pd.DataFrame(rows)
    df_atividades = pd.DataFrame(atividades_rows)
    df_equipe = pd.DataFrame(equipe_rows)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_main.to_excel(writer, index=False, sheet_name='RDO_TANQUES')
        if not df_atividades.empty:
            df_atividades.to_excel(writer, index=False, sheet_name='ATIVIDADES')
        if not df_equipe.empty:
            df_equipe.to_excel(writer, index=False, sheet_name='EQUIPE')
    output.seek(0)

    filename = f"rdo_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@login_required(login_url='/login/')
@require_GET
def pending_os_json(request):
    try:
        qs = OrdemServico.objects.select_related('Cliente', 'Unidade', 'supervisor').all()
        try:
            is_supervisor_user = (hasattr(request, 'user') and request.user.is_authenticated and request.user.groups.filter(name='Supervisor').exists())
        except Exception:
            is_supervisor_user = False
        if is_supervisor_user:
            # Supervisor deve ver suas OS ativas mesmo com RDO já iniciado.
            qs = qs.filter(supervisor=request.user)
        else:
            # Mantém comportamento legado para outros perfis.
            qs = qs.filter(rdos__isnull=True)
        qs = qs.order_by('-id')
        os_list = []
        seen = set()
        for o in qs:
            if not _os_matches_rdo_pending_rule(o):
                continue
            dedupe_key = _os_pending_dedupe_key(o, fallback=getattr(o, 'id', None))
            if dedupe_key is not None and dedupe_key in seen:
                continue
            if dedupe_key is not None:
                seen.add(dedupe_key)

            try:
                if getattr(o, 'supervisor', None):
                    try:
                        sup_val = o.supervisor.get_full_name() or o.supervisor.username
                    except Exception:
                        sup_val = str(o.supervisor)
                else:
                    sup_val = ''
            except Exception:
                sup_val = ''

            os_list.append({
                'id': o.id,
                'os_id': o.id,
                'numero_os': o.numero_os,
                'empresa': o.cliente,
                'unidade': o.unidade,
                'supervisor': sup_val,
                'status_geral': getattr(o, 'status_geral', '') or '',
                'status_operacao': getattr(o, 'status_operacao', '') or '',
                'data_fim': (o.data_fim.isoformat() if getattr(o, 'data_fim', None) else ''),
            })
            if len(os_list) >= 200:
                break
        return JsonResponse({'success': True, 'count': len(os_list), 'data': os_list, 'os_list': os_list})
    except Exception:
        logger = logging.getLogger(__name__)
        logger.exception('Erro ao gerar lista de OS pendentes')
        return JsonResponse({'success': False, 'count': 0, 'data': [], 'os_list': []}, status=500)

@login_required(login_url='/login/')
@require_GET
def next_rdo(request):
    try:
        os_id = request.GET.get('os_id') or request.GET.get('ordem_servico_id')
        os_obj = None
        if os_id:
            try:
                os_obj = OrdemServico.objects.get(pk=os_id)
            except OrdemServico.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Ordem de Serviço não encontrada (os_id).'}, status=404)
        else:
            numero = request.GET.get('numero_os') or request.GET.get('numero') or request.GET.get('os_numero')
            if not numero:
                return JsonResponse({'success': False, 'error': 'os_id ou numero_os não informado.'}, status=400)
            try:
                numero_val = int(str(numero).strip())
            except Exception:
                numero_val = None
            try:
                if numero_val is not None:
                    os_obj = OrdemServico.objects.filter(numero_os=numero_val).first()
                else:
                    os_obj = OrdemServico.objects.filter(numero_os__iexact=str(numero).strip()).first()
                if not os_obj:
                    return JsonResponse({'success': False, 'error': 'Ordem de Serviço não encontrada (numero_os).'}, status=404)
            except Exception:
                return JsonResponse({'success': False, 'error': 'Erro ao buscar Ordem de Serviço.'}, status=500)
        try:
            is_supervisor_user = (
                hasattr(request, 'user')
                and request.user.is_authenticated
                and request.user.groups.filter(name='Supervisor').exists()
            )
        except Exception:
            is_supervisor_user = False
        if is_supervisor_user and getattr(os_obj, 'supervisor', None) != request.user:
            return JsonResponse({'success': False, 'error': 'Ordem de Serviço não encontrada.'}, status=404)

        import re
        max_val = None
        try:
            if os_obj is not None:
                numero_for_lookup = getattr(os_obj, 'numero_os', None)
                if numero_for_lookup is not None:
                    rdo_qs = RDO.objects.filter(ordem_servico__numero_os=numero_for_lookup)
                else:
                    rdo_qs = RDO.objects.filter(ordem_servico=os_obj)
            else:
                rdo_qs = RDO.objects.none()
        except Exception:
            try:
                rdo_qs = RDO.objects.filter(ordem_servico=os_obj) if os_obj is not None else RDO.objects.none()
            except Exception:
                rdo_qs = RDO.objects.none()
        try:
            try:
                agg = rdo_qs.aggregate(max_rdo=Max('rdo'))
                max_rdo_raw = agg.get('max_rdo')
                if max_rdo_raw is not None:
                    try:
                        max_val = int(str(max_rdo_raw))
                    except Exception:
                        max_val = None
            except Exception:
                max_val = None

            try:
                for r in rdo_qs.only('rdo'):
                    raw = getattr(r, 'rdo', None)
                    if raw is None:
                        continue
                    s = str(raw).strip()
                    if not s:
                        continue
                    nums = re.findall(r"\d+", s)
                    if nums:
                        for n in nums:
                            try:
                                v = int(n)
                                if max_val is None or v > max_val:
                                    max_val = v
                            except Exception:
                                continue
                    else:
                        try:
                            v = int(s)
                            if max_val is None or v > max_val:
                                max_val = v
                        except Exception:
                            continue
            except Exception:
                pass
        except Exception:
            max_val = None

        next_num = (max_val or 0) + 1
        try:
            debug_flag = str(request.GET.get('debug') or '').strip() in ('1', 'true', 'yes')
        except Exception:
            debug_flag = False

        if debug_flag:
            try:
                existing = [ (getattr(r,'rdo', None) if getattr(r,'rdo', None) is not None else None) for r in rdo_qs.only('rdo') ]
            except Exception:
                existing = []
            return JsonResponse({'success': True, 'next_rdo': next_num, 'max_rdo': max_val, 'existing_rdos': existing})

        return JsonResponse({'success': True, 'next_rdo': next_num})
    except Exception:
        logger = logging.getLogger(__name__)
        logger.exception('Erro em next_rdo')
        return JsonResponse({'success': False, 'error': 'Erro interno'}, status=500)
