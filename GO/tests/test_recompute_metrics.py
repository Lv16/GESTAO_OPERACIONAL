from django.test import TestCase
from decimal import Decimal
from django.utils import timezone

from GO.models import RDO, RdoTanque

class RecomputeMetricsTest(TestCase):
    def setUp(self):
        self.today = timezone.now().date()

    def _make_rdo(self, ordem_servico=None, rdo_number=1, data=None):
        if data is None:
            data = self.today
        r = RDO.objects.create(ordem_servico=ordem_servico, rdo=rdo_number, data=data)
        return r

    def test_cumulative_sums_across_same_tank_code(self):

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
        avg1 = t1.recompute_metrics(only_when_missing=False)
        t1.save()

        later_date = self.today
        rdo2 = self._make_rdo(rdo_number=2, data=later_date)
        comp_json_2 = '{"1": {"mecanizada": 5, "fina": 3}, "2": {"mecanizada": 4, "fina": 4}}'
        t2 = RdoTanque.objects.create(
            rdo=rdo2,
            tanque_codigo='TANK9',
            numero_compartimentos=10,
            compartimentos_avanco_json=comp_json_2,
            limpeza_mecanizada_cumulativa=None,
            percentual_limpeza_cumulativo=None,
        )

        self.assertTrue(t2.limpeza_mecanizada_cumulativa in (None, ''))
        self.assertTrue(t2.percentual_limpeza_cumulativo in (None, ''))

        avg2 = t2.recompute_metrics(only_when_missing=False)
        from django.test import TestCase
        from decimal import Decimal
        from django.utils import timezone

        from GO.models import RDO, RdoTanque

        class RecomputeMetricsTest(TestCase):
            def setUp(self):
                self.today = timezone.now().date()

            def _make_rdo(self, ordem_servico=None, rdo_number=1, data=None):
                if data is None:
                    data = self.today
                r = RDO.objects.create(ordem_servico=ordem_servico, rdo=rdo_number, data=data)
                return r

            def test_cumulative_sums_across_same_tank_code(self):

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
                avg1 = t1.recompute_metrics(only_when_missing=False)
                t1.save()

                later_date = self.today
                rdo2 = self._make_rdo(rdo_number=2, data=later_date)
                comp_json_2 = '{"1": {"mecanizada": 5, "fina": 3}, "2": {"mecanizada": 4, "fina": 4}}'
                t2 = RdoTanque.objects.create(
                    rdo=rdo2,
                    tanque_codigo='TANK9',
                    numero_compartimentos=10,
                    compartimentos_avanco_json=comp_json_2,
                    limpeza_mecanizada_cumulativa=None,
                    percentual_limpeza_cumulativo=None,
                )

                self.assertTrue(t2.limpeza_mecanizada_cumulativa in (None, ''))
                self.assertTrue(t2.percentual_limpeza_cumulativo in (None, ''))

                avg2 = t2.recompute_metrics(only_when_missing=False)
                t2.save()

                t2_refreshed = RdoTanque.objects.get(pk=t2.pk)

                self.assertIsNotNone(avg2)

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
                    if mv < 0:
                        mv = 0.0
                    if fv < 0:
                        fv = 0.0
                    if mv > 100.0:
                        mv = 100.0
                    if fv > 100.0:
                        fv = 100.0
                    sums[i-1] = mv
                    sums_fina[i-1] = fv

                expected_avg = sum(sums) / float(n)
                expected_avg_fina = sum(sums_fina) / float(n)

                self.assertAlmostEqual(float(avg2), float(expected_avg), places=3)
                self.assertEqual(int(t2_refreshed.limpeza_mecanizada_cumulativa), int(round(expected_avg)))
                self.assertEqual(int(t2_refreshed.percentual_limpeza_cumulativo), int(round(expected_avg)))

                self.assertEqual(int(t2_refreshed.limpeza_fina_cumulativa), int(round(expected_avg_fina)))
                self.assertEqual(int(t2_refreshed.percentual_limpeza_fina_cumulativo), int(round(expected_avg_fina)))