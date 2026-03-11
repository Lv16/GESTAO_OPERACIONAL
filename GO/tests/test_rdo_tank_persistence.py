from decimal import Decimal
from datetime import timedelta
import json
from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from django.utils import timezone
from GO.models import Cliente, OrdemServico, RDO, RdoTanque, Unidade
from GO.views_rdo import _apply_post_to_rdo, salvar_supervisor, update_rdo_tank_ajax, rdo_detail, rdo_tank_detail

class RdoTankPersistenceTest(TestCase):
    def setUp(self):
        self.user, _ = User.objects.get_or_create(username='test_super', defaults={'is_staff': True, 'is_superuser': True, 'email': 'test@example.com'})
        self.today = timezone.now().date()
        self.rdo = RDO.objects.create(rdo='RDO-TEST', data=self.today)
        self.t1 = RdoTanque.objects.create(rdo=self.rdo, tanque_codigo='T-1')
        self.t2 = RdoTanque.objects.create(rdo=self.rdo, tanque_codigo='T-2')
        self.rf = RequestFactory()

    def test_per_tank_update_persists_and_quantizes(self):
        payload = {
            'tanque_id': str(self.t1.id),
            'limpeza_mecanizada_diaria': '21.216',
            'limpeza_mecanizada_cumulativa': '30',
            'limpeza_fina_diaria': '5.556',
            'limpeza_fina_cumulativa': '3',
            'percentual_limpeza_fina': '9',
            'percentual_limpeza_fina_cumulativo': '3',
            'sup-limp': '21.216',
            'sup-limp-acu': '30',
            'sup-limp-fina': '5.556',
            'sup-limp-fina-acu': '3',
        }
        req = self.rf.post('/fake', json.dumps(payload), content_type='application/json')
        req.user = self.user
        res = _apply_post_to_rdo(req, self.rdo)
        self.t1.refresh_from_db()
        self.assertIsNotNone(self.t1.limpeza_mecanizada_diaria)
        self.assertEqual(self.t1.limpeza_mecanizada_diaria, Decimal('21.22'))
        self.assertEqual(self.t1.limpeza_mecanizada_cumulativa, 30)
        self.assertIsNotNone(self.t1.limpeza_fina_diaria)
        self.assertEqual(self.t1.limpeza_fina_diaria, Decimal('5.56'))
        self.assertEqual(self.t1.percentual_limpeza_fina, 9)
        self.assertEqual(self.t1.percentual_limpeza_fina_cumulativo, 3)

    def test_rdo_level_replication_updates_all_tanks(self):
        payload = {
            'limpeza_mecanizada_diaria': '12.345',
            'limpeza_mecanizada_cumulativa': '44',
            'limpeza_fina_diaria': '2.718',
            'percentual_limpeza_fina': '6',
            'percentual_limpeza_fina_cumulativo': '2',
            'sup-limp': '12.345',
            'sup-limp-acu': '44',
            'sup-limp-fina': '2.718',
        }
        req = self.rf.post('/fake', json.dumps(payload), content_type='application/json')
        req.user = self.user
        res = _apply_post_to_rdo(req, self.rdo)
        self.t1.refresh_from_db()
        self.t2.refresh_from_db()
        self.assertEqual(self.t1.limpeza_mecanizada_diaria, Decimal('12.35'))
        self.assertEqual(self.t2.limpeza_mecanizada_diaria, Decimal('12.35'))
        self.assertEqual(self.t1.limpeza_mecanizada_cumulativa, 44)
        self.assertEqual(self.t2.limpeza_mecanizada_cumulativa, 44)
        self.assertEqual(self.t1.limpeza_fina_diaria, Decimal('2.72'))
        self.assertEqual(self.t2.limpeza_fina_diaria, Decimal('2.72'))
        self.assertEqual(self.t1.percentual_limpeza_fina, 6)
        self.assertEqual(self.t2.percentual_limpeza_fina, 6)
        self.assertEqual(self.t1.percentual_limpeza_fina_cumulativo, 2)
        self.assertEqual(self.t2.percentual_limpeza_fina_cumulativo, 2)

    def test_update_tank_codigo_replica_para_outros_rdos_mesmo_codigo(self):
        # t1 e t2 começam com o mesmo código (simulando o mesmo tanque em snapshots diferentes)
        self.t1.tanque_codigo = '5P'
        self.t2.tanque_codigo = '5P'
        self.t1.save(update_fields=['tanque_codigo'])
        self.t2.save(update_fields=['tanque_codigo'])

        req = self.rf.post('/api/rdo/tank/%s/update/' % self.t1.id, {'tanque_codigo': '5PX'})
        req.user = self.user
        res = update_rdo_tank_ajax(req, self.t1.id)
        self.assertEqual(res.status_code, 200)

        self.t1.refresh_from_db()
        self.t2.refresh_from_db()
        self.assertEqual(self.t1.tanque_codigo, '5PX')
        self.assertEqual(self.t2.tanque_codigo, '5PX')

    def test_update_tank_codigo_rejeita_colisao(self):
        self.t1.tanque_codigo = '5P'
        self.t2.tanque_codigo = '5P'
        self.t1.save(update_fields=['tanque_codigo'])
        self.t2.save(update_fields=['tanque_codigo'])

        # Criar um terceiro tanque no mesmo RDO com o código de destino
        t3 = RdoTanque.objects.create(rdo=self.rdo, tanque_codigo='DEST')

        req = self.rf.post('/api/rdo/tank/%s/update/' % self.t1.id, {'tanque_codigo': 'DEST'})
        req.user = self.user
        res = update_rdo_tank_ajax(req, self.t1.id)
        self.assertEqual(res.status_code, 400)

        self.t1.refresh_from_db()
        self.t2.refresh_from_db()
        t3.refresh_from_db()
        self.assertEqual(self.t1.tanque_codigo, '5P')
        self.assertEqual(self.t2.tanque_codigo, '5P')
        self.assertEqual(t3.tanque_codigo, 'DEST')

    def test_salvar_supervisor_rejeita_compartimento_ja_concluido(self):
        rdo_prev = RDO.objects.create(rdo='RDO-ANT', data=self.today - timedelta(days=1))
        RdoTanque.objects.create(
            rdo=rdo_prev,
            tanque_codigo='T-COMP',
            numero_compartimentos=10,
            compartimentos_avanco_json=json.dumps({'1': {'mecanizada': 100, 'fina': 0}}, ensure_ascii=False),
        )
        tank_atual = RdoTanque.objects.create(
            rdo=self.rdo,
            tanque_codigo='T-COMP',
            numero_compartimentos=10,
        )

        payload = {
            'rdo_id': self.rdo.id,
            'tanque_id': tank_atual.id,
            'numero_compartimentos': 10,
            'compartimento_avanco_mecanizada_1': 5,
            'compartimento_avanco_fina_1': 0,
        }
        req = self.rf.post('/fake', json.dumps(payload), content_type='application/json')
        req.user = self.user
        res = salvar_supervisor(req)

        self.assertEqual(res.status_code, 400)
        data = json.loads(res.content.decode('utf-8'))
        self.assertIn('conclu', data.get('error', '').lower())

    def test_salvar_supervisor_recalcula_limpeza_diaria_e_cumulativa_por_total_compartimentos(self):
        rdo_prev = RDO.objects.create(rdo='RDO-ANT-2', data=self.today - timedelta(days=1))
        RdoTanque.objects.create(
            rdo=rdo_prev,
            tanque_codigo='T-COMP-2',
            numero_compartimentos=10,
            compartimentos_avanco_json=json.dumps({'1': {'mecanizada': 80, 'fina': 10}}, ensure_ascii=False),
        )
        tank_atual = RdoTanque.objects.create(
            rdo=self.rdo,
            tanque_codigo='T-COMP-2',
            numero_compartimentos=10,
        )

        payload = {
            'rdo_id': self.rdo.id,
            'tanque_id': tank_atual.id,
            'numero_compartimentos': 10,
            'compartimento_avanco_mecanizada_1': 20,
            'compartimento_avanco_fina_1': 5,
        }
        req = self.rf.post('/fake', json.dumps(payload), content_type='application/json')
        req.user = self.user
        res = salvar_supervisor(req)

        self.assertEqual(res.status_code, 200)
        tank_atual.refresh_from_db()
        self.assertEqual(
            json.loads(tank_atual.compartimentos_avanco_json),
            {
                '1': {'mecanizada': 20, 'fina': 5},
                '2': {'mecanizada': 0, 'fina': 0},
                '3': {'mecanizada': 0, 'fina': 0},
                '4': {'mecanizada': 0, 'fina': 0},
                '5': {'mecanizada': 0, 'fina': 0},
                '6': {'mecanizada': 0, 'fina': 0},
                '7': {'mecanizada': 0, 'fina': 0},
                '8': {'mecanizada': 0, 'fina': 0},
                '9': {'mecanizada': 0, 'fina': 0},
                '10': {'mecanizada': 0, 'fina': 0},
            }
        )
        self.assertEqual(tank_atual.percentual_limpeza_diario, Decimal('2.00'))
        self.assertEqual(tank_atual.percentual_limpeza_cumulativo, Decimal('10.00'))
        self.assertEqual(tank_atual.percentual_limpeza_fina_diario, Decimal('0.50'))
        self.assertEqual(tank_atual.percentual_limpeza_fina_cumulativo, Decimal('1.50'))

    def test_salvar_supervisor_permita_fina_quando_mecanizada_ja_estiver_concluida(self):
        rdo_prev = RDO.objects.create(rdo='RDO-ANT-3', data=self.today - timedelta(days=1))
        RdoTanque.objects.create(
            rdo=rdo_prev,
            tanque_codigo='T-COMP-3',
            numero_compartimentos=10,
            compartimentos_avanco_json=json.dumps({'1': {'mecanizada': 100, 'fina': 80}}, ensure_ascii=False),
        )
        tank_atual = RdoTanque.objects.create(
            rdo=self.rdo,
            tanque_codigo='T-COMP-3',
            numero_compartimentos=10,
        )

        payload = {
            'rdo_id': self.rdo.id,
            'tanque_id': tank_atual.id,
            'numero_compartimentos': 10,
            'compartimentos_avanco': [1],
            'compartimento_avanco_mecanizada_1': 0,
            'compartimento_avanco_fina_1': 20,
        }
        req = self.rf.post('/fake', json.dumps(payload), content_type='application/json')
        req.user = self.user
        res = salvar_supervisor(req)

        self.assertEqual(res.status_code, 200)
        tank_atual.refresh_from_db()
        self.assertEqual(
            json.loads(tank_atual.compartimentos_avanco_json),
            {
                '1': {'mecanizada': 0, 'fina': 20},
                '2': {'mecanizada': 0, 'fina': 0},
                '3': {'mecanizada': 0, 'fina': 0},
                '4': {'mecanizada': 0, 'fina': 0},
                '5': {'mecanizada': 0, 'fina': 0},
                '6': {'mecanizada': 0, 'fina': 0},
                '7': {'mecanizada': 0, 'fina': 0},
                '8': {'mecanizada': 0, 'fina': 0},
                '9': {'mecanizada': 0, 'fina': 0},
                '10': {'mecanizada': 0, 'fina': 0},
            }
        )
        self.assertEqual(tank_atual.percentual_limpeza_cumulativo, Decimal('10.00'))
        self.assertEqual(tank_atual.percentual_limpeza_fina_cumulativo, Decimal('10.00'))

    def test_rdotanque_save_recalcula_percentual_avanco_cumulativo_mesmo_com_valor_stale(self):
        rdo_prev = RDO.objects.create(rdo='RDO-STALE-1', data=self.today - timedelta(days=1))
        RdoTanque.objects.create(
            rdo=rdo_prev,
            tanque_codigo='T-STALE',
            numero_compartimentos=10,
            compartimentos_avanco_json=json.dumps({'1': {'mecanizada': 80, 'fina': 10}}, ensure_ascii=False),
        )
        rdo_curr = RDO.objects.create(rdo='RDO-STALE-2', data=self.today)
        tank = RdoTanque.objects.create(
            rdo=rdo_curr,
            tanque_codigo='T-STALE',
            numero_compartimentos=10,
            compartimentos_avanco_json=json.dumps({'1': {'mecanizada': 20, 'fina': 5}}, ensure_ascii=False),
        )
        RdoTanque.objects.filter(pk=tank.pk).update(
            percentual_avanco=Decimal('99.99'),
            percentual_avanco_cumulativo=Decimal('1.00'),
        )

        tank.refresh_from_db()
        tank.metodo_exec = 'Manual'
        tank.save()
        tank.refresh_from_db()

        self.assertEqual(tank.percentual_limpeza_cumulativo, Decimal('10.00'))
        self.assertEqual(tank.percentual_limpeza_fina_cumulativo, Decimal('1.50'))
        self.assertEqual(tank.percentual_avanco_cumulativo, Decimal('7.46'))
        self.assertEqual(tank.percentual_avanco, Decimal('1.51'))

    def test_rdo_tank_detail_usa_rdo_atual_para_payload_e_historico_anterior(self):
        cliente = Cliente.objects.create(nome='Cliente Tank Detail')
        unidade = Unidade.objects.create(nome='Unidade Tank Detail')
        os_obj = OrdemServico.objects.create(
            numero_os='10025',
            data_inicio=self.today,
            dias_de_operacao_frente=0,
            dias_de_operacao=0,
            servico='TESTE',
            metodo='Manual',
            observacao='',
            pob=1,
            tanque='',
            volume_tanque=Decimal('0.00'),
            Cliente=cliente,
            Unidade=unidade,
            tipo_operacao='Onshore',
            solicitante='Teste',
            status_operacao='Programada',
            status_comercial='Em aberto',
        )
        rdo_1 = RDO.objects.create(rdo='1', data=self.today - timedelta(days=1), ordem_servico=os_obj)
        rdo_2 = RDO.objects.create(rdo='2', data=self.today, ordem_servico=os_obj)
        RdoTanque.objects.create(
            rdo=rdo_1,
            tanque_codigo='SLOP TANK',
            nome_tanque='SLOP TANK',
            numero_compartimentos=10,
            compartimentos_avanco_json=json.dumps({'1': {'mecanizada': 34, 'fina': 30}}, ensure_ascii=False),
        )

        req = self.rf.get('/api/rdo/tank/SLOP%20TANK/', {'rdo_id': str(rdo_2.id)})
        req.user = self.user
        res = rdo_tank_detail(req, 'SLOP TANK')

        self.assertEqual(res.status_code, 200)
        data = json.loads(res.content.decode('utf-8'))
        tank = data['tank']
        current_payload = json.loads(tank['compartimentos_avanco_json'])
        self.assertEqual(current_payload['1']['mecanizada'], 0)
        self.assertEqual(current_payload['1']['fina'], 0)
        previous = tank['previous_compartimentos'][0]
        self.assertEqual(previous['index'], 1)
        self.assertEqual(previous['mecanizada'], 34)
        self.assertEqual(previous['fina'], 30)
        self.assertEqual(previous['mecanizada_restante'], 66)
        self.assertEqual(previous['fina_restante'], 70)

    def test_rdo_tank_detail_para_novo_rdo_usa_ultimo_snapshot_como_anterior(self):
        cliente = Cliente.objects.create(nome='Cliente Tank Detail New')
        unidade = Unidade.objects.create(nome='Unidade Tank Detail New')
        os_obj = OrdemServico.objects.create(
            numero_os='10026',
            data_inicio=self.today,
            dias_de_operacao_frente=0,
            dias_de_operacao=0,
            servico='TESTE',
            metodo='Manual',
            observacao='',
            pob=1,
            tanque='',
            volume_tanque=Decimal('0.00'),
            Cliente=cliente,
            Unidade=unidade,
            tipo_operacao='Onshore',
            solicitante='Teste',
            status_operacao='Programada',
            status_comercial='Em aberto',
        )
        rdo_1 = RDO.objects.create(rdo='1', data=self.today - timedelta(days=1), ordem_servico=os_obj)
        RdoTanque.objects.create(
            rdo=rdo_1,
            tanque_codigo='SLOP TANK',
            nome_tanque='SLOP TANK',
            numero_compartimentos=10,
            compartimentos_avanco_json=json.dumps({'1': {'mecanizada': 34, 'fina': 30}}, ensure_ascii=False),
        )

        req = self.rf.get('/api/rdo/tank/SLOP%20TANK/', {'os_id': str(os_obj.id)})
        req.user = self.user
        res = rdo_tank_detail(req, 'SLOP TANK')

        self.assertEqual(res.status_code, 200)
        data = json.loads(res.content.decode('utf-8'))
        tank = data['tank']
        current_payload = json.loads(tank['compartimentos_avanco_json'])
        self.assertEqual(current_payload['1']['mecanizada'], 0)
        self.assertEqual(current_payload['1']['fina'], 0)
        previous = tank['previous_compartimentos'][0]
        self.assertEqual(previous['index'], 1)
        self.assertEqual(previous['mecanizada'], 34)
        self.assertEqual(previous['fina'], 30)
        self.assertEqual(previous['mecanizada_restante'], 66)
        self.assertEqual(previous['fina_restante'], 70)

    def test_rdo_detail_sincroniza_active_tanque_com_metricas_recalculadas(self):
        rdo_prev = RDO.objects.create(rdo='RDO-DET-1', data=self.today - timedelta(days=1))
        RdoTanque.objects.create(
            rdo=rdo_prev,
            tanque_codigo='T-DET',
            nome_tanque='Tanque Detalhe',
            numero_compartimentos=10,
            compartimentos_avanco_json=json.dumps({'1': {'mecanizada': 80, 'fina': 10}}, ensure_ascii=False),
        )
        rdo_curr = RDO.objects.create(rdo='RDO-DET-2', data=self.today)
        tank = RdoTanque.objects.create(
            rdo=rdo_curr,
            tanque_codigo='T-DET',
            nome_tanque='Tanque Detalhe',
            numero_compartimentos=10,
            compartimentos_avanco_json=json.dumps({'1': {'mecanizada': 20, 'fina': 5}}, ensure_ascii=False),
        )
        RdoTanque.objects.filter(pk=tank.pk).update(
            percentual_avanco=Decimal('99.99'),
            percentual_avanco_cumulativo=Decimal('1.00'),
        )

        req = self.rf.get(f'/rdo/{rdo_curr.id}/detail/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        req.user = self.user
        res = rdo_detail(req, rdo_curr.id)

        self.assertEqual(res.status_code, 200)
        data = json.loads(res.content.decode('utf-8'))
        payload = data['rdo']
        active = payload['active_tanque']

        self.assertEqual(str(payload['active_tanque_id']), str(tank.id))
        self.assertIn('T-DET', payload.get('active_tanque_label', ''))
        self.assertEqual(Decimal(str(payload['percentual_avanco_cumulativo'])), Decimal('7.46'))
        self.assertEqual(Decimal(str(active['percentual_avanco_cumulativo'])), Decimal('7.46'))
        self.assertEqual(Decimal(str(active['percentual_avanco'])), Decimal('1.51'))
