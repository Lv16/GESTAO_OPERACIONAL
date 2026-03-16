import tempfile
from datetime import date

from django.contrib.auth.models import Group, Permission, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings

from GO.models import Cliente, OrdemServico, RDO, RDOAtividade, RDOMembroEquipe, RdoTanque, Unidade
from GO.views_rdo import delete_rdo_ajax


class DeleteRdoAjaxTest(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.admin = User.objects.create_user(username='admin_delete_rdo', password='x', is_staff=True, is_superuser=True)
        self.supervisor_group, _ = Group.objects.get_or_create(name='Supervisor')
        self.supervisor_owner = User.objects.create_user(username='sup_owner_delete', password='x')
        self.supervisor_owner.groups.add(self.supervisor_group)
        self.supervisor_other = User.objects.create_user(username='sup_other_delete', password='x')
        self.supervisor_other.groups.add(self.supervisor_group)
        self.user_with_delete_perm = User.objects.create_user(username='delete_perm_user', password='x')
        self.regular_user = User.objects.create_user(username='regular_no_delete', password='x')
        self.delete_rdo_permission = Permission.objects.get(codename='delete_rdo')
        self.user_with_delete_perm.user_permissions.add(self.delete_rdo_permission)

        self.cliente = Cliente.objects.create(nome='Cliente Delete RDO')
        self.unidade = Unidade.objects.create(nome='Unidade Delete RDO')

    def _make_ordem_servico(self, numero_os, supervisor):
        return OrdemServico.objects.create(
            numero_os=numero_os,
            data_inicio=date(2026, 3, 13),
            dias_de_operacao=1,
            servico='LIMPEZA DE DUTO',
            metodo='Manual',
            observacao='',
            pob=1,
            tanque='',
            volume_tanque='10.00',
            Cliente=self.cliente,
            Unidade=self.unidade,
            tipo_operacao='Onshore',
            solicitante='Teste',
            supervisor=supervisor,
        )

    @override_settings(MEDIA_ROOT=tempfile.gettempdir())
    def test_delete_rdo_exclui_registro_e_filhos_em_cascata(self):
        ordem = self._make_ordem_servico(9001, self.supervisor_owner)
        rdo = RDO.objects.create(
            ordem_servico=ordem,
            rdo='77',
            data=date(2026, 3, 13),
            data_inicio=date(2026, 3, 13),
            fotos_1=SimpleUploadedFile('delete-rdo-photo.jpg', b'filecontent', content_type='image/jpeg'),
        )
        tanque = RdoTanque.objects.create(rdo=rdo, tanque_codigo='TK-77')
        atividade = RDOAtividade.objects.create(rdo=rdo, ordem=1, atividade='dds')
        membro = RDOMembroEquipe.objects.create(rdo=rdo, nome='Pessoa Teste', funcao='Supervisor')

        req = self.rf.post(f'/api/rdo/{rdo.id}/delete/', {'rdo_id': rdo.id})
        req.user = self.admin

        res = delete_rdo_ajax(req, rdo.id)

        self.assertEqual(res.status_code, 200)
        self.assertFalse(RDO.objects.filter(pk=rdo.id).exists())
        self.assertFalse(RdoTanque.objects.filter(pk=tanque.id).exists())
        self.assertFalse(RDOAtividade.objects.filter(pk=atividade.id).exists())
        self.assertFalse(RDOMembroEquipe.objects.filter(pk=membro.id).exists())

    def test_delete_rdo_bloqueia_supervisor_de_outra_os(self):
        ordem = self._make_ordem_servico(9002, self.supervisor_owner)
        rdo = RDO.objects.create(
            ordem_servico=ordem,
            rdo='88',
            data=date(2026, 3, 13),
            data_inicio=date(2026, 3, 13),
        )

        req = self.rf.post(f'/api/rdo/{rdo.id}/delete/', {'rdo_id': rdo.id})
        req.user = self.supervisor_other

        res = delete_rdo_ajax(req, rdo.id)

        self.assertEqual(res.status_code, 403)
        self.assertTrue(RDO.objects.filter(pk=rdo.id).exists())

    def test_delete_rdo_bloqueia_usuario_sem_permissao(self):
        ordem = self._make_ordem_servico(9003, self.supervisor_owner)
        rdo = RDO.objects.create(
            ordem_servico=ordem,
            rdo='89',
            data=date(2026, 3, 13),
            data_inicio=date(2026, 3, 13),
        )

        req = self.rf.post(f'/api/rdo/{rdo.id}/delete/', {'rdo_id': rdo.id})
        req.user = self.regular_user

        res = delete_rdo_ajax(req, rdo.id)

        self.assertEqual(res.status_code, 403)
        self.assertTrue(RDO.objects.filter(pk=rdo.id).exists())

    def test_delete_rdo_permite_usuario_com_delete_rdo(self):
        ordem = self._make_ordem_servico(9004, self.supervisor_owner)
        rdo = RDO.objects.create(
            ordem_servico=ordem,
            rdo='90',
            data=date(2026, 3, 13),
            data_inicio=date(2026, 3, 13),
        )

        req = self.rf.post(f'/api/rdo/{rdo.id}/delete/', {'rdo_id': rdo.id})
        req.user = self.user_with_delete_perm

        res = delete_rdo_ajax(req, rdo.id)

        self.assertEqual(res.status_code, 200)
        self.assertFalse(RDO.objects.filter(pk=rdo.id).exists())
