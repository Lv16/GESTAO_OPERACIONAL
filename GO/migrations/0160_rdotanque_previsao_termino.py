from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('GO', '0159_alter_rdoatividade_atividade'),
    ]

    operations = [
        migrations.AddField(
            model_name='rdotanque',
            name='previsao_termino',
            field=models.DateField(blank=True, null=True),
        ),
    ]
