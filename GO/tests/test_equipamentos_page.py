from django.contrib.auth.models import User
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

from GO.models import FabricanteEquipamento, TipoEquipamento


@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class EquipamentosPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='equip_page_user',
            password='senha123',
        )
        self.client.force_login(self.user)

    def test_page_loads_equipment_type_catalog_into_select(self):
        TipoEquipamento.objects.get_or_create(nome='Exaustor')
        TipoEquipamento.objects.get_or_create(nome='Bomba Pneumática')

        response = self.client.get(reverse('equipamentos'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('Bomba Pneumática', response.context['tipos_equipamento'])
        self.assertIn('Exaustor', response.context['tipos_equipamento'])
        self.assertContains(response, 'id="tipo-equipamento-select"', html=False)
        self.assertContains(response, '<option value="Exaustor">Exaustor</option>', html=False)

    def test_page_loads_manufacturer_catalog_into_select(self):
        FabricanteEquipamento.objects.get_or_create(nome='MSA')
        FabricanteEquipamento.objects.get_or_create(nome='Fabricante QA')

        response = self.client.get(reverse('equipamentos'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('Fabricante QA', response.context['fabricantes'])
        self.assertIn('MSA', response.context['fabricantes'])
        self.assertContains(response, 'id="fabricante-equipamento-select"', html=False)
        self.assertContains(response, '<option value="Fabricante QA">Fabricante QA</option>', html=False)

    def test_create_type_endpoint_persists_and_blocks_duplicate(self):
        response = self.client.post(
            reverse('api_tipos_equipamento_save'),
            data={'nome': 'Tipo QA Novo'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertTrue(payload.get('created'))
        self.assertEqual(payload['tipo']['nome'], 'Tipo QA Novo')
        self.assertTrue(TipoEquipamento.objects.filter(nome='Tipo QA Novo').exists())

        second_response = self.client.post(
            reverse('api_tipos_equipamento_save'),
            data={'nome': 'tipo qa novo'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(second_response.status_code, 400)
        second_payload = second_response.json()
        self.assertFalse(second_payload.get('success'))
        self.assertEqual(second_payload.get('error'), 'Tipo de equipamento já cadastrado.')
        self.assertEqual(TipoEquipamento.objects.filter(nome__iexact='tipo qa novo').count(), 1)

        page_response = self.client.get(reverse('equipamentos'))

        self.assertEqual(page_response.status_code, 200)
        self.assertContains(page_response, '<option value="Tipo QA Novo">Tipo QA Novo</option>', html=False)

    def test_create_manufacturer_endpoint_persists_and_blocks_duplicate(self):
        response = self.client.post(
            reverse('api_fabricantes_equipamento_save'),
            data={'nome': 'Fabricante QA Novo'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertTrue(payload.get('created'))
        self.assertEqual(payload['fabricante']['nome'], 'Fabricante QA Novo')
        self.assertTrue(FabricanteEquipamento.objects.filter(nome='Fabricante QA Novo').exists())

        second_response = self.client.post(
            reverse('api_fabricantes_equipamento_save'),
            data={'nome': 'fabricante qa novo'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(second_response.status_code, 400)
        second_payload = second_response.json()
        self.assertFalse(second_payload.get('success'))
        self.assertEqual(second_payload.get('error'), 'Fabricante já cadastrado.')
        self.assertEqual(FabricanteEquipamento.objects.filter(nome__iexact='fabricante qa novo').count(), 1)

        page_response = self.client.get(reverse('equipamentos'))

        self.assertEqual(page_response.status_code, 200)
        self.assertContains(page_response, '<option value="Fabricante QA Novo">Fabricante QA Novo</option>', html=False)
