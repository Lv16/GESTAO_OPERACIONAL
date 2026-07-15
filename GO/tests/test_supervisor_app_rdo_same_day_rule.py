import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytz
from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from GO.models import (
    Cliente,
    MobileApiToken,
    OrdemServico,
    Pessoa,
    RDO,
    RDOMembroEquipe,
    RdoTanque,
    Unidade,
)


class SupervisorAppRdoSameDayRuleTests(TestCase):
    """
    Segurança:
    - Usa exclusivamente banco de teste criado pelo Django TestCase.
    - Cada teste roda isolado e sofre rollback/flush automático.
    - O usuário `supervisor.app` existe apenas nessa base temporária.
    """

    def setUp(self):
        self.client = Client()
        self.token_client = Client()
        self.sao_paulo = pytz.timezone('America/Sao_Paulo')
        self.supervisor_group, _ = Group.objects.get_or_create(name='Supervisor')
        self.supervisor = User.objects.create_user(
            username='supervisor.app',
            password='senha123',
            first_name='Supervisor',
            last_name='App',
        )
        self.supervisor_group.user_set.add(self.supervisor)
        self.client.force_login(self.supervisor)
        self.token = MobileApiToken.objects.create(
            key='tok_supervisor_app_same_day_rule_1234567890abcdef',
            user=self.supervisor,
            is_active=True,
            expires_at=timezone.now() + timedelta(days=30),
        )
        self.cliente = Cliente.objects.create(nome='Cliente TESTE_AUTOMATIZADO')
        self.unidade = Unidade.objects.create(nome='Unidade TESTE_AUTOMATIZADO')
        self.coordenador = next(value for value, _ in OrdemServico.COORDENADORES if value)
        self.funcao_choice = next(value for value, _ in OrdemServico.FUNCOES if value)
        self.pessoa_1 = Pessoa.objects.create(
            nome='TESTE_AUTOMATIZADO Pessoa 1',
            funcao=self.funcao_choice,
        )
        self.pessoa_2 = Pessoa.objects.create(
            nome='TESTE_AUTOMATIZADO Pessoa 2',
            funcao=self.funcao_choice,
        )

    def _aware(self, year, month, day, hour=0, minute=0):
        return timezone.make_aware(
            datetime(year, month, day, hour, minute),
            self.sao_paulo,
        )

    def _create_os(self, numero_os=991001):
        return OrdemServico.objects.create(
            numero_os=numero_os,
            data_inicio=date(2026, 6, 11),
            data_fim=None,
            dias_de_operacao=0,
            servico='LIMPEZA DE TANQUE',
            servicos='LIMPEZA DE TANQUE',
            metodo='Manual',
            pob=2,
            tanque='TESTE_AUTOMATIZADO',
            tanques=None,
            volume_tanque=Decimal('10.00'),
            Cliente=self.cliente,
            Unidade=self.unidade,
            tipo_operacao='Onshore',
            solicitante='Solicitante TESTE_AUTOMATIZADO',
            coordenador=self.coordenador,
            supervisor=self.supervisor,
            status_operacao='Em andamento',
            status_geral='Em andamento',
            status_comercial='Em aberto',
            status_planejamento='Pendente',
        )

    def _mobile_headers(self):
        return {
            'HTTP_HOST': 'localhost',
            'secure': True,
            'HTTP_AUTHORIZATION': f'Bearer {self.token.key}',
        }

    def _mobile_sync(self, body):
        return self.token_client.post(
            '/api/mobile/v1/rdo/sync/',
            data=json.dumps(body),
            content_type='application/json',
            **self._mobile_headers(),
        )

    def _mobile_create_rdo(self, os_obj, *, rdo_number='1', dt='2026-06-11', observacoes='TESTE_AUTOMATIZADO'):
        body = {
            'client_uuid': f'create-{os_obj.id}-{rdo_number}-{dt}',
            'operation': 'rdo.create',
            'payload': {
                'ordem_servico_id': str(os_obj.id),
                'rdo_contagem': str(rdo_number),
                'data_inicio': dt,
                'data': dt,
                'turno': 'Diurno',
                'observacoes': observacoes,
                'observacoes_pt': observacoes,
            },
        }
        return self._mobile_sync(body)

    def _mobile_add_tank(self, rdo_obj, *, codigo='TK-TESTE', nome='Tanque TESTE_AUTOMATIZADO'):
        body = {
            'client_uuid': f'tank-{rdo_obj.id}-{codigo}',
            'operation': 'rdo.tank.add',
            'payload': {
                'rdo_id': str(rdo_obj.id),
                'tanque_codigo': codigo,
                'tanque_nome': nome,
                'tipo_tanque': 'Compartimento',
            },
        }
        return self._mobile_sync(body)

    def _create_rdo_fixture(self, *, with_tank, created_at, rdo_number='1'):
        os_obj = self._create_os(numero_os=int(f'99{rdo_number.zfill(4)}'))
        rdo = RDO.objects.create(
            ordem_servico=os_obj,
            rdo=str(rdo_number),
            data=created_at.date(),
            data_inicio=created_at.date(),
            turno='Diurno',
            contrato_po='PO TESTE_AUTOMATIZADO',
            observacoes_rdo_pt='TESTE_AUTOMATIZADO observacao original',
            planejamento_pt='TESTE_AUTOMATIZADO planejamento original',
            created_at=created_at,
        )
        RDOMembroEquipe.objects.create(
            rdo=rdo,
            pessoa=self.pessoa_1,
            funcao='Supervisor',
            em_servico=True,
            ordem=0,
        )
        if with_tank:
            RdoTanque.objects.create(
                rdo=rdo,
                tanque_codigo=f'TK-{rdo_number}',
                nome_tanque='Tanque TESTE_AUTOMATIZADO',
                tipo_tanque='Compartimento',
                created_at=created_at,
            )
        return os_obj, rdo

    def _freeze_now(self, aware_dt):
        return patch('GO.views_rdo.timezone.now', return_value=aware_dt)

    def _assert_only_date_and_team_changed(self, rdo, expected_date, expected_team_size):
        rdo.refresh_from_db()
        self.assertEqual(rdo.data, expected_date)
        self.assertEqual(rdo.data_inicio, expected_date)
        self.assertEqual(rdo.observacoes_rdo_pt, 'TESTE_AUTOMATIZADO observacao original')
        self.assertEqual(rdo.planejamento_pt, 'TESTE_AUTOMATIZADO planejamento original')
        self.assertEqual(rdo.membros_equipe.count(), expected_team_size)

    def test_create_rdo_with_tank_using_supervisor_app(self):
        os_obj = self._create_os(numero_os=991101)

        create_response = self._mobile_create_rdo(
            os_obj,
            rdo_number='11',
            observacoes='TESTE_AUTOMATIZADO criacao com tanque',
        )
        self.assertEqual(create_response.status_code, 200)
        create_payload = create_response.json()
        self.assertTrue(create_payload.get('success'))

        created_id = int(create_payload['result']['id'])
        rdo = RDO.objects.get(pk=created_id)
        tank_response = self._mobile_add_tank(
            rdo,
            codigo='TESTE_AUTOMATIZADO',
            nome='TESTE_AUTOMATIZADO',
        )
        self.assertEqual(tank_response.status_code, 200)
        tank_payload = tank_response.json()
        self.assertTrue(tank_payload.get('success'))

        rdo.refresh_from_db()
        self.assertEqual(rdo.ordem_servico_id, os_obj.id)
        self.assertEqual(rdo.rdo, '11')
        self.assertIn('TESTE_AUTOMATIZADO', rdo.observacoes_rdo_pt or '')
        self.assertEqual(rdo.tanques.count(), 1)
        self.assertEqual(rdo.tanques.first().tanque_codigo, 'TESTE_AUTOMATIZADO')

    def test_create_rdo_without_tank_using_supervisor_app(self):
        os_obj = self._create_os(numero_os=991102)

        create_response = self._mobile_create_rdo(
            os_obj,
            rdo_number='12',
            observacoes='TESTE_AUTOMATIZADO criacao sem tanque',
        )
        self.assertEqual(create_response.status_code, 200)
        create_payload = create_response.json()
        self.assertTrue(create_payload.get('success'))

        created_id = int(create_payload['result']['id'])
        rdo = RDO.objects.get(pk=created_id)
        self.assertEqual(rdo.ordem_servico_id, os_obj.id)
        self.assertEqual(rdo.rdo, '12')
        self.assertIn('TESTE_AUTOMATIZADO', rdo.observacoes_rdo_pt or '')
        self.assertEqual(rdo.tanques.count(), 0)

    def test_edit_with_tank_before_midnight_allows_full_edit(self):
        _, rdo = self._create_rdo_fixture(
            with_tank=True,
            created_at=self._aware(2026, 6, 11, 15, 0),
            rdo_number='21',
        )
        with self._freeze_now(self._aware(2026, 6, 11, 23, 59)):
            response = self.client.post(
                reverse('rdo_update_ajax'),
                data={
                    'rdo_id': str(rdo.id),
                    'observacoes': 'TESTE_AUTOMATIZADO observacao alterada',
                    'planejamento_pt': 'TESTE_AUTOMATIZADO planejamento alterado',
                    'turno': 'Noturno',
                    'rdo_data_inicio': '2026-06-11',
                    'equipe_nome[]': [self.pessoa_1.nome, self.pessoa_2.nome],
                    'equipe_funcao[]': ['Supervisor', 'Ajudante'],
                    'equipe_pessoa_id[]': [str(self.pessoa_1.id), str(self.pessoa_2.id)],
                },
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                HTTP_HOST='localhost',
                secure=True,
            )
        self.assertEqual(response.status_code, 200)
        rdo.refresh_from_db()
        self.assertEqual(rdo.turno, 'Noturno')
        self.assertEqual(rdo.observacoes_rdo_pt, 'TESTE_AUTOMATIZADO observacao alterada')
        self.assertEqual(rdo.planejamento_pt, 'TESTE_AUTOMATIZADO planejamento alterado')
        self.assertEqual(rdo.membros_equipe.count(), 2)

    def test_edit_with_tank_after_midnight_allows_only_date_and_team(self):
        _, rdo = self._create_rdo_fixture(
            with_tank=True,
            created_at=self._aware(2026, 6, 11, 15, 0),
            rdo_number='22',
        )
        with self._freeze_now(self._aware(2026, 6, 12, 0, 0)):
            blocked = self.client.post(
                reverse('rdo_update_ajax'),
                data={
                    'rdo_id': str(rdo.id),
                    'observacoes': 'TESTE_AUTOMATIZADO bloqueado',
                },
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                HTTP_HOST='localhost',
                secure=True,
            )
            allowed = self.client.post(
                reverse('rdo_update_ajax'),
                data={
                    'rdo_id': str(rdo.id),
                    'rdo_data_inicio': '2026-06-12',
                    'equipe_nome[]': [self.pessoa_2.nome],
                    'equipe_funcao[]': ['Ajudante'],
                    'equipe_pessoa_id[]': [str(self.pessoa_2.id)],
                },
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                HTTP_HOST='localhost',
                secure=True,
            )
        self.assertEqual(blocked.status_code, 400)
        self.assertIn('data e membros/equipe', blocked.json().get('error', '').lower())
        self.assertEqual(allowed.status_code, 200)
        self._assert_only_date_and_team_changed(rdo, date(2026, 6, 12), 1)

    def test_edit_without_tank_before_midnight_allows_full_edit(self):
        _, rdo = self._create_rdo_fixture(
            with_tank=False,
            created_at=self._aware(2026, 6, 11, 15, 0),
            rdo_number='23',
        )
        with self._freeze_now(self._aware(2026, 6, 11, 23, 59)):
            response = self.client.post(
                reverse('rdo_update_ajax'),
                data={
                    'rdo_id': str(rdo.id),
                    'observacoes': 'TESTE_AUTOMATIZADO sem tanque alterado',
                    'planejamento_pt': 'TESTE_AUTOMATIZADO planejamento sem tanque',
                    'turno': 'Noturno',
                },
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                HTTP_HOST='localhost',
                secure=True,
            )
        self.assertEqual(response.status_code, 200)
        rdo.refresh_from_db()
        self.assertEqual(rdo.turno, 'Noturno')
        self.assertEqual(rdo.observacoes_rdo_pt, 'TESTE_AUTOMATIZADO sem tanque alterado')
        self.assertEqual(rdo.planejamento_pt, 'TESTE_AUTOMATIZADO planejamento sem tanque')

    def test_edit_without_tank_after_midnight_allows_only_date_and_team(self):
        _, rdo = self._create_rdo_fixture(
            with_tank=False,
            created_at=self._aware(2026, 6, 11, 15, 0),
            rdo_number='24',
        )
        with self._freeze_now(self._aware(2026, 6, 12, 0, 0)):
            blocked = self.client.post(
                reverse('rdo_update_ajax'),
                data={
                    'rdo_id': str(rdo.id),
                    'planejamento_pt': 'TESTE_AUTOMATIZADO bloqueado',
                },
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                HTTP_HOST='localhost',
                secure=True,
            )
            allowed = self.client.post(
                reverse('rdo_update_ajax'),
                data={
                    'rdo_id': str(rdo.id),
                    'rdo_data_inicio': '2026-06-12',
                    'equipe_nome[]': [self.pessoa_2.nome],
                    'equipe_funcao[]': ['Ajudante'],
                    'equipe_pessoa_id[]': [str(self.pessoa_2.id)],
                },
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                HTTP_HOST='localhost',
                secure=True,
            )
        self.assertEqual(blocked.status_code, 400)
        self.assertIn('data e membros/equipe', blocked.json().get('error', '').lower())
        self.assertEqual(allowed.status_code, 200)
        self._assert_only_date_and_team_changed(rdo, date(2026, 6, 12), 1)

    def test_rdo_created_late_at_night_blocks_full_edit_at_midnight(self):
        _, rdo = self._create_rdo_fixture(
            with_tank=False,
            created_at=self._aware(2026, 6, 11, 23, 0),
            rdo_number='25',
        )
        with self._freeze_now(self._aware(2026, 6, 12, 0, 0)):
            response = self.client.post(
                reverse('rdo_update_ajax'),
                data={
                    'rdo_id': str(rdo.id),
                    'observacoes': 'TESTE_AUTOMATIZADO deveria bloquear',
                },
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                HTTP_HOST='localhost',
                secure=True,
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn('data e membros/equipe', response.json().get('error', '').lower())
        rdo.refresh_from_db()
        self.assertEqual(rdo.observacoes_rdo_pt, 'TESTE_AUTOMATIZADO observacao original')

    def test_api_direct_bypass_attempt_is_blocked_for_old_rdo(self):
        _, rdo = self._create_rdo_fixture(
            with_tank=True,
            created_at=self._aware(2026, 6, 10, 15, 0),
            rdo_number='26',
        )
        payload = {
            'data': '2026-06-12',
            'equipe_nome[]': [self.pessoa_1.nome],
            'equipe_funcao[]': ['Supervisor'],
            'equipe_pessoa_id[]': [str(self.pessoa_1.id)],
            'observacoes': 'TESTE_AUTOMATIZADO tentativa direta',
            'turno': 'Noturno',
        }
        with self._freeze_now(self._aware(2026, 6, 12, 10, 0)):
            response = self.token_client.post(
                f'/api/mobile/v1/rdo/{rdo.id}/edit/',
                data=json.dumps(payload),
                content_type='application/json',
                **self._mobile_headers(),
            )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertFalse(body.get('success'))
        self.assertIn('data e membros/equipe', body.get('error', '').lower())
        rdo.refresh_from_db()
        self.assertEqual(rdo.turno, 'Diurno')
        self.assertEqual(rdo.observacoes_rdo_pt, 'TESTE_AUTOMATIZADO observacao original')

    def test_api_allows_only_date_and_team_after_midnight(self):
        _, rdo = self._create_rdo_fixture(
            with_tank=True,
            created_at=self._aware(2026, 6, 11, 15, 0),
            rdo_number='27',
        )
        payload = {
            'data': '2026-06-12',
            'data_inicio': '2026-06-12',
            'rdo_data_inicio': '2026-06-12',
            'equipe_nome[]': [self.pessoa_2.nome],
            'equipe_funcao[]': ['Ajudante'],
            'equipe_pessoa_id[]': [str(self.pessoa_2.id)],
            'equipe_em_servico[]': ['true'],
        }
        with self._freeze_now(self._aware(2026, 6, 12, 0, 1)):
            response = self.token_client.post(
                f'/api/mobile/v1/rdo/{rdo.id}/edit/',
                data=json.dumps(payload),
                content_type='application/json',
                **self._mobile_headers(),
            )
        self.assertEqual(response.status_code, 200)
        rdo.refresh_from_db()
        self.assertEqual(rdo.data, date(2026, 6, 12))
        self.assertEqual(rdo.data_inicio, date(2026, 6, 12))
        self.assertEqual(rdo.observacoes_rdo_pt, 'TESTE_AUTOMATIZADO observacao original')
        self.assertEqual(rdo.membros_equipe.count(), 1)
        self.assertEqual(rdo.membros_equipe.first().pessoa_id, self.pessoa_2.id)
