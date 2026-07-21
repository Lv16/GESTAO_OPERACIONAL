import json
import re
import unicodedata
from io import BytesIO
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import Cliente, Financeiro, FinanceiroCampo, OrdemServico, RdoTanque, Unidade


KANBAN_COLUMN_KEYS = [
    "Em Análise",
    "Em Elaboração",
    "Enviada",
    "Em Negociação",
    "Fechada/Contratada",
]

FINAL_STATUSES = {
    "Fechada/Contratada",
    "Perdida/Recusada",
    "Cancelada",
    "DeclÃ­nio",
}

COMMERCIAL_NATURE_OPTIONS = [
    "Aditivo",
    "Reajuste",
    "Spot",
    "Contrato Novo",
    "Renovação",
]

FOLLOWUP_STATUSES = ["Pendente", "Realizado", "Sem retorno", "Reagendado"]

STATUS_KANBAN_MAP = {
    "em analise": "Em Análise",
    "avaliando escopo": "Em Análise",
    "em elaboracao": "Em Elaboração",
    "aguardando aprovacao gestores": "Em Elaboração",
    "revisada": "Enviada",
    "shortlist": "Enviada",
    "enviada": "Enviada",
    "em negociacao": "Em Negociação",
    "fechada/contratada": "Fechada/Contratada",
}

STATUS_DISPLAY_MAP = {
    "em analise": "Em Análise",
    "avaliando escopo": "Avaliando escopo",
    "em elaboracao": "Em Elaboração",
    "aguardando aprovacao gestores": "Aguardando aprovação gestores",
    "revisada": "Revisada",
    "shortlist": "ShortList",
    "enviada": "Enviada",
    "em negociacao": "Em Negociação",
    "fechada/contratada": "Fechada/Contratada",
    "perdida/recusada": "Perdida/Recusada",
    "cancelada": "Cancelada",
    "declinio": "Declínio",
    "sem retorno": "Sem Retorno",
}

STATUS_RESUMO_MAP = {
    "em analise": "em_analise",
    "avaliando escopo": "em_analise",
    "em elaboracao": "em_analise",
    "aguardando aprovacao gestores": "em_analise",
    "aguardando aprovação gestores": "em_analise",
    "revisada": "em_analise",
    "shortlist": "em_analise",
    "enviada": "em_analise",
    "em negociacao": "em_analise",
    "em negociação": "em_analise",
    "fechada/contratada": "fechada_contratada",
    "fechada / contratada": "fechada_contratada",
    "perdida/recusada": "perdida_recusada",
    "perdida / recusada": "perdida_recusada",
    "cancelada": "perdida_recusada",
    "declinio": "perdida_recusada",
    "declínio": "perdida_recusada",
}

RESUMO_MONTH_NAMES = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}


def _normalize_key(value):
    normalized = unicodedata.normalize("NFD", str(value or "").strip())
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return normalized.lower()


def _clean_text(value):
    return str(value or "").strip()


def _format_date_br(value):
    if not value:
        return ""
    return value.strftime("%d/%m/%Y")


def _format_currency_br(value):
    amount = value if isinstance(value, Decimal) else Decimal(str(value or 0))
    text = f"{amount:,.2f}"
    return f"R$ {text.replace(',', 'X').replace('.', ',').replace('X', '.')}"


def _format_millions_br(value):
    amount = Decimal(value or 0) / Decimal("1000000")
    text = f"{amount:.2f}".replace(".", ",")
    return f"R$ {text} mi"


def _format_stage_revenue_br(value):
    amount = _safe_decimal(value)
    if amount >= Decimal("1000000"):
        return _format_millions_br(amount)
    return _format_currency_br(amount)


def _format_decimal_string(value):
    amount = _safe_decimal(value)
    return f"{amount:.2f}"


def _get_next_proposal_number(lock=False):
    queryset = Financeiro.objects
    if lock:
        queryset = queryset.select_for_update()
    last_item = queryset.order_by("-proposta").first()
    return (last_item.proposta if last_item else 0) + 1


def _safe_decimal(value, default="0"):
    if value in (None, ""):
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _parse_decimal_input(value):
    if value in (None, ""):
        return Decimal("0")
    text = str(value).strip().replace("R$", "").replace(" ", "")
    text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _parse_date_input(value):
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _resolve_followup_summary_and_date(raw_value):
    text = _clean_text(raw_value)
    if not text:
        return "", None
    parsed_date = _parse_date_input(text)
    if parsed_date:
        return "", parsed_date
    return text, None


def _parse_bool_input(value):
    text = _normalize_key(value)
    return text in {"sim", "true", "1", "yes"}


def _parse_proposal_number(value):
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return None
    return int(digits)


def _format_proposal_number(value):
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return ""
    if len(digits) >= 7:
        return f"PRO-{digits[:4]}-{digits[4:]}"
    return f"PRO-{digits}"


def _display_status(raw_status):
    normalized = _normalize_key(raw_status)
    return STATUS_DISPLAY_MAP.get(normalized, _clean_text(raw_status))


def _kanban_stage(raw_status):
    normalized = _normalize_key(raw_status)
    return STATUS_KANBAN_MAP.get(normalized, "Em Análise")


def _resumo_status_bucket(raw_status):
    return STATUS_RESUMO_MAP.get(_normalize_key(raw_status), "em_analise")


def _resolve_tipo_operacao_label(financeiro):
    related = getattr(financeiro, "tipo_operacao", None)
    if related is None:
        return ""
    return _clean_text(getattr(related, "tipo_operacao", ""))


def _resolve_resumo_period(mes_value, ano_value, modo_value):
    today = timezone.localdate()
    try:
        mes = max(1, min(12, int(str(mes_value or today.month))))
    except (TypeError, ValueError):
        mes = today.month

    try:
        ano = int(str(ano_value or today.year))
    except (TypeError, ValueError):
        ano = today.year

    modo = "acumulado" if _clean_text(modo_value).lower() == "acumulado" else "mensal"

    start_month = date(ano, mes, 1)
    next_month = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)
    end_month = next_month - timedelta(days=1)

    if modo == "acumulado":
        period_start = date(ano, 1, 1)
        period_end = end_month
    else:
        period_start = start_month
        period_end = end_month

    return {
        "mes": f"{mes:02d}",
        "mes_numero": mes,
        "ano": str(ano),
        "ano_numero": ano,
        "modo": modo,
        "period_start": period_start,
        "period_end": period_end,
        "year_start": date(ano, 1, 1),
        "year_end": end_month,
    }


def _serialize_resumo_table_money(value):
    amount = _safe_decimal(value)
    return float(amount)


def _build_resumo_propostas_context():
    period = _resolve_resumo_period(None, None, None)
    return build_resumo_propostas_context(
        mes=period["mes"],
        ano=period["ano"],
        modo=period["modo"],
    )


def build_resumo_propostas_context(mes=None, ano=None, modo=None):
    period = _resolve_resumo_period(mes, ano, modo)
    base_queryset = (
        Financeiro.objects.select_related("tipo_operacao")
        .exclude(data_emissao__isnull=True)
        .order_by("-data_emissao", "-proposta")
    )

    period_queryset = base_queryset.filter(
        data_emissao__gte=period["period_start"],
        data_emissao__lte=period["period_end"],
    )
    year_queryset = base_queryset.filter(
        data_emissao__gte=period["year_start"],
        data_emissao__lte=period["year_end"],
    )

    rows = list(period_queryset)
    year_rows = list(year_queryset)

    segmento_template = {
        "Offshore": {
            "segmento": "Offshore",
            "emAnalise": Decimal("0"),
            "fechadaContratada": Decimal("0"),
            "perdidaRecusada": Decimal("0"),
            "total": Decimal("0"),
        },
        "Onshore": {
            "segmento": "Onshore",
            "emAnalise": Decimal("0"),
            "fechadaContratada": Decimal("0"),
            "perdidaRecusada": Decimal("0"),
            "total": Decimal("0"),
        },
    }

    status_money = {
        "em_analise": Decimal("0"),
        "fechada_contratada": Decimal("0"),
        "perdida_recusada": Decimal("0"),
    }
    status_quantity = {
        "em_analise": 0,
        "fechada_contratada": 0,
        "perdida_recusada": 0,
    }
    gestores_reais_map = {}
    gestores_quantidade_map = {}

    total_emitido_periodo = Decimal("0")

    for item in rows:
        valor = _safe_decimal(getattr(item, "estimativo_receita", None))
        bucket = _resumo_status_bucket(getattr(item, "status_proposta", ""))
        total_emitido_periodo += valor
        status_money[bucket] += valor
        status_quantity[bucket] += 1

        tipo_operacao = _normalize_key(_resolve_tipo_operacao_label(item))
        if tipo_operacao == "offshore":
            segment_row = segmento_template["Offshore"]
            segment_row["emAnalise" if bucket == "em_analise" else "fechadaContratada" if bucket == "fechada_contratada" else "perdidaRecusada"] += valor
            segment_row["total"] += valor
        elif tipo_operacao == "onshore":
            segment_row = segmento_template["Onshore"]
            segment_row["emAnalise" if bucket == "em_analise" else "fechadaContratada" if bucket == "fechada_contratada" else "perdidaRecusada"] += valor
            segment_row["total"] += valor

        gestor = _clean_text(getattr(item, "responsavel", "")) or "Não informado"
        if gestor not in gestores_reais_map:
            gestores_reais_map[gestor] = {
                "gestor": gestor,
                "emAnalise": Decimal("0"),
                "fechadaContratada": Decimal("0"),
                "perdidaRecusada": Decimal("0"),
                "total": Decimal("0"),
            }
        if gestor not in gestores_quantidade_map:
            gestores_quantidade_map[gestor] = {
                "gestor": gestor,
                "quantidade": 0,
                "percentual": Decimal("0"),
            }

        gestor_row = gestores_reais_map[gestor]
        if bucket == "em_analise":
            gestor_row["emAnalise"] += valor
        elif bucket == "fechada_contratada":
            gestor_row["fechadaContratada"] += valor
        else:
            gestor_row["perdidaRecusada"] += valor
        gestor_row["total"] += valor
        gestores_quantidade_map[gestor]["quantidade"] += 1

    total_acumulado_ano = sum((_safe_decimal(getattr(item, "estimativo_receita", None)) for item in year_rows), Decimal("0"))
    total_propostas_periodo = len(rows)

    segmentos = [
        {
            "segmento": "Offshore",
            "emAnalise": _serialize_resumo_table_money(segmento_template["Offshore"]["emAnalise"]),
            "fechadaContratada": _serialize_resumo_table_money(segmento_template["Offshore"]["fechadaContratada"]),
            "perdidaRecusada": _serialize_resumo_table_money(segmento_template["Offshore"]["perdidaRecusada"]),
            "total": _serialize_resumo_table_money(segmento_template["Offshore"]["total"]),
        },
        {
            "segmento": "Onshore",
            "emAnalise": _serialize_resumo_table_money(segmento_template["Onshore"]["emAnalise"]),
            "fechadaContratada": _serialize_resumo_table_money(segmento_template["Onshore"]["fechadaContratada"]),
            "perdidaRecusada": _serialize_resumo_table_money(segmento_template["Onshore"]["perdidaRecusada"]),
            "total": _serialize_resumo_table_money(segmento_template["Onshore"]["total"]),
        },
    ]
    segmentos.append(
        {
            "segmento": "Total",
            "emAnalise": _serialize_resumo_table_money(status_money["em_analise"]),
            "fechadaContratada": _serialize_resumo_table_money(status_money["fechada_contratada"]),
            "perdidaRecusada": _serialize_resumo_table_money(status_money["perdida_recusada"]),
            "total": _serialize_resumo_table_money(total_emitido_periodo),
        }
    )

    receita_status = []
    for key, label, tone in (
        ("em_analise", "Em Análise", "is-analysis"),
        ("fechada_contratada", "Fechada / Contratada", "is-closed"),
        ("perdida_recusada", "Perdida / Recusada", "is-lost"),
    ):
        valor = status_money[key]
        percentual = (valor / total_emitido_periodo * Decimal("100")) if total_emitido_periodo > 0 else Decimal("0")
        receita_status.append(
            {
                "status": label,
                "valor": _serialize_resumo_table_money(valor),
                "percentual": float(percentual),
                "tone": tone,
            }
        )
    receita_status.append(
        {
            "status": "Total",
            "valor": _serialize_resumo_table_money(total_emitido_periodo),
            "percentual": 100.0 if total_emitido_periodo > 0 else 0.0,
            "tone": "is-total",
        }
    )

    gestores_reais = sorted(
        (
            {
                "gestor": row["gestor"],
                "emAnalise": _serialize_resumo_table_money(row["emAnalise"]),
                "fechadaContratada": _serialize_resumo_table_money(row["fechadaContratada"]),
                "perdidaRecusada": _serialize_resumo_table_money(row["perdidaRecusada"]),
                "total": _serialize_resumo_table_money(row["total"]),
            }
            for row in gestores_reais_map.values()
        ),
        key=lambda item: item["total"],
        reverse=True,
    )

    distribuicao_status = []
    for key, label, tone in (
        ("em_analise", "Em Análise", "is-analysis"),
        ("fechada_contratada", "Fechada / Contratada", "is-closed"),
        ("perdida_recusada", "Perdida / Recusada", "is-lost"),
    ):
        quantidade = status_quantity[key]
        percentual = (Decimal(quantidade) / Decimal(total_propostas_periodo) * Decimal("100")) if total_propostas_periodo else Decimal("0")
        distribuicao_status.append(
            {
                "status": label,
                "quantidade": quantidade,
                "percentual": float(percentual),
                "tone": tone,
            }
        )

    gestores_quantidade = sorted(
        (
            {
                "gestor": gestor,
                "quantidade": row["quantidade"],
                "percentual": float((Decimal(row["quantidade"]) / Decimal(total_propostas_periodo) * Decimal("100")) if total_propostas_periodo else Decimal("0")),
            }
            for gestor, row in gestores_quantidade_map.items()
        ),
        key=lambda item: item["quantidade"],
        reverse=True,
    )

    month_name = RESUMO_MONTH_NAMES.get(period["mes_numero"], period["mes"])
    periodo_label = (
        f"Visão acumulada - Jan/{period['ano']}"
        if period["modo"] == "acumulado"
        else f"Visão mensal - {month_name}/{period['ano']}"
    )

    month_options = [{"value": f"{month:02d}", "label": f"{month:02d}"} for month in range(1, 13)]
    years_found = sorted(
        {
            item.year
            for item in Financeiro.objects.exclude(data_emissao__isnull=True)
            .dates("data_emissao", "year")
        }
    )
    if not years_found:
        current_year = timezone.localdate().year
        years_found = [current_year]

    bootstrap = {
        "filters": {
            "mes": period["mes"],
            "ano": period["ano"],
            "modo": period["modo"],
            "monthOptions": month_options,
            "yearOptions": [str(year) for year in years_found],
        },
        "data": {
            "indicadores": {
                "totalEmitidoPeriodo": float(total_emitido_periodo),
                "emAnalise": {"valor": float(status_money["em_analise"]), "percentual": float((status_money["em_analise"] / total_emitido_periodo * Decimal("100")) if total_emitido_periodo else Decimal("0"))},
                "fechadaContratada": {"valor": float(status_money["fechada_contratada"]), "percentual": float((status_money["fechada_contratada"] / total_emitido_periodo * Decimal("100")) if total_emitido_periodo else Decimal("0"))},
                "perdidaRecusada": {"valor": float(status_money["perdida_recusada"]), "percentual": float((status_money["perdida_recusada"] / total_emitido_periodo * Decimal("100")) if total_emitido_periodo else Decimal("0"))},
                "qtdPropostasPeriodo": total_propostas_periodo,
                "totalAcumuladoAno": float(total_acumulado_ano),
            },
            "porSegmentoReais": segmentos,
            "receitaPorStatus": receita_status,
            "porGestorReais": gestores_reais,
            "distribuicaoStatusQuantidade": distribuicao_status,
            "porGestorQuantidade": gestores_quantidade,
            "periodoLabel": periodo_label,
            "emptyMessage": "Nenhuma proposta encontrada para o período selecionado.",
        },
    }

    return {
        "resumo_bootstrap": bootstrap,
        "resumo_mes": period["mes"],
        "resumo_ano": period["ano"],
        "resumo_modo": period["modo"],
        "resumo_month_options": month_options,
        "resumo_year_options": [str(year) for year in years_found],
    }


def _resolve_cliente_name(ordem_servico):
    if not ordem_servico:
        return ""
    try:
        if getattr(ordem_servico, "Cliente", None):
            return ordem_servico.Cliente.nome
    except Exception:
        pass
    return _clean_text(getattr(ordem_servico, "cliente", ""))


def _resolve_unidade_name(ordem_servico):
    if not ordem_servico:
        return ""
    try:
        if getattr(ordem_servico, "Unidade", None):
            return ordem_servico.Unidade.nome
    except Exception:
        pass
    return _clean_text(getattr(ordem_servico, "unidade", ""))


def _resolve_os_string(ordem_servico, field_name, fallback=""):
    if not ordem_servico:
        return fallback
    value = getattr(ordem_servico, field_name, "")
    return _clean_text(value or fallback)


def _resolve_tipo_operacao(financeiro):
    return _resolve_os_string(financeiro.tipo_operacao, "tipo_operacao", "")


def _serialize_financeiro_campos(financeiro):
    items = []
    total = Decimal("0")
    for campo in financeiro.campos.all():
        subtotal = _safe_decimal(campo.subtotal)
        total += subtotal
        items.append(
            {
                "id": campo.id,
                "nome": campo.nome,
                "label": campo.get_nome_display(),
                "preco_unitario": _format_decimal_string(campo.preco_unitario),
                "quantidade": _format_decimal_string(campo.quantidade),
                "subtotal": _format_decimal_string(subtotal),
            }
        )
    return items, total


def _build_mock_followups(financeiro):
    base_date = (
        financeiro.data_entrega_proposta
        or financeiro.previsao_contratacao
        or financeiro.data_solicitacao_proposta
        or financeiro.data_emissao
    )
    if not base_date:
        return []

    summary = _clean_text(financeiro.follow_up) or "Acompanhar evoluÃ§Ã£o comercial da proposta."
    return [
        {
            "data": _format_date_br(base_date),
            "hora": "10:00",
            "responsavel": _clean_text(financeiro.responsavel),
            "tipoContato": "Acompanhamento comercial",
            "comentario": summary,
            "proximaAcao": summary,
            "dataProximaAcao": _format_date_br(financeiro.previsao_contratacao or base_date),
            "status": FOLLOWUP_STATUSES[0],
        }
    ]


def _build_mock_history(financeiro):
    history = []
    if financeiro.data_emissao:
        history.append(
            {
                "dataHora": f"{_format_date_br(financeiro.data_emissao)} 09:00",
                "usuario": _clean_text(financeiro.responsavel),
                "acao": "Proposta criada",
                "detalhe": "Registro inicial da proposta comercial no mÃ³dulo Comercial.",
            }
        )
    history.append(
        {
            "dataHora": f"{_format_date_br(date.today())} 10:00",
            "usuario": _clean_text(financeiro.responsavel),
            "acao": "Status carregado",
            "detalhe": f"Status atual da proposta: {_display_status(financeiro.status_proposta)}.",
        }
    )
    return history


def _build_default_followup_item(financeiro, summary=""):
    base_date = (
        financeiro.data_entrega_proposta
        or financeiro.previsao_contratacao
        or financeiro.data_solicitacao_proposta
        or financeiro.data_emissao
    )
    if not base_date:
        return None

    normalized_summary = _clean_text(summary) or "Acompanhar evoluÃ§Ã£o comercial da proposta."
    return {
        "data": _format_date_br(base_date),
        "hora": "10:00",
        "responsavel": _clean_text(financeiro.responsavel),
        "tipoContato": "Acompanhamento comercial",
        "comentario": normalized_summary,
        "proximaAcao": normalized_summary,
        "dataProximaAcao": _format_date_br(financeiro.previsao_contratacao or base_date),
        "status": FOLLOWUP_STATUSES[0],
    }


def _build_default_history(financeiro):
    history = []
    if financeiro.data_emissao:
        history.append(
            {
                "dataHora": f"{_format_date_br(financeiro.data_emissao)} 09:00",
                "usuario": _clean_text(financeiro.responsavel),
                "acao": "Proposta criada",
                "detalhe": "Registro inicial da proposta comercial no mÃ³dulo Comercial.",
            }
        )
    return history


def _normalize_followup_item(item, financeiro):
    if not isinstance(item, dict):
        return None

    normalized = {
        "data": _clean_text(item.get("data")),
        "hora": _clean_text(item.get("hora")) or "09:00",
        "responsavel": _clean_text(item.get("responsavel")) or _clean_text(financeiro.responsavel),
        "tipoContato": _clean_text(item.get("tipoContato")) or "Acompanhamento comercial",
        "comentario": _clean_text(item.get("comentario")),
        "proximaAcao": _clean_text(item.get("proximaAcao")) or _clean_text(item.get("comentario")),
        "dataProximaAcao": _clean_text(item.get("dataProximaAcao")) or _clean_text(item.get("data")),
        "status": _clean_text(item.get("status")) or FOLLOWUP_STATUSES[0],
    }

    if not normalized["data"] and not normalized["dataProximaAcao"]:
        fallback = _build_default_followup_item(financeiro, normalized["proximaAcao"] or normalized["comentario"])
        if fallback:
            normalized["data"] = fallback["data"]
            normalized["dataProximaAcao"] = fallback["dataProximaAcao"]

    return normalized


def _normalize_history_entry(entry, financeiro):
    if not isinstance(entry, dict):
        return None

    return {
        "dataHora": _clean_text(entry.get("dataHora")) or f"{_format_date_br(date.today())} 10:00",
        "usuario": _clean_text(entry.get("usuario")) or _clean_text(financeiro.responsavel),
        "acao": _clean_text(entry.get("acao")) or "AtualizaÃ§Ã£o",
        "detalhe": _clean_text(entry.get("detalhe")) or "Registro atualizado no mÃ³dulo Comercial.",
    }


def _load_commercial_bundle(financeiro):
    raw_value = _clean_text(financeiro.follow_up)
    bundle = {"summary": "", "items": [], "history": [], "overrides": {}}

    if not raw_value:
        return bundle

    try:
        parsed = json.loads(raw_value)
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = None

    if isinstance(parsed, dict):
        bundle["summary"] = _clean_text(parsed.get("summary"))
        bundle["items"] = [
            normalized
            for normalized in (_normalize_followup_item(item, financeiro) for item in parsed.get("items", []))
            if normalized
        ]
        bundle["history"] = [
            normalized
            for normalized in (_normalize_history_entry(item, financeiro) for item in parsed.get("history", []))
            if normalized
        ]
        raw_overrides = parsed.get("overrides", {})
        if isinstance(raw_overrides, dict):
            bundle["overrides"] = {
                "empresa": _clean_text(raw_overrides.get("empresa")),
                "unidade": _clean_text(raw_overrides.get("unidade")),
            }
        return bundle

    bundle["summary"] = raw_value
    fallback_item = _build_default_followup_item(financeiro, raw_value)
    if fallback_item:
        bundle["items"] = [fallback_item]
    return bundle


def _dump_commercial_bundle(bundle):
    payload = {
        "summary": _clean_text(bundle.get("summary")),
        "items": bundle.get("items", []),
        "history": bundle.get("history", []),
        "overrides": bundle.get("overrides", {}),
    }
    return json.dumps(payload, cls=DjangoJSONEncoder, ensure_ascii=False)


def _build_commercial_bundle(financeiro):
    bundle = _load_commercial_bundle(financeiro)
    summary = bundle.get("summary") or ""
    items = bundle.get("items", [])
    history = _build_default_history(financeiro) + bundle.get("history", [])
    overrides = bundle.get("overrides") or {}

    if not items and summary:
        fallback_item = _build_default_followup_item(financeiro, summary)
        if fallback_item:
            items = [fallback_item]

    summary_text, summary_date = _resolve_followup_summary_and_date(summary)
    if summary_date:
        summary = _format_date_br(summary_date)
        adjusted_items = []
        for item in items:
            adjusted_items.append(
                {
                    **item,
                    "data": _format_date_br(summary_date),
                    "dataProximaAcao": _format_date_br(summary_date),
                    "comentario": _clean_text(item.get("comentario")) or "Acompanhamento comercial registrado.",
                    "proximaAcao": _clean_text(item.get("proximaAcao") or item.get("comentario")) or "Acompanhamento comercial registrado.",
                }
            )
        items = adjusted_items
    else:
        summary = summary_text

    if not summary and items:
        summary = _clean_text(items[0].get("proximaAcao") or items[0].get("comentario"))

    return {"summary": summary, "items": items, "history": history, "overrides": overrides}


def _serialize_financeiro(financeiro):
    receita = _safe_decimal(financeiro.estimativo_receita)
    tipo_operacao = _resolve_tipo_operacao(financeiro)
    status_display = _display_status(financeiro.status_proposta)
    kanban_stage = _kanban_stage(financeiro.status_proposta)
    cliente_nome = _resolve_cliente_name(financeiro.cliente)
    unidade_nome = _resolve_unidade_name(financeiro.unidade)
    commercial_bundle = _build_commercial_bundle(financeiro)
    overrides = commercial_bundle.get("overrides") or {}
    cliente_nome = overrides.get("empresa") or cliente_nome
    unidade_nome = overrides.get("unidade") or unidade_nome
    campos, total_campos = _serialize_financeiro_campos(financeiro)

    return {
        "id": financeiro.proposta,
        "propostaId": financeiro.proposta,
        "numeroProposta": str(financeiro.proposta),
        "numeroPropostaRaw": str(financeiro.proposta),
        "rev": f"{int(financeiro.revisao or 0):02d}",
        "emissao": _format_date_br(financeiro.data_emissao),
        "emissaoMes": f"{financeiro.data_emissao.month:02d}" if financeiro.data_emissao else "",
        "responsavel": _clean_text(financeiro.responsavel),
        "dataEntregaProposta": _format_date_br(financeiro.data_entrega_proposta),
        "dataSolicitacaoProposta": _format_date_br(financeiro.data_solicitacao_proposta),
        "dataFechamento": _format_date_br(financeiro.data_fechamento_proposta),
        "previsaoContratacao": _format_date_br(financeiro.previsao_contratacao),
        "followUp": commercial_bundle["summary"],
        "natureza": _clean_text(financeiro.natureza),
        "tipoOperacao": tipo_operacao,
        "unidade": unidade_nome,
        "heatMap": str(financeiro.heat_map if financeiro.heat_map is not None else ""),
        "statusProposta": status_display,
        "kanbanStage": kanban_stage,
        "motivoDeclinioPerda": _clean_text(financeiro.motivo_perda),
        "analiseCriticaRealizada": "Sim" if bool(financeiro.analise_critica) else "NÃ£o",
        "pt": _clean_text(financeiro.pt_financeiro),
        "pcPtc": _clean_text(financeiro.pc_ptc),
        "empresa": cliente_nome,
        "uf": _clean_text(financeiro.uf),
        "embarcacaoLocal": unidade_nome,
        "escopo": _clean_text(financeiro.servico) or _clean_text(financeiro.comentario),
        "estimativaReceita": _format_currency_br(receita),
        "estimativaReceitaValor": float(receita),
        "tempoContratoDias": f"{financeiro.tempo_contrato_dias} dias" if financeiro.tempo_contrato_dias else "",
        "tempoContratoDiasValor": financeiro.tempo_contrato_dias or 0,
        "solicitante": _clean_text(financeiro.solicitante),
        "fonteLead": _clean_text(financeiro.fonte_lead),
        "comentario": _clean_text(financeiro.comentario),
        "segmentoCliente": _clean_text(financeiro.segmento_cliente),
        "metodo": _resolve_os_string(financeiro.metodo, "metodo", ""),
        "coordenador": _resolve_os_string(financeiro.cordenador, "coordenador", ""),
        "po": _clean_text(financeiro.po),
        "servico": _clean_text(financeiro.servico),
        "atrasada": _is_proposal_late(financeiro),
        "followUps": commercial_bundle["items"],
        "historico": commercial_bundle["history"],
        "campos": campos,
        "totalCampos": _format_decimal_string(total_campos),
        "totalCamposFormatado": _format_currency_br(total_campos),
    }


def _serialize_agenda_followup(financeiro, item, index=0):
    commercial_bundle = _build_commercial_bundle(financeiro)
    overrides = commercial_bundle.get("overrides") or {}
    cliente_nome = overrides.get("empresa") or _resolve_cliente_name(financeiro.cliente)
    unidade_nome = overrides.get("unidade") or _resolve_unidade_name(financeiro.unidade)
    data_followup = _parse_date_input(item.get("dataProximaAcao") or item.get("data"))
    data_iso = data_followup.isoformat() if data_followup else ""

    return {
        "id": f"{financeiro.proposta}-{index}",
        "proposta_id": financeiro.proposta,
        "numero_proposta": str(financeiro.proposta),
        "cliente": cliente_nome,
        "unidade": unidade_nome,
        "responsavel": _clean_text(item.get("responsavel")) or _clean_text(financeiro.responsavel),
        "data": data_iso,
        "hora": _clean_text(item.get("hora")) or "09:00",
        "status": _clean_text(item.get("status")) or FOLLOWUP_STATUSES[0],
        "titulo": _clean_text(item.get("proximaAcao") or item.get("comentario") or commercial_bundle.get("summary")),
        "comentario": _clean_text(item.get("comentario")),
        "proxima_acao": _clean_text(item.get("proximaAcao") or item.get("comentario")),
        "tipo_contato": _clean_text(item.get("tipoContato")) or "Acompanhamento comercial",
    }


def _collect_followup_agenda_items(queryset=None):
    if queryset is None:
        queryset = Financeiro.objects.select_related(
            "cliente__Cliente",
            "cliente__Unidade",
            "unidade__Cliente",
            "unidade__Unidade",
        ).order_by("-proposta")

    items = []
    for financeiro in queryset:
        bundle = _build_commercial_bundle(financeiro)
        for index, item in enumerate(bundle.get("items", []), start=1):
            serialized = _serialize_agenda_followup(financeiro, item, index=index)
            if serialized["data"]:
                items.append(serialized)

    return sorted(items, key=lambda item: (item.get("data") or "", item.get("hora") or ""))


def _parse_iso_query_date(value):
    text = _clean_text(value)
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _filter_agenda_items(items, *, search="", responsavel="Todos", status="Todos", start_date=None, end_date=None):
    search_term = _normalize_key(search)
    owner_term = _clean_text(responsavel)
    status_term = _clean_text(status)
    filtered = []

    for item in items:
        item_date = _parse_iso_query_date(item.get("data"))
        haystack = " ".join(
            [
                item.get("numero_proposta", ""),
                item.get("cliente", ""),
                item.get("unidade", ""),
                item.get("responsavel", ""),
                item.get("titulo", ""),
                item.get("comentario", ""),
            ]
        )

        if search_term and search_term not in _normalize_key(haystack):
            continue
        if owner_term and owner_term != "Todos" and _clean_text(item.get("responsavel")) != owner_term:
            continue
        if status_term and status_term != "Todos" and _clean_text(item.get("status")) != status_term:
            continue
        if start_date and item_date and item_date < start_date:
            continue
        if end_date and item_date and item_date > end_date:
            continue
        filtered.append(item)

    return filtered


def _build_followup_agenda_summary(items, today=None):
    today = today or timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    status_pending_keys = {"pendente", "sem retorno", "reagendado", "atrasado"}
    owner_totals = {}
    hoje = 0
    esta_semana = 0
    pendentes = 0

    for item in items:
        item_date = _parse_iso_query_date(item.get("data"))
        if item_date == today:
            hoje += 1
        if item_date and week_start <= item_date <= week_end:
            esta_semana += 1

        status_key = _normalize_key(item.get("status"))
        if status_key in status_pending_keys:
            pendentes += 1

        owner = _clean_text(item.get("responsavel")) or "-"
        owner_totals[owner] = owner_totals.get(owner, 0) + 1

    if owner_totals:
        top_owner_name, top_owner_count = max(owner_totals.items(), key=lambda entry: entry[1])
    else:
        top_owner_name, top_owner_count = "-", 0

    return {
        "hoje": hoje,
        "esta_semana": esta_semana,
        "pendentes": pendentes,
        "responsavel_principal": {
            "nome": top_owner_name,
            "total": top_owner_count,
        },
    }


def _build_calendar_days(items):
    counts = {}
    for item in items:
        item_date = _clean_text(item.get("data"))
        if not item_date:
            continue
        counts[item_date] = counts.get(item_date, 0) + 1

    return [{"date": day, "count": total} for day, total in sorted(counts.items())]


def _agenda_status_options(items):
    ordered = []
    seen = set()
    for item in items:
        status = _clean_text(item.get("status"))
        key = _normalize_key(status)
        if not status or key in seen:
            continue
        seen.add(key)
        ordered.append(status)
    return ["Todos", *ordered] if ordered else ["Todos", *FOLLOWUP_STATUSES]


def _agenda_responsavel_options(items):
    ordered = []
    seen = set()
    for item in items:
        responsavel = _clean_text(item.get("responsavel"))
        key = _normalize_key(responsavel)
        if not responsavel or key in seen:
            continue
        seen.add(key)
        ordered.append(responsavel)
    return ["Todos", *ordered]


def _is_proposal_late(financeiro):
    if not financeiro.data_entrega_proposta:
        return False
    if _display_status(financeiro.status_proposta) in FINAL_STATUSES:
        return False
    return financeiro.data_entrega_proposta < date.today()


def _calculate_kpis(serialized_proposals):
    total_receita = sum(Decimal(str(item.get("estimativaReceitaValor") or 0)) for item in serialized_proposals)
    total = len(serialized_proposals)
    em_analise = sum(1 for item in serialized_proposals if item.get("kanbanStage") == "Em Análise")
    em_elaboracao = sum(1 for item in serialized_proposals if item.get("kanbanStage") == "Em Elaboração")
    fechadas = sum(1 for item in serialized_proposals if item.get("kanbanStage") == "Fechada/Contratada")
    atrasadas = sum(1 for item in serialized_proposals if item.get("atrasada"))

    return [
        {"icon": "description", "title": "Total de Propostas", "value": str(total), "filterType": "all"},
        {"icon": "schedule", "title": "Em Análise", "value": str(em_analise)},
        {"icon": "edit", "title": "Em Elaboração", "value": str(em_elaboracao)},
        {"icon": "check_circle", "title": "Fechadas / Contratadas", "value": str(fechadas)},
        {"icon": "warning_amber", "title": "Propostas Atrasadas", "value": str(atrasadas), "alert": True},
        {"icon": "monetization_on", "title": "Receita Estimada", "value": _format_currency_br(total_receita)},
    ]


def _calculate_revenue_by_stage(serialized_proposals):
    amounts = {stage: Decimal("0") for stage in KANBAN_COLUMN_KEYS}
    for item in serialized_proposals:
        stage = item.get("kanbanStage")
        if stage in amounts:
            amounts[stage] += Decimal(str(item.get("estimativaReceitaValor") or 0))

    return [
        {"label": "Em Análise", "value": _format_stage_revenue_br(amounts[KANBAN_COLUMN_KEYS[0]]), "amount": float(amounts[KANBAN_COLUMN_KEYS[0]]), "highlight": False},
        {"label": "Em Elaboração", "value": _format_stage_revenue_br(amounts[KANBAN_COLUMN_KEYS[1]]), "amount": float(amounts[KANBAN_COLUMN_KEYS[1]]), "highlight": False},
        {"label": "Enviadas", "value": _format_stage_revenue_br(amounts["Enviada"]), "amount": float(amounts["Enviada"]), "highlight": False},
        {"label": "Em Negociação", "value": _format_stage_revenue_br(amounts[KANBAN_COLUMN_KEYS[3]]), "amount": float(amounts[KANBAN_COLUMN_KEYS[3]]), "highlight": False},
        {"label": "Fechadas", "value": _format_stage_revenue_br(amounts["Fechada/Contratada"]), "amount": float(amounts["Fechada/Contratada"]), "highlight": True},
    ]


def _distinct_ordered_values(values):
    seen = set()
    output = []
    for value in values:
        cleaned = _clean_text(value)
        if not cleaned:
            continue
        key = _normalize_key(cleaned)
        if key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
    return output


def _build_metadata():
    ordem_servicos = OrdemServico.objects.select_related("Cliente", "Unidade").order_by("-id")[:500]

    clientes = list(Cliente.objects.order_by("nome").values_list("nome", flat=True))
    unidades = list(Unidade.objects.order_by("nome").values_list("nome", flat=True))
    solicitantes = _distinct_ordered_values(getattr(item, "solicitante", "") for item in ordem_servicos)
    coordenadores = _distinct_ordered_values(getattr(item, "coordenador", "") for item in ordem_servicos)
    servicos = [choice[0] for choice in OrdemServico.SERVICO_CHOICES]
    metodos = _distinct_ordered_values(getattr(item, "metodo", "") for item in ordem_servicos)
    pos = _distinct_ordered_values(getattr(item, "po", "") for item in ordem_servicos)

    return {
        "responsaveis": [choice[0] for choice in Financeiro._meta.get_field("responsavel").choices],
        "naturezas": COMMERCIAL_NATURE_OPTIONS,
        "heatMaps": [{"value": str(value), "label": label} for value, label in Financeiro._meta.get_field("heat_map").choices],
        "statusOptions": [item for item in [
            "Sem Retorno",
            "Em Análise",
            "ShortList",
            "Revisada",
            "Perdida/Recusada",
            "Fechada/Contratada",
            "Cancelada",
            "Em Elaboração",
            "Declínio",
            "Avaliando escopo",
            "Aguardando aprovação gestores",
        ]],
        "tipoOperacaoOptions": [choice[0] for choice in OrdemServico.TIPO_OP_CHOICES],
        "metodoOptions": [choice[0] for choice in OrdemServico.METODO_CHOICES],
        "coordenadorOptions": [choice[0] for choice in OrdemServico.COORDENADORES if choice[0]],
        "ufOptions": [choice[0] for choice in Financeiro._meta.get_field("uf").choices],
        "fonteLeadOptions": [choice[0] for choice in Financeiro._meta.get_field("fonte_lead").choices],
        "segmentoOptions": [choice[0] for choice in Financeiro._meta.get_field("segmento_cliente").choices],
        "motivoPerdaOptions": [choice[0] for choice in Financeiro._meta.get_field("motivo_perda").choices],
        "ptOptions": [choice[0] for choice in Financeiro._meta.get_field("pt_financeiro").choices],
        "pcOptions": [choice[0] for choice in Financeiro._meta.get_field("pc_ptc").choices],
        "financeiroCampoChoices": [
            {
                "value": value,
                "label": label,
                "group": "ServiÃ§o" if value == "SERVICO_LIMPEZA_TANQUES" else "Equipamentos e Taxas",
            }
            for value, label in FinanceiroCampo._meta.get_field("nome").choices
        ],
        "clientes": clientes,
        "unidades": unidades,
        "solicitantes": solicitantes,
        "coordenadores": coordenadores,
        "servicos": servicos,
        "metodosDistinct": metodos,
        "poOptions": pos,
        "nextProposalNumber": _get_next_proposal_number(),
    }


def _build_bootstrap_payload():
    propostas = [
        _serialize_financeiro(item)
        for item in Financeiro.objects.select_related(
            "cliente__Cliente",
            "cliente__Unidade",
            "unidade__Cliente",
            "unidade__Unidade",
            "tipo_operacao",
            "metodo",
            "cordenador",
        ).prefetch_related("campos").order_by("-proposta")
    ]

    detail_pattern = reverse("comercial_detalhe_proposta", args=[0]).replace("/0/", "/__id__/")
    status_pattern = reverse("comercial_atualizar_status", args=[0]).replace("/0/", "/__id__/")
    update_pattern = reverse("comercial_atualizar_proposta", args=[0]).replace("/0/", "/__id__/")

    return {
        "proposals": propostas,
        "kpis": _calculate_kpis(propostas),
        "revenueByStage": _calculate_revenue_by_stage(propostas),
        "metadata": _build_metadata(),
        "endpoints": {
            "create": reverse("comercial_criar_proposta"),
            "detailPattern": detail_pattern,
            "statusPattern": status_pattern,
            "updatePattern": update_pattern,
            "quickClientCreate": reverse("comercial_criar_cliente"),
            "quickUnitCreate": reverse("comercial_criar_unidade"),
            "agendaList": reverse("comercial_agenda_followups"),
            "agendaCreate": reverse("comercial_criar_followup"),
        },
        "today": timezone.localdate().isoformat(),
    }


def _filter_serialized_proposals_for_home(
    proposals_list,
    *,
    search="",
    numero="",
    status="",
    natureza="",
    status_proposta="",
    tipo_operacao="",
    responsavel="",
    cliente="",
    unidade="",
    uf="",
    segmento_cliente="",
    fonte_lead="",
    heat_map="",
    motivo_perda="",
    prazo="",
    kpi_filter="",
    focused_stage="",
):
    normalized_search = _clean_text(search).lower()
    normalized_numero = _clean_text(numero).lower()
    normalized_cliente = _clean_text(cliente).lower()
    normalized_unidade = _clean_text(unidade).lower()
    filtered = []

    for proposal in proposals_list:
        haystack = " ".join(
            [
                _clean_text(proposal.get("numeroProposta")),
                _clean_text(proposal.get("empresa")),
                _clean_text(proposal.get("unidade")),
                _clean_text(proposal.get("responsavel")),
            ]
        ).lower()

        if normalized_search and normalized_search not in haystack:
            continue
        if normalized_numero and normalized_numero not in _clean_text(proposal.get("numeroProposta")).lower():
            continue
        if status and proposal.get("kanbanStage") != status:
            continue
        if natureza and proposal.get("natureza") != natureza:
            continue
        if status_proposta and proposal.get("statusProposta") != status_proposta:
            continue
        if tipo_operacao and proposal.get("tipoOperacao") != tipo_operacao:
            continue
        if responsavel and proposal.get("responsavel") != responsavel:
            continue
        if normalized_cliente and normalized_cliente not in _clean_text(proposal.get("empresa")).lower():
            continue
        if normalized_unidade and normalized_unidade not in _clean_text(proposal.get("unidade")).lower():
            continue
        if uf and proposal.get("uf") != uf:
            continue
        if segmento_cliente and proposal.get("segmentoCliente") != segmento_cliente:
            continue
        if fonte_lead and proposal.get("fonteLead") != fonte_lead:
            continue
        if heat_map and proposal.get("heatMap") != heat_map:
            continue
        if motivo_perda and proposal.get("motivoDeclinioPerda") != motivo_perda:
            continue
        if prazo == "atrasada" and not proposal.get("atrasada"):
            continue
        if prazo == "em_dia" and proposal.get("atrasada"):
            continue

        filtered.append(proposal)

    if focused_stage:
        filtered = [proposal for proposal in filtered if proposal.get("kanbanStage") == focused_stage]

    if kpi_filter == "em-analise":
        filtered = [proposal for proposal in filtered if proposal.get("kanbanStage") == "Em Análise"]
    elif kpi_filter == "em-elaboracao":
        filtered = [proposal for proposal in filtered if proposal.get("kanbanStage") == "Em Elaboração"]
    elif kpi_filter == "fechadas":
        filtered = [
            proposal
            for proposal in filtered
            if proposal.get("kanbanStage") == "Fechada/Contratada" or proposal.get("statusProposta") == "Contratada"
        ]
    elif kpi_filter == "atrasadas":
        filtered = [proposal for proposal in filtered if proposal.get("atrasada")]
    elif kpi_filter == "receita":
        filtered = sorted(
            filtered,
            key=lambda proposal: Decimal(str(proposal.get("estimativaReceitaValor") or 0)),
            reverse=True,
        )

    return filtered


def _build_comercial_export_rows(proposals_list):
    rows = []
    for proposal in proposals_list:
        rows.append(
            {
                "Nº da Proposta": proposal.get("numeroPropostaRaw") or proposal.get("numeroProposta"),
                "REV": proposal.get("rev"),
                "Emissão": proposal.get("emissao"),
                "Responsável Comercial": proposal.get("responsavel"),
                "Empresa / Cliente": proposal.get("empresa"),
                "Unidade": proposal.get("unidade"),
                "Tipo de Operação": proposal.get("tipoOperacao"),
                "Natureza": proposal.get("natureza"),
                "Status da Proposta": proposal.get("statusProposta"),
                "Data de Entrega da Proposta": proposal.get("dataEntregaProposta"),
                "Data de Solicitação da Proposta": proposal.get("dataSolicitacaoProposta"),
                "Previsão de Contratação": proposal.get("previsaoContratacao"),
                "Data de Fechamento": proposal.get("dataFechamento"),
                "Acompanhamento": proposal.get("followUp"),
                "Heat Map": proposal.get("heatMap"),
                "Estimativa de Receita": proposal.get("estimativaReceita"),
                "Tempo de Contrato": proposal.get("tempoContratoDias"),
                "Solicitante": proposal.get("solicitante"),
                "Fonte do Lead": proposal.get("fonteLead"),
                "Segmento Cliente": proposal.get("segmentoCliente"),
                "UF": proposal.get("uf"),
                "Motivo de Declínio / Perda": proposal.get("motivoDeclinioPerda"),
                "Serviço / Escopo": proposal.get("servico") or proposal.get("escopo"),
                "Comentário": proposal.get("comentario"),
            }
        )
    return rows


def _read_request_json(request):
    try:
        return json.loads(request.body.decode("utf-8"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _resolve_os_by_value(field_name, raw_value):
    value = _clean_text(raw_value)
    if not value:
        return None

    if value.isdigit():
        record = OrdemServico.objects.filter(pk=int(value)).first()
        if record:
            return record
        record = OrdemServico.objects.filter(numero_os=int(value)).first()
        if record:
            return record

    if field_name == "cliente":
        return OrdemServico.objects.select_related("Cliente").filter(Cliente__nome__iexact=value).order_by("-id").first()
    if field_name == "unidade":
        return OrdemServico.objects.select_related("Unidade").filter(Unidade__nome__iexact=value).order_by("-id").first()
    if field_name == "solicitante":
        return OrdemServico.objects.filter(solicitante__iexact=value).order_by("-id").first()
    if field_name == "tipo_operacao":
        return OrdemServico.objects.filter(tipo_operacao__iexact=value).order_by("-id").first()
    if field_name == "metodo":
        return OrdemServico.objects.filter(metodo__iexact=value).order_by("-id").first()
    if field_name == "cordenador":
        return OrdemServico.objects.filter(coordenador__iexact=value).order_by("-id").first()
    if field_name == "servico":
        return OrdemServico.objects.filter(servico__iexact=value).order_by("-id").first()
    if field_name == "po":
        return OrdemServico.objects.filter(po__iexact=value).order_by("-id").first()

    return None


def _resolve_support_references(payload):
    resolved = {
        "po": _resolve_os_by_value("po", payload.get("po")),
        "cliente": _resolve_os_by_value("cliente", payload.get("cliente")),
        "unidade": _resolve_os_by_value("unidade", payload.get("unidade")),
        "solicitante": _resolve_os_by_value("solicitante", payload.get("solicitante")),
        "tipo_operacao": _resolve_os_by_value("tipo_operacao", payload.get("tipo_operacao")),
        "metodo": _resolve_os_by_value("metodo", payload.get("metodo")),
        "cordenador": _resolve_os_by_value("cordenador", payload.get("coordenador") or payload.get("cordenador")),
        "servico": _resolve_os_by_value("servico", payload.get("servico")),
    }

    base_os = next((item for item in resolved.values() if item is not None), None)
    if base_os is None:
        base_os = OrdemServico.objects.order_by("-id").first()

    tanque = RdoTanque.objects.order_by("-id").first()
    return resolved, base_os, tanque


def _create_financeiro_from_payload(payload):
    proposal_number = _get_next_proposal_number(lock=True)

    revisao_text = _clean_text(payload.get("revisao") or payload.get("rev"))
    if not revisao_text.isdigit():
        return None, {"revisao": "Informe uma revisÃ£o vÃ¡lida."}

    resolved_refs, base_os, tank = _resolve_support_references(payload)
    if base_os is None:
        return None, {
            "referencias": "Cadastre ao menos uma Ordem de ServiÃ§o para vincular os campos obrigatÃ³rios do Financeiro."
        }
    if tank is None:
        return None, {
            "volume_tanque_exec": "Cadastre ao menos um tanque em RDO para concluir a primeira integraÃ§Ã£o do Comercial."
        }

    emissao = _parse_date_input(payload.get("data_emissao"))
    data_entrega = _parse_date_input(payload.get("data_entrega_proposta"))
    data_solicitacao = _parse_date_input(payload.get("data_solicitacao_proposta")) or emissao or date.today()
    previsao_contratacao = _parse_date_input(payload.get("previsao_contratacao")) or data_entrega or data_solicitacao
    data_fechamento = _parse_date_input(payload.get("data_fechamento_proposta"))

    fields = {
        "proposta": proposal_number,
        "revisao": int(revisao_text),
        "data_emissao": emissao,
        "data_solicitacao_proposta": data_solicitacao,
        "data_fechamento_proposta": data_fechamento,
        "previsao_contratacao": previsao_contratacao,
        "follow_up": _clean_text(payload.get("follow_up")),
        "natureza": _clean_text(payload.get("natureza")),
        "heat_map": int(str(payload.get("heat_map") or "0")),
        "motivo_perda": _clean_text(payload.get("motivo_perda")) or "N/A",
        "po": _clean_text(payload.get("po")),
        "cliente": resolved_refs["cliente"] or base_os,
        "unidade": resolved_refs["unidade"] or base_os,
        "solicitante": _clean_text(payload.get("solicitante")),
        "tipo_operacao": resolved_refs["tipo_operacao"] or base_os,
        "metodo": resolved_refs["metodo"] or base_os,
        "data_inicio_frente": base_os,
        "data_fim": base_os,
        "data_fim_frente": base_os,
        "data_entrega_proposta": data_entrega,
        "tempo_contrato_dias": int(payload.get("tempo_contrato_dias") or 0) or None,
        "status_proposta": _clean_text(payload.get("status_proposta")),
        "cordenador": resolved_refs["cordenador"] or base_os,
        "responsavel": _clean_text(payload.get("responsavel")),
        "servico": _clean_text(payload.get("servico")),
        "volume_tanque_exec": tank,
        "comentario": _clean_text(payload.get("comentario")),
        "requisitos_cliente": _clean_text(payload.get("requisitos_cliente")),
        "requisitos_ambipar": _clean_text(payload.get("requisitos_ambipar")),
        "treinamentos": _clean_text(payload.get("treinamentos")),
        "ajuste_operacional": _clean_text(payload.get("ajuste_operacional")),
        "analise_critica": _parse_bool_input(payload.get("analise_critica")),
        "pt_financeiro": _clean_text(payload.get("pt_financeiro")) or "Pendente",
        "pc_ptc": _clean_text(payload.get("pc_ptc")) or "Pendente",
        "uf": _clean_text(payload.get("uf")) or "RJ",
        "estimativo_receita": _parse_decimal_input(payload.get("estimativo_receita")),
        "fonte_lead": _clean_text(payload.get("fonte_lead")),
        "segmento_cliente": _clean_text(payload.get("segmento_cliente")),
        # Campos legados do Financeiro permanecem zerados; os itens reais agora sÃ£o persistidos em FinanceiroCampo.
    }

    required_messages = {}
    if not fields["data_emissao"]:
        required_messages["data_emissao"] = "Informe a data de emissÃ£o."
    if not fields["data_entrega_proposta"]:
        required_messages["data_entrega_proposta"] = "Informe a data de entrega da proposta."
    if not fields["responsavel"]:
        required_messages["responsavel"] = "Selecione o responsÃ¡vel comercial."
    if not fields["natureza"]:
        required_messages["natureza"] = "Selecione a natureza."
    if not fields["status_proposta"]:
        required_messages["status_proposta"] = "Selecione o status da proposta."
    if not _clean_text(payload.get("cliente")):
        required_messages["cliente"] = "Selecione um cliente."
    if not _clean_text(payload.get("unidade")):
        required_messages["unidade"] = "Selecione uma unidade."
    if not _clean_text(payload.get("servico")):
        required_messages["servico"] = "Selecione um serviÃ§o."
    if fields["estimativo_receita"] <= 0:
        required_messages["estimativo_receita"] = "Informe uma estimativa de receita vÃ¡lida."

    if required_messages:
        return None, required_messages

    financeiro = Financeiro(**fields)
    _apply_commercial_bundle_overrides(financeiro, payload)
    return financeiro, {}


def _append_history_to_bundle(financeiro, history_entry):
    if not history_entry:
        return

    bundle = _load_commercial_bundle(financeiro)
    normalized = _normalize_history_entry(history_entry, financeiro)
    if normalized:
        bundle["history"].insert(0, normalized)
        financeiro.follow_up = _dump_commercial_bundle(bundle)


def _store_followup_item(financeiro, followup_item):
    normalized = _normalize_followup_item(followup_item, financeiro)
    if not normalized:
        return

    bundle = _load_commercial_bundle(financeiro)
    bundle["items"] = [item for item in bundle.get("items", []) if item != normalized]
    bundle["items"].insert(0, normalized)
    bundle["summary"] = _clean_text(normalized.get("proximaAcao") or normalized.get("comentario"))
    financeiro.follow_up = _dump_commercial_bundle(bundle)


def _apply_commercial_bundle_overrides(financeiro, payload):
    bundle = _load_commercial_bundle(financeiro)

    if "follow_up" in payload:
        bundle["summary"] = _clean_text(payload.get("follow_up"))

    overrides = bundle.get("overrides") or {}
    empresa = _clean_text(payload.get("cliente"))
    unidade = _clean_text(payload.get("unidade"))

    if empresa:
        overrides["empresa"] = empresa
    if unidade:
        overrides["unidade"] = unidade

    bundle["overrides"] = overrides
    financeiro.follow_up = _dump_commercial_bundle(bundle)


def _parse_financeiro_campos_payload(payload):
    raw_items = payload.get("campos", [])
    if not isinstance(raw_items, list):
        return [], {"campos": "Informe uma lista vÃ¡lida de itens da proposta."}

    valid_codes = {value for value, _label in FinanceiroCampo._meta.get_field("nome").choices}
    parsed_items = []
    errors = {}

    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            errors[f"campos[{index}]"] = "Item invÃ¡lido."
            continue

        nome = _clean_text(raw_item.get("nome"))
        preco_unitario = _parse_decimal_input(raw_item.get("preco_unitario"))
        quantidade = _parse_decimal_input(raw_item.get("quantidade") or 1)

        has_any_value = bool(nome or raw_item.get("preco_unitario") not in (None, "", 0, "0") or raw_item.get("quantidade") not in (None, "", 0, "0"))
        if not has_any_value:
            continue

        if not nome:
            errors[f"campos[{index}].nome"] = "Selecione um item/equipamento."
        elif nome not in valid_codes:
            errors[f"campos[{index}].nome"] = "O item/equipamento informado Ã© invÃ¡lido."

        if preco_unitario <= 0:
            errors[f"campos[{index}].preco_unitario"] = "Informe um preÃ§o unitÃ¡rio vÃ¡lido."

        if quantidade <= 0:
            errors[f"campos[{index}].quantidade"] = "Informe uma quantidade vÃ¡lida."

        if any(key.startswith(f"campos[{index}]") for key in errors):
            continue

        parsed_items.append(
            {
                "nome": nome,
                "preco_unitario": preco_unitario,
                "quantidade": quantidade,
            }
        )

    return parsed_items, errors


def _sync_financeiro_campos(financeiro, campos):
    financeiro.campos.all().delete()
    for item in campos:
        FinanceiroCampo.objects.create(
            financeiro=financeiro,
            nome=item["nome"],
            preco_unitario=item["preco_unitario"],
            quantidade=item["quantidade"],
        )


def _update_financeiro_from_payload(financeiro, payload):
    errors = {}

    text_fields = {
        "po": "po",
        "responsavel": "responsavel",
        "natureza": "natureza",
        "status_proposta": "status_proposta",
        "solicitante": "solicitante",
        "servico": "servico",
        "motivo_perda": "motivo_perda",
        "comentario": "comentario",
        "requisitos_cliente": "requisitos_cliente",
        "requisitos_ambipar": "requisitos_ambipar",
        "treinamentos": "treinamentos",
        "ajuste_operacional": "ajuste_operacional",
        "pt_financeiro": "pt_financeiro",
        "pc_ptc": "pc_ptc",
        "uf": "uf",
        "fonte_lead": "fonte_lead",
        "segmento_cliente": "segmento_cliente",
    }
    for payload_key, model_field in text_fields.items():
        if payload_key in payload:
            setattr(financeiro, model_field, _clean_text(payload.get(payload_key)))

    date_fields = {
        "data_emissao": "data_emissao",
        "data_entrega_proposta": "data_entrega_proposta",
        "data_solicitacao_proposta": "data_solicitacao_proposta",
        "data_fechamento_proposta": "data_fechamento_proposta",
        "previsao_contratacao": "previsao_contratacao",
    }
    for payload_key, model_field in date_fields.items():
        if payload_key in payload:
            setattr(financeiro, model_field, _parse_date_input(payload.get(payload_key)))

    if "revisao" in payload:
        revisao_text = _clean_text(payload.get("revisao"))
        if revisao_text.isdigit():
            financeiro.revisao = int(revisao_text)
        else:
            errors["revisao"] = "Informe uma revisÃ£o vÃ¡lida."

    if "heat_map" in payload:
        heat_map_text = _clean_text(payload.get("heat_map"))
        if heat_map_text.isdigit():
            financeiro.heat_map = int(heat_map_text)
        elif heat_map_text:
            errors["heat_map"] = "Informe um heat map vÃ¡lido."

    if "tempo_contrato_dias" in payload:
        tempo_text = _clean_text(payload.get("tempo_contrato_dias"))
        if not tempo_text:
            financeiro.tempo_contrato_dias = None
        elif tempo_text.isdigit():
            financeiro.tempo_contrato_dias = int(tempo_text)
        else:
            errors["tempo_contrato_dias"] = "Informe um tempo de contrato vÃ¡lido."

    if "estimativo_receita" in payload:
        financeiro.estimativo_receita = _parse_decimal_input(payload.get("estimativo_receita"))

    if "analise_critica" in payload:
        financeiro.analise_critica = _parse_bool_input(payload.get("analise_critica"))

    os_field_map = {
        "cliente": "cliente",
        "unidade": "unidade",
        "tipo_operacao": "tipo_operacao",
        "metodo": "metodo",
        "cordenador": "cordenador",
    }
    for payload_key, model_field in os_field_map.items():
        if payload_key not in payload:
            continue
        raw_value = payload.get(payload_key)
        cleaned_value = _clean_text(raw_value)
        if not cleaned_value:
            continue
        resolved = _resolve_os_by_value(payload_key, cleaned_value)
        if resolved is None:
            errors[payload_key] = f"NÃ£o foi possÃ­vel localizar a referÃªncia para {payload_key.replace('_', ' ')}."
            continue
        setattr(financeiro, model_field, resolved)

    if any(key in payload for key in ("follow_up", "cliente", "unidade")) and "followup_item" not in payload:
        _apply_commercial_bundle_overrides(financeiro, payload)

    if "escopo" in payload:
        financeiro.comentario = _clean_text(payload.get("escopo"))

    followup_item = payload.get("followup_item")
    if followup_item:
        _store_followup_item(financeiro, followup_item)

    history_entry = payload.get("history_entry")
    if history_entry:
        _append_history_to_bundle(financeiro, history_entry)

    return errors


@login_required(login_url="/login/")
def comercial_home(request):
    payload = _build_bootstrap_payload()
    context = {
        "commercial_bootstrap": payload,
        "total_propostas": len(payload.get("proposals", [])),
        "proximo_numero_proposta": payload.get("metadata", {}).get("nextProposalNumber", 1),
    }
    return render(request, "comercial/propostas.html", context)


@login_required(login_url="/login/")
@require_GET
def comercial_exportar_excel(request):
    try:
        import pandas as pd
    except ImportError:
        return JsonResponse(
            {
                "success": False,
                "message": "A exportação em Excel requer pandas e openpyxl instalados no ambiente.",
            },
            status=500,
        )

    payload = _build_bootstrap_payload()
    filtered_proposals = _filter_serialized_proposals_for_home(
        payload.get("proposals", []),
        search=request.GET.get("search", ""),
        numero=request.GET.get("numero", ""),
        status=request.GET.get("status", ""),
        natureza=request.GET.get("natureza", ""),
        status_proposta=request.GET.get("status_proposta", ""),
        tipo_operacao=request.GET.get("tipo_operacao", ""),
        responsavel=request.GET.get("responsavel", ""),
        cliente=request.GET.get("cliente", ""),
        unidade=request.GET.get("unidade", ""),
        uf=request.GET.get("uf", ""),
        segmento_cliente=request.GET.get("segmento_cliente", ""),
        fonte_lead=request.GET.get("fonte_lead", ""),
        heat_map=request.GET.get("heat_map", ""),
        motivo_perda=request.GET.get("motivo_perda", ""),
        prazo=request.GET.get("prazo", ""),
        kpi_filter=request.GET.get("kpi_filter", ""),
        focused_stage=request.GET.get("focused_stage", ""),
    )

    rows = _build_comercial_export_rows(filtered_proposals)
    df = pd.DataFrame(rows or [{"Nenhum resultado": "Nenhuma proposta encontrada para os filtros selecionados."}])

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Propostas Comerciais")
    output.seek(0)

    response = HttpResponse(
        output.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="propostas_comerciais_filtradas.xlsx"'
    return response


@login_required(login_url="/login/")
@require_POST
@transaction.atomic
def comercial_criar_proposta(request):
    payload = _read_request_json(request)
    financeiro, errors = _create_financeiro_from_payload(payload)
    campos, campo_errors = _parse_financeiro_campos_payload(payload)
    if campo_errors:
        errors = {**errors, **campo_errors} if errors else campo_errors
    if errors:
        return JsonResponse(
            {
                "success": False,
                "message": "NÃ£o foi possÃ­vel criar a proposta com os dados enviados.",
                "errors": errors,
            },
            status=400,
        )

    try:
        financeiro.save()
        _sync_financeiro_campos(financeiro, campos)
    except IntegrityError:
        return JsonResponse(
            {
                "success": False,
                "message": "NÃ£o foi possÃ­vel gerar o nÃºmero da proposta. Tente novamente.",
                "errors": {"proposta": "NÃ£o foi possÃ­vel gerar o nÃºmero da proposta. Tente novamente."},
            },
            status=409,
        )

    return JsonResponse(
        {
            "success": True,
            "message": "Proposta criada com sucesso.",
            "proposal": _serialize_financeiro(financeiro),
            "nextProposalNumber": _get_next_proposal_number(),
        }
    )


@login_required(login_url="/login/")
@require_POST
def comercial_criar_cliente(request):
    payload = _read_request_json(request)
    nome = _clean_text(payload.get("nome"))

    if not nome:
        return JsonResponse(
            {"success": False, "message": "Informe o nome do cliente.", "errors": {"nome": "Informe o nome do cliente."}},
            status=400,
        )

    existing = Cliente.objects.filter(nome__iexact=nome).first()
    if existing:
        return JsonResponse(
            {
                "success": True,
                "message": "Cliente jÃ¡ existente selecionado.",
                "cliente": {"value": existing.nome, "label": existing.nome},
            }
        )

    cliente = Cliente.objects.create(nome=nome)
    return JsonResponse(
        {
            "success": True,
            "message": "Cliente cadastrado com sucesso.",
            "cliente": {"value": cliente.nome, "label": cliente.nome},
        }
    )


@login_required(login_url="/login/")
@require_POST
def comercial_criar_unidade(request):
    payload = _read_request_json(request)
    nome = _clean_text(payload.get("nome"))

    if not nome:
        return JsonResponse(
            {"success": False, "message": "Informe o nome da unidade.", "errors": {"nome": "Informe o nome da unidade."}},
            status=400,
        )

    existing = Unidade.objects.filter(nome__iexact=nome).first()
    if existing:
        return JsonResponse(
            {
                "success": True,
                "message": "Unidade jÃ¡ existente selecionada.",
                "unidade": {"value": existing.nome, "label": existing.nome},
            }
        )

    unidade = Unidade.objects.create(nome=nome)
    return JsonResponse(
        {
            "success": True,
            "message": "Unidade cadastrada com sucesso.",
            "unidade": {"value": unidade.nome, "label": unidade.nome},
        }
    )


@login_required(login_url="/login/")
@require_GET
def comercial_agenda_followups(request):
    all_items = _collect_followup_agenda_items()
    search = _clean_text(request.GET.get("q"))
    responsavel = _clean_text(request.GET.get("responsavel")) or "Todos"
    status = _clean_text(request.GET.get("status")) or "Todos"
    start_date = _parse_iso_query_date(request.GET.get("start_date"))
    end_date = _parse_iso_query_date(request.GET.get("end_date"))

    filtered_items = _filter_agenda_items(
        all_items,
        search=search,
        responsavel=responsavel,
        status=status,
        start_date=start_date,
        end_date=end_date,
    )

    return JsonResponse(
        {
            "success": True,
            "summary": _build_followup_agenda_summary(filtered_items, today=timezone.localdate()),
            "items": filtered_items,
            "calendar_days": _build_calendar_days(filtered_items),
            "responsavel_options": _agenda_responsavel_options(all_items),
            "status_options": _agenda_status_options(all_items),
            "total_all": len(all_items),
            "total_filtered": len(filtered_items),
            "today": timezone.localdate().isoformat(),
        }
    )


@login_required(login_url="/login/")
@require_POST
def comercial_criar_followup(request):
    payload = _read_request_json(request)
    proposta_id = _parse_proposal_number(payload.get("proposta_id"))
    proposta = get_object_or_404(Financeiro, proposta=proposta_id)

    data_followup = _parse_date_input(payload.get("data"))
    hora = _clean_text(payload.get("hora")) or "09:00"
    responsavel = _clean_text(payload.get("responsavel")) or _clean_text(proposta.responsavel)
    status = _clean_text(payload.get("status")) or FOLLOWUP_STATUSES[0]
    titulo = _clean_text(payload.get("titulo"))
    comentario = _clean_text(payload.get("comentario"))
    tipo_contato = _clean_text(payload.get("tipo_contato")) or "Acompanhamento comercial"

    errors = {}
    if not data_followup:
        errors["data"] = "Informe a data do acompanhamento."
    if not titulo:
        errors["titulo"] = "Informe o assunto do acompanhamento."
    if not responsavel:
        errors["responsavel"] = "Informe o responsÃ¡vel."
    if errors:
        return JsonResponse(
            {
                "success": False,
                "message": "Não foi possível criar o acompanhamento com os dados enviados.",
                "errors": errors,
            },
            status=400,
        )

    followup_item = {
        "data": data_followup.strftime("%d/%m/%Y"),
        "hora": hora,
        "responsavel": responsavel,
        "tipoContato": tipo_contato,
        "comentario": comentario or titulo,
        "proximaAcao": titulo,
        "dataProximaAcao": data_followup.strftime("%d/%m/%Y"),
        "status": status,
    }

    _store_followup_item(proposta, followup_item)
    _append_history_to_bundle(
        proposta,
        {
            "usuario": _clean_text(request.user.get_username()) or responsavel,
            "acao": "Acompanhamento registrado",
            "detalhe": titulo,
        },
    )
    proposta.save(update_fields=["follow_up"])

    return JsonResponse(
        {
            "success": True,
            "message": "Acompanhamento criado com sucesso.",
            "proposal": _serialize_financeiro(proposta),
            "followup": _serialize_agenda_followup(proposta, followup_item, index=1),
        }
    )


@login_required(login_url="/login/")
@require_GET
def comercial_detalhe_proposta(request, proposta_id):
    proposta = get_object_or_404(
        Financeiro.objects.select_related(
            "cliente__Cliente",
            "cliente__Unidade",
            "unidade__Cliente",
            "unidade__Unidade",
            "tipo_operacao",
            "metodo",
            "cordenador",
        ).prefetch_related("campos"),
        proposta=proposta_id,
    )
    return JsonResponse({"success": True, "proposal": _serialize_financeiro(proposta)})


@login_required(login_url="/login/")
@require_POST
@transaction.atomic
def comercial_atualizar_proposta(request, proposta_id):
    proposta = get_object_or_404(Financeiro, proposta=proposta_id)
    payload = _read_request_json(request)
    errors = _update_financeiro_from_payload(proposta, payload)
    campos = None
    if "campos" in payload:
        campos, campo_errors = _parse_financeiro_campos_payload(payload)
        if campo_errors:
            errors.update(campo_errors)
    if errors:
        return JsonResponse(
            {
                "success": False,
                "message": "NÃ£o foi possÃ­vel atualizar a proposta com os dados enviados.",
                "errors": errors,
            },
            status=400,
        )

    proposta.save()
    if campos is not None:
        _sync_financeiro_campos(proposta, campos)
    return JsonResponse(
        {
            "success": True,
            "message": "Proposta atualizada com sucesso.",
            "proposal": _serialize_financeiro(proposta),
        }
    )


@login_required(login_url="/login/")
@require_POST
def comercial_atualizar_status(request, proposta_id):
    proposta = get_object_or_404(Financeiro, proposta=proposta_id)
    payload = _read_request_json(request)

    next_status = _clean_text(payload.get("status_proposta"))
    motivo = _clean_text(payload.get("motivo_perda"))

    if not next_status:
        return JsonResponse(
            {"success": False, "message": "Selecione um status vÃ¡lido."},
            status=400,
        )

    proposta.status_proposta = next_status
    proposta.motivo_perda = motivo or proposta.motivo_perda or "N/A"
    _append_history_to_bundle(
        proposta,
        {
            "usuario": _clean_text(request.user.get_username()) or _clean_text(proposta.responsavel),
            "acao": "Status alterado",
            "detalhe": f"Status alterado para {_display_status(next_status)}.",
        },
    )
    proposta.save(update_fields=["status_proposta", "motivo_perda", "follow_up"])

    return JsonResponse(
        {
            "success": True,
            "message": "Status atualizado com sucesso.",
            "proposal": _serialize_financeiro(proposta),
        }
    )
