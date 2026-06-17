import statistics
from typing import Any, Dict, List, Optional

from GO.models import RDO, RdoTanque


FEATURES_NUMERICAS = [
    "ensacamento_dia",
    "ensacamento_acumulado",
    "cambagem",
    "icamento",
    "tempo_bomba",
    "percentual_avanco",
]

TANK_DAILY_FEATURES = {
    "ensacamento_dia": "Ensacamento do dia",
    "icamento_dia": "Içamento do dia",
    "cambagem_dia": "Cambagem do dia",
    "tempo_bomba": "Tempo de bomba",
    "limpeza_mecanizada_diaria": "Limpeza mecanizada do dia",
    "limpeza_fina_diaria": "Limpeza fina do dia",
}

MIN_HISTORY_FOR_TANK_BASELINE = 3
MAX_HISTORY_FOR_TANK_BASELINE = 5


def _to_float(value) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        try:
            return float(str(value).replace(",", "."))
        except Exception:
            return None


def _format_number(value: Optional[float]) -> str:
    if value is None:
        return "n/d"
    if float(value).is_integer():
        return str(int(value))
    return str(round(float(value), 2)).replace(".", ",")


def _tank_label(tank: RdoTanque) -> str:
    for raw_value in (
        getattr(tank, "tanque_codigo", None),
        getattr(tank, "nome_tanque", None),
    ):
        text = str(raw_value or "").strip()
        if text:
            return text
    return f"Tanque {tank.pk}"


def extract_features_from_rdo(rdo: RDO) -> Dict[str, float]:
    values = {f: None for f in FEATURES_NUMERICAS}

    for field_name in list(values.keys()):
        if hasattr(rdo, field_name):
            values[field_name] = _to_float(getattr(rdo, field_name))

    try:
        tanques = list(RdoTanque.objects.filter(rdo=rdo))
    except Exception:
        tanques = []

    if not tanques:
        return values

    def _sum_field(attr_name):
        found = False
        total = 0.0
        for tank in tanques:
            current = _to_float(getattr(tank, attr_name, None))
            if current is None:
                continue
            found = True
            total += current
        return total if found else None

    if values.get("ensacamento_dia") in (None, 0):
        values["ensacamento_dia"] = _sum_field("ensacamento_dia")
    if values.get("ensacamento_acumulado") in (None, 0):
        values["ensacamento_acumulado"] = _sum_field("ensacamento_cumulativo")
    if values.get("cambagem") in (None, 0):
        values["cambagem"] = _sum_field("cambagem_dia") or _sum_field("cambagem_cumulativo")
    if values.get("icamento") in (None, 0):
        values["icamento"] = _sum_field("icamento_dia") or _sum_field("icamento_cumulativo")
    if values.get("tempo_bomba") in (None, 0):
        values["tempo_bomba"] = _sum_field("tempo_bomba")

    if values.get("percentual_avanco") in (None, 0):
        best = None
        for tank in tanques:
            candidate = _to_float(
                getattr(tank, "percentual_avanco_cumulativo", None)
                or getattr(tank, "percentual_avanco", None)
            )
            if candidate is None:
                continue
            if best is None or candidate > best:
                best = candidate
        values["percentual_avanco"] = best

    return values


def fetch_historical_rdos_for_os(rdo: RDO) -> List[RDO]:
    os_obj = getattr(rdo, "ordem_servico", None) or getattr(rdo, "os", None)
    if not os_obj:
        return []
    return list(RDO.objects.filter(ordem_servico=os_obj).order_by("data", "id"))


def compute_baseline(values_list: List[float]) -> Dict[str, float]:
    clean = [v for v in values_list if v is not None]
    if not clean:
        return {
            "count": 0,
            "median": None,
            "q1": None,
            "q3": None,
            "iqr": None,
            "mean": None,
            "std": None,
            "min": None,
            "max": None,
        }
    median = statistics.median(clean)
    try:
        quartiles = statistics.quantiles(clean, n=4)
        q1 = quartiles[0]
        q3 = quartiles[2]
    except Exception:
        q1 = min(clean)
        q3 = max(clean)
    iqr = q3 - q1
    mean = statistics.mean(clean)
    std = statistics.pstdev(clean) if len(clean) > 1 else 0.0
    return {
        "count": len(clean),
        "median": median,
        "q1": q1,
        "q3": q3,
        "iqr": iqr,
        "mean": mean,
        "std": std,
        "min": min(clean),
        "max": max(clean),
    }


def compute_z_score(value: float, baseline: Dict[str, float]) -> float:
    if value is None:
        return 0.0
    std = baseline.get("std") or 0.0
    mean = baseline.get("mean")
    if std <= 0 or mean is None:
        return 0.0
    try:
        return (value - mean) / std
    except Exception:
        return 0.0


def compute_iqr_flag(value: float, baseline: Dict[str, float]) -> int:
    if value is None:
        return 0
    q1 = baseline.get("q1")
    q3 = baseline.get("q3")
    iqr = baseline.get("iqr")
    if iqr is None or q1 is None or q3 is None:
        return 0
    if iqr <= 0:
        return 0
    lower1 = q1 - 1.5 * iqr
    upper1 = q3 + 1.5 * iqr
    lower2 = q1 - 3.0 * iqr
    upper2 = q3 + 3.0 * iqr
    if value < lower2 or value > upper2:
        return 2
    if value < lower1 or value > upper1:
        return 1
    return 0


def validate_bounds(feature_name: str, value: float) -> bool:
    if value is None:
        return False
    if "percentual" in feature_name:
        try:
            return value < 0 or value > 100
        except Exception:
            return False
    return False


def validate_date_order(rdo: RDO, historical: List[RDO]) -> Dict[str, Any]:
    result = {"out_of_order": False, "last_date": None}
    try:
        current_date = getattr(rdo, "data", None)
        if not current_date:
            return result
        dates = [
            getattr(other, "data", None)
            for other in historical
            if other.pk != rdo.pk and getattr(other, "data", None) is not None
        ]
        if not dates:
            return result
        last_date = max(dates)
        result["last_date"] = last_date
        if (last_date - current_date).days >= 2:
            result["out_of_order"] = True
    except Exception:
        pass
    return result


def classificar_score(score: float) -> str:
    if score >= 0.70:
        return "alerta"
    if score >= 0.40:
        return "revisao"
    return "normal"


def _extract_tank_daily_features(tank: RdoTanque) -> Dict[str, Optional[float]]:
    snapshot = tank.build_compartimento_progress_snapshot()
    return {
        "ensacamento_dia": _to_float(getattr(tank, "ensacamento_dia", None)),
        "icamento_dia": _to_float(getattr(tank, "icamento_dia", None)),
        "cambagem_dia": _to_float(getattr(tank, "cambagem_dia", None)),
        "tempo_bomba": _to_float(getattr(tank, "tempo_bomba", None)),
        "limpeza_mecanizada_diaria": _to_float(getattr(tank, "limpeza_mecanizada_diaria", None)),
        "limpeza_fina_diaria": _to_float(getattr(tank, "limpeza_fina_diaria", None)),
        "progresso_mecanizada_dia": _to_float(snapshot.get("daily", {}).get("mecanizada")),
        "progresso_fina_dia": _to_float(snapshot.get("daily", {}).get("fina")),
    }


def _extract_compartment_daily_values(tank: RdoTanque) -> Dict[str, Dict[str, float]]:
    total = tank.get_total_compartimentos()
    normalized = tank.normalize_compartimentos_payload(
        getattr(tank, "compartimentos_avanco_json", None),
        total,
    )
    return {
        key: {
            "mecanizada": _to_float(values.get("mecanizada")) or 0.0,
            "fina": _to_float(values.get("fina")) or 0.0,
        }
        for key, values in normalized.items()
    }


def _compute_deviation_severity(current: Optional[float], baseline: Dict[str, float]) -> Dict[str, Any]:
    if current is None or baseline.get("count", 0) < MIN_HISTORY_FOR_TANK_BASELINE:
        return {"severity": 0.0, "zscore": 0.0, "iqr_flag": 0, "relative_diff": 0.0}

    zscore = compute_z_score(current, baseline)
    iqr_flag = compute_iqr_flag(current, baseline)
    mean = baseline.get("mean")
    median = baseline.get("median")
    baseline_ref = median if median is not None else mean

    relative_diff = 0.0
    if baseline_ref not in (None, 0):
        relative_diff = abs(current - baseline_ref) / abs(baseline_ref)
    elif current not in (None, 0):
        relative_diff = 1.0

    severity = 0.0
    if abs(zscore) >= 3 or iqr_flag == 2:
        severity = 1.0
    elif abs(zscore) >= 2 or iqr_flag == 1:
        severity = 0.6

    if severity == 0.0:
        min_v = baseline.get("min")
        max_v = baseline.get("max")
        if min_v == max_v and baseline_ref is not None:
            if relative_diff >= 1.0:
                severity = 1.0
            elif relative_diff >= 0.4:
                severity = 0.6
        elif baseline_ref is not None:
            if relative_diff >= 1.5:
                severity = 1.0
            elif relative_diff >= 0.75:
                severity = 0.6

    return {
        "severity": severity,
        "zscore": round(float(zscore), 3),
        "iqr_flag": iqr_flag,
        "relative_diff": round(float(relative_diff), 3),
    }


def _build_tank_anomaly(current_tank: RdoTanque) -> Optional[Dict[str, Any]]:
    historical_tanks = list(current_tank.get_prior_tank_snapshots())
    if len(historical_tanks) < MIN_HISTORY_FOR_TANK_BASELINE:
        return None

    recent_history = historical_tanks[-MAX_HISTORY_FOR_TANK_BASELINE:]
    current_features = _extract_tank_daily_features(current_tank)
    current_compartments = _extract_compartment_daily_values(current_tank)

    metric_flags = {}
    metric_baseline = {}
    metric_severities = []

    for feature_name in TANK_DAILY_FEATURES:
        historical_values = [
            _extract_tank_daily_features(prior).get(feature_name)
            for prior in recent_history
        ]
        baseline = compute_baseline(historical_values)
        metric_baseline[feature_name] = baseline
        current_value = current_features.get(feature_name)
        deviation = _compute_deviation_severity(current_value, baseline)
        if deviation["severity"] > 0:
            metric_flags[feature_name] = {
                "label": TANK_DAILY_FEATURES[feature_name],
                "valor": current_value,
                "baseline": baseline,
                **deviation,
            }
            metric_severities.append(deviation["severity"])

    compartment_flags = {}
    for compartimento, categorias in current_compartments.items():
        for categoria, valor_atual in categorias.items():
            historical_values = []
            for prior in recent_history:
                prior_payload = _extract_compartment_daily_values(prior)
                historical_values.append(
                    _to_float(prior_payload.get(compartimento, {}).get(categoria)) or 0.0
                )
            baseline = compute_baseline(historical_values)
            deviation = _compute_deviation_severity(valor_atual, baseline)
            if deviation["severity"] <= 0:
                continue
            compartment_flags.setdefault(compartimento, {})[categoria] = {
                "valor": valor_atual,
                "baseline": baseline,
                **deviation,
            }
            metric_severities.append(deviation["severity"])

    if not metric_severities:
        return {
            "tank": _tank_label(current_tank),
            "score": 0.0,
            "metric_flags": {},
            "compartment_flags": {},
            "baseline": {
                "historico_utilizado": len(recent_history),
                "rdos_referencia": [getattr(getattr(item, "rdo", None), "rdo", item.rdo_id) for item in recent_history],
                "metricas": metric_baseline,
            },
        }

    top_two = sorted(metric_severities, reverse=True)[:2]
    score = max(top_two)
    if len(top_two) > 1:
        score = max(score, round(sum(top_two) / len(top_two), 3))

    return {
        "tank": _tank_label(current_tank),
        "score": round(float(score), 3),
        "metric_flags": metric_flags,
        "compartment_flags": compartment_flags,
        "baseline": {
            "historico_utilizado": len(recent_history),
            "rdos_referencia": [getattr(getattr(item, "rdo", None), "rdo", item.rdo_id) for item in recent_history],
            "metricas": metric_baseline,
        },
    }


def _detectar_anomalia_por_tanque(rdo: RDO, historical: List[RDO]) -> Optional[Dict[str, Any]]:
    try:
        current_tanks = list(rdo.tanques.all())
    except Exception:
        current_tanks = []

    if not current_tanks:
        return None

    tank_results = []
    for tank in current_tanks:
        tank_result = _build_tank_anomaly(tank)
        if tank_result:
            tank_results.append(tank_result)

    if not tank_results:
        return None

    tank_scores = [item["score"] for item in tank_results]
    score = max(tank_scores) if tank_scores else 0.0
    date_info = validate_date_order(rdo, historical)
    if date_info.get("out_of_order"):
        score = max(score, 0.7)

    return {
        "score": round(float(score), 3),
        "nivel": classificar_score(score),
        "flags": {
            "tanques": tank_results,
            "date": date_info,
        },
        "baseline_snapshot": {
            "escopo": "os_tanque",
            "tanques": {
                item["tank"]: item["baseline"] for item in tank_results
            },
        },
    }


def _detectar_anomalia_agregada_rdo(rdo: RDO, historical: List[RDO]) -> Dict[str, Any]:
    resultado = {"score": 0.0, "nivel": "normal", "flags": {}, "baseline_snapshot": {}}
    n_hist = len(historical)

    feature_vectors = {f: [] for f in FEATURES_NUMERICAS}
    for item in historical:
        feats = extract_features_from_rdo(item)
        for feature_name in FEATURES_NUMERICAS:
            feature_vectors[feature_name].append(feats.get(feature_name))

    baseline = {
        feature_name: compute_baseline([v for v in feature_vectors[feature_name] if v is not None])
        for feature_name in FEATURES_NUMERICAS
    }
    current = extract_features_from_rdo(rdo)
    flags = {"zscore": {}, "iqr": {}, "bounds": {}, "date": {}}

    if n_hist < 5:
        any_bounds = False
        for feature_name in FEATURES_NUMERICAS:
            value = current.get(feature_name)
            out = validate_bounds(feature_name, value)
            flags["bounds"][feature_name] = {"valor": value, "out": bool(out)}
            any_bounds = any_bounds or out
        date_info = validate_date_order(rdo, historical)
        flags["date"] = date_info
        score = 0.0
        if any_bounds:
            score = 0.6
        if date_info.get("out_of_order"):
            score = max(score, 0.7)
        resultado.update(
            {
                "score": score,
                "nivel": classificar_score(score),
                "flags": flags,
                "baseline_snapshot": baseline,
            }
        )
        return resultado

    z_scores = []
    iqr_severities = []
    bounds_flags = []
    for feature_name in FEATURES_NUMERICAS:
        value = current.get(feature_name)
        base = baseline.get(feature_name) or {}
        zscore = compute_z_score(value, base)
        zsev = 1.0 if abs(zscore) >= 3.0 else 0.6 if abs(zscore) >= 2.0 else 0.0
        z_scores.append(zsev)
        flags["zscore"][feature_name] = {
            "valor": value,
            "media": base.get("mean") or base.get("median"),
            "zscore": round(float(zscore), 3),
            "sev": zsev,
        }

        iqr_flag = compute_iqr_flag(value, base)
        isev = 1.0 if iqr_flag == 2 else 0.6 if iqr_flag == 1 else 0.0
        iqr_severities.append(isev)
        flags["iqr"][feature_name] = {
            "valor": value,
            "q1": base.get("q1"),
            "q3": base.get("q3"),
            "iqr": base.get("iqr"),
            "iqr_flag": iqr_flag,
        }

        out_bounds = validate_bounds(feature_name, value)
        flags["bounds"][feature_name] = {"valor": value, "out": bool(out_bounds)}
        bounds_flags.append(1.0 if out_bounds else 0.0)

    date_info = validate_date_order(rdo, historical)
    flags["date"] = date_info

    avg_z = sum(z_scores) / len(z_scores) if z_scores else 0.0
    avg_iqr = sum(iqr_severities) / len(iqr_severities) if iqr_severities else 0.0
    avg_bounds = sum(bounds_flags) / len(bounds_flags) if bounds_flags else 0.0
    date_sev = 1.0 if date_info.get("out_of_order") else 0.0
    score = (0.35 * avg_z) + (0.35 * avg_iqr) + (0.2 * avg_bounds) + (0.1 * date_sev)

    resultado.update(
        {
            "score": round(float(score), 3),
            "nivel": classificar_score(score),
            "flags": flags,
            "baseline_snapshot": baseline,
        }
    )
    return resultado


def detectar_anomalia_rdo(rdo: RDO) -> Dict[str, Any]:
    historical = fetch_historical_rdos_for_os(rdo)
    tank_result = _detectar_anomalia_por_tanque(rdo, historical)
    if tank_result is not None:
        return tank_result
    return _detectar_anomalia_agregada_rdo(rdo, historical)


def montar_mensagem_anomalia(rdo: RDO, resultado: Dict[str, Any]) -> str:
    score = resultado.get("score", 0)
    flags = resultado.get("flags", {})
    tank_flags = flags.get("tanques") or []

    if tank_flags:
        linhas: List[str] = [
            "Identifiquei um RDO fora do padrão recente da própria OS.",
            "",
        ]

        for tank_data in tank_flags:
            if tank_data.get("score", 0) <= 0:
                continue

            linhas.append(
                f"O tanque {tank_data['tank']} fugiu do histórico recente da OS."
            )

            metric_lines = []
            for feature_name, data in sorted(
                tank_data.get("metric_flags", {}).items(),
                key=lambda item: item[1].get("severity", 0),
                reverse=True,
            )[:3]:
                baseline = data.get("baseline") or {}
                metric_lines.append(
                    f"- {data['label']}: valor deste RDO {_format_number(data.get('valor'))}. "
                    f"Histórico recente entre {_format_number(baseline.get('min'))} e {_format_number(baseline.get('max'))}."
                )

            for compartimento, categorias in sorted(
                tank_data.get("compartment_flags", {}).items(),
                key=lambda item: max(
                    category.get("severity", 0) for category in item[1].values()
                ),
                reverse=True,
            )[:2]:
                for categoria, data in categorias.items():
                    label = "limpeza fina" if categoria == "fina" else "limpeza mecanizada"
                    baseline = data.get("baseline") or {}
                    metric_lines.append(
                        f"- Compartimento {compartimento} ({label}): valor deste RDO {_format_number(data.get('valor'))}%. "
                        f"Histórico recente entre {_format_number(baseline.get('min'))}% e {_format_number(baseline.get('max'))}%."
                    )

            if metric_lines:
                linhas.append("Métricas que fugiram do histórico recente:")
                linhas.extend(metric_lines)

            referencia = tank_data.get("baseline", {}).get("rdos_referencia") or []
            if referencia:
                linhas.append(
                    f"Base de comparação: últimos {len(referencia)} RDO(s) do mesmo tanque ({', '.join(str(item) for item in referencia)})."
                )
            linhas.append("")

        if flags.get("date", {}).get("out_of_order"):
            linhas.append("A data deste RDO também parece fora da sequência da OS.")
            linhas.append("")

        linhas.append(f"Score de anomalia: {round(score, 2)}")
        linhas.append("")
        linhas.append(
            "Recomendação: confira se houve condição operacional excepcional ou erro de preenchimento nas métricas destacadas."
        )
        return "\n".join(linhas)

    baseline = resultado.get("baseline_snapshot", {})
    linhas = [
        "Identifiquei um comportamento fora do padrão neste RDO.",
        "",
    ]

    zscore = flags.get("zscore", {})
    shown_any = False
    for campo, dados in zscore.items():
        if not dados or dados.get("sev", 0) == 0:
            continue
        shown_any = True
        valor = dados.get("valor")
        media = dados.get("media")
        z = dados.get("zscore")
        linhas.append(f"O campo {campo} ficou fora do padrão histórico.")
        if media is not None:
            linhas.append(f"Média histórica: {media}")
        if valor is not None:
            linhas.append(f"Valor informado neste RDO: {valor}")
        if z is not None:
            linhas.append(f"Desvio identificado: z-score {z}")
        linhas.append("")

    iqr = flags.get("iqr", {})
    for campo, dados in iqr.items():
        if not dados or dados.get("iqr_flag") == 0:
            continue
        linhas.append(f"O campo {campo} também ficou fora da faixa esperada pelo método IQR.")
        q1 = dados.get("q1")
        q3 = dados.get("q3")
        iqr_val = dados.get("iqr")
        if q1 is not None and q3 is not None:
            linhas.append(f"Faixa esperada: {q1} - {q3} (IQR={iqr_val})")
        linhas.append("")

    bounds = flags.get("bounds", {})
    for campo, dados in bounds.items():
        if not dados or not dados.get("out"):
            continue
        linhas.append(f"O campo {campo} possui valor fora do limite esperado: {dados.get('valor')}")

    date_info = flags.get("date", {})
    if date_info.get("out_of_order"):
        last = date_info.get("last_date")
        linhas.append("")
        linhas.append("A data deste RDO parece estar fora da sequência esperada em relação aos RDOs anteriores da OS.")
        if last is not None:
            linhas.append(f"Última data registrada em outro RDO: {last}.")

    if not shown_any and not any(d.get("out") for d in bounds.values()) and not date_info.get("out_of_order"):
        linhas.append("Nenhuma métrica numérica apresentou desvio estatístico forte, mas o RDO foi sinalizado para revisão.")

    linhas.append("")
    linhas.append(f"Score de anomalia: {round(score, 2)}")
    linhas.append("")
    linhas.append(
        "Recomendação: verifique se os valores foram preenchidos corretamente ou se houve uma condição operacional extraordinária nesse dia."
    )
    return "\n".join(linhas)
