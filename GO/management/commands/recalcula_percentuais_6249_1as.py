from django.core.management.base import BaseCommand
from GO.models import OrdemServico, RdoTanque

class Command(BaseCommand):
    help = "Recalcula e salva os percentuais de ensacamento, içamento e cambagem para todos os tanques 1AS da OS 6249."

    def handle(self, *args, **options):
        os_num = 6249
        tank_code = '1AS'
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
                # Chama o método de cálculo se existir
                if hasattr(t, 'calcula_percentuais'):
                    t.calcula_percentuais()
                t.save(update_fields=[
                    'percentual_ensacamento', 'percentual_icamento', 'percentual_cambagem', 'updated_at'
                ])
                self.stdout.write(f'Recalculado: id={t.id} | ordem_id={ordem.id} | percentual_ensacamento={t.percentual_ensacamento} | percentual_icamento={t.percentual_icamento} | percentual_cambagem={t.percentual_cambagem}')
                total += 1

        self.stdout.write(f'Recalculo concluído. Total de registros alterados: {total}')
