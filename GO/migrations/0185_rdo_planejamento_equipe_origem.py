from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('GO', '0184_planejamentoequipemembro_data_desembarque_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='rdo',
            name='equipe_origem',
            field=models.CharField(
                choices=[('manual', 'Manual'), ('planejamento', 'Planejamento')],
                default='manual',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='rdo',
            name='planejamento_equipe_origem',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='rdos_gerados',
                to='GO.planejamentoequipeos',
            ),
        ),
    ]
