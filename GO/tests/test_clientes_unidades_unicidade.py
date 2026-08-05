import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from GO.models import Cliente, Unidade


class ClientesUnidadesUnicidadeTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username='comercial_uniqueness',
            password='secret',
            is_staff=True,
        )

    def test_cliente_blocks_case_and_whitespace_duplicates(self):
        Cliente.objects.create(nome='Modec')
        with self.assertRaises(ValidationError):
            Cliente.objects.create(nome='  MODEC  ')

    def test_unidade_blocks_case_and_whitespace_duplicates(self):
        Unidade.objects.create(nome='Unidade P-74')
        with self.assertRaises(ValidationError):
            Unidade.objects.create(nome='  UNIDADE p-74  ')

    def test_cadastro_cliente_page_blocks_case_insensitive_duplicate(self):
        Cliente.objects.create(nome='Modec')
        response = self.client.post(reverse('cadastrar_cliente'), {'nome': 'MODEC'})
        self.assertContains(response, 'Ja existe um cliente com este nome.')
        self.assertEqual(Cliente.objects.filter(nome__iexact='modec').count(), 1)

    def test_comercial_quick_client_returns_conflict_for_existing_name(self):
        Cliente.objects.create(nome='Modec')
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse('comercial_criar_cliente'),
            data=json.dumps({'nome': 'MODEC'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['errors']['nome'], 'Ja existe um cliente cadastrado com este nome.')

    def test_comercial_quick_unit_returns_conflict_for_existing_name(self):
        Unidade.objects.create(nome='P-74')
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse('comercial_criar_unidade'),
            data=json.dumps({'nome': 'p-74'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['errors']['nome'], 'Ja existe uma unidade cadastrada com este nome.')
