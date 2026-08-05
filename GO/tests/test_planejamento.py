from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse

from GO.models import (
    Cliente,
    OrdemServico,
    Pessoa,
    PlanejamentoEquipeHistorico,
    PlanejamentoEquipeMembro,
    PlanejamentoEquipeOS,
    RDO,
    RDOMembroEquipe,
    Unidade,
)


class PlanejamentoEquipeTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='planejamento_user',
            password='senha123',
            first_name='Planejamento',
            last_name='User',
            email='planejamento@example.com',
        )
        self.supervisor = User.objects.create_user(
            username='supervisor_planejamento',
            password='senha123',
            first_name='Supervisor',
            last_name='Atual',
            email='supervisor@example.com',
        )
        self.client.force_login(self.user)

        self.cliente = Cliente.objects.create(nome='Cliente Planejamento')
        self.unidade = Unidade.objects.create(nome='Unidade Planejamento')
        self.coordenador = next(value for value, _ in OrdemServico.COORDENADORES if value)
        self.funcao_choice = next(value for value, _ in OrdemServico.FUNCOES if value)
        self.other_funcao_choice = next(
            value for value, _ in OrdemServico.FUNCOES if value and value != self.funcao_choice
        )

    def _create_os(self, numero_os, supervisor=None, status_planejamento='Pendente', status_operacao='Programada'):
        return OrdemServico.objects.create(
            numero_os=numero_os,
            data_inicio=date(2026, 6, 1),
            data_fim=None,
            dias_de_operacao=0,
            servico='COLETA DE AR',
            servicos='COLETA DE AR',
            metodo='Manual',
            pob=4,
            tanque='TK-01',
            tanques='TK-01',
            especificacao='Especificacao Teste',
            volume_tanque=Decimal('10.00'),
            Cliente=self.cliente,
            Unidade=self.unidade,
            tipo_operacao='Onshore',
            solicitante='Solicitante Teste',
            coordenador=self.coordenador,
            supervisor=supervisor,
            status_operacao=status_operacao,
            status_geral='Programada',
            status_comercial='Em aberto',
            status_planejamento=status_planejamento,
        )

    def _create_planejamento(self, os_obj, status=PlanejamentoEquipeOS.STATUS_RASCUNHO):
        return PlanejamentoEquipeOS.objects.create(
            ordem_servico=os_obj,
            status=status,
            criado_por=self.user,
            atualizado_por=self.user,
        )

    def _add_membro(self, planejamento, pessoa=None, nome='Pessoa Teste', funcao=None, status='Ativo'):
        return PlanejamentoEquipeMembro.objects.create(
            planejamento=planejamento,
            pessoa=pessoa,
            nome_snapshot=nome,
            funcao_planejada=funcao or self.funcao_choice,
            status=status,
            criado_por=self.user,
            atualizado_por=self.user,
        )

    def test_nao_permite_criar_planejamento_sem_os(self):
        with self.assertRaises(IntegrityError):
            PlanejamentoEquipeOS.objects.create()

    def test_mesma_linha_os_tem_apenas_um_planejamento(self):
        os_obj = self._create_os(6298)
        self._create_planejamento(os_obj)

        with self.assertRaises(IntegrityError):
            self._create_planejamento(os_obj)

    def test_get_or_create_retorna_mesmo_planejamento_para_mesmo_os_id(self):
        os_obj = self._create_os(6298, supervisor=self.supervisor)
        url = reverse('api_planejamento_get_or_create', args=[os_obj.pk])

        first = self.client.post(url)
        second = self.client.post(url)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()['planejamento']['id'], second.json()['planejamento']['id'])
        self.assertEqual(PlanejamentoEquipeOS.objects.filter(ordem_servico=os_obj).count(), 1)

    def test_linhas_diferentes_mesmo_numero_os_podem_ter_planejamentos_diferentes(self):
        os_a = self._create_os(6298)
        os_b = self._create_os(6298)

        resp_a = self.client.post(reverse('api_planejamento_get_or_create', args=[os_a.pk]))
        resp_b = self.client.post(reverse('api_planejamento_get_or_create', args=[os_b.pk]))

        self.assertEqual(resp_a.status_code, 200)
        self.assertEqual(resp_b.status_code, 200)
        self.assertNotEqual(resp_a.json()['planejamento']['id'], resp_b.json()['planejamento']['id'])
        self.assertEqual(PlanejamentoEquipeOS.objects.count(), 2)

    def test_criar_planejamento_copia_supervisor_da_os(self):
        os_obj = self._create_os(7001, supervisor=self.supervisor)

        response = self.client.post(reverse('api_planejamento_get_or_create', args=[os_obj.pk]))

        self.assertEqual(response.status_code, 200)
        planejamento = PlanejamentoEquipeOS.objects.get(ordem_servico=os_obj)
        self.assertEqual(planejamento.supervisor, self.supervisor)
        self.assertEqual(planejamento.supervisor_nome_snapshot, self.supervisor.get_full_name())

    def test_pagina_planejamento_abre_e_exibe_opcoes_existentes(self):
        Pessoa.objects.create(nome='Pessoa Planejada', funcao=self.funcao_choice)

        response = self.client.get(reverse('planejamento'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Planejamento')
        self.assertContains(response, 'planejamento-pessoas-data')
        self.assertContains(response, 'Pessoa Planejada')
        self.assertContains(response, self.funcao_choice)

    def test_update_cabecalho_persiste_campos_de_embarque(self):
        os_obj = self._create_os(70011, supervisor=self.supervisor)
        planejamento = self._create_planejamento(os_obj)

        response = self.client.post(
            reverse('api_planejamento_update_cabecalho', args=[planejamento.pk]),
            data='{"titulo_planejamento":"EMBARQUE CDI","data_prevista_subida":"2026-06-14","horario_previsto_subida":"A CONFIRMAR","local_subida":"AEROPORTO JACAREPAGUA","observacao":"Levar EPIs"}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        planejamento.refresh_from_db()
        self.assertEqual(planejamento.titulo_planejamento, 'EMBARQUE CDI')
        self.assertEqual(planejamento.horario_previsto_subida, 'A CONFIRMAR')
        self.assertEqual(planejamento.local_subida, 'AEROPORTO JACAREPAGUA')
        self.assertEqual(str(planejamento.data_prevista_subida), '2026-06-14')
        self.assertEqual(response.json()['planejamento']['titulo_planejamento'], 'EMBARQUE CDI')

    def test_update_cabecalho_aceita_data_vazia(self):
        os_obj = self._create_os(70012)
        planejamento = self._create_planejamento(os_obj)

        response = self.client.post(
            reverse('api_planejamento_update_cabecalho', args=[planejamento.pk]),
            data='{"titulo_planejamento":"SEM DATA","data_prevista_subida":"","horario_previsto_subida":"","local_subida":"","observacao":""}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        planejamento.refresh_from_db()
        self.assertIsNone(planejamento.data_prevista_subida)

    def test_add_membro_preserva_cabecalho_do_planejamento_no_retorno(self):
        os_obj = self._create_os(700121, supervisor=self.supervisor)
        planejamento = self._create_planejamento(os_obj)
        planejamento.titulo_planejamento = 'EMBARQUE TESTE'
        planejamento.data_prevista_subida = date(2026, 6, 20)
        planejamento.horario_previsto_subida = '07:30'
        planejamento.local_subida = 'BASE RIO'
        planejamento.observacao = 'Cabecalho mantido'
        planejamento.save()

        response = self.client.post(
            reverse('api_planejamento_add_membro', args=[planejamento.pk]),
            data={'nome_snapshot': 'Pessoa Teste', 'funcao_planejada': self.funcao_choice},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['planejamento']['titulo_planejamento'], 'EMBARQUE TESTE')
        self.assertEqual(payload['planejamento']['data_prevista_subida'], '2026-06-20')
        self.assertEqual(payload['planejamento']['horario_previsto_subida'], '07:30')
        self.assertEqual(payload['planejamento']['local_subida'], 'BASE RIO')
        self.assertEqual(payload['planejamento']['observacao'], 'Cabecalho mantido')

    def test_primeiro_membro_herda_agenda_e_adicoes_posteriores_nao(self):
        os_obj = self._create_os(700122, supervisor=self.supervisor)
        planejamento = self._create_planejamento(os_obj)
        planejamento.data_prevista_subida = date(2026, 6, 20)
        planejamento.data_prevista_desembarque = date(2026, 7, 5)
        planejamento.horario_previsto_desembarque = '18:30'
        planejamento.local_desembarque = 'BASE RIO'
        planejamento.observacao_desembarque = 'Agenda inicial da equipe'
        planejamento.save()

        primeira_resposta = self.client.post(
            reverse('api_planejamento_add_membro', args=[planejamento.pk]),
            data={'nome_snapshot': 'Primeira Pessoa', 'funcao_planejada': self.funcao_choice},
        )

        self.assertEqual(primeira_resposta.status_code, 200)
        primeiro = PlanejamentoEquipeMembro.objects.get(nome_snapshot='Primeira Pessoa')
        self.assertEqual(primeiro.data_inicio, date(2026, 6, 20))
        self.assertEqual(primeiro.data_desembarque, date(2026, 7, 5))
        self.assertEqual(primeiro.horario_desembarque, '18:30')
        self.assertEqual(primeiro.local_desembarque_membro, 'BASE RIO')
        self.assertEqual(primeiro.observacao_desembarque, 'Agenda inicial da equipe')

        segunda_resposta = self.client.post(
            reverse('api_planejamento_add_membro', args=[planejamento.pk]),
            data={'nome_snapshot': 'Pessoa Adicional', 'funcao_planejada': self.funcao_choice},
        )

        self.assertEqual(segunda_resposta.status_code, 200)
        adicional = PlanejamentoEquipeMembro.objects.get(nome_snapshot='Pessoa Adicional')
        self.assertIsNone(adicional.data_inicio)
        self.assertIsNone(adicional.data_desembarque)
        self.assertEqual(adicional.horario_desembarque, '')
        self.assertEqual(adicional.local_desembarque_membro, '')
        self.assertEqual(adicional.observacao_desembarque, '')

    def test_substituicao_nao_herda_agenda_geral_do_planejamento(self):
        os_obj = self._create_os(700123)
        planejamento = self._create_planejamento(os_obj)
        planejamento.data_prevista_subida = date(2026, 6, 20)
        planejamento.data_prevista_desembarque = date(2026, 7, 5)
        planejamento.horario_previsto_desembarque = '18:30'
        planejamento.local_desembarque = 'BASE RIO'
        planejamento.save()
        antigo = self._add_membro(planejamento, nome='Pessoa Original')

        resposta = self.client.post(
            reverse('api_planejamento_substituir_membro', args=[antigo.pk]),
            data={
                'nome_snapshot': 'Pessoa Substituta',
                'funcao_planejada': self.other_funcao_choice,
                'motivo_substituicao': 'Troca operacional',
            },
        )

        self.assertEqual(resposta.status_code, 200)
        substituto = PlanejamentoEquipeMembro.objects.get(nome_snapshot='Pessoa Substituta')
        self.assertIsNone(substituto.data_inicio)
        self.assertIsNone(substituto.data_desembarque)
        self.assertEqual(substituto.horario_desembarque, '')
        self.assertEqual(substituto.local_desembarque_membro, '')

    def test_get_or_create_bloqueado_quando_os_finalizada(self):
        os_obj = self._create_os(70013, status_operacao='  fInAlIzAdA  ')

        response = self.client.post(reverse('api_planejamento_get_or_create', args=[os_obj.pk]))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(PlanejamentoEquipeOS.objects.filter(ordem_servico=os_obj).count(), 0)

    def test_planejamento_concluido_exige_justificativa_para_editar(self):
        os_obj = self._create_os(70014)
        planejamento = self._create_planejamento(os_obj, status=PlanejamentoEquipeOS.STATUS_CONCLUIDO)

        response = self.client.post(
            reverse('api_planejamento_update_cabecalho', args=[planejamento.pk]),
            data='{"titulo_planejamento":"EMBARQUE FINAL","data_prevista_subida":"2026-06-18","horario_previsto_subida":"07:00","local_subida":"BASE RIO","observacao":"Planejamento concluido segue editavel"}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        planejamento.refresh_from_db()
        self.assertEqual(planejamento.titulo_planejamento, '')

        response = self.client.post(
            reverse('api_planejamento_update_cabecalho', args=[planejamento.pk]),
            data='{"titulo_planejamento":"EMBARQUE FINAL","data_prevista_subida":"2026-06-18","horario_previsto_subida":"07:00","local_subida":"BASE RIO","observacao":"Planejamento concluido com justificativa","justificativa":"Ajuste operacional apos conclusao"}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        planejamento.refresh_from_db()
        self.assertEqual(planejamento.titulo_planejamento, 'EMBARQUE FINAL')
        historico = PlanejamentoEquipeHistorico.objects.get(planejamento=planejamento)
        self.assertEqual(historico.acao, PlanejamentoEquipeHistorico.ACAO_ALTERACAO_CABECALHO)
        self.assertEqual(historico.justificativa, 'Ajuste operacional apos conclusao')

    def test_operacao_finalizada_bloqueia_edicao_do_planejamento_existente(self):
        os_obj = self._create_os(70015, status_operacao=' Finalizado ')
        planejamento = self._create_planejamento(os_obj)

        response = self.client.post(
            reverse('api_planejamento_update_cabecalho', args=[planejamento.pk]),
            data='{"titulo_planejamento":"BLOQUEADO","data_prevista_subida":"2026-06-19","horario_previsto_subida":"08:00","local_subida":"BASE","observacao":"Teste"}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        planejamento.refresh_from_db()
        self.assertEqual(planejamento.titulo_planejamento, '')

    def test_status_linha_finalizada_na_home_bloqueia_alteracoes(self):
        os_obj = self._create_os(700151, status_operacao='Programada')
        os_obj.status_geral = ' Finalizada '
        os_obj.save(update_fields=['status_geral'])
        planejamento = self._create_planejamento(os_obj)

        response = self.client.post(
            reverse('api_planejamento_add_membro', args=[planejamento.pk]),
            data={'nome_snapshot': 'Pessoa Bloqueada', 'funcao_planejada': self.funcao_choice},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(PlanejamentoEquipeMembro.objects.filter(planejamento=planejamento).count(), 0)

    def test_membro_salva_funcao_independente_da_funcao_da_pessoa(self):
        os_obj = self._create_os(7002)
        planejamento = self._create_planejamento(os_obj)
        pessoa = Pessoa.objects.create(nome='Pessoa Vinculada', funcao=self.funcao_choice)

        membro = self._add_membro(
            planejamento,
            pessoa=pessoa,
            nome='',
            funcao=self.other_funcao_choice,
        )

        self.assertEqual(membro.nome_snapshot, pessoa.nome)
        self.assertEqual(membro.funcao_planejada, self.other_funcao_choice)
        self.assertNotEqual(membro.funcao_planejada, pessoa.funcao)

    def test_concluir_planejamento_exige_membro_ativo(self):
        os_obj = self._create_os(7003)
        planejamento = self._create_planejamento(os_obj)

        response = self.client.post(reverse('api_planejamento_concluir', args=[planejamento.pk]))

        self.assertEqual(response.status_code, 400)
        planejamento.refresh_from_db()
        os_obj.refresh_from_db()
        self.assertEqual(planejamento.status, PlanejamentoEquipeOS.STATUS_RASCUNHO)
        self.assertEqual(os_obj.status_planejamento, 'Pendente')

    def test_adicao_pos_conclusao_exige_justificativa_e_gera_historico(self):
        os_obj = self._create_os(70031)
        planejamento = self._create_planejamento(os_obj, status=PlanejamentoEquipeOS.STATUS_CONCLUIDO)

        response = self.client.post(
            reverse('api_planejamento_add_membro', args=[planejamento.pk]),
            data={'nome_snapshot': 'Pessoa Nova', 'funcao_planejada': self.funcao_choice},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(PlanejamentoEquipeMembro.objects.filter(planejamento=planejamento).count(), 0)

        response = self.client.post(
            reverse('api_planejamento_add_membro', args=[planejamento.pk]),
            data={
                'nome_snapshot': 'Pessoa Nova',
                'funcao_planejada': self.funcao_choice,
                'justificativa': 'Complemento da equipe apos aprovacao',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(PlanejamentoEquipeMembro.objects.filter(planejamento=planejamento).count(), 1)
        historico = PlanejamentoEquipeHistorico.objects.get(planejamento=planejamento)
        self.assertEqual(historico.acao, PlanejamentoEquipeHistorico.ACAO_ADICAO_MEMBRO_POS_CONCLUSAO)
        self.assertEqual(historico.justificativa, 'Complemento da equipe apos aprovacao')

    def test_substituir_membro_mantem_antigo_e_cria_novo_vinculado(self):
        os_obj = self._create_os(7004)
        planejamento = self._create_planejamento(os_obj)
        antigo = self._add_membro(planejamento, nome='Membro Antigo')

        response = self.client.post(
            reverse('api_planejamento_substituir_membro', args=[antigo.pk]),
            data={
                'nome_snapshot': 'Membro Novo',
                'funcao_planejada': self.other_funcao_choice,
                'motivo_substituicao': 'Troca operacional',
                'data_inicio': '2026-06-10',
                'data_fim': '2026-06-09',
            },
        )

        self.assertEqual(response.status_code, 200)
        antigo.refresh_from_db()
        novo = PlanejamentoEquipeMembro.objects.exclude(pk=antigo.pk).get()

        self.assertEqual(antigo.status, PlanejamentoEquipeMembro.STATUS_SUBSTITUIDO)
        self.assertEqual(antigo.motivo_substituicao, 'Troca operacional')
        self.assertEqual(novo.status, PlanejamentoEquipeMembro.STATUS_ATIVO)
        self.assertEqual(novo.substitui_id, antigo.pk)
        self.assertEqual(PlanejamentoEquipeMembro.objects.filter(planejamento=planejamento).count(), 2)
        payload = response.json()
        self.assertEqual(payload['membro_novo']['substitui_id'], antigo.pk)
        self.assertEqual(payload['membro_novo']['substitui_nome_snapshot'], 'Membro Antigo')
        self.assertEqual(len(payload['planejamento']['membros_ativos']), 1)
        self.assertEqual(payload['planejamento']['membros_ativos'][0]['nome_snapshot'], 'Membro Novo')
        self.assertEqual(payload['planejamento']['membros_ativos'][0]['substitui_nome_snapshot'], 'Membro Antigo')
        self.assertEqual(len(payload['planejamento']['membros_substituidos']), 1)
        self.assertEqual(payload['planejamento']['membros_substituidos'][0]['nome_snapshot'], 'Membro Antigo')

    def test_substituir_membro_pos_conclusao_exige_justificativa_e_retorna_vinculo(self):
        os_obj = self._create_os(70041)
        planejamento = self._create_planejamento(os_obj, status=PlanejamentoEquipeOS.STATUS_CONCLUIDO)
        antigo = self._add_membro(planejamento, nome='ALESSANDRO PEREIRA DIAS')

        response = self.client.post(
            reverse('api_planejamento_substituir_membro', args=[antigo.pk]),
            data={
                'nome_snapshot': 'JORGE AUGUSTO VENANCIO ANDRADE',
                'funcao_planejada': self.other_funcao_choice,
                'motivo_substituicao': 'Troca operacional embarque',
                'data_inicio': '2026-06-16',
                'data_fim': '2026-06-15',
            },
        )

        self.assertEqual(response.status_code, 400)

        response = self.client.post(
            reverse('api_planejamento_substituir_membro', args=[antigo.pk]),
            data={
                'nome_snapshot': 'JORGE AUGUSTO VENANCIO ANDRADE',
                'funcao_planejada': self.other_funcao_choice,
                'motivo_substituicao': 'Troca operacional embarque',
                'data_inicio': '2026-06-16',
                'data_fim': '2026-06-15',
                'justificativa': 'Necessidade de troca operacional para embarque.',
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['membro_novo']['nome_snapshot'], 'JORGE AUGUSTO VENANCIO ANDRADE')
        self.assertEqual(payload['membro_novo']['substitui_nome_snapshot'], 'ALESSANDRO PEREIRA DIAS')
        self.assertEqual(payload['planejamento']['membros_ativos'][0]['substitui_nome_snapshot'], 'ALESSANDRO PEREIRA DIAS')
        self.assertEqual(payload['planejamento']['membros_substituidos'][0]['nome_snapshot'], 'ALESSANDRO PEREIRA DIAS')
        historico = PlanejamentoEquipeHistorico.objects.get(planejamento=planejamento)
        self.assertEqual(historico.acao, PlanejamentoEquipeHistorico.ACAO_SUBSTITUICAO_MEMBRO_POS_CONCLUSAO)
        self.assertEqual(historico.justificativa, 'Necessidade de troca operacional para embarque.')

    def test_cancelar_membro_nao_apaga_registro(self):
        os_obj = self._create_os(7005)
        planejamento = self._create_planejamento(os_obj)
        membro = self._add_membro(planejamento)

        response = self.client.post(
            reverse('api_planejamento_cancelar_membro', args=[membro.pk]),
            data={'observacao': 'Desmobilizado', 'data_fim': '2026-06-11'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(PlanejamentoEquipeMembro.objects.filter(pk=membro.pk).exists())
        membro.refresh_from_db()
        self.assertEqual(membro.status, PlanejamentoEquipeMembro.STATUS_CANCELADO)

    def test_cancelar_planejamento_nao_apaga_membros(self):
        os_obj = self._create_os(7006, status_planejamento='Em andamento')
        planejamento = self._create_planejamento(os_obj)
        membro = self._add_membro(planejamento)

        response = self.client.post(reverse('api_planejamento_cancelar', args=[planejamento.pk]))

        self.assertEqual(response.status_code, 200)
        planejamento.refresh_from_db()
        os_obj.refresh_from_db()
        self.assertEqual(planejamento.status, PlanejamentoEquipeOS.STATUS_CANCELADO)
        self.assertEqual(os_obj.status_planejamento, 'Pendente')
        self.assertTrue(PlanejamentoEquipeMembro.objects.filter(pk=membro.pk).exists())

    def test_status_planejamento_altera_so_a_linha_especifica(self):
        os_alvo = self._create_os(6298, status_planejamento='Pendente')
        os_irma = self._create_os(6298, status_planejamento='Pendente')

        create_response = self.client.post(reverse('api_planejamento_get_or_create', args=[os_alvo.pk]))
        self.assertEqual(create_response.status_code, 200)
        planejamento_id = create_response.json()['planejamento']['id']

        add_response = self.client.post(
            reverse('api_planejamento_add_membro', args=[planejamento_id]),
            data={'nome_snapshot': 'Pessoa Ativa', 'funcao_planejada': self.funcao_choice},
        )
        self.assertEqual(add_response.status_code, 200)

        conclude_response = self.client.post(reverse('api_planejamento_concluir', args=[planejamento_id]))
        self.assertEqual(conclude_response.status_code, 200)

        os_alvo.refresh_from_db()
        os_irma.refresh_from_db()
        self.assertEqual(os_alvo.status_planejamento, 'Concluído')
        self.assertEqual(os_irma.status_planejamento, 'Pendente')

    def test_operacoes_planejamento_nao_alteram_rdo_existente(self):
        os_obj = self._create_os(7007, supervisor=self.supervisor)
        rdo = RDO.objects.create(
            ordem_servico=os_obj,
            rdo='1',
            data=date(2026, 6, 2),
            data_inicio=date(2026, 6, 2),
        )
        rdo_membro = RDOMembroEquipe.objects.create(
            rdo=rdo,
            nome='Supervisor RDO',
            funcao='SUPERVISOR',
        )

        planejamento_response = self.client.post(reverse('api_planejamento_get_or_create', args=[os_obj.pk]))
        self.assertEqual(planejamento_response.status_code, 200)
        planejamento_id = planejamento_response.json()['planejamento']['id']

        add_response = self.client.post(
            reverse('api_planejamento_add_membro', args=[planejamento_id]),
            data={'nome_snapshot': 'Novo Planejado', 'funcao_planejada': self.other_funcao_choice},
        )
        self.assertEqual(add_response.status_code, 200)

        rdo.refresh_from_db()
        rdo_membro.refresh_from_db()
        self.assertEqual(RDO.objects.count(), 1)
        self.assertEqual(RDOMembroEquipe.objects.count(), 1)
        self.assertEqual(rdo_membro.nome, 'Supervisor RDO')
        self.assertEqual(rdo_membro.funcao, 'SUPERVISOR')

    def test_documento_planejamento_exibe_dados_da_movimentacao(self):
        os_obj = self._create_os(7008, supervisor=self.supervisor)
        planejamento = self._create_planejamento(os_obj)
        planejamento.titulo_planejamento = 'EMBARQUE TESTE'
        planejamento.local_subida = 'BASE RIO'
        planejamento.horario_previsto_subida = '07:30'
        planejamento.observacao = 'Checklist liberado'
        planejamento.save()
        self._add_membro(planejamento, nome='Pessoa Documento')

        response = self.client.get(reverse('planejamento_documento', args=[planejamento.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Documento de Planejamento de Equipe')
        self.assertContains(response, 'OS 7008')
        self.assertContains(response, 'EMBARQUE TESTE')
        self.assertContains(response, 'BASE RIO')
        self.assertContains(response, 'Pessoa Documento')
