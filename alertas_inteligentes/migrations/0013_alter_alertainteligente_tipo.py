from django.db import migrations, models


def requeue_same_date_and_shift_rdos(apps, schema_editor):
    RDO = apps.get_model("GO", "RDO")
    groups = (
        RDO.objects.filter(data__isnull=False)
        .values("ordem_servico_id", "ordem_servico__numero_os", "data", "turno")
        .annotate(total=models.Count("id"))
        .filter(total__gt=1)
    )
    ids = set()
    for group in groups:
        queryset = RDO.objects.filter(data=group["data"], turno=group["turno"])
        numero_os = group["ordem_servico__numero_os"]
        if numero_os not in (None, ""):
            queryset = queryset.filter(ordem_servico__numero_os=numero_os)
        else:
            queryset = queryset.filter(ordem_servico_id=group["ordem_servico_id"])
        ids.update(queryset.values_list("id", flat=True))

    if ids:
        RDO.objects.filter(pk__in=ids).update(
            status_analise_ia="pendente",
            data_analise_ia=None,
            erro_analise_ia=None,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("alertas_inteligentes", "0012_requeue_date_anomaly_alerts"),
    ]

    operations = [
        migrations.AlterField(
            model_name="alertainteligente",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("RDO_SEM_TURNO", "RDO sem turno"),
                    ("RDO_DATA_PULADA", "RDO com data pulada na sequencia"),
                    ("RDO_DUPLICADO", "Possível RDO duplicado"),
                    ("PT_SEM_TURNO", "PT sem turno informado"),
                    ("PT_SEM_NUMERO", "PT sem número"),
                    ("PT_INCOERENTE", "PT incoerente"),
                    ("ATIVIDADE_SEM_HORARIO", "Atividade sem horário"),
                    ("ATIVIDADE_SOBREPOSTA", "Atividades sobrepostas"),
                    ("ESPACO_CONFINADO_SEM_HORARIO", "Espaço confinado sem horário"),
                    ("ESPACO_CONFINADO_INCOERENTE", "Espaço confinado incoerente"),
                    ("OPERADORES_MAIOR_EQUIPE", "Operadores maior que equipe"),
                    ("VALOR_DIARIO_MAIOR_PREVISAO", "Valor diário maior que previsão"),
                    ("AVANCO_INVALIDO", "Avanço inválido"),
                    ("FOTO_AUSENTE", "Foto ausente"),
                    ("OBSERVACAO_INCOERENTE", "Observação incoerente"),
                    ("RDO_OUTLIER", "RDO fora do padrão"),
                    ("RDO_REVISAR_ANOMALIA", "RDO precisa de revisão"),
                    ("RDO_TANQUE_INCOMPLETO", "Tanque com dados incompletos no RDO"),
                ],
                max_length=100,
            ),
        ),
        migrations.RunPython(requeue_same_date_and_shift_rdos, migrations.RunPython.noop),
    ]
