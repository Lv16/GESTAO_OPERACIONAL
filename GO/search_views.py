from datetime import datetime
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.db.models import Case, CharField, IntegerField, Q, Value, When
from django.db.models.functions import Cast
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_GET

from .models import Cliente, Equipamentos, Financeiro, OrdemServico, RDO, Unidade
from .rdo_access import user_can_edit_system, user_can_manage_rdo_permission_users, user_can_use_alerts_ai


RESULT_LIMIT = 5


def _result(icon, title, subtitle, category, url):
    return {
        "icon": icon,
        "title": str(title or ""),
        "subtitle": str(subtitle or ""),
        "category": category,
        "url": url,
    }


def _navigation_results(user, term):
    """Navigation mirrors existing routes and their current visibility rules."""
    can_edit = user_can_edit_system(user)
    can_manage_permissions = user_can_manage_rdo_permission_users(user)
    can_ai = user_can_use_alerts_ai(user)
    # Comercial is currently protected only by login_required; do not invent a
    # second permission rule for search that differs from the module itself.
    items = [
        ("home", "Home", "Ordens de Serviço", "home", reverse("home")),
        ("assignment", "Ordens de Serviço", "Operação", "ordens", reverse("home")),
        ("description", "Relatório Diário de Operação", "Operação", "rdo", reverse("rdo")),
        ("build", "Equipamentos", "Operação", "equipamentos", reverse("equipamentos")),
        ("analytics", "Dashboard RDO", "Operação", "dashboard", reverse("rdo_dashboard")),
        ("show_chart", "Relatório Técnico", "Relatórios", "relatório", reverse("curva_s")),
        ("smartphone", "Download App Mobile", "Outros", "mobile", reverse("mobile_app_download")),
        ("business_center", "Comercial", "Módulo Comercial", "comercial", reverse("comercial_propostas")),
    ]
    if can_manage_permissions:
        items.append(("devices", "Métricas Web e Mobile", "Operação", "métricas", reverse("supervisor_access_dashboard")))
        items.append(("verified_user", "Gerenciar Permissões", "Cadastros", "permissões", reverse("gerenciar_permissoes_rdo")))
    if can_edit:
        items.extend([
            ("person_outline", "Cadastrar Usuário", "Cadastros", "usuários", reverse("cadastrar_usuario")),
            ("badge", "Cadastrar Pessoa", "Cadastros", "pessoas", reverse("cadastrar_pessoa")),
            ("sell", "Cadastrar Função", "Cadastros", "funções", reverse("cadastrar_funcao")),
            ("person_add_alt", "Cadastrar Cliente", "Cadastros", "clientes", reverse("cadastrar_cliente")),
            ("business", "Cadastrar Unidade", "Cadastros", "unidades", reverse("cadastrar_unidade")),
        ])
    if can_ai:
        items.append(("auto_awesome", "Synchro AI", "Outros", "inteligência artificial", reverse("alertas_inteligentes:listar_alertas")))

    normalized = term.casefold()
    exact, partial = [], []
    for icon, title, subtitle, category, url in items:
        haystack = f"{title} {subtitle} {category}".casefold()
        target = _result(icon, title, subtitle, "Navegação", url)
        (exact if normalized == title.casefold() else partial).append(target) if normalized in haystack else None
    return (exact + partial)[:RESULT_LIMIT]


def _os_results(term):
    query = Q(
        Cliente__nome__icontains=term,
    ) | Q(Unidade__nome__icontains=term) | Q(servico__icontains=term) | Q(servicos__icontains=term) | Q(metodo__icontains=term) | Q(coordenador__icontains=term) | Q(supervisor__username__icontains=term) | Q(supervisor__first_name__icontains=term) | Q(supervisor__last_name__icontains=term)
    if term.isdigit():
        query |= Q(numero_os=int(term))
    rows = (
        OrdemServico.objects.annotate(numero_os_search=Cast("numero_os", CharField()))
        .filter(query | Q(numero_os_search__icontains=term))
        .select_related("Cliente", "Unidade", "supervisor")
        .annotate(
            exact_match=Case(When(numero_os=int(term), then=Value(0)), default=Value(1), output_field=IntegerField()) if term.isdigit() else Value(1, output_field=IntegerField())
        )
        .order_by("exact_match", "-id")
        .values("id", "numero_os", "Cliente__nome", "Unidade__nome")[:RESULT_LIMIT]
    )
    return [_result("assignment", f"OS {row['numero_os']}", f"{row['Cliente__nome']} · {row['Unidade__nome']}", "Ordens de Serviço", f"{reverse('home')}?numero_os={row['numero_os']}") for row in rows]


def _rdo_results(term):
    query = Q(rdo__icontains=term) | Q(ordem_servico__Cliente__nome__icontains=term) | Q(ordem_servico__Unidade__nome__icontains=term) | Q(ordem_servico__supervisor__username__icontains=term)
    if term.isdigit():
        query |= Q(ordem_servico__numero_os=int(term))
    try:
        query |= Q(data=datetime.strptime(term, "%Y-%m-%d").date())
    except ValueError:
        pass
    rows = (
        RDO.objects.filter(query)
        .select_related("ordem_servico", "ordem_servico__Cliente", "ordem_servico__Unidade")
        .order_by("-id")
        .values("id", "rdo", "data", "ordem_servico_id", "ordem_servico__numero_os", "ordem_servico__Unidade__nome")[:RESULT_LIMIT]
    )
    return [
        _result(
            "description",
            f"RDO {row['rdo'] or row['id']}",
            f"OS {row['ordem_servico__numero_os'] or '-'} · {row['data'].strftime('%d/%m/%Y') if row['data'] else '-'}",
            "RDO",
            f"{reverse('rdo')}?{urlencode({'rdo_id': row['id'], 'os_id': row['ordem_servico_id'] or '', 'os': row['ordem_servico__numero_os'] or ''})}",
        )
        for row in rows
    ]


def _equipment_results(term):
    query = Q(numero_tag__icontains=term) | Q(numero_serie__icontains=term) | Q(descricao__icontains=term) | Q(fabricante__icontains=term) | Q(cliente__icontains=term) | Q(embarcacao__icontains=term) | Q(numero_os__icontains=term)
    rows = Equipamentos.objects.filter(query).order_by("-pk").values("pk", "numero_tag", "numero_serie", "descricao", "situacao")[:RESULT_LIMIT]
    results = []
    for row in rows:
        identifier = row["numero_tag"] or row["numero_serie"] or f"EQ-{row['pk']:03d}"
        filter_key = "filter_tag" if row["numero_tag"] else ("filter_serie" if row["numero_serie"] else "filter_descricao")
        results.append(_result("build", f"Equipamento {identifier}", f"{row['descricao'] or 'Sem descrição'} · {row['situacao'] or 'Sem situação'}", "Equipamentos", f"{reverse('equipamentos')}?{urlencode({filter_key: identifier if filter_key != 'filter_descricao' else row['descricao'] or ''})}"))
    return results


def _client_unit_results(term, user):
    if not user_can_edit_system(user):
        return []
    results = []
    for row in Cliente.objects.filter(nome__icontains=term).values("nome")[:RESULT_LIMIT]:
        results.append(_result("person_add_alt", row["nome"], "Cliente", "Clientes e Unidades", f"{reverse('home')}?cliente={row['nome']}"))
    remaining = max(0, RESULT_LIMIT - len(results))
    for row in Unidade.objects.filter(nome__icontains=term).values("nome")[:remaining]:
        results.append(_result("business", row["nome"], "Unidade", "Clientes e Unidades", f"{reverse('home')}?unidade={row['nome']}"))
    return results


def _commercial_results(term):
    query = Q(status_proposta__icontains=term) | Q(servico__icontains=term) | Q(cliente__Cliente__nome__icontains=term) | Q(unidade__Unidade__nome__icontains=term)
    if term.isdigit():
        query |= Q(proposta=int(term))
    rows = (
        Financeiro.objects.filter(query)
        .select_related("cliente__Cliente", "unidade__Unidade")
        .annotate(exact_match=Case(When(proposta=int(term), then=Value(0)), default=Value(1), output_field=IntegerField()) if term.isdigit() else Value(1, output_field=IntegerField()))
        .order_by("exact_match", "-proposta")
        .values("proposta", "status_proposta", "cliente__Cliente__nome", "unidade__Unidade__nome")[:RESULT_LIMIT]
    )
    return [_result("business_center", f"Proposta {row['proposta']}", f"{row['cliente__Cliente__nome']} · {row['status_proposta']}", "Comercial", f"{reverse('comercial_propostas')}?proposta={row['proposta']}") for row in rows]


@login_required(login_url="/login/")
@require_GET
def global_search(request):
    term = (request.GET.get("q") or "").strip()[:100]
    if len(term) < 2:
        return JsonResponse({"query": term, "groups": []})

    groups = [
        ("Navegação", _navigation_results(request.user, term)),
        ("Ordens de Serviço", _os_results(term)),
        ("RDO", _rdo_results(term)),
        ("Equipamentos", _equipment_results(term)),
        ("Clientes e Unidades", _client_unit_results(term, request.user)),
        ("Comercial", _commercial_results(term)),
    ]
    return JsonResponse({"query": term, "groups": [{"title": title, "results": results} for title, results in groups if results]})
