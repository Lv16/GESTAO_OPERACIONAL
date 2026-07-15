import json
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from GO.models import (
    Cliente,
    OrdemServico,
    Pessoa,
    PlanejamentoEquipeMembro,
    PlanejamentoEquipeOS,
    RDO,
    RDOMembroEquipe,
    Unidade,
)


class RdoPlanejamentoIntegrationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.cliente = Cliente.objects.create(nome='Cliente Integracao RDO')
        self.unidade = Unidade.objects.create(nome='Unidade Integracao RDO')
        self.coordenador = next(value for value, _ in OrdemServico.COORDENADORES if value)
        self.funcao_a = next(value for value, _ in OrdemServico.FUNCOES if value)
        self.funcao_b = next(value for value, _ in OrdemServico.FUNCOES if value and value != self.funcao_a)
        self.supervisor_group, _ = Group.objects.get_or_create(name='Supervisor')
        self.supervisor = User.objects.create_user(
            username='supervisor_rdo_planejamento',
            password='senha123',
        )
        self.supervisor_group.user_set.add(self.supervisor)
        self.client.force_login(self.supervisor)

    def _create_os(self, numero_os, status_operacao='Programada'):
        return OrdemServico.objects.create(
            numero_os=numero_os,
            data_inicio=date(2026, 6, 10),
            data_fim=None,
            dias_de_operacao=0,
            servico='COLETA DE AR',
            servicos='COLETA DE AR',
            metodo='Manual',
            pob=1,
            tanque='TK-01',
            tanques='TK-01',
            especificacao='Integracao Planejamento x RDO',
            volume_tanque=Decimal('10.00'),
            Cliente=self.cliente,
            Unidade=self.unidade,
            tipo_operacao='Onshore',
            solicitante='Solicitante Teste',
            coordenador=self.coordenador,
            supervisor=self.supervisor,
            status_operacao=status_operacao,
            status_geral=status_operacao,
            status_comercial='Em aberto',
            status_planejamento='Pendente',
        )

    def _create_planejamento(self, os_obj, status=PlanejamentoEquipeOS.STATUS_RASCUNHO):
        return PlanejamentoEquipeOS.objects.create(
            ordem_servico=os_obj,
            status=status,
            criado_por=self.supervisor,
            atualizado_por=self.supervisor,
        )

    def _add_planejamento_membro(
        self,
        planejamento,
        *,
        nome,
        funcao,
        status=PlanejamentoEquipeMembro.STATUS_ATIVO,
        pessoa=None,
        substitui=None,
    ):
        return PlanejamentoEquipeMembro.objects.create(
            planejamento=planejamento,
            pessoa=pessoa,
            nome_snapshot=nome,
            funcao_planejada=funcao,
            status=status,
            substitui=substitui,
            criado_por=self.supervisor,
            atualizado_por=self.supervisor,
        )

    def test_lookup_os_expoe_contexto_do_planejamento_para_rdo(self):
        os_obj = self._create_os(8201)
        planejamento = self._create_planejamento(os_obj)
        self._add_planejamento_membro(
            planejamento,
            nome='CAROLINA MACHADO',
            funcao=self.funcao_a,
            pessoa=Pessoa.objects.create(nome='CAROLINA MACHADO', funcao=self.funcao_a),
        )
        self._add_planejamento_membro(
            planejamento,
            nome='MEMBRO CANCELADO',
            funcao=self.funcao_b,
            status=PlanejamentoEquipeMembro.STATUS_CANCELADO,
        )

        response = self.client.get(
            reverse('api_lookup_os', args=[os_obj.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()['data']['planejamento_rdo']
        self.assertTrue(payload['tem_planejamento'])
        self.assertTrue(payload['tem_membros_ativos'])
        self.assertEqual(payload['planejamento_id'], planejamento.pk)
        self.assertEqual(len(payload['membros']), 1)
        self.assertEqual(payload['membros'][0]['nome'], 'CAROLINA MACHADO')

    def test_create_rdo_com_planejamento_carrega_somente_membros_ativos(self):
        os_obj = self._create_os(8202)
        planejamento = self._create_planejamento(os_obj)

        pessoa_ativa = Pessoa.objects.create(nome='CAROLINA MACHADO', funcao=self.funcao_a)
        pessoa_substituta = Pessoa.objects.create(nome='JORGE AUGUSTO VENANCIO ANDRADE', funcao=self.funcao_b)

        antigo = self._add_planejamento_membro(
            planejamento,
            nome='ALESSANDRO PEREIRA DIAS',
            funcao=self.funcao_a,
            status=PlanejamentoEquipeMembro.STATUS_SUBSTITUIDO,
        )
        self._add_planejamento_membro(
            planejamento,
            nome='CAROLINA MACHADO',
            funcao=self.funcao_a,
            pessoa=pessoa_ativa,
        )
        self._add_planejamento_membro(
            planejamento,
            nome='JORGE AUGUSTO VENANCIO ANDRADE',
            funcao=self.funcao_b,
            pessoa=pessoa_substituta,
            substitui=antigo,
        )
        self._add_planejamento_membro(
            planejamento,
            nome='MEMBRO CANCELADO',
            funcao=self.funcao_a,
            status=PlanejamentoEquipeMembro.STATUS_CANCELADO,
        )

        response = self.client.post(
            reverse('rdo_create_ajax'),
            data={
                'ordem_servico_id': str(os_obj.pk),
                'data': '2026-06-10',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))

        rdo = RDO.objects.get(pk=payload['id'])
        self.assertEqual(rdo.equipe_origem, RDO.EQUIPE_ORIGEM_PLANEJAMENTO)
        self.assertEqual(rdo.planejamento_equipe_origem_id, planejamento.pk)
        self.assertEqual(rdo.pob, 2)

        membros = list(rdo.membros_equipe.order_by('ordem'))
        self.assertEqual(len(membros), 2)
        self.assertEqual([m.pessoa.nome if m.pessoa else m.nome for m in membros], ['CAROLINA MACHADO', 'JORGE AUGUSTO VENANCIO ANDRADE'])
        self.assertEqual([m.funcao for m in membros], [self.funcao_a, self.funcao_b])
        self.assertEqual(payload['rdo']['equipe_source'], 'planejamento')
        self.assertEqual(len(payload['rdo']['planejamento_rdo']['membros']), 2)

    def test_create_rdo_sem_planejamento_mantem_fluxo_manual(self):
        os_obj = self._create_os(8203)
        pessoa_manual = Pessoa.objects.create(nome='MEMBRO MANUAL', funcao=self.funcao_a)

        response = self.client.post(
            reverse('rdo_create_ajax'),
            data={
                'ordem_servico_id': str(os_obj.pk),
                'data': '2026-06-10',
                'equipe_nome[]': ['MEMBRO MANUAL', 'MEMBRO AVULSO'],
                'equipe_funcao[]': [self.funcao_a, self.funcao_b],
                'equipe_pessoa_id[]': [str(pessoa_manual.pk), ''],
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))

        rdo = RDO.objects.get(pk=payload['id'])
        self.assertEqual(rdo.equipe_origem, RDO.EQUIPE_ORIGEM_MANUAL)
        self.assertIsNone(rdo.planejamento_equipe_origem_id)

        membros = list(rdo.membros_equipe.order_by('ordem'))
        self.assertEqual(len(membros), 2)
        self.assertEqual(membros[0].pessoa, pessoa_manual)
        self.assertEqual(membros[0].funcao, self.funcao_a)
        self.assertEqual(membros[1].funcao, self.funcao_b)
        self.assertEqual(rdo.pob, 2)
        self.assertIn('MEMBRO AVULSO', str(rdo.membros or ''))
        self.assertEqual(payload['rdo']['equipe_source'], 'manual')

    def test_update_rdo_planejado_nao_duplica_equipe_existente(self):
        os_obj = self._create_os(8204)
        planejamento = self._create_planejamento(os_obj)

        pessoa_a = Pessoa.objects.create(nome='CAROLINA MACHADO', funcao=self.funcao_a)
        pessoa_b = Pessoa.objects.create(nome='ABRAAO PEREIRA DE SOUZA', funcao=self.funcao_b)
        self._add_planejamento_membro(planejamento, nome='CAROLINA MACHADO', funcao=self.funcao_a, pessoa=pessoa_a)
        self._add_planejamento_membro(planejamento, nome='ABRAAO PEREIRA DE SOUZA', funcao=self.funcao_b, pessoa=pessoa_b)

        create_response = self.client.post(
            reverse('rdo_create_ajax'),
            data={
                'ordem_servico_id': str(os_obj.pk),
                'data': '2026-06-10',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )
        self.assertEqual(create_response.status_code, 200)
        rdo = RDO.objects.get(pk=create_response.json()['id'])
        self.assertEqual(rdo.membros_equipe.count(), 2)

        update_response = self.client.post(
            reverse('rdo_update_ajax'),
            data={
                'rdo_id': str(rdo.pk),
                'data': '2026-06-10',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )

        self.assertEqual(update_response.status_code, 200)
        rdo.refresh_from_db()
        membros = list(rdo.membros_equipe.order_by('ordem'))
        self.assertEqual(len(membros), 2)
        self.assertEqual([m.pessoa.nome if m.pessoa else m.nome for m in membros], ['CAROLINA MACHADO', 'ABRAAO PEREIRA DE SOUZA'])
        self.assertEqual(rdo.equipe_origem, RDO.EQUIPE_ORIGEM_PLANEJAMENTO)
        self.assertEqual(rdo.planejamento_equipe_origem_id, planejamento.pk)

    def test_avaliacao_de_membro_planejado_persiste_e_bloqueia_supervisor(self):
        os_obj = self._create_os(8205)
        planejamento = self._create_planejamento(os_obj)
        funcao_avaliavel = next(
            value for value, _ in OrdemServico.FUNCOES
            if value and 'SUPERVISOR' not in str(value).upper()
        )
        pessoa_supervisor = Pessoa.objects.create(nome='CAROLINA MACHADO', funcao='SUPERVISOR')
        pessoa_ajudante = Pessoa.objects.create(nome='ABRAAO PEREIRA DE SOUZA', funcao=funcao_avaliavel)
        self._add_planejamento_membro(planejamento, nome='CAROLINA MACHADO', funcao='SUPERVISOR', pessoa=pessoa_supervisor)
        self._add_planejamento_membro(planejamento, nome='ABRAAO PEREIRA DE SOUZA', funcao=funcao_avaliavel, pessoa=pessoa_ajudante)

        create_response = self.client.post(
            reverse('rdo_create_ajax'),
            data={
                'ordem_servico_id': str(os_obj.pk),
                'data': '2026-06-10',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )
        self.assertEqual(create_response.status_code, 200)
        rdo = RDO.objects.get(pk=create_response.json()['id'])
        membros = list(rdo.membros_equipe.order_by('ordem'))
        supervisor_member = membros[0]
        ajudante_member = membros[1]

        ruim_sem_justificativa = self.client.post(
            reverse('api_rdo_membro_avaliacao', args=[ajudante_member.pk]),
            data={'nota': 'RUIM', 'justificativa': ''},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )
        self.assertEqual(ruim_sem_justificativa.status_code, 400)
        self.assertIn('justificativa', ruim_sem_justificativa.json()['error'].lower())

        salvar_avaliacao = self.client.post(
            reverse('api_rdo_membro_avaliacao', args=[ajudante_member.pk]),
            data={'nota': 'BOM', 'justificativa': ''},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )
        self.assertEqual(salvar_avaliacao.status_code, 200)
        ajudante_member.refresh_from_db()
        self.assertEqual(ajudante_member.avaliacao_nota, RDOMembroEquipe.AVALIACAO_BOM)

        bloquear_supervisor = self.client.post(
            reverse('api_rdo_membro_avaliacao', args=[supervisor_member.pk]),
            data={'nota': 'OTIMO', 'justificativa': ''},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )
        self.assertEqual(bloquear_supervisor.status_code, 400)
        self.assertIn('supervisor', bloquear_supervisor.json()['error'].lower())

        detail_response = self.client.get(
            reverse('api_rdo_detail', args=[rdo.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )
        self.assertEqual(detail_response.status_code, 200)
        equipe_payload = detail_response.json()['rdo']['equipe']
        self.assertEqual(equipe_payload[0]['can_rate'], False)
        self.assertEqual(equipe_payload[1]['avaliacao_nota'], RDOMembroEquipe.AVALIACAO_BOM)
        self.assertEqual(equipe_payload[1]['avaliacao_nota_label'], 'BOM')

        update_response = self.client.post(
            reverse('rdo_update_ajax'),
            data={
                'rdo_id': str(rdo.pk),
                'data': '2026-06-10',
                'equipe_source': 'planejamento',
                'equipe_avaliacoes_json': '[{"index":1,"member_id":%s,"nota":"BOM","justificativa":""}]' % ajudante_member.pk,
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )
        self.assertEqual(update_response.status_code, 200)
        rdo.refresh_from_db()
        membros_atualizados = list(rdo.membros_equipe.order_by('ordem'))
        self.assertEqual(len(membros_atualizados), 2)
        self.assertEqual(membros_atualizados[1].avaliacao_nota, RDOMembroEquipe.AVALIACAO_BOM)

    def test_avaliacoes_em_lote_salvam_toda_equipe_planejada(self):
        os_obj = self._create_os(8206)
        planejamento = self._create_planejamento(os_obj)
        funcao_avaliavel = next(
            value for value, _ in OrdemServico.FUNCOES
            if value and 'SUPERVISOR' not in str(value).upper()
        )
        pessoa_supervisor = Pessoa.objects.create(nome='CAROLINA MACHADO', funcao='SUPERVISOR')
        pessoa_a = Pessoa.objects.create(nome='ABRAAO PEREIRA DE SOUZA', funcao=funcao_avaliavel)
        pessoa_b = Pessoa.objects.create(nome='LUCAS ANTONIO ROCHA', funcao=funcao_avaliavel)
        self._add_planejamento_membro(planejamento, nome='CAROLINA MACHADO', funcao='SUPERVISOR', pessoa=pessoa_supervisor)
        self._add_planejamento_membro(planejamento, nome='ABRAAO PEREIRA DE SOUZA', funcao=funcao_avaliavel, pessoa=pessoa_a)
        self._add_planejamento_membro(planejamento, nome='LUCAS ANTONIO ROCHA', funcao=funcao_avaliavel, pessoa=pessoa_b)

        create_response = self.client.post(
            reverse('rdo_create_ajax'),
            data={'ordem_servico_id': str(os_obj.pk), 'data': '2026-06-10'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )
        self.assertEqual(create_response.status_code, 200)
        rdo = RDO.objects.get(pk=create_response.json()['id'])
        membros = list(rdo.membros_equipe.order_by('ordem'))
        ajudante_a = membros[1]
        ajudante_b = membros[2]

        sem_justificativa = self.client.post(
            reverse('api_rdo_avaliacoes_equipe', args=[rdo.pk]),
            data=json.dumps({
                'avaliacoes': [
                    {'membro_id': ajudante_a.pk, 'nota': 'BOM', 'justificativa': ''},
                    {'membro_id': ajudante_b.pk, 'nota': 'RUIM', 'justificativa': ''},
                ]
            }),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )
        self.assertEqual(sem_justificativa.status_code, 400)
        self.assertIn('justificativa', sem_justificativa.json()['error'].lower())

        salvar_lote = self.client.post(
            reverse('api_rdo_avaliacoes_equipe', args=[rdo.pk]),
            data=json.dumps({
                'avaliacoes': [
                    {'membro_id': ajudante_a.pk, 'nota': 'BOM', 'justificativa': ''},
                    {'membro_id': ajudante_b.pk, 'nota': 'RUIM', 'justificativa': 'Precisou de orientação adicional durante a atividade.'},
                ]
            }),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_HOST='localhost',
            secure=True,
        )
        self.assertEqual(salvar_lote.status_code, 200)
        ajudante_a.refresh_from_db()
        ajudante_b.refresh_from_db()
        self.assertEqual(ajudante_a.avaliacao_nota, RDOMembroEquipe.AVALIACAO_BOM)
        self.assertEqual(ajudante_b.avaliacao_nota, RDOMembroEquipe.AVALIACAO_RUIM)
        self.assertIn('orientação', ajudante_b.avaliacao_justificativa.lower())
