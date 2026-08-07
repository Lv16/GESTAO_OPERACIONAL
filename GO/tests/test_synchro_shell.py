from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from GO.models import Cliente, OrdemServico, RDO, Unidade
from alertas_inteligentes.models import (
    AlertaInteligente,
    AlertaOperacionalInteligente,
    LeituraAlertaIA,
)
from alertas_inteligentes.services.rdo_immediate_analysis import analisar_rdo_imediatamente
from GO.rdo_access import ALERTS_AI_GROUP_NAME, SYSTEM_READ_ONLY_GROUP_NAME


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

    def _create_operational_alert(self, number=99001, priority='alta', message='Alerta da central'):
        cliente = Cliente.objects.create(nome=f'Cliente {number}')
        unidade = Unidade.objects.create(nome=f'Unidade {number}')
        ordem = OrdemServico.objects.create(
            numero_os=number,
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
        alert = AlertaOperacionalInteligente.objects.create(
            ordem_servico=ordem,
            tipo='OS_SEM_RDO_RECENTE',
            mensagem=message,
            prioridade=priority,
            status='pendente',
        )
        return ordem, alert

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
        self.assertContains(response, 'Não há alertas da IA pendentes desde ontem.')
        self.assertNotContains(response, 'class="synchro-alert-count"')

    def test_active_module_is_resolved_centrally(self):
        response = self.client.get(reverse('equipamentos'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'class="menu-btn is-active" aria-current="page"',
        )

    def test_shared_drawer_contains_planning_and_commercial_modules(self):
        response = self.client.get(reverse('ajuda'))

        self.assertContains(response, f'href="{reverse("planejamento")}"')
        self.assertContains(response, '<span>Planejamento</span>')
        self.assertContains(response, 'id="nav-negocios">Negócios</h2>')
        self.assertContains(response, f'href="{reverse("comercial_propostas")}"')
        self.assertContains(response, '<span>Comercial</span>')
        self.assertContains(response, f'href="{reverse("alertas_inteligentes:listar_alertas")}"')

    def test_new_drawer_modules_are_highlighted_centrally(self):
        planejamento_response = self.client.get(reverse('planejamento'))
        comercial_response = self.client.get(reverse('comercial_propostas'))

        self.assertEqual(planejamento_response.context['synchro_active_module'], 'planejamento')
        self.assertEqual(comercial_response.context['synchro_active_module'], 'comercial')

    def test_commercial_is_coming_soon_for_regular_users(self):
        regular_user = get_user_model().objects.create_user(
            username='shell_regular',
            email='regular@example.com',
            password='test-password',
        )
        self.client.force_login(regular_user)

        menu_response = self.client.get(reverse('ajuda'))
        commercial_url = reverse('comercial_propostas')

        self.assertEqual(menu_response.status_code, 200)
        self.assertContains(menu_response, 'synchro-menu-btn--disabled')
        self.assertContains(menu_response, '<span class="synchro-menu-badge">Em breve</span>')
        self.assertNotContains(menu_response, f'href="{commercial_url}"')

        search_response = self.client.get(reverse('global_search'), {'q': 'Comercial'})
        self.assertEqual(search_response.status_code, 200)
        self.assertFalse(
            any(
                group['title'] == 'Comercial'
                or any(result['url'].startswith(commercial_url) for result in group['results'])
                for group in search_response.json()['groups']
            )
        )

        direct_response = self.client.get(commercial_url)
        self.assertEqual(direct_response.status_code, 403)

    def test_synchro_ai_is_coming_soon_and_blocked_for_non_admins(self):
        regular_user = get_user_model().objects.create_user(
            username='shell_ai_regular',
            email='ai-regular@example.com',
            password='test-password',
        )
        alerts_group, _ = Group.objects.get_or_create(name=ALERTS_AI_GROUP_NAME)
        regular_user.groups.add(alerts_group)
        self.client.force_login(regular_user)

        menu_response = self.client.get(reverse('ajuda'))
        ai_url = reverse('alertas_inteligentes:listar_alertas')

        self.assertEqual(menu_response.status_code, 200)
        self.assertContains(menu_response, '<span>Synchro AI</span>')
        self.assertContains(menu_response, '<span class="synchro-menu-badge">Em breve</span>')
        self.assertNotContains(menu_response, f'href="{ai_url}"')
        self.assertTrue(menu_response.context['can_use_alerts_ai'])
        self.assertFalse(menu_response.context['can_access_synchro_ai'])

        search_response = self.client.get(reverse('global_search'), {'q': 'Synchro AI'})
        self.assertEqual(search_response.status_code, 200)
        self.assertFalse(
            any(
                result['url'].startswith(ai_url)
                for group in search_response.json()['groups']
                for result in group['results']
            )
        )

        direct_response = self.client.get(ai_url)
        self.assertRedirects(direct_response, reverse('home'))

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
        self.assertContains(response, '1 pendente desde ontem')

    def test_daily_ai_counter_also_includes_yesterday_pending_alerts(self):
        cliente = Cliente.objects.create(nome='Cliente Shell Ontem')
        unidade = Unidade.objects.create(nome='Unidade Shell Ontem')
        ordem = OrdemServico.objects.create(
            numero_os=98702,
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
        alert = AlertaOperacionalInteligente.objects.create(
            ordem_servico=ordem,
            tipo='OS_SEM_RDO_RECENTE',
            mensagem='Alerta pendente criado ontem.',
            prioridade='media',
            status='pendente',
        )
        AlertaOperacionalInteligente.objects.filter(pk=alert.pk).update(
            criado_em=timezone.now() - timedelta(days=1),
        )

        response = self.client.get(reverse('ajuda'))

        self.assertContains(response, 'class="synchro-alert-count"')
        self.assertContains(response, 'Alerta pendente criado ontem.')

    def test_notification_center_is_embedded_in_shared_shell_without_redirect(self):
        self._create_operational_alert()

        response = self.client.get(reverse('ajuda'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="ai-notification-center-open"')
        self.assertContains(response, 'id="ai-notification-center"')
        self.assertContains(response, 'role="dialog"')
        self.assertContains(response, 'static/js/ai_notification_center.js')
        self.assertNotContains(
            response,
            f'id="ai-notification-center-open" href="{reverse("alertas_inteligentes:assistente_rdo")}"',
        )

    def test_notification_read_state_is_persisted_per_user_and_updates_unread_badge(self):
        _, alert = self._create_operational_alert(number=99002)
        endpoint = reverse(
            'alertas_inteligentes:api_notificacao_leitura',
            args=['operacional', alert.pk],
        )

        response = self.client.post(
            endpoint,
            data='{"lido": true}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['unread_count'], 0)
        receipt = LeituraAlertaIA.objects.get(usuario=self.user, alerta_operacional=alert)
        self.assertTrue(receipt.lido)
        self.assertIsNotNone(receipt.lido_em)
        shell_response = self.client.get(reverse('ajuda'))
        self.assertNotContains(shell_response, 'class="synchro-alert-count"')

        other_user = get_user_model().objects.create_superuser(
            username='other_ai_admin', email='other@example.com', password='test-password'
        )
        self.client.force_login(other_user)
        other_response = self.client.get(reverse('ajuda'))
        self.assertContains(other_response, 'class="synchro-alert-count"')

    def test_notification_can_be_marked_unread_again(self):
        _, alert = self._create_operational_alert(number=99003)
        endpoint = reverse(
            'alertas_inteligentes:api_notificacao_leitura',
            args=['operacional', alert.pk],
        )
        self.client.post(endpoint, data='{"lido": true}', content_type='application/json')

        response = self.client.post(
            endpoint,
            data='{"lido": false}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['unread_count'], 1)
        receipt = LeituraAlertaIA.objects.get(usuario=self.user, alerta_operacional=alert)
        self.assertFalse(receipt.lido)
        self.assertIsNone(receipt.lido_em)

    def test_opening_notification_detail_does_not_mark_it_as_read(self):
        _, alert = self._create_operational_alert(number=99008)
        detail_url = reverse(
            'alertas_inteligentes:api_notificacao_detalhe',
            args=['operacional', alert.pk],
        )

        response = self.client.get(detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['item']['is_read'])
        self.assertFalse(
            LeituraAlertaIA.objects.filter(usuario=self.user, alerta_operacional=alert).exists()
        )

    def test_rdo_alert_actions_use_editor_deep_link_and_filtered_rdo_page(self):
        ordem, _ = self._create_operational_alert(number=99010)
        rdo = RDO.objects.create(
            ordem_servico=ordem,
            rdo='11',
            data=timezone.localdate(),
        )
        alert = AlertaInteligente.objects.create(
            rdo=rdo,
            tipo='ESPACO_CONFINADO_SEM_HORARIO',
            mensagem='Horários de entrada e saída ausentes.',
            prioridade='alta',
            status='pendente',
        )

        response = self.client.get(
            reverse(
                'alertas_inteligentes:api_notificacao_detalhe',
                args=['rdo', alert.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        item = response.json()['item']
        self.assertIn(f'{reverse("rdo")}?', item['detail_url'])
        self.assertIn('open_editor=1', item['detail_url'])
        self.assertIn(f'rdo_id={rdo.pk}', item['detail_url'])
        self.assertIn('section=tanque', item['detail_url'])
        self.assertEqual(item['os_url'], f'{reverse("rdo")}?os={ordem.numero_os}')

    def test_possible_duplicate_rdo_alert_reaches_notification_center(self):
        ordem, operational_alert = self._create_operational_alert(number=99011)
        operational_alert.delete()
        rdo = RDO.objects.create(
            ordem_servico=ordem,
            rdo='20',
            data=timezone.localdate(),
            turno='Diurno',
        )
        alert = AlertaInteligente.objects.create(
            rdo=rdo,
            tipo='RDO_DUPLICADO',
            mensagem='Os RDOs 20 e 21 podem representar o mesmo relatório.',
            prioridade='alta',
            status='pendente',
        )

        response = self.client.get(
            reverse(
                'alertas_inteligentes:api_notificacao_detalhe',
                args=['rdo', alert.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        item = response.json()['item']
        self.assertEqual(item['type'], 'RDO_DUPLICADO')
        self.assertEqual(item['type_label'], 'Possível RDO duplicado')
        self.assertEqual(item['target_section'], 'identificacao')
        self.assertIn('RDOs 20 e 21', item['message'])
        self.assertIn(f'rdo_id={rdo.pk}', item['detail_url'])

    def test_notification_api_filters_tabs_search_priority_and_marks_all(self):
        self._create_operational_alert(number=99004, priority='alta', message='Pressão crítica na unidade')
        self._create_operational_alert(number=99005, priority='baixa', message='Revisão documental')
        list_url = reverse('alertas_inteligentes:api_notificacoes')

        filtered = self.client.get(list_url, {'q': '99004', 'prioridade': 'alta', 'tab': 'pendentes'})

        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.json()['total'], 1)
        self.assertEqual(filtered.json()['items'][0]['os_number'], 99004)
        mark_all = self.client.post(
            reverse('alertas_inteligentes:api_notificacoes_marcar_todas_lidas'),
            data='{}',
            content_type='application/json',
        )
        self.assertEqual(mark_all.status_code, 200)
        self.assertEqual(mark_all.json()['unread_count'], 0)
        self.assertEqual(self.client.get(list_url, {'tab': 'pendentes'}).json()['total'], 0)
        self.assertEqual(self.client.get(list_url, {'tab': 'lidas'}).json()['total'], 2)

    def test_notification_center_lists_full_history_while_header_keeps_daily_preview(self):
        _, alert = self._create_operational_alert(number=99009, message='Alerta histórico da IA')
        AlertaOperacionalInteligente.objects.filter(pk=alert.pk).update(
            criado_em=timezone.now() - timedelta(days=30),
        )

        central_response = self.client.get(
            reverse('alertas_inteligentes:api_notificacoes'),
            {'tab': 'todas'},
        )
        shell_response = self.client.get(reverse('ajuda'))

        self.assertEqual(central_response.status_code, 200)
        self.assertEqual(central_response.json()['total'], 1)
        self.assertEqual(central_response.json()['items'][0]['os_number'], 99009)
        self.assertNotContains(shell_response, 'class="synchro-alert-count"')

    def test_notification_api_rejects_user_without_ai_permission(self):
        regular = get_user_model().objects.create_user(
            username='no_ai_access', email='no-ai@example.com', password='test-password'
        )
        self.client.force_login(regular)

        response = self.client.get(reverse('alertas_inteligentes:api_notificacoes'))

        self.assertEqual(response.status_code, 403)

    def test_supervisor_notification_api_preserves_own_os_restriction(self):
        supervisor = get_user_model().objects.create_user(
            username='notification_supervisor',
            email='supervisor-notification@example.com',
            password='test-password',
        )
        supervisor.groups.add(Group.objects.get_or_create(name='Supervisor')[0])
        supervisor.groups.add(Group.objects.get_or_create(name='IA - Alertas')[0])
        own_order, _ = self._create_operational_alert(number=99006)
        self._create_operational_alert(number=99007)
        own_order.supervisor = supervisor
        own_order.save(update_fields=['supervisor'])
        self.client.force_login(supervisor)

        response = self.client.get(
            reverse('alertas_inteligentes:api_notificacoes'),
            {'tab': 'todas'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['total'], 1)
        self.assertEqual(response.json()['items'][0]['os_number'], 99006)

    def test_immediate_rdo_analysis_updates_status_and_resolves_stale_alerts(self):
        cliente = Cliente.objects.create(nome='Cliente Análise Imediata')
        unidade = Unidade.objects.create(nome='Unidade Análise Imediata')
        ordem = OrdemServico.objects.create(
            numero_os=98703,
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
        rdo = RDO.objects.create(
            ordem_servico=ordem,
            rdo='1',
            data=timezone.localdate(),
        )
        stale_alert = AlertaInteligente.objects.create(
            rdo=rdo,
            tipo='RDO_SEM_TURNO',
            mensagem='Pendência anterior.',
            prioridade='media',
            status='pendente',
        )

        with patch(
            'alertas_inteligentes.services.rdo_validator.validar_rdo',
            return_value=[],
        ):
            result = analisar_rdo_imediatamente(rdo.pk)

        rdo.refresh_from_db()
        stale_alert.refresh_from_db()
        self.assertTrue(result['processed'])
        self.assertEqual(rdo.status_analise_ia, 'analisado')
        self.assertEqual(stale_alert.status, 'resolvido')

    def test_reanalysis_does_not_recreate_missing_shift_alert_when_shift_is_filled(self):
        cliente = Cliente.objects.create(nome='Cliente Turno Preenchido')
        unidade = Unidade.objects.create(nome='Unidade Turno Preenchido')
        ordem = OrdemServico.objects.create(
            numero_os=98704,
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
        rdo = RDO.objects.create(
            ordem_servico=ordem,
            rdo='1',
            data=timezone.localdate(),
            turno='Diurno',
            status_analise_ia='pendente',
        )
        stale_alert = AlertaInteligente.objects.create(
            rdo=rdo,
            tipo='RDO_SEM_TURNO',
            mensagem='Alerta antigo de turno ausente.',
            prioridade='media',
            status='pendente',
        )

        result = analisar_rdo_imediatamente(rdo.pk)

        stale_alert.refresh_from_db()
        self.assertTrue(result['processed'])
        self.assertEqual(stale_alert.status, 'resolvido')
        self.assertFalse(
            AlertaInteligente.objects.filter(
                rdo=rdo,
                tipo='RDO_SEM_TURNO',
                status='pendente',
            ).exists()
        )

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

    def test_global_search_recognizes_curva_s_as_technical_report(self):
        response = self.client.get(reverse('global_search'), {'q': 'curva s'})

        self.assertEqual(response.status_code, 200)
        navigation = next(
            group for group in response.json()['groups']
            if group['title'] == 'Navegação'
        )
        technical_result = next(
            result for result in navigation['results']
            if result['title'] == 'Relatório Técnico'
        )
        self.assertEqual(technical_result['url'], reverse('curva_s'))

    def test_global_search_opens_technical_report_for_requested_os(self):
        cliente = Cliente.objects.create(nome='Cliente Curva S')
        unidade = Unidade.objects.create(nome='Unidade Curva S')
        ordem = OrdemServico.objects.create(
            numero_os=6298,
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
        RDO.objects.create(
            ordem_servico=ordem,
            rdo='1',
            data=timezone.localdate(),
        )

        search_response = self.client.get(
            reverse('global_search'),
            {'q': '6298 curva s'},
        )

        self.assertEqual(search_response.status_code, 200)
        technical_group = next(
            group for group in search_response.json()['groups']
            if group['title'] == 'Relatório Técnico'
        )
        self.assertEqual(len(technical_group['results']), 1)
        result = technical_group['results'][0]
        self.assertEqual(result['title'], 'Relatório Técnico · OS 6298')
        self.assertEqual(result['url'], f"{reverse('curva_s')}?os=6298")

        report_response = self.client.get(result['url'])
        self.assertEqual(report_response.status_code, 200)
        self.assertContains(
            report_response,
            f'<option value="{ordem.id}" selected>OS 6298</option>',
            html=True,
        )

    def test_global_search_infers_curva_s_while_user_is_still_typing(self):
        cliente = Cliente.objects.create(nome='Cliente Curva Progressiva')
        unidade = Unidade.objects.create(nome='Unidade Curva Progressiva')
        ordem = OrdemServico.objects.create(
            numero_os=6299,
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
        RDO.objects.create(
            ordem_servico=ordem,
            rdo='1',
            data=timezone.localdate(),
        )

        for query in ('6299 c', '6299 cu', '6299 cur', '6299 curva'):
            with self.subTest(query=query):
                response = self.client.get(reverse('global_search'), {'q': query})
                technical_group = next(
                    group for group in response.json()['groups']
                    if group['title'] == 'Relatório Técnico'
                )
                self.assertEqual(
                    technical_group['results'][0]['url'],
                    f"{reverse('curva_s')}?os=6299",
                )

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
