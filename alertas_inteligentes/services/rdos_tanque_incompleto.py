from alertas_inteligentes.models import AlertaInteligente
from GO.models import RDO
from alertas_inteligentes.services.chat_formatters import formatar_tanque_incompleto


def listar_achados_dinamicos_tanque_incompleto(numero_os=None, limite=None):
    rdos = RDO.objects.select_related("ordem_servico").order_by("-id")
    if numero_os:
        rdos = rdos.filter(ordem_servico__numero_os=numero_os)
    if limite is not None:
        rdos = rdos[:limite]

    persistidos = {
        alerta.rdo_id
        for alerta in AlertaInteligente.objects.filter(
            tipo="RDO_TANQUE_INCOMPLETO",
            status="pendente",
        )
    }

    resultados = []

    for rdo in rdos:
        if rdo.id in persistidos:
            continue

        try:
            tanques = list(rdo.tanques.all())
        except Exception:
            tanques = []

        for tanque in tanques:
            nome_tanque = (
                getattr(tanque, "nome_tanque", None)
                or getattr(tanque, "tanque_codigo", None)
                or getattr(tanque, "tanque", None)
                or f"Tanque {getattr(tanque, 'id', '')}".strip()
            )
            tipo_tanque = getattr(tanque, "tipo_tanque", None)
            numero_compartimentos = getattr(tanque, "numero_compartimentos", None)
            volume_tanque = (
                getattr(tanque, "volume_tanque_exec", None)
                or getattr(tanque, "volume_tanque", None)
                or getattr(tanque, "volume", None)
            )

            faltando = []
            if not tipo_tanque:
                faltando.append("tipo de tanque")
            if numero_compartimentos in (None, ""):
                faltando.append("numero de compartimentos")
            if volume_tanque in (None, ""):
                faltando.append("volume do tanque")

            if not faltando:
                continue

            resultados.append(
                {
                    "rdo": rdo,
                    "nome_tanque": nome_tanque,
                    "faltando": faltando,
                    "mensagem": (
                        f"O tanque {nome_tanque} esta com dados incompletos neste RDO. "
                        f"Campos faltando: {', '.join(faltando)}."
                    ),
                }
            )
            break

    return resultados


def _criar_alerta_sintetico_tanque_incompleto(item):
    from alertas_inteligentes.services.alertas_rdo_consolidados import AlertaRdoSintetico

    return AlertaRdoSintetico(
        rdo=item["rdo"],
        tipo="RDO_TANQUE_INCOMPLETO",
        prioridade="alta",
        equipe_responsavel="rdo",
        mensagem=item["mensagem"],
        explicacao_curta="Este RDO tem tanque com dados obrigatorios incompletos.",
        acao_recomendada=(
            "Revise o cadastro do tanque no RDO e preencha tipo de tanque, numero de compartimentos "
            "e volume para manter os calculos operacionais consistentes."
        ),
    )


def gerar_resposta_rdos_tanque_incompleto(limite=10, numero_os=None):
    alertas_persistidos = list(
        AlertaInteligente.objects
        .filter(
            tipo="RDO_TANQUE_INCOMPLETO",
            status="pendente",
        )
        .select_related("rdo", "rdo__ordem_servico")
        .order_by("-criado_em")
    )

    if numero_os:
        alertas_persistidos = [
            alerta for alerta in alertas_persistidos
            if getattr(getattr(alerta, "rdo", None), "ordem_servico", None)
            and str(getattr(alerta.rdo.ordem_servico, "numero_os", "")) == str(numero_os)
        ]

    alertas_dinamicos = [
        _criar_alerta_sintetico_tanque_incompleto(item)
        for item in listar_achados_dinamicos_tanque_incompleto(numero_os=numero_os)
    ]

    alertas = alertas_persistidos + alertas_dinamicos
    total = len(alertas)
    escopo = f" na OS {numero_os}" if numero_os else ""

    if total == 0:
        return {
            "introducao": f"Nao encontrei RDOs com tanque incompleto{escopo} no momento.",
            "alertas": [],
            "alertas_operacionais": [],
            "recomendacao": "Nenhuma acao imediata e necessaria para esse ponto.",
            "fontes": ["Alertas inteligentes", "RDOs", "Dados do tanque"],
            "confianca": "alta",
            "tipo_resposta": "rdos_tanque_incompleto",
        }

    return {
        "introducao": formatar_tanque_incompleto(alertas, total=total, numero_os=numero_os, limite=limite),
        "alertas": alertas[:limite],
        "alertas_operacionais": [],
        "ocultar_alertas": True,
        "recomendacao": (
            "Recomendo revisar esses RDOs com a equipe responsável, porque dados incompletos do tanque "
            "afetam cálculos de avanço, análise por compartimento e validações operacionais."
        ),
        "fontes": ["Alertas inteligentes", "RDOs", "Dados do tanque"],
        "confianca": "alta",
        "tipo_resposta": "rdos_tanque_incompleto",
    }
