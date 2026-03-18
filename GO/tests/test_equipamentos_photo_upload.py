import base64
import shutil
import tempfile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from GO.models import EquipamentoFoto, Equipamentos


PNG_1X1 = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQ0AAAAASUVORK5CYII='
)


class EquipamentosPhotoUploadTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='equip_photo_user',
            password='senha123',
        )
        self.client.force_login(self.user)
        self.media_root = tempfile.mkdtemp(prefix='equip-photo-tests-')
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def _photo(self, name='photo.png'):
        return SimpleUploadedFile(name, PNG_1X1, content_type='image/png')

    def _post_save(self, **data):
        return self.client.post(
            reverse('api_equipamentos_save'),
            data=data,
            secure=True,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

    def test_create_with_photo_persists_photo_without_duplicate_path(self):
        response = self._post_save(
            cliente='Cliente Teste',
            embarcacao='Unidade Teste',
            numero_os='7001',
            descricao='Detector de Gas',
            modelo='MX-1',
            tag='TAG-PHOTO-001',
            serie='SER-PHOTO-001',
            fabricante='Ambipar',
            responsavel='Tester',
            local='Base',
            data_inspecao='2026-03-18',
            previsao_retorno='2026-03-19',
            photos=self._photo('nova-foto.png'),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))

        equipamento = Equipamentos.objects.get(pk=payload['equipamento']['id'])
        foto = EquipamentoFoto.objects.get(equipamento=equipamento)

        self.assertFalse(foto.foto.name.startswith('fotos_equipamento/fotos_equipamento/'))
        self.assertTrue(foto.foto.name.startswith('fotos_equipamento/'))
        self.assertTrue(payload['formulario']['photo_urls'])
        self.assertTrue(foto.foto.storage.exists(foto.foto.name))

    def test_edit_existing_equipment_persists_new_photo(self):
        equipamento = Equipamentos.objects.create(
            descricao='Detector de Gas',
            numero_tag='TAG-PHOTO-EDIT',
            numero_serie='SER-PHOTO-EDIT',
            numero_os='7002',
        )

        response = self._post_save(
            equipamento_id=str(equipamento.pk),
            descricao='Detector de Gas',
            photos=self._photo('edicao.png'),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))

        fotos = EquipamentoFoto.objects.filter(equipamento=equipamento)
        self.assertEqual(fotos.count(), 1)
        self.assertTrue(payload['formulario']['photo_urls'])

    def test_photo_save_failure_rolls_back_equipment_creation(self):
        with patch('GO.views_equipamentos._save_equipamento_photo', side_effect=RuntimeError('falha simulada no upload')):
            response = self._post_save(
                cliente='Cliente Falha',
                embarcacao='Unidade Falha',
                numero_os='7003',
                descricao='Detector de Gas',
                modelo='MX-FAIL',
                tag='TAG-PHOTO-FAIL',
                serie='SER-PHOTO-FAIL',
                fabricante='Ambipar',
                photos=self._photo('falha.png'),
            )

        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertFalse(payload.get('success'))
        self.assertEqual(Equipamentos.objects.filter(numero_tag='TAG-PHOTO-FAIL').count(), 0)
        self.assertEqual(EquipamentoFoto.objects.count(), 0)
