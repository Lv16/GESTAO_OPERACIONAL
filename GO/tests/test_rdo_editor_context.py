from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from GO.models import Cliente, OrdemServico, RDO, RdoTanque, Unidade


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

    def test_rdo_page_expoe_tanque_id_no_contexto_do_editor(self):
        cliente = Cliente.objects.create(nome='Cliente Contexto Editor')
        unidade = Unidade.objects.create(nome='Unidade Contexto Editor')
        os_obj = OrdemServico.objects.create(
            numero_os='20001',
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

        response = self.client.get(reverse('rdo'))

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
