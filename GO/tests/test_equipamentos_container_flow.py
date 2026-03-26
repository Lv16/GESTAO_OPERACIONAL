from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from GO.models import Equipamentos, Modelo


class EquipamentosContainerFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='equip_container_user',
            password='senha123',
        )
        self.client.force_login(self.user)

    def _post_save(self, **data):
        return self.client.post(
            reverse('api_equipamentos_save'),
            data=data,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )

    def test_save_container_discards_manufacturer_even_when_model_has_one(self):
        Modelo.objects.create(
            nome='Modelo Container Teste',
            fabricante='FABRICANTE DO MODELO',
        )

        response = self._post_save(
            modelo='Modelo Container Teste',
            descricao='Container',
            fabricante='AMBIPAR',
            tag='CONT-001',
            serie='ESL-001',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))

        equipamento = Equipamentos.objects.get(pk=payload['equipamento']['id'])
        self.assertEqual(equipamento.descricao, 'Container')
        self.assertIsNone(equipamento.fabricante)
        self.assertEqual(payload['equipamento']['fabricante'], '')

    def test_save_existing_equipment_as_container_clears_manufacturer(self):
        equipamento = Equipamentos.objects.create(
            descricao='Bomba Pneumática',
            fabricante='AMBIPAR',
            numero_tag='TAG-ATUAL',
            numero_serie='SER-ATUAL',
        )

        response = self._post_save(
            equipamento_id=str(equipamento.pk),
            descricao='Container',
        )

        self.assertEqual(response.status_code, 200)
        equipamento.refresh_from_db()
        self.assertEqual(equipamento.descricao, 'Container')
        self.assertIsNone(equipamento.fabricante)

    def test_save_container_without_identifiers_returns_container_message(self):
        response = self._post_save(
            descricao='Container',
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload.get('success'))
        self.assertEqual(
            payload.get('error'),
            'Informe Número do Container ou Número da Eslinga.',
        )

    def test_swap_identifiers_for_container_uses_container_terms(self):
        equipamento = Equipamentos.objects.create(
            descricao='Container',
            numero_tag='CONT-ATUAL',
            numero_serie='ESL-ATUAL',
        )

        response = self.client.post(
            reverse('swap_identificadores_ajax'),
            data={'equipamento_id': str(equipamento.pk)},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload.get('success'))
        self.assertEqual(
            payload.get('error'),
            'Informe Número do Container ou Número da Eslinga.',
        )
