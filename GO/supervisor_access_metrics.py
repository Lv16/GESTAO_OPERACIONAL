from collections import defaultdict
from datetime import datetime, timedelta, time as dt_time

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db.models import Max, Q
from django.utils import timezone

from .models import MobileApiToken, MobileSyncEvent, RDOChannelEvent, SupervisorAccessHeartbeat
from .rdo_access import SUPERVISOR_GROUP_NAME


ACCESS_WINDOW_MINUTES = 5
ONLINE_LOOKBACK_MINUTES = 15
DEFAULT_RANGE_DAYS = 30
ALLOWED_RANGE_DAYS = (7, 15, 30, 60, 90)
DISPLAY_TIMEZONE = ZoneInfo('America/Sao_Paulo')


def is_supervisor_user(user):
    try:
        if user is None or not getattr(user, 'is_authenticated', False):
            return False
        if not getattr(user, 'is_active', False):
            return False
        return bool(user.groups.filter(name=SUPERVISOR_GROUP_NAME).exists())
    except Exception:
        return False


def localize_metric_datetime(value):
    if value is None:
        return None
    try:
        return timezone.localtime(value, DISPLAY_TIMEZONE)
    except Exception:
        return value


def floor_access_window(moment=None):
    base = moment or timezone.now()
    local_base = localize_metric_datetime(base)
    minute_bucket = (int(local_base.minute) // ACCESS_WINDOW_MINUTES) * ACCESS_WINDOW_MINUTES
    floored = local_base.replace(minute=minute_bucket, second=0, microsecond=0)
    return floored


def record_supervisor_access(
    *,
    user,
    channel,
    path='',
    session_key='',
    device_name='',
    platform='',
    moment=None,
):
    if not is_supervisor_user(user):
        return None

    normalized_channel = str(channel or '').strip().lower()
    if normalized_channel not in {
        SupervisorAccessHeartbeat.CHANNEL_WEB,
        SupervisorAccessHeartbeat.CHANNEL_MOBILE,
    }:
        return None

    window_start = floor_access_window(moment)
    defaults = {
        'path': str(path or '')[:255] or None,
        'session_key': str(session_key or '')[:64] or None,
        'device_name': str(device_name or '')[:120] or None,
        'platform': str(platform or '')[:30] or None,
    }

    try:
        heartbeat, _ = SupervisorAccessHeartbeat.objects.get_or_create(
            user=user,
            channel=normalized_channel,
            window_start=window_start,
            defaults=defaults,
        )
        return heartbeat
    except IntegrityError:
        try:
            return SupervisorAccessHeartbeat.objects.filter(
                user=user,
                channel=normalized_channel,
                window_start=window_start,
            ).first()
        except Exception:
            return None
    except Exception:
        return None


def parse_access_dashboard_range(request):
    today_local = localize_metric_datetime(timezone.now()).date()

    try:
        selected_days = int(str(request.GET.get('days') or DEFAULT_RANGE_DAYS).strip())
    except Exception:
        selected_days = DEFAULT_RANGE_DAYS
    if selected_days not in ALLOWED_RANGE_DAYS:
        selected_days = DEFAULT_RANGE_DAYS

    raw_date_from = str(request.GET.get('date_from') or '').strip()
    raw_date_to = str(request.GET.get('date_to') or '').strip()

    parsed_from = None
    parsed_to = None
    try:
        if raw_date_from:
            parsed_from = datetime.strptime(raw_date_from, '%Y-%m-%d').date()
    except Exception:
        parsed_from = None
    try:
        if raw_date_to:
            parsed_to = datetime.strptime(raw_date_to, '%Y-%m-%d').date()
    except Exception:
        parsed_to = None

    date_to = parsed_to or today_local
    date_from = parsed_from or (date_to - timedelta(days=selected_days - 1))
    if date_from > date_to:
        date_from, date_to = date_to, date_from

    start_at = timezone.make_aware(
        datetime.combine(date_from, dt_time.min),
        DISPLAY_TIMEZONE,
    )
    end_at = timezone.make_aware(
        datetime.combine(date_to, dt_time.max),
        DISPLAY_TIMEZONE,
    )

    return {
        'date_from': date_from,
        'date_to': date_to,
        'start_at': start_at,
        'end_at': end_at,
        'selected_days': selected_days,
        'day_options': ALLOWED_RANGE_DAYS,
    }


def _build_channel_hour_rows(day_hour_users, date_from, date_to):
    day_count = max(1, (date_to - date_from).days + 1)
    rows = []
    for hour in range(24):
        total = 0
        max_count = 0
        active_days = 0
        for day_offset in range(day_count):
            current_date = date_from + timedelta(days=day_offset)
            user_count = len(day_hour_users.get((current_date, hour), set()))
            total += user_count
            if user_count > 0:
                active_days += 1
            if user_count > max_count:
                max_count = user_count
        average = round(total / day_count, 2)
        rows.append(
            {
                'hour': hour,
                'label': f'{hour:02d}:00',
                'average': average,
                'max_count': max_count,
                'active_days': active_days,
            }
        )

    max_average = max((row['average'] for row in rows), default=0)
    for row in rows:
        row['intensity'] = 0 if max_average <= 0 else round((row['average'] / max_average) * 100)

    peak_row = None
    if max_average > 0:
        peak_row = max(
            rows,
            key=lambda item: (item['average'], item['max_count'], -item['hour']),
            default=None,
        )
    return rows, peak_row


def _percent(part, total):
    if not total:
        return 0
    return round((float(part) / float(total)) * 100, 1)


def detect_request_channel(request):
    explicit = str(getattr(request, 'rdo_request_channel', '') or '').strip().lower()
    if explicit in {
        SupervisorAccessHeartbeat.CHANNEL_WEB,
        SupervisorAccessHeartbeat.CHANNEL_MOBILE,
    }:
        return explicit

    if getattr(request, 'mobile_api_token', None) is not None:
        return SupervisorAccessHeartbeat.CHANNEL_MOBILE

    path = str(getattr(request, 'path', '') or '').strip().lower()
    if path.startswith('/api/mobile/'):
        return SupervisorAccessHeartbeat.CHANNEL_MOBILE

    return SupervisorAccessHeartbeat.CHANNEL_WEB


def record_rdo_channel_event(*, request, rdo_obj, event_type, user=None):
    normalized_event_type = str(event_type or '').strip().lower()
    if normalized_event_type not in {
        RDOChannelEvent.EVENT_CREATE,
        RDOChannelEvent.EVENT_UPDATE,
    }:
        return None

    if rdo_obj is None or not getattr(rdo_obj, 'pk', None):
        return None

    event_user = user or getattr(request, 'user', None)
    if not is_supervisor_user(event_user):
        return None

    try:
        return RDOChannelEvent.objects.create(
            user=event_user,
            rdo=rdo_obj,
            ordem_servico=getattr(rdo_obj, 'ordem_servico', None),
            channel=detect_request_channel(request),
            event_type=normalized_event_type,
            source_path=str(getattr(request, 'path', '') or '')[:255] or None,
        )
    except Exception:
        return None


def _coerce_int(value):
    try:
        if value in (None, ''):
            return None
        return int(str(value).strip())
    except Exception:
        return None


def _extract_rdo_id_from_mapping(payload):
    if not isinstance(payload, dict):
        return None

    for key in ('rdo_id', 'id', 'pk'):
        found = _coerce_int(payload.get(key))
        if found is not None:
            return found

    for key in ('rdo', 'result', 'payload', 'response'):
        found = _extract_rdo_id_from_mapping(payload.get(key))
        if found is not None:
            return found

    return None


def _update_rdo_ranking_bucket(bucket, *, user_id, event_type, rdo_id, occurred_at):
    if user_id in (None, '') or rdo_id in (None, ''):
        return

    row = bucket.setdefault(
        user_id,
        {
            'rdo_ids': set(),
            'created_ids': set(),
            'updated_ids': set(),
            'last_at': None,
        },
    )
    row['rdo_ids'].add(rdo_id)
    if event_type == RDOChannelEvent.EVENT_CREATE:
        row['created_ids'].add(rdo_id)
    elif event_type == RDOChannelEvent.EVENT_UPDATE:
        row['updated_ids'].add(rdo_id)

    if occurred_at and (row['last_at'] is None or occurred_at > row['last_at']):
        row['last_at'] = occurred_at


def _build_rdo_ranking_rows(bucket, supervisor_lookup, limit=8):
    rows = []
    for user_id, stats in bucket.items():
        user_meta = supervisor_lookup.get(user_id) or {}
        rows.append(
            {
                'user_id': user_id,
                'username': user_meta.get('username') or '-',
                'full_name': user_meta.get('full_name') or '',
                'total_rdos': len(stats.get('rdo_ids') or ()),
                'created_rdos': len(stats.get('created_ids') or ()),
                'updated_rdos': len(stats.get('updated_ids') or ()),
                'last_at': localize_metric_datetime(stats.get('last_at')),
            }
        )

    rows.sort(
        key=lambda row: (
            -int(row.get('total_rdos') or 0),
            -int(row.get('created_rdos') or 0),
            -int(row.get('updated_rdos') or 0),
            row.get('full_name') or row.get('username') or '',
        )
    )

    for index, row in enumerate(rows, start=1):
        row['position'] = index

    try:
        limit = max(1, int(limit or 8))
    except Exception:
        limit = 8
    return rows[:limit]


def build_supervisor_access_dashboard_context(request):
    range_info = parse_access_dashboard_range(request)
    date_from = range_info['date_from']
    date_to = range_info['date_to']
    start_at = range_info['start_at']
    end_at = range_info['end_at']

    UserModel = get_user_model()
    supervisors_qs = (
        UserModel.objects.filter(groups__name=SUPERVISOR_GROUP_NAME, is_active=True)
        .distinct()
        .order_by('username', 'id')
    )
    total_supervisors = supervisors_qs.count()
    supervisor_lookup = {
        user.id: {
            'username': user.username,
            'full_name': (user.get_full_name() or '').strip(),
        }
        for user in supervisors_qs
    }

    heartbeat_qs = SupervisorAccessHeartbeat.objects.filter(
        user__in=supervisors_qs,
        window_start__gte=start_at,
        window_start__lte=end_at,
    ).select_related('user')

    web_user_ids = set(
        heartbeat_qs.filter(channel=SupervisorAccessHeartbeat.CHANNEL_WEB)
        .values_list('user_id', flat=True)
        .distinct()
    )
    mobile_user_ids = set(
        heartbeat_qs.filter(channel=SupervisorAccessHeartbeat.CHANNEL_MOBILE)
        .values_list('user_id', flat=True)
        .distinct()
    )

    token_mobile_user_ids = set(
        MobileApiToken.objects.filter(
            user__in=supervisors_qs,
            last_used_at__gte=start_at,
            last_used_at__lte=end_at,
        )
        .values_list('user_id', flat=True)
        .distinct()
    )
    login_web_user_ids = set(
        supervisors_qs.filter(
            last_login__gte=start_at,
            last_login__lte=end_at,
        ).values_list('id', flat=True)
    )
    web_user_ids |= login_web_user_ids
    mobile_user_ids |= token_mobile_user_ids

    online_cutoff = timezone.now() - timedelta(minutes=ONLINE_LOOKBACK_MINUTES)
    web_online_ids = set(
        SupervisorAccessHeartbeat.objects.filter(
            user__in=supervisors_qs,
            channel=SupervisorAccessHeartbeat.CHANNEL_WEB,
            window_start__gte=online_cutoff,
        )
        .values_list('user_id', flat=True)
        .distinct()
    )
    web_online_ids |= set(
        supervisors_qs.filter(last_login__gte=online_cutoff).values_list('id', flat=True)
    )
    mobile_online_ids = set(
        SupervisorAccessHeartbeat.objects.filter(
            user__in=supervisors_qs,
            channel=SupervisorAccessHeartbeat.CHANNEL_MOBILE,
            window_start__gte=online_cutoff,
        )
        .values_list('user_id', flat=True)
        .distinct()
    )
    mobile_online_ids |= set(
        MobileApiToken.objects.filter(
            user__in=supervisors_qs,
            is_active=True,
            last_used_at__gte=online_cutoff,
        )
        .values_list('user_id', flat=True)
        .distinct()
    )

    grouped_users = {
        SupervisorAccessHeartbeat.CHANNEL_WEB: defaultdict(set),
        SupervisorAccessHeartbeat.CHANNEL_MOBILE: defaultdict(set),
    }
    for channel, window_start, user_id in heartbeat_qs.values_list('channel', 'window_start', 'user_id'):
        local_dt = localize_metric_datetime(window_start)
        grouped_users[channel][(local_dt.date(), local_dt.hour)].add(user_id)

    web_login_hour_qs = supervisors_qs.filter(
        last_login__gte=start_at,
        last_login__lte=end_at,
    ).values_list('last_login', 'id')
    for last_login_at, user_id in web_login_hour_qs:
        local_dt = localize_metric_datetime(last_login_at)
        if local_dt is None:
            continue
        grouped_users[SupervisorAccessHeartbeat.CHANNEL_WEB][(local_dt.date(), local_dt.hour)].add(user_id)

    token_hour_qs = MobileApiToken.objects.filter(
        user__in=supervisors_qs,
        last_used_at__gte=start_at,
        last_used_at__lte=end_at,
    ).values_list('last_used_at', 'user_id')
    for last_used_at, user_id in token_hour_qs:
        local_dt = localize_metric_datetime(last_used_at)
        if local_dt is None:
            continue
        grouped_users[SupervisorAccessHeartbeat.CHANNEL_MOBILE][(local_dt.date(), local_dt.hour)].add(user_id)

    web_hour_rows, web_peak_row = _build_channel_hour_rows(
        grouped_users[SupervisorAccessHeartbeat.CHANNEL_WEB],
        date_from,
        date_to,
    )
    mobile_hour_rows, mobile_peak_row = _build_channel_hour_rows(
        grouped_users[SupervisorAccessHeartbeat.CHANNEL_MOBILE],
        date_from,
        date_to,
    )

    supervisor_rows = []
    annotated_supervisors = supervisors_qs.annotate(
        last_web_at=Max(
            'supervisor_access_heartbeats__window_start',
            filter=Q(supervisor_access_heartbeats__channel=SupervisorAccessHeartbeat.CHANNEL_WEB),
        ),
        last_mobile_at=Max(
            'supervisor_access_heartbeats__window_start',
            filter=Q(supervisor_access_heartbeats__channel=SupervisorAccessHeartbeat.CHANNEL_MOBILE),
        ),
        last_mobile_token_at=Max(
            'mobile_api_tokens__last_used_at',
            filter=Q(mobile_api_tokens__last_used_at__isnull=False),
        ),
    )
    for supervisor in annotated_supervisors:
        user_id = supervisor.id
        last_login_at = getattr(supervisor, 'last_login', None)
        last_mobile_at = getattr(supervisor, 'last_mobile_at', None)
        last_mobile_token_at = getattr(supervisor, 'last_mobile_token_at', None)
        if last_mobile_token_at and (last_mobile_at is None or last_mobile_token_at > last_mobile_at):
            last_mobile_at = last_mobile_token_at
        last_web_at = getattr(supervisor, 'last_web_at', None)
        if last_login_at and (last_web_at is None or last_login_at > last_web_at):
            last_web_at = last_login_at
        last_web_at = localize_metric_datetime(last_web_at)
        last_mobile_at = localize_metric_datetime(last_mobile_at)
        used_web_in_range = user_id in web_user_ids
        used_mobile_in_range = user_id in mobile_user_ids
        if used_web_in_range and used_mobile_in_range:
            profile_key = 'both'
            profile_label = 'Web + Mobile'
        elif used_mobile_in_range:
            profile_key = 'mobile'
            profile_label = 'So mobile'
        elif used_web_in_range:
            profile_key = 'web'
            profile_label = 'So web'
        else:
            profile_key = 'inactive'
            profile_label = 'Sem uso'
        supervisor_rows.append(
            {
                'username': supervisor.username,
                'full_name': (supervisor.get_full_name() or '').strip(),
                'last_web_at': last_web_at,
                'last_mobile_at': last_mobile_at,
                'used_web_in_range': used_web_in_range,
                'used_mobile_in_range': used_mobile_in_range,
                'channel_profile': profile_key,
                'channel_profile_label': profile_label,
            }
        )

    supervisor_rows.sort(
        key=lambda row: (
            {'both': 0, 'mobile': 1, 'web': 2, 'inactive': 3}.get(row['channel_profile'], 9),
            row['full_name'] or row['username'],
        )
    )

    rdo_channel_qs = RDOChannelEvent.objects.filter(
        user__in=supervisors_qs,
        occurred_at__gte=start_at,
        occurred_at__lte=end_at,
    )
    web_rdo_ranking = {}
    mobile_rdo_ranking = {}
    web_rdo_ids = set(
        rdo_channel_qs.filter(channel=RDOChannelEvent.CHANNEL_WEB)
        .exclude(rdo_id__isnull=True)
        .values_list('rdo_id', flat=True)
        .distinct()
    )
    mobile_rdo_ids = set(
        rdo_channel_qs.filter(channel=RDOChannelEvent.CHANNEL_MOBILE)
        .exclude(rdo_id__isnull=True)
        .values_list('rdo_id', flat=True)
        .distinct()
    )
    web_rdo_create_ids = set(
        rdo_channel_qs.filter(
            channel=RDOChannelEvent.CHANNEL_WEB,
            event_type=RDOChannelEvent.EVENT_CREATE,
        )
        .exclude(rdo_id__isnull=True)
        .values_list('rdo_id', flat=True)
        .distinct()
    )
    web_rdo_update_ids = set(
        rdo_channel_qs.filter(
            channel=RDOChannelEvent.CHANNEL_WEB,
            event_type=RDOChannelEvent.EVENT_UPDATE,
        )
        .exclude(rdo_id__isnull=True)
        .values_list('rdo_id', flat=True)
        .distinct()
    )
    mobile_rdo_create_ids = set(
        rdo_channel_qs.filter(
            channel=RDOChannelEvent.CHANNEL_MOBILE,
            event_type=RDOChannelEvent.EVENT_CREATE,
        )
        .exclude(rdo_id__isnull=True)
        .values_list('rdo_id', flat=True)
        .distinct()
    )
    mobile_rdo_update_ids = set(
        rdo_channel_qs.filter(
            channel=RDOChannelEvent.CHANNEL_MOBILE,
            event_type=RDOChannelEvent.EVENT_UPDATE,
        )
        .exclude(rdo_id__isnull=True)
        .values_list('rdo_id', flat=True)
        .distinct()
    )
    for user_id, channel, event_type, rdo_id, occurred_at in rdo_channel_qs.exclude(
        rdo_id__isnull=True,
    ).values_list('user_id', 'channel', 'event_type', 'rdo_id', 'occurred_at'):
        if channel == RDOChannelEvent.CHANNEL_WEB:
            _update_rdo_ranking_bucket(
                web_rdo_ranking,
                user_id=user_id,
                event_type=event_type,
                rdo_id=rdo_id,
                occurred_at=occurred_at,
            )
        elif channel == RDOChannelEvent.CHANNEL_MOBILE:
            _update_rdo_ranking_bucket(
                mobile_rdo_ranking,
                user_id=user_id,
                event_type=event_type,
                rdo_id=rdo_id,
                occurred_at=occurred_at,
            )

    mobile_sync_rdo_qs = MobileSyncEvent.objects.filter(
        user__in=supervisors_qs,
        state=MobileSyncEvent.STATE_DONE,
        created_at__gte=start_at,
        created_at__lte=end_at,
        operation__in=['rdo.create', 'rdo.update'],
    ).values_list('user_id', 'operation', 'response_payload', 'request_payload', 'created_at')
    for user_id, operation, response_payload, request_payload, created_at in mobile_sync_rdo_qs:
        rdo_id = _extract_rdo_id_from_mapping(response_payload) or _extract_rdo_id_from_mapping(request_payload)
        if rdo_id is None:
            continue
        mobile_rdo_ids.add(rdo_id)
        if operation == 'rdo.create':
            mobile_rdo_create_ids.add(rdo_id)
        elif operation == 'rdo.update':
            mobile_rdo_update_ids.add(rdo_id)
        _update_rdo_ranking_bucket(
            mobile_rdo_ranking,
            user_id=user_id,
            event_type=RDOChannelEvent.EVENT_CREATE if operation == 'rdo.create' else RDOChannelEvent.EVENT_UPDATE,
            rdo_id=rdo_id,
            occurred_at=created_at,
        )

    active_both_supervisors = len(web_user_ids & mobile_user_ids)
    active_only_web_supervisors = len(web_user_ids - mobile_user_ids)
    active_only_mobile_supervisors = len(mobile_user_ids - web_user_ids)
    active_any_supervisors = len(web_user_ids | mobile_user_ids)
    inactive_supervisors = max(0, total_supervisors - active_any_supervisors)
    active_web_supervisors = len(web_user_ids)
    active_mobile_supervisors = len(mobile_user_ids)
    rdo_both_channel_ids = web_rdo_ids & mobile_rdo_ids

    return {
        **range_info,
        'total_supervisors': total_supervisors,
        'active_web_supervisors': active_web_supervisors,
        'active_mobile_supervisors': active_mobile_supervisors,
        'active_both_supervisors': active_both_supervisors,
        'active_only_web_supervisors': active_only_web_supervisors,
        'active_only_mobile_supervisors': active_only_mobile_supervisors,
        'active_any_supervisors': active_any_supervisors,
        'inactive_supervisors': inactive_supervisors,
        'web_usage_rate': _percent(active_web_supervisors, total_supervisors),
        'mobile_usage_rate': _percent(active_mobile_supervisors, total_supervisors),
        'both_usage_rate': _percent(active_both_supervisors, total_supervisors),
        'web_only_rate': _percent(active_only_web_supervisors, total_supervisors),
        'mobile_only_rate': _percent(active_only_mobile_supervisors, total_supervisors),
        'inactive_usage_rate': _percent(inactive_supervisors, total_supervisors),
        'web_online_rate': _percent(len(web_online_ids), total_supervisors),
        'mobile_online_rate': _percent(len(mobile_online_ids), total_supervisors),
        'web_online_now': len(web_online_ids),
        'mobile_online_now': len(mobile_online_ids),
        'active_mobile_tokens': MobileApiToken.objects.filter(
            user__in=supervisors_qs,
            is_active=True,
        ).count(),
        'web_rdo_total': len(web_rdo_ids),
        'mobile_rdo_total': len(mobile_rdo_ids),
        'web_rdo_created_total': len(web_rdo_create_ids),
        'mobile_rdo_created_total': len(mobile_rdo_create_ids),
        'web_rdo_updated_total': len(web_rdo_update_ids),
        'mobile_rdo_updated_total': len(mobile_rdo_update_ids),
        'rdo_both_channel_total': len(rdo_both_channel_ids),
        'web_rdo_ranking_rows': _build_rdo_ranking_rows(web_rdo_ranking, supervisor_lookup),
        'mobile_rdo_ranking_rows': _build_rdo_ranking_rows(mobile_rdo_ranking, supervisor_lookup),
        'web_hour_rows': web_hour_rows,
        'mobile_hour_rows': mobile_hour_rows,
        'web_peak_row': web_peak_row,
        'mobile_peak_row': mobile_peak_row,
        'supervisor_rows': supervisor_rows,
        'telemetry_started_at': localize_metric_datetime(timezone.now()),
    }
