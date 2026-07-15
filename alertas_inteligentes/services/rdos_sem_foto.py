import json
import logging

from django.utils import timezone

from GO.models import RDO
from alertas_inteligentes.models import AlertaInteligente
from alertas_inteligentes.services.field_utils import get_field_safe
from alertas_inteligentes.services.rdo_validator import get_fotos_count


logger = logging.getLogger(__name__)


def normalizar(texto):
    return str(texto or "").strip().lower()


def get_field(obj, *names, default=None):
    return get_field_safe(obj, *names, default=default)


def bool_true(valor):
    if valor is True:
        return True

    texto = str(valor or "").strip().lower()

    return texto in ["sim", "true", "1", "yes"]


def rdo_tem_foto(rdo):
    """Retorna True se o RDO tiver foto/anexo.

    Usa `get_fotos_count` de `rdo_validator` (já existente no código).
    Como fallback, tenta métodos heurísticos simples.
    """

    # Principal: reutilizar validação já presente no código
    try:
        return get_fotos_count(rdo) > 0
    except Exception:
        logger.exception("get_fotos_count falhou, aplicando heurística para RDO %s", getattr(rdo, 'pk', '?'))

    # Fallback heurístico (menos provável de ser necessário)
    relacionamentos_possiveis = [
        "fotos",
        "imagens",
        "anexos",
        "arquivos",
        "evidencias",
        "fotos_rdo",
        "anexos_rdo",
        "fotos_equipamento",
        "attachments",
        "files",
    ]

    for nome in relacionamentos_possiveis:
        if hasattr(rdo, nome):
            rel = getattr(rdo, nome)
            try:
                if hasattr(rel, "exists") and rel.exists():
                    return True
                if hasattr(rel, "count") and rel.count() > 0:
                    return True
                if isinstance(rel, (list, tuple, set)) and len(rel) > 0:
                    return True
            except Exception:
                pass

    campos_arquivo_possiveis = [
        "fotos_img",
        "fotos_1",
        "fotos_2",
        "fotos_3",
        "fotos_4",
        "fotos_5",
        "fotos_json",
        "foto",
        "imagem",
        "anexo",
        "arquivo",
        "evidencia",
        "foto_1",
        "foto_2",
        "foto_3",
    ]

    for nome in campos_arquivo_possiveis:
        valor = get_field(rdo, nome, default=None)
        if not valor:
            continue
        if nome == "fotos_json":
            try:
                parsed = json.loads(valor) if isinstance(valor, str) else valor
                if isinstance(parsed, list) and any(x for x in parsed):
                    return True
                if isinstance(parsed, dict) and parsed:
                    return True
            except Exception:
                pass
        try:
            if getattr(valor, "name", None):
                if str(getattr(valor, "name", "")).strip():
                    return True
        except Exception:
            pass
        try:
            if isinstance(valor, (list, tuple, set)) and len(valor) > 0:
                if any(bool(str(x or "").strip()) for x in valor):
                    return True
        except Exception:
            pass
        try:
            if isinstance(valor, str) and valor.strip():
                return True
        except Exception:
            pass

    return False


def rdo_sem_foto_prioridade(rdo):
    houve_pt = get_field(
        rdo,
        "houve_abertura_pt",
        "abertura_pt",
        "teve_pt",
        default=False
    )

    houve_espaco_confinado = get_field(
        rdo,
        "houve_acesso_espaco_confinado",
        "acesso_espaco_confinado",
        "espaco_confinado",
        default=False
    )

    percentual_avanco = get_field(
        rdo,
        "percentual_avanco",
        "avanco_percentual",
        "percentual_total",
        default=0
    )

    try:
        percentual_avanco = float(str(percentual_avanco).replace(",", "."))
    except Exception:
        percentual_avanco = 0

    if bool_true(houve_pt):
        return "alta"

    if bool_true(houve_espaco_confinado):
        return "alta"

    if percentual_avanco >= 20:
        return "alta"

    return "media"


def identificar_rdo(rdo):
    os_obj = get_field(rdo, "ordem_servico", default=None)

    numero_os = get_field(
        os_obj,
        "numero_os",
        "os",
        "numero",
        default="Não informada"
    )

    numero_rdo = get_field(
        rdo,
        "numero_rdo",
        "numero",
        "rdo",
        "id",
        default=getattr(rdo, "id", "")
    )

    data = get_field(
        rdo,
        "data",
        "data_rdo",
        "data_operacao",
        default=None
    )

    supervisor = (
        get_field(rdo, "supervisor", default=None)
        or get_field(os_obj, "supervisor", "supervisor_responsavel", default=None)
        or "Não informado"
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


def listar_rdos_sem_foto(limite=None):
    rdos = RDO.objects.select_related("ordem_servico").order_by("-id")

    if limite is not None:
        rdos = rdos[:limite]

    resultados = []

    for rdo in rdos:
        try:
            if not rdo_tem_foto(rdo):
                prioridade = rdo_sem_foto_prioridade(rdo)

                resultados.append(
                    {
                        "rdo": rdo,
                        "identificacao": identificar_rdo(rdo),
                        "prioridade": prioridade,
                    }
                )
        except Exception:
            logger.exception("Falha ao avaliar RDO %s para fotos", getattr(rdo, "pk", "?"))
            continue

    resultados.sort(key=lambda item: 0 if item["prioridade"] == "alta" else 1)
    return resultados


def gerar_resposta_rdos_sem_foto(limite=None):
    resultados = listar_rdos_sem_foto(limite=limite)
    escopo = f"os ultimos {limite} RDOs" if limite is not None else "todos os RDOs disponiveis"

    if not resultados:
        return {
            "introducao": (
                f"Analisei {escopo} e nao encontrei RDOs sem foto ou anexo."
            ),
            "alertas": [],
            "alertas_operacionais": [],
            "recomendacao": "Nenhuma ação imediata é necessária para esse ponto.",
            "fontes": ["RDOs", "Fotos/anexos"],
            "confianca": "alta",
            "tipo_resposta": "rdos_sem_foto",
        }

    total_alta = sum(1 for item in resultados if item["prioridade"] == "alta")
    total_media = sum(1 for item in resultados if item["prioridade"] == "media")

    linhas = [
        f"Analisei {escopo} e encontrei {len(resultados)} RDO(s) sem foto ou anexo vinculado.",
        "",
        "Resumo:",
        f"- {total_alta} caso(s) de prioridade alta",
        f"- {total_media} caso(s) de prioridade média",
        "",
        "Critério utilizado:",
        "- todo RDO deve possuir evidência fotográfica/anexo.",
        "- casos com PT, espaço confinado ou avanço relevante foram tratados como prioridade alta.",
        "",
        "Principais RDOs sem foto/anexo:",
    ]

    for idx, item in enumerate(resultados[:20], start=1):
        linhas.append("")
        linhas.append(f"{idx}. {item['identificacao']}")
        linhas.append(f"   Prioridade sugerida: {item['prioridade'].upper()}")

    alertas = (
        AlertaInteligente.objects
        .filter(
            rdo__in=[item["rdo"] for item in resultados[:30]],
            status="pendente",
        )
        .select_related("rdo")[:20]
    )

    return {
        "introducao": "\n".join(linhas),
        "alertas": alertas,
        "alertas_operacionais": [],
        "recomendacao": (
            "Recomendo solicitar revisão dos RDOs sem foto/anexo, principalmente os de prioridade alta. "
            "Como a evidência fotográfica é obrigatória, esses RDOs podem comprometer a validação operacional."
        ),
        "fontes": ["RDOs", "Fotos/anexos", "Alertas inteligentes"],
        "confianca": "alta",
        "tipo_resposta": "rdos_sem_foto",
    }
