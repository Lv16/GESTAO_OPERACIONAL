import json

from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST

from .rdo_access import (
    ALERTS_AI_GROUP_NAME,
    RDO_DELETE_GROUP_NAME,
    RDO_PERMISSION_MANAGER_GROUP_NAME,
    RDO_VIEW_ONLY_GROUP_NAME,
    RESPONSAVEIS_COORDENADORES_MANAGER_GROUP_NAME,
    SYSTEM_READ_ONLY_GROUP_NAME,
    build_read_only_forbidden_response,
    ensure_rdo_access_groups,
    list_permission_managed_users,
    user_has_read_only_access,
    user_can_manage_rdo_permission_users,
    user_can_manage_responsaveis_coordenadores,
)


@csrf_protect
def cadastrar_usuario(request):
    if user_has_read_only_access(getattr(request, 'user', None)):
        return build_read_only_forbidden_response('cadastrar usuarios')

    if request.method == 'POST':
        from django.contrib.auth.models import Group, User

        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        is_supervisor = request.POST.get('is_supervisor')

        if username and password and (is_supervisor or email):
            if not User.objects.filter(username=username).exists():
                user = User.objects.create_user(username=username, email=email or '', password=password)
                if is_supervisor:
                    group_name = 'Supervisor'
                    try:
                        group_obj, _ = Group.objects.get_or_create(name=group_name)
                        user.groups.add(group_obj)
                    except Exception:
                        pass
                return render(request, 'cadastrar_usuario.html', {'success': True})
            return render(request, 'cadastrar_usuario.html', {'error': 'Usuario ja existe.'})
        return render(
            request,
            'cadastrar_usuario.html',
            {'error': 'Preencha todos os campos (email opcional para Supervisor). '},
        )

    return render(request, 'cadastrar_usuario.html')


@login_required(login_url='/login/')
@csrf_protect
def _legacy_gerenciar_permissoes_rdo(request):
    if not user_can_manage_rdo_permission_users(getattr(request, 'user', None)):
        return HttpResponseForbidden('Sem permissao para gerenciar acessos de exclusao de RDO.')

    groups_info = ensure_rdo_access_groups()
    delete_group = groups_info['delete_group']
    manager_group = groups_info['manager_group']
    alerts_ai_group = groups_info['alerts_ai_group']
    read_only_group = groups_info['read_only_group']
    rdo_view_only_group = groups_info['rdo_view_only_group']
    users = list(list_permission_managed_users())

    success_message = None
    error_message = None

    if request.method == 'POST':
        status_user_id = str(request.POST.get('status_user_id', '') or '').strip()
        status_action = str(request.POST.get('status_action', '') or '').strip().lower()

        if status_user_id and status_action in {'deactivate', 'activate'}:
            target_user = None
            for user_obj in users:
                if str(getattr(user_obj, 'id', '')).strip() == status_user_id:
                    target_user = user_obj
                    break

            if target_user is None:
                error_message = 'Usuario nao encontrado para atualizacao.'
            elif getattr(target_user, 'id', None) == getattr(request.user, 'id', None):
                error_message = 'Voce nao pode alterar o proprio usuario por esta tela.'
            elif getattr(target_user, 'is_superuser', False):
                error_message = 'Nao e permitido alterar superusuarios por esta tela.'
            else:
                from .models import MobileApiToken

                with transaction.atomic():
                    target_user.is_active = status_action == 'activate'
                    target_user.save(update_fields=['is_active'])
                    if status_action == 'deactivate':
                        MobileApiToken.objects.filter(user=target_user, is_active=True).update(is_active=False)

                if status_action == 'activate':
                    success_message = f'Usuario {target_user.username} reativado com sucesso.'
                else:
                    success_message = f'Usuario {target_user.username} desativado com sucesso.'
                users = list(list_permission_managed_users())
        else:
            delete_user_ids = {
                str(value).strip()
                for value in (request.POST.getlist('delete_rdo_users') or [])
                if str(value).strip()
            }
            manager_user_ids = {
                str(value).strip()
                for value in (request.POST.getlist('manage_rdo_permission_users') or [])
                if str(value).strip()
            }
            alerts_ai_user_ids = {
                str(value).strip()
                for value in (request.POST.getlist('alerts_ai_users') or [])
                if str(value).strip()
            }
            read_only_user_ids = {
                str(value).strip()
                for value in (request.POST.getlist('read_only_users') or [])
                if str(value).strip()
            }
            rdo_view_only_user_ids = {
                str(value).strip()
                for value in (request.POST.getlist('rdo_view_only_users') or [])
                if str(value).strip()
            }
            current_user_id = str(getattr(request.user, 'id', '')).strip()

            # Avoid locking out a non-superuser manager from this screen.
            if current_user_id and not getattr(request.user, 'is_superuser', False):
                manager_user_ids.add(current_user_id)
                if current_user_id in read_only_user_ids:
                    read_only_user_ids.discard(current_user_id)
                    error_message = 'Voce nao pode definir o proprio usuario como somente visualizacao por esta tela.'

            with transaction.atomic():
                for user_obj in users:
                    user_id = str(getattr(user_obj, 'id', '')).strip()
                    if not user_id:
                        continue
                    if not getattr(user_obj, 'is_active', True):
                        continue

                    should_delete = user_id in delete_user_ids
                    should_manage = user_id in manager_user_ids
                    should_read_only = user_id in read_only_user_ids
                    should_rdo_view_only = user_id in rdo_view_only_user_ids and not should_read_only

                    if should_read_only:
                        user_obj.groups.add(read_only_group)
                        user_obj.groups.remove(rdo_view_only_group)
                        user_obj.groups.remove(delete_group)
                        user_obj.groups.remove(manager_group)
                        user_obj.groups.remove(alerts_ai_group)
                    else:
                        user_obj.groups.remove(read_only_group)
                        if should_rdo_view_only:
                            user_obj.groups.add(rdo_view_only_group)
                        else:
                            user_obj.groups.remove(rdo_view_only_group)

                        if should_delete:
                            user_obj.groups.add(delete_group)
                        else:
                            user_obj.groups.remove(delete_group)

                        if should_manage:
                            user_obj.groups.add(manager_group)
                        else:
                            user_obj.groups.remove(manager_group)

                        if user_id in alerts_ai_user_ids:
                            user_obj.groups.add(alerts_ai_group)
                        else:
                            user_obj.groups.remove(alerts_ai_group)

            if not error_message:
                success_message = 'Permissoes atualizadas com sucesso.'
            elif not success_message:
                success_message = 'Permissoes atualizadas com sucesso, com excecao das protecoes aplicadas automaticamente.'
            users = list(list_permission_managed_users())

    managed_rows = []
    for user_obj in users:
        try:
            full_name = user_obj.get_full_name() if hasattr(user_obj, 'get_full_name') else ''
        except Exception:
            full_name = ''
        try:
            is_supervisor = user_obj.groups.filter(name='Supervisor').exists()
        except Exception:
            is_supervisor = False
        try:
            can_delete = bool(
                user_obj.is_superuser or user_obj.groups.filter(name=RDO_DELETE_GROUP_NAME).exists()
            )
        except Exception:
            can_delete = bool(getattr(user_obj, 'is_superuser', False))
        try:
            can_manage = bool(
                user_obj.is_superuser
                or user_obj.groups.filter(name=RDO_PERMISSION_MANAGER_GROUP_NAME).exists()
            )
        except Exception:
            can_manage = bool(getattr(user_obj, 'is_superuser', False))
        try:
            can_use_alerts_ai = bool(
                user_obj.is_superuser
                or user_obj.groups.filter(name=ALERTS_AI_GROUP_NAME).exists()
            )
        except Exception:
            can_use_alerts_ai = bool(getattr(user_obj, 'is_superuser', False))
        try:
            is_read_only = bool(
                not getattr(user_obj, 'is_superuser', False)
                and user_obj.groups.filter(name=SYSTEM_READ_ONLY_GROUP_NAME).exists()
            )
        except Exception:
            is_read_only = False
        try:
            is_rdo_view_only = bool(
                not getattr(user_obj, 'is_superuser', False)
                and not is_read_only
                and user_obj.groups.filter(name=RDO_VIEW_ONLY_GROUP_NAME).exists()
            )
        except Exception:
            is_rdo_view_only = False

        managed_rows.append(
            {
                'id': user_obj.id,
                'username': user_obj.username,
                'full_name': full_name,
                'email': getattr(user_obj, 'email', '') or '',
                'is_superuser': bool(getattr(user_obj, 'is_superuser', False)),
                'is_supervisor': is_supervisor,
                'is_active': bool(getattr(user_obj, 'is_active', True)),
                'is_current_user': bool(
                    getattr(user_obj, 'id', None) == getattr(request.user, 'id', None)
                ),
                'can_delete_rdo': can_delete,
                'can_manage_rdo_permissions': can_manage,
                'can_use_alerts_ai': can_use_alerts_ai,
                'is_read_only': is_read_only,
                'is_rdo_view_only': is_rdo_view_only,
                'can_toggle_read_only': not bool(
                    getattr(user_obj, 'is_superuser', False)
                    or getattr(user_obj, 'id', None) == getattr(request.user, 'id', None)
                ),
                'can_toggle_rdo_view_only': not bool(
                    getattr(user_obj, 'is_superuser', False)
                ),
                'can_deactivate_user': not bool(
                    not getattr(user_obj, 'is_active', True)
                    or getattr(user_obj, 'is_superuser', False)
                    or getattr(user_obj, 'id', None) == getattr(request.user, 'id', None)
                ),
                'can_reactivate_user': not bool(
                    getattr(user_obj, 'is_active', True)
                    or getattr(user_obj, 'is_superuser', False)
                    or getattr(user_obj, 'id', None) == getattr(request.user, 'id', None)
                ),
            }
        )

    delete_enabled_count = sum(1 for row in managed_rows if row['can_delete_rdo'])
    manager_enabled_count = sum(1 for row in managed_rows if row['can_manage_rdo_permissions'])
    alerts_ai_enabled_count = sum(1 for row in managed_rows if row['can_use_alerts_ai'])
    read_only_enabled_count = sum(1 for row in managed_rows if row['is_read_only'])
    rdo_view_only_enabled_count = sum(1 for row in managed_rows if row['is_rdo_view_only'])
    active_users_count = sum(1 for row in managed_rows if row['is_active'])
    inactive_users_count = sum(1 for row in managed_rows if not row['is_active'])

    return render(
        request,
        'gerenciar_permissoes_rdo.html',
        {
            'users': managed_rows,
            'success': success_message,
            'error': error_message,
            'delete_group_name': RDO_DELETE_GROUP_NAME,
            'manager_group_name': RDO_PERMISSION_MANAGER_GROUP_NAME,
            'alerts_ai_group_name': ALERTS_AI_GROUP_NAME,
            'read_only_group_name': SYSTEM_READ_ONLY_GROUP_NAME,
            'rdo_view_only_group_name': RDO_VIEW_ONLY_GROUP_NAME,
            'visible_users_count': len(managed_rows),
            'delete_enabled_count': delete_enabled_count,
            'manager_enabled_count': manager_enabled_count,
            'alerts_ai_enabled_count': alerts_ai_enabled_count,
            'read_only_enabled_count': read_only_enabled_count,
            'rdo_view_only_enabled_count': rdo_view_only_enabled_count,
            'active_users_count': active_users_count,
            'inactive_users_count': inactive_users_count,
        },
    )


USER_PERMISSION_GROUPS = (
    (RDO_DELETE_GROUP_NAME, 'Excluir RDO', 'Permite excluir registros de RDO.'),
    (RDO_PERMISSION_MANAGER_GROUP_NAME, 'Gerenciar usuários e permissões', 'Permite administrar usuários e permissões.'),
    (ALERTS_AI_GROUP_NAME, 'Acessar alertas de IA', 'Permite acessar os alertas inteligentes.'),
    (SYSTEM_READ_ONLY_GROUP_NAME, 'Somente visualização', 'Restringe alterações no sistema.'),
    (RDO_VIEW_ONLY_GROUP_NAME, 'Visualizar RDO', 'Permite consultar RDO sem editar.'),
    (RESPONSAVEIS_COORDENADORES_MANAGER_GROUP_NAME, 'Gerenciar responsáveis e coordenadores', 'Permite administrar a fonte central de nomes.'),
)


def _admin_access_or_403(request, area):
    user = getattr(request, 'user', None)
    allowed = (
        user_can_manage_rdo_permission_users(user)
        if area == 'usuarios'
        else user_can_manage_responsaveis_coordenadores(user)
    )
    if not allowed:
        return JsonResponse({'success': False, 'error': 'Sem permissão para esta ação.'}, status=403)
    return None


def _json_body(request):
    try:
        return json.loads(request.body.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        return {}


def _user_profile(user):
    if user.is_superuser:
        return 'Superuser'
    if user.groups.filter(name='Supervisor').exists():
        return 'Supervisor'
    return 'Usuário padrão'


def _permission_groups():
    ensure_rdo_access_groups()
    return [Group.objects.get(name=name) for name, _, _ in USER_PERMISSION_GROUPS]


def _serialize_user_permissions(user):
    group_names = set(user.groups.values_list('name', flat=True))
    return {
        'id': user.id,
        'username': user.username,
        'name': user.get_full_name() or user.username,
        'email': user.email or '',
        'profile': _user_profile(user),
        'active': user.is_active,
        'superuser': user.is_superuser,
        'permission_count': 'Todas' if user.is_superuser else len(group_names.intersection({item[0] for item in USER_PERMISSION_GROUPS})),
        'protected': user.is_superuser,
    }


@login_required(login_url='/login/')
@require_GET
def gerenciar_permissoes_rdo(request):
    can_users = user_can_manage_rdo_permission_users(request.user)
    can_people = user_can_manage_responsaveis_coordenadores(request.user)
    if not can_users and not can_people:
        return HttpResponseForbidden('Sem permissão para acessar a administração do sistema.')

    requested_tab = request.GET.get('aba', '')
    active_tab = requested_tab if requested_tab in {'usuarios', 'responsaveis'} else ('usuarios' if can_users else 'responsaveis')
    if active_tab == 'usuarios' and not can_users:
        active_tab = 'responsaveis'
    if active_tab == 'responsaveis' and not can_people:
        active_tab = 'usuarios'
    return render(request, 'gerenciar_permissoes_rdo.html', {
        'admin_active_tab': active_tab,
        'can_manage_users_tab': can_users,
        'can_manage_people_tab': can_people,
    })


@login_required(login_url='/login/')
@require_GET
def administracao_listar_usuarios(request):
    denied = _admin_access_or_403(request, 'usuarios')
    if denied:
        return denied
    query = (request.GET.get('q') or '').strip()
    profile = request.GET.get('perfil') or 'todos'
    status = request.GET.get('status') or 'ativos'
    page = max(int(request.GET.get('page', 1) or 1), 1)
    page_size = min(max(int(request.GET.get('page_size', 12) or 12), 5), 50)
    User = get_user_model()
    users = User.objects.all().order_by('username', 'id')
    if query:
        users = users.filter(Q(username__icontains=query) | Q(email__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query))
    if status == 'ativos':
        users = users.filter(is_active=True)
    elif status == 'inativos':
        users = users.filter(is_active=False)
    if profile == 'superusers':
        users = users.filter(is_superuser=True)
    elif profile == 'supervisores':
        users = users.filter(groups__name='Supervisor')
    total = users.count()
    records = [_serialize_user_permissions(item) for item in users[(page - 1) * page_size:page * page_size]]
    all_users = User.objects.all()
    return JsonResponse({
        'success': True,
        'items': records,
        'total': total,
        'page': page,
        'page_size': page_size,
        'summary': {
            'total': all_users.count(),
            'active': all_users.filter(is_active=True).count(),
            'inactive': all_users.filter(is_active=False).count(),
            'superusers': all_users.filter(is_superuser=True).count(),
        },
    })


@login_required(login_url='/login/')
@require_GET
def administracao_usuario_permissoes(request, user_id):
    denied = _admin_access_or_403(request, 'usuarios')
    if denied:
        return denied
    user = get_object_or_404(get_user_model(), pk=user_id)
    selected = set(user.groups.values_list('name', flat=True))
    return JsonResponse({
        'success': True,
        'user': _serialize_user_permissions(user),
        'permissions': [
            {'key': name, 'label': label, 'description': description, 'enabled': user.is_superuser or name in selected, 'locked': user.is_superuser}
            for name, label, description in USER_PERMISSION_GROUPS
        ],
    })


@login_required(login_url='/login/')
@require_POST
def administracao_atualizar_permissoes(request, user_id):
    denied = _admin_access_or_403(request, 'usuarios')
    if denied:
        return denied
    user = get_object_or_404(get_user_model(), pk=user_id)
    if user.is_superuser:
        return JsonResponse({'success': False, 'error': 'Contas superusuárias são protegidas.'}, status=400)
    payload = _json_body(request)
    enabled = set(payload.get('permissions') or [])
    known_names = {item[0] for item in USER_PERMISSION_GROUPS}
    if not enabled.issubset(known_names):
        return JsonResponse({'success': False, 'error': 'Permissões inválidas.'}, status=400)
    groups = {group.name: group for group in _permission_groups()}
    with transaction.atomic():
        for name, group in groups.items():
            if name in enabled:
                user.groups.add(group)
            else:
                user.groups.remove(group)
    return JsonResponse({'success': True, 'message': 'Permissões atualizadas com sucesso.', 'user': _serialize_user_permissions(user)})


@login_required(login_url='/login/')
@require_POST
def administracao_alterar_status_usuario(request, user_id):
    denied = _admin_access_or_403(request, 'usuarios')
    if denied:
        return denied
    user = get_object_or_404(get_user_model(), pk=user_id)
    if user.is_superuser or user.pk == request.user.pk:
        return JsonResponse({'success': False, 'error': 'Esta conta é protegida.'}, status=400)
    active = bool(_json_body(request).get('active'))
    user.is_active = active
    user.save(update_fields=['is_active'])
    return JsonResponse({'success': True, 'user': _serialize_user_permissions(user)})


def _people_counts(person):
    from .models import Financeiro, OrdemServico
    final_proposals = Q(status_proposta__in=['Fechada/Contratada', 'Perdida/Recusada', 'Cancelada', 'Declínio'])
    proposal_qs = Financeiro.objects.filter(Q(responsavel_cadastro=person) | Q(coordenador_cadastro=person))
    os_qs = OrdemServico.objects.filter(coordenador_cadastro=person)
    return {
        'propostas_andamento': proposal_qs.exclude(final_proposals).count(),
        'propostas_encerradas': proposal_qs.filter(final_proposals).count(),
        'os_andamento': os_qs.exclude(status_operacao__in=['Finalizada', 'Concluída', 'Cancelada']).count(),
        'os_finalizadas': os_qs.filter(status_operacao__in=['Finalizada', 'Concluída', 'Cancelada']).count(),
    }


def _serialize_person(person):
    counts = _people_counts(person)
    roles = []
    if person.responsavel_comercial:
        roles.append('Responsável Comercial')
    if person.coordenador:
        roles.append('Coordenador')
    return {
        'id': person.id, 'nome': person.nome, 'ativo': person.ativo,
        'responsavel_comercial': person.responsavel_comercial, 'coordenador': person.coordenador,
        'funcoes': roles, 'vinculos': counts,
        # A tela administrativa trabalha com desativacao para preservar o historico.
        'can_delete': False,
    }


@login_required(login_url='/login/')
@require_GET
def administracao_listar_responsaveis(request):
    denied = _admin_access_or_403(request, 'responsaveis')
    if denied:
        return denied
    from .models import ResponsavelCoordenador
    query, role, status = (request.GET.get('q') or '').strip(), request.GET.get('funcao', 'todas'), request.GET.get('status', 'ativos')
    people = ResponsavelCoordenador.objects.all()
    if query:
        people = people.filter(nome__icontains=query)
    if role == 'responsavel': people = people.filter(responsavel_comercial=True, coordenador=False)
    elif role == 'coordenador': people = people.filter(coordenador=True, responsavel_comercial=False)
    elif role == 'ambos': people = people.filter(responsavel_comercial=True, coordenador=True)
    if status == 'ativos': people = people.filter(ativo=True)
    elif status == 'inativos': people = people.filter(ativo=False)
    return JsonResponse({'success': True, 'items': [_serialize_person(item) for item in people.order_by('nome')]})


@login_required(login_url='/login/')
@require_POST
def administracao_criar_responsavel(request):
    denied = _admin_access_or_403(request, 'responsaveis')
    if denied:
        return denied
    from .models import ResponsavelCoordenador, ResponsavelCoordenadorAuditoria
    payload = _json_body(request)
    try:
        person = ResponsavelCoordenador.objects.create(
            nome=payload.get('nome', ''), responsavel_comercial=bool(payload.get('responsavel_comercial')),
            coordenador=bool(payload.get('coordenador')), ativo=bool(payload.get('ativo', True)),
            criado_por=request.user, atualizado_por=request.user,
        )
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    ResponsavelCoordenadorAuditoria.objects.create(responsavel_coordenador=person, acao='criado', executado_por=request.user)
    return JsonResponse({'success': True, 'message': 'Nome adicionado com sucesso.', 'item': _serialize_person(person)})


@login_required(login_url='/login/')
@require_POST
def administracao_editar_responsavel(request, person_id):
    denied = _admin_access_or_403(request, 'responsaveis')
    if denied:
        return denied
    from .models import ResponsavelCoordenador, ResponsavelCoordenadorAuditoria
    person = get_object_or_404(ResponsavelCoordenador, pk=person_id)
    payload = _json_body(request)
    counts = _people_counts(person)
    wants_responsavel, wants_coordenador = bool(payload.get('responsavel_comercial')), bool(payload.get('coordenador'))
    if person.responsavel_comercial and not wants_responsavel and (counts['propostas_andamento'] or counts['propostas_encerradas']):
        return JsonResponse({'success': False, 'error': 'Substitua os vínculos de responsável antes de remover esta função.'}, status=400)
    if person.coordenador and not wants_coordenador and (counts['os_andamento'] or counts['os_finalizadas'] or counts['propostas_andamento'] or counts['propostas_encerradas']):
        return JsonResponse({'success': False, 'error': 'Substitua os vínculos de coordenador antes de remover esta função.'}, status=400)
    try:
        person.nome = payload.get('nome', person.nome)
        person.responsavel_comercial, person.coordenador = wants_responsavel, wants_coordenador
        person.ativo, person.atualizado_por = bool(payload.get('ativo', person.ativo)), request.user
        person.save()
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    ResponsavelCoordenadorAuditoria.objects.create(responsavel_coordenador=person, acao='editado', executado_por=request.user)
    return JsonResponse({'success': True, 'item': _serialize_person(person)})


@login_required(login_url='/login/')
@require_POST
def administracao_alterar_status_responsavel(request, person_id):
    denied = _admin_access_or_403(request, 'responsaveis')
    if denied:
        return denied
    from .models import ResponsavelCoordenador, ResponsavelCoordenadorAuditoria
    person = get_object_or_404(ResponsavelCoordenador, pk=person_id)
    person.ativo = bool(_json_body(request).get('ativo'))
    person.atualizado_por = request.user
    person.save()
    ResponsavelCoordenadorAuditoria.objects.create(responsavel_coordenador=person, acao='reativado' if person.ativo else 'desativado', executado_por=request.user)
    return JsonResponse({'success': True, 'item': _serialize_person(person)})


@login_required(login_url='/login/')
@require_POST
def administracao_excluir_responsavel(request, person_id):
    denied = _admin_access_or_403(request, 'responsaveis')
    if denied:
        return denied
    return JsonResponse(
        {
            'success': False,
            'error': 'A exclusao foi desativada. Use Desativar para preservar o historico.',
        },
        status=405,
    )
    from .models import ResponsavelCoordenador, ResponsavelCoordenadorAuditoria
    person = get_object_or_404(ResponsavelCoordenador, pk=person_id)
    if any(_people_counts(person).values()):
        return JsonResponse({'success': False, 'error': 'Nomes com vínculos não podem ser excluídos.'}, status=400)
    ResponsavelCoordenadorAuditoria.objects.create(acao='excluido', detalhes={'nome': person.nome}, executado_por=request.user)
    person.delete()
    return JsonResponse({'success': True})


@login_required(login_url='/login/')
@require_GET
def administracao_previa_substituicao(request, person_id):
    denied = _admin_access_or_403(request, 'responsaveis')
    if denied:
        return denied
    from .models import ResponsavelCoordenador
    person = get_object_or_404(ResponsavelCoordenador, pk=person_id)
    return JsonResponse({'success': True, 'item': _serialize_person(person)})


@login_required(login_url='/login/')
@require_POST
def administracao_confirmar_substituicao(request, person_id):
    denied = _admin_access_or_403(request, 'responsaveis')
    if denied:
        return denied
    from .models import Financeiro, OrdemServico, ResponsavelCoordenador, ResponsavelCoordenadorAuditoria
    current = get_object_or_404(ResponsavelCoordenador, pk=person_id)
    payload = _json_body(request)
    replacement = get_object_or_404(ResponsavelCoordenador, pk=payload.get('novo_id'))
    role = payload.get('funcao')
    if replacement.pk == current.pk or not replacement.ativo:
        return JsonResponse({'success': False, 'error': 'Selecione um nome ativo diferente do atual.'}, status=400)
    if role == 'responsavel' and not replacement.responsavel_comercial:
        return JsonResponse({'success': False, 'error': 'O novo nome não está disponível como responsável comercial.'}, status=400)
    if role == 'coordenador' and not replacement.coordenador:
        return JsonResponse({'success': False, 'error': 'O novo nome não está disponível como coordenador.'}, status=400)
    if role not in {'responsavel', 'coordenador'}:
        return JsonResponse({'success': False, 'error': 'Função de substituição inválida.'}, status=400)
    final_statuses = ['Fechada/Contratada', 'Perdida/Recusada', 'Cancelada', 'Declínio']
    with transaction.atomic():
        if role == 'responsavel':
            qs = Financeiro.objects.filter(responsavel_cadastro=current)
            if not payload.get('incluir_encerradas'):
                qs = qs.exclude(status_proposta__in=final_statuses)
            proposal_count = qs.update(responsavel_cadastro=replacement, responsavel=replacement.nome)
            os_count = 0
        else:
            proposal_qs = Financeiro.objects.filter(coordenador_cadastro=current)
            os_qs = OrdemServico.objects.filter(coordenador_cadastro=current)
            if not payload.get('incluir_propostas_encerradas'):
                proposal_qs = proposal_qs.exclude(status_proposta__in=final_statuses)
            if not payload.get('incluir_os_finalizadas'):
                os_qs = os_qs.exclude(status_operacao__in=['Finalizada', 'Concluída', 'Cancelada'])
            proposal_count = proposal_qs.update(coordenador_cadastro=replacement)
            os_count = os_qs.update(coordenador_cadastro=replacement, coordenador=replacement.nome)
        if payload.get('desativar_anterior'):
            current.ativo = False
            current.atualizado_por = request.user
            current.save()
        ResponsavelCoordenadorAuditoria.objects.create(
            responsavel_coordenador=current, acao='substituido', executado_por=request.user,
            detalhes={'novo_nome': replacement.nome, 'funcao': role, 'propostas': proposal_count, 'os': os_count},
        )
    return JsonResponse({'success': True, 'updated': {'propostas': proposal_count, 'os': os_count}})


@csrf_protect
def cadastrar_cliente(request):
    if user_has_read_only_access(getattr(request, 'user', None)):
        return build_read_only_forbidden_response('cadastrar clientes')

    if request.method == 'POST':
        from .models import Cliente

        nome = request.POST.get('nome')
        if nome:
            if not Cliente.objects.filter(nome=nome).exists():
                Cliente.objects.create(nome=nome)
                return render(request, 'cadastrar_cliente.html', {'success': True})
            return render(request, 'cadastrar_cliente.html', {'error': 'Cliente ja existe.'})
        return render(request, 'cadastrar_cliente.html', {'error': 'Preencha o nome do cliente.'})

    return render(request, 'cadastrar_cliente.html')


@csrf_protect
def cadastrar_unidade(request):
    if user_has_read_only_access(getattr(request, 'user', None)):
        return build_read_only_forbidden_response('cadastrar unidades')

    if request.method == 'POST':
        from .models import Unidade

        nome = request.POST.get('nome')
        if nome:
            if not Unidade.objects.filter(nome=nome).exists():
                Unidade.objects.create(nome=nome)
                return render(request, 'cadastrar_unidade.html', {'success': True})
            return render(request, 'cadastrar_unidade.html', {'error': 'Unidade ja existe.'})
        return render(request, 'cadastrar_unidade.html', {'error': 'Preencha o nome da unidade.'})

    return render(request, 'cadastrar_unidade.html')


@csrf_protect
def cadastrar_pessoa(request):
    if user_has_read_only_access(getattr(request, 'user', None)):
        return build_read_only_forbidden_response('cadastrar pessoas')

    from .models import OrdemServico, Pessoa

    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        if not nome:
            return render(request, 'cadastrar_pessoas.html', {'error': 'Preencha o nome da pessoa.'})
        if Pessoa.objects.filter(nome__iexact=nome).exists():
            return render(request, 'cadastrar_pessoas.html', {'error': 'Pessoa ja cadastrada.'})
        funcao_default = OrdemServico.FUNCOES[0][0] if getattr(OrdemServico, 'FUNCOES', None) else 'Ajudante'
        Pessoa.objects.create(nome=nome, funcao=funcao_default)
        return render(request, 'cadastrar_pessoas.html', {'success': True})

    return render(request, 'cadastrar_pessoas.html')


@csrf_protect
def cadastrar_funcao(request):
    if user_has_read_only_access(getattr(request, 'user', None)):
        return build_read_only_forbidden_response('cadastrar funcoes')

    from .models import Funcao

    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        if not nome:
            return render(request, 'cadastrar_funcao.html', {'error': 'Preencha o nome da funcao.'})
        if Funcao.objects.filter(nome__iexact=nome).exists():
            return render(request, 'cadastrar_funcao.html', {'error': 'Funcao ja cadastrada.'})
        Funcao.objects.create(nome=nome)
        return render(request, 'cadastrar_funcao.html', {'success': True})

    return render(request, 'cadastrar_funcao.html')
