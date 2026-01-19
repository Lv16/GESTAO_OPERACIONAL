from django.core.management.base import BaseCommand, CommandError
from GO.models import RDO, RdoTanque

def _parse_boolish(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    try:
        s = str(v).strip().lower()
    except Exception:
        return None
    if s in ('1', 'true', 'sim', 's', 'yes', 'y'):
        return True
    if s in ('0', 'false', 'nao', 'não', 'n', 'no'):
        return False
    return None

class Command(BaseCommand):
    help = 'Preenche campos bombeio/total_liquido/sentido_por_tanque a partir dos campos do RDO quando ausentes.'

    def add_arguments(self, parser):
        parser.add_argument('--rdo', type=int, help='ID do RDO para processar (opcional).')
        parser.add_argument('--force', action='store_true', help='Forçar sobrescrita de valores existentes.')

    def handle(self, *args, **options):
        rdo_id = options.get('rdo')
        force = options.get('force', False)

        qs = RDO.objects.all().order_by('id')
        if rdo_id:
            qs = qs.filter(id=rdo_id)

        total_changed = 0
        for rdo in qs:
            tanques = list(RdoTanque.objects.filter(rdo=rdo))
            if not tanques:
                continue
            rdo_bombeio = rdo.bombeio if hasattr(rdo, 'bombeio') else None
            rdo_total_liq = rdo.total_liquido if hasattr(rdo, 'total_liquido') else None
            if rdo_bombeio in (None, '') and hasattr(rdo, 'bombeio_total'):
                rdo_bombeio = getattr(rdo, 'bombeio_total')
            if rdo_total_liq in (None, '') and hasattr(rdo, 'total_liquidos'):
                rdo_total_liq = getattr(rdo, 'total_liquidos')

            rdo_sentido = None
            if hasattr(rdo, 'sentido_limpeza'):
                rdo_sentido = _parse_boolish(getattr(rdo, 'sentido_limpeza'))
            elif hasattr(rdo, 'sentido'):
                rdo_sentido = _parse_boolish(getattr(rdo, 'sentido'))

            changed_for_rdo = 0
            for t in tanques:
                changed = False
                if force or (getattr(t, 'bombeio', None) in (None, '', '-')):
                    if rdo_bombeio not in (None, '', '-'): 
                        try:
                            t.bombeio = rdo_bombeio
                            changed = True
                        except Exception:
                            pass
                if force or (getattr(t, 'total_liquido', None) in (None, '', '-')):
                    if rdo_total_liq not in (None, '', '-'):
                        try:
                            t.total_liquido = rdo_total_liq
                            changed = True
                        except Exception:
                            pass
                if force or (getattr(t, 'sentido_limpeza', None) in (None, '')):
                    if rdo_sentido is not None:
                        try:
                            t.sentido_limpeza = rdo_sentido
                            changed = True
                        except Exception:
                            pass

                if changed:
                    t.save()
                    changed_for_rdo += 1
                    total_changed += 1

            if changed_for_rdo:
                self.stdout.write(self.style.SUCCESS(f'RDO {rdo.id} updated: {changed_for_rdo} tanques modificados'))

        self.stdout.write(self.style.SUCCESS(f'Done. Total tanques modificados: {total_changed}'))