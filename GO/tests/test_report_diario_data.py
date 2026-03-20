import json
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from GO.models import Cliente, OrdemServico, RDO, RDOAtividade, RdoTanque, Unidade
from GO.views_dashboard_rdo import os_tanques_data, report_diario_data


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

        tank_prev = RdoTanque.objects.create(
            rdo=rdo_prev,
            tanque_codigo='TQ-01',
            numero_compartimentos=7,
            sentido_limpeza=RdoTanque.SENTIDO_VANTE_RE,
            limpeza_mecanizada_cumulativa=Decimal('20.00'),
            limpeza_fina_cumulativa=Decimal('3.00'),
            percentual_ensacamento=Decimal('8.00'),
            percentual_icamento=Decimal('0.00'),
            percentual_cambagem=Decimal('8.00'),
            percentual_avanco_cumulativo=Decimal('28.00'),
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
        tank_curr = RdoTanque.objects.create(
            rdo=rdo_curr,
            tanque_codigo='TQ-01',
            numero_compartimentos=7,
            sentido_limpeza=RdoTanque.SENTIDO_VANTE_RE,
            limpeza_mecanizada_cumulativa=Decimal('50.00'),
            limpeza_fina_cumulativa=Decimal('12.00'),
            percentual_ensacamento=Decimal('40.00'),
            percentual_icamento=Decimal('35.00'),
            percentual_cambagem=Decimal('50.00'),
            percentual_avanco_cumulativo=Decimal('55.00'),
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
        tank_prev.refresh_from_db()
        tank_curr.refresh_from_db()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['info_os']['tanque'], 'TQ-01')
        self.assertEqual(payload['curva_s']['raspagem_acumulada'], [
            round(float(tank_prev.limpeza_mecanizada_cumulativa or 0), 1),
            round(float(tank_curr.limpeza_mecanizada_cumulativa or 0), 1),
        ])
        self.assertEqual(payload['curva_s']['ensacamento_acumulado'], [
            round(float(tank_prev.percentual_ensacamento or 0), 1),
            round(float(tank_curr.percentual_ensacamento or 0), 1),
        ])
        self.assertEqual(payload['curva_s']['icamento_acumulado'], [
            round(float(tank_prev.percentual_icamento or 0), 1),
            round(float(tank_curr.percentual_icamento or 0), 1),
        ])
        self.assertEqual(payload['curva_s']['cambagem_acumulada'], [
            round(float(tank_prev.percentual_cambagem or 0), 1),
            round(float(tank_curr.percentual_cambagem or 0), 1),
        ])
        self.assertEqual(payload['curva_s']['limpeza_fina_acumulada'], [
            round(float(tank_prev.limpeza_fina_cumulativa or 0), 1),
            round(float(tank_curr.limpeza_fina_cumulativa or 0), 1),
        ])
        self.assertEqual(payload['curva_s']['totais']['raspagem'], round(float(tank_curr.limpeza_mecanizada_cumulativa or 0), 1))
        self.assertEqual(payload['curva_s']['totais']['ensacamento'], round(float(tank_curr.percentual_ensacamento or 0), 1))
        self.assertEqual(payload['curva_s']['totais']['icamento'], round(float(tank_curr.percentual_icamento or 0), 1))
        self.assertEqual(payload['curva_s']['totais']['cambagem'], round(float(tank_curr.percentual_cambagem or 0), 1))
        self.assertEqual(payload['curva_s']['totais']['limpeza_fina'], round(float(tank_curr.limpeza_fina_cumulativa or 0), 1))
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

    def test_report_diario_data_monta_comparativo_realizado_e_programado(self):
        self.os_obj.data_inicio_frente = date(2026, 3, 10)
        self.os_obj.data_fim_frente = date(2026, 3, 14)
        self.os_obj.save(update_fields=['data_inicio_frente', 'data_fim_frente', 'dias_de_operacao_frente'])

        rdo_1 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-PLAN-1',
            data=date(2026, 3, 10),
        )
        rdo_2 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-PLAN-2',
            data=date(2026, 3, 12),
        )
        rdo_3 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-PLAN-3',
            data=date(2026, 3, 14),
        )
        RDOAtividade.objects.create(
            rdo=rdo_1,
            atividade='Instalação / Preparação / Montagem / Setup ',
        )

        tank_1 = RdoTanque.objects.create(
            rdo=rdo_1,
            tanque_codigo='TQ-PLAN',
            numero_compartimentos=6,
            ensacamento_prev=40,
            icamento_prev=20,
            cambagem_prev=10,
            limpeza_mecanizada_cumulativa=Decimal('10.00'),
            limpeza_fina_cumulativa=Decimal('0.00'),
            percentual_ensacamento=Decimal('5.00'),
            percentual_icamento=Decimal('0.00'),
            percentual_cambagem=Decimal('4.00'),
            percentual_avanco_cumulativo=Decimal('12.00'),
        )
        tank_2 = RdoTanque.objects.create(
            rdo=rdo_2,
            tanque_codigo='TQ-PLAN',
            numero_compartimentos=6,
            ensacamento_prev=40,
            icamento_prev=20,
            cambagem_prev=10,
            limpeza_mecanizada_cumulativa=Decimal('32.00'),
            limpeza_fina_cumulativa=Decimal('2.00'),
            percentual_ensacamento=Decimal('18.00'),
            percentual_icamento=Decimal('10.00'),
            percentual_cambagem=Decimal('12.00'),
            percentual_avanco_cumulativo=Decimal('40.00'),
        )
        tank_3 = RdoTanque.objects.create(
            rdo=rdo_3,
            tanque_codigo='TQ-PLAN',
            numero_compartimentos=6,
            previsao_termino=date(2026, 3, 18),
            ensacamento_prev=40,
            icamento_prev=20,
            cambagem_prev=10,
            limpeza_mecanizada_cumulativa=Decimal('68.00'),
            limpeza_fina_cumulativa=Decimal('24.00'),
            percentual_ensacamento=Decimal('55.00'),
            percentual_icamento=Decimal('40.00'),
            percentual_cambagem=Decimal('28.00'),
            percentual_avanco_cumulativo=Decimal('78.00'),
        )
        RdoTanque.objects.filter(pk=tank_1.pk).update(
            ensacamento_prev=40,
            icamento_prev=20,
            cambagem_prev=10,
            limpeza_mecanizada_cumulativa=Decimal('10.00'),
            limpeza_fina_cumulativa=Decimal('0.00'),
            percentual_ensacamento=Decimal('5.00'),
            percentual_icamento=Decimal('0.00'),
            percentual_cambagem=Decimal('4.00'),
            percentual_avanco_cumulativo=Decimal('12.00'),
        )
        RdoTanque.objects.filter(pk=tank_2.pk).update(
            ensacamento_prev=40,
            icamento_prev=20,
            cambagem_prev=10,
            limpeza_mecanizada_cumulativa=Decimal('32.00'),
            limpeza_fina_cumulativa=Decimal('2.00'),
            percentual_ensacamento=Decimal('18.00'),
            percentual_icamento=Decimal('10.00'),
            percentual_cambagem=Decimal('12.00'),
            percentual_avanco_cumulativo=Decimal('40.00'),
        )
        RdoTanque.objects.filter(pk=tank_3.pk).update(
            previsao_termino=date(2026, 3, 18),
            ensacamento_prev=40,
            icamento_prev=20,
            cambagem_prev=10,
            limpeza_mecanizada_cumulativa=Decimal('68.00'),
            limpeza_fina_cumulativa=Decimal('24.00'),
            percentual_ensacamento=Decimal('55.00'),
            percentual_icamento=Decimal('40.00'),
            percentual_cambagem=Decimal('28.00'),
            percentual_avanco_cumulativo=Decimal('78.00'),
        )

        request = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
            'tanque': 'TQ-PLAN',
        })
        response = report_diario_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])

        comp = payload['comparativo_avanco']
        self.assertEqual(comp['labels'], ['10/03', '11/03', '12/03', '13/03', '14/03', '15/03', '16/03', '17/03', '18/03'])
        self.assertEqual(comp['realizado_acumulado'], [12.6, 12.6, 30.1, 30.1, 62.1, None, None, None, None])
        self.assertEqual(comp['realizado_diario'], [12.6, 0.0, 17.5, 0.0, 32.0, None, None, None, None])
        self.assertEqual(comp['programado_acumulado'][-1], 100.0)
        self.assertAlmostEqual(sum(comp['programado_diario']), 100.0, places=1)
        self.assertEqual(comp['programado_diario'][0], 5.0)
        self.assertLess(comp['programado_acumulado'][comp['labels'].index('14/03')], 100.0)
        self.assertTrue(all(
            current <= nxt
            for current, nxt in zip(comp['programado_acumulado'], comp['programado_acumulado'][1:])
        ))
        non_zero_programado = [round(value, 1) for value in comp['programado_diario'] if value > 0]
        self.assertGreater(len(set(non_zero_programado)), 1)
        self.assertTrue(all(value > 0 for value in comp['programado_diario']))

    def test_report_diario_data_distribui_setup_em_dois_dias_no_comparativo(self):
        self.os_obj.data_inicio_frente = date(2026, 3, 10)
        self.os_obj.data_fim_frente = date(2026, 3, 14)
        self.os_obj.save(update_fields=['data_inicio_frente', 'data_fim_frente', 'dias_de_operacao_frente'])

        rdo_1 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-SETUP-1',
            data=date(2026, 3, 10),
        )
        rdo_2 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-SETUP-2',
            data=date(2026, 3, 12),
        )
        rdo_3 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-SETUP-3',
            data=date(2026, 3, 14),
        )

        RDOAtividade.objects.create(
            rdo=rdo_1,
            atividade='Instalação / Preparação / Montagem / Setup ',
        )
        RDOAtividade.objects.create(
            rdo=rdo_2,
            atividade='Instalação / Preparação / Montagem / Setup ',
        )

        tank_payloads = [
            (
                rdo_1,
                {
                    'tanque_codigo': 'TQ-SETUP',
                    'numero_compartimentos': 6,
                    'ensacamento_prev': 40,
                    'icamento_prev': 20,
                    'cambagem_prev': 10,
                    'limpeza_mecanizada_cumulativa': Decimal('10.00'),
                    'limpeza_fina_cumulativa': Decimal('0.00'),
                    'percentual_ensacamento': Decimal('5.00'),
                    'percentual_icamento': Decimal('0.00'),
                    'percentual_cambagem': Decimal('4.00'),
                    'percentual_avanco_cumulativo': Decimal('12.00'),
                },
            ),
            (
                rdo_2,
                {
                    'tanque_codigo': 'TQ-SETUP',
                    'numero_compartimentos': 6,
                    'ensacamento_prev': 40,
                    'icamento_prev': 20,
                    'cambagem_prev': 10,
                    'limpeza_mecanizada_cumulativa': Decimal('32.00'),
                    'limpeza_fina_cumulativa': Decimal('2.00'),
                    'percentual_ensacamento': Decimal('18.00'),
                    'percentual_icamento': Decimal('10.00'),
                    'percentual_cambagem': Decimal('12.00'),
                    'percentual_avanco_cumulativo': Decimal('40.00'),
                },
            ),
            (
                rdo_3,
                {
                    'tanque_codigo': 'TQ-SETUP',
                    'numero_compartimentos': 6,
                    'previsao_termino': date(2026, 3, 18),
                    'ensacamento_prev': 40,
                    'icamento_prev': 20,
                    'cambagem_prev': 10,
                    'limpeza_mecanizada_cumulativa': Decimal('68.00'),
                    'limpeza_fina_cumulativa': Decimal('24.00'),
                    'percentual_ensacamento': Decimal('55.00'),
                    'percentual_icamento': Decimal('40.00'),
                    'percentual_cambagem': Decimal('28.00'),
                    'percentual_avanco_cumulativo': Decimal('78.00'),
                },
            ),
        ]
        for rdo, kwargs in tank_payloads:
            tank = RdoTanque.objects.create(rdo=rdo, **kwargs)
            RdoTanque.objects.filter(pk=tank.pk).update(**kwargs)

        request = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
            'tanque': 'TQ-SETUP',
        })
        response = report_diario_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])

        comp = payload['comparativo_avanco']
        self.assertEqual(comp['programado_diario'][0], 5.0)
        self.assertEqual(comp['programado_acumulado'][0], 5.0)
        self.assertEqual(comp['realizado_acumulado'], [12.6, 12.6, 30.1, 30.1, 62.1, None, None, None, None])
        self.assertEqual(comp['realizado_diario'], [12.6, 0.0, 17.5, 0.0, 32.0, None, None, None, None])

    def test_report_diario_data_comparativo_inicia_no_primeiro_rdo(self):
        self.os_obj.data_inicio_frente = date(2026, 3, 8)
        self.os_obj.data_fim_frente = date(2026, 3, 14)
        self.os_obj.save(update_fields=['data_inicio_frente', 'data_fim_frente', 'dias_de_operacao_frente'])

        rdo_1 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-FIRST-1',
            data=date(2026, 3, 10),
        )
        rdo_2 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-FIRST-2',
            data=date(2026, 3, 12),
        )

        RDOAtividade.objects.create(
            rdo=rdo_1,
            atividade='Instalação / Preparação / Montagem / Setup ',
        )
        RdoTanque.objects.create(
            rdo=rdo_1,
            tanque_codigo='TQ-FIRST',
            numero_compartimentos=6,
            previsao_termino=date(2026, 3, 18),
            limpeza_mecanizada_cumulativa=Decimal('10.00'),
            percentual_ensacamento=Decimal('5.00'),
            percentual_cambagem=Decimal('4.00'),
            percentual_avanco_cumulativo=Decimal('12.00'),
        )
        RdoTanque.objects.create(
            rdo=rdo_2,
            tanque_codigo='TQ-FIRST',
            numero_compartimentos=6,
            previsao_termino=date(2026, 3, 18),
            limpeza_mecanizada_cumulativa=Decimal('20.00'),
            percentual_ensacamento=Decimal('10.00'),
            percentual_cambagem=Decimal('6.00'),
            percentual_avanco_cumulativo=Decimal('24.00'),
        )

        request = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
            'tanque': 'TQ-FIRST',
        })
        response = report_diario_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['comparativo_avanco']['labels'][0], '10/03')

    def test_report_diario_data_programado_para_na_previsao_termino(self):
        self.os_obj.data_inicio_frente = date(2026, 3, 10)
        self.os_obj.data_fim_frente = date(2026, 3, 14)
        self.os_obj.save(update_fields=['data_inicio_frente', 'data_fim_frente', 'dias_de_operacao_frente'])

        rdo_1 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-END-1',
            data=date(2026, 3, 10),
        )
        rdo_2 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-END-2',
            data=date(2026, 3, 20),
        )

        RDOAtividade.objects.create(
            rdo=rdo_1,
            atividade='Instalação / Preparação / Montagem / Setup ',
        )
        RdoTanque.objects.create(
            rdo=rdo_1,
            tanque_codigo='TQ-END',
            numero_compartimentos=6,
            previsao_termino=date(2026, 3, 18),
            limpeza_mecanizada_cumulativa=Decimal('10.00'),
            percentual_ensacamento=Decimal('5.00'),
            percentual_cambagem=Decimal('4.00'),
            percentual_avanco_cumulativo=Decimal('12.00'),
        )
        RdoTanque.objects.create(
            rdo=rdo_2,
            tanque_codigo='TQ-END',
            numero_compartimentos=6,
            previsao_termino=date(2026, 3, 18),
            limpeza_mecanizada_cumulativa=Decimal('40.00'),
            percentual_ensacamento=Decimal('20.00'),
            percentual_cambagem=Decimal('12.00'),
            percentual_avanco_cumulativo=Decimal('50.00'),
        )

        request = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
            'tanque': 'TQ-END',
        })
        response = report_diario_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])

        comp = payload['comparativo_avanco']
        idx_previsao = comp['labels'].index('18/03')
        idx_pos_previsao = comp['labels'].index('19/03')
        self.assertEqual(comp['programado_acumulado'][idx_previsao], 100.0)
        self.assertIsNone(comp['programado_acumulado'][idx_pos_previsao])
        self.assertIsNone(comp['programado_diario'][idx_pos_previsao])

    def test_report_diario_data_programado_dez_dias_segues_escada_planejada(self):
        self.os_obj.data_inicio_frente = date(2026, 3, 10)
        self.os_obj.data_fim_frente = date(2026, 3, 19)
        self.os_obj.save(update_fields=['data_inicio_frente', 'data_fim_frente', 'dias_de_operacao_frente'])

        rdo_1 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-STEP-1',
            data=date(2026, 3, 10),
        )
        RDOAtividade.objects.create(
            rdo=rdo_1,
            atividade='Instalação / Preparação / Montagem / Setup ',
        )
        RdoTanque.objects.create(
            rdo=rdo_1,
            tanque_codigo='TQ-STEP',
            numero_compartimentos=6,
            previsao_termino=date(2026, 3, 19),
            limpeza_mecanizada_cumulativa=Decimal('10.00'),
            percentual_ensacamento=Decimal('5.00'),
            percentual_cambagem=Decimal('4.00'),
            percentual_avanco_cumulativo=Decimal('12.00'),
        )

        request = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
            'tanque': 'TQ-STEP',
        })
        response = report_diario_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])

        comp = payload['comparativo_avanco']
        self.assertEqual(comp['labels'], ['10/03', '11/03', '12/03', '13/03', '14/03', '15/03', '16/03', '17/03', '18/03', '19/03'])
        self.assertEqual(comp['programado_diario'], [5.0, 5.0, 10.0, 10.0, 15.0, 15.0, 15.0, 10.0, 10.0, 5.0])
        self.assertEqual(comp['programado_acumulado'], [5.0, 10.0, 20.0, 30.0, 45.0, 60.0, 75.0, 85.0, 95.0, 100.0])

    def test_report_diario_data_calcula_tempo_drenagem_por_atividade(self):
        rdo_1 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-DREN-1',
            data=date(2026, 3, 10),
        )
        rdo_2 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-DREN-2',
            data=date(2026, 3, 11),
        )
        rdo_3 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-DREN-3',
            data=date(2026, 3, 12),
        )

        RDOAtividade.objects.create(
            rdo=rdo_1,
            ordem=1,
            atividade='Drenagem inicial do tanque ',
            inicio=time(8, 0),
            fim=time(9, 30),
        )
        RDOAtividade.objects.create(
            rdo=rdo_1,
            ordem=2,
            atividade='DDS',
            inicio=time(10, 0),
            fim=time(10, 15),
        )
        RDOAtividade.objects.create(
            rdo=rdo_2,
            ordem=1,
            atividade='Acesso ao tanque',
            inicio=time(7, 0),
            fim=time(8, 0),
        )
        RDOAtividade.objects.create(
            rdo=rdo_3,
            ordem=1,
            atividade='Drenagem do tanque',
            inicio=time(7, 0),
            fim=time(7, 45),
        )
        RDOAtividade.objects.create(
            rdo=rdo_3,
            ordem=2,
            atividade='Drenagem do tanque',
            inicio=time(8, 0),
            fim=time(8, 30),
        )

        request = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
        })
        response = report_diario_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['tempo_drenagem']['labels'], ['10/03', '11/03', '12/03'])
        self.assertEqual(payload['tempo_drenagem']['minutos'], [90, 0, 75])
        self.assertEqual(payload['tempo_drenagem']['total_minutos'], 165)

    def test_report_diario_data_calcula_tempo_setup_por_atividade(self):
        rdo_1 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-SETUP-1',
            data=date(2026, 3, 10),
        )
        rdo_2 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-SETUP-2',
            data=date(2026, 3, 11),
        )
        rdo_3 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-SETUP-3',
            data=date(2026, 3, 12),
        )

        RDOAtividade.objects.create(
            rdo=rdo_1,
            ordem=1,
            atividade='instalação/preparação/montagem',
            inicio=time(8, 0),
            fim=time(13, 0),
        )
        RDOAtividade.objects.create(
            rdo=rdo_1,
            ordem=2,
            atividade='DDS',
            inicio=time(13, 30),
            fim=time(14, 0),
        )
        RDOAtividade.objects.create(
            rdo=rdo_2,
            ordem=1,
            atividade='Instalação / Preparação / Montagem / Setup ',
            inicio=time(6, 0),
            fim=time(7, 0),
        )
        RDOAtividade.objects.create(
            rdo=rdo_3,
            ordem=1,
            atividade='Acesso ao tanque',
            inicio=time(6, 0),
            fim=time(10, 0),
        )

        request = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
        })
        response = report_diario_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['tempo_setup']['labels'], ['10/03', '11/03', '12/03'])
        self.assertEqual(payload['tempo_setup']['minutos'], [300, 60, 0])
        self.assertEqual(payload['tempo_setup']['total_minutos'], 360)

    def test_report_diario_data_agrupa_horas_nao_efetivas_por_atividade(self):
        rdo_1 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-NEF-1',
            data=date(2026, 3, 10),
        )
        rdo_2 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-NEF-2',
            data=date(2026, 3, 11),
        )
        rdo_3 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-NEF-3',
            data=date(2026, 3, 12),
        )

        RDOAtividade.objects.create(
            rdo=rdo_1,
            ordem=1,
            atividade='conferência do material e equipamento no container',
            inicio=time(8, 0),
            fim=time(12, 0),
        )
        RDOAtividade.objects.create(
            rdo=rdo_1,
            ordem=2,
            atividade='instalação/preparação/montagem',
            inicio=time(13, 0),
            fim=time(17, 0),
        )
        RDOAtividade.objects.create(
            rdo=rdo_2,
            ordem=1,
            atividade='Instalação / Preparação / Montagem / Setup ',
            inicio=time(5, 0),
            fim=time(6, 0),
        )
        RDOAtividade.objects.create(
            rdo=rdo_2,
            ordem=2,
            atividade='aferição de pressão arterial',
            inicio=time(6, 0),
            fim=time(7, 0),
        )
        RDOAtividade.objects.create(
            rdo=rdo_2,
            ordem=3,
            atividade='almoço',
            inicio=time(12, 0),
            fim=time(13, 0),
        )
        RDOAtividade.objects.create(
            rdo=rdo_3,
            ordem=1,
            atividade='acesso ao tanque',
            inicio=time(6, 0),
            fim=time(10, 0),
        )

        request = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
        })
        response = report_diario_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['horas_nao_efetivas']['labels'], ['10/03', '11/03'])
        self.assertEqual(payload['horas_nao_efetivas']['total_minutos'], 600)

        series = {
            item['label']: item
            for item in payload['horas_nao_efetivas']['series']
        }
        self.assertEqual(sorted(series.keys()), ['AFERIÇÃO PRESSÃO', 'OFFLOADING', 'SETUP'])
        self.assertEqual(series['OFFLOADING']['minutos'], [240, 0])
        self.assertEqual(series['OFFLOADING']['total_minutos'], 240)
        self.assertEqual(series['SETUP']['minutos'], [240, 60])
        self.assertEqual(series['SETUP']['total_minutos'], 300)
        self.assertEqual(series['AFERIÇÃO PRESSÃO']['minutos'], [0, 60])
        self.assertEqual(series['AFERIÇÃO PRESSÃO']['total_minutos'], 60)

    def test_report_diario_data_lista_anotacoes_e_observacoes_por_data(self):
        RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-NOTE-1',
            data=date(2026, 3, 10),
            observacoes_rdo_pt='Primeira observação do RDO.',
        )
        RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-NOTE-2',
            data=date(2026, 3, 11),
            observacoes_rdo_pt='Comentário consolidado do dia.',
        )
        RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-NOTE-3',
            data=date(2026, 3, 12),
        )

        request = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
        })
        response = report_diario_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['anotacoes_observacoes'], [
            {'data': '10/03/2026', 'observacao': 'Primeira observação do RDO.'},
            {'data': '11/03/2026', 'observacao': 'Comentário consolidado do dia.'},
            {'data': '12/03/2026', 'observacao': ''},
        ])

    def test_os_tanques_data_exige_selecao_quando_ha_multiplos_tanques(self):
        rdo_curr = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-TANQUES-MULTI',
            data=date(2026, 3, 14),
        )
        RdoTanque.objects.create(rdo=rdo_curr, tanque_codigo='TQ-10')
        RdoTanque.objects.create(rdo=rdo_curr, tanque_codigo='TQ-11')

        request = self.factory.get('/api/os-tanques/data/', {
            'os_id': self.os_obj.id,
        })
        response = os_tanques_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['tanques_disponiveis'], ['TQ-10', 'TQ-11'])
        self.assertEqual(payload['total_tanques'], 2)
        self.assertTrue(payload['requires_tank_selection'])
        self.assertEqual(payload['auto_selected_tank'], '')

    def test_os_tanques_data_auto_define_tanque_unico(self):
        rdo_curr = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-TANQUE-UNICO',
            data=date(2026, 3, 15),
        )
        RdoTanque.objects.create(rdo=rdo_curr, tanque_codigo='TQ-UNICO')

        request = self.factory.get('/api/os-tanques/data/', {
            'os_id': self.os_obj.id,
        })
        response = os_tanques_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['tanques_disponiveis'], ['TQ-UNICO'])
        self.assertEqual(payload['total_tanques'], 1)
        self.assertFalse(payload['requires_tank_selection'])
        self.assertEqual(payload['auto_selected_tank'], 'TQ-UNICO')
