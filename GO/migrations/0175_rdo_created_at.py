from datetime import datetime, time

from django.db import migrations, models
from django.utils import timezone
import pytz


def _backfill_rdo_created_at(apps, schema_editor):
    RDO = apps.get_model('GO', 'RDO')
    sao_paulo = pytz.timezone('America/Sao_Paulo')

    for rdo in RDO.objects.all().only('id', 'data', 'data_inicio', 'created_at'):
        reference_date = getattr(rdo, 'data_inicio', None) or getattr(rdo, 'data', None)
        if reference_date is not None:
            created_at = timezone.make_aware(
                datetime.combine(reference_date, time(hour=12, minute=0)),
                sao_paulo,
            )
        else:
            created_at = timezone.now()
        RDO.objects.filter(pk=rdo.pk).update(created_at=created_at)


class Migration(migrations.Migration):

    dependencies = [
        ('GO', '0174_alter_ordemservico_servico_alter_rdo_servico_rdo'),
    ]

    operations = [
        migrations.AddField(
            model_name='rdo',
            name='created_at',
            field=models.DateTimeField(db_index=True, default=timezone.now),
        ),
        migrations.RunPython(_backfill_rdo_created_at, migrations.RunPython.noop),
    ]
