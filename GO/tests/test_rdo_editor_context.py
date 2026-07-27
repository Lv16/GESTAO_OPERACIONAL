import os
import shutil
import tempfile
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.test.client import RequestFactory
from django.urls import reverse

from GO.models import Cliente, OrdemServico, RDO, RdoTanque, Unidade
from GO.views_rdo import _build_rdo_page_context, _build_rdo_photo_public_path


@override_settings(
    STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage',
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    },
)
class RdoEditorContextPageTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username='editor.context',
            email='editor-context@example.com',
            password='secret123',
        )
        self.client.force_login(self.user)
        self.factory = RequestFactory()

    def _build_os(self, numero_os='20001'):
        cliente = Cliente.objects.create(nome=f'Cliente {numero_os}')
        unidade = Unidade.objects.create(nome=f'Unidade {numero_os}')
        return OrdemServico.objects.create(
            numero_os=numero_os,
            data_inicio=date(2026, 4, 10),
            dias_de_operacao_frente=0,
            dias_de_operacao=0,
            servico='TESTE',
            metodo='Manual',
            observacao='',
            pob=1,
            tanque='',
            volume_tanque=Decimal('0.00'),
            Cliente=cliente,
            Unidade=unidade,
            tipo_operacao='Onshore',
            solicitante='Teste',
            status_operacao='Programada',
            status_comercial='Em aberto',
        )

    def test_rdo_page_expoe_tanque_id_no_contexto_do_editor(self):
        os_obj = self._build_os('20001')
        rdo = RDO.objects.create(
            ordem_servico=os_obj,
            rdo='15',
            data=date(2026, 4, 11),
            data_inicio=date(2026, 4, 11),
        )
        tank = RdoTanque.objects.create(
            rdo=rdo,
            tanque_codigo='TK-CTX',
            nome_tanque='Tanque Contexto',
            numero_compartimentos=4,
        )

        response = self.client.get(reverse('rdo'), follow=True)

        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertRegex(
            html,
            rf'<tr[^>]*data-rdo-id="{rdo.id}"[^>]*data-tanque-id="{tank.id}"',
        )
        self.assertRegex(
            html,
            rf'<button[^>]*class="action-btn edit allow-edit"[^>]*data-tanque-id="{tank.id}"',
        )

    def test_rdo_page_context_resolve_foto_correta_sem_fallback_generico(self):
        media_root = tempfile.mkdtemp(prefix='rdo-photo-test-')
        self.addCleanup(lambda: shutil.rmtree(media_root, ignore_errors=True))

        with override_settings(MEDIA_ROOT=media_root, MEDIA_URL='/media/'):
            os_obj = self._build_os('20002')
            rdo = RDO.objects.create(
                ordem_servico=os_obj,
                rdo='1',
                data=date(2026, 4, 11),
                data_inicio=date(2026, 4, 11),
            )

            expected_name = '20260619150330803454_1.jpg'
            rdo.fotos_1.save(expected_name, ContentFile(b'foto-correta'), save=True)

            os.makedirs(os.path.join(media_root, 'outras'), exist_ok=True)
            with open(os.path.join(media_root, 'outras', '99999999999999999999_1.jpg'), 'wb') as handle:
                handle.write(b'foto-errada-maior')

            request = self.factory.get(f'/rdo/{rdo.id}/page/')
            request.user = self.user

            context = _build_rdo_page_context(request, rdo.id)

            self.assertEqual(
                context['fotos_padded'][0],
                f'/fotos_rdo/rdos/{expected_name}',
            )

    def test_foto_referenciada_sem_arquivo_nao_gera_url_publica(self):
        media_root = tempfile.mkdtemp(prefix='rdo-photo-missing-test-')
        self.addCleanup(lambda: shutil.rmtree(media_root, ignore_errors=True))

        with override_settings(MEDIA_ROOT=media_root, MEDIA_URL='/media/'):
            self.assertIsNone(
                _build_rdo_photo_public_path(
                    '/fotos_rdo/rdos/foto-que-nao-existe.jpg',
                ),
            )
