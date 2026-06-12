from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase

from GO.models import Cliente, Equipamentos, Modelo, OrdemServico, Unidade


class RdoRetornoEquipamentosWebEndpointTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.supervisor_group, _ = Group.objects.get_or_create(name='Supervisor')
        self.user = User.objects.create_user(
            username='web_supervisor',
            password='xpto1234',
        )
        self.supervisor_group.user_set.add(self.user)
        self.other_user = User.objects.create_user(
            username='web_supervisor_2',
            password='xpto1234',
        )
        self.supervisor_group.user_set.add(self.other_user)
        self.client.force_login(self.user)

        self.cliente = Cliente.objects.create(nome='Cliente Web Retorno')
        self.unidade = Unidade.objects.create(nome='Unidade Web Retorno')
        self.modelo = Modelo.objects.create(
            nome='Modelo Web Retorno',
            descricao='Bomba',
        )

    def _create_os(self, numero_os, supervisor):
        return OrdemServico.objects.create(
            numero_os=numero_os,
            data_inicio=date.today(),
            dias_de_operacao=1,
            servico='LIMPEZA',
            metodo='Manual',
            pob=1,
            volume_tanque=Decimal('10.00'),
            Cliente=self.cliente,
            Unidade=self.unidade,
            tipo_operacao='Onshore',
            solicitante='Teste',
            supervisor=supervisor,
        )

    def test_endpoint_returns_only_current_os_embarked_equipments(self):
        os_obj = self._create_os(8123, self.user)
        other_os = self._create_os(9001, self.user)

        embarked = Equipamentos.objects.create(
            modelo=self.modelo,
            descricao='Gerador',
            numero_serie='SER-001',
            numero_tag='TAG-001',
            numero_os=str(os_obj.numero_os),
            situacao='embarcardo',
        )
        Equipamentos.objects.create(
            modelo=self.modelo,
            descricao='Compressor',
            numero_serie='SER-002',
            numero_tag='TAG-002',
            numero_os=str(os_obj.numero_os),
            situacao='Retornou para a base',
        )
        Equipamentos.objects.create(
            modelo=self.modelo,
            descricao='Bomba',
            numero_serie='SER-003',
            numero_tag='TAG-003',
            numero_os=str(other_os.numero_os),
            situacao='embarcardo',
        )

        response = self.client.get(
            f'/api/rdo/os/{os_obj.id}/equipamentos-retorno/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data['os']['id'], os_obj.id)
        self.assertEqual(len(data['items']), 1)
        self.assertEqual(data['items'][0]['id'], embarked.id)
        self.assertEqual(data['items'][0]['numero_serie'], 'SER-001')
        self.assertEqual(data['items'][0]['tag'], 'TAG-001')
        self.assertEqual(data['items'][0]['situacao'], 'embarcardo')

    def test_supervisor_cannot_access_other_supervisor_os(self):
        other_os = self._create_os(9550, self.other_user)

        response = self.client.get(
            f'/api/rdo/os/{other_os.id}/equipamentos-retorno/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertFalse(data.get('success'))
