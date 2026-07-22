from django.db import migrations, models


def normalizar_equipe_rdo(apps, schema_editor):
    AlertaInteligente = apps.get_model("alertas_inteligentes", "AlertaInteligente")
    AlertaInteligente.objects.filter(equipe_responsavel="RDO").update(
        equipe_responsavel="rdo"
    )


def reverter_equipe_rdo(apps, schema_editor):
    AlertaInteligente = apps.get_model("alertas_inteligentes", "AlertaInteligente")
    AlertaInteligente.objects.filter(equipe_responsavel="rdo").update(
        equipe_responsavel="RDO"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("alertas_inteligentes", "0008_alter_alertainteligente_tipo"),
    ]

    operations = [
        migrations.AlterField(
            model_name="alertainteligente",
            name="equipe_responsavel",
            field=models.CharField(
                choices=[
                    ("operacao", "Operação"),
                    ("coordenacao", "Coordenação"),
                    ("qsms", "QSMS"),
                    ("administrativo", "Administrativo"),
                    ("rdo", "RDO"),
                ],
                default="operacao",
                max_length=50,
            ),
        ),
        migrations.RunPython(normalizar_equipe_rdo, reverter_equipe_rdo),
    ]
