from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('GO', '0175_rdo_created_at'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='rdo',
            name='retorno_equipamentos',
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='RdoEquipamentoRetornoPrevisto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('previsto_retorno', models.BooleanField(default=True)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('equipamento', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='rdo_retorno_previsto', to='GO.equipamentos')),
                ('os', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='rdo_equipamentos_retorno_previsto', to='GO.ordemservico')),
                ('rdo', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='equipamentos_retorno_previsto', to='GO.rdo')),
                ('supervisor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='rdo_equipamentos_retorno_previsto', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name_plural': 'RDO Equipamentos Previsto Retorno',
                'ordering': ['-id'],
            },
        ),
        migrations.AddConstraint(
            model_name='rdoequipamentoretornoprevisto',
            constraint=models.UniqueConstraint(fields=('rdo', 'equipamento'), name='uniq_rdo_equipamento_retorno_previsto'),
        ),
    ]
