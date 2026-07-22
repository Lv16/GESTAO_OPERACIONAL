from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from GO.rdo_access import ensure_rdo_access_groups


class AssistenteInteligentePermissaoTests(TestCase):
    def setUp(self):
        groups_info = ensure_rdo_access_groups()
        self.alerts_ai_group = groups_info["alerts_ai_group"]
        self.url = reverse("alertas_inteligentes:assistente_rdo")

    def test_usuario_sem_grupo_ia_e_redirecionado(self):
        user = User.objects.create_user(username="sem_ia", password="senha123")
        self.client.force_login(user)

        resposta = self.client.get(self.url, HTTP_HOST="localhost", secure=True)

        self.assertEqual(resposta.status_code, 302)

    def test_usuario_com_grupo_ia_pode_acessar(self):
        user = User.objects.create_user(username="com_ia", password="senha123")
        user.groups.add(self.alerts_ai_group)
        self.client.force_login(user)

        resposta = self.client.get(self.url, HTTP_HOST="localhost", secure=True)

        self.assertEqual(resposta.status_code, 200)
