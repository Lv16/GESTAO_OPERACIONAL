import json

from django.test import TestCase
from decimal import Decimal
from django.utils import timezone

from GO.models import RDO, RDOAtividade, RdoTanque

class RecomputeMetricsTestNew(TestCase):
    def setUp(self):
        self.today = timezone.now().date()

    def _make_rdo(self, ordem_servico=None, rdo_number=1, data=None):
        if data is None:
            data = self.today
        r = RDO.objects.create(ordem_servico=ordem_servico, rdo=rdo_number, data=data)
        return r

    def test_cumulative_sums_across_same_tank_code_with_fina(self):
        rdo1 = self._make_rdo(rdo_number=1, data=self.today)
        comp_json_1 = '{"1": {"mecanizada": 10, "fina": 1}, "2": {"mecanizada": 5, "fina": 2}}'
        t1 = RdoTanque.objects.create(
            rdo=rdo1,
            tanque_codigo='TANK9',
            numero_compartimentos=10,
            compartimentos_avanco_json=comp_json_1,
            limpeza_mecanizada_cumulativa=None,
            percentual_limpeza_cumulativo=None,
        )
        rdo1.compartimentos_avanco_json = comp_json_1
        rdo1.save()
        t1.recompute_metrics(only_when_missing=False)
        t1.save()

        rdo2 = self._make_rdo(rdo_number=2, data=self.today)
        comp_json_2 = '{"1": {"mecanizada": 5, "fina": 3}, "2": {"mecanizada": 4, "fina": 4}}'
        t2 = RdoTanque.objects.create(
            rdo=rdo2,
            tanque_codigo='TANK9',
            numero_compartimentos=10,
            compartimentos_avanco_json=comp_json_2,
            limpeza_mecanizada_cumulativa=None,
            percentual_limpeza_cumulativo=None,
        )

        avg2 = t2.recompute_metrics(only_when_missing=False)
        t2.save()
        t2_refreshed = RdoTanque.objects.get(pk=t2.pk)

        import json as _json
        p1 = _json.loads(comp_json_1)
        p2 = _json.loads(comp_json_2)
        n = 10
        sums = [0.0] * n
        sums_fina = [0.0] * n
        for i in range(1, n+1):
            k = str(i)
            mv = float(p1.get(k, {}).get('mecanizada', 0)) + float(p2.get(k, {}).get('mecanizada', 0))
            fv = float(p1.get(k, {}).get('fina', 0)) + float(p2.get(k, {}).get('fina', 0))
            mv = max(0.0, min(100.0, mv))
            fv = max(0.0, min(100.0, fv))
            sums[i-1] = mv
            sums_fina[i-1] = fv
        expected_avg = sum(sums) / float(n)
        expected_avg_fina = sum(sums_fina) / float(n)

        self.assertAlmostEqual(float(avg2), float(expected_avg), places=3)
        self.assertEqual(int(t2_refreshed.limpeza_mecanizada_cumulativa), int(round(expected_avg)))
        self.assertEqual(int(t2_refreshed.percentual_limpeza_cumulativo), int(round(expected_avg)))
        self.assertEqual(int(t2_refreshed.limpeza_fina_cumulativa), int(round(expected_avg_fina)))
        self.assertEqual(int(t2_refreshed.percentual_limpeza_fina_cumulativo), int(round(expected_avg_fina)))

    def test_previous_compartimentos_payload_reports_remaining_and_blocked_state(self):
        rdo1 = self._make_rdo(rdo_number=1, data=self.today)
        t1 = RdoTanque.objects.create(
            rdo=rdo1,
            tanque_codigo='TANK-HIST',
            numero_compartimentos=4,
            compartimentos_avanco_json='{"1": {"mecanizada": 100, "fina": 0}, "2": {"mecanizada": 40, "fina": 10}}',
        )
        t1.recompute_metrics(only_when_missing=False)
        t1.save()

        rdo2 = self._make_rdo(rdo_number=2, data=self.today)
        t2 = RdoTanque.objects.create(
            rdo=rdo2,
            tanque_codigo='TANK-HIST',
            numero_compartimentos=4,
        )

        previous = t2.get_previous_compartimentos_payload()
        row1 = next(item for item in previous if item['index'] == 1)
        row2 = next(item for item in previous if item['index'] == 2)

        self.assertEqual(row1['mecanizada'], 100)
        self.assertEqual(row1['mecanizada_restante'], 0)
        self.assertTrue(row1['mecanizada_bloqueado'])
        self.assertEqual(row2['mecanizada'], 40)
        self.assertEqual(row2['mecanizada_restante'], 60)
        self.assertFalse(row2['mecanizada_bloqueado'])
        self.assertEqual(row2['fina'], 10)
        self.assertEqual(row2['fina_restante'], 90)

    def test_validate_compartimentos_payload_rejects_excess_and_clamps_to_remaining(self):
        rdo1 = self._make_rdo(rdo_number=1, data=self.today)
        t1 = RdoTanque.objects.create(
            rdo=rdo1,
            tanque_codigo='TANK-VALID',
            numero_compartimentos=5,
            compartimentos_avanco_json='{"1": {"mecanizada": 80, "fina": 0}}',
        )
        t1.recompute_metrics(only_when_missing=False)
        t1.save()

        rdo2 = self._make_rdo(rdo_number=2, data=self.today)
        t2 = RdoTanque.objects.create(
            rdo=rdo2,
            tanque_codigo='TANK-VALID',
            numero_compartimentos=5,
        )

        validation = t2.validate_compartimentos_payload({
            '1': {'mecanizada': 30, 'fina': 0},
            '2': {'mecanizada': 10, 'fina': 0},
        }, total_compartimentos=5)

        self.assertFalse(validation['is_valid'])
        self.assertEqual(validation['payload']['1']['mecanizada'], 20)
        self.assertEqual(validation['payload']['2']['mecanizada'], 10)
        self.assertEqual(validation['snapshot']['daily']['mecanizada'], 6.0)
        self.assertEqual(validation['snapshot']['cumulative']['mecanizada'], 22.0)

    def test_rdo_compute_limpeza_from_compartimentos_uses_total_slots_and_sets_fina(self):
        rdo = self._make_rdo(rdo_number=10, data=self.today)
        rdo.tanque_codigo = 'RDO-LEGADO'
        rdo.numero_compartimentos = 10
        rdo.compartimentos_avanco_json = json.dumps({
            '1': {'mecanizada': 20, 'fina': 5},
        }, ensure_ascii=False)

        result = rdo.compute_limpeza_from_compartimentos()

        self.assertEqual(result, Decimal('2.00'))
        self.assertEqual(rdo.limpeza_mecanizada_diaria, Decimal('2.00'))
        self.assertEqual(rdo.percentual_limpeza_diario, Decimal('2.00'))
        self.assertEqual(rdo.limpeza_fina_diaria, Decimal('0.50'))
        self.assertEqual(rdo.percentual_limpeza_fina_diario, Decimal('0.50'))
        self.assertEqual(rdo.percentual_limpeza_fina, Decimal('0.50'))

    def test_rdo_compute_limpeza_cumulativa_caps_history_by_total_slots(self):
        rdo1 = self._make_rdo(rdo_number=11, data=self.today)
        rdo1.tanque_codigo = 'RDO-HIST'
        rdo1.numero_compartimentos = 10
        rdo1.compartimentos_avanco_json = json.dumps({
            '1': {'mecanizada': 80, 'fina': 10},
        }, ensure_ascii=False)
        rdo1.save()

        rdo2 = self._make_rdo(rdo_number=12, data=self.today)
        rdo2.tanque_codigo = 'RDO-HIST'
        rdo2.numero_compartimentos = 10
        rdo2.compartimentos_avanco_json = json.dumps({
            '1': {'mecanizada': 30, 'fina': 5},
        }, ensure_ascii=False)

        result = rdo2.compute_limpeza_cumulativa()

        self.assertEqual(result, Decimal('10.00'))
        self.assertEqual(rdo2.limpeza_mecanizada_cumulativa, Decimal('10.00'))
        self.assertEqual(rdo2.percentual_limpeza_diario_cumulativo, Decimal('10.00'))
        self.assertEqual(rdo2.limpeza_fina_cumulativa, Decimal('1.50'))
        self.assertEqual(rdo2.percentual_limpeza_fina_cumulativo, Decimal('1.50'))

    def test_rdo_calcula_percentuais_uses_real_weight_total_for_day_and_cumulative(self):
        rdo = self._make_rdo(rdo_number=13, data=self.today)
        RDOAtividade.objects.create(
            rdo=rdo,
            atividade='Instalação / Preparação / Montagem / Setup ',
        )
        rdo.percentual_limpeza_diario = Decimal('100.00')
        rdo.percentual_limpeza_fina = Decimal('100.00')
        rdo.percentual_limpeza_diario_cumulativo = Decimal('100.00')
        rdo.percentual_limpeza_fina_cumulativo = Decimal('100.00')
        rdo.percentual_ensacamento = Decimal('100.00')
        rdo.percentual_icamento = Decimal('100.00')
        rdo.percentual_cambagem = Decimal('100.00')

        rdo.calcula_percentuais()

        self.assertEqual(rdo.percentual_avanco, Decimal('100.00'))
        self.assertEqual(rdo.percentual_avanco_cumulativo, Decimal('100.00'))
