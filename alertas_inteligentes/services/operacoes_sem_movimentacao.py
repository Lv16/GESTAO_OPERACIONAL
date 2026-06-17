from decimal import Decimal, InvalidOperation
from datetime import timedelta, time as dt_time

from django.utils import timezone

from GO.models import RDO, OrdemServico
from alertas_inteligentes.models import AlertaOperacionalInteligente
from alertas_inteligentes.services.field_utils import get_field_safe


def normalizar(texto):
    return str(texto or "").strip().lower()


def get_field(obj, *names, default=None):
    return get_field_safe(obj, *names, default=default)


def to_decimal(valor):
    if valor in [None, ""]:
        return Decimal("0")

    try:
        return Decimal(str(valor).replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _duration_to_decimal_hours(value):
    if value in (None, ""):
        return Decimal("0")
    try:
        if isinstance(value, timedelta):
            return Decimal(value.total_seconds()) / Decimal(3600)
        if hasattr(value, 'hour') and hasattr(value, 'minute'):
            hours = Decimal(getattr(value, 'hour', 0)) + (Decimal(getattr(value, 'minute', 0)) / Decimal(60))
            return hours
        return to_decimal(value)
    except Exception:
        return Decimal("0")


def eh_status_em_andamento(valor):
    texto = normalizar(valor)

    return texto in [
        "em andamento",
        "andamento",
        "em_andamento",
        "em andamento",
    ]


def identificar_linha_operacional(os_obj):
    numero_os = get_field(os_obj, "numero_os", "os", "numero", default=getattr(os_obj, "id", ""))
    unidade = get_field(os_obj, "unidade", default=None)
    tanque = get_field(os_obj, "tanque", default=None)
    supervisor = get_field(os_obj, "supervisor", "supervisor_responsavel", default=None)

    partes = [f"OS {numero_os}", f"Linha {getattr(os_obj, 'id', '')}"]

    if unidade:
        partes.append(str(unidade))

    if tanque:
        partes.append(f"Tanque {tanque}")

    if supervisor:
        partes.append(f"Supervisor: {supervisor}")

    return " | ".join(partes)


def buscar_rdos_da_linha(os_obj, limite=3):
    return list(
        RDO.objects
        .filter(ordem_servico=os_obj)
        .select_related("ordem_servico")
        .order_by("-data", "-id")[:limite]
    )


def extrair_metricas_rdo(rdo):
    return {
        "ensacamento": to_decimal(get_field(rdo, "ensacamento_cumulativo", "ensacamento", "ensacamento_total", default=0)),
        "cambagem": to_decimal(get_field(rdo, "cambagem_cumulativo", "cambagem", "cambagem_total", default=0)),
        "icamento": to_decimal(get_field(rdo, "icamento_cumulativo", "icamento", "icamento_total", default=0)),
        "tempo_bomba": _duration_to_decimal_hours(get_field(rdo, "tempo_uso_bomba", "total_hh_cumulativo_real", default=0)),
        "avanco_percentual": to_decimal(get_field(rdo, "percentual_avanco_cumulativo", "percentual_avanco", default=0)),
    }


def calcular_variacao_metricas(rdos):
    """
    Recebe os RDOs em ordem desc:
    [mais_recente, anterior, ...]
    """
    if len(rdos) < 2:
        return {
            "tem_comparacao": False,
            "houve_avanco": False,
            "variacoes": {},
        }

    mais_recente = rdos[0]
    anterior = rdos[1]

    atual = extrair_metricas_rdo(mais_recente)
    base = extrair_metricas_rdo(anterior)

    variacoes = {}

    for campo, valor_atual in atual.items():
        valor_anterior = base.get(campo, Decimal("0"))
        variacoes[campo] = valor_atual - valor_anterior

    houve_avanco = any(valor > 0 for valor in variacoes.values())

    return {
        "tem_comparacao": True,
        "houve_avanco": houve_avanco,
        "variacoes": variacoes,
    }


def analisar_linha_sem_movimentacao(os_obj, dias_sem_rdo_limite=2):
    status_operacao = get_field(
        os_obj,
        "status_operacao",
        "status_da_operacao",
        "status",
        default=""
    )

    if not eh_status_em_andamento(status_operacao):
        return None

    hoje = timezone.localdate()

    rdos = buscar_rdos_da_linha(os_obj, limite=3)

    if not rdos:
        return {
            "os_obj": os_obj,
            "identificacao": identificar_linha_operacional(os_obj),
            "nivel": "alto",
            "motivos": [
                "Linha operacional em andamento sem nenhum RDO vinculado."
            ],
            "dias_sem_rdo": None,
            "variacoes": {},
        }

    ultimo_rdo = rdos[0]
    data_ultimo_rdo = get_field(ultimo_rdo, "data", "data_rdo", "data_operacao", default=None)

    motivos = []
    nivel = "medio"
    dias_sem_rdo = None

    if data_ultimo_rdo:
        try:
            dias_sem_rdo = (hoje - data_ultimo_rdo).days
        except Exception:
            dias_sem_rdo = None

        if dias_sem_rdo is not None and dias_sem_rdo >= dias_sem_rdo_limite:
            motivos.append(
                f"Último RDO registrado há {dias_sem_rdo} dia(s), em {data_ultimo_rdo.strftime('%d/%m/%Y')}."
            )

    variacao = calcular_variacao_metricas(rdos)

    if variacao["tem_comparacao"] and not variacao["houve_avanco"]:
        motivos.append(
            "Não identifiquei avanço nos principais indicadores entre os dois últimos RDOs."
        )

    if dias_sem_rdo and dias_sem_rdo >= 3:
        nivel = "alto"

    if variacao["tem_comparacao"] and not variacao["houve_avanco"] and dias_sem_rdo and dias_sem_rdo >= 2:
        nivel = "alto"

    if not motivos:
        return None

    return {
        "os_obj": os_obj,
        "identificacao": identificar_linha_operacional(os_obj),
        "nivel": nivel,
        "motivos": motivos,
        "dias_sem_rdo": dias_sem_rdo,
        "variacoes": variacao.get("variacoes", {}),
    }


def gerar_resposta_operacoes_sem_movimentacao():
    ordens = OrdemServico.objects.all().order_by("-id")

    resultados = []

    for os_obj in ordens:
        resultado = analisar_linha_sem_movimentacao(os_obj)

        if resultado:
            resultados.append(resultado)

    resultados.sort(
        key=lambda item: (
            0 if item["nivel"] == "alto" else 1,
            -(item["dias_sem_rdo"] or 0)
        )
    )

    total = len(resultados)

    if total == 0:
        return {
            "introducao": (
                "Não encontrei operações em andamento com sinais relevantes de falta de movimentação."
            ),
            "alertas": [],
            "alertas_operacionais": [],
            "recomendacao": "Nenhuma ação imediata é necessária para esse ponto no momento.",
            "fontes": ["Home Operacional", "RDOs"],
            "confianca": "alta",
            "tipo_resposta": "operacoes_sem_movimentacao",
        }

    linhas = [
        f"Encontrei {total} linha(s) operacional(is) com possível falta de movimentação recente.",
        "",
        "Critérios considerados:",
        "- status da operação em andamento",
        "- ausência de RDO recente",
        "- ausência de avanço entre os últimos RDOs",
        "- variação nos indicadores de ensacamento, cambagem, içamento, tempo de bomba e avanço percentual",
        "",
        "Principais operações identificadas:",
    ]

    for idx, item in enumerate(resultados[:15], start=1):
        linhas.append("")
        linhas.append(f"{idx}. {item['identificacao']}")
        linhas.append(f"   Nível: {item['nivel'].upper()}")

        for motivo in item["motivos"]:
            linhas.append(f"   - {motivo}")

        variacoes = item.get("variacoes") or {}

        if variacoes:
            variacoes_texto = []

            for campo, valor in variacoes.items():
                if valor != 0:
                    variacoes_texto.append(f"{campo}: {valor}")

            if variacoes_texto:
                linhas.append("   Variações identificadas:")
                for texto in variacoes_texto:
                    linhas.append(f"   - {texto}")

    alertas_operacionais = AlertaOperacionalInteligente.objects.filter(
        status="pendente",
        tipo="OS_SEM_RDO_RECENTE"
    ).select_related("ordem_servico")[:15]

    return {
        "introducao": "\n".join(linhas),
        "alertas": [],
        "alertas_operacionais": alertas_operacionais,
        "recomendacao": (
            "Recomendo verificar primeiro as linhas classificadas como nível ALTO, "
            "principalmente as que estão em andamento e sem RDO recente. "
            "Caso a operação tenha sido encerrada, atualize o status da linha operacional."
        ),
        "fontes": ["Home Operacional", "RDOs", "Alertas operacionais"],
        "confianca": "média",
        "tipo_resposta": "operacoes_sem_movimentacao",
    }
