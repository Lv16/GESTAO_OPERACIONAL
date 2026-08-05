from typing import Any, Dict, List, Optional


PRIMARY_STATUSES = {"fora_do_padrao", "mudanca_brusca"}


def format_anomaly_number(value: Optional[float], suffix: str = "") -> str:
    if value is None:
        return "n/d"
    try:
        number = float(value)
    except Exception:
        try:
            number = float(str(value).replace(",", "."))
        except Exception:
            return f"{value}{suffix}"

    if number.is_integer():
        base = str(int(number))
    else:
        base = str(round(number, 2)).replace(".", ",")
    return f"{base}{suffix}"


def format_anomaly_date(value: Any) -> str:
    if value in (None, ""):
        return "data não informada"
    try:
        return value.strftime("%d/%m/%Y")
    except Exception:
        raw = str(value).strip()
        parts = raw[:10].split("-")
        if len(parts) == 3 and all(parts):
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
        return raw


def format_anomaly_message(explanation: Dict[str, Any], *, tipo: str) -> str:
    """Converte a explicação estruturada em texto operacional simples."""
    explanation = explanation or {}
    lines: List[str] = [
        (
            "O Synchro encontrou uma informação que precisa ser conferida neste RDO."
            if tipo == "RDO_OUTLIER"
            else "O Synchro encontrou uma variação incomum. Isso não significa necessariamente que exista um erro."
        )
    ]

    context = explanation.get("contexto")
    if context:
        lines.extend(["", f"Tanque analisado: {context}."])

    principal = explanation.get("principal_motivo") or []
    if principal:
        lines.extend(["", "Por que este alerta foi gerado:"])
        lines.extend(f"• {item}" for item in principal)

    other_outliers = explanation.get("metricas_fora_do_padrao") or []
    if other_outliers:
        lines.extend(["", "Outros pontos que também precisam de conferência:"])
        lines.extend(f"• {item}" for item in other_outliers)

    checked = explanation.get("metricas_avaliadas") or []
    if checked:
        lines.extend(["", "Dados conferidos que não causaram este alerta:"])
        lines.extend(f"• {item}" for item in checked)

    comparison = explanation.get("base_comparacao") or []
    if comparison:
        lines.extend(["", "Comparação utilizada:"])
        lines.extend(f"• {item}" for item in comparison)

    recommendation = explanation.get("acao_recomendada")
    if recommendation:
        lines.extend(["", "O que conferir:", recommendation])

    return "\n".join(lines).strip()


def build_metric_entry(
    *,
    label: str,
    current_value: Optional[float],
    baseline: Optional[Dict[str, Any]],
    severity: float = 0.0,
    zscore: Optional[float] = None,
    iqr_flag: Optional[int] = None,
    relative_diff: Optional[float] = None,
    suffix: str = "",
    tank: Optional[str] = None,
    compartimento: Optional[str] = None,
    categoria: Optional[str] = None,
) -> Dict[str, Any]:
    baseline = baseline or {}
    minimum = baseline.get("min")
    maximum = baseline.get("max")
    mean = baseline.get("mean")
    median = baseline.get("median")
    baseline_ref = median if median is not None else mean
    within_interval = (
        current_value is not None
        and minimum is not None
        and maximum is not None
        and minimum <= current_value <= maximum
    )
    stable_history = minimum is not None and maximum is not None and minimum == maximum
    status = "dentro_do_intervalo"
    reason = (
        f"{label}: neste RDO foi informado {format_anomaly_number(current_value, suffix)}. "
        f"Nos RDOs usados na comparação, os valores ficaram entre "
        f"{format_anomaly_number(minimum, suffix)} e {format_anomaly_number(maximum, suffix)}. "
        f"Este dado está dentro da faixa histórica e não é, sozinho, motivo de erro."
    )

    if current_value is None:
        status = "sem_historico_suficiente"
        reason = f"{label}: sem valor atual suficiente para comparação."
    elif minimum is None or maximum is None:
        status = "sem_historico_suficiente"
        reason = f"{label}: sem histórico recente suficiente para comparação."
    elif stable_history and current_value != minimum:
        status = "mudanca_brusca"
        reason = (
            f"{label}: nos RDOs anteriores o valor permaneceu em "
            f"{format_anomaly_number(minimum, suffix)}, mas neste RDO foi informado "
            f"{format_anomaly_number(current_value, suffix)}."
        )
    elif current_value < minimum:
        status = "fora_do_padrao"
        reason = (
            f"{label}: neste RDO foi informado {format_anomaly_number(current_value, suffix)}. "
            f"Nos RDOs usados na comparação, o menor valor foi "
            f"{format_anomaly_number(minimum, suffix)} e o maior foi "
            f"{format_anomaly_number(maximum, suffix)}. O valor atual está abaixo dessa faixa."
        )
    elif current_value > maximum:
        status = "fora_do_padrao"
        reason = (
            f"{label}: neste RDO foi informado {format_anomaly_number(current_value, suffix)}. "
            f"Nos RDOs usados na comparação, o menor valor foi "
            f"{format_anomaly_number(minimum, suffix)} e o maior foi "
            f"{format_anomaly_number(maximum, suffix)}. O valor atual está acima dessa faixa."
        )
    elif severity > 0 and (relative_diff or 0) >= 0.75:
        reason = (
            f"{label}: neste RDO foi informado {format_anomaly_number(current_value, suffix)}. "
            f"Nos RDOs usados na comparação, os valores ficaram entre "
            f"{format_anomaly_number(minimum, suffix)} e {format_anomaly_number(maximum, suffix)}. "
            f"Este dado está dentro da faixa histórica e não foi o motivo principal do alerta."
        )

    contribution = round(float(severity or 0.0), 3)
    if contribution >= 1.0:
        prioridade = "alta"
    elif contribution >= 0.6:
        prioridade = "media"
    else:
        prioridade = "baixa"

    return {
        "label": label,
        "tank": tank,
        "compartimento": compartimento,
        "categoria": categoria,
        "current_value": current_value,
        "historical_min": minimum,
        "historical_max": maximum,
        "historical_mean": mean,
        "historical_median": median,
        "status": status,
        "reason": reason,
        "priority": prioridade,
        "contribution": contribution,
        "severity": contribution,
        "zscore": zscore,
        "iqr_flag": iqr_flag,
        "relative_diff": relative_diff,
        "within_historical_interval": within_interval,
        "suffix": suffix,
    }


def _entry_sort_key(item: Dict[str, Any]):
    status = item.get("status")
    primary_weight = 0 if status in PRIMARY_STATUSES else 1
    return (primary_weight, -(item.get("severity") or 0.0), item.get("label") or "")


def _with_tank_prefix(text: str, tank_name: Optional[str], include_prefix: bool) -> str:
    if not include_prefix or not tank_name:
        return text
    return f"Tanque {tank_name}: {text}"


def _fallback_metric_entry(
    *,
    label: str,
    raw: Dict[str, Any],
    tank_name: Optional[str] = None,
    compartimento: Optional[str] = None,
    categoria: Optional[str] = None,
    suffix: str = "",
) -> Dict[str, Any]:
    baseline = raw.get("baseline") or {}
    return build_metric_entry(
        label=label,
        current_value=raw.get("current_value", raw.get("valor")),
        baseline=baseline,
        severity=raw.get("severity", raw.get("sev", 0.0)) or 0.0,
        zscore=raw.get("zscore"),
        iqr_flag=raw.get("iqr_flag"),
        relative_diff=raw.get("relative_diff"),
        suffix=suffix or raw.get("suffix", ""),
        tank=tank_name or raw.get("tank"),
        compartimento=compartimento or raw.get("compartimento"),
        categoria=categoria or raw.get("categoria"),
    )


def _extract_tank_entries(tank_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    tank_name = tank_data.get("tank")

    for raw in (tank_data.get("metric_flags") or {}).values():
        label = raw.get("label") or "Métrica do tanque"
        entry = raw if raw.get("reason") and raw.get("status") else _fallback_metric_entry(
            label=label,
            raw=raw,
            tank_name=tank_name,
        )
        entry = {**entry}
        entry["tank"] = tank_name or entry.get("tank")
        entries.append(entry)

    for compartimento, categorias in (tank_data.get("compartment_flags") or {}).items():
        for categoria, raw in categorias.items():
            categoria_label = "limpeza fina" if categoria == "fina" else "limpeza mecanizada"
            label = raw.get("label") or f"Compartimento {compartimento} / {categoria_label}"
            entry = raw if raw.get("reason") and raw.get("status") else _fallback_metric_entry(
                label=label,
                raw=raw,
                tank_name=tank_name,
                compartimento=str(compartimento),
                categoria=categoria,
                suffix="%",
            )
            entry = {**entry}
            entry["tank"] = tank_name or entry.get("tank")
            entries.append(entry)

    entries.sort(key=_entry_sort_key)
    return entries


def build_anomaly_explanation(
    flags: Optional[Dict[str, Any]],
    *,
    tipo: str = "RDO_OUTLIER",
    score: Optional[float] = None,
) -> Dict[str, Any]:
    flags = flags or {}
    tanks = flags.get("tanques") or []
    date_info = flags.get("date") or {}
    include_tank_prefix = len(tanks) > 1

    entries: List[Dict[str, Any]] = []
    base_comparacao: List[str] = []
    nomes_tanques: List[str] = []

    for tank_data in tanks:
        tank_name = str(tank_data.get("tank") or "").strip()
        if tank_name:
            nomes_tanques.append(tank_name)
        entries.extend(_extract_tank_entries(tank_data))

        referencia = (tank_data.get("baseline") or {}).get("rdos_referencia") or []
        if referencia:
            prefixo = f"Tanque {tank_name}: " if tank_name else ""
            base_comparacao.append(
                f"{prefixo}RDOs {', '.join(str(item) for item in referencia)} "
                f"({len(referencia)} registros anteriores)."
            )

    primary_entries = [item for item in entries if item.get("status") in PRIMARY_STATUSES]
    secondary_entries = [item for item in entries if item.get("status") == "dentro_do_intervalo"]

    principal_motivos: List[str] = []
    if primary_entries:
        principal_motivos = [
            _with_tank_prefix(item.get("reason") or "", item.get("tank"), include_tank_prefix)
            for item in primary_entries[:1]
        ]

    metricas_fora = [
        _with_tank_prefix(item.get("reason") or "", item.get("tank"), include_tank_prefix)
        for item in primary_entries[1 if primary_entries else 0:4]
    ]
    secondary_offset = 0 if primary_entries or date_info.get("out_of_order") else 1
    metricas_avaliadas = [
        _with_tank_prefix(item.get("reason") or "", item.get("tank"), include_tank_prefix)
        for item in secondary_entries[secondary_offset:secondary_offset + 3]
    ]

    if date_info.get("out_of_order"):
        data_atual = date_info.get("current_date")
        ultima_data = date_info.get("last_date")
        if data_atual and ultima_data:
            texto_data = (
                f"A data informada neste RDO é {format_anomaly_date(data_atual)}, mas já existe outro RDO "
                f"da mesma OS com data {format_anomaly_date(ultima_data)}. Por isso, este lançamento ficou "
                f"fora da ordem cronológica."
            )
        elif ultima_data:
            texto_data = (
                f"A data deste RDO é anterior a outro registro da mesma OS, datado de "
                f"{format_anomaly_date(ultima_data)}. "
                f"Por isso, este lançamento ficou fora da ordem cronológica."
            )
        else:
            texto_data = "A data deste RDO ficou fora da ordem cronológica dos demais registros da mesma OS."
        if not primary_entries:
            principal_motivos.insert(0, texto_data)
        else:
            metricas_fora.append(texto_data)

    if not principal_motivos and entries:
        principal_motivos = [
            _with_tank_prefix(entries[0].get("reason") or "", entries[0].get("tank"), include_tank_prefix)
        ]

    if tipo == "RDO_OUTLIER":
        titulo = "RDO fora do padrão"
        subtitulo = (
            "A data deste RDO não segue a ordem cronológica dos demais registros da OS."
            if date_info.get("out_of_order") and not primary_entries
            else "Um ou mais valores deste RDO ficaram fora da faixa registrada recentemente para o mesmo tanque."
        )
    else:
        titulo = "RDO precisa de revisão"
        subtitulo = (
            "Este alerta não significa necessariamente erro. Ele indica uma variação incomum "
            "no histórico recente e merece conferência."
        )

    contexto = ""
    if nomes_tanques:
        contexto = nomes_tanques[0] if len(nomes_tanques) == 1 else ", ".join(nomes_tanques)

    acao_recomendada = (
        "Compare este RDO com os últimos registros do mesmo tanque antes de concluir a revisão."
        if tipo == "RDO_REVISAR_ANOMALIA"
        else "Confirme se a variação destacada reflete uma condição operacional real ou erro de preenchimento."
    )
    if date_info.get("out_of_order") and not primary_entries:
        acao_recomendada = (
            "Confira a data informada neste RDO. Se ela estiver correta, confirme se o RDO foi lançado "
            "fora de ordem; se estiver incorreta, ajuste a data e salve novamente."
        )
    if primary_entries:
        label = (primary_entries[0].get("label") or "a métrica destacada").lower()
        if tipo == "RDO_REVISAR_ANOMALIA":
            acao_recomendada = (
                f"Compare {label} com os últimos registros do mesmo tanque antes de marcar a revisão como concluída."
            )
        else:
            acao_recomendada = (
                f"Verifique se a variação em {label} neste RDO reflete uma condição operacional real ou erro de preenchimento."
            )

    nivel_atencao = "alto" if score is not None and score >= 0.7 else "médio" if score is not None and score >= 0.4 else "baixo"

    return {
        "titulo": titulo,
        "subtitulo": subtitulo,
        "contexto": contexto,
        "principal_motivo": principal_motivos,
        "metricas_fora_do_padrao": metricas_fora,
        "metricas_avaliadas": metricas_avaliadas,
        "base_comparacao": base_comparacao,
        "acao_recomendada": acao_recomendada,
        "nivel_atencao": nivel_atencao,
        "metricas_detalhadas": entries,
    }
