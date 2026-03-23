import json
from datetime import date, time, timedelta
from decimal import Decimal
from unittest.mock import patch

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

    def test_os_tanques_data_consolida_os_irmas_e_tanques_declarados(self):
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
        self.assertEqual(payload['tanques_disponiveis'], ['COT-5s', 'HFO OVERFLOW TANK'])
        self.assertEqual(payload['total_tanques'], 2)
        self.assertTrue(payload['requires_tank_selection'])
        self.assertEqual(payload['auto_selected_tank'], '')

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
        self.assertEqual(payload['produtividade_media_diaria']['ultimo_percentual'], 14.0)
        self.assertEqual(payload['produtividade_media_diaria']['dias_considerados'], 2)
        self.assertEqual(payload['produtividade_media_diaria']['total_avanco_diario'], 26.0)
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

        class _FixedDate(date):
            @classmethod
            def today(cls):
                return cls(2026, 3, 23)

        request = self.factory.get('/api/report-diario/data/', {
            'os_id': self.os_obj.id,
            'tanque': 'TQ-PROD-AND',
        })
        with patch('GO.views_dashboard_rdo.datetime.date', _FixedDate):
            response = report_diario_data(request)

        self.assertEqual(response.status_code, 200)
        payload = self._parse_response(response)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['produtividade_media_diaria']['dias_considerados'], 6)
        self.assertEqual(payload['produtividade_media_diaria']['total_avanco_diario'], 26.0)
        self.assertEqual(payload['produtividade_media_diaria']['media_percentual'], 4.3)

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
