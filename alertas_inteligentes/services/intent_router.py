import re
from unidecode import unidecode

from alertas_inteligentes.services.aprendizado_ia import buscar_intencao_aprendida
from alertas_inteligentes.services.ollama_client import classificar_intencao_com_ollama
from alertas_inteligentes.services import extractors


def normalizar(texto):
    return unidecode(str(texto or "").strip().lower())


def match_any(texto, termos):
    texto = normalizar(texto)
    return any(termo in texto for termo in termos)


def classificar_por_regras(pergunta):
    texto = normalizar(pergunta)

    if match_any(texto, [
        "o que mudou entre",
        "diferenca entre",
        "diferença entre",
    ]) or ("compare" in texto and "rdo" in texto):
        return "comparacao_rdos"

    # Mudancas desde ontem
    if match_any(texto, [
        "o que mudou desde ontem",
        "mudou desde ontem",
        "mudancas desde ontem",
        "novidades desde ontem",
    ]):
        return "mudancas_desde_ontem"

    # Operacoes sem movimentacao
    if match_any(texto, [
        "sem movimentação",
        "sem movimentacao",
        "sem avanço",
        "sem avanco",
        "sem progresso",
        "operações paradas",
        "operacoes paradas",
    ]):
        return "operacoes_sem_movimentacao"

    # RDOs com preenchimento ruim
    if match_any(texto, [
        "preenchimento ruim",
        "preenchimento fraco",
        "rdos ruins",
        "rdos incompletos",
    ]):
        return "rdos_preenchimento_ruim"

    # Resumo por empresa/unidade
    if match_any(texto, ["resumo por cliente", "resumo por empresa", "resuma as operações", "como estão as operações"]):
        # tente identificar empresa/unidade explicitamente
        empresa = extractors.extrair_empresa_da_pergunta(pergunta)
        unidade = extractors.extrair_unidade_da_pergunta(pergunta)
        if unidade:
            return "resumo_unidade"
        if empresa:
            return "resumo_empresa"

    # Lancamento atrasado
    if match_any(texto, [
        "lançamento atrasado",
        "lancamento atrasado",
        "rdos lançados atrasados",
        "preenchimento retroativo",
        "atraso no lançamento",
    ]):
        return "lancamento_atrasado"

    # Supervisores com pendencias
    if match_any(texto, [
        "supervisores com pendência",
        "supervisores com pendencia",
        "ranking de supervisores",
        "supervisores com rdos pendentes",
    ]):
        return "supervisores_com_pendencias"

    # Também aceitar menções separadas (ex: "quais supervisores têm mais RDOs com pendência?")
    if "supervisores" in texto and "pendencia" in texto:
        return "supervisores_com_pendencias"

    # Comparar supervisores por tanque (ex: "Compare os supervisores no tanque 03P COT")
    if ("compar" in texto or "compare" in texto or "compare os" in texto) and "supervisor" in texto and "tanque" in texto:
        return "supervisores_por_tanque"

    # RDOs por periodo (datas explicitas)
    if re.search(r"\b\d{2}/\d{2}/\d{4}\b", pergunta):
        return "rdos_por_periodo"

    # OS / RDO / Supervisor specific queries
    if re.search(r"\brdo\b\s*\d+", pergunta, flags=re.IGNORECASE):
        return "consulta_rdo"

    if re.search(r"\bos\b\s*\d+", pergunta, flags=re.IGNORECASE):
        return "consulta_os"

    if "supervisor" in texto or "supervisora" in texto or "supervisores" in texto:
        return "consulta_supervisor"

    return None


def classify_intent(pergunta, contexto=None):
    """Classifica a intenção da pergunta.

    Ordem de prioridade: regras fixas > aprendizado supervisionado > Ollama.
    Retorna um dict: { 'intent': str|None, 'source': 'rule'|'learned'|'ollama'|'none', 'confidence': float }
    """
    contexto = contexto or {}

    # 1) Regras fixas
    intent = classificar_por_regras(pergunta)
    if intent:
        return {"intent": intent, "source": "rule", "confidence": 0.95}

    # 2) Aprendizado supervisionado
    try:
        aprendido = buscar_intencao_aprendida(pergunta)
    except Exception:
        aprendido = None

    if aprendido:
        return {"intent": aprendido, "source": "learned", "confidence": 0.8}

    # 3) Ollama (fallback)
    try:
        ollama_intent = classificar_intencao_com_ollama(pergunta)
    except Exception:
        ollama_intent = None

    if ollama_intent:
        return {"intent": ollama_intent, "source": "ollama", "confidence": 0.6}

    return {"intent": None, "source": "none", "confidence": 0.0}
