from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from GO.models import Cliente, OrdemServico, RDO, Unidade
from GO.rdo_access import (
    RDO_VIEW_ONLY_GROUP_NAME,
    SYSTEM_READ_ONLY_GROUP_NAME,
    ensure_rdo_access_groups,
)


class ReadOnlyAccessTests(TestCase):
    def setUp(self):
        ensure_rdo_access_groups()
        self.read_only_group = Group.objects.get(name=SYSTEM_READ_ONLY_GROUP_NAME)
        self.rdo_view_only_group = Group.objects.get(name=RDO_VIEW_ONLY_GROUP_NAME)
        self.read_only_user = User.objects.create_user(
            username='readonly_user',
            password='senha123',
        )
        self.read_only_user.groups.add(self.read_only_group)
        self.rdo_view_only_user = User.objects.create_user(
            username='rdo_view_only_user',
            password='senha123',
        )
        self.rdo_view_only_user.groups.add(self.rdo_view_only_group)
        self.client.force_login(self.read_only_user)

        self.cliente = Cliente.objects.create(nome='Cliente Read Only')
        self.unidade = Unidade.objects.create(nome='Unidade Read Only')
        self.coordenador = next(value for value, _ in OrdemServico.COORDENADORES if value)
        self.supervisor = User.objects.create_user(
            username='readonly_supervisor_owner',
            password='senha123',
        )

    def _create_os(self):
        return OrdemServico.objects.create(
            numero_os=99001,
            data_inicio=date(2026, 3, 26),
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

    def _edit_payload(self, os_obj):
        return {
            'os_id': str(os_obj.pk),
            'cliente': self.cliente.nome,
            'unidade': self.unidade.nome,
            'solicitante': 'Solicitante Teste',
            'servico': 'COLETA DE AR',
            'metodo': 'Manual',
            'pob': '1',
            'data_inicio': '2026-03-26',
            'tipo_operacao': 'Onshore',
            'status_operacao': 'Programada',
            'status_geral': 'Programada',
            'status_comercial': 'Em aberto',
            'status_planejamento': 'Pendente',
            'coordenador': self.coordenador,
            'supervisor': str(self.supervisor.pk),
            'volume_tanque': '0',
        }

    def _post(self, url, data=None, **extra):
        return self.client.post(
            url,
            data=data or {},
            HTTP_HOST='localhost',
            secure=True,
            **extra,
        )

    def _get(self, url, **extra):
        return self.client.get(
            url,
            HTTP_HOST='localhost',
            secure=True,
            **extra,
        )

    def test_read_only_user_cannot_create_os(self):
        response = self._post(reverse('lista_servicos'), {})

        self.assertEqual(response.status_code, 403)
        self.assertIn('somente para visualizacao', response.json().get('error', '').lower())

    def test_read_only_user_cannot_edit_os(self):
        os_obj = self._create_os()

        response = self.client.post(
            reverse('editar_os_post'),
            data=self._edit_payload(os_obj),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn('somente para visualizacao', response.json().get('error', '').lower())

    def test_read_only_user_cannot_save_equipment(self):
        response = self._post(
            reverse('api_equipamentos_save'),
            data={
                'descricao': 'Bomba Pneumatica',
                'tag': 'TAG-READONLY-1',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn('somente para visualizacao', response.json().get('error', '').lower())

    def test_read_only_user_cannot_create_or_update_rdo(self):
        os_obj = self._create_os()
        rdo = RDO.objects.create(
            ordem_servico=os_obj,
            rdo='1',
            data=date(2026, 3, 26),
            data_inicio=date(2026, 3, 26),
        )

        create_response = self._post(
            reverse('api_rdo_create_ajax'),
            data={'ordem_servico_id': str(os_obj.pk)},
        )
        update_response = self._post(
            reverse('api_rdo_update_ajax'),
            data={'rdo_id': str(rdo.pk)},
        )

        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(update_response.status_code, 403)
        self.assertIn('somente para visualizacao', create_response.json().get('error', '').lower())
        self.assertIn('somente para visualizacao', update_response.json().get('error', '').lower())

    def test_read_only_user_cannot_open_rdo_page(self):
        os_obj = self._create_os()
        rdo = RDO.objects.create(
            ordem_servico=os_obj,
            rdo='1',
            data=date(2026, 3, 26),
            data_inicio=date(2026, 3, 26),
        )

        response = self._get(reverse('rdo_page', args=[rdo.pk]))

        self.assertEqual(response.status_code, 200)

    def test_read_only_user_cannot_load_rdo_editor_detail(self):
        os_obj = self._create_os()
        rdo = RDO.objects.create(
            ordem_servico=os_obj,
            rdo='1',
            data=date(2026, 3, 26),
            data_inicio=date(2026, 3, 26),
        )

        response = self.client.get(
            reverse('rdo_detail', args=[rdo.pk]) + '?render=editor',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn('somente para visualizacao', response.json().get('error', '').lower())

    def test_rdo_view_only_user_can_open_rdo_page(self):
        os_obj = self._create_os()
        rdo = RDO.objects.create(
            ordem_servico=os_obj,
            rdo='1',
            data=date(2026, 3, 26),
            data_inicio=date(2026, 3, 26),
        )
        self.client.force_login(self.rdo_view_only_user)

        response = self._get(reverse('rdo_page', args=[rdo.pk]))

        self.assertEqual(response.status_code, 200)

    def test_rdo_view_only_user_cannot_create_update_or_load_editor_rdo(self):
        os_obj = self._create_os()
        rdo = RDO.objects.create(
            ordem_servico=os_obj,
            rdo='1',
            data=date(2026, 3, 26),
            data_inicio=date(2026, 3, 26),
        )
        self.client.force_login(self.rdo_view_only_user)

        create_response = self._post(
            reverse('api_rdo_create_ajax'),
            data={'ordem_servico_id': str(os_obj.pk)},
        )
        update_response = self._post(
            reverse('api_rdo_update_ajax'),
            data={'rdo_id': str(rdo.pk)},
        )
        detail_response = self._get(
            reverse('rdo_detail', args=[rdo.pk]) + '?render=editor',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(update_response.status_code, 403)
        self.assertEqual(detail_response.status_code, 403)
        self.assertIn('visualizacao do rdo', create_response.json().get('error', '').lower())
        self.assertIn('visualizacao do rdo', update_response.json().get('error', '').lower())
        self.assertIn('visualizacao do rdo', detail_response.json().get('error', '').lower())
