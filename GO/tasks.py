import logging

from celery import shared_task
from django.db import close_old_connections


logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={'max_retries': 5},
)
def refresh_tank_group_metrics_task(self, tank_id):
    try:
        from GO.views_rdo import _refresh_tank_group_metrics_for_reference_tank

        _refresh_tank_group_metrics_for_reference_tank(tank_id, logger=logger)
    finally:
        try:
            close_old_connections()
        except Exception:
            pass


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={'max_retries': 5},
)
def analyze_rdo_task(self, rdo_id):
    try:
        from alertas_inteligentes.services.rdo_immediate_analysis import (
            analisar_rdo_imediatamente,
        )

        result = analisar_rdo_imediatamente(rdo_id)
        if result.get('error'):
            raise RuntimeError(result['error'])
        return result
    finally:
        try:
            close_old_connections()
        except Exception:
            pass
