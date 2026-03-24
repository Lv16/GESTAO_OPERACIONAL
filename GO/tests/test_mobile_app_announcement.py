import os
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from GO.mobile_release import resolve_mobile_release_context


class MobileReleaseContextTest(SimpleTestCase):
    def test_resolve_mobile_release_context_prefers_real_apk_over_hml_url(self):
        request = RequestFactory().get('/rdo/')
        apk_path = (
            '/var/www/html/GESTAO_OPERACIONAL/static/mobile/releases/'
            'ambipar-synchro-v1.0.0+27.apk'
        )

        with patch.dict(
            os.environ,
            {
                'MOBILE_APP_ANDROID_URL': 'https://example.com/ambipar-synchro-hml-latest.apk',
                'MOBILE_APP_DOWNLOAD_ENABLED': '1',
            },
            clear=False,
        ):
            with patch('GO.mobile_release.glob', return_value=[apk_path]):
                with patch('GO.mobile_release.os.path.getmtime', return_value=1710200000.0):
                    with patch(
                        'GO.mobile_release.os.path.exists',
                        side_effect=lambda path: path == apk_path,
                    ):
                        context = resolve_mobile_release_context(request)

        self.assertTrue(context['mobile_app_download_enabled'])
        self.assertEqual(context['mobile_app_android_version_name'], '1.0.0+27')
        self.assertEqual(context['mobile_app_android_build_number'], 27)
        self.assertEqual(
            context['mobile_app_android_url'],
            'http://testserver/static/mobile/releases/ambipar-synchro-v1.0.0+27.apk',
        )


@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }
)
class RdoMobileAppAnnouncementViewTest(TestCase):
    def setUp(self):
        self.supervisor_group, _ = Group.objects.get_or_create(name='Supervisor')
        self.supervisor = User.objects.create_user(
            username='sup_mobile_notice',
            password='xpto1234',
        )
        self.supervisor.groups.add(self.supervisor_group)
        self.client.force_login(self.supervisor)
        self.url = reverse('rdo')
        self.release_context = {
            'mobile_app_download_enabled': True,
            'mobile_app_android_url': 'https://testserver/static/mobile/releases/ambipar-synchro-v1.0.0+27.apk',
            'mobile_app_android_version_name': '1.0.0+27',
            'mobile_app_android_build_number': 27,
            'mobile_app_ios_url': '',
        }

    @patch('GO.views_rdo.resolve_mobile_release_context')
    def test_rdo_shows_mobile_app_announcement_for_supervisor_on_mobile(self, mock_release_context):
        mock_release_context.return_value = self.release_context

        response = self.client.get(
            self.url,
            HTTP_USER_AGENT='Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Mobile Safari/537.36',
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Synchro Mobile liberado para download')
        self.assertContains(response, 'Baixar Synchro Mobile')
        self.assertContains(response, self.release_context['mobile_app_android_url'])

    @patch('GO.views_rdo.resolve_mobile_release_context')
    def test_rdo_does_not_show_mobile_app_announcement_outside_mobile(self, mock_release_context):
        mock_release_context.return_value = self.release_context

        response = self.client.get(
            self.url,
            HTTP_USER_AGENT='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36',
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Synchro Mobile liberado para download')
