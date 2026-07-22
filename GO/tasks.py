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
