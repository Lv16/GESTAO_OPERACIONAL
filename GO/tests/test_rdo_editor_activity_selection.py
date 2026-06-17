from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from GO.models import Cliente, OrdemServico, RDO, RDOAtividade, Unidade


@override_settings(
    STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage',
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    },
)
class RdoEditorActivitySelectionTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username='editor.activity.selection',
            email='editor-activity-selection@example.com',
            password='secret123',
        )
        self.client.force_login(self.user)

    def test_editor_fragment_marks_saved_activity_instead_of_first_option(self):
        cliente = Cliente.objects.create(nome='Cliente Editor Atividade')
        unidade = Unidade.objects.create(nome='Unidade Editor Atividade')
        os_obj = OrdemServico.objects.create(
            numero_os='20002',
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
            rdo='16',
            data=date(2026, 4, 11),
            data_inicio=date(2026, 4, 11),
        )
        RDOAtividade.objects.create(
            rdo=rdo,
            ordem=0,
            atividade='Coleta de Água / Water sampling',
            inicio=time(8, 0),
            fim=time(9, 0),
            comentario_pt='atividade legada',
        )

        response = self.client.get(
            reverse('rdo_detail', args=[rdo.id]),
            {'render': 'editor'},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        html = payload.get('html') or ''
        self.assertIn('<option value="coleta de água" selected>', html)
        self.assertNotIn('<option value="abertura pt" selected>', html)
