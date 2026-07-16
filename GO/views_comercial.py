import json
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
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
    "Declínio",
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

    summary = _clean_text(financeiro.follow_up) or "Acompanhar evolução comercial da proposta."
    return [
        {
            "data": _format_date_br(base_date),
            "hora": "10:00",
            "responsavel": _clean_text(financeiro.responsavel),
            "tipoContato": "Follow-up comercial",
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
                "detalhe": "Registro inicial da proposta comercial no módulo Comercial.",
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

    normalized_summary = _clean_text(summary) or "Acompanhar evolução comercial da proposta."
    return {
        "data": _format_date_br(base_date),
        "hora": "10:00",
        "responsavel": _clean_text(financeiro.responsavel),
        "tipoContato": "Follow-up comercial",
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
                "detalhe": "Registro inicial da proposta comercial no módulo Comercial.",
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
        "tipoContato": _clean_text(item.get("tipoContato")) or "Follow-up comercial",
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
        "acao": _clean_text(entry.get("acao")) or "Atualização",
        "detalhe": _clean_text(entry.get("detalhe")) or "Registro atualizado no módulo Comercial.",
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
        "analiseCriticaRealizada": "Sim" if bool(financeiro.analise_critica) else "Não",
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
        {"label": "Em Análise", "value": _format_millions_br(amounts["Em Análise"]), "amount": float(amounts["Em Análise"]), "highlight": False},
        {"label": "Em Elaboração", "value": _format_millions_br(amounts["Em Elaboração"]), "amount": float(amounts["Em Elaboração"]), "highlight": False},
        {"label": "Enviadas", "value": _format_millions_br(amounts["Enviada"]), "amount": float(amounts["Enviada"]), "highlight": False},
        {"label": "Em Negociação", "value": _format_millions_br(amounts["Em Negociação"]), "amount": float(amounts["Em Negociação"]), "highlight": False},
        {"label": "Fechadas", "value": _format_millions_br(amounts["Fechada/Contratada"]), "amount": float(amounts["Fechada/Contratada"]), "highlight": True},
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
                "group": "Serviço" if value == "SERVICO_LIMPEZA_TANQUES" else "Equipamentos e Taxas",
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
        },
        "today": date.today().isoformat(),
    }


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
        return None, {"revisao": "Informe uma revisão válida."}

    resolved_refs, base_os, tank = _resolve_support_references(payload)
    if base_os is None:
        return None, {
            "referencias": "Cadastre ao menos uma Ordem de Serviço para vincular os campos obrigatórios do Financeiro."
        }
    if tank is None:
        return None, {
            "volume_tanque_exec": "Cadastre ao menos um tanque em RDO para concluir a primeira integração do Comercial."
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
        # Campos legados do Financeiro permanecem zerados; os itens reais agora são persistidos em FinanceiroCampo.
    }

    required_messages = {}
    if not fields["data_emissao"]:
        required_messages["data_emissao"] = "Informe a data de emissão."
    if not fields["data_entrega_proposta"]:
        required_messages["data_entrega_proposta"] = "Informe a data de entrega da proposta."
    if not fields["responsavel"]:
        required_messages["responsavel"] = "Selecione o responsável comercial."
    if not fields["natureza"]:
        required_messages["natureza"] = "Selecione a natureza."
    if not fields["status_proposta"]:
        required_messages["status_proposta"] = "Selecione o status da proposta."
    if not _clean_text(payload.get("cliente")):
        required_messages["cliente"] = "Selecione um cliente."
    if not _clean_text(payload.get("unidade")):
        required_messages["unidade"] = "Selecione uma unidade."
    if not _clean_text(payload.get("servico")):
        required_messages["servico"] = "Selecione um serviço."
    if fields["estimativo_receita"] <= 0:
        required_messages["estimativo_receita"] = "Informe uma estimativa de receita válida."

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
        return [], {"campos": "Informe uma lista válida de itens da proposta."}

    valid_codes = {value for value, _label in FinanceiroCampo._meta.get_field("nome").choices}
    parsed_items = []
    errors = {}

    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            errors[f"campos[{index}]"] = "Item inválido."
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
            errors[f"campos[{index}].nome"] = "O item/equipamento informado é inválido."

        if preco_unitario <= 0:
            errors[f"campos[{index}].preco_unitario"] = "Informe um preço unitário válido."

        if quantidade <= 0:
            errors[f"campos[{index}].quantidade"] = "Informe uma quantidade válida."

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
            errors["revisao"] = "Informe uma revisão válida."

    if "heat_map" in payload:
        heat_map_text = _clean_text(payload.get("heat_map"))
        if heat_map_text.isdigit():
            financeiro.heat_map = int(heat_map_text)
        elif heat_map_text:
            errors["heat_map"] = "Informe um heat map válido."

    if "tempo_contrato_dias" in payload:
        tempo_text = _clean_text(payload.get("tempo_contrato_dias"))
        if not tempo_text:
            financeiro.tempo_contrato_dias = None
        elif tempo_text.isdigit():
            financeiro.tempo_contrato_dias = int(tempo_text)
        else:
            errors["tempo_contrato_dias"] = "Informe um tempo de contrato válido."

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
            errors[payload_key] = f"Não foi possível localizar a referência para {payload_key.replace('_', ' ')}."
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
                "message": "Não foi possível criar a proposta com os dados enviados.",
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
                "message": "Não foi possível gerar o número da proposta. Tente novamente.",
                "errors": {"proposta": "Não foi possível gerar o número da proposta. Tente novamente."},
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
                "message": "Cliente já existente selecionado.",
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
                "message": "Unidade já existente selecionada.",
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
                "message": "Não foi possível atualizar a proposta com os dados enviados.",
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
            {"success": False, "message": "Selecione um status válido."},
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
