import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.cache import caches
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from GO.models import Cliente, OrdemServico, RDO, RDOAtividade, RdoTanque, Unidade
from alertas_inteligentes.models import (
    AlertaInteligente,
    AlertaOperacionalInteligente,
    ExemploIntencaoIA,
    PerguntaAssistenteIA,
)
from alertas_inteligentes.services.alertas_rdo_consolidados import (
    listar_alertas_rdo_consolidados,
)
from alertas_inteligentes.services.anomaly_detector import (
    detectar_anomalia_rdo,
    montar_mensagem_anomalia,
)
from alertas_inteligentes.services.assistente_livre import (
    responder_alertas_pendentes,
    responder_pergunta_livre,
)
from alertas_inteligentes.services.aprendizado_ia import aprovar_pergunta_como_exemplo
from alertas_inteligentes.services.lancamento_atrasado_rdo import (
    listar_rdos_lancados_fora_do_dia,
)
from alertas_inteligentes.services.rdos_preenchimento_ruim import (
    avaliar_preenchimento_rdo,
    listar_rdos_preenchimento_ruim,
)
from alertas_inteligentes.services.rdos_tanque_incompleto import (
    gerar_resposta_rdos_tanque_incompleto,
)
from alertas_inteligentes.services.rdo_validator import (
    criar_alerta,
    validar_campos_basicos,
    validar_dados_operacionais,
    validar_fotos,
    validar_observacoes,
    validar_tanque_incompleto_rdo,
)
from alertas_inteligentes.management.command_lock import (
    COMMAND_EXECUTION_LOCK_CACHE_ALIAS,
    COMMAND_EXECUTION_LOCK_KEY,
)


@override_settings(OLLAMA_ENABLED=False)
class AssistenteLivreTanqueTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(nome="Cliente IA")
        self.unidade = Unidade.objects.create(nome="Unidade IA")
        self.supervisor = User.objects.create_user(
            username="carolina.machado",
            first_name="Carolina",
            last_name="Machado",
            password="senha123",
        )
        self.coordenador = next(value for value, _ in OrdemServico.COORDENADORES if value)
        self.os_obj = OrdemServico.objects.create(
            numero_os=6231,
            data_inicio=date(2026, 5, 1),
            data_fim=None,
            dias_de_operacao=0,
            servico="LIMPEZA",
            servicos="LIMPEZA",
            metodo="Mecanizada",
            pob=1,
            tanque="TQ-01",
            tanques="TQ-01",
            volume_tanque=Decimal("0.00"),
            Cliente=self.cliente,
            Unidade=self.unidade,
            tipo_operacao="Offshore",
            solicitante="Solicitante Teste",
            coordenador=self.coordenador,
            supervisor=self.supervisor,
            status_operacao="Em Andamento",
            status_geral="Em Andamento",
            status_comercial="Em aberto",
            status_planejamento="Pendente",
        )

    def test_responde_metricas_do_tanque_unico_sem_nome_explicito(self):
        rdo_prev = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="1",
            data=date(2026, 5, 1),
        )
        RdoTanque.objects.create(
            rdo=rdo_prev,
            tanque_codigo="TQ-01",
            nome_tanque="TQ-01",
            numero_compartimentos=2,
            ensacamento_dia=10,
            ensacamento_cumulativo=10,
            compartimentos_avanco_json=json.dumps(
                {
                    "1": {"mecanizada": 20, "fina": 0},
                    "2": {"mecanizada": 10, "fina": 0},
                }
            ),
        )
        rdo_curr = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="2",
            data=date(2026, 5, 2),
        )
        RdoTanque.objects.create(
            rdo=rdo_curr,
            tanque_codigo="TQ-01",
            nome_tanque="TQ-01",
            numero_compartimentos=2,
            ensacamento_dia=15,
            ensacamento_cumulativo=25,
            percentual_avanco=Decimal("15.00"),
            percentual_avanco_cumulativo=Decimal("26.50"),
            limpeza_mecanizada_diaria=Decimal("15.00"),
            limpeza_mecanizada_cumulativa=Decimal("30.00"),
            limpeza_fina_diaria=Decimal("5.00"),
            limpeza_fina_cumulativa=Decimal("5.00"),
            compartimentos_avanco_json=json.dumps(
                {
                    "1": {"mecanizada": 20, "fina": 10},
                    "2": {"mecanizada": 10, "fina": 0},
                }
            ),
        )

        resposta = responder_pergunta_livre("qual o avanco da OS 6231 por compartimento?")

        self.assertIn("tanque TQ-01", resposta["introducao"])
        self.assertIn("Avanco total do tanque: 21.3%", resposta["introducao"])
        self.assertIn("Compartimento 1", resposta["introducao"])
        self.assertIn("mecanizada 40%", resposta["introducao"])

    def test_responde_total_diario_por_supervisor_com_nome_completo(self):
        rdo_1 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="1",
            data=date(2026, 5, 1),
        )
        rdo_2 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="2",
            data=date(2026, 5, 2),
        )
        RdoTanque.objects.create(rdo=rdo_1, tanque_codigo="TQ-01", ensacamento_dia=10)
        RdoTanque.objects.create(rdo=rdo_2, tanque_codigo="TQ-01", ensacamento_dia=15)

        resposta = responder_pergunta_livre(
            "quanto a supervisora Carolina Machado teve de ensacamento?"
        )

        self.assertIn("Carolina Machado", resposta["introducao"])
        self.assertIn("Ensacamento: 25 saco(s).", resposta["introducao"])

    def test_pergunta_de_tanque_nao_desvia_para_analise_por_supervisor(self):
        rdo_prev = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="1",
            data=date(2026, 5, 1),
        )
        RdoTanque.objects.create(
            rdo=rdo_prev,
            tanque_codigo="TQ-01",
            nome_tanque="TQ-01",
            percentual_avanco_cumulativo=Decimal("10.00"),
            compartimentos_avanco_json=json.dumps({"1": {"mecanizada": 20, "fina": 0}}),
        )
        rdo_curr = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="2",
            data=date(2026, 5, 2),
        )
        RdoTanque.objects.create(
            rdo=rdo_curr,
            tanque_codigo="TQ-01",
            nome_tanque="TQ-01",
            percentual_avanco_cumulativo=Decimal("21.30"),
            compartimentos_avanco_json=json.dumps({"1": {"mecanizada": 40, "fina": 0}}),
        )

        resposta = responder_pergunta_livre("qual o avanco da OS 6231 por compartimento?")

        self.assertIn("Avanco total do tanque: 21.3%", resposta["introducao"])
        self.assertNotIn("Resumo por supervisor", resposta["introducao"])

    def test_pergunta_explicita_por_supervisor_da_os_usa_nova_analise(self):
        rdo_1 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="1",
            data=date(2026, 5, 1),
        )
        rdo_2 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="2",
            data=date(2026, 5, 2),
        )
        RdoTanque.objects.create(
            rdo=rdo_1,
            tanque_codigo="TQ-01",
            nome_tanque="TQ-01",
            ensacamento_cumulativo=10,
        )
        RdoTanque.objects.create(
            rdo=rdo_2,
            tanque_codigo="TQ-01",
            nome_tanque="TQ-01",
            ensacamento_cumulativo=25,
        )

        resposta = responder_pergunta_livre("qual o ensacamento por supervisor da OS 6231?")

        self.assertIn("Analisei a OS 6231", resposta["introducao"])
        self.assertIn("Resumo por supervisor", resposta["introducao"])
        self.assertIn("Ensacamento atribuido: 25", resposta["introducao"])

    def test_observacoes_da_analise_mostram_numero_funcional_do_rdo(self):
        rdo_1 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="10",
            data=date(2026, 5, 1),
        )
        rdo_2 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="11",
            data=date(2026, 5, 2),
        )
        RdoTanque.objects.create(
            rdo=rdo_1,
            tanque_codigo="TQ-01",
            nome_tanque="TQ-01",
            percentual_avanco_cumulativo=Decimal("30.00"),
            compartimentos_avanco_json=json.dumps({"8": {"mecanizada": 30, "fina": 0}}),
        )
        RdoTanque.objects.create(
            rdo=rdo_2,
            tanque_codigo="TQ-01",
            nome_tanque="TQ-01",
            percentual_avanco_cumulativo=Decimal("20.00"),
            tempo_bomba=Decimal("1.00"),
            compartimentos_avanco_json=json.dumps({"8": {"mecanizada": 10, "fina": 0}}),
        )

        resposta = responder_pergunta_livre("qual o avanco por supervisor da OS 6231?")

        self.assertIn("RDO 11", resposta["introducao"])
        self.assertNotIn(f"RDO {rdo_2.id}", resposta["introducao"])

    def test_nao_aponta_reducao_quando_rdo_atual_nao_tem_movimentacao_operacional(self):
        rdo_1 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="27",
            data=date(2026, 5, 1),
        )
        rdo_2 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="28",
            data=date(2026, 5, 2),
        )
        RdoTanque.objects.create(
            rdo=rdo_1,
            tanque_codigo="TQ-01",
            nome_tanque="TQ-01",
            percentual_avanco_cumulativo=Decimal("92.19"),
            limpeza_mecanizada_diaria=Decimal("0.00"),
            limpeza_fina_diaria=Decimal("28.57"),
            compartimentos_avanco_json=json.dumps({"4": {"mecanizada": 0, "fina": 100}}),
        )
        RdoTanque.objects.create(
            rdo=rdo_2,
            tanque_codigo="TQ-01",
            nome_tanque="TQ-01",
            percentual_avanco_cumulativo=Decimal("79.29"),
            limpeza_mecanizada_diaria=Decimal("0.00"),
            limpeza_fina_diaria=Decimal("0.00"),
            compartimentos_avanco_json=json.dumps({"4": {"mecanizada": 0, "fina": 0}}),
        )

        resposta = responder_pergunta_livre("qual o avanco por supervisor da OS 6231?")

        self.assertNotIn("apresentou reducao no RDO 28", resposta["introducao"])
        self.assertNotIn("apresentou reducao de avanco no RDO 28", resposta["introducao"])
        self.assertNotIn("apresentou reducao de limpeza fina no RDO 28", resposta["introducao"])

    def test_compartimentos_por_supervisor_separam_mecanizada_e_fina(self):
        rdo_1 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="1",
            data=date(2026, 5, 1),
        )
        rdo_2 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="2",
            data=date(2026, 5, 2),
        )
        RdoTanque.objects.create(
            rdo=rdo_1,
            tanque_codigo="TQ-01",
            nome_tanque="TQ-01",
            compartimentos_avanco_json=json.dumps({"7": {"mecanizada": 20, "fina": 5}}),
        )
        RdoTanque.objects.create(
            rdo=rdo_2,
            tanque_codigo="TQ-01",
            nome_tanque="TQ-01",
            compartimentos_avanco_json=json.dumps({"7": {"mecanizada": 55, "fina": 15}}),
        )

        resposta = responder_pergunta_livre("qual o avanco por compartimento por supervisor da OS 6231?")

        self.assertIn("55% de limpeza mecanizada", resposta["introducao"])
        self.assertIn("15% de limpeza fina", resposta["introducao"])
        self.assertIn("Maior avanco em mecanizada", resposta["introducao"])
        self.assertNotIn("200%", resposta["introducao"])

    def test_cumulativo_do_tanque_nao_e_recontado_quando_ha_lacuna_entre_rdos(self):
        rdo_1 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="1",
            data=date(2026, 5, 1),
        )
        rdo_2 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="2",
            data=date(2026, 5, 2),
        )
        rdo_3 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="3",
            data=date(2026, 5, 3),
        )
        RdoTanque.objects.create(
            rdo=rdo_1,
            tanque_codigo="TQ-01",
            nome_tanque="TQ-01",
            ensacamento_cumulativo=100,
        )
        # RDO 2 sem esse tanque para simular lacuna operacional.
        RdoTanque.objects.create(
            rdo=rdo_2,
            tanque_codigo="TQ-02",
            nome_tanque="TQ-02",
            ensacamento_cumulativo=50,
        )
        RdoTanque.objects.create(
            rdo=rdo_3,
            tanque_codigo="TQ-01",
            nome_tanque="TQ-01",
            ensacamento_cumulativo=150,
        )

        resposta = responder_pergunta_livre("qual o ensacamento por supervisor da OS 6231?")

        self.assertIn("Ensacamento atribuido: 200", resposta["introducao"])
        self.assertNotIn("Ensacamento atribuido: 300", resposta["introducao"])

    def test_os_com_varios_tanques_exibe_avanco_percentual_por_tanque(self):
        rdo_1 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="1",
            data=date(2026, 5, 1),
        )
        RdoTanque.objects.create(
            rdo=rdo_1,
            tanque_codigo="TQ-01",
            nome_tanque="TQ-01",
            percentual_avanco_cumulativo=Decimal("80.00"),
        )
        RdoTanque.objects.create(
            rdo=rdo_1,
            tanque_codigo="TQ-02",
            nome_tanque="TQ-02",
            percentual_avanco_cumulativo=Decimal("70.00"),
        )

        resposta = responder_pergunta_livre("qual o avanco por supervisor da OS 6231?")

        self.assertIn("Avanco percentual por tanque:", resposta["introducao"])
        self.assertIn("TQ-01: 80%", resposta["introducao"])
        self.assertIn("TQ-02: 70%", resposta["introducao"])
        self.assertNotIn("Avanco percentual atribuido: 150%", resposta["introducao"])

    def test_reaproveita_contexto_da_os_em_pergunta_seguinte_sobre_tanque(self):
        rdo = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="1",
            data=date(2026, 5, 1),
        )
        RdoTanque.objects.create(
            rdo=rdo,
            tanque_codigo="TQ-01",
            nome_tanque="TQ-01",
            ensacamento_dia=10,
            ensacamento_cumulativo=10,
        )

        resposta_os = responder_pergunta_livre("me fale sobre a OS 6231")
        resposta_tanque = responder_pergunta_livre(
            "me fale sobre o tanque",
            contexto=resposta_os["contexto"],
        )

        self.assertIn("OS 6231", resposta_tanque["introducao"])
        self.assertIn("tanque TQ-01", resposta_tanque["introducao"])

    def test_resumo_com_tanque_prioriza_analise_de_tanque_antes_do_resumo_generico(self):
        rdo = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="12",
            data=date(2026, 5, 3),
        )
        RdoTanque.objects.create(
            rdo=rdo,
            tanque_codigo="TQ-01",
            nome_tanque="TQ-01",
            ensacamento_cumulativo=20,
            percentual_avanco_cumulativo=Decimal("35.00"),
        )

        resposta = responder_pergunta_livre("resuma a OS 6231 no tanque TQ-01")

        self.assertIn("Encontrei dados do tanque TQ-01 na OS 6231.", resposta["introducao"])
        self.assertNotIn("Resumo da OS 6231", resposta["introducao"])

    def test_consulta_de_supervisores_da_os_prioriza_analise_especifica(self):
        rdo = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="13",
            data=date(2026, 5, 4),
        )
        RdoTanque.objects.create(
            rdo=rdo,
            tanque_codigo="TQ-01",
            nome_tanque="TQ-01",
            ensacamento_cumulativo=12,
        )

        resposta = responder_pergunta_livre("quais supervisores da OS 6231?")

        self.assertIn("Analisei a OS 6231", resposta["introducao"])
        self.assertIn("Resumo por supervisor", resposta["introducao"])
        self.assertNotIn("Visao geral da OS 6231", resposta["introducao"])

    def test_resumo_linha_do_tempo_comparacao_e_operacao_parada(self):
        rdo_1 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="10",
            data=date(2026, 5, 1),
            turno="Diurno",
            confinado=False,
        )
        RDOAtividade.objects.create(rdo=rdo_1, ordem=1, atividade="abertura pt")
        RdoTanque.objects.create(
            rdo=rdo_1,
            tanque_codigo="TQ-01",
            percentual_avanco_cumulativo=Decimal("20.00"),
            ensacamento_cumulativo=10,
        )
        rdo_2 = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="11",
            data=date(2026, 5, 2),
            turno="Noturno",
            confinado=True,
        )
        RDOAtividade.objects.create(rdo=rdo_2, ordem=1, atividade="abertura pt")
        RDOAtividade.objects.create(rdo=rdo_2, ordem=2, atividade="acesso ao tanque")
        RdoTanque.objects.create(
            rdo=rdo_2,
            tanque_codigo="TQ-01",
            percentual_avanco_cumulativo=Decimal("20.00"),
            ensacamento_cumulativo=15,
        )

        resumo = responder_pergunta_livre("resuma a OS 6231")
        linha_tempo = responder_pergunta_livre("mostre a linha do tempo da OS 6231")
        comparacao = responder_pergunta_livre("o que mudou entre o RDO 10 e o RDO 11 da OS 6231?")
        parada = responder_pergunta_livre("a operacao da OS 6231 esta parada?")

        self.assertIn("Resumo da OS 6231", resumo["introducao"])
        self.assertIn("Linha do tempo da OS 6231", linha_tempo["introducao"])
        self.assertIn("RDO 10 lancado.", linha_tempo["introducao"])
        self.assertIn("Comparacao entre o RDO 10 e o RDO 11", comparacao["introducao"])
        self.assertIn("Turno: Diurno para Noturno.", comparacao["introducao"])
        self.assertIn("possivel parada", parada["introducao"])

    def test_analise_supervisor_unidade_priorizacao_e_resumo_diario(self):
        rdo = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="20",
            data=date(2026, 5, 17),
        )
        RDO.objects.filter(pk=rdo.pk).update(data_analise_ia="2026-05-17T10:00:00Z")
        alerta_rdo = AlertaInteligente.objects.create(
            rdo=rdo,
            tipo="PT_SEM_NUMERO",
            mensagem="PT sem numero.",
            prioridade="alta",
            equipe_responsavel="operacao",
        )
        alerta_operacional = AlertaOperacionalInteligente.objects.create(
            ordem_servico=self.os_obj,
            tipo="OS_SEM_RDO_RECENTE",
            mensagem="Linha sem RDO recente.",
            prioridade="critica",
        )

        resposta_supervisor = responder_pergunta_livre(
            "como esta o desempenho operacional da supervisora Carolina Machado?"
        )
        resposta_unidade = responder_pergunta_livre(
            "como estao as operacoes da unidade Unidade IA?"
        )
        resposta_prioridade = responder_pergunta_livre("o que devo priorizar agora?")
        resposta_diaria = responder_pergunta_livre("resumo de hoje")

        self.assertIn("Resumo do supervisor", resposta_supervisor["introducao"])
        self.assertIn("Linhas sem RDO recente: 1", resposta_supervisor["introducao"])
        self.assertIn("Analisei as operações de unidade 'Unidade IA'.", resposta_unidade["introducao"])
        self.assertIn("1 alerta(s) operacional(is) pendente(s)", resposta_unidade["introducao"])
        self.assertIn("Eu recomendo priorizar", resposta_prioridade["introducao"])
        self.assertIn("OS em andamento sem RDO recente", resposta_prioridade["introducao"])
        self.assertIn("Resumo inteligente de hoje", resposta_diaria["introducao"])
        self.assertIn("Alertas de RDO criados hoje: 1", resposta_diaria["introducao"])

    def test_reutiliza_exemplo_aprovado_para_corrigir_intencao_generica(self):
        resposta_inicial = responder_pergunta_livre("me da um panorama da OS 6231")
        pergunta = PerguntaAssistenteIA.objects.get(pergunta="me da um panorama da OS 6231")

        self.assertEqual(pergunta.status, "entendida")
        self.assertIn("Visao geral da OS 6231", resposta_inicial["introducao"])

        pergunta.intencao_detectada = "resumo_os"
        pergunta.save(update_fields=["intencao_detectada"])
        aprovar_pergunta_como_exemplo(pergunta, "resumo_os", usuario=self.supervisor)

        resposta_aprendida = responder_pergunta_livre("me da um panorama da OS 6231")
        pergunta.refresh_from_db()

        self.assertEqual(ExemploIntencaoIA.objects.count(), 1)
        self.assertEqual(pergunta.status, "revisada")
        self.assertIn("Resumo da OS 6231", resposta_aprendida["introducao"])

    def test_consulta_os_retorna_texto_mais_organizado(self):
        resposta = responder_pergunta_livre("preciso das informacoes da OS 6231")

        self.assertIn("Visao geral da OS 6231", resposta["introducao"])
        self.assertIn("Panorama atual", resposta["introducao"])
        self.assertIn("Numeros consolidados", resposta["introducao"])
        self.assertIn("Proximo passo sugerido", resposta["introducao"])

    def test_consulta_generica_da_os_retorna_resumo_consolidado(self):
        rdo = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="40",
            data=date(2026, 5, 22),
        )
        RdoTanque.objects.create(
            rdo=rdo,
            tanque_codigo="TQ-01",
            nome_tanque="TQ-01",
            percentual_avanco_cumulativo=Decimal("32.00"),
        )

        resposta = responder_pergunta_livre("me fale sobre a OS 6231")

        self.assertIn("Visao geral da OS 6231", resposta["introducao"])
        self.assertIn("Panorama atual", resposta["introducao"])
        self.assertIn("Ultima movimentacao identificada", resposta["introducao"])
        self.assertIn("Avanco mais recente", resposta["introducao"])

    def test_consulta_generica_de_supervisor_retorna_resumo_consolidado(self):
        rdo = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="41",
            data=date(2026, 5, 23),
        )
        RdoTanque.objects.create(
            rdo=rdo,
            tanque_codigo="TQ-01",
            ensacamento_dia=12,
            cambagem_dia=3,
        )

        resposta = responder_pergunta_livre("a supervisora Carolina Machado esta em alguma OS?")

        self.assertIn("Resumo do supervisor 'Carolina Machado'", resposta["introducao"])
        self.assertIn("Linhas vinculadas", resposta["introducao"])
        self.assertIn("Linhas em destaque", resposta["introducao"])
        self.assertIn("OS 6231", resposta["introducao"])

    def test_consulta_generica_de_unidade_retorna_resumo_consolidado(self):
        RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="42",
            data=date(2026, 5, 24),
        )

        resposta = responder_pergunta_livre("quais OS existem na unidade Unidade IA?")

        self.assertIn("Analisei as operações de unidade 'Unidade IA'.", resposta["introducao"])
        self.assertIn("Resumo operacional", resposta["introducao"])
        self.assertIn("Linhas em destaque", resposta["introducao"])
        self.assertIn("OS 6231", resposta["introducao"])

    def test_pendencias_gerais_digitadas_exibem_alertas_de_rdo_quando_nao_ha_operacionais(self):
        rdo = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="30",
            data=date(2026, 5, 18),
        )
        alerta_rdo = AlertaInteligente.objects.create(
            rdo=rdo,
            tipo="PT_SEM_NUMERO",
            mensagem="PT sem numero.",
            prioridade="media",
            equipe_responsavel="operacao",
        )

        resposta = responder_pergunta_livre("quais pendencias operacionais existem?")
        tipos = [alerta.get_tipo_display() for alerta in resposta["alertas"]]

        self.assertIn("Nao encontrei pendencias operacionais abertas agora", resposta["introducao"])
        self.assertEqual(len(resposta["alertas_operacionais"]), 0)
        self.assertGreaterEqual(len(resposta["alertas"]), 1)
        self.assertIn("PT sem n\u00famero", tipos)
        self.assertIn(alerta_rdo.id, [alerta.id for alerta in resposta["alertas"] if alerta.id])

    def test_consulta_digitada_de_alertas_pendentes_prioriza_alertas_de_rdo(self):
        rdo = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="31",
            data=date(2026, 5, 19),
        )
        alerta_rdo = AlertaInteligente.objects.create(
            rdo=rdo,
            tipo="PT_SEM_NUMERO",
            mensagem="PT sem numero.",
            prioridade="alta",
            equipe_responsavel="operacao",
        )

        resposta = responder_pergunta_livre("quais alertas pendentes existem?")
        tipos = [alerta.get_tipo_display() for alerta in resposta["alertas"]]

        self.assertIn("Eu encontrei", resposta["introducao"])
        self.assertGreaterEqual(len(resposta["alertas"]), 1)
        self.assertIn("PT sem n\u00famero", tipos)
        self.assertIn(alerta_rdo.id, [alerta.id for alerta in resposta["alertas"] if alerta.id])
        self.assertEqual(len(resposta["alertas_operacionais"]), 0)

    def test_consulta_digitada_de_alertas_pendentes_agrega_achados_dinamicos_de_rdo(self):
        rdo_alerta = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="32",
            data=date(2026, 5, 20),
        )
        AlertaInteligente.objects.create(
            rdo=rdo_alerta,
            tipo="PT_SEM_NUMERO",
            mensagem="PT sem numero.",
            prioridade="alta",
            equipe_responsavel="operacao",
        )
        RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="33",
            data=date(2026, 5, 21),
        )

        resposta = responder_pergunta_livre("quais alertas pendentes existem?")

        tipos = [alerta.get_tipo_display() for alerta in resposta["alertas"]]

        self.assertGreaterEqual(len(resposta["alertas"]), 2)
        self.assertIn("PT sem n\u00famero", tipos)
        self.assertIn("Foto ausente", tipos)

    def test_consulta_sem_foto_varre_a_base_toda_por_padrao(self):
        rdos = []
        for indice in range(151):
            rdos.append(
                RDO.objects.create(
                    ordem_servico=self.os_obj,
                    rdo=str(100 + indice),
                    data=date(2026, 5, 22),
                )
            )

        rdo_antigo_sem_foto = rdos[0]

        def _tem_foto(rdo):
            return rdo.id != rdo_antigo_sem_foto.id

        with patch(
            "alertas_inteligentes.services.rdos_sem_foto.rdo_tem_foto",
            side_effect=_tem_foto,
        ):
            resposta = responder_pergunta_livre("quais rdos estao sem foto?")

        self.assertIn("encontrei 1 rdo", resposta["introducao"].lower())
        self.assertIn(f"RDO {rdo_antigo_sem_foto.rdo}", resposta["introducao"])
        self.assertNotIn("ultimos 150", resposta["introducao"].lower())

    def test_consulta_de_data_pulada_retorna_alerta_persistido_por_tipo(self):
        rdo = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="77",
            data=date(2026, 5, 17),
        )
        alerta = AlertaInteligente.objects.create(
            rdo=rdo,
            tipo="RDO_DATA_PULADA",
            mensagem="Ha lacuna de data entre o RDO anterior e este RDO.",
            prioridade="media",
            equipe_responsavel="coordenacao",
        )

        resposta = responder_pergunta_livre("quais rdos tem data pulada?")

        self.assertIn("data pulada", resposta["introducao"].lower())
        self.assertEqual(len(resposta["alertas"]), 1)
        self.assertEqual(resposta["alertas"][0].id, alerta.id)

    def test_consulta_de_tanque_incompleto_varre_rdotanque_mesmo_sem_alerta_persistido(self):
        rdo = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="88",
            data=date(2026, 5, 18),
        )
        RdoTanque.objects.create(
            rdo=rdo,
            tanque_codigo="TQ-INCOMPLETO",
            nome_tanque="TQ-INCOMPLETO",
            tipo_tanque=None,
            numero_compartimentos=None,
            volume_tanque_exec=None,
        )

        resposta = responder_pergunta_livre("quais rdos tem tanque incompleto?")

        self.assertIn("tanque incompleto", resposta["introducao"].lower())
        self.assertGreaterEqual(len(resposta["alertas"]), 1)
        self.assertIn(f"RDO {rdo.rdo}", resposta["introducao"])
        self.assertIn("nº de compartimentos", resposta["introducao"])
        self.assertNotIn("estÃ¡", resposta["introducao"])
        self.assertNotIn("nÂº", resposta["introducao"])

    def test_alerta_tanque_incompleto_usa_equipe_rdo(self):
        rdo = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="188",
            data=date(2026, 5, 18),
        )
        RdoTanque.objects.create(
            rdo=rdo,
            tanque_codigo="TQ-RDO",
            nome_tanque="TQ-RDO",
            tipo_tanque=None,
            numero_compartimentos=None,
            volume_tanque_exec=None,
        )

        resposta = gerar_resposta_rdos_tanque_incompleto()
        alerta = next(item for item in resposta["alertas"] if getattr(item, "rdo_id", None) == rdo.id)

        self.assertEqual(alerta.equipe_responsavel, "rdo")
        self.assertEqual(alerta.get_equipe_responsavel_display(), "RDO")

    def test_resposta_tanque_incompleto_limita_exibicao_e_indica_total(self):
        for indice in range(12):
            rdo = RDO.objects.create(
                ordem_servico=self.os_obj,
                rdo=str(300 + indice),
                data=date(2026, 5, 18),
            )
            RdoTanque.objects.create(
                rdo=rdo,
                tanque_codigo=f"TQ-{indice}",
                nome_tanque=f"TQ-{indice}",
                tipo_tanque=None,
                numero_compartimentos=None,
                volume_tanque_exec=None,
            )

        resposta = gerar_resposta_rdos_tanque_incompleto()

        self.assertIn("Mostrando os 10 primeiros de 12 registros.", resposta["introducao"])
        self.assertIn("Principais pendências encontradas:", resposta["introducao"])

    def test_pendencias_por_equipe_exibe_label_rdo(self):
        from alertas_inteligentes.views import gerar_resposta_pendencias_por_equipe

        rdo = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="189",
            data=date(2026, 5, 18),
        )
        AlertaInteligente.objects.create(
            rdo=rdo,
            tipo="RDO_TANQUE_INCOMPLETO",
            mensagem="Tanque incompleto",
            prioridade="alta",
            equipe_responsavel="rdo",
        )

        resposta = gerar_resposta_pendencias_por_equipe()

        self.assertIn("- RDO: 1 pendencia(s)", resposta["introducao"])

    def test_preenchimento_fraco_ignora_caso_leve_sem_execucao(self):
        rdo = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="89",
            data=date(2026, 5, 18),
            observacoes_rdo_pt="ok",
            planejamento_pt="ok",
        )

        avaliacao = avaliar_preenchimento_rdo(rdo)
        resultados = listar_rdos_preenchimento_ruim()

        self.assertEqual(avaliacao["nivel"], "normal")
        self.assertNotIn(rdo.id, [item["rdo"].id for item in resultados])

    def test_preenchimento_fraco_classifica_execucao_sem_campos_como_critico(self):
        rdo = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="90",
            data=date(2026, 5, 19),
            exist_pt=True,
            observacoes_rdo_pt="",
            planejamento_pt="",
        )
        RdoTanque.objects.create(
            rdo=rdo,
            tanque_codigo="TQ-CRITICO",
            nome_tanque="TQ-CRITICO",
            ensacamento_dia=20,
            tipo_tanque=None,
            numero_compartimentos=None,
            volume_tanque_exec=None,
        )

        with patch(
            "alertas_inteligentes.services.rdos_preenchimento_ruim.rdo_tem_foto",
            return_value=False,
        ):
            avaliacao = avaliar_preenchimento_rdo(rdo)
            resultados = listar_rdos_preenchimento_ruim()

        self.assertEqual(avaliacao["nivel"], "critico")
        self.assertIn("pt_sem_numero", avaliacao["subtipos"])
        self.assertIn("tanque_incompleto_execucao", avaliacao["subtipos"])
        self.assertIn(rdo.id, [item["rdo"].id for item in resultados])

    def test_alertas_pendentes_seleciona_amostra_sortida_e_sem_mencionar_fila(self):
        rdo_pt = RDO.objects.create(ordem_servico=self.os_obj, rdo="201", data=date(2026, 5, 18))
        rdo_data = RDO.objects.create(ordem_servico=self.os_obj, rdo="202", data=date(2026, 5, 19))
        rdo_foto = RDO.objects.create(ordem_servico=self.os_obj, rdo="203", data=date(2026, 5, 20))
        rdo_preench = RDO.objects.create(ordem_servico=self.os_obj, rdo="204", data=date(2026, 5, 21))
        rdo_tanque = RDO.objects.create(ordem_servico=self.os_obj, rdo="205", data=date(2026, 5, 22))
        rdo_gap = RDO.objects.create(ordem_servico=self.os_obj, rdo="206", data=date(2026, 5, 23))
        RDO.objects.filter(pk=rdo_gap.pk).update(status_analise_ia="pendente")

        alerta_pt = AlertaInteligente.objects.create(
            rdo=rdo_pt,
            tipo="PT_SEM_NUMERO",
            mensagem="PT sem numero",
            prioridade="alta",
            equipe_responsavel="coordenacao",
        )
        alerta_data = AlertaInteligente.objects.create(
            rdo=rdo_data,
            tipo="RDO_DATA_PULADA",
            mensagem="Data pulada",
            prioridade="media",
            equipe_responsavel="coordenacao",
        )

        with patch(
            "alertas_inteligentes.services.alertas_rdo_consolidados.listar_rdos_sem_foto",
            return_value=[{"rdo": rdo_foto, "prioridade": "baixa"}],
        ), patch(
            "alertas_inteligentes.services.alertas_rdo_consolidados.listar_rdos_preenchimento_ruim",
            return_value=[{"rdo": rdo_preench, "avaliacao": {"nivel": "critico", "problemas": ["Observacao fraca"]}}],
        ), patch(
            "alertas_inteligentes.services.alertas_rdo_consolidados.listar_achados_dinamicos_tanque_incompleto",
            return_value=[{"rdo": rdo_tanque, "mensagem": "Tanque incompleto."}],
        ), patch(
            "alertas_inteligentes.services.alertas_rdo_consolidados.listar_rdos_lancados_fora_do_dia",
            return_value=[
                {
                    "rdo": rdo_gap,
                    "data_operacional": date(2026, 5, 23),
                    "data_lancamento": date(2026, 5, 24),
                    "dias_atraso": 1,
                    "nivel": "baixo",
                }
            ],
        ):
            alertas_info = listar_alertas_rdo_consolidados(limit_exibicao=6, limit_scan=None)
            resposta = responder_alertas_pendentes()

        tipos = [alerta.tipo for alerta in alertas_info["alertas"]]
        self.assertEqual(
            tipos,
            [
                alerta_pt.tipo,
                alerta_data.tipo,
                "RDO_TANQUE_INCOMPLETO",
                "RDO_PREENCHIMENTO_RUIM",
                "RDO_LANCADO_FORA_DO_DIA",
                "FOTO_AUSENTE",
            ],
        )
        self.assertNotIn("pendentes de analise inteligente", resposta["introducao"].lower())
        self.assertIn("Separei ate 28 itens distribuidos por tipo", resposta["introducao"])

    def test_listar_rdos_lancados_fora_do_dia_pega_gap_de_ontem_lancado_hoje(self):
        ontem = timezone.localdate() - timedelta(days=1)
        hoje = timezone.localdate()
        rdo = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="207",
            data=ontem,
        )
        tanque = RdoTanque.objects.create(
            rdo=rdo,
            tanque_codigo="TQ-GAP",
            nome_tanque="TQ-GAP",
        )
        RdoTanque.objects.filter(pk=tanque.pk).update(
            created_at=timezone.make_aware(
                datetime.combine(hoje, time.min)
            )
        )

        resultados = listar_rdos_lancados_fora_do_dia()

        item = next((resultado for resultado in resultados if resultado["rdo"].id == rdo.id), None)
        self.assertIsNotNone(item)
        self.assertEqual(item["dias_atraso"], 1)
        self.assertEqual(item["data_operacional"], ontem)
        self.assertEqual(item["data_lancamento"], hoje)

    def test_detector_de_anomalia_ignora_outros_tanques_da_mesma_os(self):
        for indice in range(1, 6):
            rdo = RDO.objects.create(
                ordem_servico=self.os_obj,
                rdo=str(300 + indice),
                data=date(2026, 5, indice),
            )
            RdoTanque.objects.create(
                rdo=rdo,
                tanque_codigo="TQ-01",
                nome_tanque="TQ-01",
                ensacamento_dia=100,
                tempo_bomba=Decimal("4.00"),
                percentual_avanco_cumulativo=Decimal(str(indice * 5)),
                numero_compartimentos=2,
                compartimentos_avanco_json=json.dumps(
                    {"1": {"mecanizada": 5, "fina": 0}, "2": {"mecanizada": 5, "fina": 0}}
                ),
            )
            RdoTanque.objects.create(
                rdo=rdo,
                tanque_codigo="TQ-99",
                nome_tanque="TQ-99",
                ensacamento_dia=500,
                tempo_bomba=Decimal("6.00"),
                percentual_avanco_cumulativo=Decimal(str(indice * 8)),
                numero_compartimentos=2,
                compartimentos_avanco_json=json.dumps(
                    {"1": {"mecanizada": 8, "fina": 0}, "2": {"mecanizada": 8, "fina": 0}}
                ),
            )

        rdo_atual = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="306",
            data=date(2026, 5, 6),
        )
        RdoTanque.objects.create(
            rdo=rdo_atual,
            tanque_codigo="TQ-01",
            nome_tanque="TQ-01",
            ensacamento_dia=110,
            tempo_bomba=Decimal("4.20"),
            percentual_avanco_cumulativo=Decimal("30.00"),
            numero_compartimentos=2,
            compartimentos_avanco_json=json.dumps(
                {"1": {"mecanizada": 6, "fina": 0}, "2": {"mecanizada": 5, "fina": 0}}
            ),
        )

        resultado = detectar_anomalia_rdo(rdo_atual)

        self.assertEqual(resultado["nivel"], "normal")

    def test_detector_de_anomalia_explicita_tanque_e_metricas_fora_do_padrao(self):
        for indice in range(1, 6):
            rdo = RDO.objects.create(
                ordem_servico=self.os_obj,
                rdo=str(400 + indice),
                data=date(2026, 5, indice),
            )
            RdoTanque.objects.create(
                rdo=rdo,
                tanque_codigo="TQ-02",
                nome_tanque="TQ-02",
                ensacamento_dia=100,
                tempo_bomba=Decimal("4.00"),
                percentual_avanco_cumulativo=Decimal(str(indice * 5)),
                numero_compartimentos=2,
                compartimentos_avanco_json=json.dumps(
                    {"1": {"mecanizada": 5, "fina": 0}, "2": {"mecanizada": 4, "fina": 1}}
                ),
            )

        rdo_atual = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="406",
            data=date(2026, 5, 6),
        )
        RdoTanque.objects.create(
            rdo=rdo_atual,
            tanque_codigo="TQ-02",
            nome_tanque="TQ-02",
            ensacamento_dia=450,
            tempo_bomba=Decimal("0.50"),
            percentual_avanco_cumulativo=Decimal("55.00"),
            numero_compartimentos=2,
            compartimentos_avanco_json=json.dumps(
                {"1": {"mecanizada": 25, "fina": 5}, "2": {"mecanizada": 22, "fina": 4}}
            ),
        )

        resultado = detectar_anomalia_rdo(rdo_atual)
        mensagem = montar_mensagem_anomalia(rdo_atual, resultado)

        self.assertIn(resultado["nivel"], ["revisao", "alerta"])
        self.assertIn("principal motivo", mensagem.lower())
        self.assertIn("métricas realmente fora do padrão", mensagem.lower())
        self.assertIn("base de comparação", mensagem.lower())
        self.assertIn("tanque tq-02", mensagem.lower())

    def test_alerta_de_anomalia_expoe_resumo_curto_e_metricas_principais(self):
        rdo = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="500",
            data=date(2026, 5, 20),
        )
        alerta = AlertaInteligente.objects.create(
            rdo=rdo,
            tipo="RDO_OUTLIER",
            mensagem="Mensagem longa de anomalia.",
            prioridade="alta",
            equipe_responsavel="operacao",
            anomaly_score=0.91,
            anomaly_flags={
                "tanques": [
                    {
                        "tank": "03P COT",
                        "score": 1.0,
                        "metric_flags": {
                            "ensacamento_dia": {
                                "label": "Ensacamento do dia",
                                "valor": 450.0,
                                "baseline": {"min": 80.0, "max": 140.0},
                                "severity": 1.0,
                            },
                            "tempo_bomba": {
                                "label": "Tempo de bomba",
                                "valor": 4.0,
                                "baseline": {"min": 3.0, "max": 5.0},
                                "severity": 0.6,
                                "relative_diff": 0.8,
                            },
                        },
                        "compartment_flags": {
                            "1": {
                                "fina": {
                                    "valor": 0.0,
                                    "baseline": {"min": 0.0, "max": 50.0},
                                    "severity": 0.6,
                                    "relative_diff": 0.9,
                                }
                            },
                            "4": {
                                "fina": {
                                    "valor": 100.0,
                                    "baseline": {"min": 0.0, "max": 0.0},
                                    "severity": 1.0,
                                }
                            }
                        },
                        "baseline": {
                            "historico_utilizado": 4,
                            "rdos_referencia": ["1", "2", "3", "4"],
                        },
                    }
                ]
            },
        )

        self.assertIn("diferente dos últimos registros", alerta.explicacao_curta.lower())
        self.assertIn("condição operacional real ou erro de preenchimento", alerta.acao_recomendada.lower())
        self.assertEqual(
            alerta.anomalia_titulo_operacional,
            "RDO fora do padrão",
        )
        self.assertEqual(len(alerta.anomalia_principal_motivo), 2)
        self.assertEqual(len(alerta.anomalia_metricas_principais), 1)
        self.assertGreaterEqual(len(alerta.anomalia_metricas_avaliadas), 2)
        self.assertIn("03P COT", alerta.anomalia_contexto)
        self.assertIn("compartimento 4 / limpeza fina", alerta.anomalia_principal_motivo[0].lower())
        self.assertIn("ensacamento do dia", alerta.anomalia_metricas_principais[0].lower())
        self.assertTrue(
            any("tempo de bomba" in item.lower() for item in alerta.anomalia_metricas_avaliadas)
        )
        self.assertTrue(
            any("dentro do intervalo recente" in item.lower() for item in alerta.anomalia_metricas_avaliadas)
        )
        self.assertIn("últimos 4 RDOs", alerta.anomalia_base_comparacao)

    def test_tela_do_assistente_expoe_hooks_de_audio_no_composer(self):
        admin = User.objects.create_user(
            username="admin_audio",
            password="senha123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(admin)

        resposta = self.client.get(
            reverse("alertas_inteligentes:assistente_rdo"),
            HTTP_HOST="localhost",
            secure=True,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'data-voice-trigger="true"', html=False)
        self.assertContains(resposta, 'aria-pressed="false"', html=False)
        self.assertContains(resposta, 'data-voice-input="true"', html=False)
        self.assertContains(resposta, 'data-voice-status="true"', html=False)
        self.assertContains(resposta, 'data-voice-wave="true"', html=False)
        self.assertContains(resposta, '>Voz<', html=False)

    def test_tela_do_assistente_carrega_script_js_na_pasta_estatica_correta(self):
        admin = User.objects.create_user(
            username="admin_script",
            password="senha123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(admin)

        resposta = self.client.get(
            reverse("alertas_inteligentes:assistente_rdo"),
            HTTP_HOST="localhost",
            secure=True,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(
            resposta,
            '/static/js/script',
            html=False,
        )

    def test_tela_supervisao_aprendizado_restrita_a_superuser_e_aprova_exemplo(self):
        comum = User.objects.create_user(username="usuario_comum", password="senha123")
        admin = User.objects.create_user(
            username="admin_ia",
            password="senha123",
            is_staff=True,
            is_superuser=True,
        )
        pergunta = PerguntaAssistenteIA.objects.create(
            pergunta="me da um panorama da OS 6231",
            pergunta_normalizada="me da um panorama da os 6231",
            status="entendida",
            intencao_detectada="consulta_os",
        )
        url = reverse("alertas_inteligentes:supervisionar_aprendizado")

        self.client.force_login(comum)
        resposta_negada = self.client.get(url, HTTP_HOST="localhost", secure=True)
        self.assertEqual(resposta_negada.status_code, 302)

        self.client.force_login(admin)
        resposta_ok = self.client.get(url, HTTP_HOST="localhost", secure=True)
        self.assertContains(resposta_ok, "Supervisao do aprendizado da IA")

        resposta_post = self.client.post(
            url,
            {"pergunta_id": pergunta.id, "intencao": "resumo_os"},
            HTTP_HOST="localhost",
            secure=True,
        )
        pergunta.refresh_from_db()

        self.assertEqual(resposta_post.status_code, 302)
        self.assertEqual(pergunta.status, "revisada")
        self.assertEqual(pergunta.exemplo_aprovado.intencao, "resumo_os")


@override_settings(OLLAMA_ENABLED=False)
class AnalisarRdosPendentesCommandTests(TestCase):
    def setUp(self):
        caches[COMMAND_EXECUTION_LOCK_CACHE_ALIAS].delete(COMMAND_EXECUTION_LOCK_KEY)
        self.cliente = Cliente.objects.create(nome="Cliente Cmd")
        self.unidade = Unidade.objects.create(nome="Unidade Cmd")
        self.supervisor = User.objects.create_user(
            username="supervisor_cmd",
            password="senha123",
        )
        self.coordenador = next(value for value, _ in OrdemServico.COORDENADORES if value)

    def _create_os(self, numero_os, status_operacao):
        return OrdemServico.objects.create(
            numero_os=numero_os,
            data_inicio=date(2026, 5, 1),
            data_fim=None,
            dias_de_operacao=0,
            servico="LIMPEZA",
            servicos="LIMPEZA",
            metodo="Manual",
            pob=1,
            tanque="",
            tanques=None,
            volume_tanque=Decimal("0.00"),
            Cliente=self.cliente,
            Unidade=self.unidade,
            tipo_operacao="Offshore",
            solicitante="Solicitante Teste",
            coordenador=self.coordenador,
            supervisor=self.supervisor,
            status_operacao=status_operacao,
            status_geral=status_operacao,
            status_comercial="Em aberto",
            status_planejamento="Pendente",
        )

    def _create_rdo_pendente(self, ordem_servico, numero_rdo, data_rdo=None):
        rdo = RDO.objects.create(
            ordem_servico=ordem_servico,
            rdo=str(numero_rdo),
            data=data_rdo or date(2026, 5, 2),
            status_analise_ia="pendente",
        )
        RDO.objects.filter(pk=rdo.pk).update(status_analise_ia="pendente")
        return RDO.objects.get(pk=rdo.pk)

    def test_sem_limite_analisa_todos_os_rdos_pendentes(self):
        os_andamento = self._create_os(9101, "Em Andamento")
        os_finalizada = self._create_os(9102, "Finalizada")
        rdo_1 = self._create_rdo_pendente(os_andamento, 1)
        rdo_2 = self._create_rdo_pendente(os_finalizada, 1)

        with patch(
            "alertas_inteligentes.management.commands.analisar_rdos_pendentes.validar_rdo",
            return_value=[],
        ) as validar_mock:
            call_command("analisar_rdos_pendentes", stdout=StringIO())

        rdo_1.refresh_from_db()
        rdo_2.refresh_from_db()

        self.assertEqual(validar_mock.call_count, 2)
        self.assertEqual(rdo_1.status_analise_ia, "analisado")
        self.assertEqual(rdo_2.status_analise_ia, "analisado")

    def test_com_limite_prioriza_os_em_andamento_antes_de_finalizada(self):
        os_andamento = self._create_os(9201, "Em Andamento")
        os_finalizada = self._create_os(9202, "Finalizada")
        rdo_andamento = self._create_rdo_pendente(os_andamento, 1)
        rdo_finalizada = self._create_rdo_pendente(os_finalizada, 1)

        with patch(
            "alertas_inteligentes.management.commands.analisar_rdos_pendentes.validar_rdo",
            return_value=[],
        ):
            call_command("analisar_rdos_pendentes", limite=1, stdout=StringIO())

        rdo_andamento.refresh_from_db()
        rdo_finalizada.refresh_from_db()

        self.assertEqual(rdo_andamento.status_analise_ia, "analisado")
        self.assertEqual(rdo_finalizada.status_analise_ia, "pendente")

    def test_com_limite_prioriza_rdo_mais_recente_dentro_da_mesma_prioridade(self):
        os_andamento_1 = self._create_os(9301, "Em Andamento")
        os_andamento_2 = self._create_os(9302, "Em Andamento")
        rdo_antigo = self._create_rdo_pendente(
            os_andamento_1,
            1,
            data_rdo=date(2026, 5, 1),
        )
        rdo_recente = self._create_rdo_pendente(
            os_andamento_2,
            1,
            data_rdo=date(2026, 5, 20),
        )

        with patch(
            "alertas_inteligentes.management.commands.analisar_rdos_pendentes.validar_rdo",
            return_value=[],
        ):
            call_command("analisar_rdos_pendentes", limite=1, stdout=StringIO())

        rdo_antigo.refresh_from_db()
        rdo_recente.refresh_from_db()

        self.assertEqual(rdo_recente.status_analise_ia, "analisado")
        self.assertEqual(rdo_antigo.status_analise_ia, "pendente")

    def test_nao_executa_quando_rotina_ja_esta_em_andamento(self):
        os_andamento = self._create_os(9401, "Em Andamento")
        rdo = self._create_rdo_pendente(os_andamento, 1)
        caches[COMMAND_EXECUTION_LOCK_CACHE_ALIAS].set(
            COMMAND_EXECUTION_LOCK_KEY,
            {
                "token": "externo",
                "command": "rodar_ia_synchro",
                "started_at": "2026-06-16T10:00:00",
            },
            timeout=60,
        )
        stdout = StringIO()

        with patch(
            "alertas_inteligentes.management.commands.analisar_rdos_pendentes.validar_rdo",
            return_value=[],
        ) as validar_mock:
            call_command("analisar_rdos_pendentes", stdout=stdout)

        rdo.refresh_from_db()
        self.assertEqual(validar_mock.call_count, 0)
        self.assertEqual(rdo.status_analise_ia, "pendente")
        self.assertIn("ja esta em execucao", stdout.getvalue().lower())

    def test_isola_falha_de_um_rdo_e_continua_os_demais_com_traceback(self):
        os_andamento = self._create_os(9402, "Em Andamento")
        rdo_com_erro = self._create_rdo_pendente(os_andamento, 1)
        rdo_ok = self._create_rdo_pendente(os_andamento, 2, data_rdo=date(2026, 5, 3))
        stdout = StringIO()

        def validar_side_effect(rdo):
            if rdo.pk == rdo_com_erro.pk:
                raise RuntimeError("falha controlada")
            return []

        with patch(
            "alertas_inteligentes.management.commands.analisar_rdos_pendentes.validar_rdo",
            side_effect=validar_side_effect,
        ):
            call_command("analisar_rdos_pendentes", stdout=stdout)

        rdo_com_erro.refresh_from_db()
        rdo_ok.refresh_from_db()

        self.assertEqual(rdo_com_erro.status_analise_ia, "erro")
        self.assertIn("falha controlada", rdo_com_erro.erro_analise_ia)
        self.assertEqual(rdo_ok.status_analise_ia, "analisado")

        output = stdout.getvalue()
        self.assertIn(f"RDO ID {rdo_com_erro.id}", output)
        self.assertIn("Traceback (most recent call last)", output)


class RodarIaSynchroCommandTests(TestCase):
    def setUp(self):
        caches[COMMAND_EXECUTION_LOCK_CACHE_ALIAS].delete(COMMAND_EXECUTION_LOCK_KEY)

    def test_repassa_limites_corretos_para_rdos_e_operacoes(self):
        with patch(
            "alertas_inteligentes.management.commands.rodar_ia_synchro.call_command"
        ) as call_command_mock:
            call_command(
                "rodar_ia_synchro",
                limite_rdos=50,
                limite_operacoes=25,
                stdout=StringIO(),
            )

        self.assertEqual(call_command_mock.call_count, 2)
        self.assertEqual(
            call_command_mock.call_args_list[0].args,
            ("analisar_rdos_pendentes",),
        )
        self.assertEqual(
            call_command_mock.call_args_list[0].kwargs,
            {"limite": 50},
        )
        self.assertEqual(
            call_command_mock.call_args_list[1].args,
            ("analisar_operacoes",),
        )
        self.assertEqual(
            call_command_mock.call_args_list[1].kwargs,
            {"limite": 25},
        )

    def test_nao_executa_quando_rotina_ja_esta_travada(self):
        caches[COMMAND_EXECUTION_LOCK_CACHE_ALIAS].set(
            COMMAND_EXECUTION_LOCK_KEY,
            {
                "token": "externo",
                "command": "analisar_operacoes",
                "started_at": "2026-06-16T11:00:00",
            },
            timeout=60,
        )
        stdout = StringIO()

        with patch(
            "alertas_inteligentes.management.commands.rodar_ia_synchro.call_command"
        ) as call_command_mock:
            call_command("rodar_ia_synchro", stdout=stdout)

        self.assertEqual(call_command_mock.call_count, 0)
        self.assertIn("ja esta em execucao", stdout.getvalue().lower())

    def test_libera_trava_apos_erro(self):
        with patch(
            "alertas_inteligentes.management.commands.rodar_ia_synchro.call_command",
            side_effect=RuntimeError("falha controlada"),
        ):
            with self.assertRaises(RuntimeError):
                call_command("rodar_ia_synchro", stdout=StringIO())

        self.assertIsNone(caches[COMMAND_EXECUTION_LOCK_CACHE_ALIAS].get(COMMAND_EXECUTION_LOCK_KEY))

        with patch(
            "alertas_inteligentes.management.commands.rodar_ia_synchro.call_command"
        ) as call_command_mock:
            call_command("rodar_ia_synchro", stdout=StringIO())

        self.assertEqual(call_command_mock.call_count, 2)


class AnalisarOperacoesCommandTests(TestCase):
    def setUp(self):
        caches[COMMAND_EXECUTION_LOCK_CACHE_ALIAS].delete(COMMAND_EXECUTION_LOCK_KEY)
        self.cliente = Cliente.objects.create(nome="Cliente Cmd OS")
        self.unidade = Unidade.objects.create(nome="Unidade Cmd OS")
        self.supervisor = User.objects.create_user(
            username="supervisor_cmd_os",
            password="senha123",
        )
        self.coordenador = next(value for value, _ in OrdemServico.COORDENADORES if value)
        self.os_obj = OrdemServico.objects.create(
            numero_os=9501,
            data_inicio=date(2026, 5, 1),
            data_fim=None,
            dias_de_operacao=0,
            servico="LIMPEZA",
            servicos="LIMPEZA",
            metodo="Manual",
            pob=1,
            tanque="",
            tanques=None,
            volume_tanque=Decimal("0.00"),
            Cliente=self.cliente,
            Unidade=self.unidade,
            tipo_operacao="Offshore",
            solicitante="Solicitante Teste",
            coordenador=self.coordenador,
            supervisor=self.supervisor,
            status_operacao="Em Andamento",
            status_geral="Em Andamento",
            status_comercial="Em aberto",
            status_planejamento="Pendente",
        )

    def test_nao_executa_quando_rotina_ja_esta_em_andamento(self):
        caches[COMMAND_EXECUTION_LOCK_CACHE_ALIAS].set(
            COMMAND_EXECUTION_LOCK_KEY,
            {
                "token": "externo",
                "command": "rodar_ia_synchro",
                "started_at": "2026-06-16T12:00:00",
            },
            timeout=60,
        )
        stdout = StringIO()

        with patch(
            "alertas_inteligentes.management.commands.analisar_operacoes.validar_os_operacional",
            return_value=[],
        ) as validar_os_mock, patch(
            "alertas_inteligentes.management.commands.analisar_operacoes.validar_supervisores_em_os_simultaneas",
            return_value=[],
        ) as validar_supervisor_mock:
            call_command("analisar_operacoes", stdout=stdout)

        self.assertEqual(validar_os_mock.call_count, 0)
        self.assertEqual(validar_supervisor_mock.call_count, 0)
        self.assertIn("ja esta em execucao", stdout.getvalue().lower())

    def test_nao_recria_alerta_operacional_igual_em_execucoes_seguidas(self):
        stdout = StringIO()

        call_command("analisar_operacoes", limite=10, stdout=stdout)
        call_command("analisar_operacoes", limite=10, stdout=stdout)

        alertas = AlertaOperacionalInteligente.objects.filter(
            ordem_servico=self.os_obj,
            tipo="OS_SEM_RDO_RECENTE",
            referencia=f"os_sem_rdo_linha_{self.os_obj.id}",
        ).order_by("id")

        self.assertEqual(alertas.count(), 1)
        self.assertEqual(alertas.first().status, "pendente")

    def test_reabre_mesmo_alerta_operacional_sem_criar_novo_historico(self):
        stdout = StringIO()

        call_command("analisar_operacoes", limite=10, stdout=stdout)
        alerta_inicial = AlertaOperacionalInteligente.objects.get(
            ordem_servico=self.os_obj,
            tipo="OS_SEM_RDO_RECENTE",
            referencia=f"os_sem_rdo_linha_{self.os_obj.id}",
        )

        self.os_obj.status_operacao = "Finalizada"
        self.os_obj.status_geral = "Finalizada"
        self.os_obj.save(update_fields=["status_operacao", "status_geral"])

        call_command("analisar_operacoes", limite=10, stdout=stdout)

        alerta_resolvido = AlertaOperacionalInteligente.objects.get(pk=alerta_inicial.pk)
        self.assertEqual(alerta_resolvido.status, "resolvido")

        self.os_obj.status_operacao = "Em Andamento"
        self.os_obj.status_geral = "Em Andamento"
        self.os_obj.save(update_fields=["status_operacao", "status_geral"])

        call_command("analisar_operacoes", limite=10, stdout=stdout)

        alertas = AlertaOperacionalInteligente.objects.filter(
            ordem_servico=self.os_obj,
            tipo="OS_SEM_RDO_RECENTE",
            referencia=f"os_sem_rdo_linha_{self.os_obj.id}",
        )
        self.assertEqual(alertas.count(), 1)
        alerta_reaberto = alertas.get()
        self.assertEqual(alerta_reaberto.pk, alerta_inicial.pk)
        self.assertEqual(alerta_reaberto.status, "pendente")

    def test_supervisor_conflito_usa_referencia_estavel_por_linha(self):
        outra_os = OrdemServico.objects.create(
            numero_os=9502,
            data_inicio=date(2026, 5, 2),
            data_fim=None,
            dias_de_operacao=0,
            servico="LIMPEZA",
            servicos="LIMPEZA",
            metodo="Manual",
            pob=1,
            tanque="TK-02",
            tanques="TK-02",
            volume_tanque=Decimal("0.00"),
            Cliente=self.cliente,
            Unidade=self.unidade,
            tipo_operacao="Offshore",
            solicitante="Solicitante Teste",
            coordenador=self.coordenador,
            supervisor=self.supervisor,
            status_operacao="Em Andamento",
            status_geral="Em Andamento",
            status_comercial="Em aberto",
            status_planejamento="Pendente",
        )

        call_command("analisar_operacoes", limite=10, stdout=StringIO())

        alertas = AlertaOperacionalInteligente.objects.filter(
            tipo="SUPERVISOR_EM_OS_SIMULTANEAS",
            ordem_servico__in=[self.os_obj, outra_os],
        ).order_by("ordem_servico_id")

        self.assertEqual(alertas.count(), 2)
        self.assertEqual(
            alertas[0].referencia,
            f"supervisor_conflito_{self.supervisor.username}_linha_{self.os_obj.id}",
        )
        self.assertEqual(
            alertas[1].referencia,
            f"supervisor_conflito_{self.supervisor.username}_linha_{outra_os.id}",
        )


@override_settings(OLLAMA_ENABLED=False)
class RdoValidatorConsolidacaoTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(nome="Cliente Validator")
        self.unidade = Unidade.objects.create(nome="Unidade Validator")
        self.coordenador = next(value for value, _ in OrdemServico.COORDENADORES if value)
        self.os_obj = OrdemServico.objects.create(
            numero_os=6401,
            data_inicio=date(2026, 6, 1),
            servico="LIMPEZA",
            servicos="LIMPEZA",
            metodo="Mecanizada",
            pob=4,
            tanque="TQ-VAL",
            tanques="TQ-VAL",
            volume_tanque=Decimal("0.00"),
            Cliente=self.cliente,
            Unidade=self.unidade,
            tipo_operacao="Offshore",
            solicitante="Solicitante Validator",
            coordenador=self.coordenador,
            status_operacao="Em Andamento",
            status_geral="Em Andamento",
            status_comercial="Em aberto",
            status_planejamento="Pendente",
        )

    def test_validar_dados_operacionais_considera_campos_diretos_do_rdo(self):
        rdo = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="501",
            data=date(2026, 6, 2),
            ensacamento=15,
            ensacamento_previsao=10,
        )

        alertas = validar_dados_operacionais(rdo)

        self.assertIn("VALOR_DIARIO_MAIOR_PREVISAO", [alerta.tipo for alerta in alertas])

    def test_turno_preenchido_nao_gera_alerta_de_turno_ausente(self):
        for index, turno in enumerate(("Diurno", "Noturno"), start=1):
            with self.subTest(turno=turno):
                rdo = RDO.objects.create(
                    ordem_servico=self.os_obj,
                    rdo=str(510 + index),
                    data=date(2026, 6, 2 + index),
                    turno=turno,
                )

                alertas = validar_campos_basicos(rdo)

                self.assertNotIn(
                    "RDO_SEM_TURNO",
                    [alerta.tipo for alerta in alertas],
                )

    def test_turno_vazio_gera_alerta_de_turno_ausente(self):
        rdo = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="513",
            data=date(2026, 6, 5),
            turno="",
        )

        alertas = validar_campos_basicos(rdo)

        self.assertEqual([alerta.tipo for alerta in alertas], ["RDO_SEM_TURNO"])

    def test_validar_fotos_considera_avanco_direto_do_rdo_sem_tanque(self):
        rdo = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="502",
            data=date(2026, 6, 3),
            ensacamento=12,
        )
        rdo.status = "Concluido"

        alertas = validar_fotos(rdo)

        self.assertIn("FOTO_AUSENTE", [alerta.tipo for alerta in alertas])

    def test_validar_observacoes_mantem_leitura_de_observacoes_rdo_pt(self):
        rdo = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="503",
            data=date(2026, 6, 4),
            observacoes_rdo_pt="Atividade pendente para continuidade",
        )
        rdo.status = "Concluido"

        alertas = validar_observacoes(rdo)

        self.assertIn("OBSERVACAO_INCOERENTE", [alerta.tipo for alerta in alertas])

    def test_validar_tanque_incompleto_nao_quebra_com_campos_ausentes(self):
        rdo = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="504",
            data=date(2026, 6, 5),
        )
        RdoTanque.objects.create(
            rdo=rdo,
            tanque_codigo="TQ-SEM-DADOS",
            nome_tanque="TQ-SEM-DADOS",
        )

        alertas = validar_tanque_incompleto_rdo(rdo)

        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0].tipo, "RDO_TANQUE_INCOMPLETO")

    def test_criar_alerta_serializa_datas_em_metadados_de_anomalia(self):
        rdo = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="505",
            data=date(2026, 6, 6),
        )

        alerta = criar_alerta(
            rdo=rdo,
            tipo="RDO_OUTLIER",
            mensagem="Anomalia detectada.",
            prioridade="alta",
            equipe="operacao",
            referencia="anomalia_datas",
            anomaly_score=0.91,
            anomaly_flags={"date": {"last_date": date(2026, 6, 5)}},
            baseline_snapshot={"ultima_data": date(2026, 6, 4)},
        )

        alerta.refresh_from_db()

        self.assertEqual(
            alerta.anomaly_flags["date"]["last_date"],
            "2026-06-05",
        )
        self.assertEqual(
            alerta.baseline_snapshot["ultima_data"],
            "2026-06-04",
        )

    def test_montar_mensagem_anomalia_com_historico_curto_nao_quebra_bounds(self):
        rdo_anterior = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="506",
            data=date(2026, 6, 7),
        )
        RdoTanque.objects.create(
            rdo=rdo_anterior,
            tanque_codigo="TQ-ANOM",
            nome_tanque="TQ-ANOM",
            percentual_avanco_cumulativo=Decimal("15.00"),
        )

        rdo_atual = RDO.objects.create(
            ordem_servico=self.os_obj,
            rdo="507",
            data=date(2026, 6, 8),
        )
        RdoTanque.objects.create(
            rdo=rdo_atual,
            tanque_codigo="TQ-ANOM",
            nome_tanque="TQ-ANOM",
            percentual_avanco_cumulativo=Decimal("150.00"),
        )

        resultado = detectar_anomalia_rdo(rdo_atual)
        mensagem = montar_mensagem_anomalia(rdo_atual, resultado)

        self.assertIn("RDO marcado para revisão", mensagem)
        self.assertIn("Ação recomendada", mensagem)
