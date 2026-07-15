from django.utils import timezone
from django.db.models import Count

from alertas_inteligentes.models import (
    AlertaInteligente,
    AlertaOperacionalInteligente,
)
from alertas_inteligentes.services.field_utils import get_field_safe, has_field_safe

from GO.models import RDO, OrdemServico
from decimal import Decimal


def get_field(obj, *names, default=None):
    return get_field_safe(obj, *names, default=default)


def buscar_rdos_criados_desde(data_inicio):
    campos_possiveis = [
        "criado_em",
        "created_at",
        "data_criacao",
        "data_lancamento",
    ]

    for campo in campos_possiveis:
        if has_field_safe(RDO, campo):
            filtro = {f"{campo}__gte": data_inicio}
            return (
                RDO.objects
                .filter(**filtro)
                .select_related("ordem_servico")
                .order_by(f"-{campo}", "-id")
            )

    # fallback: usa a data do RDO
    hoje = timezone.localdate()
    ontem = hoje - timezone.timedelta(days=1)

    return (
        RDO.objects
        .filter(data__gte=ontem)
        .select_related("ordem_servico")
        .order_by("-data", "-id")
    )


def montar_principais_mudancas(
    rdos_novos,
    alertas_rdo_novos,
    alertas_operacionais_novos,
    anomalias_novas,
):
    principais = []

    for alerta in anomalias_novas[:3]:
        rdo = getattr(alerta, "rdo", None)
        if not rdo:
            continue

        os_obj = getattr(rdo, "ordem_servico", None)
        numero_os = get_field(os_obj, "numero_os", "os") or "Não informada"
        numero_rdo = get_field(rdo, "rdo", "numero_rdo", "numero", "id") or getattr(rdo, "id", "")

        principais.append(
            f"- OS {numero_os} | RDO {numero_rdo}: nova anomalia estatística identificada."
        )

    for alerta in alertas_operacionais_novos[:3]:
        identificacao = getattr(alerta, "identificacao_operacional", None)

        if identificacao:
            principais.append(
                f"- {identificacao}: novo alerta operacional do tipo {get_field(alerta, 'tipo', default='')}."
            )
        else:
            os_obj = getattr(alerta, "ordem_servico", None)
            numero_os = get_field(os_obj, "numero_os", "os") or "Não informada"
            principais.append(
                f"- OS {numero_os}: novo alerta operacional do tipo {get_field(alerta, 'tipo', default='')}."
            )

    for rdo in rdos_novos[:3]:
        os_obj = getattr(rdo, "ordem_servico", None)
        numero_os = get_field(os_obj, "numero_os", "os") or "Não informada"
        numero_rdo = get_field(rdo, "rdo", "numero_rdo", "numero", "id") or getattr(rdo, "id", "")

        principais.append(
            f"- OS {numero_os} | RDO {numero_rdo}: novo RDO lançado no período."
        )

    # evita lista gigante
    return principais[:8]


def montar_recomendacao_mudancas(
    alertas_rdo_novos,
    alertas_operacionais_novos,
    anomalias_novas,
):
    if anomalias_novas.exists():
        return (
            "Recomendo revisar primeiro as novas anomalias estatísticas, "
            "pois elas podem indicar preenchimento fora do padrão ou avanço operacional incomum."
        )

    if alertas_operacionais_novos.filter(prioridade="alta").exists():
        return (
            "Recomendo priorizar os novos alertas operacionais de alta prioridade, "
            "principalmente casos envolvendo OS em andamento sem atualização recente."
        )

    if alertas_rdo_novos.filter(prioridade="alta").exists():
        return (
            "Recomendo revisar os novos alertas de RDO com prioridade alta antes dos demais."
        )

    if alertas_rdo_novos.exists() or alertas_operacionais_novos.exists():
        return (
            "Houve novos alertas desde ontem. Recomendo revisar os itens pendentes para evitar acúmulo de inconsistências."
        )

    return (
        "Não identifiquei mudanças críticas desde ontem. Acompanhe os próximos RDOs lançados para manter a operação atualizada."
    )


def gerar_resposta_mudancas_desde_ontem():
    hoje = timezone.localdate()
    ontem = hoje - timezone.timedelta(days=1)

    inicio_ontem = timezone.make_aware(
        timezone.datetime.combine(ontem, timezone.datetime.min.time())
    )

    inicio_hoje = timezone.make_aware(
        timezone.datetime.combine(hoje, timezone.datetime.min.time())
    )

    agora = timezone.now()

    # RDOs criados/lançados desde ontem
    rdos_novos = buscar_rdos_criados_desde(inicio_ontem)

    # Alertas criados desde ontem
    alertas_rdo_novos = AlertaInteligente.objects.filter(
        criado_em__gte=inicio_ontem
    ).select_related("rdo")

    alertas_operacionais_novos = AlertaOperacionalInteligente.objects.filter(
        criado_em__gte=inicio_ontem
    ).select_related("ordem_servico")

    # Alertas resolvidos/ignorados desde ontem
    alertas_rdo_resolvidos = AlertaInteligente.objects.filter(
        resolvido_em__gte=inicio_ontem,
        status="resolvido",
    )

    alertas_rdo_ignorados = AlertaInteligente.objects.filter(
        resolvido_em__gte=inicio_ontem,
        status="ignorado",
    )

    alertas_operacionais_resolvidos = AlertaOperacionalInteligente.objects.filter(
        resolvido_em__gte=inicio_ontem,
        status="resolvido",
    )

    alertas_operacionais_ignorados = AlertaOperacionalInteligente.objects.filter(
        resolvido_em__gte=inicio_ontem,
        status="ignorado",
    )

    anomalias_novas = alertas_rdo_novos.filter(
        tipo__in=[
            "RDO_OUTLIER",
            "RDO_REVISAR_ANOMALIA",
        ]
    )

    os_com_rdo_novo = (
        rdos_novos
        .values("ordem_servico__numero_os")
        .annotate(total=Count("id"))
        .order_by("-total")[:10]
    )

    linhas = [
        f"Analisei as mudanças registradas de {ontem.strftime('%d/%m/%Y')} até agora.",
        "",
        "Resumo das mudanças:",
        f"- {rdos_novos.count()} novo(s) RDO(s) lançado(s)",
        f"- {alertas_rdo_novos.count()} novo(s) alerta(s) de RDO",
        f"- {alertas_operacionais_novos.count()} novo(s) alerta(s) operacional(is)",
        f"- {alertas_rdo_resolvidos.count() + alertas_operacionais_resolvidos.count()} alerta(s) resolvido(s)",
        f"- {alertas_rdo_ignorados.count() + alertas_operacionais_ignorados.count()} alerta(s) ignorado(s)",
        f"- {anomalias_novas.count()} nova(s) anomalia(s) estatística(s)",
    ]

    if os_com_rdo_novo:
        linhas.append("")
        linhas.append("OS com novos RDOs:")
        for item in os_com_rdo_novo:
            numero_os = item.get("ordem_servico__numero_os") or "Não informada"
            linhas.append(f"- OS {numero_os}: {item['total']} RDO(s) novo(s)")

    principais = montar_principais_mudancas(
        rdos_novos=rdos_novos,
        alertas_rdo_novos=alertas_rdo_novos,
        alertas_operacionais_novos=alertas_operacionais_novos,
        anomalias_novas=anomalias_novas,
    )

    if principais:
        linhas.append("")
        linhas.append("Principais pontos identificados:")
        linhas.extend(principais)

    recomendacao = montar_recomendacao_mudancas(
        alertas_rdo_novos,
        alertas_operacionais_novos,
        anomalias_novas,
    )

    return {
        "introducao": "\n".join(linhas),
        "alertas": alertas_rdo_novos.filter(status="pendente")[:15],
        "alertas_operacionais": alertas_operacionais_novos.filter(status="pendente")[:15],
        "recomendacao": recomendacao,
        "fontes": [
            "RDOs",
            "Alertas inteligentes",
            "Alertas operacionais",
            "Histórico de resolução/ignorar",
        ],
        "confianca": "alta",
        "tipo_resposta": "mudancas_desde_ontem",
    }
