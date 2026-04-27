from django.db import migrations, models


FABRICANTES_EQUIPAMENTO_PADRAO = [
    'AMBIPAR',
    'ARCOFIL',
    'CENTURION',
    'IBR',
    'MME MANUFACTERING CO.',
    'NAVILLE',
    'NEOFEU',
    'STEELFLEX',
    'TERYAIR',
    'TIMEWAY ENTERPRISE',
    'WILDEN',
    'DRAEGER',
    'FANGHZAN',
    'KARCHER',
    'MSA',
    'RANFAM',
    'ULTRASAFE',
    'WOLF',
]


def popular_fabricantes_equipamento(apps, schema_editor):
    FabricanteEquipamento = apps.get_model('GO', 'FabricanteEquipamento')
    Equipamentos = apps.get_model('GO', 'Equipamentos')
    Modelo = apps.get_model('GO', 'Modelo')

    nomes = []
    nomes.extend(FABRICANTES_EQUIPAMENTO_PADRAO)

    try:
        for fabricante in Equipamentos.objects.values_list('fabricante', flat=True).distinct():
            nomes.append(str(fabricante or '').strip())
    except Exception:
        pass

    try:
        for fabricante in Modelo.objects.values_list('fabricante', flat=True).distinct():
            nomes.append(str(fabricante or '').strip())
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
        if FabricanteEquipamento.objects.filter(nome__iexact=nome_normalizado).exists():
            continue
        FabricanteEquipamento.objects.create(nome=nome_normalizado)


class Migration(migrations.Migration):

    dependencies = [
        ('GO', '0168_tipoequipamento'),
    ]

    operations = [
        migrations.CreateModel(
            name='FabricanteEquipamento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=100, unique=True)),
            ],
            options={
                'verbose_name_plural': 'Fabricantes de Equipamento',
                'ordering': ['nome'],
            },
        ),
        migrations.RunPython(popular_fabricantes_equipamento, migrations.RunPython.noop),
    ]
