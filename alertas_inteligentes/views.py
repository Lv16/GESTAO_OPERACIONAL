from django.db.models import Case, Count, IntegerField, When
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
import json

from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from urllib.parse import urlencode
from .models import (
    AlertaInteligente,
    AlertaOperacionalInteligente,
    ExemploIntencaoIA,
    PerguntaAssistenteIA,
)
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from .permissions import permissao_ia_rdo_required, superuser_ia_required
from .services.aprendizado_ia import aprovar_pergunta_como_exemplo
from .services.chat_formatters import sanitizar_resultado_chat
from .services.assistente_livre import (
    montar_resposta_pendencias_inteligentes,
    responder_alertas_pendentes,
    responder_pergunta_livre,
)
from GO.rdo_access import user_can_use_alerts_ai
from .notification_center import (
    filtered_page,
    get_accessible_alert,
    mark_all_read,
    notification_snapshot,
    serialize_alert,
    set_read_state,
)

SESSAO_HISTORICO_IA = "alertas_inteligentes_historico"
SESSAO_CONTEXTO_IA = "alertas_inteligentes_contexto"
EQUIPE_LABELS_ALERTA = dict(AlertaInteligente.EQUIPES)


def _notification_api_forbidden(request):
    if not getattr(request.user, "is_authenticated", False):
        return JsonResponse({"success": False, "error": "Autenticação necessária."}, status=401)
    if not user_can_use_alerts_ai(request.user):
        return JsonResponse({"success": False, "error": "Sem permissão para visualizar alertas da IA."}, status=403)
    return None


def _json_body(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return {}


def api_notificacoes(request):
    forbidden = _notification_api_forbidden(request)
    if forbidden:
        return forbidden
    if request.method != "GET":
        return JsonResponse({"success": False, "error": "Método não permitido."}, status=405)
    payload = filtered_page(
        request.user,
        tab=request.GET.get("tab", "pendentes"),
        query=request.GET.get("q", ""),
        priority=request.GET.get("prioridade", ""),
        page=request.GET.get("page", 1),
        page_size=request.GET.get("page_size", 20),
    )
    payload["success"] = True
    return JsonResponse(payload)


def api_notificacao_detalhe(request, source, alert_id):
    forbidden = _notification_api_forbidden(request)
    if forbidden:
        return forbidden
    if request.method != "GET":
        return JsonResponse({"success": False, "error": "Método não permitido."}, status=405)
    result = get_accessible_alert(request.user, source, alert_id)
    if not result:
        return JsonResponse({"success": False, "error": "Alerta não encontrado."}, status=404)
    alert, is_read = result
    return JsonResponse({"success": True, "item": serialize_alert(source, alert, is_read)})


def api_notificacao_leitura(request, source, alert_id):
    forbidden = _notification_api_forbidden(request)
    if forbidden:
        return forbidden
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Método não permitido."}, status=405)
    result = get_accessible_alert(request.user, source, alert_id)
    if not result:
        return JsonResponse({"success": False, "error": "Alerta não encontrado."}, status=404)
    alert, _ = result
    body = _json_body(request)
    is_read = body.get("lido")
    if not isinstance(is_read, bool):
        return JsonResponse({"success": False, "error": "Informe um estado de leitura válido."}, status=400)
    set_read_state(request.user, source, alert, is_read)
    snapshot = notification_snapshot(request.user)
    return JsonResponse(
        {
            "success": True,
            "item": serialize_alert(source, alert, is_read),
            "unread_count": snapshot["unread_count"],
            "compact_items": snapshot["items"],
        }
    )


def api_notificacoes_marcar_todas_lidas(request):
    forbidden = _notification_api_forbidden(request)
    if forbidden:
        return forbidden
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Método não permitido."}, status=405)
    marked_count = mark_all_read(request.user)
    snapshot = notification_snapshot(request.user)
    return JsonResponse(
        {
            "success": True,
            "marked_count": marked_count,
            "unread_count": snapshot["unread_count"],
            "compact_items": snapshot["items"],
        }
    )


@superuser_ia_required
def listar_alertas(request):
    return assistente_rdo(request)


@superuser_ia_required
def assistente_rdo(request):
    resultado = None
    acao = request.GET.get("acao")
    if acao == "nova_conversa":
        limpar_conversa_ia(request)
        return redirect("alertas_inteligentes:assistente_rdo")

    os_numero = request.GET.get("os")
    rdo_numero = request.GET.get("rdo")
    pergunta_livre = (request.GET.get("pergunta") or "").strip()
    contexto_conversa = request.session.get(SESSAO_CONTEXTO_IA, {})
    historico_conversa = request.session.get(SESSAO_HISTORICO_IA, [])
    pergunta = (
        pergunta_livre
        if acao == "pergunta_livre" and pergunta_livre
        else pergunta_da_acao(acao, os_numero)
    )

    if acao == "pergunta_livre" and pergunta_livre:
        resultado = responder_pergunta_livre(pergunta_livre, contexto=contexto_conversa)
    elif acao == "alertas_pendentes":
        resultado = gerar_resposta_alertas_pendentes()
    elif acao == "os_sem_rdo_recente":
        resultado = gerar_resposta_os_sem_rdo_recente()
    elif acao == "supervisores_conflito":
        resultado = gerar_resposta_supervisores_em_conflito()
    elif acao == "pendencias_operacionais":
        resultado = gerar_resposta_pendencias_operacionais()
    elif acao == "rdos_criticos":
        resultado = gerar_resposta_rdos_criticos()
    elif acao == "pendencias_por_equipe":
        resultado = gerar_resposta_pendencias_por_equipe()
    elif acao == "resumo_os" and os_numero:
        resultado = gerar_resposta_resumo_os(os_numero)

    if resultado and pergunta:
        resultado = sanitizar_resultado_chat(resultado)
        atualizar_conversa_ia(request, pergunta, resultado)
        contexto_conversa = request.session.get(SESSAO_CONTEXTO_IA, {})
        historico_conversa = request.session.get(SESSAO_HISTORICO_IA, [])
    elif resultado:
        resultado = sanitizar_resultado_chat(resultado)

    # Se for requisição AJAX, retornar apenas o fragmento da resposta
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if is_ajax and resultado:
        return render(
            request,
            "alertas_inteligentes/resultado_partial.html",
            {"resultado": resultado},
        )

    return render(
        request,
        "alertas_inteligentes/listar.html",
        {
            "resultado": resultado,
            "pergunta": pergunta,
            "acao": acao,
            "os_numero": os_numero,
            "rdo_numero": rdo_numero,
            "pergunta_livre": "" if acao == "pergunta_livre" else pergunta_livre,
            "historico_conversa": historico_conversa[:-1] if resultado and pergunta else historico_conversa,
            "contexto_conversa": contexto_conversa,
        },
    )


@superuser_ia_required
def supervisionar_aprendizado(request):
    if request.method == "POST":
        pergunta = get_object_or_404(PerguntaAssistenteIA, pk=request.POST.get("pergunta_id"))
        intencao = (request.POST.get("intencao") or "").strip()
        filtro_status = (request.POST.get("status") or "pendentes").strip()
        page = (request.POST.get("page") or "1").strip()
        if intencao in dict(ExemploIntencaoIA.INTENCOES):
            pergunta.intencao_detectada = intencao
            pergunta.save(update_fields=["intencao_detectada"])
            aprovar_pergunta_como_exemplo(pergunta, intencao, usuario=request.user)
        query = urlencode({"status": filtro_status, "page": page})
        return redirect(f"{reverse('alertas_inteligentes:supervisionar_aprendizado')}?{query}")

    filtro_status = (request.GET.get("status") or "pendentes").strip()
    perguntas = PerguntaAssistenteIA.objects.select_related(
        "revisada_por",
        "exemplo_aprovado",
    )
    if filtro_status == "pendentes":
        perguntas = perguntas.exclude(status="revisada")
    elif filtro_status in {"entendida", "nao_entendida", "revisada"}:
        perguntas = perguntas.filter(status=filtro_status)

    perguntas = perguntas.order_by("-criada_em")
    # Paginar resultados para evitar pagina muito longa
    page = request.GET.get('page', 1)
    paginator = Paginator(perguntas, 20)
    try:
        perguntas_page = paginator.page(page)
    except (PageNotAnInteger, EmptyPage):
        perguntas_page = paginator.page(1)

    contexto = {
        "perguntas": perguntas_page,
        "page_obj": perguntas_page,
        "paginator": paginator,
        "intencoes": ExemploIntencaoIA.INTENCOES,
        "filtro_status": filtro_status,
        "totais": {
            "pendentes": PerguntaAssistenteIA.objects.exclude(status="revisada").count(),
            "nao_entendidas": PerguntaAssistenteIA.objects.filter(status="nao_entendida").count(),
            "revisadas": PerguntaAssistenteIA.objects.filter(status="revisada").count(),
            "exemplos": ExemploIntencaoIA.objects.filter(ativo=True).count(),
        },
    }
    return render(
        request,
        "alertas_inteligentes/supervisionar_aprendizado.html",
        contexto,
    )


def pergunta_da_acao(acao, os_numero=None):
    perguntas = {
        "alertas_pendentes": "Quais alertas inteligentes ainda estao pendentes?",
        "os_sem_rdo_recente": "Quais linhas operacionais estao sem RDO recente?",
        "supervisores_conflito": "Existem supervisores em possivel conflito operacional?",
        "pendencias_operacionais": "Quais pendencias operacionais precisam da minha atencao?",
        "rdos_criticos": "Quais RDOs precisam da minha atencao primeiro?",
        "pendencias_por_equipe": "Como estao as pendencias por equipe?",
    }
    if acao == "resumo_os" and os_numero:
        return f"Analise a OS {os_numero} para mim."
    return perguntas.get(acao, "")


def atualizar_conversa_ia(request, pergunta, resultado):
    historico = request.session.get(SESSAO_HISTORICO_IA, [])
    historico.append(
        {
            "pergunta": pergunta,
            "introducao": resultado.get("introducao", ""),
            "recomendacao": resultado.get("recomendacao", ""),
        }
    )
    request.session[SESSAO_HISTORICO_IA] = historico[-20:]

    contexto_atual = dict(request.session.get(SESSAO_CONTEXTO_IA, {}))
    contexto_atual.update(resultado.get("contexto") or {})
    request.session[SESSAO_CONTEXTO_IA] = contexto_atual
    request.session.modified = True


def limpar_conversa_ia(request):
    request.session.pop(SESSAO_HISTORICO_IA, None)
    request.session.pop(SESSAO_CONTEXTO_IA, None)
    request.session.modified = True


@permissao_ia_rdo_required
def resolver_alerta(request, alerta_id):
    if request.method == "POST":
        alerta = get_object_or_404(AlertaInteligente, pk=alerta_id)
        alerta.status = "resolvido"
        alerta.resolvido_em = timezone.now()
        alerta.resolvido_por = request.user
        alerta.save(update_fields=["status", "resolvido_em", "resolvido_por"])

    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url:
        return redirect(next_url)
    return redirect("alertas_inteligentes:listar_alertas")


@permissao_ia_rdo_required
def ignorar_alerta(request, alerta_id):
    if request.method == "POST":
        alerta = get_object_or_404(AlertaInteligente, pk=alerta_id)
        justificativa = (request.POST.get("justificativa") or "").strip()
        alerta.status = "ignorado"
        alerta.justificativa = justificativa
        alerta.resolvido_em = timezone.now()
        alerta.ignorado_por = request.user
        alerta.save(
            update_fields=[
                "status",
                "justificativa",
                "resolvido_em",
                "ignorado_por",
            ]
        )

    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url:
        return redirect(next_url)
    return redirect("alertas_inteligentes:listar_alertas")


@permissao_ia_rdo_required
def resolver_alerta_operacional(request, alerta_id):
    alerta = get_object_or_404(AlertaOperacionalInteligente, id=alerta_id)

    if request.method == "POST":
        alerta.status = "resolvido"
        alerta.resolvido_em = timezone.now()
        alerta.resolvido_por = request.user
        alerta.save(update_fields=["status", "resolvido_em", "resolvido_por"])

    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url:
        return redirect(next_url)
    return redirect("alertas_inteligentes:assistente_rdo")


@permissao_ia_rdo_required
def ignorar_alerta_operacional(request, alerta_id):
    alerta = get_object_or_404(AlertaOperacionalInteligente, id=alerta_id)

    if request.method == "POST":
        justificativa = (request.POST.get("justificativa") or "").strip()
        alerta.status = "ignorado"
        alerta.justificativa = justificativa
        alerta.resolvido_em = timezone.now()
        alerta.ignorado_por = request.user
        alerta.save(
            update_fields=[
                "status",
                "justificativa",
                "resolvido_em",
                "ignorado_por",
            ]
        )

    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url:
        return redirect(next_url)
    return redirect("alertas_inteligentes:assistente_rdo")


def gerar_resposta_alertas_pendentes():
    return responder_alertas_pendentes()


def prioridade_operacional():
    return Case(
        When(prioridade="critica", then=0),
        When(prioridade="alta", then=1),
        When(prioridade="media", then=2),
        When(prioridade="baixa", then=3),
        default=4,
        output_field=IntegerField(),
    )


def gerar_resposta_os_sem_rdo_recente():
    alertas = (
        AlertaOperacionalInteligente.objects
        .filter(
            status="pendente",
            tipo="OS_SEM_RDO_RECENTE",
        )
        .select_related("ordem_servico")
        .annotate(ordem_prioridade=prioridade_operacional())
        .order_by("ordem_prioridade", "-criado_em")[:15]
    )

    total = AlertaOperacionalInteligente.objects.filter(
        status="pendente",
        tipo="OS_SEM_RDO_RECENTE",
    ).count()

    if total == 0:
        return {
            "introducao": "Nao encontrei linhas operacionais em andamento sem RDO recente.",
            "alertas_operacionais": [],
            "alertas": [],
            "recomendacao": "Nenhuma acao operacional e necessaria para esse ponto no momento.",
        }

    return {
        "introducao": (
            f"Encontrei {total} linha(s) operacional(is) em andamento sem RDO recente. "
            "Listei abaixo as principais para revisao:"
        ),
        "alertas_operacionais": alertas,
        "alertas": [],
        "recomendacao": (
            "Recomendo verificar se essas operacoes continuam ativas. "
            "Se continuarem, confirme se ha RDO pendente de lancamento. "
            "Caso contrario, atualize o status da linha operacional."
        ),
    }


def gerar_resposta_supervisores_em_conflito():
    alertas = (
        AlertaOperacionalInteligente.objects
        .filter(
            status="pendente",
            tipo="SUPERVISOR_EM_OS_SIMULTANEAS",
        )
        .select_related("ordem_servico")
        .order_by("-criado_em")
    )

    if not alertas.exists():
        return {
            "introducao": "Nao encontrei supervisores vinculados em linhas operacionais conflitantes.",
            "alertas_operacionais": [],
            "alertas": [],
            "recomendacao": "Nenhuma acao e necessaria para alocacao de supervisores no momento.",
        }

    return {
        "introducao": (
            f"Encontrei {alertas.count()} alerta(s) de possivel conflito de supervisor. "
            "Isso indica que o mesmo supervisor aparece em linhas operacionais abertas de OS diferentes:"
        ),
        "alertas_operacionais": alertas,
        "alertas": [],
        "recomendacao": (
            "Recomendo confirmar se o supervisor realmente esta alocado nessas operacoes "
            "ou se alguma movimentacao anterior precisa ser finalizada."
        ),
    }


def gerar_resposta_pendencias_operacionais():
    return montar_resposta_pendencias_inteligentes(limit_operacionais=20, limit_rdo=20)


def gerar_resposta_rdos_criticos():
    alertas = (
        AlertaInteligente.objects.filter(
            status="pendente",
            prioridade__in=["alta", "critica"],
        )
        .select_related("rdo", "rdo__ordem_servico")
        .order_by("-criado_em")[:10]
    )

    if not alertas.exists():
        return {
            "introducao": "Verifiquei os alertas de maior prioridade e nao encontrei RDOs criticos ou de alta prioridade agora.",
            "alertas": [],
            "recomendacao": "Voce pode seguir para os alertas de media e baixa prioridade, ou consultar uma OS especifica.",
        }

    return {
        "introducao": (
            f"Eu encontrei {alertas.count()} RDO(s) com alertas de maior prioridade. "
            "Estes sao os pontos que eu revisaria primeiro, porque podem impactar a consistencia operacional."
        ),
        "alertas": alertas,
        "recomendacao": (
            "Trate estes RDOs antes dos demais, porque eles tendem a impactar liberacao, seguranca, "
            "QSMS ou consistencia operacional."
        ),
    }


def gerar_resposta_pendencias_por_equipe():
    dados = (
        AlertaInteligente.objects.filter(status="pendente")
        .values("equipe_responsavel")
        .annotate(total=Count("id"))
        .order_by("-total")
    )
    alertas = (
        AlertaInteligente.objects.filter(status="pendente")
        .select_related("rdo", "rdo__ordem_servico")
        .order_by("equipe_responsavel", "-criado_em")[:10]
    )

    if not dados:
        return {
            "introducao": "Nao encontrei pendencias inteligentes separadas por equipe no momento.",
            "alertas": [],
            "recomendacao": "Nenhuma equipe possui alertas pendentes agora.",
        }

    linhas = [
        "Eu agrupei as pendencias por equipe para mostrar onde esta a maior concentracao de tratamento:"
    ]
    for item in dados:
        equipe_codigo = item["equipe_responsavel"] or "sem equipe"
        equipe = EQUIPE_LABELS_ALERTA.get(equipe_codigo, str(equipe_codigo).title())
        linhas.append(f"- {equipe}: {item['total']} pendencia(s)")

    return {
        "introducao": "\n".join(linhas),
        "alertas": alertas,
        "recomendacao": "Direcione a tratativa para a equipe responsavel e use os RDOs listados abaixo como ponto de partida.",
    }


def gerar_resposta_resumo_os(os_numero):
    alertas = (
        AlertaInteligente.objects.filter(
            status="pendente",
            rdo__ordem_servico__numero_os=os_numero,
        )
        .select_related("rdo", "rdo__ordem_servico")
        .order_by("rdo_id")
    )

    if not alertas.exists():
        return {
            "introducao": f"Analisei a OS {os_numero} e nao encontrei alertas pendentes para ela.",
            "alertas": [],
            "recomendacao": "Se houve uma correcao recente, mantenha os RDOs marcados para reanalise para confirmar que a IA continua sem apontamentos.",
        }

    return {
        "introducao": f"Analisei a OS {os_numero} e encontrei {alertas.count()} ponto(s) que merecem atencao. Organizei cada apontamento para facilitar a correcao.",
        "alertas": alertas,
        "recomendacao": "Abra cada RDO, confira o campo citado e depois resolva ou justifique o alerta de acordo com a situacao real da operacao.",
    }
