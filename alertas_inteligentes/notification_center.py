from datetime import timedelta
from urllib.parse import urlencode

from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.urls import reverse
from django.utils import timezone

from .models import (
    AlertaInteligente,
    AlertaOperacionalInteligente,
    LeituraAlertaIA,
)


PAGE_SIZE_DEFAULT = 20
PAGE_SIZE_MAX = 50

RDO_ALERT_SECTION_MAP = {
    "RDO_SEM_TURNO": "identificacao",
    "RDO_DATA_PULADA": "identificacao",
    "PT_SEM_TURNO": "pt",
    "PT_SEM_NUMERO": "pt",
    "PT_INCOERENTE": "pt",
    "ATIVIDADE_SEM_HORARIO": "atividades",
    "ATIVIDADE_SOBREPOSTA": "atividades",
    "ESPACO_CONFINADO_SEM_HORARIO": "tanque",
    "ESPACO_CONFINADO_INCOERENTE": "tanque",
    "RDO_TANQUE_INCOMPLETO": "tanque",
    "OPERADORES_MAIOR_EQUIPE": "equipe",
    "VALOR_DIARIO_MAIOR_PREVISAO": "operacionais",
    "AVANCO_INVALIDO": "operacionais",
    "FOTO_AUSENTE": "equipe",
    "OBSERVACAO_INCOERENTE": "equipe",
    "RDO_OUTLIER": "identificacao",
    "RDO_REVISAR_ANOMALIA": "identificacao",
}


def _period_filter():
    today = timezone.localdate()
    return {
        "criado_em__date__gte": today - timedelta(days=1),
        "criado_em__date__lte": today,
    }


def _is_supervisor(user):
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and not getattr(user, "is_superuser", False)
        and user.groups.filter(name="Supervisor").exists()
    )


def accessible_alert_querysets(user, *, daily_only=False):
    """Return both AI alert sources, optionally restricted to the daily preview."""
    period = _period_filter() if daily_only else {}
    rdo_qs = (
        AlertaInteligente.objects.filter(status="pendente", **period)
        .select_related(
            "rdo",
            "rdo__ordem_servico",
            "rdo__ordem_servico__Cliente",
            "rdo__ordem_servico__Unidade",
        )
        .order_by("-criado_em", "-id")
    )
    operational_qs = (
        AlertaOperacionalInteligente.objects.filter(status="pendente", **period)
        .select_related(
            "ordem_servico",
            "ordem_servico__Cliente",
            "ordem_servico__Unidade",
        )
        .order_by("-criado_em", "-id")
    )
    # Supervisors already see only their own operational context on the RDO
    # screen. Preserve that restriction in the notification APIs as well.
    if _is_supervisor(user):
        rdo_qs = rdo_qs.filter(rdo__ordem_servico__supervisor=user)
        operational_qs = operational_qs.filter(ordem_servico__supervisor=user)
    return rdo_qs, operational_qs


def _with_read_state(queryset, user, source):
    receipt_filter = {
        "usuario": user,
        "lido": True,
        "alerta_rdo_id" if source == "rdo" else "alerta_operacional_id": OuterRef("pk"),
    }
    return queryset.annotate(
        user_has_read=Exists(LeituraAlertaIA.objects.filter(**receipt_filter))
    )


def _apply_database_filters(queryset, source, query, priority):
    if priority:
        queryset = queryset.filter(prioridade=priority)
    if not query:
        return queryset
    if source == "rdo":
        searchable = (
            Q(mensagem__icontains=query)
            | Q(tipo__icontains=query)
            | Q(referencia__icontains=query)
            | Q(rdo__rdo__icontains=query)
            | Q(rdo__ordem_servico__numero_os__icontains=query)
            | Q(rdo__ordem_servico__Cliente__nome__icontains=query)
            | Q(rdo__ordem_servico__Unidade__nome__icontains=query)
        )
    else:
        searchable = (
            Q(mensagem__icontains=query)
            | Q(tipo__icontains=query)
            | Q(referencia__icontains=query)
            | Q(ordem_servico__numero_os__icontains=query)
            | Q(ordem_servico__Cliente__nome__icontains=query)
            | Q(ordem_servico__Unidade__nome__icontains=query)
        )
    return queryset.filter(searchable)


def _serialize_annotated(source, alerts):
    return [serialize_alert(source, alert, bool(alert.user_has_read)) for alert in alerts]


def _read_keys(user, rdo_ids, operational_ids):
    keys = set()
    if rdo_ids:
        keys.update(
            ("rdo", object_id)
            for object_id in LeituraAlertaIA.objects.filter(
                usuario=user,
                alerta_rdo_id__in=rdo_ids,
                lido=True,
            ).values_list("alerta_rdo_id", flat=True)
        )
    if operational_ids:
        keys.update(
            ("operacional", object_id)
            for object_id in LeituraAlertaIA.objects.filter(
                usuario=user,
                alerta_operacional_id__in=operational_ids,
                lido=True,
            ).values_list("alerta_operacional_id", flat=True)
        )
    return keys


def _safe_name(value):
    if not value:
        return ""
    return str(getattr(value, "nome", None) or value)


def serialize_alert(source, alert, is_read=False):
    target_section = ""
    if source == "rdo":
        rdo = alert.rdo
        os_obj = getattr(rdo, "ordem_servico", None)
        rdo_number = getattr(rdo, "rdo", None) or getattr(rdo, "numero_rdo", None) or rdo.pk
        target_section = RDO_ALERT_SECTION_MAP.get(alert.tipo, "identificacao")
        detail_query = urlencode(
            {
                "open_editor": "1",
                "rdo_id": rdo.pk,
                "os_id": getattr(os_obj, "pk", "") or "",
                "os": getattr(os_obj, "numero_os", "") or "",
                "rdo": rdo_number,
                "section": target_section,
            }
        )
        detail_url = f"{reverse('rdo')}?{detail_query}"
        origin = "Synchro AI · RDO"
    else:
        os_obj = alert.ordem_servico
        rdo_number = ""
        detail_url = ""
        origin = "Synchro AI · Operação"

    os_number = getattr(os_obj, "numero_os", None) if os_obj else None
    client = _safe_name(getattr(os_obj, "Cliente", None)) if os_obj else ""
    unit = _safe_name(getattr(os_obj, "Unidade", None)) if os_obj else ""
    recommendation = getattr(alert, "acao_recomendada", None) or ""
    explanation = getattr(alert, "explicacao_curta", None) or ""
    title = alert.identificacao_operacional
    created_local = timezone.localtime(alert.criado_em)
    os_filter_url = ""
    if os_obj and os_number:
        os_filter_url = f"{reverse('rdo')}?{urlencode({'os': os_number})}"

    return {
        "key": f"{source}:{alert.pk}",
        "source": source,
        "id": alert.pk,
        "title": title,
        "message": alert.mensagem,
        "summary": explanation or alert.mensagem,
        "recommendation": recommendation,
        "priority": alert.prioridade,
        "priority_label": alert.get_prioridade_display(),
        "type": alert.tipo,
        "type_label": alert.get_tipo_display(),
        "is_read": bool(is_read),
        "created_at": alert.criado_em.isoformat(),
        "created_date": created_local.strftime("%d/%m/%Y"),
        "created_time": created_local.strftime("%H:%M"),
        "os_number": os_number or "",
        "rdo_number": rdo_number or "",
        "client": client,
        "unit": unit,
        "origin": origin,
        "target_section": target_section,
        "detail_url": detail_url,
        "os_url": os_filter_url,
    }


def all_accessible_serialized(user):
    rdo_qs, operational_qs = accessible_alert_querysets(user)
    rdo_alerts = list(rdo_qs)
    operational_alerts = list(operational_qs)
    read_keys = _read_keys(
        user,
        [item.pk for item in rdo_alerts],
        [item.pk for item in operational_alerts],
    )
    items = [
        serialize_alert("rdo", item, ("rdo", item.pk) in read_keys)
        for item in rdo_alerts
    ] + [
        serialize_alert("operacional", item, ("operacional", item.pk) in read_keys)
        for item in operational_alerts
    ]
    return sorted(items, key=lambda item: (item["created_at"], item["id"]), reverse=True)


def notification_snapshot(user, limit=5):
    # The compact header dropdown remains a lightweight daily preview.
    rdo_qs, operational_qs = accessible_alert_querysets(user, daily_only=True)
    rdo_qs = _with_read_state(rdo_qs, user, "rdo")
    operational_qs = _with_read_state(operational_qs, user, "operacional")
    unread_count = (
        rdo_qs.filter(user_has_read=False).count()
        + operational_qs.filter(user_has_read=False).count()
    )
    unread = _serialize_annotated("rdo", list(rdo_qs.filter(user_has_read=False)[:limit]))
    unread += _serialize_annotated(
        "operacional", list(operational_qs.filter(user_has_read=False)[:limit])
    )
    read = _serialize_annotated("rdo", list(rdo_qs.filter(user_has_read=True)[:limit]))
    read += _serialize_annotated(
        "operacional", list(operational_qs.filter(user_has_read=True)[:limit])
    )
    unread.sort(key=lambda item: (item["created_at"], item["id"]), reverse=True)
    read.sort(key=lambda item: (item["created_at"], item["id"]), reverse=True)
    ordered = unread + read
    return {
        "unread_count": unread_count,
        "items": ordered[:limit],
        "total": rdo_qs.count() + operational_qs.count(),
    }


def filtered_page(user, *, tab="pendentes", query="", priority="", page=1, page_size=PAGE_SIZE_DEFAULT):
    query = (query or "").strip()
    priority = (priority or "").strip().lower()
    rdo_qs, operational_qs = accessible_alert_querysets(user)
    rdo_qs = _with_read_state(rdo_qs, user, "rdo")
    operational_qs = _with_read_state(operational_qs, user, "operacional")
    global_unread = (
        rdo_qs.filter(user_has_read=False).count()
        + operational_qs.filter(user_has_read=False).count()
    )
    rdo_qs = _apply_database_filters(rdo_qs, "rdo", query, priority)
    operational_qs = _apply_database_filters(operational_qs, "operacional", query, priority)
    counts = {
        "all": rdo_qs.count() + operational_qs.count(),
        "pending": (
            rdo_qs.filter(user_has_read=False).count()
            + operational_qs.filter(user_has_read=False).count()
        ),
        "read": (
            rdo_qs.filter(user_has_read=True).count()
            + operational_qs.filter(user_has_read=True).count()
        ),
    }
    if tab == "lidas":
        rdo_qs = rdo_qs.filter(user_has_read=True)
        operational_qs = operational_qs.filter(user_has_read=True)
    elif tab == "todas":
        pass
    else:
        tab = "pendentes"
        rdo_qs = rdo_qs.filter(user_has_read=False)
        operational_qs = operational_qs.filter(user_has_read=False)

    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = min(PAGE_SIZE_MAX, max(1, int(page_size)))
    except (TypeError, ValueError):
        page_size = PAGE_SIZE_DEFAULT
    total = rdo_qs.count() + operational_qs.count()
    start = (page - 1) * page_size
    end = min(total, start + page_size)
    candidates = _serialize_annotated("rdo", list(rdo_qs[:end]))
    candidates += _serialize_annotated("operacional", list(operational_qs[:end]))
    candidates.sort(key=lambda item: (item["created_at"], item["id"]), reverse=True)
    items = candidates[start:end]
    return {
        "items": items,
        "counts": counts,
        "unread_count": global_unread,
        "tab": tab,
        "page": page,
        "page_size": page_size,
        "total": total,
        "start": 0 if not items or start >= total else start + 1,
        "end": end,
        "has_more": end < total,
        "priorities": [
            {"value": value, "label": label}
            for value, label in AlertaInteligente.PRIORIDADES
        ],
    }


def get_accessible_alert(user, source, alert_id):
    rdo_qs, operational_qs = accessible_alert_querysets(user)
    if source == "rdo":
        alert = rdo_qs.filter(pk=alert_id).first()
    elif source == "operacional":
        alert = operational_qs.filter(pk=alert_id).first()
    else:
        alert = None
    if not alert:
        return None
    read_keys = _read_keys(
        user,
        [alert.pk] if source == "rdo" else [],
        [alert.pk] if source == "operacional" else [],
    )
    return alert, (source, alert.pk) in read_keys


def set_read_state(user, source, alert, is_read):
    lookup = {
        "usuario": user,
        "alerta_rdo": alert if source == "rdo" else None,
        "alerta_operacional": alert if source == "operacional" else None,
    }
    receipt, _ = LeituraAlertaIA.objects.update_or_create(
        **lookup,
        defaults={
            "lido": bool(is_read),
            "lido_em": timezone.now() if is_read else None,
        },
    )
    return receipt


@transaction.atomic
def mark_all_read(user):
    rdo_qs, operational_qs = accessible_alert_querysets(user)
    rdo_ids = list(rdo_qs.values_list("id", flat=True))
    operational_ids = list(operational_qs.values_list("id", flat=True))
    now = timezone.now()
    existing_rdo = set(
        LeituraAlertaIA.objects.filter(usuario=user, alerta_rdo_id__in=rdo_ids)
        .values_list("alerta_rdo_id", flat=True)
    )
    existing_operational = set(
        LeituraAlertaIA.objects.filter(usuario=user, alerta_operacional_id__in=operational_ids)
        .values_list("alerta_operacional_id", flat=True)
    )
    unread_existing_count = LeituraAlertaIA.objects.filter(
        usuario=user,
        lido=False,
    ).filter(
        Q(alerta_rdo_id__in=rdo_ids)
        | Q(alerta_operacional_id__in=operational_ids)
    ).count()
    LeituraAlertaIA.objects.filter(
        usuario=user,
        alerta_rdo_id__in=rdo_ids,
    ).update(lido=True, lido_em=now, atualizado_em=now)
    LeituraAlertaIA.objects.filter(
        usuario=user,
        alerta_operacional_id__in=operational_ids,
    ).update(lido=True, lido_em=now, atualizado_em=now)
    LeituraAlertaIA.objects.bulk_create(
        [
            LeituraAlertaIA(usuario=user, alerta_rdo_id=alert_id, lido=True, lido_em=now)
            for alert_id in rdo_ids if alert_id not in existing_rdo
        ] + [
            LeituraAlertaIA(usuario=user, alerta_operacional_id=alert_id, lido=True, lido_em=now)
            for alert_id in operational_ids if alert_id not in existing_operational
        ],
        ignore_conflicts=True,
    )
    return (
        unread_existing_count
        + len([alert_id for alert_id in rdo_ids if alert_id not in existing_rdo])
        + len([alert_id for alert_id in operational_ids if alert_id not in existing_operational])
    )
