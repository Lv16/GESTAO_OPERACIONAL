import os
import tempfile
from datetime import date
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from GO.models import Cliente, OrdemServico, Unidade


class ImportarOsCsvCommandTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(nome="Cliente Existente")
        self.unidade = Unidade.objects.create(nome="Unidade Existente")
        self.supervisor = User.objects.create_user(
            username="supervisor_csv",
            first_name="Carlos",
            last_name="Silva",
            password="senha123",
            email="supervisor.csv@example.com",
        )
        self.coordenador = next(value for value, _ in OrdemServico.COORDENADORES if value)

    def _write_csv(self, content):
        tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".csv", delete=False)
        tmp.write(content)
        tmp.flush()
        tmp.close()
        self.addCleanup(lambda: os.path.exists(tmp.name) and os.unlink(tmp.name))
        return tmp.name

    def test_importa_csv_e_cria_os(self):
        csv_path = self._write_csv(
            "\n".join(
                [
                    "numero_os;data_inicio;servico;metodo;cliente;unidade;tipo_operacao;solicitante;coordenador;supervisor;status_operacao;volume_tanque;pob;po",
                    f"7001;05/07/2026;coleta de ar;manual;Cliente Novo;Unidade Nova;onshore;Solicitante CSV;{self.coordenador};supervisor_csv;programada;12,50;8;PO-123",
                ]
            )
        )

        stdout = StringIO()
        call_command("importar_os_csv", csv_path, stdout=stdout)

        os_obj = OrdemServico.objects.get(numero_os=7001)
        self.assertEqual(os_obj.Cliente.nome, "Cliente Novo")
        self.assertEqual(os_obj.Unidade.nome, "Unidade Nova")
        self.assertEqual(os_obj.supervisor_id, self.supervisor.pk)
        self.assertEqual(os_obj.servico, "COLETA DE AR")
        self.assertEqual(os_obj.metodo, "Manual")
        self.assertEqual(os_obj.tipo_operacao, "Onshore")
        self.assertEqual(os_obj.status_operacao, "Programada")
        self.assertEqual(os_obj.status_geral, "Programada")
        self.assertEqual(os_obj.volume_tanque, Decimal("12.50"))
        self.assertIn("criadas=1", stdout.getvalue())

    def test_dry_run_nao_grava(self):
        csv_path = self._write_csv(
            "\n".join(
                [
                    "numero_os;data_inicio;servico;metodo;cliente;unidade;tipo_operacao;solicitante",
                    "7002;2026-07-05;COLETA DE AR;Manual;Cliente Dry;Unidade Dry;Onshore;Solicitante Dry",
                ]
            )
        )

        stdout = StringIO()
        call_command("importar_os_csv", csv_path, "--dry-run", stdout=stdout)

        self.assertFalse(OrdemServico.objects.filter(numero_os=7002).exists())
        self.assertIn("Dry run concluído", stdout.getvalue())

    def test_update_existing_atualiza_registros_mesma_os(self):
        OrdemServico.objects.create(
            numero_os=7003,
            data_inicio=date(2026, 7, 1),
            data_fim=None,
            dias_de_operacao=0,
            servico="COLETA DE AR",
            servicos="COLETA DE AR",
            metodo="Manual",
            pob=1,
            tanque="",
            tanques=None,
            volume_tanque=Decimal("0.00"),
            Cliente=self.cliente,
            Unidade=self.unidade,
            tipo_operacao="Onshore",
            solicitante="Solicitante Antigo",
            coordenador=self.coordenador,
            status_operacao="Programada",
            status_geral="Programada",
            status_comercial="Em aberto",
            status_planejamento="Pendente",
        )
        OrdemServico.objects.create(
            numero_os=7003,
            data_inicio=date(2026, 7, 2),
            data_fim=None,
            dias_de_operacao=0,
            servico="COLETA DE AR",
            servicos="COLETA DE AR",
            metodo="Manual",
            pob=1,
            tanque="",
            tanques=None,
            volume_tanque=Decimal("0.00"),
            Cliente=self.cliente,
            Unidade=self.unidade,
            tipo_operacao="Onshore",
            solicitante="Solicitante Antigo 2",
            coordenador=self.coordenador,
            status_operacao="Programada",
            status_geral="Programada",
            status_comercial="Em aberto",
            status_planejamento="Pendente",
        )

        csv_path = self._write_csv(
            "\n".join(
                [
                    "numero_os;data_inicio;servico;metodo;cliente;unidade;tipo_operacao;solicitante;status_operacao",
                    "7003;2026-07-05;COLETA DE AR;Manual;Cliente Existente;Unidade Existente;Onshore;Solicitante Atualizado;Em Andamento",
                ]
            )
        )

        stdout = StringIO()
        call_command("importar_os_csv", csv_path, "--update-existing", stdout=stdout)

        registros = list(OrdemServico.objects.filter(numero_os=7003).order_by("id"))
        self.assertEqual(len(registros), 2)
        self.assertTrue(all(item.solicitante == "Solicitante Atualizado" for item in registros))
        self.assertTrue(all(item.status_operacao == "Em Andamento" for item in registros))
        self.assertIn("registros_db_atualizados=2", stdout.getvalue())

    def test_strict_related_falha_quando_cliente_nao_existe(self):
        csv_path = self._write_csv(
            "\n".join(
                [
                    "numero_os;data_inicio;servico;metodo;cliente;unidade;tipo_operacao;solicitante",
                    "7004;2026-07-05;COLETA DE AR;Manual;Cliente Inexistente;Unidade Existente;Onshore;Solicitante Strict",
                ]
            )
        )

        with self.assertRaises(CommandError):
            call_command("importar_os_csv", csv_path, "--strict-related", stdout=StringIO(), stderr=StringIO())
