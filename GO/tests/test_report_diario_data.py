import json
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from GO.models import Cliente, OrdemServico, RDO, RDOAtividade, RdoTanque, Unidade
from GO.views_dashboard_rdo import get_ordens_servico, os_tanques_data, report_diario_data


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
        self.assertEqual(payload['compartimentos_avanco_cumulado']['2']['avanco'], 61.8)
        self.assertEqual(payload['compartimentos_avanco_cumulado']['2']['sujidade'], 38.2)
        self.assertEqual(payload['tanque_3d']['total_compartimentos'], 7)
        self.assertEqual(payload['tanque_3d']['total_percent'], 19.03)
        self.assertTrue(payload['tanque_3d']['available'])
        self.assertEqual(payload['tanque_3d']['source_kind'], 'rdo')
        self.assertEqual(payload['tanque_3d']['chart']['key'], 'avanco')
        self.assertEqual(len(payload['tanque_3d']['charts']), 1)
        self.assertEqual(payload['tanque_3d']['charts'][0]['key'], 'avanco')
        self.assertEqual(payload['tanque_3d']['charts'][0]['items'][0]['value'], 63.8)
        self.assertEqual(payload['tanque_3d']['charts'][0]['items'][1]['value'], 61.8)
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

    def test_report_diario_data_tanque_3d_usa_sentido_do_ultimo_rdo_do_tanque(self):
        rdo_base = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-SENTIDO-BASE',
            data=date(2026, 3, 10),
        )
        rdo_latest_tank = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-SENTIDO-TQ',
            data=date(2026, 3, 11),
        )
        RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-SENTIDO-OUTRO',
            data=date(2026, 3, 12),
        )

        RdoTanque.objects.create(
            rdo=rdo_base,
            tanque_codigo='TQ-SENTIDO',
            numero_compartimentos=2,
            sentido_limpeza=RdoTanque.SENTIDO_VANTE_RE,
            compartimentos_avanco_json=json.dumps({
                '1': {'mecanizada': 40, 'fina': 0},
                '2': {'mecanizada': 20, 'fina': 0},
            }, ensure_ascii=False),
        )
        RdoTanque.objects.create(
            rdo=rdo_latest_tank,
            tanque_codigo='TQ-SENTIDO',
            numero_compartimentos=2,
            sentido_limpeza=RdoTanque.SENTIDO_BOMBORDO_BORESTE,
        )

        request = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
            'tanque': 'TQ-SENTIDO',
        })
        response = report_diario_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['tanque_3d']['sentido_inicio'], 'Bombordo')
        self.assertEqual(payload['tanque_3d']['sentido_fim'], 'Boreste')

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

    def test_report_diario_data_expoe_setup_na_producao(self):
        rdo_1 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-SETUP-PROD-1',
            data=date(2026, 3, 10),
        )
        rdo_2 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-SETUP-PROD-2',
            data=date(2026, 3, 11),
        )

        RdoTanque.objects.create(
            rdo=rdo_1,
            tanque_codigo='TQ-OUTRO',
            percentual_avanco_cumulativo=Decimal('5.00'),
        )
        RdoTanque.objects.create(
            rdo=rdo_2,
            tanque_codigo='TQ-SETUP',
            percentual_avanco_cumulativo=Decimal('12.00'),
        )

        RDOAtividade.objects.create(
            rdo=rdo_1,
            ordem=1,
            atividade='Instalação / Preparação / Montagem / Setup ',
            inicio=time(7, 0),
            fim=time(8, 30),
        )

        request = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
            'tanque': 'TQ-SETUP',
        })
        response = report_diario_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['producao']['setup'], 100.0)

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
            fim=time(10, 0),
        )
        RDOAtividade.objects.create(
            rdo=rdo_1,
            ordem=2,
            atividade='offloading',
            inicio=time(10, 0),
            fim=time(12, 0),
        )
        RDOAtividade.objects.create(
            rdo=rdo_1,
            ordem=3,
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
        self.assertEqual(payload['horas_nao_efetivas']['labels'], [
            'OFFLOADING',
            'SETUP',
            'AFERIÇÃO PRESSÃO / DDS / INSTR. SEG.',
        ])
        self.assertEqual(payload['horas_nao_efetivas']['total_minutos'], 480)

        items = {
            item['label']: item
            for item in payload['horas_nao_efetivas']['items']
        }
        self.assertEqual(sorted(items.keys()), ['AFERIÇÃO PRESSÃO / DDS / INSTR. SEG.', 'OFFLOADING', 'SETUP'])
        self.assertEqual(items['OFFLOADING']['total_minutos'], 120)
        self.assertEqual(items['SETUP']['total_minutos'], 300)
        self.assertEqual(items['AFERIÇÃO PRESSÃO / DDS / INSTR. SEG.']['total_minutos'], 60)

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

    def test_os_tanques_data_consolida_os_irmas_e_ignora_tanques_apenas_declarados(self):
        os_sibling = OrdemServico.objects.create(
            numero_os=self.os_obj.numero_os,
            data_inicio=date(2026, 3, 16),
            data_fim=None,
            dias_de_operacao=0,
            servico='COLETA DE AR',
            servicos='COLETA DE AR',
            metodo='Manual',
            pob=1,
            tanque='',
            tanques='5S, HFO OVERFLOW TANK',
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
        rdo_curr = RDO.objects.create(
            ordem_servico=os_sibling,
            rdo='RDO-TANQUE-SCOPE',
            data=date(2026, 3, 16),
        )
        RdoTanque.objects.create(rdo=rdo_curr, tanque_codigo='COT-5s', nome_tanque='COT-5s')

        request = self.factory.get('/api/os-tanques/data/', {
            'os_id': self.os_obj.id,
        })
        response = os_tanques_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['tanques_disponiveis'], ['COT-5s'])
        self.assertEqual(payload['total_tanques'], 1)
        self.assertFalse(payload['requires_tank_selection'])
        self.assertEqual(payload['auto_selected_tank'], 'COT-5s')

    def test_os_tanques_data_deduplica_alias_com_zero_a_esquerda(self):
        self.os_obj.tanques = '3P COT'
        self.os_obj.save(update_fields=['tanques'])

        rdo_curr = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-TANQUE-03P',
            data=date(2026, 3, 17),
        )
        RdoTanque.objects.create(
            rdo=rdo_curr,
            tanque_codigo='03P COT',
            nome_tanque='03P COT',
        )

        request = self.factory.get('/api/os-tanques/data/', {
            'os_id': self.os_obj.id,
        })
        response = os_tanques_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['tanques_disponiveis'], ['03P COT'])
        self.assertEqual(payload['total_tanques'], 1)
        self.assertFalse(payload['requires_tank_selection'])
        self.assertEqual(payload['auto_selected_tank'], '03P COT')

    def test_report_diario_data_filtra_alias_de_tanque_equivalente(self):
        self.os_obj.tanques = '3P COT'
        self.os_obj.save(update_fields=['tanques'])

        rdo_curr = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-TANQUE-ALIAS',
            data=date(2026, 3, 17),
        )
        RdoTanque.objects.create(
            rdo=rdo_curr,
            tanque_codigo='03P COT',
            nome_tanque='03P COT',
            numero_compartimentos=1,
            sentido_limpeza=RdoTanque.SENTIDO_VANTE_RE,
            limpeza_mecanizada_cumulativa=Decimal('25.00'),
            percentual_avanco_cumulativo=Decimal('25.00'),
        )

        request = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
            'tanque': '3P COT',
        })
        response = report_diario_data(request)
        request_canonical = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
            'tanque': '03P COT',
        })
        response_canonical = report_diario_data(request_canonical)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_canonical.status_code, 200)
        payload = self._parse_response(response)
        canonical_payload = self._parse_response(response_canonical)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['tanques_disponiveis'], ['03P COT'])
        self.assertEqual(canonical_payload['tanques_disponiveis'], ['03P COT'])
        self.assertEqual(payload['curva_s']['labels'], ['17/03'])
        self.assertEqual(payload['curva_s'], canonical_payload['curva_s'])
        self.assertEqual(payload['tanque_3d']['available'], canonical_payload['tanque_3d']['available'])
        self.assertEqual(payload['tanque_3d']['total_compartimentos'], canonical_payload['tanque_3d']['total_compartimentos'])
        self.assertEqual(payload['tanque_3d']['compartimentos'], canonical_payload['tanque_3d']['compartimentos'])

    def test_report_diario_data_consolida_rdos_de_os_irmas(self):
        os_sibling = OrdemServico.objects.create(
            numero_os=self.os_obj.numero_os,
            data_inicio=date(2026, 3, 16),
            data_fim=None,
            dias_de_operacao=0,
            servico='COLETA DE AR',
            servicos='COLETA DE AR',
            metodo='Manual',
            pob=1,
            tanque='',
            tanques='TQ-SCOPE',
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
        rdo_curr = RDO.objects.create(
            ordem_servico=os_sibling,
            rdo='RDO-ESCOPO-IRMA',
            data=date(2026, 3, 16),
        )
        RdoTanque.objects.create(
            rdo=rdo_curr,
            tanque_codigo='TQ-SCOPE',
            nome_tanque='TQ-SCOPE',
            numero_compartimentos=3,
            sentido_limpeza=RdoTanque.SENTIDO_VANTE_RE,
            limpeza_mecanizada_cumulativa=Decimal('40.00'),
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
        self.assertEqual(payload['tanques_disponiveis'], ['TQ-SCOPE'])
        self.assertEqual(payload['info_os']['tanque'], 'TQ-SCOPE')
        self.assertEqual(payload['curva_s']['labels'], ['16/03'])
        self.assertTrue(payload['tanque_3d']['available'])
        self.assertFalse(payload['tanque_3d']['requires_specific_tank'])

    def test_report_diario_data_mantem_producao_com_ultimo_percentual_valido(self):
        rdo_prev = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-PCT-VALIDO-1',
            data=date(2026, 3, 18),
        )
        rdo_curr = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-PCT-VALIDO-2',
            data=date(2026, 3, 19),
        )
        RdoTanque.objects.create(
            rdo=rdo_prev,
            tanque_codigo='TQ-PCT',
            nome_tanque='TQ-PCT',
            numero_compartimentos=1,
            percentual_ensacamento=Decimal('20.00'),
            percentual_avanco_cumulativo=Decimal('1.40'),
        )
        RdoTanque.objects.create(
            rdo=rdo_curr,
            tanque_codigo='TQ-PCT',
            nome_tanque='TQ-PCT',
            numero_compartimentos=1,
            percentual_ensacamento=Decimal('0.00'),
            percentual_avanco_cumulativo=Decimal('0.00'),
        )

        request = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
        })
        response = report_diario_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['tanques_disponiveis'], ['TQ-PCT'])
        self.assertEqual(payload['curva_s']['totais']['ensacamento'], 20.0)
        self.assertEqual(payload['producao']['ensacamento'], 20.0)
        self.assertEqual(payload['producao']['avanco_total'], 1.4)

    def test_report_diario_data_trava_curva_s_acumulada_para_nao_regredir(self):
        rdo_1 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-CURVA-MONO-1',
            data=date(2026, 3, 18),
        )
        rdo_2 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-CURVA-MONO-2',
            data=date(2026, 3, 19),
        )

        tank_1 = RdoTanque.objects.create(
            rdo=rdo_1,
            tanque_codigo='TQ-MONO',
            numero_compartimentos=1,
        )
        tank_2 = RdoTanque.objects.create(
            rdo=rdo_2,
            tanque_codigo='TQ-MONO',
            numero_compartimentos=1,
        )
        RdoTanque.objects.filter(pk=tank_1.pk).update(
            limpeza_mecanizada_cumulativa=Decimal('20.00'),
            percentual_limpeza_cumulativo=Decimal('20.00'),
            percentual_avanco_cumulativo=Decimal('14.00'),
        )
        RdoTanque.objects.filter(pk=tank_2.pk).update(
            limpeza_mecanizada_cumulativa=Decimal('10.00'),
            percentual_limpeza_cumulativo=Decimal('10.00'),
            percentual_avanco_cumulativo=Decimal('7.00'),
        )

        request = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
            'tanque': 'TQ-MONO',
        })
        response = report_diario_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['curva_s']['labels'], ['18/03', '19/03'])
        self.assertEqual(payload['curva_s']['raspagem_acumulada'], [20.0, 20.0])
        self.assertEqual(payload['curva_s']['avanco_acumulado'], [14.0, 14.0])
        self.assertEqual(payload['curva_s']['avanco_diario'], [14.0, 0.0])

    def test_report_diario_data_faz_fallback_por_campo_de_rdotanque_para_rdo(self):
        rdo_curr = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-FALLBACK-CAMPO',
            data=date(2026, 3, 20),
        )
        rdo_curr.percentual_ensacamento = Decimal('35.00')
        rdo_curr.ensacamento = 180
        rdo_curr.ensacamento_cumulativo = 180
        rdo_curr.numero_compartimentos = 6
        rdo_curr.gavetas = 24
        rdo_curr.save(
            update_fields=[
                'percentual_ensacamento',
                'ensacamento',
                'ensacamento_cumulativo',
                'numero_compartimentos',
                'gavetas',
            ]
        )

        tank = RdoTanque.objects.create(
            rdo=rdo_curr,
            tanque_codigo='TQ-FALLBACK',
            nome_tanque='TQ-FALLBACK',
            numero_compartimentos=1,
            sentido_limpeza=RdoTanque.SENTIDO_VANTE_RE,
            limpeza_mecanizada_cumulativa=Decimal('42.00'),
            percentual_avanco_cumulativo=Decimal('29.40'),
            percentual_ensacamento=None,
            ensacamento_cumulativo=None,
            compartimentos_avanco_json=json.dumps({
                '1': {'mecanizada': 42, 'fina': 0},
            }, ensure_ascii=False),
            gavetas=None,
        )
        RdoTanque.objects.filter(pk=tank.pk).update(
            percentual_ensacamento=None,
            ensacamento_cumulativo=None,
            ensacamento_dia=None,
            numero_compartimentos=None,
            gavetas=None,
        )

        request = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
        })
        response = report_diario_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['tanques_disponiveis'], ['TQ-FALLBACK'])
        self.assertEqual(payload['info_os']['tanque'], 'TQ-FALLBACK')
        self.assertEqual(payload['producao']['raspagem'], 42.0)
        self.assertEqual(payload['curva_s']['raspagem_acumulada'], [42.0])
        self.assertEqual(payload['producao']['ensacamento'], 35.0)
        self.assertEqual(payload['curva_s']['ensacamento_acumulado'], [35.0])
        self.assertEqual(payload['kpi']['sacos'], 180)
        self.assertEqual(payload['kpi']['compartimentos'], 6)
        self.assertEqual(payload['kpi']['gavetas'], 24)

    def test_get_ordens_servico_lista_os_duplicadas_com_rotulos_distintos(self):
        os_repetida = OrdemServico.objects.create(
            numero_os=self.os_obj.numero_os,
            data_inicio=date(2026, 3, 16),
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
        RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-LISTA-1',
            data=date(2026, 3, 10),
        )
        RDO.objects.create(
            ordem_servico=os_repetida,
            rdo='RDO-LISTA-2',
            data=date(2026, 3, 16),
        )

        request = self.factory.get('/api/ordens-servico/')
        response = get_ordens_servico(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])

        itens_os = [item for item in payload['items'] if item['numero_os'] == self.os_obj.numero_os]
        self.assertEqual(len(itens_os), 2)
        self.assertNotEqual(itens_os[0]['id'], itens_os[1]['id'])
        self.assertNotEqual(itens_os[0]['label'], itens_os[1]['label'])

    def test_report_diario_data_retorna_media_produtividade_diaria(self):
        rdo_d1 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-PROD-1',
            data=date(2026, 3, 18),
            entrada_confinado=time(8, 0),
            saida_confinado=time(11, 0),
        )
        rdo_d2 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-PROD-2',
            data=date(2026, 3, 19),
            entrada_confinado=time(8, 0),
            saida_confinado=time(11, 0),
        )
        RDOAtividade.objects.create(
            rdo=rdo_d1,
            ordem=1,
            atividade='Instalação / Preparação / Montagem / Setup ',
            inicio=time(8, 0),
            fim=time(10, 0),
        )
        RDOAtividade.objects.create(
            rdo=rdo_d1,
            ordem=2,
            atividade='limpeza mecânica',
            inicio=time(10, 0),
            fim=time(12, 0),
        )
        RDOAtividade.objects.create(
            rdo=rdo_d1,
            ordem=3,
            atividade='em espera',
            inicio=time(13, 0),
            fim=time(14, 0),
        )
        RDOAtividade.objects.create(
            rdo=rdo_d2,
            ordem=1,
            atividade='Instalação / Preparação / Montagem / Setup ',
            inicio=time(8, 0),
            fim=time(10, 0),
        )
        RDOAtividade.objects.create(
            rdo=rdo_d2,
            ordem=2,
            atividade='limpeza mecânica',
            inicio=time(10, 0),
            fim=time(12, 0),
        )
        RDOAtividade.objects.create(
            rdo=rdo_d2,
            ordem=3,
            atividade='em espera',
            inicio=time(13, 0),
            fim=time(14, 0),
        )
        RdoTanque.objects.create(
            rdo=rdo_d1,
            tanque_codigo='TQ-PROD',
            total_n_efetivo_confinado=60,
            limpeza_mecanizada_cumulativa=Decimal('10.00'),
        )
        RdoTanque.objects.create(
            rdo=rdo_d2,
            tanque_codigo='TQ-PROD',
            total_n_efetivo_confinado=0,
            limpeza_mecanizada_cumulativa=Decimal('30.00'),
        )
        self.os_obj.status_operacao = 'Finalizada'
        self.os_obj.status_geral = 'Finalizada'
        self.os_obj.save(update_fields=['status_operacao', 'status_geral'])

        request = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
            'tanque': 'TQ-PROD',
        })
        response = report_diario_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['produtividade_media_diaria']['media_percentual'], 13.0)
        self.assertEqual(payload['produtividade_media_diaria']['ultimo_percentual'], 5.0)
        self.assertEqual(payload['produtividade_media_diaria']['dias_considerados'], 2)
        self.assertEqual(payload['produtividade_media_diaria']['total_avanco_diario'], 10.0)
        self.assertEqual(payload['produtividade_media_diaria']['avanco_total_real'], 26.0)
        self.assertEqual(payload['produtividade_media_diaria']['hh_efetivo_total_min'], 420)
        self.assertEqual(payload['produtividade_media_diaria']['hh_total_min'], 600)
        self.assertEqual(payload['produtividade_media_diaria']['hh_efetivo_total'], '7:00:00')
        self.assertEqual(payload['produtividade_media_diaria']['hh_total'], '10:00:00')

    def test_report_diario_data_media_produtividade_conta_dias_da_operacao_em_andamento(self):
        rdo_d1 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-PROD-EM-AND-1',
            data=date(2026, 3, 18),
        )
        rdo_d2 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-PROD-EM-AND-2',
            data=date(2026, 3, 19),
        )
        rdo_d3 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-PROD-EM-AND-3',
            data=date(2026, 3, 23),
        )
        RDOAtividade.objects.create(
            rdo=rdo_d1,
            ordem=1,
            atividade='Instalação / Preparação / Montagem / Setup ',
            inicio=time(8, 0),
            fim=time(10, 0),
        )
        RdoTanque.objects.create(
            rdo=rdo_d1,
            tanque_codigo='TQ-PROD-AND',
            limpeza_mecanizada_cumulativa=Decimal('10.00'),
        )
        RdoTanque.objects.create(
            rdo=rdo_d2,
            tanque_codigo='TQ-PROD-AND',
            limpeza_mecanizada_cumulativa=Decimal('30.00'),
        )
        RdoTanque.objects.create(
            rdo=rdo_d3,
            tanque_codigo='TQ-OUTRO',
            limpeza_mecanizada_cumulativa=Decimal('80.00'),
        )

        request = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
            'tanque': 'TQ-PROD-AND',
        })
        response = report_diario_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['produtividade_media_diaria']['dias_considerados'], 2)
        self.assertEqual(payload['produtividade_media_diaria']['total_avanco_diario'], 19.0)
        self.assertEqual(payload['produtividade_media_diaria']['avanco_total_real'], 26.0)
        self.assertEqual(payload['produtividade_media_diaria']['media_percentual'], 13.0)

    def test_report_diario_data_trava_percentuais_acumulados_produtivos_em_100(self):
        rdo_curr = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-PCT-CLAMP',
            data=date(2026, 3, 15),
        )
        RdoTanque.objects.create(
            rdo=rdo_curr,
            tanque_codigo='TQ-CLAMP',
            numero_compartimentos=6,
            percentual_ensacamento=Decimal('780.00'),
            percentual_icamento=Decimal('160.00'),
            percentual_cambagem=Decimal('200.00'),
            percentual_avanco_cumulativo=Decimal('55.00'),
        )

        request = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
            'tanque': 'TQ-CLAMP',
        })
        response = report_diario_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['curva_s']['ensacamento_acumulado'], [100.0])
        self.assertEqual(payload['curva_s']['icamento_acumulado'], [100.0])
        self.assertEqual(payload['curva_s']['cambagem_acumulada'], [100.0])
        self.assertEqual(payload['curva_s']['totais']['ensacamento'], 100.0)
        self.assertEqual(payload['curva_s']['totais']['icamento'], 100.0)
        self.assertEqual(payload['curva_s']['totais']['cambagem'], 100.0)

    def test_report_diario_data_recalcula_produtivos_com_previsao_atual_do_tanque(self):
        rdo_prev = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-PREV-OLD',
            data=date(2026, 3, 23),
        )
        rdo_curr = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-PREV-NEW',
            data=date(2026, 3, 24),
        )

        RdoTanque.objects.create(
            rdo=rdo_prev,
            tanque_codigo='TQ-PREV',
            nome_tanque='TQ-PREV',
            numero_compartimentos=1,
            ensacamento_dia=50,
            ensacamento_prev=50,
            percentual_ensacamento=Decimal('100.00'),
            percentual_avanco_cumulativo=Decimal('7.00'),
        )
        RdoTanque.objects.create(
            rdo=rdo_curr,
            tanque_codigo='TQ-PREV',
            nome_tanque='TQ-PREV',
            numero_compartimentos=1,
            ensacamento_dia=30,
            ensacamento_prev=100,
            percentual_ensacamento=Decimal('100.00'),
            percentual_avanco_cumulativo=Decimal('11.20'),
        )

        request = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
            'tanque': 'TQ-PREV',
        })
        response = report_diario_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['curva_s']['ensacamento_acumulado'], [50.0, 80.0])
        self.assertEqual(payload['curva_s']['totais']['ensacamento'], 80.0)
        self.assertEqual(payload['producao']['ensacamento'], 80.0)

    def test_report_diario_data_programado_tem_curva_mais_proxima_de_s(self):
        rdo_curr = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo='RDO-PROG-S',
            data=date(2026, 3, 10),
        )
        RdoTanque.objects.create(
            rdo=rdo_curr,
            tanque_codigo='TQ-PROG-S',
            previsao_termino=date(2026, 3, 19),
        )

        request = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
            'tanque': 'TQ-PROG-S',
        })
        response = report_diario_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])

        planned_daily = payload['comparativo_avanco']['programado_diario']
        planned_accum = payload['comparativo_avanco']['programado_acumulado']

        self.assertEqual(planned_daily[0], 5.0)
        self.assertEqual(planned_accum[-1], 100.0)
        self.assertTrue(all(
            float(planned_accum[idx]) >= float(planned_accum[idx - 1])
            for idx in range(1, len(planned_accum))
        ))

        middle_idx = len(planned_daily) // 2
        self.assertGreater(planned_daily[middle_idx], planned_daily[1])
        self.assertGreater(planned_daily[middle_idx], planned_daily[-1])
