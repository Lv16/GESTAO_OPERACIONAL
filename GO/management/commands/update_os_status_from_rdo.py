from django.core.management.base import BaseCommand
from django.db.models import Q
from GO.models import OrdemServico


def _needs_em_andamento(field_name):
    return (
        Q(**{f"{field_name}__isnull": True})
        | Q(**{f"{field_name}__exact": ""})
        | Q(**{f"{field_name}__iexact": "Programada"})
        | Q(**{f"{field_name}__iexact": "Programado"})
    )


class Command(BaseCommand):
    help = (
        'Atualiza status_operacao e status_geral para "Em Andamento" '
        'em OS que já possuem ao menos 1 RDO e ainda estão Programada.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Apenas mostra quantos registros seriam atualizados.',
        )

    def handle(self, *args, **options):
        dry_run = bool(options.get('dry_run'))

        base = OrdemServico.objects.filter(rdos__isnull=False)

        total_os = base.values('pk').distinct().count()
        qs_geral = base.filter(_needs_em_andamento('status_geral'))

        count_geral = qs_geral.values('pk').distinct().count()

        self.stdout.write(
            f"OS com ao menos 1 RDO: {total_os} | "
            f"status_geral para atualizar: {count_geral}"
        )

        if dry_run:
            self.stdout.write(self.style.WARNING('Dry run: nenhuma alteração aplicada.'))
            return

        updated_geral = qs_geral.update(status_geral='Em Andamento')

        self.stdout.write(
            self.style.SUCCESS(
                f"Atualização concluída. status_geral: {updated_geral}"
            )
        )
