import re
from collections import Counter
from types import SimpleNamespace


MOJIBAKE_MARKERS = ("Ã", "Â", "â€™", "â€œ", "â€", "ðŸ")


def corrigir_mojibake(texto):
    if not texto or not isinstance(texto, str):
        return texto

    if not any(marker in texto for marker in MOJIBAKE_MARKERS):
        return texto

    try:
        return texto.encode("latin1").decode("utf-8")
    except Exception:
        return texto


def sanitizar_texto_chat(texto):
    texto = corrigir_mojibake(texto)
    if not isinstance(texto, str):
        return texto
    return texto.replace("\r\n", "\n").replace("\r", "\n").strip()


def sanitizar_alerta_para_chat(alerta):
    dados = {}
    campos_texto = (
        "mensagem",
        "explicacao_curta",
        "acao_recomendada",
        "anomalia_titulo_operacional",
        "anomalia_subtitulo_operacional",
        "anomalia_contexto",
        "anomalia_base_comparacao",
    )
    for campo in campos_texto:
        dados[campo] = sanitizar_texto_chat(getattr(alerta, campo, None))

    dados["anomalia_metricas_principais"] = None
    if hasattr(alerta, "anomalia_metricas_principais") and getattr(alerta, "anomalia_metricas_principais", None):
        dados["anomalia_metricas_principais"] = [
            sanitizar_texto_chat(item)
            for item in (alerta.anomalia_metricas_principais or [])
        ]

    dados["anomalia_metricas_avaliadas"] = None
    if hasattr(alerta, "anomalia_metricas_avaliadas") and getattr(alerta, "anomalia_metricas_avaliadas", None):
        dados["anomalia_metricas_avaliadas"] = [
            sanitizar_texto_chat(item)
            for item in (alerta.anomalia_metricas_avaliadas or [])
        ]

    dados["anomalia_principal_motivo"] = None
    if hasattr(alerta, "anomalia_principal_motivo") and getattr(alerta, "anomalia_principal_motivo", None):
        dados["anomalia_principal_motivo"] = [
            sanitizar_texto_chat(item)
            for item in (alerta.anomalia_principal_motivo or [])
        ]

    class AlertaChatProxy(SimpleNamespace):
        def __init__(self, origem, **kwargs):
            super().__init__(**kwargs)
            self._origem = origem

        def __getattr__(self, item):
            return getattr(self._origem, item)

    return AlertaChatProxy(alerta, **dados)


def sanitizar_resultado_chat(resultado):
    if not isinstance(resultado, dict):
        return resultado

    for campo in ("introducao", "recomendacao", "confianca", "tipo_resposta"):
        if campo in resultado:
            resultado[campo] = sanitizar_texto_chat(resultado.get(campo))

    if isinstance(resultado.get("fontes"), (list, tuple)):
        resultado["fontes"] = [sanitizar_texto_chat(item) for item in resultado["fontes"]]

    if isinstance(resultado.get("linha_tempo"), (list, tuple)):
        for item in resultado["linha_tempo"]:
            if isinstance(item, dict):
                item["data"] = sanitizar_texto_chat(item.get("data"))
                item["descricao"] = sanitizar_texto_chat(item.get("descricao"))

    for chave in ("alertas", "alertas_operacionais"):
        itens = resultado.get(chave)
        if itens is not None:
            try:
                resultado[chave] = [sanitizar_alerta_para_chat(alerta) for alerta in list(itens)]
            except TypeError:
                pass

    return resultado


def _normalizar_campo_faltando(campo):
    campo = sanitizar_texto_chat(campo or "").lower()
    mapa = {
        "tipo de tanque": "tipo de tanque",
        "numero de compartimentos": "nº de compartimentos",
        "número de compartimentos": "nº de compartimentos",
        "nº de compartimentos": "nº de compartimentos",
        "volume do tanque": "volume do tanque",
    }
    return mapa.get(campo.rstrip(".;:"), campo.rstrip(".;:"))


def _extrair_campos_faltando(alerta):
    mensagem = sanitizar_texto_chat(getattr(alerta, "mensagem", "") or "")
    match = re.search(r"Campos faltando:\s*(.+?)(?:\.\s|$)", mensagem, flags=re.IGNORECASE)
    if not match:
        return []
    return [
        _normalizar_campo_faltando(parte)
        for parte in match.group(1).split(",")
        if parte.strip()
    ]


def _extrair_nome_tanque(alerta):
    mensagem = sanitizar_texto_chat(getattr(alerta, "mensagem", "") or "")
    match = re.search(r"O tanque\s+(.+?)\s+está com dados incompletos", mensagem, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return "não informado"


def _formatar_lista_campos(campos):
    campos = [campo for campo in campos if campo]
    if not campos:
        return "campos obrigatórios do tanque"
    if len(campos) == 1:
        return campos[0]
    if len(campos) == 2:
        return f"{campos[0]} e {campos[1]}"
    return ", ".join(campos[:-1]) + f" e {campos[-1]}"


def formatar_tanque_incompleto(alertas, total, numero_os=None, limite=10):
    escopo = f" na OS {numero_os}" if numero_os else ""
    limite_exibicao = min(limite, len(alertas))

    contagem_campos = Counter()
    for alerta in alertas:
        for campo in _extrair_campos_faltando(alerta):
            contagem_campos[campo] += 1

    linhas = [f"Encontrei {total} RDO(s) com tanque incompleto{escopo}."]

    if contagem_campos:
        linhas.extend(["", "Principais pendências encontradas:", ""])
        for campo, quantidade in contagem_campos.most_common(3):
            linhas.append(f"* {campo[:1].upper() + campo[1:]} ausente{f' em {quantidade} registro(s)' if quantidade else ''}")

    if limite_exibicao:
        linhas.extend(["", "Primeiros casos:", ""])

    for indice, alerta in enumerate(alertas[:limite_exibicao], start=1):
        rdo = getattr(alerta, "rdo", None)
        os_obj = getattr(rdo, "ordem_servico", None)
        numero_os_item = getattr(os_obj, "numero_os", None) or "Não informada"
        numero_rdo = (
            getattr(rdo, "numero_rdo", None)
            or getattr(rdo, "rdo", None)
            or getattr(rdo, "numero", None)
            or getattr(rdo, "id", None)
            or "não informado"
        )
        cliente = (
            getattr(getattr(os_obj, "Cliente", None), "nome", None)
            or getattr(os_obj, "cliente", None)
            or getattr(os_obj, "embarcacao", None)
            or "Cliente não informado"
        )
        nome_tanque = _extrair_nome_tanque(alerta)
        campos_faltando = _extrair_campos_faltando(alerta)

        linhas.append(f"{indice}. OS {numero_os_item} | RDO {numero_rdo} | {cliente}")
        linhas.append(f"   Tanque: {nome_tanque}")
        linhas.append(f"   Campos faltando: {_formatar_lista_campos(campos_faltando)}.")
        linhas.append("")

    if total > limite_exibicao:
        linhas.append(
            f"Mostrando os {limite_exibicao} primeiros de {total} registros. "
            "Refine por OS, cliente ou período para ver menos resultados."
        )

    return "\n".join(linha for linha in linhas if linha is not None).strip()
