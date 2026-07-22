from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from GO.models import Cliente, OrdemServico, RDO, Unidade


class RdoOsStatusSyncTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.cliente = Cliente.objects.create(nome='Cliente RDO Status')
        self.unidade = Unidade.objects.create(nome='Unidade RDO Status')
        self.coordenador = next(value for value, _ in OrdemServico.COORDENADORES if value)
        self.supervisor_group, _ = Group.objects.get_or_create(name='Supervisor')
        self.supervisor = User.objects.create_user(
            username='supervisor_rdo_status_sync',
            password='senha123',
        )
        self.supervisor_group.user_set.add(self.supervisor)
        self.client.force_login(self.supervisor)

    def _create_os(self, numero_os, status_operacao='Programada', status_geral='Programada'):
        return OrdemServico.objects.create(
            numero_os=numero_os,
            data_inicio=date(2026, 3, 10),
            data_fim=None,
            dias_de_operacao=0,
            servico='COLETA DE AR',
            servicos='COLETA DE AR',
            metodo='Manual',
            pob=1,
            tanque='',
            tanques=None,
            volume_tanque=Decimal('0.00'),
            Cliente=self.cliente,
            Unidade=self.unidade,
            tipo_operacao='Onshore',
            solicitante='Solicitante Teste',
            coordenador=self.coordenador,
            supervisor=self.supervisor,
            status_operacao=status_operacao,
            status_geral=status_geral,
            status_comercial='Em aberto',
            status_planejamento='Pendente',
        )

    def test_create_rdo_promove_linhas_programadas_da_mesma_os_para_em_andamento(self):
        os_principal = self._create_os(numero_os=6043)
        os_mesma_ordem = self._create_os(numero_os=6043)
        os_paralizada = self._create_os(numero_os=6043, status_operacao='Paralizada', status_geral='Paralizada')
        os_outra_ordem = self._create_os(numero_os=6044)

        response = self.client.post(
            reverse('rdo_create_ajax'),
            data={
                'ordem_servico_id': str(os_principal.pk),
                'data': '2026-03-10',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertTrue(payload.get('status_promovido_em_andamento'))
        self.assertEqual(payload.get('same_os_status_updates'), 2)

        os_principal.refresh_from_db()
        os_mesma_ordem.refresh_from_db()
        os_paralizada.refresh_from_db()
        os_outra_ordem.refresh_from_db()

        self.assertEqual(os_principal.status_operacao, 'Em Andamento')
        self.assertEqual(os_principal.status_geral, 'Em Andamento')
        self.assertEqual(os_mesma_ordem.status_operacao, 'Em Andamento')
        self.assertEqual(os_mesma_ordem.status_geral, 'Em Andamento')
        self.assertEqual(os_paralizada.status_operacao, 'Paralizada')
        self.assertEqual(os_paralizada.status_geral, 'Paralizada')
        self.assertEqual(os_outra_ordem.status_operacao, 'Programada')
        self.assertEqual(os_outra_ordem.status_geral, 'Programada')

    def test_update_rdo_promove_linhas_programadas_da_mesma_os_para_em_andamento(self):
        os_principal = self._create_os(numero_os=6045)
        os_mesma_ordem = self._create_os(numero_os=6045)
        os_finalizada = self._create_os(numero_os=6045, status_operacao='Finalizada', status_geral='Finalizada')
        rdo = RDO.objects.create(
            ordem_servico=os_principal,
            rdo='1',
            data=date(2026, 3, 10),
            data_inicio=date(2026, 3, 10),
        )

        response = self.client.post(
            reverse('rdo_update_ajax'),
            data={
                'rdo_id': str(rdo.pk),
                'data': '2026-03-10',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertTrue(payload.get('status_promovido_em_andamento'))
        self.assertEqual(payload.get('same_os_status_updates'), 2)

        os_principal.refresh_from_db()
        os_mesma_ordem.refresh_from_db()
        os_finalizada.refresh_from_db()

        self.assertEqual(os_principal.status_operacao, 'Em Andamento')
        self.assertEqual(os_principal.status_geral, 'Em Andamento')
        self.assertEqual(os_mesma_ordem.status_operacao, 'Em Andamento')
        self.assertEqual(os_mesma_ordem.status_geral, 'Em Andamento')
        self.assertEqual(os_finalizada.status_operacao, 'Finalizada')
        self.assertEqual(os_finalizada.status_geral, 'Finalizada')
