from django.core.management.base import BaseCommand
from GO.models import OrdemServico, RdoTanque

class Command(BaseCommand):
    help = "Atualiza previsões de ensacamento, içamento e cambagem para OS 6249 tanque 1AS."

    def handle(self, *args, **options):
        os_num = 6249
        tank_code = '1AS'
        ensacamento_prev = 1250
        icamento_prev = 1250
        cambagem_prev = 1200

        ordens = OrdemServico.objects.filter(numero_os=os_num)
        if not ordens.exists():
            self.stderr.write(f'Nenhuma OS {os_num} encontrada.')
            return

        total = 0
        for ordem in ordens:
            qs = RdoTanque.objects.filter(rdo__ordem_servico=ordem, tanque_codigo__iexact=tank_code)
            if not qs.exists():
                self.stdout.write(f'Nenhum registro encontrado para OS={os_num} tanque="{tank_code}" (ordem id={ordem.id})')
                continue
            for t in qs:
                t.ensacamento_prev = ensacamento_prev
                t.icamento_prev = icamento_prev
                t.cambagem_prev = cambagem_prev
                t.save(update_fields=[
                    'ensacamento_prev', 'icamento_prev', 'cambagem_prev', 'updated_at'
                ])
                self.stdout.write(f'Atualizado: id={t.id} | ordem_id={ordem.id} | ensacamento_prev={ensacamento_prev} | icamento_prev={icamento_prev} | cambagem_prev={cambagem_prev}')
                total += 1

        self.stdout.write(f'Atualização concluída. Total de registros alterados: {total}')
