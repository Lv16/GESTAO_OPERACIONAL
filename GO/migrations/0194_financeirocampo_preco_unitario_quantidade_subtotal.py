from decimal import Decimal

from django.db import migrations, models


FINANCEIRO_CAMPO_CHOICES = [
    ("SERVICO_LIMPEZA_TANQUES", "Serviço de Limpeza de Tanques"),
    ("DISPONIBILIZACAO_EQUIPAMENTOS", "Disponibilização de Equipamentos"),
    ("VENTILADOR_EXAUSTOR", "Ventilador ou Exaustor"),
    ("BOMBA_PNEUMATICA", "Bomba Pneumática"),
    ("CONJUNTO_PAINEL_ELETRICO", "Conjunto de Painel Elétrico"),
    ("CONJUNTO_LUMINARIAS_ELETRICAS", "Conjunto de Luminárias Elétricas"),
    ("CONJUNTO_LUMINARIAS_PNEUMATICAS", "Conjunto de Luminárias Pneumáticas"),
    ("AR_CONDICIONADO", "Ar Condicionado"),
    ("COMPRESSOR_AR", "Compressor de Ar"),
    ("TANK_SCOPE", "Tank Scope"),
    ("KIT_RESGATE_1", "Kit Resgate 1"),
    ("KIT_RESGATE_2", "Kit Resgate 2"),
    ("CONJUNTO_EQUIPAMENTOS_LIMPEZA_MECANIZADA", "Conjunto de Equipamentos para Limpeza Mecanizada"),
    ("TAXA_DIARIA_DISPON_EQUIP_LIMPEZA_MECANIZADA_ONSHORE", "Taxa Diária de Dispon. de Equip. para Limpeza Mecanizada Onshore"),
    ("TAXA_MENSAL_EQUIPE_ONSHORE", "Taxa Mensal de Equipe Onshore"),
    ("TAXA_DIARIA_SUPERV_SERVICO_LIMPEZA_OPERADOR_DISPOSICAO", "Taxa Diária Superv. de Serviço de Limpeza ou Operador à Disposição"),
    ("TAXA_DIARIA_AUXILIAR_SERVICOS_GERAIS_LIMPEZA_DISPOSICAO", "Taxa Diária de Auxiliar de Serviços Gerais de Limpeza à Disposição"),
    ("TAXA_MONITORAMENTO_SAUDE", "Taxa de Monitoramento de Saúde"),
]


def populate_financeirocampo_subtotal(apps, schema_editor):
    FinanceiroCampo = apps.get_model("GO", "FinanceiroCampo")
    for campo in FinanceiroCampo.objects.all():
        preco = campo.preco_unitario or Decimal("0")
        quantidade = campo.quantidade or Decimal("1")
        campo.subtotal = preco * quantidade
        campo.save(update_fields=["subtotal"])


class Migration(migrations.Migration):

    dependencies = [
        ("GO", "0193_remove_financeiro_taxa1_remove_financeiro_taxa2_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="financeirocampo",
            old_name="valor",
            new_name="preco_unitario",
        ),
        migrations.AlterField(
            model_name="financeirocampo",
            name="nome",
            field=models.CharField(choices=FINANCEIRO_CAMPO_CHOICES, max_length=150),
        ),
        migrations.AddField(
            model_name="financeirocampo",
            name="quantidade",
            field=models.DecimalField(decimal_places=2, default=1, max_digits=10),
        ),
        migrations.AddField(
            model_name="financeirocampo",
            name="subtotal",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.RunPython(populate_financeirocampo_subtotal, migrations.RunPython.noop),
    ]
