from GO.models import RDO
from alertas_inteligentes.models import AlertaInteligente
from alertas_inteligentes.services.field_utils import get_field_safe


def normalizar(texto):
    return str(texto or "").strip().lower()


def get_field(obj, *names, default=None):
    return get_field_safe(obj, *names, default=default)


def obter_data_operacional_rdo(rdo):
    return get_field(
        rdo,
        "data",
        "data_rdo",
        "data_operacao",
        "data_da_operacao",
        default=None,
    )


def obter_data_lancamento_rdo(rdo):
    data_lancamento = get_field(
        rdo,
        "criado_em",
        "created_at",
        "data_criacao",
        "data_lancamento",
        "dt_criacao",
        "created",
        "created_on",
        default=None,
    )

    if data_lancamento:
        if hasattr(data_lancamento, "date"):
            return data_lancamento.date()
        return data_lancamento

    try:
        tanque_snapshot = rdo.tanques.order_by("created_at").first()
    except Exception:
        tanque_snapshot = None

    if tanque_snapshot:
        data_lancamento = get_field(tanque_snapshot, "created_at", default=None)
        if hasattr(data_lancamento, "date"):
            return data_lancamento.date()
        return data_lancamento

    return None


def avaliar_lancamento_atrasado(rdo, limite_dias=2):
    data_operacional = obter_data_operacional_rdo(rdo)
    data_lancamento = obter_data_lancamento_rdo(rdo)

    if not data_operacional or not data_lancamento:
        return None

    try:
        dias_atraso = (data_lancamento - data_operacional).days
    except Exception:
        return None

    if dias_atraso <= limite_dias:
        return None

    if dias_atraso >= 5:
        nivel = "alto"
    elif dias_atraso >= 3:
        nivel = "medio"
    else:
        nivel = "baixo"

    return {
        "rdo": rdo,
        "data_operacional": data_operacional,
        "data_lancamento": data_lancamento,
        "dias_atraso": dias_atraso,
        "nivel": nivel,
    }


def avaliar_lancamento_fora_do_dia(rdo):
    data_operacional = obter_data_operacional_rdo(rdo)
    data_lancamento = obter_data_lancamento_rdo(rdo)

    if not data_operacional or not data_lancamento:
        return None

    try:
        dias_atraso = (data_lancamento - data_operacional).days
    except Exception:
        return None

    if dias_atraso < 1:
        return None

    if dias_atraso >= 3:
        nivel = "alto"
    elif dias_atraso >= 2:
        nivel = "medio"
    else:
        nivel = "baixo"

    return {
        "rdo": rdo,
        "data_operacional": data_operacional,
        "data_lancamento": data_lancamento,
        "dias_atraso": dias_atraso,
        "nivel": nivel,
    }


def identificar_rdo(rdo):
    os_obj = get_field(rdo, "ordem_servico", default=None)

    numero_os = get_field(os_obj, "numero_os", "os", "numero", default="Nao informada")
    numero_rdo = get_field(rdo, "rdo", "numero_rdo", "numero", "id", default=getattr(rdo, "id", ""))
    data = obter_data_operacional_rdo(rdo)

    supervisor = (
        get_field(rdo, "supervisor", default=None)
        or get_field(os_obj, "supervisor", "supervisor_responsavel", default=None)
        or "Nao informado"
    )

    unidade = get_field(os_obj, "unidade", default=None)
    tanque = get_field(os_obj, "tanque", default=None)

    partes = [f"OS {numero_os}", f"RDO {numero_rdo}"]

    if data:
        try:
            partes.append(data.strftime("%d/%m/%Y"))
        except Exception:
            partes.append(str(data))

    if unidade:
        partes.append(str(unidade))

    if tanque:
        partes.append(f"Tanque {tanque}")

    partes.append(f"Supervisor: {supervisor}")

    return " | ".join(partes)


def listar_rdos_lancamento_atrasado(limite=None, limite_dias=2):
    rdos = RDO.objects.select_related("ordem_servico").order_by("-id")

    if limite is not None:
        rdos = rdos[:limite]

    resultados = []

    for rdo in rdos:
        avaliacao = avaliar_lancamento_atrasado(rdo, limite_dias=limite_dias)
        if avaliacao:
            avaliacao["identificacao"] = identificar_rdo(rdo)
            resultados.append(avaliacao)

    resultados.sort(key=lambda item: item["dias_atraso"], reverse=True)
    return resultados


def listar_rdos_lancados_fora_do_dia(limite=None):
    rdos = RDO.objects.select_related("ordem_servico").order_by("-id")

    if limite is not None:
        rdos = rdos[:limite]

    resultados = []

    for rdo in rdos:
        avaliacao = avaliar_lancamento_fora_do_dia(rdo)
        if avaliacao:
            avaliacao["identificacao"] = identificar_rdo(rdo)
            resultados.append(avaliacao)

    resultados.sort(key=lambda item: (item["dias_atraso"], item["rdo"].id), reverse=True)
    return resultados


def gerar_resposta_lancamento_atrasado(limite=None, limite_dias=2):
    resultados = listar_rdos_lancamento_atrasado(limite=limite, limite_dias=limite_dias)
    escopo = f"os ultimos {limite} RDOs" if limite is not None else "todos os RDOs disponiveis"

    if not resultados:
        return {
            "introducao": (
                f"Analisei {escopo} e nao encontrei lancamentos atrasados acima de {limite_dias} dia(s)."
            ),
            "alertas": [],
            "alertas_operacionais": [],
            "recomendacao": "Nenhuma acao imediata e necessaria para esse ponto no momento.",
            "fontes": ["RDOs", "Data operacional", "Data de criacao/lancamento"],
            "confianca": "alta",
            "tipo_resposta": "lancamento_atrasado_rdo",
        }

    total_alto = sum(1 for item in resultados if item["nivel"] == "alto")
    total_medio = sum(1 for item in resultados if item["nivel"] == "medio")
    total_baixo = sum(1 for item in resultados if item["nivel"] == "baixo")

    linhas = [
        f"Analisei {escopo} e encontrei {len(resultados)} RDO(s) com possivel lancamento atrasado.",
        "",
        "Criterio utilizado:",
        f"- diferenca maior que {limite_dias} dia(s) entre a data operacional do RDO e a data em que ele foi criado ou lancado no sistema.",
        "",
        "Resumo:",
        f"- {total_alto} caso(s) com atraso alto",
        f"- {total_medio} caso(s) com atraso medio",
        f"- {total_baixo} caso(s) com atraso baixo",
        "",
        "Principais RDOs identificados:",
    ]

    for idx, item in enumerate(resultados[:15], start=1):
        linhas.append("")
        linhas.append(f"{idx}. {item['identificacao']}")
        linhas.append(f"   Nivel: {item['nivel'].upper()}")
        linhas.append(
            f"   - Data operacional: {item['data_operacional'].strftime('%d/%m/%Y')}"
        )
        linhas.append(
            f"   - Data de lancamento ou criacao: {item['data_lancamento'].strftime('%d/%m/%Y')}"
        )
        linhas.append(f"   - Atraso identificado: {item['dias_atraso']} dia(s)")

    rdos_com_atraso = [item["rdo"] for item in resultados[:30]]

    alertas = (
        AlertaInteligente.objects
        .filter(
            rdo__in=rdos_com_atraso,
            status="pendente",
        )
        .select_related("rdo")[:20]
    )

    return {
        "introducao": "\n".join(linhas),
        "alertas": alertas,
        "alertas_operacionais": [],
        "recomendacao": (
            "Recomendo revisar os RDOs com maior atraso primeiro, principalmente quando o lancamento ocorreu varios dias apos a operacao. "
            "Isso pode indicar preenchimento retroativo, atraso no envio do supervisor ou necessidade de ajuste no fluxo de cobranca e validacao dos RDOs."
        ),
        "fontes": ["RDOs", "Data operacional", "Data de criacao/lancamento", "Alertas inteligentes"],
        "confianca": "alta",
        "tipo_resposta": "lancamento_atrasado_rdo",
    }
