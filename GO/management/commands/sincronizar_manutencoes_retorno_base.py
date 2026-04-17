from django.core.management.base import BaseCommand

from GO.models import Equipamentos
from GO.views_equipamentos import enviar_para_manutencao


class Command(BaseCommand):
    help = 'Sincroniza para a API de manutencao todos os equipamentos em retorno de base.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limita a quantidade de equipamentos processados.',
        )

    def handle(self, *args, **options):
        limit = options.get('limit')

        qs = Equipamentos.objects.filter(situacao='retornou_base').order_by('id')
        if limit:
            qs = qs[:limit]

        total = 0
        enviados = 0
        falhas = 0

        for equipamento in qs:
            total += 1
            ok = enviar_para_manutencao(equipamento)
            if ok:
                enviados += 1
            else:
                falhas += 1
                self.stdout.write(
                    self.style.ERROR(
                        f'Falha ao sincronizar equipamento {equipamento.pk}'
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'Sincronizacao concluida. Processados={total} enviados_ou_existentes={enviados} falhas={falhas}'
            )
        )
