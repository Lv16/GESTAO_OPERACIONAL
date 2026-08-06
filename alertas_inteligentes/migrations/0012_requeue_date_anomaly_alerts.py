from django.db import migrations
from django.utils import timezone


def requeue_date_anomaly_alerts(apps, schema_editor):
    AlertaInteligente = apps.get_model("alertas_inteligentes", "AlertaInteligente")
    RDO = apps.get_model("GO", "RDO")

    rdo_ids = list(
        AlertaInteligente.objects.filter(
            tipo__in=["RDO_OUTLIER", "RDO_REVISAR_ANOMALIA"],
            status__in=["pendente", "em_analise"],
            anomaly_flags__date__out_of_order=True,
        )
        .values_list("rdo_id", flat=True)
        .distinct()
    )
    if not rdo_ids:
        return

    AlertaInteligente.objects.filter(
        tipo__in=["RDO_OUTLIER", "RDO_REVISAR_ANOMALIA"],
        status__in=["pendente", "em_analise"],
        anomaly_flags__date__out_of_order=True,
    ).update(
        status="resolvido",
        resolvido_em=timezone.now(),
        justificativa="Reanálise necessária após correção da validação da sequência de datas.",
    )

    RDO.objects.filter(pk__in=rdo_ids).update(
        status_analise_ia="pendente",
        data_analise_ia=None,
        erro_analise_ia=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("alertas_inteligentes", "0011_leituraalertaia_and_more"),
    ]

    operations = [
        migrations.RunPython(requeue_date_anomaly_alerts, migrations.RunPython.noop),
    ]
