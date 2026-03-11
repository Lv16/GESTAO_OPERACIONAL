from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.utils import timezone
from datetime import timedelta

from GO.models import RDO, RdoTanque
from GO.views_rdo import add_tank_ajax


class RdoTankAssociationReusePlaceholderTest(TestCase):
    def setUp(self):
        self.user, _ = User.objects.get_or_create(
            username='test_assoc_super',
            defaults={
                'is_staff': True,
                'is_superuser': True,
                'email': 'test_assoc@example.com',
            },
        )
        self.rf = RequestFactory()

    def test_associate_reuses_placeholder_and_updates_daily_kpi(self):
        src_rdo = RDO.objects.create(rdo='SRC-RDO')
        dst_rdo = RDO.objects.create(rdo='DST-RDO')

        src_tank = RdoTanque.objects.create(
            rdo=src_rdo,
            tanque_codigo='2P',
            nome_tanque='2P',
            tipo_tanque='Compartimento',
            numero_compartimentos=10,
            volume_tanque_exec='200.000',
            servico_exec='LIMPEZA DE TANQUE DE ÓLEO',
            metodo_exec='Manual',
            ensacamento_dia=9,
        )

        placeholder = RdoTanque.objects.create(
            rdo=dst_rdo,
            tipo_tanque='Salão',
            numero_compartimentos=1,
            metodo_exec='Manual',
            total_n_efetivo_confinado=41,
            ensacamento_dia=7,
        )

        req = self.rf.post(
            '/api/rdo/%s/add_tank/' % dst_rdo.id,
            {
                'tank_id': str(src_tank.id),
            },
        )
        req.user = self.user

        res = add_tank_ajax(req, dst_rdo.id)
        self.assertEqual(res.status_code, 200)

        rows = RdoTanque.objects.filter(rdo=dst_rdo).order_by('id')
        self.assertEqual(rows.count(), 1)

        target = rows.first()
        self.assertEqual(target.id, placeholder.id)

        # Campos fixos vêm do tanque associado.
        self.assertEqual(target.tanque_codigo, '2P')
        self.assertEqual(target.nome_tanque, '2P')
        self.assertEqual(target.tipo_tanque, 'Compartimento')
        self.assertEqual(target.numero_compartimentos, 10)
        self.assertEqual(str(target.volume_tanque_exec), '200.000')
        self.assertEqual(target.servico_exec, 'LIMPEZA DE TANQUE DE ÓLEO')
        self.assertEqual(target.metodo_exec, 'Manual')

        # KPI diário existente no RDO atual é preservado.
        self.assertEqual(target.ensacamento_dia, 7)
        self.assertEqual(target.total_n_efetivo_confinado, 41)

    def test_associate_reconciles_duplicate_preferring_unidentified_row(self):
        src_rdo = RDO.objects.create(rdo='SRC-RDO-DUP')
        dst_rdo = RDO.objects.create(rdo='DST-RDO-DUP')

        src_tank = RdoTanque.objects.create(
            rdo=src_rdo,
            tanque_codigo='2P',
            nome_tanque='2P',
            tipo_tanque='Compartimento',
            numero_compartimentos=10,
            volume_tanque_exec='200.000',
            servico_exec='LIMPEZA DE TANQUE DE ÓLEO',
            metodo_exec='Manual',
        )

        wrong_row = RdoTanque.objects.create(
            rdo=dst_rdo,
            tipo_tanque='Salão',
            numero_compartimentos=1,
            metodo_exec='Manual',
            total_n_efetivo_confinado=41,
            ensacamento_dia=7,
        )

        duplicate_row = RdoTanque.objects.create(
            rdo=dst_rdo,
            tanque_codigo='2P',
            nome_tanque='2P',
            tipo_tanque='Compartimento',
            numero_compartimentos=10,
            volume_tanque_exec='200.000',
            servico_exec='LIMPEZA DE TANQUE DE ÓLEO',
            metodo_exec='Manual',
        )

        req = self.rf.post(
            '/api/rdo/%s/add_tank/' % dst_rdo.id,
            {
                'tank_id': str(src_tank.id),
            },
        )
        req.user = self.user

        res = add_tank_ajax(req, dst_rdo.id)
        self.assertEqual(res.status_code, 200)

        rows = list(RdoTanque.objects.filter(rdo=dst_rdo).order_by('id'))
        self.assertEqual(len(rows), 1)
        target = rows[0]

        # A linha "errada" é reaproveitada e a duplicada é removida.
        self.assertEqual(target.id, wrong_row.id)
        self.assertNotEqual(target.id, duplicate_row.id)
        self.assertFalse(RdoTanque.objects.filter(pk=duplicate_row.id).exists())

        # Mantém KPIs do preenchimento diário e fixa identificação correta do tanque.
        self.assertEqual(target.tanque_codigo, '2P')
        self.assertEqual(target.nome_tanque, '2P')
        self.assertEqual(target.tipo_tanque, 'Compartimento')
        self.assertEqual(target.total_n_efetivo_confinado, 41)
        self.assertEqual(target.ensacamento_dia, 7)

    def test_associate_updates_kpi_cumulative_including_current_day(self):
        today = timezone.now().date()

        prev_rdo = RDO.objects.create(rdo='PREV-RDO', data=today - timedelta(days=1))
        dst_rdo = RDO.objects.create(rdo='DST-RDO-CUM', data=today)
        src_rdo = RDO.objects.create(rdo='SRC-RDO-CUM', data=today + timedelta(days=1))

        src_tank = RdoTanque.objects.create(
            rdo=src_rdo,
            tanque_codigo='2P',
            nome_tanque='2P',
            tipo_tanque='Compartimento',
            numero_compartimentos=10,
            volume_tanque_exec='200.000',
            servico_exec='LIMPEZA DE TANQUE DE OLEO',
            metodo_exec='Manual',
        )

        RdoTanque.objects.create(
            rdo=prev_rdo,
            tanque_codigo='2P',
            nome_tanque='2P',
            numero_compartimentos=10,
            ensacamento_dia=70,
            icamento_dia=50,
            cambagem_dia=52,
        )

        wrong_row = RdoTanque.objects.create(
            rdo=dst_rdo,
            numero_compartimentos=10,
            ensacamento_dia=300,
            icamento_dia=300,
            cambagem_dia=300,
        )

        req = self.rf.post(
            '/api/rdo/%s/add_tank/' % dst_rdo.id,
            {
                'tank_id': str(src_tank.id),
            },
        )
        req.user = self.user

        res = add_tank_ajax(req, dst_rdo.id)
        self.assertEqual(res.status_code, 200)

        target = RdoTanque.objects.get(pk=wrong_row.id)
        self.assertEqual(target.tanque_codigo, '2P')
        self.assertEqual(target.ensacamento_cumulativo, 370)
        self.assertEqual(target.icamento_cumulativo, 350)
        self.assertEqual(target.cambagem_cumulativo, 352)
