from django.db.models import Count
from django.utils import timezone

from GO.models import RDO, OrdemServico
from alertas_inteligentes.services import extractors
from alertas_inteligentes.models import (
    AlertaInteligente,
    AlertaOperacionalInteligente,
)
from alertas_inteligentes.services.field_utils import get_field_safe


def normalizar(texto):
    return str(texto or "").strip().lower()


def get_field(obj, *names, default=None):
    return get_field_safe(obj, *names, default=default)


def eh_status_em_andamento(valor):
    texto = normalizar(valor)

    return texto in [
        "em andamento",
        "andamento",
        "em_andamento",
    ]


def eh_status_finalizado(valor):
    texto = normalizar(valor)

    return texto in [
        "finalizado",
        "finalizada",
        "concluido",
        "concluida",
        "concluído",
        "concluída",
        "encerrado",
        "encerrada",
    ]


def eh_status_programado(valor):
    texto = normalizar(valor)

    return texto in [
        "programado",
        "programada",
        "planejado",
        "planejada",
        "a iniciar",
    ]


def extrair_empresa_da_pergunta(pergunta):
    return extractors.extrair_empresa_da_pergunta(pergunta)


def extrair_unidade_da_pergunta(pergunta):
    return extractors.extrair_unidade_da_pergunta(pergunta)


def buscar_linhas_por_empresa(empresa):
    return (
        OrdemServico.objects
        .filter(Cliente__nome__icontains=empresa)
        .order_by("-id")
    )


def buscar_linhas_por_unidade(unidade):
    return (
        OrdemServico.objects
        .filter(Unidade__nome__icontains=unidade)
        .order_by("-id")
    )


def montar_pontos_atencao_contexto(
    alertas_rdo,
    alertas_operacionais,
    anomalias,
    os_sem_rdo_recente,
):
    pontos = []

    for alerta in os_sem_rdo_recente[:3]:
        identificacao = getattr(alerta, "identificacao_operacional", None)

        if identificacao:
            pontos.append(
                f"- {identificacao}: linha operacional sem RDO recente."
            )
        else:
            os_obj = getattr(alerta, "ordem_servico", None)
            numero_os = get_field(os_obj, "numero_os", "os", default="Não informada")
            pontos.append(
                f"- OS {numero_os}: linha operacional sem RDO recente."
            )

    for alerta in anomalias[:3]:
        rdo = getattr(alerta, "rdo", None)
        os_obj = getattr(rdo, "ordem_servico", None)

        numero_os = get_field(os_obj, "numero_os", "os", default="Não informada")
        numero_rdo = get_field(rdo, "rdo", "numero_rdo", "numero", "id", default=getattr(rdo, "id", ""))

        pontos.append(
            f"- OS {numero_os} | RDO {numero_rdo}: possível anomalia estatística."
        )

    for alerta in alertas_operacionais.exclude(tipo="OS_SEM_RDO_RECENTE")[:3]:
        identificacao = getattr(alerta, "identificacao_operacional", None)

        if identificacao:
            pontos.append(
                f"- {identificacao}: {alerta.get_tipo_display()}."
            )

    for alerta in alertas_rdo.exclude(tipo__in=["RDO_OUTLIER", "RDO_REVISAR_ANOMALIA"])[:3]:
        rdo = getattr(alerta, "rdo", None)
        os_obj = getattr(rdo, "ordem_servico", None)

        numero_os = get_field(os_obj, "numero_os", "os", default="Não informada")
        numero_rdo = get_field(rdo, "rdo", "numero_rdo", "numero", "id", default=getattr(rdo, "id", ""))

        pontos.append(
            f"- OS {numero_os} | RDO {numero_rdo}: {alerta.get_tipo_display()}."
        )

    return pontos[:10]


def montar_recomendacao_contexto(
    alertas_rdo,
    alertas_operacionais,
    anomalias,
    os_sem_rdo_recente,
):
    if os_sem_rdo_recente.exists():
        return (
            "Recomendo priorizar as linhas em andamento sem RDO recente, "
            "pois elas podem indicar operação sem atualização, atraso de lançamento ou status desatualizado."
        )

    if anomalias.exists():
        return (
            "Recomendo revisar as anomalias estatísticas identificadas nos RDOs desse contexto, "
            "principalmente valores de avanço, ensacamento, cambagem, içamento e tempo de bomba."
        )

    if alertas_operacionais.filter(prioridade="alta").exists():
        return (
            "Recomendo revisar os alertas operacionais de alta prioridade antes dos demais."
        )

    if alertas_rdo.filter(prioridade="alta").exists():
        return (
            "Recomendo revisar os alertas de RDO de alta prioridade antes dos demais."
        )

    if alertas_rdo.exists() or alertas_operacionais.exists():
        return (
            "Existem alertas pendentes nesse contexto. Recomendo revisar os itens listados para evitar acúmulo de pendências."
        )

    return (
        "Não encontrei pendências críticas nesse contexto. Acompanhe os próximos RDOs para manter a operação atualizada."
    )


def gerar_resumo_contexto_operacional(tipo, valor, linhas_os):
    total_linhas = linhas_os.count()

    if total_linhas == 0:
        return {
            "introducao": f"Não encontrei operações para {tipo} '{valor}'.",
            "alertas": [],
            "alertas_operacionais": [],
            "recomendacao": "Verifique se o nome foi digitado corretamente ou tente usar apenas parte do nome.",
            "fontes": ["Home Operacional"],
            "confianca": "baixa",
            "tipo_resposta": f"resumo_{tipo}",
        }

    ids_os = list(linhas_os.values_list("id", flat=True))

    total_em_andamento = 0
    total_finalizadas = 0
    total_programadas = 0
    total_outros = 0

    for os_obj in linhas_os:
        status = get_field(
            os_obj,
            "status_operacao",
            "status_da_operacao",
            "status",
            default=""
        )

        if eh_status_em_andamento(status):
            total_em_andamento += 1
        elif eh_status_finalizado(status):
            total_finalizadas += 1
        elif eh_status_programado(status):
            total_programadas += 1
        else:
            total_outros += 1

    rdos = (
        RDO.objects
        .filter(ordem_servico_id__in=ids_os)
        .select_related("ordem_servico")
        .order_by("-id")
    )

    total_rdos = rdos.count()

    alertas_rdo = (
        AlertaInteligente.objects
        .filter(
            rdo__ordem_servico_id__in=ids_os,
            status="pendente",
        )
        .select_related("rdo")
    )

    alertas_operacionais = (
        AlertaOperacionalInteligente.objects
        .filter(
            ordem_servico_id__in=ids_os,
            status="pendente",
        )
        .select_related("ordem_servico")
    )

    anomalias = alertas_rdo.filter(
        tipo__in=["RDO_OUTLIER", "RDO_REVISAR_ANOMALIA"]
    )

    os_sem_rdo_recente = alertas_operacionais.filter(
        tipo="OS_SEM_RDO_RECENTE"
    )

    resumo_por_os = (
        rdos
        .values("ordem_servico__numero_os")
        .annotate(total=Count("id"))
        .order_by("-total")[:10]
    )

    linhas = [
        f"Analisei as operações de {tipo} '{valor}'.",
        "",
        "Resumo operacional:",
        f"- {total_linhas} linha(s) operacional(is) encontrada(s)",
        f"- {total_em_andamento} em andamento",
        f"- {total_finalizadas} finalizada(s)",
        f"- {total_programadas} programada(s)",
        f"- {total_outros} com outro status",
        f"- {total_rdos} RDO(s) vinculado(s)",
        f"- {alertas_rdo.count()} alerta(s) de RDO pendente(s)",
        f"- {alertas_operacionais.count()} alerta(s) operacional(is) pendente(s)",
        f"- {anomalias.count()} anomalia(s) estatística(s)",
        f"- {os_sem_rdo_recente.count()} linha(s) sem RDO recente",
    ]

    if resumo_por_os:
        linhas.append("")
        linhas.append("RDOs por OS:")

        for item in resumo_por_os:
            numero_os = item.get("ordem_servico__numero_os") or "Não informada"
            linhas.append(f"- OS {numero_os}: {item['total']} RDO(s)")

    # Deduplicate OSs (numero_os) to avoid showing same OS multiple times
    # when there are multiple OrdemServico records (linhas operacionais) for the same OS number
    oses_vistas = set()
    linhas_destaque = []
    for os_obj in linhas_os:
        numero_os = get_field(os_obj, "numero_os", "os", default="Não informada")
        if numero_os in oses_vistas:
            continue
        if len(linhas_destaque) >= 8:
            break
        oses_vistas.add(numero_os)
        linhas_destaque.append(os_obj)
    
    if linhas_destaque:
        linhas.append("")
        linhas.append("Linhas em destaque:")
        for os_obj in linhas_destaque:
            numero_os = get_field(os_obj, "numero_os", "os", default="Não informada")
            unidade_nome = get_field(os_obj, "unidade", default="Não informada")
            tanque = get_field(os_obj, "tanque", default="Não informado")
            status = get_field(
                os_obj,
                "status_operacao",
                "status_da_operacao",
                "status",
                default="Não informado",
            )
            linhas.append(
                f"- OS {numero_os} | Unidade: {unidade_nome} | Tanque: {tanque} | Status: {status}"
            )

    pontos = montar_pontos_atencao_contexto(
        alertas_rdo=alertas_rdo,
        alertas_operacionais=alertas_operacionais,
        anomalias=anomalias,
        os_sem_rdo_recente=os_sem_rdo_recente,
    )

    if pontos:
        linhas.append("")
        linhas.append("Principais pontos de atenção:")
        linhas.extend(pontos)

    recomendacao = montar_recomendacao_contexto(
        alertas_rdo,
        alertas_operacionais,
        anomalias,
        os_sem_rdo_recente,
    )

    return {
        "introducao": "\n".join(linhas),
        "alertas": alertas_rdo[:15],
        "alertas_operacionais": alertas_operacionais[:15],
        "recomendacao": recomendacao,
        "fontes": [
            "Home Operacional",
            "RDOs",
            "Alertas inteligentes",
            "Alertas operacionais",
        ],
        "confianca": "alta",
        "tipo_resposta": f"resumo_{tipo}",
    }


def gerar_resumo_empresa(pergunta):
    empresa = extrair_empresa_da_pergunta(pergunta)

    if not empresa:
        return {
            "introducao": (
                "Entendi que você quer um resumo por cliente/empresa, "
                "mas não consegui identificar o nome da empresa na pergunta."
            ),
            "alertas": [],
            "alertas_operacionais": [],
            "recomendacao": "Tente perguntar assim: resuma as operações da Petrobras.",
            "fontes": ["Pergunta do usuário"],
            "confianca": "baixa",
            "tipo_resposta": "resumo_empresa",
        }

    linhas_os = buscar_linhas_por_empresa(empresa)

    return gerar_resumo_contexto_operacional(
        tipo="empresa",
        valor=empresa,
        linhas_os=linhas_os,
    )


def gerar_resumo_unidade(pergunta):
    unidade = extrair_unidade_da_pergunta(pergunta)

    if not unidade:
        return {
            "introducao": (
                "Entendi que você quer um resumo por unidade, "
                "mas não consegui identificar a unidade na pergunta."
            ),
            "alertas": [],
            "alertas_operacionais": [],
            "recomendacao": "Tente perguntar assim: como estão as operações da P-77?",
            "fontes": ["Pergunta do usuário"],
            "confianca": "baixa",
            "tipo_resposta": "resumo_unidade",
        }

    linhas_os = buscar_linhas_por_unidade(unidade)

    return gerar_resumo_contexto_operacional(
        tipo="unidade",
        valor=unidade,
        linhas_os=linhas_os,
    )
