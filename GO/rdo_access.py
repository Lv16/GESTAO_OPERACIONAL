from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission


SUPERVISOR_GROUP_NAME = 'Supervisor'
RDO_DELETE_GROUP_NAME = 'RDO - Excluir'
RDO_PERMISSION_MANAGER_GROUP_NAME = 'RDO - Gerenciar Permissões'
RDO_DELETE_PERMISSION_CODE = 'GO.delete_rdo'


def ensure_rdo_access_groups():
    delete_group, _ = Group.objects.get_or_create(name=RDO_DELETE_GROUP_NAME)
    manager_group, _ = Group.objects.get_or_create(name=RDO_PERMISSION_MANAGER_GROUP_NAME)

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
        'delete_permission': permission,
    }


def user_can_delete_rdo(user):
    try:
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        if getattr(user, 'is_superuser', False):
            return True
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
        ensure_rdo_access_groups()
        return bool(user.groups.filter(name=RDO_PERMISSION_MANAGER_GROUP_NAME).exists())
    except Exception:
        return False


def list_permission_managed_users():
    UserModel = get_user_model()
    ensure_rdo_access_groups()
    return (
        UserModel.objects
        .exclude(groups__name=SUPERVISOR_GROUP_NAME)
        .distinct()
        .order_by('username', 'id')
    )
