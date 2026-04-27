from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('GO', '0166_rdotanque_completion_flags'),
    ]

    operations = [
        migrations.AddField(
            model_name='ordemservico',
            name='tanques_inativos',
            field=models.TextField(blank=True, null=True),
        ),
    ]
