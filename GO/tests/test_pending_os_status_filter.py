from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from GO.models import Cliente, OrdemServico, Unidade


class PendingOsStatusFilterTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='pending_os_status_user',
            password='senha123',
        )
        self.client.force_login(self.user)

        self.cliente = Cliente.objects.create(nome='Cliente Pending OS')
        self.unidade = Unidade.objects.create(nome='Unidade Pending OS')
        self.coordenador = next(value for value, _ in OrdemServico.COORDENADORES if value)

    def _create_os(self, numero_os, status_operacao, status_geral):
        return OrdemServico.objects.create(
            numero_os=numero_os,
            data_inicio=date(2026, 4, 1),
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
            status_operacao=status_operacao,
            status_geral=status_geral,
            status_comercial='Em aberto',
            status_planejamento='Pendente',
        )

    def test_pending_os_endpoint_uses_only_status_operacao(self):
        included = self._create_os(
            numero_os=81001,
            status_operacao='Programada',
            status_geral='Finalizada',
        )
        self._create_os(
            numero_os=81002,
            status_operacao='Finalizada',
            status_geral='Programada',
        )
        self._create_os(
            numero_os=81003,
            status_operacao='Em Andamento',
            status_geral='Cancelada',
        )

        response = self.client.get(reverse('rdo_pending_os'))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        numeros = {item['numero_os'] for item in payload['os_list']}

        self.assertIn(included.numero_os, numeros)
        self.assertIn(81003, numeros)
        self.assertNotIn(81002, numeros)
