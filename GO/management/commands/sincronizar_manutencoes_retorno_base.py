from django.core.management.base import BaseCommand

from GO.models import EquipamentoSituacaoLog, Equipamentos
from GO.views_equipamentos import enviar_para_manutencao


class Command(BaseCommand):
    help = 'Sincroniza para a API de manutencao todos os eventos de retorno de base registrados no Synchro.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limita a quantidade de eventos processados.',
        )
        parser.add_argument(
            '--since',
            type=str,
            default=None,
            help='Data inicial no formato YYYY-MM-DD para filtrar logs de retorno.',
        )
        parser.add_argument(
            '--source',
            type=str,
            choices=['current', 'logs'],
            default='current',
            help='Origem da sincronizacao: "current" usa o estado atual dos equipamentos em retornou_base; "logs" usa os eventos historicos.',
        )

    def handle(self, *args, **options):
        limit = options.get('limit')
        since = options.get('since')
        source = options.get('source') or 'current'

        total = 0
        enviados = 0
        falhas = 0

        if source == 'logs':
            qs = (
                EquipamentoSituacaoLog.objects
                .filter(current='retornou_base')
                .exclude(equipamento__numero_os='3011')
                .select_related('equipamento')
                .order_by('created_at', 'id')
            )
            if since:
                qs = qs.filter(created_at__date__gte=since)
            if limit:
                qs = qs[:limit]

            for log in qs:
                equipamento = log.equipamento
                if not equipamento:
                    continue
                total += 1
                ok = enviar_para_manutencao(
                    equipamento,
                    synchro_id=f'equipamento-situacao-log:{log.id}',
                    data_retorno_base=log.created_at.date().isoformat(),
                )
                if ok:
                    enviados += 1
                else:
                    falhas += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f'Falha ao sincronizar log {log.id} do equipamento {equipamento.pk}'
                        )
                    )
        else:
            qs = (
                Equipamentos.objects
                .filter(situacao='retornou_base')
                .exclude(numero_os='3011')
                .order_by('id')
            )
            if limit:
                qs = qs[:limit]

            equipamentos = list(qs)
            equipamento_ids = [equipamento.id for equipamento in equipamentos]
            datas_retorno = {}

            if equipamento_ids:
                logs = (
                    EquipamentoSituacaoLog.objects
                    .filter(equipamento_id__in=equipamento_ids, current='retornou_base')
                    .order_by('equipamento_id', '-created_at')
                    .values_list('equipamento_id', 'created_at')
                )

                for equipamento_id, created_at in logs:
                    if equipamento_id not in datas_retorno:
                        datas_retorno[equipamento_id] = created_at.date().isoformat()

            for equipamento in equipamentos:
                total += 1
                ok = enviar_para_manutencao(
                    equipamento,
                    synchro_id=f'equipamento:{equipamento.id}',
                    data_retorno_base=datas_retorno.get(equipamento.id),
                )
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
                f'Sincronizacao concluida. source={source} processados={total} enviados_ou_existentes={enviados} falhas={falhas}'
            )
        )
