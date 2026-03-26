from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

from GO.models import Cliente, OrdemServico, Unidade


@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class HomeStatusDatabookFilterTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='home_filter_user',
            password='senha123',
        )
        self.client.force_login(self.user)

        self.cliente = Cliente.objects.create(nome='Cliente Filtro Home')
        self.unidade = Unidade.objects.create(nome='Unidade Filtro Home')
        self.coordenador = next(value for value, _ in OrdemServico.COORDENADORES if value)

    def _create_os(self, numero_os, status_databook):
        return OrdemServico.objects.create(
            numero_os=numero_os,
            data_inicio=date(2026, 3, 26),
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
            status_operacao='Programada',
            status_geral='Programada',
            status_comercial='Em aberto',
            status_planejamento='Pendente',
            status_databook=status_databook,
        )

    def test_home_filters_by_status_databook_and_keeps_active_filter(self):
        os_finalizada = self._create_os(numero_os=92001, status_databook='Finalizado')
        self._create_os(numero_os=92002, status_databook='Em Andamento')

        response = self.client.get(reverse('home'), {'status_databook': 'Finalizado'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="filter_especificacao"', html=False)
        self.assertContains(response, 'id="filter_status_databook"', html=False)
        self.assertContains(response, 'list="status_databook_datalist"', html=False)
        self.assertEqual(
            [obj.pk for obj in response.context['servicos'].object_list],
            [os_finalizada.pk],
        )
        self.assertEqual(
            response.context['filtros_ativos'].get('Status Databook'),
            'Finalizado',
        )

    def test_lista_servicos_get_filters_by_status_databook(self):
        os_finalizada = self._create_os(numero_os=93001, status_databook='Finalizado')
        self._create_os(numero_os=93002, status_databook='Em Andamento')

        response = self.client.get(reverse('lista_servicos'), {'status_databook': 'Finalizado'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [obj.pk for obj in response.context['servicos'].object_list],
            [os_finalizada.pk],
        )
