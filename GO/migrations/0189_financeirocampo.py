from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('GO', '0188_financeiro_data_entrega_proposta_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='FinanceiroCampo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=150)),
                ('valor', models.DecimalField(decimal_places=2, max_digits=12)),
                ('financeiro', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='campos', to='GO.financeiro')),
            ],
            options={
                'verbose_name': 'campo financeiro',
                'verbose_name_plural': 'campos financeiros',
                'ordering': ['id'],
            },
        ),
    ]
