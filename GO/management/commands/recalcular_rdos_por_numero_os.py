from django.core.management.base import BaseCommand

from GO.rdo_sequence import apply_rdo_renumber_plan, build_rdo_renumber_plan


class Command(BaseCommand):
    help = (
        'Recalcula a numeracao dos RDOs por numero_os para manter a sequencia '
        'unica e cronologica dentro de cada OS.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--numero-os',
            action='append',
            dest='numero_os_list',
            help='Filtra uma ou mais OS especificas. Pode ser repetido.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Somente mostra o plano, sem gravar.',
        )
        parser.add_argument(
            '--commit',
            action='store_true',
            help='Grava as alteracoes encontradas.',
        )

    def handle(self, *args, **options):
        numero_os_list = options.get('numero_os_list') or None
        dry_run = bool(options.get('dry_run'))
        commit = bool(options.get('commit'))

        if dry_run and commit:
            self.stderr.write('Use apenas um entre --dry-run e --commit.')
            return

        plan, summary = build_rdo_renumber_plan(numero_os_list=numero_os_list)

        if not plan:
            self.stdout.write('Nenhum RDO precisa ser renumerado.')
            return

        self.stdout.write(
            f'OS afetadas: {len(summary)} | RDOs a renumerar: {len(plan)}'
        )
        for item in summary:
            self.stdout.write(
                f'OS {item["numero_os"]}: {item["changes"]} alteracoes '
                f'em {item["total_rdos"]} RDOs'
            )

        for change in plan:
            self.stdout.write(
                f'OS {change["numero_os"]} | RDO id={change["id"]} | '
                f'{change["old_rdo"]} -> {change["new_rdo"]} | '
                f'data={change["data_inicio"] or change["data"]}'
            )

        if not commit:
            self.stdout.write(
                'Dry run concluido. Rode com --commit para aplicar as alteracoes.'
            )
            return

        updated = apply_rdo_renumber_plan(plan)
        self.stdout.write(
            f'Commit concluido. RDOs renumerados: {updated}.'
        )
