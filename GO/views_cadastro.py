from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.views.decorators.csrf import csrf_protect

from .rdo_access import (
    RDO_DELETE_GROUP_NAME,
    RDO_PERMISSION_MANAGER_GROUP_NAME,
    SYSTEM_READ_ONLY_GROUP_NAME,
    build_read_only_forbidden_response,
    ensure_rdo_access_groups,
    list_permission_managed_users,
    user_has_read_only_access,
    user_can_manage_rdo_permission_users,
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
def gerenciar_permissoes_rdo(request):
    if not user_can_manage_rdo_permission_users(getattr(request, 'user', None)):
        return HttpResponseForbidden('Sem permissao para gerenciar acessos de exclusao de RDO.')

    groups_info = ensure_rdo_access_groups()
    delete_group = groups_info['delete_group']
    manager_group = groups_info['manager_group']
    read_only_group = groups_info['read_only_group']
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
            read_only_user_ids = {
                str(value).strip()
                for value in (request.POST.getlist('read_only_users') or [])
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

                    if should_read_only:
                        user_obj.groups.add(read_only_group)
                        user_obj.groups.remove(delete_group)
                        user_obj.groups.remove(manager_group)
                    else:
                        user_obj.groups.remove(read_only_group)

                        if should_delete:
                            user_obj.groups.add(delete_group)
                        else:
                            user_obj.groups.remove(delete_group)

                        if should_manage:
                            user_obj.groups.add(manager_group)
                        else:
                            user_obj.groups.remove(manager_group)

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
            is_read_only = bool(
                not getattr(user_obj, 'is_superuser', False)
                and user_obj.groups.filter(name=SYSTEM_READ_ONLY_GROUP_NAME).exists()
            )
        except Exception:
            is_read_only = False

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
                'is_read_only': is_read_only,
                'can_toggle_read_only': not bool(
                    getattr(user_obj, 'is_superuser', False)
                    or getattr(user_obj, 'id', None) == getattr(request.user, 'id', None)
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
    read_only_enabled_count = sum(1 for row in managed_rows if row['is_read_only'])
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
            'read_only_group_name': SYSTEM_READ_ONLY_GROUP_NAME,
            'visible_users_count': len(managed_rows),
            'delete_enabled_count': delete_enabled_count,
            'manager_enabled_count': manager_enabled_count,
            'read_only_enabled_count': read_only_enabled_count,
            'active_users_count': active_users_count,
            'inactive_users_count': inactive_users_count,
        },
    )


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
