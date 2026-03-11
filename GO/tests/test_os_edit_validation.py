from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from GO.models import Cliente, OrdemServico, Unidade


class OrdemServicoEditValidationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.cliente_a = Cliente.objects.create(nome='Cliente Validacao A')
        self.cliente_b = Cliente.objects.create(nome='Cliente Validacao B')
        self.unidade = Unidade.objects.create(nome='Unidade Validacao')
        self.coordenador = next(value for value, _ in OrdemServico.COORDENADORES if value)
        self.supervisor_group, _ = Group.objects.get_or_create(name='Supervisor')
        self.supervisor = User.objects.create_user(
            username='supervisor_validacao_os',
            password='senha123',
        )
        self.supervisor_group.user_set.add(self.supervisor)

    def _create_os(self):
        return OrdemServico.objects.create(
            numero_os=91001,
            data_inicio=date(2026, 3, 1),
            data_fim=None,
            dias_de_operacao=0,
            servico='COLETA DE AR',
            servicos='COLETA DE AR',
            metodo='Manual',
            pob=1,
            tanque='',
            tanques=None,
            volume_tanque=Decimal('0.00'),
            Cliente=self.cliente_a,
            Unidade=self.unidade,
            tipo_operacao='Onshore',
            solicitante='Solicitante Teste',
            coordenador=self.coordenador,
            supervisor=self.supervisor,
            status_operacao='Programada',
            status_geral='Programada',
            status_comercial='Em aberto',
            status_planejamento='Pendente',
        )

    def _edit_payload(self, os_obj, **overrides):
        payload = {
            'os_id': str(os_obj.pk),
            'cliente': self.cliente_a.nome,
            'unidade': self.unidade.nome,
            'solicitante': 'Solicitante Teste',
            'servico': 'COLETA DE AR',
            'metodo': 'Manual',
            'pob': '1',
            'data_inicio': '2026-03-01',
            'tipo_operacao': 'Onshore',
            'status_operacao': 'Programada',
            'status_geral': 'Programada',
            'status_comercial': 'Em aberto',
            'status_planejamento': 'Pendente',
            'coordenador': self.coordenador,
            'supervisor': str(self.supervisor.pk),
            'volume_tanque': '0',
        }
        payload.update(overrides)
        return payload

    def test_edicao_aceita_cliente_cadastrado(self):
        os_obj = self._create_os()

        response = self.client.post(
            reverse('editar_os_post'),
            data=self._edit_payload(os_obj, cliente=self.cliente_b.nome),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))

        os_obj.refresh_from_db()
        self.assertEqual(os_obj.Cliente_id, self.cliente_b.pk)
        self.assertEqual(os_obj.cliente, self.cliente_b.nome)

    def test_edicao_rejeita_cliente_inexistente_com_erro_400(self):
        os_obj = self._create_os()

        response = self.client.post(
            reverse('editar_os_post'),
            data=self._edit_payload(os_obj, cliente='Cliente Inexistente XYZ'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload.get('success'))
        self.assertEqual(payload.get('error'), 'Cliente não encontrado. Selecione um cliente cadastrado.')

        os_obj.refresh_from_db()
        self.assertEqual(os_obj.Cliente_id, self.cliente_a.pk)
