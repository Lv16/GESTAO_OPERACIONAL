import logging
import threading

from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone


logger = logging.getLogger(__name__)


def analisar_rdo_imediatamente(rdo_id):
    """Claim and analyse one RDO without allowing a failure to affect its creation."""
    from GO.models import RDO
    from alertas_inteligentes.models import AlertaInteligente
    from alertas_inteligentes.services.rdo_validator import validar_rdo

    try:
        rdo_id = int(rdo_id)
    except (TypeError, ValueError):
        return {'processed': False, 'alerts': 0, 'error': 'RDO inválido.'}

    close_old_connections()
    try:
        with transaction.atomic():
            claimed = RDO.objects.filter(
                pk=rdo_id,
                status_analise_ia__in=['pendente', 'erro'],
            ).update(
                status_analise_ia='em_analise',
                erro_analise_ia=None,
            )
            if not claimed:
                return {'processed': False, 'alerts': 0, 'error': None}

            rdo = RDO.objects.select_related('ordem_servico').get(pk=rdo_id)
            AlertaInteligente.objects.filter(
                rdo=rdo,
                status__in=['pendente', 'em_analise'],
            ).update(
                status='resolvido',
                resolvido_em=timezone.now(),
                justificativa='Resolvido automaticamente após nova análise do RDO.',
            )

            alerts = validar_rdo(rdo)
            RDO.objects.filter(pk=rdo_id).update(
                status_analise_ia='analisado',
                data_analise_ia=timezone.now(),
                erro_analise_ia=None,
            )
            return {'processed': True, 'alerts': len(alerts), 'error': None}
    except Exception as exc:
        logger.exception('Falha na análise automática do RDO %s', rdo_id)
        RDO.objects.filter(pk=rdo_id).update(
            # Keep it in the queue so the scheduled routine can retry later.
            status_analise_ia='pendente',
            erro_analise_ia=str(exc),
        )
        return {'processed': False, 'alerts': 0, 'error': str(exc)}
    finally:
        close_old_connections()


def agendar_analise_rdo(rdo):
    """Queue an RDO analysis after the surrounding database transaction commits."""
    from alertas_inteligentes.services import marcar_rdo_para_reanalise

    rdo_id = getattr(rdo, 'pk', None) or getattr(rdo, 'id', None) or rdo
    try:
        rdo_id = int(rdo_id)
    except (TypeError, ValueError):
        return False

    marcar_rdo_para_reanalise(rdo_id)

    def dispatch():
        if getattr(settings, 'CELERY_ENABLED', False):
            try:
                from GO.tasks import analyze_rdo_task

                analyze_rdo_task.delay(rdo_id)
                return
            except Exception:
                logger.exception(
                    'Falha ao enviar a análise do RDO %s ao Celery; usando execução local.',
                    rdo_id,
                )

        threading.Thread(
            target=analisar_rdo_imediatamente,
            args=(rdo_id,),
            name=f'synchro-ai-rdo-{rdo_id}',
            daemon=True,
        ).start()

    transaction.on_commit(dispatch)
    return True
