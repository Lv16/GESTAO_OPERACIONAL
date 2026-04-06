from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from GO.models import Cliente, OrdemServico, Pessoa, RDO, RDOAtividade, RDOMembroEquipe, Unidade


class RdoSupervisorLimitedUpdateTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.cliente = Cliente.objects.create(nome='Cliente Supervisor')
        self.unidade = Unidade.objects.create(nome='Unidade Supervisor')
        self.coordenador = next(value for value, _ in OrdemServico.COORDENADORES if value)
        self.funcao_choice = next(value for value, _ in OrdemServico.FUNCOES if value)
        self.supervisor_group, _ = Group.objects.get_or_create(name='Supervisor')
        self.supervisor = User.objects.create_user(
            username='supervisor_limited_update',
            password='senha123',
        )
        self.supervisor_group.user_set.add(self.supervisor)
        self.client.force_login(self.supervisor)

    def _create_os(self):
        return OrdemServico.objects.create(
            numero_os=7123,
            data_inicio=date(2026, 3, 31),
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

    def test_supervisor_update_only_changes_date_and_team(self):
        os_obj = self._create_os()
        pessoa_antiga = Pessoa.objects.create(nome='Equipe Antiga', funcao=self.funcao_choice)
        pessoa_nova_1 = Pessoa.objects.create(nome='Equipe Nova 1', funcao=self.funcao_choice)
        pessoa_nova_2 = Pessoa.objects.create(nome='Equipe Nova 2', funcao=self.funcao_choice)

        rdo = RDO.objects.create(
            ordem_servico=os_obj,
            rdo='7',
            data=date(2026, 3, 31),
            data_inicio=date(2026, 3, 31),
            turno='Diurno',
            contrato_po='PO-ORIGINAL',
            observacoes_rdo_pt='Observacao original',
            pob=1,
        )
        RDOAtividade.objects.create(
            rdo=rdo,
            ordem=0,
            atividade='abertura pt',
            comentario_pt='atividade original',
        )
        RDOMembroEquipe.objects.create(
            rdo=rdo,
            pessoa=pessoa_antiga,
            funcao='Supervisor',
            em_servico=True,
            ordem=0,
        )

        response = self.client.post(
            reverse('rdo_update_ajax'),
            data={
                'rdo_id': str(rdo.pk),
                'rdo_data_inicio': '2026-04-01',
                'turno': 'noturno',
                'contrato_po': 'PO-ALTERADO',
                'observacoes': 'observacao alterada',
                'atividade_nome[]': ['dds'],
                'atividade_inicio[]': ['07:00'],
                'atividade_fim[]': ['08:00'],
                'atividade_comentario_pt[]': ['atividade alterada'],
                'equipe_nome[]': [pessoa_nova_1.nome, pessoa_nova_2.nome],
                'equipe_funcao[]': ['Lider', 'Ajudante'],
                'equipe_pessoa_id[]': [str(pessoa_nova_1.id), str(pessoa_nova_2.id)],
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))

        rdo.refresh_from_db()

        self.assertEqual(rdo.data, date(2026, 4, 1))
        self.assertEqual(rdo.data_inicio, date(2026, 4, 1))
        self.assertEqual(rdo.turno, 'Diurno')
        self.assertEqual(rdo.contrato_po, 'PO-ORIGINAL')
        self.assertEqual(rdo.observacoes_rdo_pt, 'Observacao original')
        self.assertEqual(rdo.atividades_rdo.count(), 1)
        self.assertEqual(rdo.atividades_rdo.first().atividade, 'abertura pt')
        self.assertEqual(rdo.atividades_rdo.first().comentario_pt, 'atividade original')

        membros = list(rdo.membros_equipe.order_by('ordem'))
        self.assertEqual(len(membros), 2)
        self.assertEqual(membros[0].pessoa, pessoa_nova_1)
        self.assertEqual(membros[0].funcao, 'Lider')
        self.assertEqual(membros[1].pessoa, pessoa_nova_2)
        self.assertEqual(membros[1].funcao, 'Ajudante')
        self.assertEqual(rdo.pob, 2)

    def test_pending_os_json_for_supervisor_includes_latest_rdo_context(self):
        os_obj = self._create_os()
        RDO.objects.create(
            ordem_servico=os_obj,
            rdo='6',
            data=date(2026, 3, 30),
            data_inicio=date(2026, 3, 30),
            turno='Diurno',
            contrato_po='PO-ANTERIOR',
            pob=1,
        )
        latest_rdo = RDO.objects.create(
            ordem_servico=os_obj,
            rdo='7',
            data=date(2026, 3, 31),
            data_inicio=date(2026, 3, 31),
            turno='Noturno',
            contrato_po='PO-ATUAL',
            pob=2,
        )

        response = self.client.get(
            '/rdo/pending_os_json/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        items = payload.get('data') or []
        self.assertEqual(len(items), 1)

        item = items[0]
        self.assertEqual(item.get('os_id'), os_obj.id)
        self.assertEqual(item.get('rdo_id'), latest_rdo.id)
        self.assertEqual(item.get('rdo'), latest_rdo.rdo)
        self.assertEqual(item.get('data_inicio'), '2026-03-31')
