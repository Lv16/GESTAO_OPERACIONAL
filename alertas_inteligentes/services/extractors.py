import re
from unidecode import unidecode

from GO.models import OrdemServico


def normalizar(texto):
    return str(texto or "").strip().lower()


def normalizar_busca(texto):
    return unidecode(normalizar(texto))


def extrair_entidade_por_padrao(texto, padroes):
    for padrao in padroes:
        match = re.search(padrao, str(texto or ""), flags=re.IGNORECASE)
        if not match:
            continue
        valor = match.group(1).strip()
        valor = re.sub(
            r"\b(tem|possui|com|quais|qual|em|na|no|acontecendo|atualmente|hoje|esta|estao)\b.*",
            "",
            valor,
            flags=re.IGNORECASE,
        ).strip()
        if valor:
            return valor
    return None


def extrair_nome_empresa(texto):
    return extrair_entidade_por_padrao(
        texto,
        (
            r"empresa\s+([a-zA-ZÀ-ÿ0-9\.\-\s]+)",
            r"cliente\s+([a-zA-ZÀ-ÿ0-9\.\-\s]+)",
        ),
    )


def extrair_nome_unidade(texto):
    return extrair_entidade_por_padrao(
        texto,
        (
            r"unidade\s+([a-zA-ZÀ-ÿ0-9\.\-\s]+)",
        ),
    )


def extrair_nome_tanque(texto):
    match = re.search(
        r"tanque\s+(.+?)(?=\s+(?:da|de|na|no)\s+os\b|\s+da\s+ordem\b|[?.,;]|$)",
        str(texto or ""),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    tanque = match.group(1).strip()
    return tanque or None


def extrair_empresa_da_pergunta(pergunta):
    texto = normalizar(pergunta)

    empresas = (
        OrdemServico.objects
        .exclude(Cliente__nome__isnull=True)
        .exclude(Cliente__nome="")
        .values_list("Cliente__nome", flat=True)
        .distinct()
    )

    empresas_ordenadas = sorted(
        [str(e).strip() for e in empresas if str(e).strip()],
        key=len,
        reverse=True
    )

    for empresa in empresas_ordenadas:
        if normalizar(empresa) in texto:
            return empresa

    # fallback regex
    return extrair_nome_empresa(pergunta)


def extrair_unidade_da_pergunta(pergunta):
    texto = normalizar(pergunta)

    unidades = (
        OrdemServico.objects
        .exclude(Unidade__nome__isnull=True)
        .exclude(Unidade__nome="")
        .values_list("Unidade__nome", flat=True)
        .distinct()
    )

    unidades_ordenadas = sorted(
        [str(u).strip() for u in unidades if str(u).strip()],
        key=len,
        reverse=True
    )

    for unidade in unidades_ordenadas:
        unidade_normalizada = normalizar(unidade)
        if len(unidade_normalizada) < 3:
            continue
        if unidade_normalizada in texto:
            return unidade

    # fallback regex
    return extrair_nome_unidade(pergunta)


def extrair_unidade(texto):
    texto_normalizado = normalizar(texto)

    unidades = (
        OrdemServico.objects
        .exclude(Unidade__nome__isnull=True)
        .exclude(Unidade__nome="")
        .values_list("Unidade__nome", flat=True)
        .distinct()
    )

    for unidade in unidades:
        unidade_str = str(unidade).strip()
        unidade_normalizada = normalizar(unidade_str)
        if len(unidade_normalizada) < 3:
            continue
        if unidade_str and unidade_normalizada in texto_normalizado:
            return unidade_str

    return None


def extrair_empresa(texto):
    texto_normalizado = normalizar(texto)

    empresas = (
        OrdemServico.objects
        .exclude(Cliente__nome__isnull=True)
        .exclude(Cliente__nome="")
        .values_list("Cliente__nome", flat=True)
        .distinct()
    )

    for empresa in empresas:
        empresa_str = str(empresa).strip()
        if empresa_str and normalizar(empresa_str) in texto_normalizado:
            return empresa_str

    return None


def extrair_tanque(texto):
    # reuse the regex from analise_supervisores_os
    texto = normalizar(texto)
    padroes = [
        r"tanque\s+([a-zA-Z0-9:\-\/\s\(\)]+)",
    ]

    for padrao in padroes:
        match = re.search(padrao, texto)
        if match:
            tanque = match.group(1).strip()
            tanque = tanque.replace("da os", "").replace("do os", "").strip()
            return tanque.upper()

    return None


def extrair_supervisor(texto):
    for padrao in (
        r"supervisor\s+([a-zA-ZÀ-ÿ\.\s]+)",
        r"supervisora\s+([a-zA-ZÀ-ÿ\.\s]+)",
    ):
        match = re.search(padrao, str(texto or ""), flags=re.IGNORECASE)
        if match:
            nome = match.group(1).strip()
            nome = re.sub(
                r"\b(se\s+encontra|est[aá]|esta|teve|tem|em|na|no|vinculado|vinculada)\b.*",
                "",
                nome,
                flags=re.IGNORECASE,
            ).strip()
            return nome
    return None
