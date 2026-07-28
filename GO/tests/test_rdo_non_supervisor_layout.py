from datetime import date, timedelta

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse

from GO.models import Cliente, OrdemServico, RDO, Unidade


@override_settings(
    STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage',
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    },
)
class RdoNonSupervisorLayoutTest(TestCase):
    def setUp(self):
        self.supervisor_group, _ = Group.objects.get_or_create(name='Supervisor')
        self.supervisor = User.objects.create_user(username='rdo_supervisor_layout', password='senha')
        self.supervisor.groups.add(self.supervisor_group)
        self.admin_user = User.objects.create_user(
            username='rdo_admin_layout',
            password='senha',
            is_staff=True,
            is_superuser=True,
        )

    def test_supervisor_keeps_legacy_rdo_without_admin_assets(self):
        self.client.force_login(self.supervisor)

        response = self.client.get(reverse('rdo'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'css/rdo.mobile.css')
        self.assertContains(response, 'css/rdo.supervisor.css')
        self.assertNotContains(response, 'css/rdo_nao_supervisor.css')
        self.assertNotContains(response, 'js/rdo_nao_supervisor.js')
        self.assertNotContains(response, 'js/synchro_shell.js')
        self.assertNotContains(response, 'rdo-admin-layout')

    def test_non_supervisor_receives_scoped_admin_assets(self):
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse('rdo'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'css/rdo.mobile.css')
        # O modal "Gerar RDO" é compartilhado com administradores e depende
        # desta folha, cujos seletores são isolados em #supv-modal-overlay.
        self.assertContains(response, 'css/rdo.supervisor.css')
        self.assertContains(response, 'css/rdo_nao_supervisor.css')
        self.assertContains(response, 'js/rdo_nao_supervisor.js')
        self.assertContains(response, 'js/synchro_shell.js')
        self.assertContains(response, 'rdo-synchro-header-guard')
        self.assertContains(response, 'enforceSynchroSearchField')
        self.assertContains(response, 'rdo-admin-layout')
        self.assertContains(response, 'rdo-admin-select-all')
        self.assertContains(response, 'rdo-admin-selection-bar')

        content = response.content.decode()
        self.assertLess(
            content.index('css/rdo_nao_supervisor.css'),
            content.index('css/synchro_shell.css'),
        )

    def test_non_supervisor_pagination_changes_the_rdo_page(self):
        cliente = Cliente.objects.create(nome='Cliente Paginação RDO')
        unidade = Unidade.objects.create(nome='Unidade Paginação RDO')
        ordem = OrdemServico.objects.create(
            numero_os=99101,
            data_inicio=date(2026, 7, 1),
            dias_de_operacao=1,
            servico='LIMPEZA DE DUTO',
            metodo='Manual',
            observacao='',
            pob=1,
            tanque='',
            volume_tanque='10.00',
            Cliente=cliente,
            Unidade=unidade,
            tipo_operacao='Onshore',
            solicitante='Teste',
        )
        for index in range(7):
            RDO.objects.create(
                ordem_servico=ordem,
                rdo=str(100 + index),
                data=date(2026, 7, 1) + timedelta(days=index),
                data_inicio=date(2026, 7, 1) + timedelta(days=index),
            )

        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('rdo'), {'page': 2, 'per_page': 6})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mostrando 7')
        self.assertContains(response, '?page=1')
