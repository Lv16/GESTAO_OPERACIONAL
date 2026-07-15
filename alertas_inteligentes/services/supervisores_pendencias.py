from collections import defaultdict

from GO.models import RDO
from alertas_inteligentes.models import AlertaInteligente
from alertas_inteligentes.models import AlertaOperacionalInteligente
from alertas_inteligentes.services.field_utils import get_field_safe


def normalizar(texto):
    return str(texto or "").strip().lower()


def get_field(obj, *names, default=None):
    return get_field_safe(obj, *names, default=default)


def obter_supervisor_rdo(rdo):
    os_obj = get_field(rdo, "ordem_servico", default=None)

    supervisor = (
        get_field(rdo, "supervisor", default=None)
        or get_field(os_obj, "supervisor", "supervisor_responsavel", default=None)
        or "Não informado"
    )

    return str(supervisor).strip() or "Não informado"


def obter_identificacao_rdo(rdo):
    os_obj = get_field(rdo, "ordem_servico", default=None)

    numero_os = get_field(os_obj, "numero_os", "os", "numero", default="Não informada")
    numero_rdo = get_field(rdo, "rdo", "numero_rdo", "numero", "id", default=getattr(rdo, "id", ""))
    data = get_field(rdo, "data", "data_rdo", "data_operacao", default=None)

    partes = [f"OS {numero_os}", f"RDO {numero_rdo}"]

    if data:
        try:
            partes.append(data.strftime("%d/%m/%Y"))
        except Exception:
            partes.append(str(data))

    return " | ".join(partes)


def gerar_resposta_supervisores_com_pendencias(limite_alertas=300):
    alertas = (
        AlertaInteligente.objects
        .filter(status="pendente")
        .select_related("rdo", "rdo__ordem_servico")
        .order_by("-prioridade", "-criado_em")[:limite_alertas]
    )

    if not alertas:
        return {
            "introducao": (
                "Não encontrei RDOs com pendências inteligentes vinculadas a supervisores no momento."
            ),
            "alertas": [],
            "alertas_operacionais": [],
            "recomendacao": "Nenhuma ação imediata é necessária para esse ponto.",
            "fontes": ["Alertas inteligentes", "RDOs"],
            "confianca": "alta",
            "tipo_resposta": "supervisores_com_pendencias",
        }

    resumo = defaultdict(lambda: {
        "total_alertas": 0,
        "rdos_ids": set(),
        "rdos": [],
        "tipos": defaultdict(int),
        "prioridades": defaultdict(int),
        "anomalias": 0,
        "preenchimento": 0,
    })

    for alerta in alertas:
        rdo = getattr(alerta, "rdo", None)

        if not rdo:
            continue

        supervisor = obter_supervisor_rdo(rdo)

        dados = resumo[supervisor]
        dados["total_alertas"] += 1
        try:
            dados["rdos_ids"].add(rdo.id)
        except Exception:
            pass

        tipo = getattr(alerta, "tipo", "OUTRO")
        prioridade = getattr(alerta, "prioridade", "media")

        dados["tipos"][tipo] += 1
        dados["prioridades"][prioridade] += 1

        if tipo in ["RDO_OUTLIER", "RDO_REVISAR_ANOMALIA"]:
            dados["anomalias"] += 1

        if tipo in ["RDO_PREENCHIMENTO_RUIM", "RDO_PREENCHIMENTO_FRACO"]:
            dados["preenchimento"] += 1

        if len(dados["rdos"]) < 5:
            dados["rdos"].append({
                "identificacao": obter_identificacao_rdo(rdo),
                "tipo": tipo,
                "tipo_display": alerta.get_tipo_display() if hasattr(alerta, "get_tipo_display") else tipo,
                "prioridade": prioridade,
            })

    # Também agregar alertas operacionais (vinculados à OrdemServico)
    alertas_operacionais = (
        AlertaOperacionalInteligente.objects
        .filter(status="pendente")
        .select_related("ordem_servico")
        .order_by("-prioridade", "-criado_em")[:limite_alertas]
    )

    for alerta in alertas_operacionais:
        os_obj = getattr(alerta, 'ordem_servico', None)
        if not os_obj:
            continue

        supervisor = (
            getattr(os_obj, 'supervisor', None)
            or getattr(os_obj, 'supervisor_responsavel', None)
            or 'Não informado'
        )

        supervisor = str(supervisor).strip() or 'Não informado'

        dados = resumo[supervisor]
        dados['total_alertas'] += 1
        try:
            dados['rdos_ids'].add(getattr(os_obj, 'id', None))
        except Exception:
            pass

        tipo = getattr(alerta, 'tipo', 'OPERACIONAL')
        prioridade = getattr(alerta, 'prioridade', 'media')

        dados['tipos'][tipo] += 1
        dados['prioridades'][prioridade] += 1

        # contar como preenchimento/anomalia se aplicável (não tem os mesmos tipos)
        if tipo in ['OS_SEM_RDO_RECENTE']:
            dados['preenchimento'] += 1

        if len(dados['rdos']) < 5:
            identificacao = getattr(alerta, 'identificacao_operacional', None) or str(os_obj.id)
            dados['rdos'].append({
                'identificacao': identificacao,
                'tipo': tipo,
                'tipo_display': getattr(alerta, 'tipo', tipo),
                'prioridade': prioridade,
            })

    ranking = []

    for supervisor, dados in resumo.items():
        ranking.append({
            "supervisor": supervisor,
            "total_alertas": dados["total_alertas"],
            "total_rdos": len(dados["rdos_ids"]),
            "tipos": dict(dados["tipos"]),
            "prioridades": dict(dados["prioridades"]),
            "anomalias": dados["anomalias"],
            "preenchimento": dados["preenchimento"],
            "rdos": dados["rdos"],
        })

    ranking.sort(
        key=lambda item: (
            item["prioridades"].get("alta", 0),
            item["total_alertas"],
            item["total_rdos"],
        ),
        reverse=True
    )

    linhas = [
        "Analisei os RDOs com alertas pendentes e agrupei por supervisor responsável.",
        "",
        f"Encontrei {len(ranking)} supervisor(es) com RDOs que precisam de revisão.",
        "",
        "Resumo por supervisor:",
    ]

    for idx, item in enumerate(ranking[:15], start=1):
        linhas.append("")
        linhas.append(f"{idx}. {item['supervisor']}")
        linhas.append(f"   - RDOs com pendência: {item['total_rdos']}")
        linhas.append(f"   - Alertas pendentes: {item['total_alertas']}")

        alta = item["prioridades"].get("alta", 0)
        media = item["prioridades"].get("media", 0)
        baixa = item["prioridades"].get("baixa", 0)

        linhas.append(f"   - Prioridades: alta {alta}, média {media}, baixa {baixa}")

        if item["anomalias"]:
            linhas.append(f"   - Anomalias estatísticas: {item['anomalias']}")

        if item["preenchimento"]:
            linhas.append(f"   - Alertas de preenchimento: {item['preenchimento']}")

        if item["rdos"]:
            linhas.append("   - Principais RDOs:")
            for rdo_info in item["rdos"][:3]:
                linhas.append(
                    f"     • {rdo_info['identificacao']} — {rdo_info['tipo_display']} "
                    f"({rdo_info['prioridade']})"
                )

    return {
        "introducao": "\n".join(linhas),
        "alertas": alertas[:20],
        "alertas_operacionais": alertas_operacionais[:20],
        "recomendacao": (
            "Recomendo usar essa análise como apoio para orientar revisões de RDO, "
            "priorizando supervisores com alertas de alta prioridade, anomalias estatísticas "
            "ou grande volume de RDOs pendentes. A análise indica pendências vinculadas aos RDOs, "
            "não uma avaliação individual do supervisor."
        ),
        "fontes": ["Alertas inteligentes", "RDOs", "Home Operacional"],
        "confianca": "média",
        "tipo_resposta": "supervisores_com_pendencias",
    }
