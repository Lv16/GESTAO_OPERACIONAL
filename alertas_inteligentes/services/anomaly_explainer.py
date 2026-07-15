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
        f"{label}: {format_anomaly_number(current_value, suffix)}, "
        f"dentro do intervalo recente de {format_anomaly_number(minimum, suffix)} "
        f"a {format_anomaly_number(maximum, suffix)}."
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
            f"{label} saiu de {format_anomaly_number(minimum, suffix)} no histórico recente "
            f"para {format_anomaly_number(current_value, suffix)} neste RDO."
        )
    elif current_value < minimum:
        status = "fora_do_padrao"
        reason = (
            f"{label}: {format_anomaly_number(current_value, suffix)}, "
            f"abaixo do histórico recente de {format_anomaly_number(minimum, suffix)} "
            f"a {format_anomaly_number(maximum, suffix)}."
        )
    elif current_value > maximum:
        status = "fora_do_padrao"
        reason = (
            f"{label}: {format_anomaly_number(current_value, suffix)}, "
            f"acima do histórico recente de {format_anomaly_number(minimum, suffix)} "
            f"a {format_anomaly_number(maximum, suffix)}."
        )
    elif severity > 0 and (relative_diff or 0) >= 0.75:
        reason = (
            f"{label}: {format_anomaly_number(current_value, suffix)}, "
            f"dentro do intervalo recente de {format_anomaly_number(minimum, suffix)} "
            f"a {format_anomaly_number(maximum, suffix)}, mas com variação relevante "
            f"em relação ao comportamento recente."
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
                f"{prefixo}últimos {len(referencia)} RDOs ({', '.join(str(item) for item in referencia)})."
            )

    primary_entries = [item for item in entries if item.get("status") in PRIMARY_STATUSES]
    secondary_entries = [item for item in entries if item.get("status") == "dentro_do_intervalo"]

    principal_motivos: List[str] = []
    if primary_entries:
        top_primary = primary_entries[:2]
        principal_motivos = [
            _with_tank_prefix(item.get("reason") or "", item.get("tank"), include_tank_prefix)
            for item in top_primary
        ]
    elif entries:
        principal_motivos = [
            _with_tank_prefix(entries[0].get("reason") or "", entries[0].get("tank"), include_tank_prefix)
        ]

    metricas_fora = [
        _with_tank_prefix(item.get("reason") or "", item.get("tank"), include_tank_prefix)
        for item in primary_entries[1 if primary_entries else 0:4]
    ]
    secondary_offset = 0 if primary_entries else 1
    metricas_avaliadas = [
        _with_tank_prefix(item.get("reason") or "", item.get("tank"), include_tank_prefix)
        for item in secondary_entries[secondary_offset:secondary_offset + 3]
    ]

    if date_info.get("out_of_order"):
        texto_data = "A data deste RDO ficou fora da sequência esperada em relação aos registros anteriores da OS."
        ultima_data = date_info.get("last_date")
        if ultima_data:
            texto_data = (
                f"{texto_data} Última data registrada antes dele: {ultima_data}."
            )
        if not principal_motivos:
            principal_motivos.append(texto_data)
        elif len(principal_motivos) < 2:
            metricas_fora.append(texto_data)

    if tipo == "RDO_OUTLIER":
        titulo = "RDO fora do padrão"
        subtitulo = "O avanço informado neste RDO ficou diferente dos últimos registros do mesmo tanque."
    else:
        titulo = "RDO precisa de revisão"
        subtitulo = (
            "Este alerta não significa necessariamente erro. Ele indica uma variação incomum "
            "no histórico recente e merece conferência."
        )

    contexto = ""
    if nomes_tanques:
        contexto = f"Tanque {nomes_tanques[0]}" if len(nomes_tanques) == 1 else "Tanques " + ", ".join(nomes_tanques)

    acao_recomendada = (
        "Compare este RDO com os últimos registros do mesmo tanque antes de concluir a revisão."
        if tipo == "RDO_REVISAR_ANOMALIA"
        else "Confirme se a variação destacada reflete uma condição operacional real ou erro de preenchimento."
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
