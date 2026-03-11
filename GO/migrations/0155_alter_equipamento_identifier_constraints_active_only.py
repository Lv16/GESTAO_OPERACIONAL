from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('GO', '0154_backfill_identificadorlog_snapshot'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='equipamentos',
            name='uniq_equip_numero_tag_not_blank',
        ),
        migrations.RemoveConstraint(
            model_name='equipamentos',
            name='uniq_equip_numero_serie_not_blank',
        ),
        migrations.AddConstraint(
            model_name='equipamentos',
            constraint=models.UniqueConstraint(
                condition=(
                    models.Q(numero_tag__isnull=False)
                    & ~models.Q(numero_tag='')
                    & ~models.Q(situacao='trocou_unidade')
                    & ~models.Q(situacao='retornou_base')
                ),
                fields=('numero_tag',),
                name='uniq_equip_numero_tag_active',
            ),
        ),
        migrations.AddConstraint(
            model_name='equipamentos',
            constraint=models.UniqueConstraint(
                condition=(
                    models.Q(numero_serie__isnull=False)
                    & ~models.Q(numero_serie='')
                    & ~models.Q(situacao='trocou_unidade')
                    & ~models.Q(situacao='retornou_base')
                ),
                fields=('numero_serie',),
                name='uniq_equip_numero_serie_active',
            ),
        ),
    ]
