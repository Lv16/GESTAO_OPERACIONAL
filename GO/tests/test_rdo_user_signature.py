import io
import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas

from GO.models import AssinaturaUsuario, Cliente, OrdemServico, RDO, Unidade
from GO.rdo_access import ensure_rdo_access_groups


def _jpeg_signature():
    image = Image.new('RGB', (400, 160), 'white')
    draw = ImageDraw.Draw(image)
    draw.line((80, 100, 170, 55, 260, 105, 330, 60), fill='black', width=7)
    output = io.BytesIO()
    image.save(output, format='JPEG')
    return output.getvalue()


def _png_signature():
    image = Image.new('RGB', (400, 160), 'white')
    draw = ImageDraw.Draw(image)
    draw.line((60, 90, 160, 50, 260, 100, 340, 55), fill='navy', width=7)
    output = io.BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()


def _pdf_signature():
    output = io.BytesIO()
    document = canvas.Canvas(output, pagesize=(400, 160))
    document.setLineWidth(5)
    document.line(70, 60, 150, 105)
    document.line(150, 105, 250, 55)
    document.line(250, 55, 330, 100)
    document.showPage()
    document.save()
    return output.getvalue()


@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }
)
class RdoUserSignatureTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.TemporaryDirectory()
        self.override_media = override_settings(MEDIA_ROOT=self.media_root.name)
        self.override_media.enable()
        User = get_user_model()
        self.admin = User.objects.create_user('signature_admin', password='secret')
        self.approver = User.objects.create_user('signature_approver', password='secret')
        self.regular = User.objects.create_user('signature_regular', password='secret')
        self.admin.groups.add(ensure_rdo_access_groups()['manager_group'])

        cliente = Cliente.objects.create(nome='Cliente Assinatura')
        unidade = Unidade.objects.create(nome='Unidade Assinatura')
        ordem = OrdemServico.objects.create(
            numero_os=9191,
            data_inicio=date(2026, 8, 1),
            dias_de_operacao=1,
            servico='LIMPEZA DE DUTO',
            metodo='Manual',
            Cliente=cliente,
            Unidade=unidade,
            pob=1,
        )
        self.rdo = RDO.objects.create(
            ordem_servico=ordem,
            rdo='9191',
            data=date(2026, 8, 1),
            data_inicio=date(2026, 8, 1),
            aprovado=True,
            aprovado_por=self.approver,
        )

    def tearDown(self):
        self.override_media.disable()
        self.media_root.cleanup()

    def _upload(self, user=None):
        target = user or self.approver
        return self.client.post(
            reverse('administracao_atualizar_assinatura', args=[target.id]),
            {'assinatura': SimpleUploadedFile('rubrica.jpg', _jpeg_signature(), content_type='image/jpeg')},
        )

    def test_manager_can_upload_and_replace_user_signature(self):
        self.client.force_login(self.admin)
        response = self._upload()
        self.assertEqual(response.status_code, 200)
        signature = AssinaturaUsuario.objects.get(usuario=self.approver)
        self.assertTrue(signature.arquivo_original.name.endswith('.jpg'))
        self.assertTrue(signature.imagem_processada.name.endswith('.png'))
        with signature.imagem_processada.open('rb') as processed_file:
            processed = Image.open(processed_file).convert('RGBA')
            self.assertEqual(processed.getpixel((0, 0))[3], 0)
        self.assertTrue(response.json()['user']['has_signature'])

        response = self._upload()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AssinaturaUsuario.objects.filter(usuario=self.approver).count(), 1)

    def test_regular_user_cannot_upload_signature(self):
        self.client.force_login(self.regular)
        response = self._upload()
        self.assertEqual(response.status_code, 403)
        self.assertFalse(AssinaturaUsuario.objects.filter(usuario=self.approver).exists())

    def test_invalid_file_is_rejected(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('administracao_atualizar_assinatura', args=[self.approver.id]),
            {'assinatura': SimpleUploadedFile('rubrica.txt', b'not an image', content_type='text/plain')},
        )
        self.assertEqual(response.status_code, 400)

    def test_png_photo_is_accepted(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('administracao_atualizar_assinatura', args=[self.approver.id]),
            {'assinatura': SimpleUploadedFile('foto-assinatura.png', _png_signature(), content_type='image/png')},
        )
        self.assertEqual(response.status_code, 200)
        signature = AssinaturaUsuario.objects.get(usuario=self.approver)
        self.assertTrue(signature.arquivo_original.name.endswith('.png'))
        self.assertTrue(signature.imagem_processada.name.endswith('.png'))

    def test_pdf_signature_is_converted_and_used_by_rdo_document(self):
        self.client.force_login(self.admin)
        upload_response = self.client.post(
            reverse('administracao_atualizar_assinatura', args=[self.approver.id]),
            {'assinatura': SimpleUploadedFile('rubrica.pdf', _pdf_signature(), content_type='application/pdf')},
        )
        self.assertEqual(upload_response.status_code, 200)
        signature = AssinaturaUsuario.objects.get(usuario=self.approver)
        self.assertTrue(signature.arquivo_original.name.endswith('.pdf'))
        self.assertTrue(signature.imagem_processada.name.endswith('.png'))

        document_response = self.client.get(reverse('rdo_page', args=[self.rdo.id]))
        self.assertEqual(document_response.status_code, 200)
        self.assertContains(document_response, 'approval-signature-img')
        self.assertContains(document_response, 'data:image/png;base64,')

    def test_approved_rdo_contains_signature_and_without_it_remains_blank(self):
        self.client.force_login(self.admin)
        blank_response = self.client.get(reverse('rdo_page', args=[self.rdo.id]))
        self.assertNotContains(blank_response, 'approval-signature-img')

        self._upload()
        signed_response = self.client.get(reverse('rdo_page', args=[self.rdo.id]))
        self.assertContains(signed_response, 'approval-signature-img')
        self.assertContains(signed_response, 'data:image/png;base64,')

    def test_unapproved_rdo_does_not_contain_registered_signature(self):
        self.client.force_login(self.admin)
        self._upload()
        self.rdo.aprovado = False
        self.rdo.save(update_fields=['aprovado'])
        response = self.client.get(reverse('rdo_page', args=[self.rdo.id]))
        self.assertNotContains(response, 'approval-signature-img')

    def test_manager_can_remove_signature(self):
        self.client.force_login(self.admin)
        self._upload()
        response = self.client.post(reverse('administracao_remover_assinatura', args=[self.approver.id]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AssinaturaUsuario.objects.filter(usuario=self.approver).exists())
