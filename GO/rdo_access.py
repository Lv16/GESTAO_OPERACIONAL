from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.http import HttpResponseForbidden, JsonResponse


SUPERVISOR_GROUP_NAME = 'Supervisor'
RDO_DELETE_GROUP_NAME = 'RDO - Excluir'
RDO_PERMISSION_MANAGER_GROUP_NAME = 'RDO - Gerenciar Permissões'
SYSTEM_READ_ONLY_GROUP_NAME = 'Sistema - Somente Visualizacao'
RDO_VIEW_ONLY_GROUP_NAME = 'RDO - Somente Visualizacao'
RDO_DELETE_PERMISSION_CODE = 'GO.delete_rdo'
READ_ONLY_ACCESS_MESSAGE = 'Seu usuario possui acesso somente para visualizacao.'
RDO_VIEW_ONLY_ACCESS_MESSAGE = 'Seu usuario possui acesso somente para visualizacao do RDO.'


def ensure_rdo_access_groups():
    delete_group, _ = Group.objects.get_or_create(name=RDO_DELETE_GROUP_NAME)
    manager_group, _ = Group.objects.get_or_create(name=RDO_PERMISSION_MANAGER_GROUP_NAME)
    read_only_group, _ = Group.objects.get_or_create(name=SYSTEM_READ_ONLY_GROUP_NAME)
    rdo_view_only_group, _ = Group.objects.get_or_create(name=RDO_VIEW_ONLY_GROUP_NAME)

    permission = None
    try:
        permission = Permission.objects.get(
            content_type__app_label='GO',
            codename='delete_rdo',
        )
    except Permission.DoesNotExist:
        permission = None

    try:
        if permission is not None and not delete_group.permissions.filter(pk=permission.pk).exists():
            delete_group.permissions.add(permission)
    except Exception:
        pass

    return {
        'delete_group': delete_group,
        'manager_group': manager_group,
        'read_only_group': read_only_group,
        'rdo_view_only_group': rdo_view_only_group,
        'delete_permission': permission,
    }


def user_has_read_only_access(user):
    try:
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        if getattr(user, 'is_superuser', False):
            return False
        ensure_rdo_access_groups()
        return bool(user.groups.filter(name=SYSTEM_READ_ONLY_GROUP_NAME).exists())
    except Exception:
        return False


def user_can_edit_system(user):
    try:
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        if getattr(user, 'is_superuser', False):
            return True
        return not user_has_read_only_access(user)
    except Exception:
        return False


def user_has_rdo_view_only_access(user):
    try:
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        if getattr(user, 'is_superuser', False):
            return False
        if user_has_read_only_access(user):
            return False
        ensure_rdo_access_groups()
        return bool(user.groups.filter(name=RDO_VIEW_ONLY_GROUP_NAME).exists())
    except Exception:
        return False


def user_can_open_or_edit_rdo(user):
    try:
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        if getattr(user, 'is_superuser', False):
            return True
        if user_has_read_only_access(user):
            return False
        if user_has_rdo_view_only_access(user):
            return False
        return True
    except Exception:
        return False


def user_can_delete_rdo(user):
    try:
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        if getattr(user, 'is_superuser', False):
            return True
        if user_has_read_only_access(user):
            return False
        ensure_rdo_access_groups()
        return bool(user.has_perm(RDO_DELETE_PERMISSION_CODE))
    except Exception:
        return False


def user_can_manage_rdo_permission_users(user):
    try:
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        if getattr(user, 'is_superuser', False):
            return True
        if user_has_read_only_access(user):
            return False
        ensure_rdo_access_groups()
        return bool(user.groups.filter(name=RDO_PERMISSION_MANAGER_GROUP_NAME).exists())
    except Exception:
        return False


def build_read_only_forbidden_response(action=None):
    message = READ_ONLY_ACCESS_MESSAGE
    if action:
        message = f'Sem permissao para {action}. {message}'
    return HttpResponseForbidden(message)


def build_read_only_json_response(action=None):
    message = READ_ONLY_ACCESS_MESSAGE
    if action:
        message = f'Sem permissao para {action}. {message}'
    return JsonResponse({'success': False, 'error': message}, status=403)


def build_rdo_open_edit_forbidden_response(user, action=None):
    if user_has_read_only_access(user):
        return build_read_only_forbidden_response(action)
    message = RDO_VIEW_ONLY_ACCESS_MESSAGE
    if action:
        message = f'Sem permissao para {action}. {message}'
    return HttpResponseForbidden(message)


def build_rdo_open_edit_json_response(user, action=None):
    if user_has_read_only_access(user):
        return build_read_only_json_response(action)
    message = RDO_VIEW_ONLY_ACCESS_MESSAGE
    if action:
        message = f'Sem permissao para {action}. {message}'
    return JsonResponse({'success': False, 'error': message}, status=403)


def list_permission_managed_users():
    UserModel = get_user_model()
    ensure_rdo_access_groups()
    return (
        UserModel.objects
        .exclude(groups__name=SUPERVISOR_GROUP_NAME)
        .distinct()
        .order_by('username', 'id')
    )
