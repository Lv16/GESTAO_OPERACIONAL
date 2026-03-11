from django.db import migrations


def backfill_identifier_logs(apps, schema_editor):
    Equipamentos = apps.get_model('GO', 'Equipamentos')
    EquipamentoIdentificadorLog = apps.get_model('GO', 'EquipamentoIdentificadorLog')

    for equipamento in Equipamentos.objects.all().iterator():
        tag = (equipamento.numero_tag or '').strip().upper()
        serie = (equipamento.numero_serie or '').strip().upper()

        if tag:
            exists_tag = EquipamentoIdentificadorLog.objects.filter(
                equipamento_id=equipamento.pk,
                identifier_type='tag',
            ).exists()
            if not exists_tag:
                EquipamentoIdentificadorLog.objects.create(
                    equipamento_id=equipamento.pk,
                    identifier_type='tag',
                    previous_value=None,
                    current_value=tag,
                    note='snapshot inicial',
                )

        if serie:
            exists_serie = EquipamentoIdentificadorLog.objects.filter(
                equipamento_id=equipamento.pk,
                identifier_type='serie',
            ).exists()
            if not exists_serie:
                EquipamentoIdentificadorLog.objects.create(
                    equipamento_id=equipamento.pk,
                    identifier_type='serie',
                    previous_value=None,
                    current_value=serie,
                    note='snapshot inicial',
                )


def noop_reverse(apps, schema_editor):
    # Keep audit trail immutable on reverse.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('GO', '0153_equipamentoidentificadorlog'),
    ]

    operations = [
        migrations.RunPython(backfill_identifier_logs, noop_reverse),
    ]
