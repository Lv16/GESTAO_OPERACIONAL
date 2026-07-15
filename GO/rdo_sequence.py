from __future__ import annotations

from collections import defaultdict
from datetime import date

from django.db import transaction

from GO.models import RDO


def parse_rdo_numeric(value):
    try:
        return int(str(value).strip())
    except Exception:
        return None


def rdo_renumber_sort_key(rdo_obj):
    effective_date = (
        getattr(rdo_obj, 'data_inicio', None)
        or getattr(rdo_obj, 'data', None)
        or date.min
    )
    created_at = getattr(rdo_obj, 'created_at', None)
    current_numeric = parse_rdo_numeric(getattr(rdo_obj, 'rdo', None))
    return (
        effective_date,
        created_at.isoformat() if hasattr(created_at, 'isoformat') else '',
        0 if current_numeric is not None else 1,
        current_numeric or 0,
        getattr(rdo_obj, 'id', 0) or 0,
    )


def build_rdo_renumber_plan(numero_os_list=None):
    qs = (
        RDO.objects
        .select_related('ordem_servico')
        .only(
            'id',
            'rdo',
            'data',
            'data_inicio',
            'created_at',
            'ordem_servico_id',
            'ordem_servico__numero_os',
        )
    )
    if numero_os_list:
        qs = qs.filter(ordem_servico__numero_os__in=list(numero_os_list))

    grouped = defaultdict(list)
    for rdo_obj in qs.iterator():
        numero_os = getattr(getattr(rdo_obj, 'ordem_servico', None), 'numero_os', None)
        if numero_os in (None, ''):
            continue
        grouped[numero_os].append(rdo_obj)

    plan = []
    summary = []

    for numero_os, items in grouped.items():
        ordered = sorted(items, key=rdo_renumber_sort_key)
        os_changes = []
        for expected, rdo_obj in enumerate(ordered, start=1):
            current = str(getattr(rdo_obj, 'rdo', '') or '').strip()
            target = str(expected)
            if current == target:
                continue
            change = {
                'id': getattr(rdo_obj, 'id', None),
                'numero_os': numero_os,
                'ordem_servico_id': getattr(rdo_obj, 'ordem_servico_id', None),
                'old_rdo': current,
                'new_rdo': target,
                'data_inicio': getattr(rdo_obj, 'data_inicio', None),
                'data': getattr(rdo_obj, 'data', None),
            }
            os_changes.append(change)
            plan.append(change)

        if os_changes:
            summary.append({
                'numero_os': numero_os,
                'total_rdos': len(ordered),
                'changes': len(os_changes),
            })

    summary.sort(key=lambda item: item['numero_os'])
    plan.sort(key=lambda item: (item['numero_os'], int(item['new_rdo'])))
    return plan, summary


def apply_rdo_renumber_plan(plan):
    if not plan:
        return 0

    ordered_plan = [
        item for item in plan
        if item.get('id') is not None
    ]
    if not ordered_plan:
        return 0

    target_ids = [item['id'] for item in ordered_plan]
    existing_ids = set(
        RDO.objects
        .filter(id__in=target_ids)
        .values_list('id', flat=True)
    )

    updated = 0
    with transaction.atomic():
        # First move every affected row to a unique temporary token so the
        # final sequential pass never collides with current duplicated values.
        for change in ordered_plan:
            rdo_id = change['id']
            if rdo_id not in existing_ids:
                continue
            RDO.objects.filter(id=rdo_id).update(rdo=f'__renumber__{rdo_id}')

        for change in ordered_plan:
            rdo_id = change['id']
            if rdo_id not in existing_ids:
                continue
            RDO.objects.filter(id=rdo_id).update(rdo=change['new_rdo'])
            updated += 1

    return updated
