from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('GO', '0165_rdochannelevent'),
    ]

    operations = [
        migrations.AddField(
            model_name='rdotanque',
            name='cambagem_concluido',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='rdotanque',
            name='ensacamento_concluido',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='rdotanque',
            name='icamento_concluido',
            field=models.BooleanField(default=False),
        ),
    ]
