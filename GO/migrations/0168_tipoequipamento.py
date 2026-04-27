from django.db import migrations, models


TIPOS_EQUIPAMENTO_PADRAO = [
    'Bomba Pneumática',
    'Bomba submersível',
    'Caixa transformadora EX',
    'Cavalete de ar mandado',
    'Exaustor',
    'Guincho Pneumático',
    'Guincho Tripé',
    'Hidrojato de alta pressão',
    'Manifold',
    'Refletor led',
    'Trava quedas',
    'Container',
    'Container DryBox - 10pés',
    'Container DryBox - 20pés',
    'Container OpenTop - 10pés',
    'Container OpenTop - 20pés',
    'Caixa Metálica',
    'Cutting Box',
    'Caixa Distribuidora EX',
    'Caixa Metálica de Passagem',
    'Compressor de Ar',
    'Exaustor SH-30',
    'Hidrojato BP',
    'HPU',
    'HVAC',
    'WPU',
    'Painel Elétrico Móvel',
    'Soprador Pneumático',
    'Ventilador Holandês',
    'Luminária Pneumática',
    'Roto Router',
    'Bomba Tornado',
    'Bomba Draga',
    'Bomba Nemo',
    'Robô',
    'Hidrojato Lemasa',
]


def popular_tipos_equipamento(apps, schema_editor):
    TipoEquipamento = apps.get_model('GO', 'TipoEquipamento')
    Equipamentos = apps.get_model('GO', 'Equipamentos')

    nomes = []
    nomes.extend(TIPOS_EQUIPAMENTO_PADRAO)

    try:
        for descricao in Equipamentos.objects.values_list('descricao', flat=True).distinct():
            nomes.append(str(descricao or '').strip())
    except Exception:
        pass

    vistos = set()
    for nome in nomes:
        nome_normalizado = str(nome or '').strip()
        if not nome_normalizado:
            continue
        chave = nome_normalizado.casefold()
        if chave in vistos:
            continue
        vistos.add(chave)
        if TipoEquipamento.objects.filter(nome__iexact=nome_normalizado).exists():
            continue
        TipoEquipamento.objects.create(nome=nome_normalizado)


class Migration(migrations.Migration):

    dependencies = [
        ('GO', '0167_ordemservico_tanques_inativos'),
    ]

    operations = [
        migrations.CreateModel(
            name='TipoEquipamento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=100, unique=True)),
            ],
            options={
                'verbose_name_plural': 'Tipos de Equipamento',
                'ordering': ['nome'],
            },
        ),
        migrations.RunPython(popular_tipos_equipamento, migrations.RunPython.noop),
    ]
