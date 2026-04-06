from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse

from GO.models import MobileApiToken
from GO.rdo_access import (
    RDO_DELETE_GROUP_NAME,
    RDO_PERMISSION_MANAGER_GROUP_NAME,
    RDO_VIEW_ONLY_GROUP_NAME,
    SYSTEM_READ_ONLY_GROUP_NAME,
    ensure_rdo_access_groups,
    user_can_delete_rdo,
    user_can_manage_rdo_permission_users,
    user_can_open_or_edit_rdo,
    user_has_rdo_view_only_access,
    user_has_read_only_access,
)


@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }
)
class ManageRdoPermissionsViewTest(TestCase):
    def setUp(self):
        groups_info = ensure_rdo_access_groups()
        self.delete_group = groups_info['delete_group']
        self.manager_group = groups_info['manager_group']
        self.supervisor_group, _ = Group.objects.get_or_create(name='Supervisor')
        self.url = reverse('gerenciar_permissoes_rdo')

        self.superuser = User.objects.create_user(
            username='perm_superuser',
            password='x',
            is_staff=True,
            is_superuser=True,
        )
        self.manager_user = User.objects.create_user(username='perm_manager', password='x')
        self.manager_user.groups.add(self.manager_group)
        self.target_user = User.objects.create_user(
            username='perm_target',
            password='x',
            first_name='Alvo',
            last_name='RDO',
            email='alvo@example.com',
        )
        self.supervisor_user = User.objects.create_user(
            username='perm_supervisor_hidden',
            password='x',
            email='supervisor@example.com',
        )
        self.supervisor_user.groups.add(self.supervisor_group)
        self.regular_user = User.objects.create_user(username='perm_regular', password='x')

    def _get(self, url):
        return self.client.get(url, HTTP_HOST='localhost', secure=True)

    def _post(self, url, data=None):
        return self.client.post(url, data or {}, HTTP_HOST='localhost', secure=True)

    def test_regular_user_cannot_access_management_screen(self):
        self.client.force_login(self.regular_user)

        response = self._get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_manager_user_can_access_management_screen(self):
        self.client.force_login(self.manager_user)

        response = self._get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.target_user.username)
        self.assertNotContains(response, self.supervisor_user.username)
        self.assertContains(response, RDO_DELETE_GROUP_NAME)
        self.assertContains(response, RDO_PERMISSION_MANAGER_GROUP_NAME)
        self.assertContains(response, RDO_VIEW_ONLY_GROUP_NAME)

    def test_post_grants_delete_and_manager_groups(self):
        self.client.force_login(self.manager_user)

        response = self._post(
            self.url,
            {
                'delete_rdo_users': [str(self.target_user.id)],
                'manage_rdo_permission_users': [str(self.target_user.id)],
            },
        )

        self.assertEqual(response.status_code, 200)

        self.target_user.refresh_from_db()
        self.manager_user.refresh_from_db()

        self.assertTrue(self.target_user.groups.filter(name=RDO_DELETE_GROUP_NAME).exists())
        self.assertTrue(self.target_user.groups.filter(name=RDO_PERMISSION_MANAGER_GROUP_NAME).exists())
        self.assertTrue(user_can_delete_rdo(User.objects.get(pk=self.target_user.pk)))
        self.assertTrue(user_can_manage_rdo_permission_users(User.objects.get(pk=self.target_user.pk)))

        self.assertTrue(
            self.manager_user.groups.filter(name=RDO_PERMISSION_MANAGER_GROUP_NAME).exists(),
            'O gerente atual deve manter o proprio acesso a tela.',
        )

    def test_superuser_can_revoke_groups_from_target_user(self):
        self.target_user.groups.add(self.delete_group, self.manager_group)
        self.client.force_login(self.superuser)

        response = self._post(self.url, {})

        self.assertEqual(response.status_code, 200)

        self.target_user.refresh_from_db()

        self.assertFalse(self.target_user.groups.filter(name=RDO_DELETE_GROUP_NAME).exists())
        self.assertFalse(self.target_user.groups.filter(name=RDO_PERMISSION_MANAGER_GROUP_NAME).exists())
        self.assertFalse(user_can_delete_rdo(User.objects.get(pk=self.target_user.pk)))
        self.assertFalse(user_can_manage_rdo_permission_users(User.objects.get(pk=self.target_user.pk)))
        self.assertFalse(user_has_read_only_access(User.objects.get(pk=self.target_user.pk)))

    def test_post_grants_read_only_and_revokes_write_groups(self):
        self.target_user.groups.add(self.delete_group, self.manager_group)
        self.client.force_login(self.manager_user)

        response = self._post(
            self.url,
            {
                'delete_rdo_users': [str(self.target_user.id)],
                'manage_rdo_permission_users': [str(self.target_user.id)],
                'read_only_users': [str(self.target_user.id)],
            },
        )

        self.assertEqual(response.status_code, 200)

        self.target_user.refresh_from_db()

        self.assertTrue(self.target_user.groups.filter(name=SYSTEM_READ_ONLY_GROUP_NAME).exists())
        self.assertFalse(self.target_user.groups.filter(name=RDO_DELETE_GROUP_NAME).exists())
        self.assertFalse(self.target_user.groups.filter(name=RDO_PERMISSION_MANAGER_GROUP_NAME).exists())
        self.assertTrue(user_has_read_only_access(User.objects.get(pk=self.target_user.pk)))
        self.assertFalse(user_can_delete_rdo(User.objects.get(pk=self.target_user.pk)))
        self.assertFalse(user_can_manage_rdo_permission_users(User.objects.get(pk=self.target_user.pk)))

    def test_post_grants_rdo_view_only_without_blocking_system_edit(self):
        self.client.force_login(self.manager_user)

        response = self._post(
            self.url,
            {
                'rdo_view_only_users': [str(self.target_user.id)],
            },
        )

        self.assertEqual(response.status_code, 200)

        self.target_user.refresh_from_db()

        self.assertTrue(self.target_user.groups.filter(name=RDO_VIEW_ONLY_GROUP_NAME).exists())
        self.assertFalse(self.target_user.groups.filter(name=SYSTEM_READ_ONLY_GROUP_NAME).exists())
        self.assertTrue(user_has_rdo_view_only_access(User.objects.get(pk=self.target_user.pk)))
        self.assertFalse(user_can_open_or_edit_rdo(User.objects.get(pk=self.target_user.pk)))
        self.assertFalse(user_has_read_only_access(User.objects.get(pk=self.target_user.pk)))

    def test_manager_can_deactivate_user_and_revoke_mobile_access(self):
        token = MobileApiToken.objects.create(
            key='a' * 64,
            user=self.target_user,
            device_name='Android',
            is_active=True,
        )
        self.client.force_login(self.manager_user)

        response = self._post(
            self.url,
            {
                'status_user_id': str(self.target_user.id),
                'status_action': 'deactivate',
            },
        )

        self.assertEqual(response.status_code, 200)

        self.target_user.refresh_from_db()
        token.refresh_from_db()

        self.assertFalse(self.target_user.is_active)
        self.assertFalse(token.is_active)
        self.assertContains(response, 'desativado com sucesso')
        self.assertContains(response, 'Reativar')

    def test_manager_cannot_deactivate_self(self):
        self.client.force_login(self.manager_user)

        response = self._post(
            self.url,
            {
                'status_user_id': str(self.manager_user.id),
                'status_action': 'deactivate',
            },
        )

        self.assertEqual(response.status_code, 200)

        self.manager_user.refresh_from_db()

        self.assertTrue(self.manager_user.is_active)
        self.assertContains(response, 'Voce nao pode alterar o proprio usuario por esta tela.')

    def test_manager_can_reactivate_inactive_user(self):
        self.target_user.is_active = False
        self.target_user.save(update_fields=['is_active'])
        self.client.force_login(self.manager_user)

        response = self._post(
            self.url,
            {
                'status_user_id': str(self.target_user.id),
                'status_action': 'activate',
            },
        )

        self.assertEqual(response.status_code, 200)

        self.target_user.refresh_from_db()

        self.assertTrue(self.target_user.is_active)
        self.assertContains(response, 'reativado com sucesso')
