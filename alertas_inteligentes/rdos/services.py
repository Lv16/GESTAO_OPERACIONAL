def marcar_rdo_para_reanalise(rdo):
    from django.utils import timezone

    rdo.status_analise_ia = "pendente"
    rdo.data_analise_ia = None
    rdo.data_pendente_analise_ia = timezone.now()
    rdo.erro_analise_ia = None
    rdo.save(update_fields=[
        "status_analise_ia",
        "data_analise_ia",
        "data_pendente_analise_ia",
        "erro_analise_ia",
    ])
