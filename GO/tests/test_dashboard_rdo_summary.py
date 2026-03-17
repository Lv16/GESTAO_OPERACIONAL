from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from GO.models import Cliente, OrdemServico, Unidade
from GO.views_dashboard_rdo import summary_operations_data


class DashboardRdoSummaryTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(nome='Cliente Resumo RDO')
        self.unidade = Unidade.objects.create(nome='Unidade Resumo RDO')
        self.coordenador = next(value for value, _ in OrdemServico.COORDENADORES if value)
        self.supervisor = User.objects.create_user(
            username='supervisor_resumo_rdo',
            first_name='Supervisor',
            last_name='Resumo',
            password='senha123',
        )

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

    def test_summary_status_filter_prefers_status_geral(self):
        os_em_andamento_mov = self._create_os(
            numero_os=7101,
            status_operacao='Programada',
            status_geral='Em Andamento',
        )
        self._create_os(
            numero_os=7102,
            status_operacao='Em Andamento',
            status_geral='Programada',
        )

        items = summary_operations_data({
            'status': 'Em Andamento',
            'supervisor': 'supervisor_resumo_rdo',
        })

        numeros = {item.get('numero_os') for item in items}
        self.assertIn(os_em_andamento_mov.numero_os, numeros)
        self.assertNotIn(7102, numeros)

    def test_summary_status_filter_falls_back_to_status_operacao_when_status_geral_is_empty(self):
        os_legada = self._create_os(
            numero_os=7103,
            status_operacao='Em Andamento',
            status_geral='',
        )

        items = summary_operations_data({
            'status': 'Em Andamento',
            'supervisor': 'supervisor_resumo_rdo',
        })

        numeros = {item.get('numero_os') for item in items}
        self.assertIn(os_legada.numero_os, numeros)

    def test_summary_excludes_placeholder_supervisor_a_definir(self):
        supervisor_placeholder = User.objects.create_user(
            username='a definir',
            first_name='A',
            last_name='Definir',
            password='senha123',
        )
        self._create_os(
            numero_os=7104,
            status_operacao='Em Andamento',
            status_geral='Em Andamento',
        )
        OrdemServico.objects.create(
            numero_os=7105,
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
            supervisor=supervisor_placeholder,
            status_operacao='Em Andamento',
            status_geral='Em Andamento',
            status_comercial='Em aberto',
            status_planejamento='Pendente',
        )

        items = summary_operations_data({
            'status': 'Em Andamento',
        })

        numeros = {item.get('numero_os') for item in items}
        self.assertIn(7104, numeros)
        self.assertNotIn(7105, numeros)
