from decimal import Decimal
import json
from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from GO.models import RDO, RdoTanque
from GO.views_rdo import _apply_post_to_rdo

class RdoTankPersistenceTest(TestCase):
    def setUp(self):
        self.user, _ = User.objects.get_or_create(username='test_super', defaults={'is_staff': True, 'is_superuser': True, 'email': 'test@example.com'})
        self.rdo = RDO.objects.create(rdo='RDO-TEST')
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