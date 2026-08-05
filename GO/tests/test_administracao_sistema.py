import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from GO.models import ResponsavelCoordenador
from GO.rdo_access import (
    RESPONSAVEIS_COORDENADORES_MANAGER_GROUP_NAME,
    RDO_PERMISSION_MANAGER_GROUP_NAME,
    ensure_rdo_access_groups,
)


class AdministracaoSistemaTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user('admin_permissions', password='secret')
        self.people_manager = User.objects.create_user('people_manager', password='secret')
        self.regular = User.objects.create_user('regular_user', password='secret')
        groups = ensure_rdo_access_groups()
        self.admin.groups.add(groups['manager_group'])
        self.people_manager.groups.add(groups['responsaveis_coordenadores_group'])

    def test_user_manager_only_sees_users_tab(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('gerenciar_permissoes_rdo'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'synchro-header-search--permissions')
        self.assertContains(response, 'synchro-page-search-mirror is-placeholder')
        self.assertContains(response, 'Usuários e Permissões')
        self.assertNotContains(response, 'Responsáveis e Coordenadores')

    def test_people_manager_cannot_call_user_endpoint(self):
        self.client.force_login(self.people_manager)
        response = self.client.get(reverse('administracao_listar_usuarios'))
        self.assertEqual(response.status_code, 403)

    def test_regular_user_cannot_access_administration(self):
        self.client.force_login(self.regular)
        response = self.client.get(reverse('gerenciar_permissoes_rdo'))
        self.assertEqual(response.status_code, 403)

    def test_people_manager_creates_person_with_both_roles(self):
        self.client.force_login(self.people_manager)
        response = self.client.post(
            reverse('administracao_criar_responsavel'),
            data=json.dumps({'nome': '  Pessoa de Teste  ', 'responsavel_comercial': True, 'coordenador': True, 'ativo': True}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        person = ResponsavelCoordenador.objects.get(nome='Pessoa de Teste')
        self.assertTrue(person.responsavel_comercial)
        self.assertTrue(person.coordenador)

    def test_person_requires_at_least_one_role(self):
        self.client.force_login(self.people_manager)
        response = self.client.post(
            reverse('administracao_criar_responsavel'),
            data=json.dumps({'nome': 'Sem Função', 'responsavel_comercial': False, 'coordenador': False}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_existing_name_receives_new_role_ignoring_case(self):
        ResponsavelCoordenador.objects.create(nome='Nome Duplicado de Teste', responsavel_comercial=True)
        self.client.force_login(self.people_manager)
        response = self.client.post(
            reverse('administracao_criar_responsavel'),
            data=json.dumps({'nome': 'nome duplicado de teste', 'responsavel_comercial': False, 'coordenador': True}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        person = ResponsavelCoordenador.objects.get(nome='Nome Duplicado de Teste')
        self.assertTrue(person.responsavel_comercial)
        self.assertTrue(person.coordenador)

    def test_existing_name_cannot_repeat_the_same_role(self):
        ResponsavelCoordenador.objects.create(nome='Coordenador de Teste', coordenador=True)
        self.client.force_login(self.people_manager)
        response = self.client.post(
            reverse('administracao_criar_responsavel'),
            data=json.dumps({'nome': 'coordenador de teste', 'responsavel_comercial': False, 'coordenador': True}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ResponsavelCoordenador.objects.filter(nome__iexact='coordenador de teste').count(), 1)

    def test_permission_update_persists_new_administration_permission(self):
        target = get_user_model().objects.create_user('target_user', password='secret')
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('administracao_atualizar_permissoes', args=[target.id]),
            data=json.dumps({'permissions': [RESPONSAVEIS_COORDENADORES_MANAGER_GROUP_NAME]}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(target.groups.filter(name=RESPONSAVEIS_COORDENADORES_MANAGER_GROUP_NAME).exists())

    def test_new_permission_group_is_real_group(self):
        self.assertTrue(ensure_rdo_access_groups()['responsaveis_coordenadores_group'].name)
