from django.core.management.base import BaseCommand
from django.db import transaction
import logging

class Command(BaseCommand):
    help = 'Migra valores antigos de sentido_limpeza para tokens canônicos usando _canonicalize_sentido.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Aplicar alterações no banco. Sem esta flag, roda em modo dry-run.')
        parser.add_argument('--batch', type=int, default=100, help='Número de objetos processados por commit (padrão 100).')

    def handle(self, *args, **options):
        from GO import views_rdo
        from GO.models import RDO, RdoTanque
        logger = logging.getLogger(__name__)
        apply_changes = bool(options.get('apply'))
        batch = int(options.get('batch') or 100)

        total_rdo = 0
        total_rdo_changed = 0
        total_tank = 0
        total_tank_changed = 0
        undecidable = []

        qs_rdo = RDO.objects.all()
        self.stdout.write(self.style.NOTICE(f"Processing {qs_rdo.count()} RDO rows (dry-run={not apply_changes})"))
        buf = []
        for r in qs_rdo.iterator():
            total_rdo += 1
            try:
                cur = getattr(r, 'sentido_limpeza', None)
                canon = views_rdo._canonicalize_sentido(cur)
                if canon and (cur != canon):
                    total_rdo_changed += 1
                    buf.append((r, canon))
                else:
                    if isinstance(cur, bool):
                        canon2 = views_rdo._canonicalize_sentido(cur)
                        if canon2 and (cur != canon2):
                            total_rdo_changed += 1
                            buf.append((r, canon2))
                if len(buf) >= batch:
                    if apply_changes:
                        with transaction.atomic():
                            for obj, new in buf:
                                try:
                                    obj.sentido_limpeza = new
                                    obj.save(update_fields=['sentido_limpeza'])
                                except Exception:
                                    logger.exception('Failed updating RDO id=%s', getattr(obj, 'id', None))
                    buf = []
            except Exception:
                logger.exception('Error processing RDO id=%s', getattr(r, 'id', None))

        if buf and apply_changes:
            with transaction.atomic():
                for obj, new in buf:
                    try:
                        obj.sentido_limpeza = new
                        obj.save(update_fields=['sentido_limpeza'])
                    except Exception:
                        logger.exception('Failed updating RDO id=%s', getattr(obj, 'id', None))
        buf = []

        qs_tank = RdoTanque.objects.all()
        self.stdout.write(self.style.NOTICE(f"Processing {qs_tank.count()} RdoTanque rows (dry-run={not apply_changes})"))
        for t in qs_tank.iterator():
            total_tank += 1
            try:
                cur = getattr(t, 'sentido_limpeza', None)
                canon = views_rdo._canonicalize_sentido(cur)
                if canon and (cur != canon):
                    total_tank_changed += 1
                    buf.append((t, canon))
                else:
                    if isinstance(cur, bool):
                        canon2 = views_rdo._canonicalize_sentido(cur)
                        if canon2 and (cur != canon2):
                            total_tank_changed += 1
                            buf.append((t, canon2))
                if len(buf) >= batch:
                    if apply_changes:
                        with transaction.atomic():
                            for obj, new in buf:
                                try:
                                    obj.sentido_limpeza = new
                                    obj.save(update_fields=['sentido_limpeza'])
                                except Exception:
                                    logger.exception('Failed updating RdoTanque id=%s', getattr(obj, 'id', None))
                    buf = []
            except Exception:
                logger.exception('Error processing RdoTanque id=%s', getattr(t, 'id', None))

        if buf and apply_changes:
            with transaction.atomic():
                for obj, new in buf:
                    try:
                        obj.sentido_limpeza = new
                        obj.save(update_fields=['sentido_limpeza'])
                    except Exception:
                        logger.exception('Failed updating RdoTanque id=%s', getattr(obj, 'id', None))

        self.stdout.write(self.style.SUCCESS(f"RDO rows scanned: {total_rdo}, changed: {total_rdo_changed}"))
        self.stdout.write(self.style.SUCCESS(f"RdoTanque rows scanned: {total_tank}, changed: {total_tank_changed}"))
        if not apply_changes:
            self.stdout.write(self.style.WARNING('Dry-run complete. To actually apply changes run with --apply'))
        else:
            self.stdout.write(self.style.SUCCESS('Migration applied successfully.'))