from datetime import date
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from GO.models import Cliente, OrdemServico, RDO, Unidade

@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }
)
class RdoApprovalPreventionTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='test_approver', password='x')
        
        cliente = Cliente.objects.create(nome='Cliente Teste')
        unidade = Unidade.objects.create(nome='Unidade Teste')
        self.ordem = OrdemServico.objects.create(
            numero_os=1010,
            data_inicio=date(2026, 7, 1),
            dias_de_operacao=1,
            servico='LIMPEZA DE DUTO',
            metodo='Manual',
            Cliente=cliente,
            Unidade=unidade,
            pob=1,
        )
        self.rdo = RDO.objects.create(
            ordem_servico=self.ordem,
            rdo='101',
            data=date(2026, 7, 1),
            data_inicio=date(2026, 7, 1),
            aprovado=False
        )
        self.url = reverse('api_rdo_aprovar', kwargs={'rdo_id': self.rdo.id})

    def test_approve_rdo_succeeds_but_cannot_be_undone(self):
        self.client.force_login(self.user)
        
        # 1. Approve the RDO
        response = self.client.post(self.url, {'approved': 'true'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        
        self.rdo.refresh_from_db()
        self.assertTrue(self.rdo.aprovado)
        self.assertEqual(self.rdo.aprovado_por, self.user)
        
        # 2. Attempt to uncheck/unapprove the RDO
        response = self.client.post(self.url, {'approved': 'false'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload['success'])
        self.assertEqual(payload['error'], 'Não é permitido desmarcar um RDO já aprovado.')
        
        # Verify it remains approved in database
        self.rdo.refresh_from_db()
        self.assertTrue(self.rdo.aprovado)
        self.assertEqual(self.rdo.aprovado_por, self.user)
