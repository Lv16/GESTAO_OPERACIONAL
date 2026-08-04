from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
import pytz

from GO.models import Cliente, OrdemServico, Pessoa, RDO, RDOAtividade, RDOMembroEquipe, Unidade


class RdoSupervisorLimitedUpdateTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.cliente = Cliente.objects.create(nome='Cliente Supervisor')
        self.unidade = Unidade.objects.create(nome='Unidade Supervisor')
        self.coordenador = next(value for value, _ in OrdemServico.COORDENADORES if value)
        self.funcao_choice = next(value for value, _ in OrdemServico.FUNCOES if value)
        self.supervisor_group, _ = Group.objects.get_or_create(name='Supervisor')
        self.supervisor = User.objects.create_user(
            username='supervisor_limited_update',
            password='senha123',
        )
        self.supervisor_group.user_set.add(self.supervisor)
        self.client.force_login(self.supervisor)
        self.sao_paulo = pytz.timezone('America/Sao_Paulo')

    def _create_os(self):
        return OrdemServico.objects.create(
            numero_os=7123,
            data_inicio=date(2026, 3, 31),
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
            status_operacao='Programada',
            status_geral='Programada',
            status_comercial='Em aberto',
            status_planejamento='Pendente',
        )

    def test_supervisor_update_only_changes_date_and_team_when_rdo_is_from_previous_day(self):
        os_obj = self._create_os()
        pessoa_antiga = Pessoa.objects.create(nome='Equipe Antiga', funcao=self.funcao_choice)
        pessoa_nova_1 = Pessoa.objects.create(nome='Equipe Nova 1', funcao=self.funcao_choice)
        pessoa_nova_2 = Pessoa.objects.create(nome='Equipe Nova 2', funcao=self.funcao_choice)

        rdo = RDO.objects.create(
            ordem_servico=os_obj,
            rdo='7',
            data=date(2026, 3, 31),
            data_inicio=date(2026, 3, 31),
            turno='Diurno',
            contrato_po='PO-ORIGINAL',
            observacoes_rdo_pt='Observacao original',
            pob=1,
        )
        RDOAtividade.objects.create(
            rdo=rdo,
            ordem=0,
            atividade='abertura pt',
            comentario_pt='atividade original',
        )
        RDOMembroEquipe.objects.create(
            rdo=rdo,
            pessoa=pessoa_antiga,
            funcao='Supervisor',
            em_servico=True,
            ordem=0,
        )
        RDO.objects.filter(pk=rdo.pk).update(
            created_at=timezone.make_aware(
                datetime(2026, 3, 31, 15, 0),
                self.sao_paulo,
            ),
        )

        with patch(
            'GO.views_rdo.timezone.now',
            return_value=timezone.make_aware(
                datetime(2026, 4, 1, 0, 0),
                self.sao_paulo,
            ),
        ):
            response = self.client.post(
                reverse('rdo_update_ajax'),
                data={
                    'rdo_id': str(rdo.pk),
                    'rdo_data_inicio': '2026-04-01',
                    'equipe_nome[]': [pessoa_nova_1.nome, pessoa_nova_2.nome],
                    'equipe_funcao[]': ['Lider', 'Ajudante'],
                    'equipe_pessoa_id[]': [str(pessoa_nova_1.id), str(pessoa_nova_2.id)],
                },
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                HTTP_HOST='localhost',
                secure=True,
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))

        rdo.refresh_from_db()

        self.assertEqual(rdo.data, date(2026, 4, 1))
        self.assertEqual(rdo.data_inicio, date(2026, 4, 1))
        self.assertEqual(rdo.turno, 'Diurno')
        self.assertEqual(rdo.contrato_po, 'PO-ORIGINAL')
        self.assertEqual(rdo.observacoes_rdo_pt, 'Observacao original')
        self.assertEqual(rdo.atividades_rdo.count(), 1)
        self.assertEqual(rdo.atividades_rdo.first().atividade, 'abertura pt')
        self.assertEqual(rdo.atividades_rdo.first().comentario_pt, 'atividade original')

        membros = list(rdo.membros_equipe.order_by('ordem'))
        self.assertEqual(len(membros), 2)
        self.assertEqual(membros[0].pessoa, pessoa_nova_1)
        self.assertEqual(membros[0].funcao, 'Lider')
        self.assertEqual(membros[1].pessoa, pessoa_nova_2)
        self.assertEqual(membros[1].funcao, 'Ajudante')
        self.assertEqual(rdo.pob, 2)

    def test_supervisor_same_day_can_edit_full_rdo(self):
        os_obj = self._create_os()
        rdo = RDO.objects.create(
            ordem_servico=os_obj,
            rdo='8',
            data=date(2026, 6, 11),
            data_inicio=date(2026, 6, 11),
            turno='Diurno',
            contrato_po='PO-ORIGINAL',
            observacoes_rdo_pt='Observacao original',
            created_at=timezone.make_aware(
                datetime(2026, 6, 11, 15, 0),
                self.sao_paulo,
            ),
        )

        with patch(
            'GO.views_rdo.timezone.now',
            return_value=timezone.make_aware(
                datetime(2026, 6, 11, 20, 0),
                self.sao_paulo,
            ),
        ), patch('GO.views_rdo.agendar_analise_rdo') as agendar_analise_mock:
            response = self.client.post(
                reverse('rdo_update_ajax'),
                data={
                    'rdo_id': str(rdo.pk),
                    'rdo_data_inicio': '2026-06-11',
                    'turno': 'Noturno',
                    'contrato_po': 'PO-ALTERADO',
                    'observacoes': 'observacao alterada',
                },
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                HTTP_HOST='localhost',
                secure=True,
            )

        self.assertEqual(response.status_code, 200)
        rdo.refresh_from_db()
        self.assertEqual(rdo.turno, 'Noturno')
        self.assertEqual(rdo.contrato_po, 'PO-ALTERADO')
        self.assertEqual(rdo.observacoes_rdo_pt, 'observacao alterada')
        agendar_analise_mock.assert_called_once_with(rdo)

    def test_supervisor_old_rdo_rejects_blocked_field_changes(self):
        os_obj = self._create_os()
        rdo = RDO.objects.create(
            ordem_servico=os_obj,
            rdo='9',
            data=date(2026, 6, 11),
            data_inicio=date(2026, 6, 11),
            observacoes_rdo_pt='Observacao original',
            created_at=timezone.make_aware(
                datetime(2026, 6, 11, 23, 0),
                self.sao_paulo,
            ),
        )

        with patch(
            'GO.views_rdo.timezone.now',
            return_value=timezone.make_aware(
                datetime(2026, 6, 12, 0, 0),
                self.sao_paulo,
            ),
        ):
            response = self.client.post(
                reverse('rdo_update_ajax'),
                data={
                    'rdo_id': str(rdo.pk),
                    'observacoes': 'nao deveria salvar',
                },
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                HTTP_HOST='localhost',
                secure=True,
            )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn('apenas data e membros', payload.get('error', '').lower())
        rdo.refresh_from_db()
        self.assertEqual(rdo.observacoes_rdo_pt, 'Observacao original')

    def test_admin_can_edit_old_rdo_without_same_day_restriction(self):
        admin = User.objects.create_user(
            username='admin_rdo_full_edit',
            password='senha123',
            is_superuser=True,
            is_staff=True,
        )
        self.client.force_login(admin)
        os_obj = OrdemServico.objects.create(
            numero_os=7999,
            data_inicio=date(2026, 6, 11),
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
            status_operacao='Programada',
            status_geral='Programada',
            status_comercial='Em aberto',
            status_planejamento='Pendente',
        )
        rdo = RDO.objects.create(
            ordem_servico=os_obj,
            rdo='10',
            data=date(2026, 6, 10),
            data_inicio=date(2026, 6, 10),
            observacoes_rdo_pt='Observacao original',
            created_at=timezone.make_aware(
                datetime(2026, 6, 10, 10, 0),
                self.sao_paulo,
            ),
        )

        with patch(
            'GO.views_rdo.timezone.now',
            return_value=timezone.make_aware(
                datetime(2026, 6, 12, 9, 0),
                self.sao_paulo,
            ),
        ):
            response = self.client.post(
                reverse('rdo_update_ajax'),
                data={
                    'rdo_id': str(rdo.pk),
                    'observacoes': 'admin alterou',
                },
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                HTTP_HOST='localhost',
                secure=True,
            )

        self.assertEqual(response.status_code, 200)
        rdo.refresh_from_db()
        self.assertEqual(rdo.observacoes_rdo_pt, 'admin alterou')

    def test_pending_os_json_for_supervisor_includes_latest_rdo_context(self):
        os_obj = self._create_os()
        RDO.objects.create(
            ordem_servico=os_obj,
            rdo='6',
            data=date(2026, 3, 30),
            data_inicio=date(2026, 3, 30),
            turno='Diurno',
            contrato_po='PO-ANTERIOR',
            pob=1,
        )
        latest_rdo = RDO.objects.create(
            ordem_servico=os_obj,
            rdo='7',
            data=date(2026, 3, 31),
            data_inicio=date(2026, 3, 31),
            turno='Noturno',
            contrato_po='PO-ATUAL',
            pob=2,
        )

        response = self.client.get(
            '/rdo/pending_os_json/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        items = payload.get('data') or []
        self.assertEqual(len(items), 1)

        item = items[0]
        self.assertEqual(item.get('os_id'), os_obj.id)
        self.assertEqual(item.get('rdo_id'), latest_rdo.id)
        self.assertEqual(item.get('rdo'), latest_rdo.rdo)
        self.assertEqual(item.get('data_inicio'), '2026-03-31')

    def test_pending_os_json_for_supervisor_prefere_maior_numero_rdo_na_mesma_numero_os(self):
        os_obj = self._create_os()
        os_mesma_numero = self._create_os()

        RDO.objects.create(
            ordem_servico=os_obj,
            rdo='29',
            data=date(2026, 3, 30),
            data_inicio=date(2026, 3, 30),
            turno='Diurno',
            contrato_po='PO-29',
            pob=1,
        )
        rdo_id_mais_novo_porem_menor = RDO.objects.create(
            ordem_servico=os_mesma_numero,
            rdo='14',
            data=date(2026, 3, 31),
            data_inicio=date(2026, 3, 31),
            turno='Noturno',
            contrato_po='PO-14',
            pob=2,
        )

        response = self.client.get(
            '/rdo/pending_os_json/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        items = payload.get('data') or []
        self.assertEqual(len(items), 1)

        item = items[0]
        self.assertNotEqual(item.get('rdo_id'), rdo_id_mais_novo_porem_menor.id)
        self.assertEqual(item.get('rdo'), '29')
