from datetime import date
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from GO.models import Cliente, OrdemServico, RDO, Unidade
from GO.rdo_sequence import apply_rdo_renumber_plan, build_rdo_renumber_plan


class RdoSequenceRenumberTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(nome='Cliente Renumber')
        self.unidade = Unidade.objects.create(nome='Unidade Renumber')
        self.coordenador = next(value for value, _ in OrdemServico.COORDENADORES if value)

    def _create_os(self, numero_os):
        return OrdemServico.objects.create(
            numero_os=numero_os,
            data_inicio=date(2026, 6, 1),
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
        )

    def _create_rdo(self, os_obj, numero, dia):
        return RDO.objects.create(
            ordem_servico=os_obj,
            rdo=str(numero),
            data=dia,
            data_inicio=dia,
        )

    def _force_rdo_value(self, rdo_obj, numero):
        RDO.objects.filter(pk=rdo_obj.pk).update(rdo=str(numero))
        rdo_obj.refresh_from_db()
        return rdo_obj

    def _rdos_por_numero_os(self, numero_os):
        return list(
            RDO.objects
            .filter(ordem_servico__numero_os=numero_os)
            .order_by('data_inicio', 'id')
            .values_list('rdo', flat=True)
        )

    def test_build_rdo_renumber_plan_recalcula_escopo_da_mesma_os(self):
        os_a = self._create_os(6376)
        os_b = self._create_os(6376)
        os_c = self._create_os(7001)

        self._create_rdo(os_a, 29, date(2026, 6, 3))
        self._create_rdo(os_a, 30, date(2026, 6, 4))
        self._create_rdo(os_b, 13, date(2026, 6, 16))
        self._create_rdo(os_b, 14, date(2026, 6, 17))
        self._create_rdo(os_c, 1, date(2026, 6, 18))

        plan, summary = build_rdo_renumber_plan(numero_os_list=['6376'])

        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]['numero_os'], 6376)
        self.assertEqual(summary[0]['changes'], 4)
        self.assertEqual(
            [(item['old_rdo'], item['new_rdo']) for item in plan],
            [('29', '1'), ('30', '2'), ('13', '3'), ('14', '4')],
        )

    def test_apply_rdo_renumber_plan_usa_fase_temporaria_para_evitar_conflitos(self):
        os_a = self._create_os(6255)
        os_b = self._create_os(6255)

        self._create_rdo(os_a, 5, date(2026, 6, 10))
        rdo_b = self._create_rdo(os_b, 6, date(2026, 6, 11))
        rdo_c = self._create_rdo(os_b, 7, date(2026, 6, 12))
        self._force_rdo_value(rdo_b, 5)
        self._force_rdo_value(rdo_c, 7)

        plan, summary = build_rdo_renumber_plan(numero_os_list=['6255'])
        updated = apply_rdo_renumber_plan(plan)

        self.assertEqual(len(summary), 1)
        self.assertEqual(updated, 3)
        self.assertEqual(self._rdos_por_numero_os(6255), ['1', '2', '3'])

    def test_management_command_dry_run_nao_persiste_alteracoes(self):
        os_a = self._create_os(6231)
        os_b = self._create_os(6231)

        self._create_rdo(os_a, 8, date(2026, 6, 10))
        rdo_b = self._create_rdo(os_b, 9, date(2026, 6, 11))
        self._force_rdo_value(rdo_b, 8)

        stdout = StringIO()
        call_command(
            'recalcular_rdos_por_numero_os',
            '--numero-os',
            '6231',
            '--dry-run',
            stdout=stdout,
        )

        self.assertEqual(self._rdos_por_numero_os(6231), ['8', '8'])
        self.assertIn('Dry run concluido', stdout.getvalue())
        self.assertIn('OS 6231', stdout.getvalue())

    def test_management_command_commit_persiste_alteracoes(self):
        os_a = self._create_os(6247)
        os_b = self._create_os(6247)

        self._create_rdo(os_a, 11, date(2026, 6, 10))
        rdo_b = self._create_rdo(os_b, 12, date(2026, 6, 11))
        rdo_c = self._create_rdo(os_b, 13, date(2026, 6, 12))
        self._force_rdo_value(rdo_b, 11)
        self._force_rdo_value(rdo_c, 12)

        stdout = StringIO()
        call_command(
            'recalcular_rdos_por_numero_os',
            '--numero-os',
            '6247',
            '--commit',
            stdout=stdout,
        )

        self.assertEqual(self._rdos_por_numero_os(6247), ['1', '2', '3'])
        self.assertIn('Commit concluido', stdout.getvalue())
