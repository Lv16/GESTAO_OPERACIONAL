import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _ollama_url(path):
    base_url = (getattr(settings, "OLLAMA_BASE_URL", "") or "http://127.0.0.1:11434").rstrip("/")
    path = "/" + str(path or "").lstrip("/")
    if not path.startswith("/api/"):
        path = f"/api{path}"
    return f"{base_url}{path}"


def ollama_disponivel():
    try:
        response = requests.get(
            _ollama_url("/tags"),
            timeout=2,
        )
        return response.status_code == 200
    except requests.RequestException as exc:
        logger.warning("Synchro AI: Ollama indisponivel em %s (%s)", _ollama_url("/tags"), exc)
        return False


def melhorar_resposta_com_ollama(pergunta, dados_contexto, resposta_base):
    if not getattr(settings, "OLLAMA_ENABLED", False):
        return resposta_base

    if not ollama_disponivel():
        return resposta_base

    prompt = f"""
Voce e o assistente operacional do sistema Synchro.

Tarefa:
- Reescreva apenas o texto base abaixo para ficar mais natural e organizado.
- Nao acrescente, remova ou altere nenhum fato.
- Preserve exatamente nomes, numeros, datas e status.
- Nao crie interpretacoes, contexto adicional, urgencia ou conclusoes novas.
- Nao use markdown.
- Preserve a estrutura em blocos curtos, com os mesmos titulos e com as quebras de linha.
- Se nao conseguir cumprir, devolva exatamente o texto base.

Pergunta do usuario:
{pergunta}

Texto base:
{resposta_base}
""".strip()

    try:
        response = requests.post(
            _ollama_url("/generate"),
            json={
                "model": settings.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": 180,
                },
            },
            timeout=getattr(settings, "OLLAMA_TIMEOUT_SECONDS", 20),
        )
        response.raise_for_status()
        data = response.json()
        texto = (data.get("response") or "").strip()
        if not texto or not resposta_fiel(texto, resposta_base):
            logger.warning(
                "Synchro AI: resposta do Ollama ignorada por conteudo vazio ou invalido para %s",
                settings.OLLAMA_MODEL,
            )
            return resposta_base
        return texto
    except requests.Timeout as exc:
        logger.warning("Synchro AI: timeout ao melhorar resposta com Ollama (%s)", exc)
        return resposta_base
    except requests.RequestException as exc:
        logger.exception("Synchro AI: erro de conexao com Ollama ao melhorar resposta: %s", exc)
        return resposta_base
    except ValueError as exc:
        logger.exception("Synchro AI: resposta JSON invalida do Ollama ao melhorar resposta: %s", exc)
        return resposta_base


def classificar_intencao_com_ollama(pergunta):
    if not getattr(settings, "OLLAMA_ENABLED", False):
        return None

    if not ollama_disponivel():
        return None

    prompt = f"""
Classifique a pergunta do usuario para o assistente operacional Synchro.

Responda SOMENTE com uma destas opcoes:
- consulta_os
- consulta_rdo
- consulta_supervisor
- os_sem_rdo_recente
- supervisores_conflito
- pendencias_gerais
- desconhecida

Pergunta:
{pergunta}
""".strip()

    try:
        response = requests.post(
            _ollama_url("/generate"),
            json={
                "model": settings.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0,
                    "num_predict": 20,
                },
            },
            timeout=min(getattr(settings, "OLLAMA_TIMEOUT_SECONDS", 30), 15),
        )
        response.raise_for_status()
        resposta = (response.json().get("response") or "").strip().lower()
        resposta = resposta.splitlines()[0].strip(" .:-")
        opcoes = {
            "consulta_os",
            "consulta_rdo",
            "consulta_supervisor",
            "os_sem_rdo_recente",
            "supervisores_conflito",
            "pendencias_gerais",
            "desconhecida",
        }
        return resposta if resposta in opcoes else None
    except requests.Timeout as exc:
        logger.warning("Synchro AI: timeout ao classificar intencao com Ollama (%s)", exc)
        return None
    except requests.RequestException as exc:
        logger.exception("Synchro AI: erro de conexao com Ollama ao classificar intencao: %s", exc)
        return None
    except ValueError as exc:
        logger.exception("Synchro AI: resposta JSON invalida do Ollama ao classificar intencao: %s", exc)
        return None


def resposta_fiel(texto, resposta_base):
    termos_obrigatorios = [
        termo
        for termo in extrair_termos_relevantes(resposta_base)
        if termo
    ]
    if not termos_obrigatorios:
        return texto.strip() == str(resposta_base or "").strip()
    texto_normalizado = texto.lower()
    return all(termo.lower() in texto_normalizado for termo in termos_obrigatorios)


def extrair_termos_relevantes(resposta_base):
    termos = []
    for linha in str(resposta_base or "").splitlines():
        if ":" not in linha:
            continue
        _, valor = linha.split(":", 1)
        valor = valor.strip()
        if valor and valor.lower() not in {"nao informado", "nao informada"}:
            termos.append(valor)
    return termos
