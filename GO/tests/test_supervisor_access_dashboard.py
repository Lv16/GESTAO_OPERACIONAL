from datetime import datetime, timedelta

from django.contrib.auth.models import Group, User
from django.test import RequestFactory
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from GO.models import MobileApiToken, MobileSyncEvent, RDO, SupervisorAccessHeartbeat
from GO.rdo_access import ensure_rdo_access_groups
from GO.supervisor_access_metrics import (
    DISPLAY_TIMEZONE,
    record_rdo_channel_event,
    record_supervisor_access,
)


@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }
)
class SupervisorAccessDashboardViewTest(TestCase):
    def setUp(self):
        groups_info = ensure_rdo_access_groups()
        self.manager_group = groups_info['manager_group']
        self.supervisor_group, _ = Group.objects.get_or_create(name='Supervisor')
        self.url = reverse('supervisor_access_dashboard')

        self.manager_user = User.objects.create_user(username='metrics_manager', password='x')
        self.manager_user.groups.add(self.manager_group)
        self.regular_user = User.objects.create_user(username='metrics_regular', password='x')
        self.supervisor_web = User.objects.create_user(username='sup_web_mobile', password='x')
        self.supervisor_mobile = User.objects.create_user(username='sup_mobile_only', password='x')
        self.supervisor_web.groups.add(self.supervisor_group)
        self.supervisor_mobile.groups.add(self.supervisor_group)
        self.request_factory = RequestFactory()

    def _get(self, user, params=None):
        self.client.force_login(user)
        return self.client.get(self.url, params or {}, HTTP_HOST='localhost', secure=True)

    def test_dashboard_requires_authorized_user(self):
        response = self._get(self.regular_user)
        self.assertEqual(response.status_code, 403)

    def test_record_supervisor_access_deduplicates_same_window(self):
        base_dt = timezone.make_aware(
            datetime(2026, 4, 2, 10, 2, 0),
            timezone=DISPLAY_TIMEZONE,
        )

        record_supervisor_access(
            user=self.supervisor_web,
            channel='web',
            path='/rdo/',
            moment=base_dt,
        )
        record_supervisor_access(
            user=self.supervisor_web,
            channel='web',
            path='/rdo/',
            moment=base_dt + timedelta(minutes=4),
        )
        record_supervisor_access(
            user=self.supervisor_web,
            channel='web',
            path='/rdo/',
            moment=base_dt + timedelta(minutes=5),
        )

        self.assertEqual(
            SupervisorAccessHeartbeat.objects.filter(
                user=self.supervisor_web,
                channel='web',
            ).count(),
            2,
        )

    def test_dashboard_aggregates_web_mobile_usage_and_token_fallback(self):
        base_dt = timezone.make_aware(
            datetime(2026, 4, 2, 14, 0, 0),
            timezone=DISPLAY_TIMEZONE,
        )

        record_supervisor_access(
            user=self.supervisor_web,
            channel='web',
            path='/rdo/',
            moment=base_dt,
        )
        record_supervisor_access(
            user=self.supervisor_web,
            channel='mobile',
            path='/api/mobile/v1/bootstrap/',
            moment=base_dt,
        )

        token = MobileApiToken.objects.create(
            key='b' * 64,
            user=self.supervisor_mobile,
            device_name='Android',
            platform='android',
            is_active=True,
        )
        token.last_used_at = base_dt
        token.save(update_fields=['last_used_at', 'updated_at'])

        response = self._get(
            self.manager_user,
            {
                'date_from': '2026-04-01',
                'date_to': '2026-04-03',
                'days': '30',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_supervisors'], 2)
        self.assertEqual(response.context['active_web_supervisors'], 1)
        self.assertEqual(response.context['active_mobile_supervisors'], 2)
        self.assertEqual(response.context['active_both_supervisors'], 1)
        self.assertEqual(response.context['active_only_mobile_supervisors'], 1)
        self.assertEqual(response.context['active_mobile_tokens'], 1)
        self.assertIsNotNone(response.context['web_peak_row'])
        self.assertEqual(response.context['web_peak_row']['label'], '14:00')
        self.assertIsNotNone(response.context['mobile_peak_row'])
        self.assertEqual(response.context['mobile_peak_row']['label'], '14:00')

        rows = {row['username']: row for row in response.context['supervisor_rows']}
        self.assertTrue(rows['sup_web_mobile']['used_web_in_range'])
        self.assertTrue(rows['sup_web_mobile']['used_mobile_in_range'])
        self.assertFalse(rows['sup_mobile_only']['used_web_in_range'])
        self.assertTrue(rows['sup_mobile_only']['used_mobile_in_range'])
        self.assertIsNotNone(rows['sup_mobile_only']['last_mobile_at'])

        mobile_hour_rows = {row['label']: row for row in response.context['mobile_hour_rows']}
        self.assertEqual(mobile_hour_rows['14:00']['max_count'], 2)
        self.assertGreater(mobile_hour_rows['14:00']['average'], 0)

        self.assertContains(response, 'Métricas de acesso Web x Mobile')
        self.assertContains(response, 'Mobile')

    def test_dashboard_returns_none_peak_when_channel_has_no_hourly_data(self):
        response = self._get(
            self.manager_user,
            {
                'date_from': '2026-04-01',
                'date_to': '2026-04-03',
                'days': '30',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['web_peak_row'])
        self.assertIsNone(response.context['mobile_peak_row'])

    def test_dashboard_aggregates_web_usage_from_last_login_fallback(self):
        base_dt = timezone.make_aware(
            datetime(2026, 4, 2, 9, 30, 0),
            timezone=DISPLAY_TIMEZONE,
        )
        self.supervisor_web.last_login = base_dt
        self.supervisor_web.save(update_fields=['last_login'])

        response = self._get(
            self.manager_user,
            {
                'date_from': '2026-04-01',
                'date_to': '2026-04-03',
                'days': '30',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_web_supervisors'], 1)
        self.assertIsNotNone(response.context['web_peak_row'])
        self.assertEqual(response.context['web_peak_row']['label'], '09:00')

        rows = {row['username']: row for row in response.context['supervisor_rows']}
        self.assertTrue(rows['sup_web_mobile']['used_web_in_range'])
        self.assertIsNotNone(rows['sup_web_mobile']['last_web_at'])

    def test_dashboard_aggregates_rdo_counts_by_channel(self):
        rdo_web = RDO.objects.create(rdo='101')
        rdo_mobile = RDO.objects.create(rdo='102')

        web_request = self.request_factory.post('/rdo/')
        web_request.user = self.supervisor_web
        web_request.session = {}
        record_rdo_channel_event(request=web_request, rdo_obj=rdo_web, event_type='create')
        record_rdo_channel_event(request=web_request, rdo_obj=rdo_web, event_type='update')

        MobileSyncEvent.objects.create(
            client_uuid='11111111-1111-1111-1111-111111111111',
            operation='rdo.create',
            user=self.supervisor_mobile,
            request_payload={'payload': {}},
            response_payload={'rdo': {'id': rdo_mobile.id}},
            state=MobileSyncEvent.STATE_DONE,
            http_status=200,
        )
        MobileSyncEvent.objects.create(
            client_uuid='22222222-2222-2222-2222-222222222222',
            operation='rdo.update',
            user=self.supervisor_mobile,
            request_payload={'payload': {'rdo_id': rdo_mobile.id}},
            response_payload={'rdo': {'id': rdo_mobile.id}},
            state=MobileSyncEvent.STATE_DONE,
            http_status=200,
        )

        response = self._get(
            self.manager_user,
            {
                'date_from': '2026-04-01',
                'date_to': '2026-04-03',
                'days': '30',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['web_rdo_total'], 1)
        self.assertEqual(response.context['web_rdo_created_total'], 1)
        self.assertEqual(response.context['web_rdo_updated_total'], 1)
        self.assertEqual(response.context['mobile_rdo_total'], 1)
        self.assertEqual(response.context['mobile_rdo_created_total'], 1)
        self.assertEqual(response.context['mobile_rdo_updated_total'], 1)

    def test_dashboard_builds_rdo_ranking_rows(self):
        supervisor_web_extra = User.objects.create_user(username='sup_web_extra', password='x')
        supervisor_mobile_extra = User.objects.create_user(username='sup_mobile_extra', password='x')
        supervisor_web_extra.groups.add(self.supervisor_group)
        supervisor_mobile_extra.groups.add(self.supervisor_group)

        rdo_web_1 = RDO.objects.create(rdo='201')
        rdo_web_2 = RDO.objects.create(rdo='202')
        rdo_mobile_1 = RDO.objects.create(rdo='203')
        rdo_mobile_2 = RDO.objects.create(rdo='204')

        web_request = self.request_factory.post('/rdo/')
        web_request.session = {}
        web_request.user = self.supervisor_web
        record_rdo_channel_event(request=web_request, rdo_obj=rdo_web_1, event_type='create')
        record_rdo_channel_event(request=web_request, rdo_obj=rdo_web_2, event_type='create')

        web_request_extra = self.request_factory.post('/rdo/')
        web_request_extra.session = {}
        web_request_extra.user = supervisor_web_extra
        record_rdo_channel_event(request=web_request_extra, rdo_obj=rdo_web_1, event_type='update')

        MobileSyncEvent.objects.create(
            client_uuid='33333333-3333-3333-3333-333333333333',
            operation='rdo.create',
            user=self.supervisor_mobile,
            request_payload={'payload': {}},
            response_payload={'rdo': {'id': rdo_mobile_1.id}},
            state=MobileSyncEvent.STATE_DONE,
            http_status=200,
        )
        MobileSyncEvent.objects.create(
            client_uuid='44444444-4444-4444-4444-444444444444',
            operation='rdo.create',
            user=self.supervisor_mobile,
            request_payload={'payload': {}},
            response_payload={'rdo': {'id': rdo_mobile_2.id}},
            state=MobileSyncEvent.STATE_DONE,
            http_status=200,
        )
        MobileSyncEvent.objects.create(
            client_uuid='55555555-5555-5555-5555-555555555555',
            operation='rdo.update',
            user=supervisor_mobile_extra,
            request_payload={'payload': {'rdo_id': rdo_mobile_1.id}},
            response_payload={'rdo': {'id': rdo_mobile_1.id}},
            state=MobileSyncEvent.STATE_DONE,
            http_status=200,
        )

        response = self._get(
            self.manager_user,
            {
                'date_from': '2026-04-01',
                'date_to': '2026-04-03',
                'days': '30',
            },
        )

        self.assertEqual(response.status_code, 200)

        web_rows = response.context['web_rdo_ranking_rows']
        mobile_rows = response.context['mobile_rdo_ranking_rows']

        self.assertEqual(web_rows[0]['username'], 'sup_web_mobile')
        self.assertEqual(web_rows[0]['total_rdos'], 2)
        self.assertEqual(web_rows[0]['created_rdos'], 2)
        self.assertEqual(web_rows[1]['username'], 'sup_web_extra')
        self.assertEqual(web_rows[1]['total_rdos'], 1)

        self.assertEqual(mobile_rows[0]['username'], 'sup_mobile_only')
        self.assertEqual(mobile_rows[0]['total_rdos'], 2)
        self.assertEqual(mobile_rows[0]['created_rdos'], 2)
        self.assertEqual(mobile_rows[1]['username'], 'sup_mobile_extra')
        self.assertEqual(mobile_rows[1]['updated_rdos'], 1)
