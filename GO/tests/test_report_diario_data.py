import json
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from GO.models import Cliente, OrdemServico, RDO, RdoTanque, Unidade
from GO.views_dashboard_rdo import report_diario_data


class ReportDiarioDataTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.cliente = Cliente.objects.create(nome='Cliente Report Diario')
        self.unidade = Unidade.objects.create(nome='Unidade Report Diario')
        self.supervisor = User.objects.create_user(
            username='supervisor_report_diario',
            first_name='Supervisor',
            last_name='Report',
            password='senha123',
        )
        self.coordenador = next(value for value, _ in OrdemServico.COORDENADORES if value)
        self.os_obj = OrdemServico.objects.create(
            numero_os=8201,
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
            status_operacao='Em Andamento',
            status_geral='Em Andamento',
            status_comercial='Em aberto',
            status_planejamento='Pendente',
        )

    def _parse_response(self, response):
        return json.loads(response.content.decode('utf-8'))

    def test_report_diario_data_returns_cumulative_compartments_for_selected_tank(self):
        rdo_prev = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-ANT',
            data=date(2026, 3, 10),
        )
        rdo_prev.tanque_codigo = 'TQ-01'
        rdo_prev.numero_compartimentos = 7
        rdo_prev.compartimentos_avanco_json = json.dumps({
            '1': {'mecanizada': 20, 'fina': 0},
            '2': {'mecanizada': 30, 'fina': 10},
            '3': {'mecanizada': 0, 'fina': 0},
            '4': {'mecanizada': 0, 'fina': 0},
            '5': {'mecanizada': 0, 'fina': 0},
            '6': {'mecanizada': 0, 'fina': 0},
            '7': {'mecanizada': 0, 'fina': 0},
        }, ensure_ascii=False)
        rdo_prev.save()
        rdo_curr = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-ATUAL',
            data=date(2026, 3, 11),
        )
        rdo_curr.tanque_codigo = 'TQ-01'
        rdo_curr.numero_compartimentos = 7
        rdo_curr.compartimentos_avanco_json = json.dumps({
            '1': {'mecanizada': 55, 'fina': 0},
            '2': {'mecanizada': 40, 'fina': 5},
            '3': {'mecanizada': 9, 'fina': 0},
            '4': {'mecanizada': 0, 'fina': 0},
            '5': {'mecanizada': 0, 'fina': 0},
            '6': {'mecanizada': 0, 'fina': 0},
            '7': {'mecanizada': 0, 'fina': 0},
        }, ensure_ascii=False)
        rdo_curr.save()

        RdoTanque.objects.create(
            rdo=rdo_prev,
            tanque_codigo='TQ-01',
            numero_compartimentos=7,
            sentido_limpeza=RdoTanque.SENTIDO_VANTE_RE,
            compartimentos_avanco_json=json.dumps({
                '1': {'mecanizada': 20, 'fina': 0},
                '2': {'mecanizada': 30, 'fina': 10},
                '3': {'mecanizada': 0, 'fina': 0},
                '4': {'mecanizada': 0, 'fina': 0},
                '5': {'mecanizada': 0, 'fina': 0},
                '6': {'mecanizada': 0, 'fina': 0},
                '7': {'mecanizada': 0, 'fina': 0},
            }, ensure_ascii=False),
        )
        RdoTanque.objects.create(
            rdo=rdo_curr,
            tanque_codigo='TQ-01',
            numero_compartimentos=7,
            sentido_limpeza=RdoTanque.SENTIDO_VANTE_RE,
            compartimentos_avanco_json=json.dumps({
                '1': {'mecanizada': 55, 'fina': 0},
                '2': {'mecanizada': 40, 'fina': 5},
                '3': {'mecanizada': 9, 'fina': 0},
                '4': {'mecanizada': 0, 'fina': 0},
                '5': {'mecanizada': 0, 'fina': 0},
                '6': {'mecanizada': 0, 'fina': 0},
                '7': {'mecanizada': 0, 'fina': 0},
            }, ensure_ascii=False),
        )

        request = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
            'tanque': 'TQ-01',
        })
        response = report_diario_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['info_os']['tanque'], 'TQ-01')
        self.assertEqual(payload['compartimentos_avanco_cumulado']['1']['mecanizada'], 75.0)
        self.assertEqual(payload['compartimentos_avanco_cumulado']['2']['mecanizada'], 70.0)
        self.assertEqual(payload['compartimentos_avanco_cumulado']['3']['mecanizada'], 9.0)
        self.assertEqual(payload['compartimentos_avanco_cumulado']['2']['fina'], 15.0)
        self.assertEqual(payload['compartimentos_avanco_cumulado']['2']['avanco'], 85.0)
        self.assertEqual(payload['compartimentos_avanco_cumulado']['2']['sujidade'], 15.0)
        self.assertEqual(payload['tanque_3d']['total_compartimentos'], 7)
        self.assertEqual(payload['tanque_3d']['total_percent'], 24.14)
        self.assertTrue(payload['tanque_3d']['available'])
        self.assertEqual(payload['tanque_3d']['source_kind'], 'rdo')
        self.assertEqual(payload['tanque_3d']['chart']['key'], 'avanco')
        self.assertEqual(len(payload['tanque_3d']['charts']), 1)
        self.assertEqual(payload['tanque_3d']['charts'][0]['key'], 'avanco')
        self.assertEqual(payload['tanque_3d']['charts'][0]['items'][0]['value'], 75.0)
        self.assertEqual(payload['tanque_3d']['charts'][0]['items'][1]['value'], 85.0)
        self.assertEqual(payload['tanque_3d']['sentido_inicio'], 'Vante')
        self.assertEqual(payload['tanque_3d']['sentido_fim'], 'Ré')

    def test_report_diario_data_requires_specific_tank_for_3d_chart(self):
        rdo_curr = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-ATUAL-2',
            data=date(2026, 3, 12),
        )
        RdoTanque.objects.create(
            rdo=rdo_curr,
            tanque_codigo='TQ-02',
            numero_compartimentos=4,
            compartimentos_avanco_json=json.dumps({
                '1': {'mecanizada': 10, 'fina': 0},
                '2': {'mecanizada': 0, 'fina': 0},
                '3': {'mecanizada': 0, 'fina': 0},
                '4': {'mecanizada': 0, 'fina': 0},
            }, ensure_ascii=False),
        )
        RdoTanque.objects.create(
            rdo=rdo_curr,
            tanque_codigo='TQ-03',
            numero_compartimentos=4,
            compartimentos_avanco_json=json.dumps({
                '1': {'mecanizada': 25, 'fina': 0},
                '2': {'mecanizada': 0, 'fina': 0},
                '3': {'mecanizada': 0, 'fina': 0},
                '4': {'mecanizada': 0, 'fina': 0},
            }, ensure_ascii=False),
        )

        request = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
        })
        response = report_diario_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])
        self.assertFalse(payload['tanque_3d']['available'])
        self.assertTrue(payload['tanque_3d']['requires_specific_tank'])

    def test_report_diario_data_auto_selects_single_available_tank(self):
        rdo_curr = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-ATUAL-3',
            data=date(2026, 3, 13),
        )
        RdoTanque.objects.create(
            rdo=rdo_curr,
            tanque_codigo='TQ-UNICO',
            numero_compartimentos=3,
            sentido_limpeza=RdoTanque.SENTIDO_VANTE_RE,
            compartimentos_avanco_json=json.dumps({
                '1': {'mecanizada': 40, 'fina': 0},
                '2': {'mecanizada': 20, 'fina': 0},
                '3': {'mecanizada': 0, 'fina': 0},
            }, ensure_ascii=False),
        )

        request = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
        })
        response = report_diario_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['info_os']['tanque'], 'TQ-UNICO')
        self.assertTrue(payload['tanque_3d']['available'])
        self.assertFalse(payload['tanque_3d']['requires_specific_tank'])

    def test_report_diario_data_kpi_usa_hh_real_cumulativo_calculado(self):
        RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-HH-1',
            data=date(2026, 3, 10),
            total_hh_frente_real=time(6, 0),
        )
        rdo_curr = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-HH-2',
            data=date(2026, 3, 11),
            total_hh_frente_real=time(5, 30),
        )
        RDO.objects.filter(pk=rdo_curr.pk).update(total_hh_cumulativo_real=None)

        request = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
        })
        response = report_diario_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['kpi']['hh_real'], '11:30:00')
