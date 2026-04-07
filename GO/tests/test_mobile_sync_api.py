import json
import os
from decimal import Decimal
from datetime import date
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.utils import timezone

from GO.models import (
    Cliente,
    MobileApiToken,
    MobileSyncEvent,
    OrdemServico,
    Pessoa,
    RDO,
    RDOMembroEquipe,
    RdoTanque,
    Unidade,
)


class MobileSyncApiIdempotencyTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.supervisor_group, _ = Group.objects.get_or_create(name='Supervisor')
        self.user = User.objects.create_user(
            username='mobile_sync_super',
            password='xpto1234',
            is_staff=True,
            is_superuser=True,
        )
        self.supervisor_group.user_set.add(self.user)
        self.client.force_login(self.user)
        self.token = MobileApiToken.objects.create(
            key='tok_mobile_sync_test_key_1234567890abcdef1234567890abcdef',
            user=self.user,
            is_active=True,
            expires_at=timezone.now() + timedelta(days=30),
        )
        self.other_supervisor = User.objects.create_user(
            username='mobile_sync_super_2',
            password='xpto1234',
        )
        self.supervisor_group.user_set.add(self.other_supervisor)
        self.other_token = MobileApiToken.objects.create(
            key=MobileApiToken.generate_key(),
            user=self.other_supervisor,
            is_active=True,
            expires_at=timezone.now() + timedelta(days=30),
        )

    def test_rdo_update_replay_is_idempotent(self):
        rdo = RDO.objects.create(rdo='RDO-MOBILE-1')

        first_body = {
            'client_uuid': '4a91fb4c-69ef-44a0-aee7-f04fc799f7d7',
            'operation': 'rdo.update',
            'payload': {
                'rdo_id': str(rdo.id),
                'observacoes': 'Primeiro envio mobile',
            },
        }
        response1 = self.client.post(
            '/api/mobile/v1/rdo/sync/',
            data=json.dumps(first_body),
            content_type='application/json',
            HTTP_HOST='localhost',
            secure=True,
        )
        self.assertEqual(response1.status_code, 200)
        data1 = response1.json()
        self.assertTrue(data1.get('success'))
        self.assertFalse(data1.get('idempotent'))

        rdo.refresh_from_db()
        self.assertEqual(rdo.observacoes_rdo_pt, 'Primeiro envio mobile')

        second_body = {
            'client_uuid': '4a91fb4c-69ef-44a0-aee7-f04fc799f7d7',
            'operation': 'rdo.update',
            'payload': {
                'rdo_id': str(rdo.id),
                'observacoes': 'Segundo envio que nao deve aplicar',
            },
        }
        response2 = self.client.post(
            '/api/mobile/v1/rdo/sync/',
            data=json.dumps(second_body),
            content_type='application/json',
            HTTP_HOST='localhost',
            secure=True,
        )
        self.assertEqual(response2.status_code, 200)
        data2 = response2.json()
        self.assertTrue(data2.get('idempotent'))
        self.assertEqual(data2.get('state'), MobileSyncEvent.STATE_DONE)

        rdo.refresh_from_db()
        self.assertEqual(rdo.observacoes_rdo_pt, 'Primeiro envio mobile')
        self.assertEqual(MobileSyncEvent.objects.filter(client_uuid='4a91fb4c-69ef-44a0-aee7-f04fc799f7d7').count(), 1)

    def test_rdo_update_reprocesses_stale_processing_event(self):
        rdo = RDO.objects.create(rdo='RDO-MOBILE-STALE-1')
        client_uuid = 'd3ce21df-f95e-4be2-9512-d4f6be66f4df'
        stale_at = timezone.now() - timedelta(minutes=10)
        event = MobileSyncEvent.objects.create(
            client_uuid=client_uuid,
            operation='rdo.update',
            user=self.user,
            request_payload={'payload': {'rdo_id': str(rdo.id)}},
            state=MobileSyncEvent.STATE_PROCESSING,
            http_status=202,
        )
        MobileSyncEvent.objects.filter(pk=event.pk).update(
            created_at=stale_at,
            updated_at=stale_at,
        )

        body = {
            'client_uuid': client_uuid,
            'operation': 'rdo.update',
            'payload': {
                'rdo_id': str(rdo.id),
                'observacoes': 'Reprocessado apos travamento',
            },
        }

        response = self.client.post(
            '/api/mobile/v1/rdo/sync/',
            data=json.dumps(body),
            content_type='application/json',
            HTTP_HOST='localhost',
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertFalse(data.get('idempotent'))

        event.refresh_from_db()
        self.assertEqual(event.state, MobileSyncEvent.STATE_DONE)
        self.assertEqual(event.http_status, 200)
        rdo.refresh_from_db()
        self.assertEqual(rdo.observacoes_rdo_pt, 'Reprocessado apos travamento')

    def test_add_tank_replay_does_not_duplicate(self):
        rdo = RDO.objects.create(rdo='RDO-MOBILE-2')

        body = {
            'client_uuid': '57f3cbf1-a48b-4d8b-9ed5-f8f34fd55be4',
            'operation': 'rdo.tank.add',
            'payload': {
                'rdo_id': str(rdo.id),
                'tanque_codigo': '7P',
                'tanque_nome': '7P',
                'tipo_tanque': 'Compartimento',
            },
        }

        response1 = self.client.post(
            '/api/mobile/v1/rdo/sync/',
            data=json.dumps(body),
            content_type='application/json',
            HTTP_HOST='localhost',
            secure=True,
        )
        self.assertEqual(response1.status_code, 200)
        self.assertEqual(RdoTanque.objects.filter(rdo=rdo).count(), 1)

        response2 = self.client.post(
            '/api/mobile/v1/rdo/sync/',
            data=json.dumps(body),
            content_type='application/json',
            HTTP_HOST='localhost',
            secure=True,
        )
        self.assertEqual(response2.status_code, 200)
        data2 = response2.json()
        self.assertTrue(data2.get('idempotent'))
        self.assertEqual(RdoTanque.objects.filter(rdo=rdo).count(), 1)
        self.assertEqual(MobileSyncEvent.objects.filter(client_uuid='57f3cbf1-a48b-4d8b-9ed5-f8f34fd55be4').count(), 1)

    def test_token_auth_works_without_session(self):
        rdo = RDO.objects.create(rdo='RDO-MOBILE-TOKEN')
        token_client = Client()

        body = {
            'client_uuid': 'fe1ff5e7-4fac-4f56-90ac-288e73c5ef26',
            'operation': 'rdo.update',
            'payload': {
                'rdo_id': str(rdo.id),
                'observacoes': 'Sync com token bearer',
            },
        }

        response = token_client.post(
            '/api/mobile/v1/rdo/sync/',
            data=json.dumps(body),
            content_type='application/json',
            HTTP_HOST='localhost',
            secure=True,
            HTTP_AUTHORIZATION=f'Bearer {self.token.key}',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        rdo.refresh_from_db()
        self.assertEqual(rdo.observacoes_rdo_pt, 'Sync com token bearer')

    def test_photo_upload_idempotent_with_token(self):
        rdo = RDO.objects.create(rdo='RDO-MOBILE-PHOTO')
        token_client = Client()
        image_bytes = b'fake-image-content'

        payload = {
            'client_uuid': '347f7ec9-62c4-463d-8bc7-c6dcac17d64e',
            'rdo_id': str(rdo.id),
            'fotos': SimpleUploadedFile('test.png', image_bytes, content_type='image/png'),
        }

        response1 = token_client.post(
            '/api/mobile/v1/rdo/photo/upload/',
            data=payload,
            HTTP_HOST='localhost',
            secure=True,
            HTTP_AUTHORIZATION=f'Bearer {self.token.key}',
        )
        self.assertEqual(response1.status_code, 200)

        payload_replay = {
            'client_uuid': '347f7ec9-62c4-463d-8bc7-c6dcac17d64e',
            'rdo_id': str(rdo.id),
            'fotos': SimpleUploadedFile('test.png', image_bytes, content_type='image/png'),
        }
        response2 = token_client.post(
            '/api/mobile/v1/rdo/photo/upload/',
            data=payload_replay,
            HTTP_HOST='localhost',
            secure=True,
            HTTP_AUTHORIZATION=f'Bearer {self.token.key}',
        )
        self.assertEqual(response2.status_code, 200)
        data2 = response2.json()
        self.assertTrue(data2.get('idempotent'))
        self.assertEqual(MobileSyncEvent.objects.filter(client_uuid='347f7ec9-62c4-463d-8bc7-c6dcac17d64e').count(), 1)

    def test_batch_sync_supports_dependency_and_ref_mapping(self):
        rdo = RDO.objects.create(rdo='RDO-MOBILE-BATCH-1')
        token_client = Client()

        body = {
            'items': [
                {
                    'client_uuid': '5f090189-92d4-46cf-aa89-4161f4f8138a',
                    'operation': 'rdo.update',
                    'entity_alias': 'rdo_main',
                    'payload': {
                        'rdo_id': str(rdo.id),
                        'observacoes': 'Batch passo 1',
                    },
                },
                {
                    'client_uuid': '4e42ebcc-9a10-4d9f-98ef-c92158aef666',
                    'operation': 'rdo.tank.add',
                    'depends_on': ['5f090189-92d4-46cf-aa89-4161f4f8138a', 'rdo_main'],
                    'entity_alias': 'tank_main',
                    'payload': {
                        'rdo_id': '@ref:rdo_main',
                        'tanque_codigo': '9P',
                        'tanque_nome': '9P',
                        'tipo_tanque': 'Compartimento',
                    },
                },
                {
                    'client_uuid': '2d2ff54a-b9a6-430d-ba49-c9a643cb2327',
                    'operation': 'rdo.update',
                    'depends_on': ['tank_main'],
                    'payload': {
                        'rdo_id': '@ref:rdo_main',
                        'observacoes': 'Batch passo 3',
                    },
                },
            ],
        }

        response = token_client.post(
            '/api/mobile/v1/rdo/sync/batch/',
            data=json.dumps(body),
            content_type='application/json',
            HTTP_HOST='localhost',
            secure=True,
            HTTP_AUTHORIZATION=f'Bearer {self.token.key}',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('requested_count'), 3)
        self.assertEqual(data.get('executed_count'), 3)
        self.assertEqual(data.get('success_count'), 3)
        self.assertEqual(data.get('error_count'), 0)
        self.assertEqual(data.get('blocked_count'), 0)

        id_map = data.get('id_map') or {}
        self.assertEqual(id_map.get('rdo_main'), rdo.id)
        self.assertTrue(int(id_map.get('tank_main')) > 0)

        rdo.refresh_from_db()
        self.assertEqual(rdo.observacoes_rdo_pt, 'Batch passo 3')
        self.assertEqual(RdoTanque.objects.filter(rdo=rdo).count(), 1)
        tank = RdoTanque.objects.filter(rdo=rdo).first()
        self.assertIsNotNone(tank)
        self.assertEqual(tank.id, int(id_map.get('tank_main')))
        self.assertEqual(
            MobileSyncEvent.objects.filter(
                client_uuid__in=[
                    '5f090189-92d4-46cf-aa89-4161f4f8138a',
                    '4e42ebcc-9a10-4d9f-98ef-c92158aef666',
                    '2d2ff54a-b9a6-430d-ba49-c9a643cb2327',
                ]
            ).count(),
            3,
        )

    def test_batch_sync_unresolved_ref_does_not_execute_item(self):
        rdo = RDO.objects.create(rdo='RDO-MOBILE-BATCH-2')
        token_client = Client()

        body = {
            'stop_on_error': False,
            'items': [
                {
                    'client_uuid': 'f8dcf5f8-90a3-4a8f-99d8-48d31b5a0108',
                    'operation': 'rdo.tank.add',
                    'entity_alias': 'tank_missing',
                    'payload': {
                        'rdo_id': '@ref:rdo_nao_existe',
                        'tanque_codigo': '8P',
                        'tanque_nome': '8P',
                    },
                },
                {
                    'client_uuid': 'f08d9ee2-f532-48b2-bfd6-31ca2a2c0cb5',
                    'operation': 'rdo.update',
                    'payload': {
                        'rdo_id': str(rdo.id),
                        'observacoes': 'Batch segue após ref inválida',
                    },
                },
            ],
        }

        response = token_client.post(
            '/api/mobile/v1/rdo/sync/batch/',
            data=json.dumps(body),
            content_type='application/json',
            HTTP_HOST='localhost',
            secure=True,
            HTTP_AUTHORIZATION=f'Bearer {self.token.key}',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data.get('success'))
        self.assertEqual(data.get('requested_count'), 2)
        self.assertEqual(data.get('executed_count'), 1)
        self.assertEqual(data.get('success_count'), 1)
        self.assertEqual(data.get('error_count'), 1)
        self.assertEqual(data.get('blocked_count'), 0)

        items = data.get('items') or []
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].get('http_status'), 400)
        self.assertIn('Referências não resolvidas', items[0].get('error_message') or '')
        self.assertTrue(items[1].get('success'))

        self.assertEqual(MobileSyncEvent.objects.filter(client_uuid='f8dcf5f8-90a3-4a8f-99d8-48d31b5a0108').count(), 0)
        self.assertEqual(MobileSyncEvent.objects.filter(client_uuid='f08d9ee2-f532-48b2-bfd6-31ca2a2c0cb5').count(), 1)
        rdo.refresh_from_db()
        self.assertEqual(rdo.observacoes_rdo_pt, 'Batch segue após ref inválida')

    def test_batch_sync_blocks_item_when_dependency_failed(self):
        token_client = Client()

        body = {
            'stop_on_error': False,
            'items': [
                {
                    'client_uuid': '0d7a4b85-63e0-47de-8db6-27b0c3763b4d',
                    'operation': 'unsupported.test',
                    'entity_alias': 'first_step',
                    'payload': {},
                },
                {
                    'client_uuid': '4bc1ac39-67a4-4b4b-b41e-797f0a72f5fb',
                    'operation': 'rdo.update',
                    'depends_on': ['0d7a4b85-63e0-47de-8db6-27b0c3763b4d'],
                    'payload': {'rdo_id': '999999', 'observacoes': 'Não deve executar'},
                },
            ],
        }

        response = token_client.post(
            '/api/mobile/v1/rdo/sync/batch/',
            data=json.dumps(body),
            content_type='application/json',
            HTTP_HOST='localhost',
            secure=True,
            HTTP_AUTHORIZATION=f'Bearer {self.token.key}',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data.get('success'))
        self.assertEqual(data.get('executed_count'), 1)
        self.assertEqual(data.get('error_count'), 1)
        self.assertEqual(data.get('blocked_count'), 1)

        items = data.get('items') or []
        self.assertEqual(len(items), 2)
        self.assertFalse(items[0].get('success'))
        self.assertEqual(items[1].get('state'), 'blocked')
        self.assertIn('dependências com falha', (items[1].get('error_message') or '').lower())

        self.assertEqual(MobileSyncEvent.objects.filter(client_uuid='0d7a4b85-63e0-47de-8db6-27b0c3763b4d').count(), 1)
        self.assertEqual(MobileSyncEvent.objects.filter(client_uuid='4bc1ac39-67a4-4b4b-b41e-797f0a72f5fb').count(), 0)

    def test_mobile_auth_token_rejects_non_supervisor_user(self):
        User.objects.create_user(
            username='usuario_sem_supervisor',
            email='usuario_sem_supervisor@teste.local',
            password='xpto1234',
        )
        token_client = Client()
        body = {
            'username': 'usuario_sem_supervisor',
            'password': 'xpto1234',
        }
        response = token_client.post(
            '/api/mobile/v1/auth/token/',
            data=json.dumps(body),
            content_type='application/json',
            HTTP_HOST='localhost',
            secure=True,
        )
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertFalse(data.get('success'))

    def test_mobile_sync_status_is_scoped_by_authenticated_user(self):
        MobileSyncEvent.objects.create(
            client_uuid='status-scoped-uuid-01',
            operation='rdo.update',
            user=self.user,
            state=MobileSyncEvent.STATE_DONE,
            http_status=200,
            response_payload={'success': True},
        )

        other_client = Client()
        response_other = other_client.get(
            '/api/mobile/v1/rdo/sync/status/?client_uuid=status-scoped-uuid-01',
            HTTP_HOST='localhost',
            secure=True,
            HTTP_AUTHORIZATION=f'Bearer {self.other_token.key}',
        )
        self.assertEqual(response_other.status_code, 404)

        owner_client = Client()
        response_owner = owner_client.get(
            '/api/mobile/v1/rdo/sync/status/?client_uuid=status-scoped-uuid-01',
            HTTP_HOST='localhost',
            secure=True,
            HTTP_AUTHORIZATION=f'Bearer {self.token.key}',
        )
        self.assertEqual(response_owner.status_code, 200)
        owner_data = response_owner.json()
        self.assertTrue(owner_data.get('found'))

    def test_mobile_photo_upload_forbidden_when_rdo_belongs_to_other_supervisor(self):
        cliente = Cliente.objects.create(nome='Cliente Teste Mobile')
        unidade = Unidade.objects.create(nome='Unidade Teste Mobile')
        os_obj = OrdemServico.objects.create(
            numero_os=900001,
            data_inicio=date.today(),
            dias_de_operacao=1,
            servico='COLETA DE AR',
            metodo='Manual',
            pob=1,
            volume_tanque=Decimal('1.00'),
            Cliente=cliente,
            Unidade=unidade,
            tipo_operacao='Onshore',
            solicitante='Teste',
            supervisor=self.user,
        )
        rdo = RDO.objects.create(rdo='RDO-MOBILE-PERM', ordem_servico=os_obj)

        token_client = Client()
        payload = {
            'client_uuid': 'photo-forbidden-supervisor-01',
            'rdo_id': str(rdo.id),
            'fotos': SimpleUploadedFile('test.png', b'fake-image-content', content_type='image/png'),
        }
        response = token_client.post(
            '/api/mobile/v1/rdo/photo/upload/',
            data=payload,
            HTTP_HOST='localhost',
            secure=True,
            HTTP_AUTHORIZATION=f'Bearer {self.other_token.key}',
        )
        self.assertEqual(response.status_code, 403)

    def test_mobile_bootstrap_includes_tanks_and_activity_choices(self):
        cliente = Cliente.objects.create(nome='Cliente Bootstrap Mobile')
        unidade = Unidade.objects.create(nome='Unidade Bootstrap Mobile')
        os_obj = OrdemServico.objects.create(
            numero_os=900111,
            data_inicio=date.today(),
            dias_de_operacao=5,
            servico='LIMPEZA DE TANQUE',
            metodo='Manual',
            pob=4,
            volume_tanque=Decimal('10.00'),
            Cliente=cliente,
            Unidade=unidade,
            tipo_operacao='Offshore',
            solicitante='Teste bootstrap',
            supervisor=self.user,
            status_operacao='Em andamento',
            status_geral='Em andamento',
        )
        OrdemServico.objects.create(
            numero_os=900111,
            data_inicio=date.today() - timedelta(days=1),
            dias_de_operacao=5,
            servico='LIMPEZA DE TANQUE',
            servicos='LIMPEZA DE TANQUE\nLIMPEZA DE TANQUE DE ÓLEO\nLIMPEZA DE TANQUE SEWAGE',
            metodo='Manual',
            pob=4,
            volume_tanque=Decimal('10.00'),
            Cliente=cliente,
            Unidade=unidade,
            tipo_operacao='Offshore',
            solicitante='Teste bootstrap services',
            supervisor=self.user,
            status_operacao='Em andamento',
            status_geral='Em andamento',
        )
        OrdemServico.objects.create(
            numero_os=900222,
            data_inicio=date.today(),
            dias_de_operacao=2,
            servico='LIMPEZA DE TANQUE',
            metodo='Manual',
            pob=2,
            volume_tanque=Decimal('5.00'),
            Cliente=cliente,
            Unidade=unidade,
            tipo_operacao='Offshore',
            solicitante='Teste bootstrap finalizada',
            supervisor=self.user,
            status_geral='Finalizada',
        )

        rdo_1 = RDO.objects.create(rdo='1', ordem_servico=os_obj, data=date.today())
        rdo_2 = RDO.objects.create(rdo='2', ordem_servico=os_obj, data=date.today())
        RdoTanque.objects.create(
            rdo=rdo_1,
            tanque_codigo='7P',
            nome_tanque='Tanque 7P antigo',
        )
        RdoTanque.objects.create(
            rdo=rdo_2,
            tanque_codigo='7P',
            nome_tanque='Tanque 7P atual',
        )
        RdoTanque.objects.create(
            rdo=rdo_2,
            tanque_codigo='8P',
            nome_tanque='Tanque 8P',
        )

        token_client = Client()
        response = token_client.get(
            '/api/mobile/v1/bootstrap/',
            HTTP_HOST='localhost',
            secure=True,
            HTTP_AUTHORIZATION=f'Bearer {self.token.key}',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertIn('atividade_choices', payload)
        self.assertTrue(isinstance(payload.get('atividade_choices'), list))
        self.assertGreater(len(payload.get('atividade_choices') or []), 0)

        items = payload.get('items') or []
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.get('numero_os'), '900111')
        self.assertIn('tanks', item)
        tanks = item.get('tanks') or []
        self.assertEqual(len(tanks), 2)
        codes = {str(t.get('tanque_codigo') or '').strip() for t in tanks}
        self.assertEqual(codes, {'7P', '8P'})
        self.assertEqual(int(item.get('servicos_count') or 0), 3)
        self.assertEqual(int(item.get('max_tanques_servicos') or 0), 3)
        self.assertEqual(int(item.get('total_tanques_os') or 0), 2)

    def test_mobile_bootstrap_fallbacks_to_declared_os_tanks_when_missing_rdotanque(self):
        cliente = Cliente.objects.create(nome='Cliente Bootstrap Tanques OS')
        unidade = Unidade.objects.create(nome='Unidade Bootstrap Tanques OS')
        OrdemServico.objects.create(
            numero_os=900119,
            data_inicio=date.today(),
            dias_de_operacao=3,
            servico='LIMPEZA DE TANQUE',
            servicos='LIMPEZA DE TANQUE\nLIMPEZA DE TANQUE DE ÓLEO',
            tanques='7P\n8P',
            metodo='Manual',
            pob=3,
            volume_tanque=Decimal('10.00'),
            Cliente=cliente,
            Unidade=unidade,
            tipo_operacao='Offshore',
            solicitante='Teste fallback tanques OS',
            supervisor=self.user,
            status_operacao='Em andamento',
            status_geral='Em andamento',
        )

        token_client = Client()
        response = token_client.get(
            '/api/mobile/v1/bootstrap/',
            HTTP_HOST='localhost',
            secure=True,
            HTTP_AUTHORIZATION=f'Bearer {self.token.key}',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))

        items = payload.get('items') or []
        target = None
        for item in items:
            if str(item.get('numero_os') or '').strip() == '900119':
                target = item
                break

        self.assertIsNotNone(target)
        tanks = target.get('tanks') or []
        self.assertEqual(len(tanks), 2)
        codes = {str(t.get('tanque_codigo') or '').strip() for t in tanks}
        self.assertEqual(codes, {'7P', '8P'})
        self.assertEqual(int(target.get('servicos_count') or 0), 2)
        self.assertEqual(int(target.get('max_tanques_servicos') or 0), 2)
        self.assertEqual(int(target.get('total_tanques_os') or 0), 2)

    def test_mobile_bootstrap_exposes_cumulative_compartimento_snapshot_for_latest_tank(self):
        cliente = Cliente.objects.create(nome='Cliente Bootstrap Compartimento')
        unidade = Unidade.objects.create(nome='Unidade Bootstrap Compartimento')
        os_obj = OrdemServico.objects.create(
            numero_os=900130,
            data_inicio=date.today(),
            dias_de_operacao=4,
            servico='LIMPEZA DE TANQUE',
            metodo='Manual',
            pob=4,
            volume_tanque=Decimal('12.00'),
            Cliente=cliente,
            Unidade=unidade,
            tipo_operacao='Offshore',
            solicitante='Teste cumulativo compartimento',
            supervisor=self.user,
            status_operacao='Em andamento',
            status_geral='Em andamento',
        )

        rdo_1 = RDO.objects.create(rdo='1', ordem_servico=os_obj, data=date.today())
        rdo_2 = RDO.objects.create(rdo='2', ordem_servico=os_obj, data=date.today() + timedelta(days=1))

        RdoTanque.objects.create(
            rdo=rdo_1,
            tanque_codigo='SLOP',
            nome_tanque='SLOP TANK',
            numero_compartimentos=1,
            compartimentos_avanco_json=json.dumps({
                '1': {'mecanizada': 50, 'fina': 0},
            }),
        )
        latest_tank = RdoTanque.objects.create(
            rdo=rdo_2,
            tanque_codigo='SLOP',
            nome_tanque='SLOP TANK',
            numero_compartimentos=1,
            compartimentos_avanco_json=json.dumps({
                '1': {'mecanizada': 50, 'fina': 30},
            }),
        )

        token_client = Client()
        response = token_client.get(
            '/api/mobile/v1/bootstrap/',
            HTTP_HOST='localhost',
            secure=True,
            HTTP_AUTHORIZATION=f'Bearer {self.token.key}',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))

        items = payload.get('items') or []
        target = None
        for item in items:
            if str(item.get('numero_os') or '').strip() == '900130':
                target = item
                break

        self.assertIsNotNone(target)
        tanks = target.get('tanks') or []
        self.assertEqual(len(tanks), 1)
        tank_payload = tanks[0]
        self.assertEqual(int(tank_payload.get('rdo_id') or 0), latest_tank.rdo_id)
        self.assertEqual(int(tank_payload.get('rdo_sequence') or 0), 2)

        cumulative_raw = tank_payload.get('compartimentos_cumulativo_json')
        self.assertTrue(isinstance(cumulative_raw, str))
        cumulative = json.loads(cumulative_raw)
        self.assertEqual(
            cumulative,
            {'1': {'mecanizada': 100, 'fina': 30}},
        )

    def test_mobile_bootstrap_resolves_numero_compartimentos_from_rdo_when_tank_field_is_empty(self):
        cliente = Cliente.objects.create(nome='Cliente Bootstrap Compartimentos Herdados')
        unidade = Unidade.objects.create(nome='Unidade Bootstrap Compartimentos Herdados')
        os_obj = OrdemServico.objects.create(
            numero_os=900131,
            data_inicio=date.today(),
            dias_de_operacao=4,
            servico='LIMPEZA DE TANQUE',
            metodo='Manual',
            pob=4,
            volume_tanque=Decimal('12.00'),
            Cliente=cliente,
            Unidade=unidade,
            tipo_operacao='Offshore',
            solicitante='Teste total compartimentos mobile',
            supervisor=self.user,
            status_operacao='Em andamento',
            status_geral='Em andamento',
        )

        rdo = RDO.objects.create(
            rdo='1',
            ordem_servico=os_obj,
            data=date.today(),
            numero_compartimentos=3,
            compartimentos_avanco_json=json.dumps({
                '1': {'mecanizada': 100, 'fina': 20},
                '2': {'mecanizada': 40, 'fina': 0},
                '3': {'mecanizada': 0, 'fina': 0},
            }),
        )
        RdoTanque.objects.create(
            rdo=rdo,
            tanque_codigo='7P',
            nome_tanque='Tanque 7P',
            numero_compartimentos=None,
            compartimentos_avanco_json=json.dumps({
                '1': {'mecanizada': 100, 'fina': 20},
                '2': {'mecanizada': 40, 'fina': 0},
                '3': {'mecanizada': 0, 'fina': 0},
            }),
        )

        token_client = Client()
        response = token_client.get(
            '/api/mobile/v1/bootstrap/',
            HTTP_HOST='localhost',
            secure=True,
            HTTP_AUTHORIZATION=f'Bearer {self.token.key}',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))

        items = payload.get('items') or []
        target = None
        for item in items:
            if str(item.get('numero_os') or '').strip() == '900131':
                target = item
                break

        self.assertIsNotNone(target)
        tanks = target.get('tanks') or []
        self.assertEqual(len(tanks), 1)
        tank_payload = tanks[0]
        self.assertEqual(int(tank_payload.get('numero_compartimentos') or 0), 3)

    def test_mobile_bootstrap_keeps_latest_rdotanque_even_when_identity_comes_from_rdo_fields(self):
        cliente = Cliente.objects.create(nome='Cliente Bootstrap Identidade RdoTanque')
        unidade = Unidade.objects.create(nome='Unidade Bootstrap Identidade RdoTanque')
        os_obj = OrdemServico.objects.create(
            numero_os=900132,
            data_inicio=date.today(),
            dias_de_operacao=4,
            servico='LIMPEZA DE TANQUE',
            metodo='Manual',
            pob=4,
            volume_tanque=Decimal('12.00'),
            Cliente=cliente,
            Unidade=unidade,
            tipo_operacao='Offshore',
            solicitante='Teste identidade mobile',
            supervisor=self.user,
            status_operacao='Em andamento',
            status_geral='Em andamento',
        )

        rdo_1 = RDO.objects.create(
            rdo='1',
            ordem_servico=os_obj,
            data=date.today(),
            tanque_codigo='SLOP',
            nome_tanque='SLOP TANK',
            numero_compartimentos=1,
        )
        rdo_2 = RDO.objects.create(
            rdo='2',
            ordem_servico=os_obj,
            data=date.today() + timedelta(days=1),
            tanque_codigo='SLOP',
            nome_tanque='SLOP TANK',
            numero_compartimentos=1,
        )

        RdoTanque.objects.create(
            rdo=rdo_1,
            tanque_codigo='SLOP',
            nome_tanque='SLOP TANK',
            numero_compartimentos=1,
            compartimentos_avanco_json=json.dumps({
                '1': {'mecanizada': 40, 'fina': 0},
            }),
        )
        latest_tank = RdoTanque.objects.create(
            rdo=rdo_2,
            tanque_codigo='',
            nome_tanque='',
            numero_compartimentos=1,
            compartimentos_avanco_json=json.dumps({
                '1': {'mecanizada': 60, 'fina': 20},
            }),
        )

        token_client = Client()
        response = token_client.get(
            '/api/mobile/v1/bootstrap/',
            HTTP_HOST='localhost',
            secure=True,
            HTTP_AUTHORIZATION=f'Bearer {self.token.key}',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))

        items = payload.get('items') or []
        target = None
        for item in items:
            if str(item.get('numero_os') or '').strip() == '900132':
                target = item
                break

        self.assertIsNotNone(target)
        tanks = target.get('tanks') or []
        self.assertEqual(len(tanks), 1)
        tank_payload = tanks[0]
        self.assertEqual(int(tank_payload.get('rdo_id') or 0), latest_tank.rdo_id)
        cumulative = json.loads(tank_payload.get('compartimentos_cumulativo_json') or '{}')
        self.assertEqual(cumulative, {'1': {'mecanizada': 100, 'fina': 20}})

    def test_mobile_bootstrap_counts_repeated_equal_services_as_distinct_tank_slots(self):
        cliente = Cliente.objects.create(nome='Cliente Bootstrap Serviços Iguais')
        unidade = Unidade.objects.create(nome='Unidade Bootstrap Serviços Iguais')
        OrdemServico.objects.create(
            numero_os=900120,
            data_inicio=date.today(),
            dias_de_operacao=3,
            servico='LIMPEZA DE TANQUE',
            servicos='LIMPEZA DE TANQUE\nLIMPEZA DE TANQUE\nLIMPEZA DE TANQUE',
            metodo='Manual',
            pob=3,
            volume_tanque=Decimal('10.00'),
            Cliente=cliente,
            Unidade=unidade,
            tipo_operacao='Offshore',
            solicitante='Teste serviços iguais',
            supervisor=self.user,
            status_operacao='Em andamento',
            status_geral='Em andamento',
        )

        token_client = Client()
        response = token_client.get(
            '/api/mobile/v1/bootstrap/',
            HTTP_HOST='localhost',
            secure=True,
            HTTP_AUTHORIZATION=f'Bearer {self.token.key}',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))

        items = payload.get('items') or []
        target = None
        for item in items:
            if str(item.get('numero_os') or '').strip() == '900120':
                target = item
                break

        self.assertIsNotNone(target)
        self.assertEqual(int(target.get('servicos_count') or 0), 3)
        self.assertEqual(int(target.get('max_tanques_servicos') or 0), 3)

    def test_batch_sync_can_create_rdo_then_update_and_add_tank(self):
        cliente = Cliente.objects.create(nome='Cliente Batch Create Mobile')
        unidade = Unidade.objects.create(nome='Unidade Batch Create Mobile')
        os_obj = OrdemServico.objects.create(
            numero_os=900333,
            data_inicio=date.today(),
            dias_de_operacao=3,
            servico='LIMPEZA DE TANQUE',
            metodo='Manual',
            pob=3,
            volume_tanque=Decimal('20.00'),
            Cliente=cliente,
            Unidade=unidade,
            tipo_operacao='Offshore',
            solicitante='Teste batch create',
            supervisor=self.user,
            status_operacao='Em andamento',
        )

        token_client = Client()
        body = {
            'items': [
                {
                    'client_uuid': '648b531d-febf-4fa3-8140-b87af3ba0d4a',
                    'operation': 'rdo.create',
                    'entity_alias': 'rdo_new',
                    'payload': {
                        'ordem_servico_id': str(os_obj.id),
                        'rdo_contagem': '1',
                        'data_inicio': date.today().isoformat(),
                        'turno': 'Diurno',
                    },
                },
                {
                    'client_uuid': '8f9d4af1-c8b7-4e5f-8a91-19565a0f7680',
                    'operation': 'rdo.update',
                    'depends_on': ['rdo_new'],
                    'payload': {
                        'rdo_id': '@ref:rdo_new',
                        'observacoes': 'Observação batch mobile',
                        'observacoes_pt': 'Observação batch mobile',
                    },
                },
                {
                    'client_uuid': '1f9d775d-95d9-4c3f-b111-ea5b7b55bc49',
                    'operation': 'rdo.tank.add',
                    'depends_on': ['rdo_new'],
                    'entity_alias': 'tank_new',
                    'payload': {
                        'rdo_id': '@ref:rdo_new',
                        'tanque_codigo': 'TK-01',
                        'tanque_nome': 'Tanque TK-01',
                        'tipo_tanque': 'Compartimento',
                    },
                },
            ],
        }

        response = token_client.post(
            '/api/mobile/v1/rdo/sync/batch/',
            data=json.dumps(body),
            content_type='application/json',
            HTTP_HOST='localhost',
            secure=True,
            HTTP_AUTHORIZATION=f'Bearer {self.token.key}',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertEqual(payload.get('requested_count'), 3)
        self.assertEqual(payload.get('executed_count'), 3)
        self.assertEqual(payload.get('success_count'), 3)
        self.assertEqual(payload.get('error_count'), 0)
        self.assertEqual(payload.get('blocked_count'), 0)

        id_map = payload.get('id_map') or {}
        rdo_id = int(id_map.get('rdo_new'))
        self.assertGreater(rdo_id, 0)
        self.assertGreater(int(id_map.get('tank_new')), 0)

        created_rdo = RDO.objects.get(pk=rdo_id)
        self.assertEqual(created_rdo.ordem_servico_id, os_obj.id)
        self.assertEqual(created_rdo.rdo, '1')
        self.assertEqual(created_rdo.data, date.today())
        self.assertEqual(created_rdo.data_inicio, date.today())
        self.assertEqual(created_rdo.observacoes_rdo_pt, 'Observação batch mobile')

        created_tank = RdoTanque.objects.filter(rdo=created_rdo).first()
        self.assertIsNotNone(created_tank)
        self.assertEqual(created_tank.tanque_codigo, 'TK-01')

    def test_batch_sync_maps_tank_alias_to_real_tank_id_when_update_references_it(self):
        dummy_rdo = RDO.objects.create(rdo='RDO-DUMMY-TANK-REF-1')
        for index in range(1, 4):
            RdoTanque.objects.create(
                rdo=dummy_rdo,
                tanque_codigo=f'DUMMY-{index}',
                nome_tanque=f'Dummy Tank {index}',
                tipo_tanque='Compartimento',
            )

        cliente = Cliente.objects.create(nome='Cliente Batch Alias Tank')
        unidade = Unidade.objects.create(nome='Unidade Batch Alias Tank')
        os_obj = OrdemServico.objects.create(
            numero_os=900334,
            data_inicio=date.today(),
            dias_de_operacao=3,
            servico='LIMPEZA DE TANQUE',
            metodo='Manual',
            pob=3,
            volume_tanque=Decimal('20.00'),
            Cliente=cliente,
            Unidade=unidade,
            tipo_operacao='Offshore',
            solicitante='Teste batch alias tank',
            supervisor=self.user,
            status_operacao='Em andamento',
        )

        token_client = Client()
        body = {
            'items': [
                {
                    'client_uuid': 'b02bf4bb-708d-41c7-af85-d9a0806a4dc1',
                    'operation': 'rdo.create',
                    'entity_alias': 'rdo_new',
                    'payload': {
                        'ordem_servico_id': str(os_obj.id),
                        'rdo_contagem': '1',
                        'data_inicio': date.today().isoformat(),
                        'turno': 'Diurno',
                    },
                },
                {
                    'client_uuid': '5be8a871-a1de-48a4-b0b1-a1e45d6db847',
                    'operation': 'rdo.tank.add',
                    'depends_on': ['rdo_new'],
                    'entity_alias': 'tank_new',
                    'payload': {
                        'rdo_id': '@ref:rdo_new',
                        'tanque_codigo': 'TK-REAL-01',
                        'tanque_nome': 'Tanque Real 01',
                        'tipo_tanque': 'Compartimento',
                        'numero_compartimentos': '2',
                        'metodo_exec': 'Manual',
                        'servico_exec': 'LIMPEZA DE TANQUE',
                        'ensacamento_dia': '10',
                    },
                },
                {
                    'client_uuid': '6bfdbd78-5859-49c4-8ca1-6d66a558242f',
                    'operation': 'rdo.update',
                    'depends_on': ['rdo_new', 'tank_new'],
                    'payload': {
                        'rdo_id': '@ref:rdo_new',
                        'tanque_id': '@ref:tank_new',
                        'tank_id': '@ref:tank_new',
                        'observacoes': 'Fluxo do app com tanque referenciado',
                        'observacoes_pt': 'Fluxo do app com tanque referenciado',
                        'ensacamento_dia': '10',
                        'atividade_nome[]': ['dds'],
                        'atividade_inicio[]': ['07:00'],
                        'atividade_fim[]': ['07:30'],
                        'atividade_comentario_pt[]': ['DDS inicial'],
                        'atividade_comentario_en[]': [''],
                    },
                },
            ],
        }

        response = token_client.post(
            '/api/mobile/v1/rdo/sync/batch/',
            data=json.dumps(body),
            content_type='application/json',
            HTTP_HOST='localhost',
            secure=True,
            HTTP_AUTHORIZATION=f'Bearer {self.token.key}',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertEqual(payload.get('requested_count'), 3)
        self.assertEqual(payload.get('success_count'), 3)
        self.assertEqual(payload.get('error_count'), 0)

        id_map = payload.get('id_map') or {}
        rdo_id = int(id_map.get('rdo_new'))
        tank_id = int(id_map.get('tank_new'))
        self.assertGreater(rdo_id, 0)
        self.assertGreater(tank_id, 0)
        self.assertNotEqual(
            rdo_id,
            tank_id,
            'O teste precisa garantir ids diferentes entre RDO e tanque.',
        )

        created_rdo = RDO.objects.get(pk=rdo_id)
        created_tank = RdoTanque.objects.get(pk=tank_id)
        self.assertEqual(created_tank.rdo_id, created_rdo.id)
        self.assertEqual(created_tank.tanque_codigo, 'TK-REAL-01')
        self.assertEqual(created_rdo.observacoes_rdo_pt, 'Fluxo do app com tanque referenciado')

    def test_batch_sync_update_with_same_locked_predictions_is_noop_and_finishes(self):
        cliente = Cliente.objects.create(nome='Cliente Batch Locked Prediction')
        unidade = Unidade.objects.create(nome='Unidade Batch Locked Prediction')
        os_obj = OrdemServico.objects.create(
            numero_os=900335,
            data_inicio=date.today(),
            dias_de_operacao=3,
            servico='LIMPEZA DE TANQUE',
            metodo='Manual',
            pob=3,
            volume_tanque=Decimal('20.00'),
            Cliente=cliente,
            Unidade=unidade,
            tipo_operacao='Offshore',
            solicitante='Teste batch locked prediction',
            supervisor=self.user,
            status_operacao='Em andamento',
        )

        rdo_anterior = RDO.objects.create(
            ordem_servico=os_obj,
            rdo='1',
            data=date.today(),
            data_inicio=date.today(),
            turno='Diurno',
        )
        tanque_anterior = RdoTanque.objects.create(
            rdo=rdo_anterior,
            tanque_codigo='TK-LOCK-01',
            nome_tanque='Tanque Lock 01',
            tipo_tanque='Compartimento',
            numero_compartimentos=2,
            ensacamento_prev=55,
            icamento_prev=55,
            cambagem_prev=55,
        )

        token_client = Client()
        body = {
            'items': [
                {
                    'client_uuid': 'c44a13b1-d0b7-4bc0-a1c1-7a71866c3b11',
                    'operation': 'rdo.create',
                    'entity_alias': 'rdo_new',
                    'payload': {
                        'ordem_servico_id': str(os_obj.id),
                        'rdo_contagem': '2',
                        'data_inicio': date.today().isoformat(),
                        'turno': 'Diurno',
                    },
                },
                {
                    'client_uuid': '1b2f0a94-7ed4-4a0c-a768-b0620b96ce32',
                    'operation': 'rdo.tank.add',
                    'depends_on': ['rdo_new'],
                    'payload': {
                        'rdo_id': '@ref:rdo_new',
                        'tanque_id': str(tanque_anterior.id),
                        'tank_id': str(tanque_anterior.id),
                    },
                },
                {
                    'client_uuid': '6ee06442-4988-4aef-9a54-bcc1dddb313f',
                    'operation': 'rdo.update',
                    'depends_on': ['rdo_new'],
                    'payload': {
                        'rdo_id': '@ref:rdo_new',
                        'tanque_id': str(tanque_anterior.id),
                        'tank_id': str(tanque_anterior.id),
                        'observacoes': 'Replay com previsões já travadas',
                        'observacoes_pt': 'Replay com previsões já travadas',
                        'ensacamento_prev': '55',
                        'icamento_prev': '55',
                        'cambagem_prev': '55',
                    },
                },
            ],
        }

        with patch('GO.views_rdo._sync_tank_prediction_group_metrics') as sync_mock:
            response = token_client.post(
                '/api/mobile/v1/rdo/sync/batch/',
                data=json.dumps(body),
                content_type='application/json',
                HTTP_HOST='localhost',
                secure=True,
                HTTP_AUTHORIZATION=f'Bearer {self.token.key}',
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertEqual(payload.get('success_count'), 3)
        self.assertEqual(payload.get('error_count'), 0)
        sync_mock.assert_not_called()

    def test_mobile_bootstrap_marks_single_primary_os_for_start(self):
        cliente = Cliente.objects.create(nome='Cliente Bootstrap Primary')
        unidade = Unidade.objects.create(nome='Unidade Bootstrap Primary')

        os_primary = OrdemServico.objects.create(
            numero_os=900701,
            data_inicio=date.today(),
            dias_de_operacao=3,
            servico='LIMPEZA DE TANQUE',
            metodo='Manual',
            pob=4,
            volume_tanque=Decimal('12.00'),
            Cliente=cliente,
            Unidade=unidade,
            tipo_operacao='Offshore',
            solicitante='Teste primary',
            supervisor=self.user,
            status_operacao='Em andamento',
        )
        os_secondary = OrdemServico.objects.create(
            numero_os=900702,
            data_inicio=date.today(),
            dias_de_operacao=3,
            servico='LIMPEZA DE TANQUE',
            metodo='Manual',
            pob=4,
            volume_tanque=Decimal('14.00'),
            Cliente=cliente,
            Unidade=unidade,
            tipo_operacao='Offshore',
            solicitante='Teste secondary',
            supervisor=self.user,
            status_operacao='Programada',
        )

        token_client = Client()
        response = token_client.get(
            '/api/mobile/v1/bootstrap/',
            HTTP_HOST='localhost',
            secure=True,
            HTTP_AUTHORIZATION=f'Bearer {self.token.key}',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))

        items = payload.get('items') or []
        by_os = {str(item.get('numero_os')): item for item in items}
        self.assertIn(str(os_primary.numero_os), by_os)
        self.assertIn(str(os_secondary.numero_os), by_os)

        primary_item = by_os[str(os_primary.numero_os)]
        secondary_item = by_os[str(os_secondary.numero_os)]

        self.assertTrue(primary_item.get('can_start'))
        self.assertFalse(secondary_item.get('can_start'))
        self.assertIn(
            str(os_primary.numero_os),
            str(secondary_item.get('start_block_reason') or ''),
        )

    def test_mobile_os_rdos_includes_team_summary_for_editing(self):
        cliente = Cliente.objects.create(nome='Cliente Edit RDO')
        unidade = Unidade.objects.create(nome='Unidade Edit RDO')
        os_obj = OrdemServico.objects.create(
            numero_os=6255,
            data_inicio=date.today(),
            dias_de_operacao=2,
            servico='COLETA DE AR',
            metodo='Manual',
            pob=2,
            volume_tanque=Decimal('10.00'),
            Cliente=cliente,
            Unidade=unidade,
            tipo_operacao='Onshore',
            solicitante='Teste',
            supervisor=self.user,
        )
        rdo = RDO.objects.create(
            ordem_servico=os_obj,
            rdo='18',
            data=date.today(),
            data_inicio=date.today(),
        )
        pessoa = Pessoa.objects.create(nome='Rafael Silva')
        RDOMembroEquipe.objects.create(
            rdo=rdo,
            pessoa=pessoa,
            funcao='Supervisor',
            em_servico=True,
            ordem=0,
        )

        token_client = Client()
        response = token_client.get(
            f'/api/mobile/v1/os/{os_obj.id}/rdos/?numero_os={os_obj.numero_os}',
            HTTP_HOST='localhost',
            secure=True,
            HTTP_AUTHORIZATION=f'Bearer {self.token.key}',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertEqual(len(payload.get('rdos') or []), 1)
        row = payload['rdos'][0]
        self.assertEqual(row.get('id'), rdo.id)
        self.assertEqual(str(row.get('rdo')), '18')
        self.assertEqual(row.get('data'), date.today().isoformat())
        self.assertEqual(row.get('pob'), 1)
        self.assertEqual(len(row.get('equipe') or []), 1)
        self.assertEqual(row['equipe'][0].get('nome'), 'Rafael Silva')
        self.assertEqual(row['equipe'][0].get('funcao'), 'Supervisor')

    def test_mobile_rdo_supervisor_edit_updates_only_date_and_team(self):
        cliente = Cliente.objects.create(nome='Cliente Edit Save')
        unidade = Unidade.objects.create(nome='Unidade Edit Save')
        os_obj = OrdemServico.objects.create(
            numero_os=7001,
            data_inicio=date.today(),
            dias_de_operacao=2,
            servico='COLETA DE AR',
            metodo='Manual',
            pob=1,
            volume_tanque=Decimal('10.00'),
            Cliente=cliente,
            Unidade=unidade,
            tipo_operacao='Onshore',
            solicitante='Teste',
            supervisor=self.user,
        )
        rdo = RDO.objects.create(
            ordem_servico=os_obj,
            rdo='3',
            data=date(2026, 4, 1),
            data_inicio=date(2026, 4, 1),
            observacoes_rdo_pt='nao deve mudar',
        )

        pessoa = Pessoa.objects.create(nome='Carlos Souza')
        payload = {
            'data': '2026-04-05',
            'equipe_nome[]': ['Carlos Souza'],
            'equipe_funcao[]': ['Supervisor'],
            'equipe_pessoa_id[]': [str(pessoa.id)],
            'equipe_em_servico[]': ['true'],
        }

        token_client = Client()
        response = token_client.post(
            f'/api/mobile/v1/rdo/{rdo.id}/edit/',
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_HOST='localhost',
            secure=True,
            HTTP_AUTHORIZATION=f'Bearer {self.token.key}',
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body.get('success'))

        rdo.refresh_from_db()
        self.assertEqual(rdo.data.isoformat(), '2026-04-05')
        self.assertEqual(rdo.data_inicio.isoformat(), '2026-04-05')
        self.assertEqual(rdo.observacoes_rdo_pt, 'nao deve mudar')
        self.assertEqual(rdo.pob, 1)
        self.assertEqual(rdo.membros_equipe.count(), 1)
        self.assertEqual(rdo.membros_equipe.first().pessoa_id, pessoa.id)
        self.assertEqual(rdo.membros_equipe.first().funcao, 'Supervisor')

    def test_mobile_app_update_returns_android_metadata(self):
        token_client = Client()
        env = {
            'MOBILE_APP_DOWNLOAD_ENABLED': '1',
            'MOBILE_APP_ANDROID_AUTO_VERSION': '0',
            'MOBILE_APP_ANDROID_URL': 'https://example.com/releases/ambipar-synchro-v1.0.0+10.apk',
            'MOBILE_APP_ANDROID_VERSION_NAME': '1.0.0+10',
            'MOBILE_APP_ANDROID_BUILD_NUMBER': '10',
            'MOBILE_APP_ANDROID_MIN_SUPPORTED_BUILD': '8',
            'MOBILE_APP_ANDROID_FORCE_UPDATE': '0',
            'MOBILE_APP_ANDROID_RELEASE_NOTES': 'Correcoes e melhorias de sincronizacao.',
        }
        with patch.dict(os.environ, env, clear=False):
            response = token_client.get(
                '/api/mobile/v1/app/update/?platform=android',
                HTTP_HOST='localhost',
                secure=True,
                HTTP_AUTHORIZATION=f'Bearer {self.token.key}',
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertEqual(payload.get('platform'), 'android')

        update = payload.get('update') or {}
        self.assertTrue(update.get('available'))
        self.assertEqual(update.get('version_name'), '1.0.0+10')
        self.assertEqual(update.get('build_number'), 10)
        self.assertEqual(update.get('min_supported_build'), 8)
        self.assertFalse(update.get('force_update'))
        self.assertTrue(str(update.get('download_url') or '').endswith('.apk'))

    def test_mobile_app_update_auto_discovers_latest_android_release(self):
        token_client = Client()
        env = {
            'MOBILE_APP_DOWNLOAD_ENABLED': '1',
            'MOBILE_APP_ANDROID_AUTO_VERSION': '1',
            'MOBILE_APP_ANDROID_URL': '',
            'MOBILE_APP_ANDROID_VERSION_NAME': '',
            'MOBILE_APP_ANDROID_BUILD_NUMBER': '',
            'MOBILE_APP_ANDROID_VERSION_CODE': '',
            'MOBILE_APP_ANDROID_RELEASE_NOTES': 'Atualizacao automatica por APK.',
        }
        discovered = {
            'version_name': '1.0.0+11',
            'build_number': 11,
            'apk_path': '/var/www/html/GESTAO_OPERACIONAL/static/mobile/releases/ambipar-synchro-v1.0.0+11.apk',
        }

        with patch.dict(os.environ, env, clear=False):
            with patch(
                'GO.views_mobile_api._discover_android_release_metadata',
                return_value=discovered,
            ):
                response = token_client.get(
                    '/api/mobile/v1/app/update/?platform=android',
                    HTTP_HOST='localhost',
                    secure=True,
                    HTTP_AUTHORIZATION=f'Bearer {self.token.key}',
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertEqual(payload.get('platform'), 'android')

        update = payload.get('update') or {}
        self.assertTrue(update.get('available'))
        self.assertEqual(update.get('version_name'), '1.0.0+11')
        self.assertEqual(update.get('build_number'), 11)
        self.assertTrue(
            str(update.get('download_url') or '').endswith(
                '/static/mobile/releases/ambipar-synchro-v1.0.0+11.apk'
            )
        )

    def test_mobile_app_update_auto_replaces_latest_alias_with_versioned_url(self):
        token_client = Client()
        env = {
            'MOBILE_APP_DOWNLOAD_ENABLED': '1',
            'MOBILE_APP_ANDROID_AUTO_VERSION': '1',
            'MOBILE_APP_ANDROID_URL': 'https://synchro.ambipar.vps-kinghost.net/static/mobile/releases/ambipar-synchro-latest.apk',
            'MOBILE_APP_ANDROID_VERSION_NAME': '1.0.0+10',
            'MOBILE_APP_ANDROID_BUILD_NUMBER': '10',
        }
        discovered = {
            'version_name': '1.0.0+12',
            'build_number': 12,
            'apk_path': '/var/www/html/GESTAO_OPERACIONAL/static/mobile/releases/ambipar-synchro-v1.0.0+12.apk',
        }

        with patch.dict(os.environ, env, clear=False):
            with patch(
                'GO.views_mobile_api._discover_android_release_metadata',
                return_value=discovered,
            ):
                response = token_client.get(
                    '/api/mobile/v1/app/update/?platform=android',
                    HTTP_HOST='localhost',
                    secure=True,
                    HTTP_AUTHORIZATION=f'Bearer {self.token.key}',
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        update = payload.get('update') or {}
        self.assertEqual(update.get('build_number'), 12)
        self.assertEqual(update.get('version_name'), '1.0.0+12')
        self.assertTrue(
            str(update.get('download_url') or '').endswith(
                '/static/mobile/releases/ambipar-synchro-v1.0.0+12.apk'
            )
        )

    def test_mobile_app_update_requires_authentication(self):
        anon_client = Client()
        response = anon_client.get(
            '/api/mobile/v1/app/update/?platform=android',
            HTTP_HOST='localhost',
            secure=True,
        )
        self.assertEqual(response.status_code, 401)
