from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from GO.models import Cliente, OrdemServico, RDO, Unidade


class RdoOsStatusSyncTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.cliente = Cliente.objects.create(nome='Cliente RDO Status')
        self.unidade = Unidade.objects.create(nome='Unidade RDO Status')
        self.coordenador = next(value for value, _ in OrdemServico.COORDENADORES if value)
        self.supervisor_group, _ = Group.objects.get_or_create(name='Supervisor')
        self.supervisor = User.objects.create_user(
            username='supervisor_rdo_status_sync',
            password='senha123',
        )
        self.supervisor_group.user_set.add(self.supervisor)
        self.client.force_login(self.supervisor)

    def _create_os(self, numero_os, status_operacao='Programada', status_geral='Programada'):
        return OrdemServico.objects.create(
            numero_os=numero_os,
            data_inicio=date(2026, 3, 10),
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
            status_operacao=status_operacao,
            status_geral=status_geral,
            status_comercial='Em aberto',
            status_planejamento='Pendente',
        )

    def test_create_rdo_promove_linhas_programadas_da_mesma_os_para_em_andamento(self):
        os_principal = self._create_os(numero_os=6043)
        os_mesma_ordem = self._create_os(numero_os=6043)
        os_paralizada = self._create_os(numero_os=6043, status_operacao='Paralizada', status_geral='Paralizada')
        os_outra_ordem = self._create_os(numero_os=6044)

        with patch('GO.views_rdo.agendar_analise_rdo') as schedule_analysis:
            response = self.client.post(
                reverse('rdo_create_ajax'),
                data={
                    'ordem_servico_id': str(os_principal.pk),
                    'data': '2026-03-10',
                },
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                HTTP_HOST='localhost',
                secure=True,
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertTrue(payload.get('status_promovido_em_andamento'))
        self.assertEqual(payload.get('same_os_status_updates'), 2)
        schedule_analysis.assert_called_once()

        os_principal.refresh_from_db()
        os_mesma_ordem.refresh_from_db()
        os_paralizada.refresh_from_db()
        os_outra_ordem.refresh_from_db()

        self.assertEqual(os_principal.status_operacao, 'Em Andamento')
        self.assertEqual(os_principal.status_geral, 'Em Andamento')
        self.assertEqual(os_mesma_ordem.status_operacao, 'Em Andamento')
        self.assertEqual(os_mesma_ordem.status_geral, 'Em Andamento')
        self.assertEqual(os_paralizada.status_operacao, 'Paralizada')
        self.assertEqual(os_paralizada.status_geral, 'Paralizada')
        self.assertEqual(os_outra_ordem.status_operacao, 'Programada')
        self.assertEqual(os_outra_ordem.status_geral, 'Programada')

    def test_update_rdo_promove_linhas_programadas_da_mesma_os_para_em_andamento(self):
        os_principal = self._create_os(numero_os=6045)
        os_mesma_ordem = self._create_os(numero_os=6045)
        os_finalizada = self._create_os(numero_os=6045, status_operacao='Finalizada', status_geral='Finalizada')
        rdo = RDO.objects.create(
            ordem_servico=os_principal,
            rdo='1',
            data=date(2026, 3, 10),
            data_inicio=date(2026, 3, 10),
        )

        response = self.client.post(
            reverse('rdo_update_ajax'),
            data={
                'rdo_id': str(rdo.pk),
                'data': '2026-03-10',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertTrue(payload.get('status_promovido_em_andamento'))
        self.assertEqual(payload.get('same_os_status_updates'), 2)

        os_principal.refresh_from_db()
        os_mesma_ordem.refresh_from_db()
        os_finalizada.refresh_from_db()

        self.assertEqual(os_principal.status_operacao, 'Em Andamento')
        self.assertEqual(os_principal.status_geral, 'Em Andamento')
        self.assertEqual(os_mesma_ordem.status_operacao, 'Em Andamento')
        self.assertEqual(os_mesma_ordem.status_geral, 'Em Andamento')
        self.assertEqual(os_finalizada.status_operacao, 'Finalizada')
        self.assertEqual(os_finalizada.status_geral, 'Finalizada')

    def test_create_rdo_para_supervisor_respeita_sequencia_global_da_mesma_numero_os(self):
        outro_supervisor = User.objects.create_user(
            username='supervisor_rdo_status_sync_2',
            password='senha123',
        )
        self.supervisor_group.user_set.add(outro_supervisor)

        os_supervisor_1 = self._create_os(numero_os=6046)
        os_supervisor_2 = self._create_os(numero_os=6046)
        os_supervisor_2.supervisor = outro_supervisor
        os_supervisor_2.save(update_fields=['supervisor'])

        for numero in range(1, 16):
            RDO.objects.create(
                ordem_servico=os_supervisor_1,
                rdo=str(numero),
                data=date(2026, 3, 10),
                data_inicio=date(2026, 3, 10),
            )

        self.client.force_login(outro_supervisor)
        response = self.client.post(
            reverse('rdo_create_ajax'),
            data={
                'ordem_servico_id': str(os_supervisor_2.pk),
                'data': '2026-03-10',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))

        criado = RDO.objects.get(pk=payload['id'])
        self.assertEqual(criado.rdo, '16')
        self.assertEqual(
            RDO.objects.filter(ordem_servico__numero_os=6046, rdo='15').count(),
            1,
        )
        self.assertEqual(
            RDO.objects.filter(ordem_servico__numero_os=6046, rdo='16').count(),
            1,
        )

    def test_next_rdo_para_supervisor_usa_ultima_sequencia_global_da_mesma_numero_os(self):
        outro_supervisor = User.objects.create_user(
            username='supervisor_rdo_status_sync_3',
            password='senha123',
        )
        self.supervisor_group.user_set.add(outro_supervisor)

        os_supervisor = self._create_os(numero_os=6047)
        os_supervisor.supervisor = outro_supervisor
        os_supervisor.save(update_fields=['supervisor'])
        os_mesma_numero_os = self._create_os(numero_os=6047)
        os_outra_linha = self._create_os(numero_os=7001)

        for numero in range(1, 15):
            RDO.objects.create(
                ordem_servico=os_supervisor,
                rdo=str(numero),
                data=date(2026, 3, 10),
                data_inicio=date(2026, 3, 10),
            )

        RDO.objects.create(
            ordem_servico=os_mesma_numero_os,
            rdo='29',
            data=date(2026, 3, 10),
            data_inicio=date(2026, 3, 10),
        )

        RDO.objects.create(
            ordem_servico=os_outra_linha,
            rdo='9991',
            data=date(2026, 3, 10),
            data_inicio=date(2026, 3, 10),
        )

        self.client.force_login(outro_supervisor)
        response = self.client.get(
            reverse('api_rdo_next'),
            data={'os_id': str(os_supervisor.pk)},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertEqual(payload.get('next_rdo'), 30)

    def test_create_rdo_para_supervisor_usa_sequencia_global_da_mesma_numero_os(self):
        outro_supervisor = User.objects.create_user(
            username='supervisor_rdo_status_sync_4',
            password='senha123',
        )
        self.supervisor_group.user_set.add(outro_supervisor)

        os_supervisor = self._create_os(numero_os=6048)
        os_supervisor.supervisor = outro_supervisor
        os_supervisor.save(update_fields=['supervisor'])
        os_mesma_numero_os = self._create_os(numero_os=6048)
        os_outra_linha = self._create_os(numero_os=7002)

        for numero in range(1, 15):
            RDO.objects.create(
                ordem_servico=os_supervisor,
                rdo=str(numero),
                data=date(2026, 3, 10),
                data_inicio=date(2026, 3, 10),
            )

        RDO.objects.create(
            ordem_servico=os_mesma_numero_os,
            rdo='29',
            data=date(2026, 3, 10),
            data_inicio=date(2026, 3, 10),
        )

        RDO.objects.create(
            ordem_servico=os_outra_linha,
            rdo='9991',
            data=date(2026, 3, 10),
            data_inicio=date(2026, 3, 10),
        )

        self.client.force_login(outro_supervisor)
        response = self.client.post(
            reverse('rdo_create_ajax'),
            data={
                'ordem_servico_id': str(os_supervisor.pk),
                'data': '2026-03-10',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))

        criado = RDO.objects.get(pk=payload['id'])
        self.assertEqual(criado.rdo, '30')
        self.assertEqual(
            RDO.objects.filter(ordem_servico__numero_os=6048, rdo='14').count(),
            1,
        )
        self.assertEqual(
            RDO.objects.filter(ordem_servico__numero_os=6048, rdo='29').count(),
            1,
        )
        self.assertEqual(
            RDO.objects.filter(ordem_servico__numero_os=6048, rdo='30').count(),
            1,
        )
        self.assertEqual(
            RDO.objects.filter(ordem_servico=os_outra_linha, rdo='9991').count(),
            1,
        )

    def test_rdo_os_rdos_para_supervisor_lista_rdos_da_mesma_numero_os_independente_do_supervisor(self):
        outro_supervisor = User.objects.create_user(
            username='supervisor_rdo_status_sync_5',
            password='senha123',
        )
        terceiro_supervisor = User.objects.create_user(
            username='supervisor_rdo_status_sync_6',
            password='senha123',
        )
        self.supervisor_group.user_set.add(outro_supervisor)
        self.supervisor_group.user_set.add(terceiro_supervisor)

        os_supervisor = self._create_os(numero_os=6049)
        os_supervisor.supervisor = outro_supervisor
        os_supervisor.save(update_fields=['supervisor'])

        os_mesma_linha_outro_supervisor = self._create_os(numero_os=6049)
        os_mesma_linha_outro_supervisor.supervisor = terceiro_supervisor
        os_mesma_linha_outro_supervisor.save(update_fields=['supervisor'])

        rdo_14 = RDO.objects.create(
            ordem_servico=os_supervisor,
            rdo='14',
            data=date(2026, 3, 10),
            data_inicio=date(2026, 3, 10),
        )
        rdo_15 = RDO.objects.create(
            ordem_servico=os_mesma_linha_outro_supervisor,
            rdo='15',
            data=date(2026, 3, 10),
            data_inicio=date(2026, 3, 10),
        )

        self.client.force_login(outro_supervisor)
        response = self.client.get(
            reverse('api_rdo_os_rdos', args=[os_supervisor.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))

        returned_ids = {item.get('id') for item in payload.get('rdos', [])}
        self.assertIn(rdo_14.id, returned_ids)
        self.assertIn(rdo_15.id, returned_ids)

    def test_create_rdo_recupera_quando_reserva_colide_com_validationerror_de_duplicidade(self):
        os_principal = self._create_os(numero_os=6376)
        RDO.objects.create(
            ordem_servico=os_principal,
            rdo='15',
            data=date(2026, 3, 10),
            data_inicio=date(2026, 3, 10),
        )

        from GO import views_rdo

        original_safe_save = views_rdo._safe_save_global
        collision_state = {'raised': False}

        def fake_safe_save(obj, *args, **kwargs):
            if (
                not collision_state['raised']
                and isinstance(obj, RDO)
                and getattr(obj, 'pk', None) is None
                and getattr(obj, 'rdo', None) == '16'
            ):
                collision_state['raised'] = True
                RDO.objects.create(
                    ordem_servico=os_principal,
                    rdo='16',
                    data=date(2026, 3, 10),
                    data_inicio=date(2026, 3, 10),
                )
                raise ValidationError({
                    'rdo': 'Ja existe um RDO 16 na OS 6376. O numero do RDO precisa ser unico dentro da OS.'
                })
            return original_safe_save(obj, *args, **kwargs)

        with patch('GO.views_rdo._safe_save_global', side_effect=fake_safe_save):
            response = self.client.post(
                reverse('rdo_create_ajax'),
                data={
                    'ordem_servico_id': str(os_principal.pk),
                    'data': '2026-03-10',
                },
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                HTTP_HOST='localhost',
                secure=True,
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))

        criado = RDO.objects.get(pk=payload['id'])
        self.assertEqual(criado.rdo, '17')
        self.assertEqual(
            RDO.objects.filter(ordem_servico__numero_os=6376, rdo='16').count(),
            1,
        )
        self.assertEqual(
            RDO.objects.filter(ordem_servico__numero_os=6376, rdo='17').count(),
            1,
        )
