from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from GO.models import Cliente, OrdemServico, RDO, Unidade
from alertas_inteligentes.models import AlertaOperacionalInteligente
from GO.rdo_access import SYSTEM_READ_ONLY_GROUP_NAME


@override_settings(
    STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage',
)
class SynchroShellTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='shell_admin',
            email='shell@example.com',
            password='test-password',
            first_name='Ana',
            last_name='Silva',
        )
        self.client.force_login(self.user)

    def test_shared_shell_is_closed_and_accessible_by_default(self):
        response = self.client.get(reverse('ajuda'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="synchro-drawer-nav"')
        self.assertContains(response, 'aria-hidden="true"')
        self.assertContains(response, 'id="synchro-menu-toggle"')
        self.assertContains(response, 'aria-expanded="false"')
        self.assertContains(response, 'Buscar no Synchro...')
        self.assertNotContains(response, 'help</span>')

    def test_header_uses_existing_logout_url_and_real_empty_alert_state(self):
        response = self.client.get(reverse('ajuda'))

        self.assertContains(response, f'action="{reverse("logout")}"')
        self.assertContains(response, 'Alertas diários da IA')
        self.assertContains(response, 'Não há alertas diários da IA pendentes.')
        self.assertNotContains(response, 'class="synchro-alert-count"')

    def test_active_module_is_resolved_centrally(self):
        response = self.client.get(reverse('equipamentos'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'class="menu-btn is-active" aria-current="page"',
        )

    def test_home_uses_the_redesigned_workspace_without_table_selection(self):
        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="home-main"')
        self.assertContains(response, 'id="filter-toggle"')
        self.assertContains(response, 'id="campos-filtro"')
        table_markup = response.content.decode().split('<table class="home-os-table', 1)[1].split('</table>', 1)[0]
        self.assertNotIn('type="checkbox"', table_markup)

    def test_daily_ai_counter_uses_real_pending_alerts(self):
        cliente = Cliente.objects.create(nome='Cliente Shell')
        unidade = Unidade.objects.create(nome='Unidade Shell')
        ordem = OrdemServico.objects.create(
            numero_os=98701,
            data_inicio=timezone.localdate(),
            dias_de_operacao=1,
            servico=OrdemServico.SERVICO_CHOICES[0][0],
            metodo='Manual',
            pob=1,
            volume_tanque=0,
            Cliente=cliente,
            Unidade=unidade,
            tipo_operacao='Onshore',
            solicitante='Teste',
        )
        AlertaOperacionalInteligente.objects.create(
            ordem_servico=ordem,
            tipo='OS_SEM_RDO_RECENTE',
            mensagem='Alerta real criado pelo teste.',
            prioridade='alta',
            status='pendente',
        )

        response = self.client.get(reverse('ajuda'))

        self.assertContains(response, 'class="synchro-alert-count"')
        self.assertContains(response, 'Alerta real criado pelo teste.')
        self.assertContains(response, '1 pendente hoje')

    def test_global_search_returns_only_limited_real_os_results(self):
        cliente = Cliente.objects.create(nome='Cliente Busca')
        unidade = Unidade.objects.create(nome='Unidade Busca')
        for number in range(7020, 7027):
            OrdemServico.objects.create(
                numero_os=number,
                data_inicio=timezone.localdate(),
                dias_de_operacao=1,
                servico=OrdemServico.SERVICO_CHOICES[0][0],
                metodo='Manual', pob=1, volume_tanque=0,
                Cliente=cliente, Unidade=unidade,
                tipo_operacao='Onshore', solicitante='Teste',
            )

        response = self.client.get(reverse('global_search'), {'q': '702'})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        os_group = next(group for group in payload['groups'] if group['title'] == 'Ordens de Serviço')
        self.assertEqual(len(os_group['results']), 5)
        self.assertEqual(os_group['results'][0]['title'], 'OS 7026')
        self.assertIn('?numero_os=', os_group['results'][0]['url'])

    def test_global_search_requires_authentication(self):
        self.client.logout()
        response = self.client.get(reverse('global_search'), {'q': 'OS'})
        self.assertEqual(response.status_code, 302)

    def test_rdo_search_opens_the_rdo_workspace_instead_of_the_document_page(self):
        cliente = Cliente.objects.create(nome='Cliente RDO Busca')
        unidade = Unidade.objects.create(nome='Unidade RDO Busca')
        ordem = OrdemServico.objects.create(
            numero_os=6298, data_inicio=timezone.localdate(), dias_de_operacao=1,
            servico=OrdemServico.SERVICO_CHOICES[0][0], metodo='Manual', pob=1,
            volume_tanque=0, Cliente=cliente, Unidade=unidade,
            tipo_operacao='Onshore', solicitante='Teste',
        )
        rdo = RDO.objects.create(ordem_servico=ordem, rdo='34', data=timezone.localdate())

        response = self.client.get(reverse('global_search'), {'q': '6298'})
        payload = response.json()
        rdo_group = next(group for group in payload['groups'] if group['title'] == 'RDO')
        result = next(item for item in rdo_group['results'] if item['title'] == 'RDO 34')

        self.assertTrue(result['url'].startswith(f"{reverse('rdo')}?rdo_id={rdo.id}"))
        self.assertNotIn('/page/', result['url'])

    def test_global_search_hides_registration_and_client_results_for_read_only_user(self):
        Cliente.objects.create(nome='Cliente Restrito')
        read_only = get_user_model().objects.create_user(
            username='shell_read_only', password='test-password',
        )
        group, _ = Group.objects.get_or_create(name=SYSTEM_READ_ONLY_GROUP_NAME)
        read_only.groups.add(group)
        self.client.force_login(read_only)

        response = self.client.get(reverse('global_search'), {'q': 'Cliente'})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(any(group['title'] == 'Clientes e Unidades' for group in payload['groups']))
        navigation = next((group for group in payload['groups'] if group['title'] == 'Navegação'), {'results': []})
        self.assertNotIn('Cadastrar Cliente', [item['title'] for item in navigation['results']])
