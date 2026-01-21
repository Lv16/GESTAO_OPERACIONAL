from django.core.management.base import BaseCommand
from django.db import transaction
from GO.models import OrdemServico, RdoTanque


class Command(BaseCommand):
    help = "Recompute ensacamento_cumulativo for a given tank code on a specific OS"

    def add_arguments(self, parser):
        parser.add_argument('--os', type=int, default=6048, help='Número da OS (default: 6048)')
        parser.add_argument('--tank', type=str, default='4p cot', help='Código do tanque (case-insensitive)')
        parser.add_argument('--dry-run', action='store_true', help='Não grava, apenas mostra o que mudaria')
        parser.add_argument('--commit', action='store_true', help='Grava as alterações')

    def handle(self, *args, **options):
        os_num = options.get('os')
        tank_code = (options.get('tank') or '').strip()
        dry = options.get('dry_run')
        commit = options.get('commit')

        if not tank_code:
            self.stderr.write('Código do tanque vazio; abortando.')
            return

        try:
            ordem = OrdemServico.objects.get(numero_os=os_num)
        except OrdemServico.DoesNotExist:
            self.stderr.write(f'OS {os_num} não encontrada.')
            return

        qs = RdoTanque.objects.filter(rdo__ordem_servico=ordem, tanque_codigo__iexact=tank_code).select_related('rdo').order_by('rdo__data', 'rdo__pk')
        if not qs.exists():
            self.stdout.write(f'Nenhum registro RdoTanque encontrado para OS={os_num} tanque="{tank_code}"')
            return

        total = 0
        changed = 0
        self.stdout.write(f'Processando {qs.count()} registros para OS {os_num} tanque "{tank_code}"...')
        with transaction.atomic():
            for t in qs:
                try:
                    dia = int(t.ensacamento_dia or 0)
                except Exception:
                    try:
                        dia = int(float(t.ensacamento_dia or 0))
                    except Exception:
                        dia = 0

                total += dia
                old = t.ensacamento_cumulativo or 0
                if old != total:
                    self.stdout.write(f'RDO {getattr(t.rdo, "rdo", t.rdo_id)} (id={t.rdo_id}) data={getattr(t.rdo, "data", None)} tanque={t.tanque_codigo!r} old={old} -> new={total}')
                    if commit and not dry:
                        t.ensacamento_cumulativo = total
                        try:
                            t.save(update_fields=['ensacamento_cumulativo', 'updated_at'])
                        except Exception:
                            t.save()
                        changed += 1

        if dry or not commit:
            self.stdout.write(f'Dry run: total acumulado calculado = {total}; alterações pendentes = {changed}')
        else:
            self.stdout.write(f'Commit realizado: total acumulado final = {total}; registros atualizados = {changed}')
