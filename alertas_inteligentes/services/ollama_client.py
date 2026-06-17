import requests
from django.conf import settings


def ollama_disponivel():
    try:
        response = requests.get(
            f"{settings.OLLAMA_BASE_URL}/tags",
            timeout=2,
        )
        return response.status_code == 200
    except requests.RequestException:
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
            f"{settings.OLLAMA_BASE_URL}/generate",
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
            return resposta_base
        return texto
    except (requests.RequestException, ValueError):
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
            f"{settings.OLLAMA_BASE_URL}/generate",
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
    except (requests.RequestException, ValueError):
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
