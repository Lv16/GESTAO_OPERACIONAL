def marcar_rdo_para_reanalise(rdo):
    from GO.models import RDO
    from django.utils import timezone

    rdo_id = getattr(rdo, "pk", None) or getattr(rdo, "id", None) or rdo
    if not rdo_id:
        return 0

    return RDO.objects.filter(pk=rdo_id).update(
        status_analise_ia="pendente",
        data_analise_ia=None,
        data_pendente_analise_ia=timezone.now(),
        erro_analise_ia=None,
    )
