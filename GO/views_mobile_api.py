import json
import logging
import os
import re
from glob import glob
from datetime import timedelta
from functools import wraps

from django.contrib.auth import authenticate
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.test.client import RequestFactory
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import (
    Funcao,
    MobileApiToken,
    MobileSyncEvent,
    OrdemServico,
    Pessoa,
    RDO,
    RdoTanque,
)
from .views_rdo import (
    _build_supervisor_limited_rdo_payload,
    _build_rdo_page_context,
    _resolve_os_service_limit,
    _resolve_os_tank_progress,
    add_tank_ajax,
    create_rdo_ajax,
    update_rdo_ajax,
    upload_rdo_photos,
)
from .supervisor_access_metrics import record_supervisor_access

logger = logging.getLogger(__name__)


def _build_compartimentos_cumulativo_json(snapshot_owner):
    if snapshot_owner is None:
        return None

    snapshot = None
    try:
        if hasattr(snapshot_owner, 'build_compartimento_progress_snapshot'):
            snapshot = snapshot_owner.build_compartimento_progress_snapshot()
        elif hasattr(snapshot_owner, '_build_compartimento_progress_snapshot'):
            snapshot = snapshot_owner._build_compartimento_progress_snapshot()
    except Exception:
        snapshot = None

    if not isinstance(snapshot, dict):
        return None

    try:
        total = int(snapshot.get('total_compartimentos') or 0)
    except Exception:
        total = 0
    if total <= 0:
        return None

    payload = {
        str(i): {'mecanizada': 0, 'fina': 0}
        for i in range(1, total + 1)
    }

    for row in snapshot.get('rows', []) or []:
        try:
            index = int(row.get('index') or 0)
        except Exception:
            index = 0
        if index <= 0 or index > total:
            continue
        key = str(index)
        for category in ('mecanizada', 'fina'):
            meta = row.get(category) or {}
            try:
                payload[key][category] = max(
                    0,
                    min(100, int(meta.get('final', 0) or 0)),
                )
            except Exception:
                payload[key][category] = 0

    try:
        return json.dumps(payload, ensure_ascii=False)
    except Exception:
        return None


def _build_declared_os_tanks(os_obj):
    if os_obj is None:
        return []

    def clean_text(value):
        return '' if value is None else str(value).strip()

    try:
        raw = getattr(os_obj, 'tanques', None)
    except Exception:
        raw = None
    raw_text = clean_text(raw)
    if not raw_text:
        return []

    labels = []
    seen = set()
    for piece in re.split(r'[\n,;]+', raw_text):
        label = clean_text(piece)
        if not label:
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        labels.append(label)

    if not labels:
        return []

    try:
        os_id = int(getattr(os_obj, 'id', 0) or 0)
    except Exception:
        os_id = 0

    out = []
    for idx, label in enumerate(labels, start=1):
        fallback_id = -((os_id or 1) * 1000 + idx)
        out.append(
            {
                'id': fallback_id,
                'tanque_codigo': label,
                'nome_tanque': label,
                'tipo_tanque': '',
                'numero_compartimentos': None,
                'gavetas': None,
                'patamares': None,
                'volume_tanque_exec': None,
                'servico_exec': '',
                'metodo_exec': '',
                'espaco_confinado': None,
                'operadores_simultaneos': None,
                'h2s_ppm': None,
                'lel': None,
                'co_ppm': None,
                'o2_percent': None,
                'total_n_efetivo_confinado': None,
                'tempo_bomba': None,
                'sentido_limpeza': '',
                'ensacamento_prev': None,
                'icamento_prev': None,
                'cambagem_prev': None,
                'ensacamento_dia': None,
                'icamento_dia': None,
                'cambagem_dia': None,
                'tambores_dia': None,
                'bombeio': None,
                'total_liquido': None,
                'residuos_solidos': None,
                'residuos_totais': None,
                'ensacamento_cumulativo': None,
                'icamento_cumulativo': None,
                'cambagem_cumulativo': None,
                'tambores_cumulativo': None,
                'total_liquido_cumulativo': None,
                'residuos_solidos_cumulativo': None,
                'percentual_limpeza_diario': None,
                'percentual_limpeza_fina_diario': None,
                'percentual_limpeza_cumulativo': None,
                'percentual_limpeza_fina_cumulativo': None,
                'avanco_limpeza': '',
                'avanco_limpeza_fina': '',
                'compartimentos_avanco_json': None,
                'compartimentos_cumulativo_json': None,
                'rdo_id': None,
                'rdo_sequence': None,
                'rdo_data': None,
            }
        )
    return out


def _resolve_mobile_total_compartimentos(snapshot_owner):
    if snapshot_owner is None:
        return None

    candidates = []

    for attr_name in ('numero_compartimentos',):
        try:
            raw_value = getattr(snapshot_owner, attr_name, None)
        except Exception:
            raw_value = None
        try:
            value = int(raw_value or 0)
        except Exception:
            value = 0
        if value > 0:
            candidates.append(value)

    try:
        if hasattr(snapshot_owner, 'get_total_compartimentos'):
            value = int(snapshot_owner.get_total_compartimentos() or 0)
            if value > 0:
                candidates.append(value)
    except Exception:
        pass

    try:
        if hasattr(snapshot_owner, '_get_total_compartimentos_for_progress'):
            raw_payload = getattr(snapshot_owner, 'compartimentos_avanco_json', None)
            value = int(snapshot_owner._get_total_compartimentos_for_progress(raw_payload=raw_payload) or 0)
            if value > 0:
                candidates.append(value)
    except Exception:
        pass

    return max(candidates) if candidates else None


def _resolve_mobile_tank_identity(snapshot_owner):
    if snapshot_owner is None:
        return {
            'code': '',
            'name': '',
            'dedup_key': '',
        }

    def clean_text(value):
        return '' if value is None else str(value).strip()

    related_rdo = None
    try:
        related_rdo = getattr(snapshot_owner, 'rdo', None)
    except Exception:
        related_rdo = None

    os_num = None
    try:
        ordem = getattr(related_rdo, 'ordem_servico', None)
        os_num = getattr(ordem, 'numero_os', None)
    except Exception:
        os_num = None
    if os_num in (None, ''):
        try:
            ordem = getattr(snapshot_owner, 'ordem_servico', None)
            os_num = getattr(ordem, 'numero_os', None)
        except Exception:
            os_num = None

    raw_code = ''
    raw_name = ''
    for owner in (snapshot_owner, related_rdo):
        if owner is None:
            continue
        if not raw_code:
            try:
                raw_code = clean_text(getattr(owner, 'tanque_codigo', None))
            except Exception:
                raw_code = ''
        if not raw_name:
            try:
                raw_name = clean_text(
                    getattr(owner, 'nome_tanque', None)
                    or getattr(owner, 'nome', None)
                )
            except Exception:
                raw_name = ''

    aliases = []
    for raw_value in (raw_code, raw_name):
        cleaned = clean_text(raw_value)
        if cleaned:
            aliases.append(cleaned)
        try:
            canon = _canonical_tank_alias_for_os(os_num, raw_value)
        except Exception:
            canon = None
        canon = clean_text(canon)
        if canon:
            aliases.append(canon)

    try:
        getter = getattr(snapshot_owner, '_get_tank_aliases', None)
        if callable(getter):
            for alias in getter() or set():
                cleaned = clean_text(alias)
                if cleaned:
                    aliases.append(cleaned)
    except Exception:
        pass

    dedup_tokens = []
    for alias in aliases:
        token = alias.casefold()
        if token and token not in dedup_tokens:
            dedup_tokens.append(token)

    dedup_key = dedup_tokens[0] if dedup_tokens else ''
    code = raw_code or (aliases[0] if aliases else '')
    name = raw_name or (aliases[0] if aliases else '')

    return {
        'code': code,
        'name': name,
        'dedup_key': dedup_key,
    }


def _parse_json_body(request):
    try:
        raw = request.body.decode('utf-8') if getattr(request, 'body', None) else ''
    except Exception:
        raw = ''
    if not raw:
        return None, 'Corpo JSON não enviado.'
    try:
        data = json.loads(raw)
    except Exception:
        return None, 'JSON inválido.'
    if not isinstance(data, dict):
        return None, 'Payload JSON deve ser um objeto.'
    return data, None


def _extract_token_from_request(request):
    try:
        auth_header = request.META.get('HTTP_AUTHORIZATION', '') or ''
    except Exception:
        auth_header = ''

    if auth_header:
        parts = auth_header.split(' ', 1)
        if len(parts) == 2 and parts[0].strip().lower() == 'bearer':
            token = parts[1].strip()
            if token:
                return token

    try:
        x_token = request.META.get('HTTP_X_MOBILE_TOKEN', '') or ''
        if x_token:
            return x_token.strip()
    except Exception:
        pass

    # Fallback para abertura de páginas mobile no navegador externo.
    # Mantemos escopo restrito apenas para GET /api/mobile/v1/rdo/<id>/page/.
    try:
        if str(getattr(request, 'method', '')).upper() == 'GET':
            path = str(getattr(request, 'path', '') or '')
            if '/api/mobile/v1/rdo/' in path and path.rstrip('/').endswith('/page'):
                query_token = str(
                    request.GET.get('access_token') or request.GET.get('token') or ''
                ).strip()
                if query_token:
                    return query_token
    except Exception:
        pass

    return ''


def _mobile_token_ttl_days():
    raw = (os.environ.get('MOBILE_API_TOKEN_TTL_DAYS') or '').strip()
    if not raw:
        return 30
    try:
        days = int(raw)
    except Exception:
        days = 30
    if days < 1:
        return 1
    if days > 180:
        return 180
    return days


def _env_bool(varname, default=False):
    raw = (os.environ.get(varname) or '').strip().lower()
    if not raw:
        return bool(default)
    return raw in ('1', 'true', 'yes', 'on')


def _env_int(varname, default=None):
    raw = (os.environ.get(varname) or '').strip()
    if not raw:
        return default
    try:
        return int(raw)
    except Exception:
        return default


def _extract_version_name_from_url(download_url):
    text = str(download_url or '').strip()
    if not text:
        return ''
    # Exemplos esperados:
    # ambipar-synchro-v1.0.0+9.apk
    # ambipar-synchro-v1.2.3.apk
    match = re.search(r'v(\d+\.\d+\.\d+(?:[+-][A-Za-z0-9._-]+)?)', text)
    if not match:
        return ''
    version_name = str(match.group(1) or '').strip()
    lowered = version_name.lower()
    if lowered.endswith('.apk') or lowered.endswith('.aab'):
        version_name = version_name[:-4]
    return version_name


def _extract_build_number(*raw_values):
    for raw in raw_values:
        value = str(raw or '').strip()
        if not value:
            continue

        if '+' in value:
            suffix = value.rsplit('+', 1)[-1].strip()
            try:
                return int(suffix)
            except Exception:
                pass

        match = re.search(r'build[^\d]*(\d+)', value, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except Exception:
                pass

        match_digits = re.search(r'(\d+)(?!.*\d)', value)
        if match_digits:
            try:
                return int(match_digits.group(1))
            except Exception:
                pass
    return None


def _discover_android_release_metadata():
    """
    Descobre automaticamente a versão/build mais recente a partir dos APKs
    publicados no servidor, sem depender de atualização manual de env var.
    """
    globs_to_scan = []
    custom_glob = (os.environ.get('MOBILE_APP_ANDROID_RELEASE_GLOB') or '').strip()
    if custom_glob:
        globs_to_scan.append(custom_glob)

    globs_to_scan.extend(
        [
            '/var/www/html/GESTAO_OPERACIONAL/static/mobile/releases/ambipar-synchro-v*.apk',
            '/var/www/mobile/rdo_offline_app/dist/android/*/ambipar-synchro-v*.apk',
        ]
    )

    best = None
    for pattern in globs_to_scan:
        try:
            candidates = glob(pattern)
        except Exception:
            candidates = []

        for apk_path in candidates:
            filename = os.path.basename(apk_path)
            version_name = _extract_version_name_from_url(filename)
            if not version_name:
                continue
            build_number = _extract_build_number(version_name, filename)
            if build_number is None:
                continue
            try:
                mtime = float(os.path.getmtime(apk_path))
            except Exception:
                mtime = 0.0

            candidate = {
                'version_name': version_name,
                'build_number': int(build_number),
                'apk_path': apk_path,
                '_mtime': mtime,
            }

            if best is None:
                best = candidate
                continue
            if int(candidate['build_number']) > int(best['build_number']):
                best = candidate
                continue
            if int(candidate['build_number']) == int(best['build_number']) and candidate['_mtime'] > best['_mtime']:
                best = candidate

    if best is None:
        return None
    best.pop('_mtime', None)
    return best


def _android_release_download_url(request, apk_path=''):
    """
    Converte um APK local publicado em URL pública do Django static.
    Se não identificar caminho público, usa o alias latest.
    """
    default_relative = '/static/mobile/releases/ambipar-synchro-latest.apk'
    base_static_dir = '/var/www/html/GESTAO_OPERACIONAL/static/mobile/releases/'
    raw_path = str(apk_path or '').strip()

    if raw_path and raw_path.startswith(base_static_dir):
        filename = os.path.basename(raw_path)
        if filename:
            return request.build_absolute_uri(f'/static/mobile/releases/{filename}')

    return request.build_absolute_uri(default_relative)


def _is_supervisor_user(user):
    try:
        if user is None or not getattr(user, 'is_authenticated', False):
            return False
        return bool(user.groups.filter(name='Supervisor').exists())
    except Exception:
        return False


def _mobile_supervisor_forbidden_response():
    return JsonResponse(
        {
            'success': False,
            'error': 'Acesso mobile permitido apenas para usuários Supervisor.',
        },
        status=403,
    )


def _coerce_post_value(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return '1' if value else '0'
    if isinstance(value, (int, float, str)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def _build_internal_post_request(source_request, payload):
    rf = RequestFactory()
    data = {}
    for key, raw_value in (payload or {}).items():
        if raw_value is None:
            continue
        if isinstance(raw_value, (list, tuple)):
            values = []
            for item in raw_value:
                coerced = _coerce_post_value(item)
                if coerced is not None:
                    values.append(coerced)
            data[str(key)] = values
            continue
        coerced = _coerce_post_value(raw_value)
        if coerced is not None:
            data[str(key)] = coerced

    req = rf.post('/api/mobile/internal/', data=data)
    req.user = getattr(source_request, 'user', None)
    req.session = getattr(source_request, 'session', {})
    req.mobile_api_token = getattr(source_request, 'mobile_api_token', None)
    explicit_channel = str(getattr(source_request, 'rdo_request_channel', '') or '').strip().lower()
    if explicit_channel in {'web', 'mobile'}:
        req.rdo_request_channel = explicit_channel
    elif getattr(source_request, 'mobile_api_token', None) is not None:
        req.rdo_request_channel = 'mobile'
    req._dont_enforce_csrf_checks = True
    return req


def _build_internal_photo_request(source_request, photo_file):
    rf = RequestFactory()

    data = {}
    try:
        for key in source_request.POST.keys():
            if key in ('foto', 'fotos'):
                continue
            vals = source_request.POST.getlist(key) if hasattr(source_request.POST, 'getlist') else [source_request.POST.get(key)]
            if vals is None:
                continue
            if len(vals) > 1:
                data[str(key)] = [v for v in vals if v is not None]
            elif len(vals) == 1 and vals[0] is not None:
                data[str(key)] = vals[0]
    except Exception:
        pass

    data['fotos'] = photo_file

    req = rf.post('/api/mobile/internal/photo/', data=data)
    req.user = getattr(source_request, 'user', None)
    req.session = getattr(source_request, 'session', {})
    req.mobile_api_token = getattr(source_request, 'mobile_api_token', None)
    explicit_channel = str(getattr(source_request, 'rdo_request_channel', '') or '').strip().lower()
    if explicit_channel in {'web', 'mobile'}:
        req.rdo_request_channel = explicit_channel
    elif getattr(source_request, 'mobile_api_token', None) is not None:
        req.rdo_request_channel = 'mobile'
    req._dont_enforce_csrf_checks = True
    return req


def _response_to_json(http_response):
    status_code = int(getattr(http_response, 'status_code', 200) or 200)
    payload = {}
    try:
        body = http_response.content.decode('utf-8') if getattr(http_response, 'content', None) else ''
    except Exception:
        body = ''
    if body:
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                payload = parsed
            else:
                payload = {'raw': parsed}
        except Exception:
            payload = {'raw': body}
    return status_code, payload


def _extract_mobile_request_payload(request):
    try:
        body = request.body.decode('utf-8') if getattr(request, 'body', None) else ''
    except Exception:
        body = ''

    if body:
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                nested = parsed.get('payload')
                if isinstance(nested, dict):
                    return nested
                return parsed
        except Exception:
            pass

    payload = {}
    try:
        for key in request.POST.keys():
            values = request.POST.getlist(key) if hasattr(request.POST, 'getlist') else [request.POST.get(key)]
            if not values:
                continue
            if len(values) > 1:
                payload[str(key)] = list(values)
            else:
                payload[str(key)] = values[0]
    except Exception:
        payload = {}
    return payload


def mobile_auth_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        # If a mobile bearer token is provided, always authenticate by token first.
        # This prevents conflicts when the same browser also carries a web session
        # cookie from a non-supervisor user.
        token_key = _extract_token_from_request(request)
        if token_key:
            token_obj = MobileApiToken.objects.select_related('user').filter(key=token_key, is_active=True).first()
            if token_obj is None:
                return JsonResponse({'success': False, 'error': 'Token inválido.'}, status=401)

            if token_obj.is_expired():
                try:
                    token_obj.is_active = False
                    token_obj.save(update_fields=['is_active', 'updated_at'])
                except Exception:
                    pass
                return JsonResponse({'success': False, 'error': 'Token expirado.'}, status=401)

            user = getattr(token_obj, 'user', None)
            if user is None or not getattr(user, 'is_active', False):
                return JsonResponse({'success': False, 'error': 'Usuário do token inválido.'}, status=401)
            if not _is_supervisor_user(user):
                try:
                    token_obj.is_active = False
                    token_obj.save(update_fields=['is_active', 'updated_at'])
                except Exception:
                    pass
                return _mobile_supervisor_forbidden_response()

            request.user = user
            request.mobile_api_token = token_obj
            request.rdo_request_channel = 'mobile'

            try:
                token_obj.last_used_at = timezone.now()
                token_obj.save(update_fields=['last_used_at', 'updated_at'])
            except Exception:
                pass

            try:
                record_supervisor_access(
                    user=user,
                    channel='mobile',
                    path=getattr(request, 'path', ''),
                    device_name=getattr(token_obj, 'device_name', '') or '',
                    platform=getattr(token_obj, 'platform', '') or '',
                )
            except Exception:
                pass

            return view_func(request, *args, **kwargs)

        try:
            user = getattr(request, 'user', None)
            if user is not None and getattr(user, 'is_authenticated', False):
                if not _is_supervisor_user(user):
                    return _mobile_supervisor_forbidden_response()
                return view_func(request, *args, **kwargs)
        except Exception:
            pass

        return JsonResponse({'success': False, 'error': 'Autenticação requerida.'}, status=401)

    return _wrapped


def _dispatch_operation(source_request, operation, payload):
    op = str(operation or '').strip().lower()
    request_for_view = _build_internal_post_request(source_request, payload)

    if op in {'rdo.create', 'rdo_create', 'create_rdo'}:
        return create_rdo_ajax(request_for_view)

    if op in {'rdo.update', 'rdo_update', 'update_rdo'}:
        request_for_view.rdo_mobile_full_sync = True
        return update_rdo_ajax(request_for_view)

    if op in {'rdo.tank.add', 'rdo_add_tank', 'add_tank'}:
        rdo_id_raw = payload.get('rdo_id') or payload.get('id')
        try:
            rdo_id = int(str(rdo_id_raw).strip())
        except Exception:
            return JsonResponse(
                {'success': False, 'error': 'rdo_id é obrigatório para rdo.tank.add.'},
                status=400,
            )
        return add_tank_ajax(request_for_view, rdo_id)

    return JsonResponse({'success': False, 'error': f'Operação não suportada: {operation}'}, status=400)


def _sync_replay_response(event_obj):
    return {
        'success': event_obj.state == MobileSyncEvent.STATE_DONE,
        'idempotent': True,
        'client_uuid': event_obj.client_uuid,
        'operation': event_obj.operation,
        'state': event_obj.state,
        'result': event_obj.response_payload or {},
        'error_message': event_obj.error_message,
        'http_status': int(getattr(event_obj, 'http_status', 200) or 200),
    }


def _sync_runtime_response(
    *,
    success,
    idempotent,
    client_uuid,
    operation,
    state,
    result=None,
    error_message=None,
    http_status=200,
):
    return {
        'success': bool(success),
        'idempotent': bool(idempotent),
        'client_uuid': str(client_uuid or '').strip(),
        'operation': str(operation or '').strip(),
        'state': str(state or MobileSyncEvent.STATE_ERROR),
        'result': result if isinstance(result, dict) else (result or {}),
        'error_message': error_message,
        'http_status': int(http_status or 200),
    }


def _execute_sync_operation(source_request, client_uuid, operation, payload):
    request_user = getattr(source_request, 'user', None)
    existing = MobileSyncEvent.objects.filter(client_uuid=client_uuid, user=request_user).first()
    if existing is not None:
        replay_marker = (
            getattr(existing, 'updated_at', None)
            or getattr(existing, 'processed_at', None)
            or getattr(existing, 'created_at', None)
        )
        replay_age_limit = timezone.now() - timedelta(minutes=2)
        should_reprocess = False
        try:
            if existing.state == MobileSyncEvent.STATE_PROCESSING and replay_marker and replay_marker <= replay_age_limit:
                should_reprocess = True
            elif (
                existing.state == MobileSyncEvent.STATE_ERROR
                and int(getattr(existing, 'http_status', 0) or 0) >= 500
                and replay_marker
                and replay_marker <= replay_age_limit
            ):
                should_reprocess = True
        except Exception:
            should_reprocess = False

        if not should_reprocess:
            return _sync_replay_response(existing)

        event = existing
        event.operation = operation
        event.request_payload = {'payload': payload}
        event.state = MobileSyncEvent.STATE_PROCESSING
        event.http_status = 202
        event.response_payload = {}
        event.error_message = None
        event.processed_at = None
        event.save(
            update_fields=[
                'operation',
                'request_payload',
                'state',
                'http_status',
                'response_payload',
                'error_message',
                'processed_at',
                'updated_at',
            ]
        )
    else:
        try:
            with transaction.atomic():
                event = MobileSyncEvent.objects.create(
                    client_uuid=client_uuid,
                    operation=operation,
                    user=request_user,
                    request_payload={'payload': payload},
                    state=MobileSyncEvent.STATE_PROCESSING,
                    http_status=202,
                )
        except IntegrityError:
            existing = MobileSyncEvent.objects.filter(client_uuid=client_uuid, user=request_user).first()
            if existing is None:
                return _sync_runtime_response(
                    success=False,
                    idempotent=False,
                    client_uuid=client_uuid,
                    operation=operation,
                    state=MobileSyncEvent.STATE_ERROR,
                    result={},
                    error_message='Falha de concorrência na idempotência.',
                    http_status=409,
                )
            return _sync_replay_response(existing)

    try:
        internal_response = _dispatch_operation(source_request, operation, payload)
        status_code, response_payload = _response_to_json(internal_response)
        status_code = int(status_code or 200)

        success = bool(200 <= status_code < 300)
        if isinstance(response_payload, dict) and 'success' in response_payload:
            success = success and bool(response_payload.get('success'))

        event.state = MobileSyncEvent.STATE_DONE if success else MobileSyncEvent.STATE_ERROR
        event.http_status = status_code
        event.response_payload = response_payload
        event.error_message = None if success else (
            (response_payload.get('error') if isinstance(response_payload, dict) else None)
            or f'Operação retornou status {status_code}.'
        )
        event.processed_at = timezone.now()
        event.save(
            update_fields=[
                'state',
                'http_status',
                'response_payload',
                'error_message',
                'processed_at',
                'updated_at',
            ]
        )

        return _sync_runtime_response(
            success=success,
            idempotent=False,
            client_uuid=client_uuid,
            operation=operation,
            state=event.state,
            result=response_payload,
            error_message=event.error_message,
            http_status=status_code,
        )
    except Exception as exc:
        logger.exception('Erro ao processar sync mobile para client_uuid=%s', client_uuid)
        event.state = MobileSyncEvent.STATE_ERROR
        event.http_status = 500
        event.response_payload = {'success': False, 'error': 'Erro interno no processamento mobile.'}
        event.error_message = str(exc)
        event.processed_at = timezone.now()
        event.save(
            update_fields=[
                'state',
                'http_status',
                'response_payload',
                'error_message',
                'processed_at',
                'updated_at',
            ]
        )
        return _sync_runtime_response(
            success=False,
            idempotent=False,
            client_uuid=client_uuid,
            operation=operation,
            state=event.state,
            result={},
            error_message=event.error_message,
            http_status=500,
        )


def _coerce_int(value):
    try:
        if value is None:
            return None
        s = str(value).strip()
        if not s:
            return None
        return int(s)
    except Exception:
        try:
            return int(float(str(value).strip()))
        except Exception:
            return None


def _extract_entity_id(operation, payload, response_payload):
    op = str(operation or '').strip().lower()
    candidates = []
    if isinstance(response_payload, dict):
        rdo_obj = response_payload.get('rdo')
        tank_obj = response_payload.get('tank')
        updated_obj = response_payload.get('updated')
        if op in {'rdo.tank.add', 'rdo_add_tank', 'add_tank'}:
            candidates.extend([
                response_payload.get('tank_id'),
                tank_obj.get('id') if isinstance(tank_obj, dict) else None,
                updated_obj.get('tank_id') if isinstance(updated_obj, dict) else None,
                response_payload.get('id'),
                response_payload.get('rdo_id'),
                rdo_obj.get('id') if isinstance(rdo_obj, dict) else None,
                updated_obj.get('rdo_id') if isinstance(updated_obj, dict) else None,
            ])
        else:
            candidates.extend([
                response_payload.get('id'),
                response_payload.get('rdo_id'),
                rdo_obj.get('id') if isinstance(rdo_obj, dict) else None,
                updated_obj.get('rdo_id') if isinstance(updated_obj, dict) else None,
                response_payload.get('tank_id'),
                tank_obj.get('id') if isinstance(tank_obj, dict) else None,
                updated_obj.get('tank_id') if isinstance(updated_obj, dict) else None,
            ])

    if isinstance(payload, dict):
        if op in {'rdo.tank.add', 'rdo_add_tank', 'add_tank'}:
            candidates.append(payload.get('tank_id'))
        if op in {'rdo.update', 'rdo_update', 'update_rdo', 'rdo.tank.add', 'rdo_add_tank', 'add_tank'}:
            candidates.append(payload.get('rdo_id'))

    for value in candidates:
        parsed = _coerce_int(value)
        if parsed is not None:
            return parsed
    return None


def _resolve_payload_refs(payload, alias_to_entity_id):
    unresolved = []

    def _walk(value):
        if isinstance(value, str):
            marker = value.strip()
            if marker.lower().startswith('@ref:'):
                alias = marker[5:].strip()
                if alias and alias in alias_to_entity_id:
                    return alias_to_entity_id.get(alias)
                unresolved.append(alias or marker)
                return value
            return value

        if isinstance(value, dict):
            if len(value) == 1 and '$ref' in value:
                alias = str(value.get('$ref') or '').strip()
                if alias and alias in alias_to_entity_id:
                    return alias_to_entity_id.get(alias)
                unresolved.append(alias or '$ref')
                return value
            return {k: _walk(v) for k, v in value.items()}

        if isinstance(value, list):
            return [_walk(v) for v in value]

        return value

    resolved_payload = _walk(payload if isinstance(payload, dict) else {})

    dedup = []
    for item in unresolved:
        if item not in dedup:
            dedup.append(item)

    return resolved_payload, dedup


def _evaluate_dependencies(depends_on, status_by_uuid, status_by_alias):
    missing = []
    failed = []

    for dep in depends_on:
        dep_key = str(dep or '').strip()
        if not dep_key:
            continue
        if dep_key in status_by_uuid:
            if not bool(status_by_uuid.get(dep_key)):
                failed.append(dep_key)
            continue
        if dep_key in status_by_alias:
            if not bool(status_by_alias.get(dep_key)):
                failed.append(dep_key)
            continue
        missing.append(dep_key)

    return missing, failed


@csrf_exempt
@require_POST
def mobile_auth_token(request):
    body, parse_error = _parse_json_body(request)
    if parse_error:
        return JsonResponse({'success': False, 'error': parse_error}, status=400)

    username = str(body.get('username') or '').strip()
    password = str(body.get('password') or '')
    device_name = str(body.get('device_name') or '').strip()[:120]
    platform = str(body.get('platform') or '').strip()[:30]

    if not username or not password:
        return JsonResponse({'success': False, 'error': 'username e password são obrigatórios.'}, status=400)

    user = authenticate(request, username=username, password=password)
    if user is None:
        try:
            user = authenticate(request, email=username, password=password)
        except Exception:
            user = None

    # Some auth backends in this project authenticate by e-mail only.
    # Allow supervisor login with username by resolving the mapped e-mail.
    if user is None and '@' not in username:
        try:
            from django.contrib.auth.models import User as DjangoUser

            user_obj = DjangoUser.objects.filter(username=username).only('email').first()
            resolved_email = (getattr(user_obj, 'email', None) or '').strip()
            if resolved_email:
                user = authenticate(request, email=resolved_email, password=password)
        except Exception:
            user = None

    if user is None:
        return JsonResponse({'success': False, 'error': 'Credenciais inválidas.'}, status=401)
    if not getattr(user, 'is_active', False):
        return JsonResponse({'success': False, 'error': 'Usuário inativo.'}, status=403)
    if not _is_supervisor_user(user):
        return _mobile_supervisor_forbidden_response()

    ttl_days = _mobile_token_ttl_days()
    expires_at = timezone.now() + timedelta(days=ttl_days)

    token = MobileApiToken.objects.create(
        key=MobileApiToken.generate_key(),
        user=user,
        device_name=device_name or None,
        platform=platform or None,
        is_active=True,
        expires_at=expires_at,
    )

    return JsonResponse(
        {
            'success': True,
            'token_type': 'Bearer',
            'access_token': token.key,
            'expires_at': token.expires_at.isoformat() if token.expires_at else None,
            'user': {
                'id': user.id,
                'username': user.username,
                'is_superuser': bool(getattr(user, 'is_superuser', False)),
                'is_supervisor': True,
            },
        },
        status=200,
    )


@csrf_exempt
@mobile_auth_required
@require_POST
def mobile_auth_revoke(request):
    token_obj = getattr(request, 'mobile_api_token', None)

    if token_obj is None:
        token_key = _extract_token_from_request(request)
        if token_key:
            token_obj = MobileApiToken.objects.filter(key=token_key, user=request.user).first()

    if token_obj is None:
        return JsonResponse({'success': False, 'error': 'Token não informado.'}, status=400)

    token_obj.is_active = False
    token_obj.save(update_fields=['is_active', 'updated_at'])
    return JsonResponse({'success': True, 'message': 'Token revogado.'}, status=200)


@csrf_exempt
@mobile_auth_required
@require_GET
def mobile_bootstrap(request):
    qs = OrdemServico.objects.filter(supervisor=request.user)

    # Keep parity with web "OS pendentes" logic: finalized/canceled operations
    # are not relevant for starting new RDOs in mobile.
    try:
        final_pattern = r'finaliz|encerrad|fechad|conclu|retorn|cancel'
        qs = qs.exclude(Q(status_operacao__iregex=final_pattern))
    except Exception:
        pass

    qs = qs.annotate(rdo_count=Count('rdos'), last_rdo_id=Max('rdos__id')).order_by('-data_inicio', '-id')

    def _clean_text(value):
        if value is None:
            return ''
        return str(value).strip()

    def _is_final_status(*values):
        final_keywords = ('retorn', 'finaliz', 'encerrad', 'fechad', 'conclu')
        for value in values:
            low = _clean_text(value).lower()
            if low and any(keyword in low for keyword in final_keywords):
                return True
        return False

    def _is_in_progress_status(*values):
        progress_keywords = ('andamento', 'em andamento', 'iniciad', 'execut')
        for value in values:
            low = _clean_text(value).lower()
            if low and any(keyword in low for keyword in progress_keywords):
                return True
        return False

    def _is_canceled_status(*values):
        canceled_keywords = ('cancel', 'cancelad', 'cancelled')
        for value in values:
            low = _clean_text(value).lower()
            if low and any(keyword in low for keyword in canceled_keywords):
                return True
        return False

    def _max_int(a, b):
        try:
            ai = int(a) if a is not None else None
        except Exception:
            ai = None
        try:
            bi = int(b) if b is not None else None
        except Exception:
            bi = None
        if ai is None:
            return bi
        if bi is None:
            return ai
        return ai if ai >= bi else bi

    def _extract_rdo_numeric_max(raw):
        try:
            text = _clean_text(raw)
        except Exception:
            text = ''
        if not text:
            return None

        # Keep parity with web next_rdo behavior:
        # if the RDO label contains digits (e.g. "RDO 18"), use the max chunk.
        max_found = None
        token = ''
        for ch in text:
            if ch.isdigit():
                token += ch
                continue
            if token:
                try:
                    parsed = int(token)
                except Exception:
                    parsed = None
                if parsed is not None and (max_found is None or parsed > max_found):
                    max_found = parsed
                token = ''
        if token:
            try:
                parsed = int(token)
            except Exception:
                parsed = None
            if parsed is not None and (max_found is None or parsed > max_found):
                max_found = parsed

        if max_found is not None:
            return max_found

        try:
            return int(text)
        except Exception:
            return None

    grouped_by_os = {}
    for os_obj in qs[:500]:
        numero_os = _clean_text(getattr(os_obj, 'numero_os', None))
        if not numero_os:
            continue

        status_geral = _clean_text(getattr(os_obj, 'status_geral', None))
        status_operacao = _clean_text(getattr(os_obj, 'status_operacao', None))
        status_linha = _clean_text(
            getattr(os_obj, 'status_frente', None) or getattr(os_obj, 'status', None) or status_geral
        )

        # Mobile must show OS only while the supervisor line status is in progress.
        # Cancelled/finalized lines (or operations) are hidden to avoid confusion.
        if _is_canceled_status(status_linha, status_operacao, status_geral):
            continue
        if _is_final_status(status_linha, status_operacao):
            continue
        if not (_clean_text(status_linha) or _clean_text(status_operacao) or _clean_text(status_geral)):
            continue

        try:
            cliente = getattr(os_obj, 'cliente', None)
        except Exception:
            cliente = None
        try:
            unidade = getattr(os_obj, 'unidade', None)
        except Exception:
            unidade = None

        data_inicio = getattr(os_obj, 'data_inicio', None)
        data_fim = getattr(os_obj, 'data_fim', None)
        candidate = {
            'id': os_obj.id,
            'numero_os': numero_os,
            'servico': getattr(os_obj, 'servico', None),
            'status_geral': status_geral,
            'status_operacao': status_operacao,
            'status_linha_movimentacao': status_linha,
            'data_inicio': data_inicio.isoformat() if data_inicio else None,
            'data_fim': data_fim.isoformat() if data_fim else None,
            'cliente': cliente,
            'unidade': unidade,
            'rdo_count': int(getattr(os_obj, 'rdo_count', 0) or 0),
            'last_rdo_id': getattr(os_obj, 'last_rdo_id', None),
            '_is_in_progress': _is_in_progress_status(status_operacao, status_linha, status_geral),
            '_sort_date': data_inicio.isoformat() if data_inicio else '',
            '_source_os_ids': {int(os_obj.id)},
        }

        existing = grouped_by_os.get(numero_os)
        if existing is None:
            grouped_by_os[numero_os] = candidate
            continue

        # Keep aggregate counters safe when multiple rows map to same numero_os.
        merged_rdo_count = max(int(existing.get('rdo_count') or 0), int(candidate.get('rdo_count') or 0))
        merged_last_rdo_id = _max_int(existing.get('last_rdo_id'), candidate.get('last_rdo_id'))
        merged_source_os_ids = set(existing.get('_source_os_ids') or set())
        merged_source_os_ids.update(candidate.get('_source_os_ids') or set())

        prefer_candidate = False
        if bool(candidate.get('_is_in_progress')) != bool(existing.get('_is_in_progress')):
            prefer_candidate = bool(candidate.get('_is_in_progress'))
        else:
            existing_sort = (existing.get('_sort_date') or '', int(existing.get('id') or 0))
            candidate_sort = (candidate.get('_sort_date') or '', int(candidate.get('id') or 0))
            prefer_candidate = candidate_sort > existing_sort

        if prefer_candidate:
            grouped_by_os[numero_os] = candidate
            existing = candidate

        existing['rdo_count'] = merged_rdo_count
        existing['last_rdo_id'] = merged_last_rdo_id
        existing['_source_os_ids'] = merged_source_os_ids

    items = list(grouped_by_os.values())

    # Reconcile RDO counters by numero_os (global), independent of supervisor
    # reassignment. This avoids showing "RDO 3" when the OS already has
    # historical records from another supervisor (e.g. should be "RDO 18").
    try:
        os_numbers = []
        for row in items:
            numero = _clean_text(row.get('numero_os'))
            if numero:
                os_numbers.append(numero)

        global_rdo_stats = {}
        if os_numbers:
            rdo_rows = (
                RDO.objects
                .filter(ordem_servico__numero_os__in=os_numbers)
                .values_list('id', 'ordem_servico__numero_os', 'rdo')
            )
            for rdo_id, numero_raw, rdo_label in rdo_rows:
                numero = _clean_text(numero_raw)
                if not numero:
                    continue

                bucket = global_rdo_stats.setdefault(
                    numero,
                    {
                        'count': 0,
                        'last_rdo_id': None,
                        'max_rdo_numeric': 0,
                    },
                )
                bucket['count'] = int(bucket.get('count') or 0) + 1
                bucket['last_rdo_id'] = _max_int(bucket.get('last_rdo_id'), rdo_id)

                parsed_rdo = _extract_rdo_numeric_max(rdo_label)
                if parsed_rdo is not None and int(parsed_rdo) > int(bucket.get('max_rdo_numeric') or 0):
                    bucket['max_rdo_numeric'] = int(parsed_rdo)

        for row in items:
            numero = _clean_text(row.get('numero_os'))
            local_count = int(row.get('rdo_count') or 0)
            local_last_id = row.get('last_rdo_id')

            stats = global_rdo_stats.get(numero)
            if stats:
                global_count = int(stats.get('count') or 0)
                max_rdo_numeric = int(stats.get('max_rdo_numeric') or 0)
                effective_rdo_base = max(local_count, global_count, max_rdo_numeric)
                # Keep backward compatibility with app builds that still derive
                # "next RDO" from rdo_count only.
                row['rdo_count'] = effective_rdo_base
                row['last_rdo_id'] = _max_int(local_last_id, stats.get('last_rdo_id'))
                base_numeric = effective_rdo_base
            else:
                row['rdo_count'] = local_count
                row['last_rdo_id'] = local_last_id
                base_numeric = local_count

            row['next_rdo'] = int(base_numeric or 0) + 1
    except Exception:
        logger.exception('Falha ao reconciliar contagem de RDO por numero_os no bootstrap mobile')
        for row in items:
            try:
                row['next_rdo'] = int(row.get('rdo_count') or 0) + 1
            except Exception:
                row['next_rdo'] = 1

    items.sort(
        key=lambda row: (
            1 if row.get('_is_in_progress') else 0,
            row.get('_sort_date') or '',
            int(row.get('id') or 0),
        ),
        reverse=True,
    )

    primary_os = None
    for row in items:
        if row.get('_is_in_progress'):
            primary_os = row.get('numero_os')
            break
    if primary_os is None and items:
        primary_os = items[0].get('numero_os')

    tank_by_os_number = {}
    try:
        os_numbers_scope = []
        for row in items:
            numero = _clean_text(row.get('numero_os'))
            if numero:
                os_numbers_scope.append(numero)

        if os_numbers_scope:
            tanks_qs = (
                RdoTanque.objects
                .filter(rdo__ordem_servico__numero_os__in=os_numbers_scope)
                .select_related('rdo__ordem_servico')
                .order_by('rdo__ordem_servico__numero_os', '-rdo__data', '-id')
            )

            seen_by_os = {}
            for tank in tanks_qs:
                try:
                    tank_rdo = getattr(tank, 'rdo', None)
                    tank_os = getattr(tank_rdo, 'ordem_servico', None)
                    numero = _clean_text(getattr(tank_os, 'numero_os', None))
                except Exception:
                    numero = ''
                if not numero:
                    continue

                identity = _resolve_mobile_tank_identity(tank)
                code = identity.get('code') or ''
                name = identity.get('name') or ''
                dedup_key = identity.get('dedup_key') or ''
                if not dedup_key:
                    continue

                os_seen = seen_by_os.setdefault(numero, set())
                if dedup_key in os_seen:
                    continue
                os_seen.add(dedup_key)

                bucket = tank_by_os_number.setdefault(numero, [])
                if len(bucket) >= 120:
                    continue

                try:
                    rdo_date = getattr(tank_rdo, 'data', None)
                except Exception:
                    rdo_date = None

                bucket.append(
                    {
                        'id': getattr(tank, 'id', None),
                        'tanque_codigo': code,
                        'nome_tanque': name,
                        'tipo_tanque': _clean_text(getattr(tank, 'tipo_tanque', None)),
                        'numero_compartimentos': _resolve_mobile_total_compartimentos(tank),
                        'gavetas': getattr(tank, 'gavetas', None),
                        'patamares': getattr(tank, 'patamares', None),
                        'volume_tanque_exec': (
                            str(getattr(tank, 'volume_tanque_exec', None))
                            if getattr(tank, 'volume_tanque_exec', None) is not None
                            else None
                        ),
                        'servico_exec': _clean_text(getattr(tank, 'servico_exec', None)),
                        'metodo_exec': _clean_text(getattr(tank, 'metodo_exec', None)),
                        'espaco_confinado': getattr(tank, 'espaco_confinado', None),
                        'operadores_simultaneos': getattr(tank, 'operadores_simultaneos', None),
                        'h2s_ppm': getattr(tank, 'h2s_ppm', None),
                        'lel': getattr(tank, 'lel', None),
                        'co_ppm': getattr(tank, 'co_ppm', None),
                        'o2_percent': getattr(tank, 'o2_percent', None),
                        'total_n_efetivo_confinado': getattr(tank, 'total_n_efetivo_confinado', None),
                        'tempo_bomba': getattr(tank, 'tempo_bomba', None),
                        'sentido_limpeza': _clean_text(getattr(tank, 'sentido_limpeza', None)),
                        'ensacamento_prev': getattr(tank, 'ensacamento_prev', None),
                        'icamento_prev': getattr(tank, 'icamento_prev', None),
                        'cambagem_prev': getattr(tank, 'cambagem_prev', None),
                        'ensacamento_dia': getattr(tank, 'ensacamento_dia', None),
                        'icamento_dia': getattr(tank, 'icamento_dia', None),
                        'cambagem_dia': getattr(tank, 'cambagem_dia', None),
                        'tambores_dia': getattr(tank, 'tambores_dia', None),
                        'bombeio': getattr(tank, 'bombeio', None),
                        'total_liquido': getattr(tank, 'total_liquido', None),
                        'residuos_solidos': getattr(tank, 'residuos_solidos', None),
                        'residuos_totais': getattr(tank, 'residuos_totais', None),
                        'ensacamento_cumulativo': getattr(tank, 'ensacamento_cumulativo', None),
                        'icamento_cumulativo': getattr(tank, 'icamento_cumulativo', None),
                        'cambagem_cumulativo': getattr(tank, 'cambagem_cumulativo', None),
                        'tambores_cumulativo': getattr(tank, 'tambores_cumulativo', None),
                        'total_liquido_cumulativo': getattr(tank, 'total_liquido_cumulativo', None),
                        'residuos_solidos_cumulativo': getattr(tank, 'residuos_solidos_cumulativo', None),
                        'percentual_limpeza_diario': getattr(tank, 'percentual_limpeza_diario', None),
                        'percentual_limpeza_fina_diario': getattr(tank, 'percentual_limpeza_fina_diario', None),
                        'percentual_limpeza_cumulativo': getattr(tank, 'percentual_limpeza_cumulativo', None),
                        'percentual_limpeza_fina_cumulativo': getattr(tank, 'percentual_limpeza_fina_cumulativo', None),
                        'avanco_limpeza': _clean_text(getattr(tank, 'avanco_limpeza', None)),
                        'avanco_limpeza_fina': _clean_text(getattr(tank, 'avanco_limpeza_fina', None)),
                        'compartimentos_avanco_json': getattr(tank, 'compartimentos_avanco_json', None),
                        'compartimentos_cumulativo_json': _build_compartimentos_cumulativo_json(tank),
                        'rdo_id': getattr(tank_rdo, 'id', None),
                        'rdo_sequence': _extract_rdo_numeric_max(getattr(tank_rdo, 'rdo', None)),
                        'rdo_data': rdo_date.isoformat() if rdo_date else None,
                    }
                )

            missing_numbers = []
            for numero in os_numbers_scope:
                if not tank_by_os_number.get(numero):
                    missing_numbers.append(numero)

            if missing_numbers:
                rdo_fallback_qs = (
                    RDO.objects
                    .filter(ordem_servico__numero_os__in=missing_numbers)
                    .order_by('ordem_servico__numero_os', '-data', '-id')
                )

                seen_legacy_by_os = {}
                for rdo in rdo_fallback_qs:
                    try:
                        rdo_os = getattr(rdo, 'ordem_servico', None)
                        numero = _clean_text(getattr(rdo_os, 'numero_os', None))
                    except Exception:
                        numero = ''
                    if not numero or numero not in missing_numbers:
                        continue

                    identity = _resolve_mobile_tank_identity(rdo)
                    code = identity.get('code') or ''
                    name = identity.get('name') or ''
                    dedup_key = identity.get('dedup_key') or ''
                    if not dedup_key:
                        continue

                    os_seen = seen_legacy_by_os.setdefault(numero, set())
                    if dedup_key in os_seen:
                        continue
                    os_seen.add(dedup_key)

                    bucket = tank_by_os_number.setdefault(numero, [])
                    if len(bucket) >= 120:
                        continue

                    try:
                        rdo_date = getattr(rdo, 'data', None)
                    except Exception:
                        rdo_date = None

                    fallback_id = None
                    try:
                        rid = int(getattr(rdo, 'id', 0) or 0)
                        if rid > 0:
                            fallback_id = -rid
                    except Exception:
                        fallback_id = None

                    bucket.append(
                        {
                            'id': fallback_id,
                            'tanque_codigo': code,
                            'nome_tanque': name,
                            'tipo_tanque': _clean_text(getattr(rdo, 'tipo_tanque', None)),
                            'numero_compartimentos': _resolve_mobile_total_compartimentos(rdo),
                            'gavetas': getattr(rdo, 'gavetas', None),
                            'patamares': getattr(rdo, 'patamares', None),
                            'volume_tanque_exec': (
                                str(getattr(rdo, 'volume_tanque_exec', None))
                                if getattr(rdo, 'volume_tanque_exec', None) is not None
                                else None
                            ),
                            'servico_exec': _clean_text(getattr(rdo, 'servico_exec', None)),
                            'metodo_exec': _clean_text(getattr(rdo, 'metodo_exec', None)),
                            'espaco_confinado': getattr(rdo, 'confinado', None),
                            'operadores_simultaneos': getattr(rdo, 'operadores_simultaneos', None),
                            'h2s_ppm': getattr(rdo, 'h2s_ppm', None),
                            'lel': getattr(rdo, 'lel', None),
                            'co_ppm': getattr(rdo, 'co_ppm', None),
                            'o2_percent': getattr(rdo, 'o2_percent', None),
                            'total_n_efetivo_confinado': getattr(rdo, 'total_n_efetivo_confinado', None),
                            'tempo_bomba': getattr(rdo, 'tempo_uso_bomba', None),
                            'sentido_limpeza': _clean_text(getattr(rdo, 'sentido_limpeza', None)),
                            'ensacamento_prev': getattr(rdo, 'ensacamento_prev', None),
                            'icamento_prev': getattr(rdo, 'icamento_prev', None),
                            'cambagem_prev': getattr(rdo, 'cambagem_prev', None),
                            'ensacamento_dia': getattr(rdo, 'ensacamento', None),
                            'icamento_dia': getattr(rdo, 'icamento', None),
                            'cambagem_dia': getattr(rdo, 'cambagem', None),
                            'tambores_dia': getattr(rdo, 'tambores', None),
                            'bombeio': getattr(rdo, 'bombeio', None),
                            'total_liquido': getattr(rdo, 'total_liquido', None),
                            'residuos_solidos': getattr(rdo, 'total_solidos', None),
                            'residuos_totais': getattr(rdo, 'total_residuos', None),
                            'ensacamento_cumulativo': getattr(rdo, 'ensacamento_cumulativo', None),
                            'icamento_cumulativo': getattr(rdo, 'icamento_cumulativo', None),
                            'cambagem_cumulativo': getattr(rdo, 'cambagem_cumulativo', None),
                            'tambores_cumulativo': getattr(rdo, 'tambores_acu', None),
                            'total_liquido_cumulativo': getattr(rdo, 'total_liquido_acu', None),
                            'residuos_solidos_cumulativo': getattr(rdo, 'residuos_solidos_acu', None),
                            'percentual_limpeza_diario': getattr(rdo, 'percentual_limpeza_diario', None),
                            'percentual_limpeza_fina_diario': getattr(rdo, 'percentual_limpeza_fina_diario', None),
                            'percentual_limpeza_cumulativo': getattr(rdo, 'percentual_limpeza_cumulativo', None),
                            'percentual_limpeza_fina_cumulativo': getattr(rdo, 'percentual_limpeza_fina_cumulativo', None),
                            'avanco_limpeza': _clean_text(getattr(rdo, 'avanco_limpeza', None)),
                            'avanco_limpeza_fina': _clean_text(getattr(rdo, 'avanco_limpeza_fina', None)),
                            'compartimentos_avanco_json': getattr(rdo, 'compartimentos_avanco_json', None),
                            'compartimentos_cumulativo_json': _build_compartimentos_cumulativo_json(rdo),
                            'rdo_id': getattr(rdo, 'id', None),
                            'rdo_sequence': _extract_rdo_numeric_max(getattr(rdo, 'rdo', None)),
                            'rdo_data': rdo_date.isoformat() if rdo_date else None,
                        }
                    )
    except Exception:
        logger.exception('Falha ao montar lista de tanques no bootstrap mobile')

    limit_by_os_number = {}
    declared_tanks_by_os_number = {}
    try:
        for row in items:
            numero = _clean_text(row.get('numero_os'))
            if not numero or numero in limit_by_os_number:
                continue

            scoped_os = None
            source_ids = row.get('_source_os_ids') or set()
            try:
                scoped_ids = [int(raw_id) for raw_id in source_ids if raw_id is not None]
            except Exception:
                scoped_ids = []

            if scoped_ids:
                try:
                    scoped_os = (
                        OrdemServico.objects
                        .filter(id__in=scoped_ids)
                        .order_by('-data_inicio', '-id')
                        .first()
                    )
                except Exception:
                    scoped_os = None

            if scoped_os is None:
                try:
                    scoped_os = (
                        OrdemServico.objects
                        .filter(numero_os=numero)
                        .order_by('-data_inicio', '-id')
                        .first()
                    )
                except Exception:
                    scoped_os = None

            servicos_count = 0
            total_tanques_os = 0
            if scoped_os is not None:
                try:
                    servicos_count, _servicos_labels = _resolve_os_service_limit(scoped_os)
                except Exception:
                    servicos_count = 0
                try:
                    total_tanques_os, _tank_keys = _resolve_os_tank_progress(scoped_os)
                except Exception:
                    total_tanques_os = 0

            try:
                servicos_count = int(servicos_count or 0)
            except Exception:
                servicos_count = 0
            if servicos_count < 0:
                servicos_count = 0

            try:
                total_tanques_os = int(total_tanques_os or 0)
            except Exception:
                total_tanques_os = 0
            if total_tanques_os < 0:
                total_tanques_os = 0

            if not tank_by_os_number.get(numero):
                declared_tanks_by_os_number[numero] = _build_declared_os_tanks(scoped_os)

            limit_by_os_number[numero] = {
                'servicos_count': servicos_count,
                'max_tanques_servicos': (servicos_count if servicos_count > 0 else None),
                'total_tanques_os': total_tanques_os,
            }
    except Exception:
        logger.exception('Falha ao calcular limites de serviço/tanque no bootstrap mobile')

    atividade_choices = []
    try:
        seen_values = set()
        for raw in (getattr(RDO, 'ATIVIDADES_CHOICES', None) or []):
            if isinstance(raw, (list, tuple)) and len(raw) >= 2:
                value = _clean_text(raw[0])
                label = _clean_text(raw[1]) or value
            else:
                value = _clean_text(raw)
                label = value
            if not value:
                continue
            key = value.lower()
            if key in seen_values:
                continue
            seen_values.add(key)
            atividade_choices.append({'value': value, 'label': label})
    except Exception:
        logger.exception('Falha ao montar atividades_choices no bootstrap mobile')

    servico_choices = []
    try:
        seen_servico = set()
        for raw in (getattr(OrdemServico, 'SERVICO_CHOICES', None) or []):
            if isinstance(raw, (list, tuple)) and len(raw) >= 1:
                value = _clean_text(raw[0])
                label = _clean_text(raw[1]) if len(raw) >= 2 else value
            else:
                value = _clean_text(raw)
                label = value
            if not value:
                continue
            key = value.lower()
            if key in seen_servico:
                continue
            seen_servico.add(key)
            servico_choices.append({'value': value, 'label': label or value})
    except Exception:
        logger.exception('Falha ao montar servico_choices no bootstrap mobile')

    metodo_choices = []
    try:
        seen_metodo = set()
        for raw in (getattr(OrdemServico, 'METODO_CHOICES', None) or []):
            if isinstance(raw, (list, tuple)) and len(raw) >= 1:
                value = _clean_text(raw[0])
                label = _clean_text(raw[1]) if len(raw) >= 2 else value
            else:
                value = _clean_text(raw)
                label = value
            if not value:
                continue
            key = value.lower()
            if key in seen_metodo:
                continue
            seen_metodo.add(key)
            metodo_choices.append({'value': value, 'label': label or value})

        # Garante a opção Robotizada no app mobile supervisor.
        if not any(str(item.get('value') or '').strip().lower() == 'robotizada' for item in metodo_choices):
            metodo_choices.append({'value': 'Robotizada', 'label': 'Robotizada'})
    except Exception:
        logger.exception('Falha ao montar metodo_choices no bootstrap mobile')

    pessoas_choices = []
    try:
        seen_pessoas = set()
        for pessoa in Pessoa.objects.order_by('nome').all()[:2000]:
            nome = _clean_text(getattr(pessoa, 'nome', None))
            if not nome:
                continue
            key = nome.lower()
            if key in seen_pessoas:
                continue
            seen_pessoas.add(key)
            pessoas_choices.append({'value': nome, 'label': nome})
    except Exception:
        logger.exception('Falha ao montar pessoas_choices no bootstrap mobile')

    funcoes_choices = []
    try:
        seen_funcoes = set()
        for raw in (getattr(OrdemServico, 'FUNCOES', None) or []):
            value = ''
            label = ''
            if isinstance(raw, (list, tuple)) and len(raw) >= 1:
                value = _clean_text(raw[0])
                label = _clean_text(raw[1]) if len(raw) >= 2 else value
            else:
                value = _clean_text(raw)
                label = value
            if not value:
                continue
            key = value.lower()
            if key in seen_funcoes:
                continue
            seen_funcoes.add(key)
            funcoes_choices.append({'value': value, 'label': label or value})

        for funcao in Funcao.objects.order_by('nome').all()[:1200]:
            nome = _clean_text(getattr(funcao, 'nome', None))
            if not nome:
                continue
            key = nome.lower()
            if key in seen_funcoes:
                continue
            seen_funcoes.add(key)
            funcoes_choices.append({'value': nome, 'label': nome})
    except Exception:
        logger.exception('Falha ao montar funcoes_choices no bootstrap mobile')

    data = []
    for row in items[:300]:
        can_start = bool(primary_os and row.get('numero_os') == primary_os)
        if can_start:
            block_reason = ''
        else:
            block_reason = (
                f'Supervisor só pode iniciar uma OS por vez. Priorize a OS {primary_os}.'
                if primary_os
                else 'Não há OS liberada para iniciar RDO.'
            )

        row['can_start'] = can_start
        row['start_block_reason'] = block_reason
        row['tanks'] = (
            tank_by_os_number.get(row.get('numero_os'), [])
            or declared_tanks_by_os_number.get(_clean_text(row.get('numero_os')), [])
        )
        limits = limit_by_os_number.get(_clean_text(row.get('numero_os')), {})
        servicos_count = int(limits.get('servicos_count') or 0)
        row['servicos_count'] = servicos_count
        row['max_tanques_servicos'] = (
            limits.get('max_tanques_servicos')
            if servicos_count > 0
            else None
        )
        fallback_tank_total = len(row.get('tanks') or [])
        try:
            total_tanques_os = int(limits.get('total_tanques_os') or 0)
        except Exception:
            total_tanques_os = 0
        if total_tanques_os < fallback_tank_total:
            total_tanques_os = fallback_tank_total
        row['total_tanques_os'] = total_tanques_os
        row.pop('_is_in_progress', None)
        row.pop('_sort_date', None)
        row.pop('_source_os_ids', None)
        data.append(row)

    return JsonResponse(
        {
            'success': True,
            'count': len(data),
            'items': data,
            'atividade_choices': atividade_choices,
            'servico_choices': servico_choices,
            'metodo_choices': metodo_choices,
            'pessoas_choices': pessoas_choices,
            'funcoes_choices': funcoes_choices,
            'sentido_limpeza_choices': [
                {'value': 'vante > ré', 'label': 'Vante → Ré'},
                {'value': 'ré > vante', 'label': 'Ré → Vante'},
                {'value': 'bombordo > boreste', 'label': 'Bombordo → Boreste'},
                {'value': 'boreste < bombordo', 'label': 'Boreste ← Bombordo'},
            ],
            'pt_turnos_choices': [
                {'value': 'manha', 'label': 'Manhã'},
                {'value': 'tarde', 'label': 'Tarde'},
                {'value': 'noite', 'label': 'Noite'},
            ],
        }
    )


@csrf_exempt
@mobile_auth_required
@require_GET
def mobile_app_update(request):
    platform = str(request.GET.get('platform') or 'android').strip().lower()
    if platform not in {'android', 'ios'}:
        platform = 'android'

    discovered_android_release = None
    if platform == 'ios':
        download_url = (os.environ.get('MOBILE_APP_IOS_URL') or '').strip()
        version_name = (os.environ.get('MOBILE_APP_IOS_VERSION_NAME') or '').strip()
        build_number = _env_int('MOBILE_APP_IOS_BUILD_NUMBER', None)
        min_supported_build = _env_int('MOBILE_APP_IOS_MIN_SUPPORTED_BUILD', None)
        force_update = _env_bool('MOBILE_APP_IOS_FORCE_UPDATE', False)
        release_notes = (os.environ.get('MOBILE_APP_IOS_RELEASE_NOTES') or '').strip()
    else:
        auto_version_enabled = _env_bool('MOBILE_APP_ANDROID_AUTO_VERSION', True)
        if auto_version_enabled:
            discovered_android_release = _discover_android_release_metadata()

        download_url = (os.environ.get('MOBILE_APP_ANDROID_URL') or '').strip()
        version_name = (os.environ.get('MOBILE_APP_ANDROID_VERSION_NAME') or '').strip()
        build_number = _env_int('MOBILE_APP_ANDROID_BUILD_NUMBER', None)
        # Compatibilidade com nomenclaturas alternativas.
        if build_number is None:
            build_number = _env_int('MOBILE_APP_ANDROID_VERSION_CODE', None)
        min_supported_build = _env_int('MOBILE_APP_ANDROID_MIN_SUPPORTED_BUILD', None)
        force_update = _env_bool('MOBILE_APP_ANDROID_FORCE_UPDATE', False)
        release_notes = (os.environ.get('MOBILE_APP_ANDROID_RELEASE_NOTES') or '').strip()

        discovered_build = _extract_build_number(
            (discovered_android_release or {}).get('build_number'),
            (discovered_android_release or {}).get('version_name'),
        )
        discovered_version_name = str(
            (discovered_android_release or {}).get('version_name') or ''
        ).strip()

        if discovered_build is not None:
            if build_number is None or int(discovered_build) >= int(build_number):
                build_number = int(discovered_build)
                if discovered_version_name:
                    version_name = discovered_version_name
        elif not version_name and discovered_version_name:
            version_name = discovered_version_name

        discovered_path = str(
            (discovered_android_release or {}).get('apk_path') or ''
        ).strip()
        if discovered_path:
            discovered_download_url = _android_release_download_url(request, discovered_path)
            points_to_latest_alias = str(download_url or '').strip().endswith(
                '/static/mobile/releases/ambipar-synchro-latest.apk'
            )
            if not download_url or (auto_version_enabled and points_to_latest_alias):
                download_url = discovered_download_url

    if not version_name:
        version_name = _extract_version_name_from_url(download_url)

    if build_number is None:
        build_number = _extract_build_number(version_name, download_url)

    if build_number is None:
        build_number = 0

    download_enabled = _env_bool('MOBILE_APP_DOWNLOAD_ENABLED', False) or bool(download_url)
    has_package = bool(download_enabled and download_url)

    response_payload = {
        'success': True,
        'platform': platform,
        'checked_at': timezone.now().isoformat(),
        'update': {
            'available': has_package,
            'download_url': download_url,
            'version_name': version_name,
            'build_number': int(build_number or 0),
            'min_supported_build': min_supported_build,
            'force_update': bool(force_update),
            'release_notes': release_notes,
        },
    }
    return JsonResponse(response_payload, status=200)


@csrf_exempt
@mobile_auth_required
@require_POST
def mobile_translate_preview(request):
    body, parse_error = _parse_json_body(request)
    if parse_error:
        return JsonResponse(
            {'success': False, 'en': '', 'error': parse_error},
            status=400,
        )

    text = str(body.get('text') or '').strip()
    if len(text) < 3:
        return JsonResponse({'success': True, 'en': ''}, status=200)

    try:
        from deep_translator import GoogleTranslator

        translated = GoogleTranslator(source='pt', target='en').translate(text)
        return JsonResponse(
            {
                'success': True,
                'en': str(translated or '').strip(),
            },
            status=200,
        )
    except Exception:
        logger.exception('Erro ao traduzir texto no mobile_translate_preview')
        return JsonResponse(
            {'success': False, 'en': '', 'error': 'Falha tradução'},
            status=200,
        )


@csrf_exempt
@mobile_auth_required
@require_GET
def mobile_rdo_page(request, rdo_id):
    try:
        rdo_obj = RDO.objects.select_related('ordem_servico').only(
            'id', 'ordem_servico__supervisor_id'
        ).get(pk=rdo_id)
    except RDO.DoesNotExist:
        return HttpResponse(
            'RDO não encontrado.',
            status=404,
            content_type='text/plain; charset=utf-8',
        )

    try:
        ordem = getattr(rdo_obj, 'ordem_servico', None)
        if ordem is None or getattr(ordem, 'supervisor', None) != request.user:
            return HttpResponse(
                'Sem permissão para visualizar este RDO.',
                status=403,
                content_type='text/plain; charset=utf-8',
            )
    except Exception:
        return HttpResponse(
            'Sem permissão para visualizar este RDO.',
            status=403,
            content_type='text/plain; charset=utf-8',
        )

    context = _build_rdo_page_context(request, rdo_id)
    return render(request, 'rdo_page.html', context)


@csrf_exempt
@mobile_auth_required
@require_GET
def mobile_os_rdos(request, os_id):
    def _normalize_os_number(value):
        raw = str(value or '').strip()
        if not raw:
            return ''
        digits = ''.join(ch for ch in raw if ch.isdigit())
        if digits:
            try:
                return str(int(digits))
            except Exception:
                cleaned = digits.lstrip('0')
                return cleaned or '0'
        parsed = _coerce_int(raw)
        if parsed is not None:
            return str(parsed)
        return raw

    requested_numero = _normalize_os_number(request.GET.get('numero_os'))
    os_numbers = set()
    if requested_numero:
        os_numbers.add(requested_numero)

    primary_os_id = _coerce_int(os_id) or 0
    if primary_os_id > 0:
        try:
            os_obj = OrdemServico.objects.filter(pk=primary_os_id).only(
                'id', 'numero_os'
            ).first()
        except Exception:
            os_obj = None
        if os_obj is not None:
            normalized = _normalize_os_number(getattr(os_obj, 'numero_os', None))
            if normalized:
                os_numbers.add(normalized)

    lookup_numbers = []
    for item in os_numbers:
        parsed = _coerce_int(item)
        if parsed is not None:
            lookup_numbers.append(parsed)

    if not lookup_numbers:
        return JsonResponse({'success': False, 'error': 'OS não encontrada.'}, status=404)

    try:
        os_qs = OrdemServico.objects.filter(numero_os__in=lookup_numbers)
        os_qs = os_qs.filter(supervisor=request.user)
        os_rows = list(os_qs.only('id', 'numero_os'))
    except Exception:
        os_rows = []

    os_ids = [int(getattr(row, 'id', 0) or 0) for row in os_rows if int(getattr(row, 'id', 0) or 0) > 0]
    if not os_ids:
        return JsonResponse(
            {
                'success': True,
                'os': {'id': primary_os_id or None, 'numero_os': requested_numero},
                'rdos': [],
            },
            status=200,
        )

    try:
        rdo_qs = list(
            RDO.objects.filter(ordem_servico_id__in=os_ids)
            .select_related('ordem_servico')
            .prefetch_related('membros_equipe__pessoa')
        )
    except Exception:
        rdo_qs = []

    def _rdo_sort_key(obj):
        rdo_num = _coerce_int(getattr(obj, 'rdo', None))
        dt_val = getattr(obj, 'data', None) or getattr(obj, 'data_inicio', None)
        try:
            dt_key = dt_val.isoformat() if dt_val is not None else ''
        except Exception:
            dt_key = str(dt_val or '')
        return (
            0 if rdo_num is not None else 1,
            rdo_num or 0,
            dt_key,
            int(getattr(obj, 'id', 0) or 0),
        )

    try:
        rdo_qs.sort(key=_rdo_sort_key)
    except Exception:
        pass

    rdos_payload = []
    for rdo_obj in rdo_qs:
        limited_payload = _build_supervisor_limited_rdo_payload(rdo_obj)
        dt_val = getattr(rdo_obj, 'data', None) or getattr(rdo_obj, 'data_inicio', None)
        try:
            dt_str = dt_val.isoformat() if dt_val is not None else ''
        except Exception:
            dt_str = str(dt_val or '')

        os_obj = getattr(rdo_obj, 'ordem_servico', None)
        numero_os = _normalize_os_number(getattr(os_obj, 'numero_os', None))
        rdos_payload.append(
                {
                    'id': getattr(rdo_obj, 'id', None),
                    'rdo': getattr(rdo_obj, 'rdo', None),
                    'data': dt_str,
                    'data_inicio': limited_payload.get('data_inicio'),
                    'os_id': getattr(os_obj, 'id', None) if os_obj else None,
                    'numero_os': numero_os,
                    'equipe': limited_payload.get('equipe') or [],
                    'pob': limited_payload.get('pob'),
                    'can_edit': True,
                }
            )

    primary_numero = requested_numero
    if not primary_numero and os_rows:
        primary_numero = _normalize_os_number(getattr(os_rows[0], 'numero_os', None))

    return JsonResponse(
        {
            'success': True,
            'os': {'id': primary_os_id or None, 'numero_os': primary_numero},
            'rdos': rdos_payload,
        },
        status=200,
    )


@csrf_exempt
@mobile_auth_required
@require_POST
def mobile_rdo_supervisor_edit(request, rdo_id):
    payload = _extract_mobile_request_payload(request)
    if not isinstance(payload, dict):
        payload = {}

    payload = dict(payload)
    payload['rdo_id'] = str(rdo_id)

    request_for_view = _build_internal_post_request(request, payload)
    return update_rdo_ajax(request_for_view)


@csrf_exempt
@mobile_auth_required
@require_GET
def mobile_rdo_sync_status(request):
    client_uuid = str(request.GET.get('client_uuid') or '').strip()
    if not client_uuid:
        return JsonResponse({'success': False, 'error': 'client_uuid é obrigatório.'}, status=400)

    item = MobileSyncEvent.objects.filter(client_uuid=client_uuid, user=request.user).first()
    if not item:
        return JsonResponse({'success': False, 'error': 'Evento não encontrado.'}, status=404)

    return JsonResponse(
        {
            'success': item.state == MobileSyncEvent.STATE_DONE,
            'found': True,
            'client_uuid': item.client_uuid,
            'operation': item.operation,
            'state': item.state,
            'http_status': int(item.http_status or 0),
            'error_message': item.error_message,
            'result': item.response_payload or {},
            'idempotent': True,
        },
        status=int(item.http_status or 200),
    )


@csrf_exempt
@mobile_auth_required
@require_POST
def mobile_rdo_sync(request):
    body, parse_error = _parse_json_body(request)
    if parse_error:
        return JsonResponse({'success': False, 'error': parse_error}, status=400)

    client_uuid = str(body.get('client_uuid') or '').strip()
    operation = str(body.get('operation') or '').strip()
    payload = body.get('payload') or {}

    if not client_uuid:
        return JsonResponse({'success': False, 'error': 'client_uuid é obrigatório.'}, status=400)
    if not operation:
        return JsonResponse({'success': False, 'error': 'operation é obrigatória.'}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({'success': False, 'error': 'payload deve ser um objeto JSON.'}, status=400)

    sync_result = _execute_sync_operation(request, client_uuid, operation, payload)
    status_code = int(sync_result.get('http_status') or 200)
    return JsonResponse(sync_result, status=status_code)


@csrf_exempt
@mobile_auth_required
@require_POST
def mobile_rdo_sync_batch(request):
    body, parse_error = _parse_json_body(request)
    if parse_error:
        return JsonResponse({'success': False, 'error': parse_error}, status=400)

    raw_items = body.get('items')
    if not isinstance(raw_items, list) or not raw_items:
        return JsonResponse({'success': False, 'error': 'items deve ser uma lista não vazia.'}, status=400)
    if len(raw_items) > 500:
        return JsonResponse({'success': False, 'error': 'items excede o limite máximo de 500 por lote.'}, status=400)

    stop_on_error_raw = body.get('stop_on_error')
    stop_on_error = True if stop_on_error_raw is None else bool(stop_on_error_raw)

    alias_to_entity_id = {}
    status_by_uuid = {}
    status_by_alias = {}

    results = []
    executed_count = 0
    first_failure_index = None

    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            item_result = {
                'index': index,
                'success': False,
                'blocked': False,
                'idempotent': False,
                'state': MobileSyncEvent.STATE_ERROR,
                'http_status': 400,
                'error_message': 'Item do lote inválido (esperado objeto JSON).',
                'client_uuid': '',
                'operation': '',
                'depends_on': [],
                'entity_alias': None,
                'entity_id': None,
                'result': {},
            }
            results.append(item_result)
            if stop_on_error:
                first_failure_index = index
                break
            continue

        client_uuid = str(item.get('client_uuid') or '').strip()
        operation = str(item.get('operation') or '').strip()
        payload = item.get('payload') or {}
        entity_alias = str(item.get('entity_alias') or '').strip() or None
        depends_on = item.get('depends_on') or []

        if not isinstance(depends_on, list):
            depends_on = [depends_on]

        if not client_uuid:
            item_result = {
                'index': index,
                'success': False,
                'blocked': False,
                'idempotent': False,
                'state': MobileSyncEvent.STATE_ERROR,
                'http_status': 400,
                'error_message': 'client_uuid é obrigatório.',
                'client_uuid': client_uuid,
                'operation': operation,
                'depends_on': depends_on,
                'entity_alias': entity_alias,
                'entity_id': None,
                'result': {},
            }
            results.append(item_result)
            if entity_alias:
                status_by_alias[entity_alias] = False
            if stop_on_error:
                first_failure_index = index
                break
            continue

        if not operation:
            item_result = {
                'index': index,
                'success': False,
                'blocked': False,
                'idempotent': False,
                'state': MobileSyncEvent.STATE_ERROR,
                'http_status': 400,
                'error_message': 'operation é obrigatória.',
                'client_uuid': client_uuid,
                'operation': operation,
                'depends_on': depends_on,
                'entity_alias': entity_alias,
                'entity_id': None,
                'result': {},
            }
            results.append(item_result)
            status_by_uuid[client_uuid] = False
            if entity_alias:
                status_by_alias[entity_alias] = False
            if stop_on_error:
                first_failure_index = index
                break
            continue

        if not isinstance(payload, dict):
            item_result = {
                'index': index,
                'success': False,
                'blocked': False,
                'idempotent': False,
                'state': MobileSyncEvent.STATE_ERROR,
                'http_status': 400,
                'error_message': 'payload deve ser um objeto JSON.',
                'client_uuid': client_uuid,
                'operation': operation,
                'depends_on': depends_on,
                'entity_alias': entity_alias,
                'entity_id': None,
                'result': {},
            }
            results.append(item_result)
            status_by_uuid[client_uuid] = False
            if entity_alias:
                status_by_alias[entity_alias] = False
            if stop_on_error:
                first_failure_index = index
                break
            continue

        missing_deps, failed_deps = _evaluate_dependencies(depends_on, status_by_uuid, status_by_alias)
        if missing_deps or failed_deps:
            reason_parts = []
            if missing_deps:
                reason_parts.append('dependências ausentes: ' + ', '.join(missing_deps))
            if failed_deps:
                reason_parts.append('dependências com falha: ' + ', '.join(failed_deps))
            item_result = {
                'index': index,
                'success': False,
                'blocked': True,
                'idempotent': False,
                'state': 'blocked',
                'http_status': 424,
                'error_message': '; '.join(reason_parts) or 'Dependências não atendidas.',
                'client_uuid': client_uuid,
                'operation': operation,
                'depends_on': depends_on,
                'entity_alias': entity_alias,
                'entity_id': None,
                'result': {},
            }
            results.append(item_result)
            status_by_uuid[client_uuid] = False
            if entity_alias:
                status_by_alias[entity_alias] = False
            if stop_on_error:
                first_failure_index = index
                break
            continue

        resolved_payload, unresolved_refs = _resolve_payload_refs(payload, alias_to_entity_id)
        if unresolved_refs:
            item_result = {
                'index': index,
                'success': False,
                'blocked': False,
                'idempotent': False,
                'state': MobileSyncEvent.STATE_ERROR,
                'http_status': 400,
                'error_message': 'Referências não resolvidas: ' + ', '.join(unresolved_refs),
                'client_uuid': client_uuid,
                'operation': operation,
                'depends_on': depends_on,
                'entity_alias': entity_alias,
                'entity_id': None,
                'result': {},
            }
            results.append(item_result)
            status_by_uuid[client_uuid] = False
            if entity_alias:
                status_by_alias[entity_alias] = False
            if stop_on_error:
                first_failure_index = index
                break
            continue

        sync_result = _execute_sync_operation(request, client_uuid, operation, resolved_payload)
        executed_count += 1

        response_payload = sync_result.get('result') if isinstance(sync_result.get('result'), dict) else {}
        entity_id = _extract_entity_id(operation, resolved_payload, response_payload)
        if entity_alias and entity_id is not None:
            alias_to_entity_id[entity_alias] = entity_id

        item_result = {
            'index': index,
            'success': bool(sync_result.get('success')),
            'blocked': False,
            'idempotent': bool(sync_result.get('idempotent')),
            'state': sync_result.get('state'),
            'http_status': int(sync_result.get('http_status') or 200),
            'error_message': sync_result.get('error_message'),
            'client_uuid': client_uuid,
            'operation': operation,
            'depends_on': depends_on,
            'entity_alias': entity_alias,
            'entity_id': entity_id,
            'result': response_payload,
        }
        results.append(item_result)

        status_by_uuid[client_uuid] = bool(item_result.get('success'))
        if entity_alias:
            status_by_alias[entity_alias] = bool(item_result.get('success'))

        if stop_on_error and not bool(item_result.get('success')):
            first_failure_index = index
            break

    if first_failure_index is not None and first_failure_index + 1 < len(raw_items):
        for index in range(first_failure_index + 1, len(raw_items)):
            raw_item = raw_items[index]
            client_uuid = ''
            operation = ''
            entity_alias = None
            depends_on = []
            if isinstance(raw_item, dict):
                client_uuid = str(raw_item.get('client_uuid') or '').strip()
                operation = str(raw_item.get('operation') or '').strip()
                entity_alias = str(raw_item.get('entity_alias') or '').strip() or None
                deps = raw_item.get('depends_on') or []
                depends_on = deps if isinstance(deps, list) else [deps]
            results.append(
                {
                    'index': index,
                    'success': False,
                    'blocked': True,
                    'idempotent': False,
                    'state': 'blocked',
                    'http_status': 424,
                    'error_message': 'Item não executado: lote interrompido por stop_on_error.',
                    'client_uuid': client_uuid,
                    'operation': operation,
                    'depends_on': depends_on,
                    'entity_alias': entity_alias,
                    'entity_id': None,
                    'result': {},
                }
            )

    success_count = len([r for r in results if bool(r.get('success'))])
    error_count = len([r for r in results if not bool(r.get('success')) and not bool(r.get('blocked'))])
    blocked_count = len([r for r in results if bool(r.get('blocked'))])
    idempotent_count = len([r for r in results if bool(r.get('idempotent'))])
    overall_success = error_count == 0 and blocked_count == 0 and success_count == len(results)

    return JsonResponse(
        {
            'success': overall_success,
            'stop_on_error': stop_on_error,
            'requested_count': len(raw_items),
            'result_count': len(results),
            'executed_count': executed_count,
            'success_count': success_count,
            'error_count': error_count,
            'blocked_count': blocked_count,
            'idempotent_count': idempotent_count,
            'id_map': alias_to_entity_id,
            'items': results,
        },
        status=200,
    )


@csrf_exempt
@mobile_auth_required
@require_POST
def mobile_rdo_photo_upload(request):
    client_uuid = str(request.POST.get('client_uuid') or '').strip()
    if not client_uuid:
        return JsonResponse({'success': False, 'error': 'client_uuid é obrigatório.'}, status=400)

    rdo_id_raw = str(request.POST.get('rdo_id') or '').strip()
    try:
        rdo_id = int(rdo_id_raw)
    except Exception:
        return JsonResponse({'success': False, 'error': 'rdo_id inválido.'}, status=400)
    try:
        rdo_obj = RDO.objects.select_related('ordem_servico').get(pk=rdo_id)
    except RDO.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'RDO não encontrado.'}, status=404)
    try:
        ordem = getattr(rdo_obj, 'ordem_servico', None)
        if ordem is not None and getattr(ordem, 'supervisor', None) != request.user:
            return JsonResponse({'success': False, 'error': 'Sem permissão para anexar foto neste RDO.'}, status=403)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Sem permissão para anexar foto neste RDO.'}, status=403)

    photo_obj = None
    try:
        photo_obj = request.FILES.get('fotos') or request.FILES.get('foto')
    except Exception:
        photo_obj = None

    if photo_obj is None:
        try:
            candidate = request.FILES.getlist('fotos') if hasattr(request.FILES, 'getlist') else []
            if candidate:
                photo_obj = candidate[0]
        except Exception:
            photo_obj = None

    if photo_obj is None:
        return JsonResponse({'success': False, 'error': 'Arquivo de foto não enviado.'}, status=400)

    existing = MobileSyncEvent.objects.filter(client_uuid=client_uuid, user=request.user).first()
    if existing is not None:
        return JsonResponse(_sync_replay_response(existing), status=int(existing.http_status or 200))

    try:
        with transaction.atomic():
            event = MobileSyncEvent.objects.create(
                client_uuid=client_uuid,
                operation='rdo.photo.upload',
                user=getattr(request, 'user', None),
                request_payload={
                    'payload': {
                        'rdo_id': rdo_id,
                        'filename': getattr(photo_obj, 'name', None),
                        'size': getattr(photo_obj, 'size', None),
                    }
                },
                state=MobileSyncEvent.STATE_PROCESSING,
                http_status=202,
            )
    except IntegrityError:
        existing = MobileSyncEvent.objects.filter(client_uuid=client_uuid, user=request.user).first()
        if existing is None:
            return JsonResponse({'success': False, 'error': 'Falha de concorrência na idempotência.'}, status=409)
        return JsonResponse(_sync_replay_response(existing), status=int(existing.http_status or 200))

    try:
        internal_request = _build_internal_photo_request(request, photo_obj)
        internal_response = upload_rdo_photos(internal_request, rdo_id)
        status_code, response_payload = _response_to_json(internal_response)
        status_code = int(status_code or 200)

        success = bool(200 <= status_code < 300)
        if isinstance(response_payload, dict) and 'success' in response_payload:
            success = success and bool(response_payload.get('success'))

        event.state = MobileSyncEvent.STATE_DONE if success else MobileSyncEvent.STATE_ERROR
        event.http_status = status_code
        event.response_payload = response_payload
        event.error_message = None if success else (
            (response_payload.get('error') if isinstance(response_payload, dict) else None)
            or f'Upload retornou status {status_code}.'
        )
        event.processed_at = timezone.now()
        event.save(
            update_fields=[
                'state',
                'http_status',
                'response_payload',
                'error_message',
                'processed_at',
                'updated_at',
            ]
        )

        return JsonResponse(
            {
                'success': success,
                'idempotent': False,
                'client_uuid': client_uuid,
                'operation': 'rdo.photo.upload',
                'state': event.state,
                'result': response_payload,
                'error_message': event.error_message,
            },
            status=status_code,
        )
    except Exception as exc:
        logger.exception('Erro ao processar upload mobile de foto client_uuid=%s', client_uuid)
        event.state = MobileSyncEvent.STATE_ERROR
        event.http_status = 500
        event.response_payload = {'success': False, 'error': 'Erro interno no upload mobile de foto.'}
        event.error_message = str(exc)
        event.processed_at = timezone.now()
        event.save(
            update_fields=[
                'state',
                'http_status',
                'response_payload',
                'error_message',
                'processed_at',
                'updated_at',
            ]
        )
        return JsonResponse(
            {
                'success': False,
                'idempotent': False,
                'client_uuid': client_uuid,
                'operation': 'rdo.photo.upload',
                'state': event.state,
                'error_message': event.error_message,
            },
            status=500,
        )
