from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.db import models
from django.utils import timezone

from GO.models import OrdemServico


class ExemploIntencaoIA(models.Model):
    INTENCOES = [
        ("consulta_os", "Consulta de OS"),
        ("consulta_rdo", "Consulta de RDO"),
        ("consulta_supervisor", "Consulta de supervisor"),
        ("resumo_os", "Resumo de OS"),
        ("linha_tempo_os", "Linha do tempo da OS"),
        ("comparacao_rdos", "Comparacao entre RDOs"),
        ("operacao_parada", "Operacao parada"),
        ("analise_supervisor", "Analise de supervisor"),
        ("analise_unidade", "Analise de unidade"),
        ("priorizacao", "Prioridades"),
        ("resumo_diario", "Resumo diario"),
        ("os_sem_rdo_recente", "OS sem RDO recente"),
        ("supervisores_conflito", "Supervisores em conflito"),
        ("pendencias_gerais", "Pendencias gerais"),
    ]

    frase = models.TextField()
    frase_normalizada = models.TextField(db_index=True, unique=True)
    intencao = models.CharField(max_length=50, choices=INTENCOES)
    ativo = models.BooleanField(default=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="exemplos_intencao_ia_criados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-atualizado_em"]

    def __str__(self):
        return f"{self.get_intencao_display()} - {self.frase[:80]}"


class PerguntaAssistenteIA(models.Model):
    STATUS = [
        ("entendida", "Entendida"),
        ("nao_entendida", "Nao entendida"),
        ("revisada", "Revisada"),
    ]

    pergunta = models.TextField()
    pergunta_normalizada = models.TextField(db_index=True)
    intencao_detectada = models.CharField(
        max_length=50,
        choices=ExemploIntencaoIA.INTENCOES,
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=20, choices=STATUS, default="nao_entendida")
    contexto = models.JSONField(default=dict, blank=True)
    revisada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="perguntas_ia_revisadas",
    )
    exemplo_aprovado = models.ForeignKey(
        ExemploIntencaoIA,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="perguntas_origem",
    )
    criada_em = models.DateTimeField(auto_now_add=True)
    revisada_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criada_em"]

    def __str__(self):
        return f"{self.get_status_display()} - {self.pergunta[:80]}"

class AlertaInteligente(models.Model):
    PRIORIDADES = [
        ("baixa", "Baixa"),
        ("media", "Média"),
        ("alta", "Alta"),
        ("critica", "Crítica"),
    ]

    STATUS = [
        ("pendente", "Pendente"),
        ("em_analise", "Em análise"),
        ("resolvido", "Resolvido"),
        ("ignorado", "Ignorado com justificativa"),
    ]

    EQUIPES = [
        ("operacao", "Operação"),
        ("coordenacao", "Coordenação"),
        ("qsms", "QSMS"),
        ("administrativo", "Administrativo"),
        ("rdo", "RDO"),
    ]

    TIPOS = [
        ("RDO_SEM_TURNO", "RDO sem turno"),
        ("RDO_DATA_PULADA", "RDO com data pulada na sequencia"),

        ("PT_SEM_TURNO", "PT sem turno informado"),
        ("PT_SEM_NUMERO", "PT sem número"),
        ("PT_INCOERENTE", "PT incoerente"),

        ("ATIVIDADE_SEM_HORARIO", "Atividade sem horário"),
        ("ATIVIDADE_SOBREPOSTA", "Atividades sobrepostas"),

        ("ESPACO_CONFINADO_SEM_HORARIO", "Espaço confinado sem horário"),
        ("ESPACO_CONFINADO_INCOERENTE", "Espaço confinado incoerente"),

        ("OPERADORES_MAIOR_EQUIPE", "Operadores maior que equipe"),
        ("VALOR_DIARIO_MAIOR_PREVISAO", "Valor diário maior que previsão"),
        ("AVANCO_INVALIDO", "Avanço inválido"),

        ("FOTO_AUSENTE", "Foto ausente"),
        ("OBSERVACAO_INCOERENTE", "Observação incoerente"),

        ("RDO_OUTLIER", "RDO com comportamento fora do padrão"),
        ("RDO_REVISAR_ANOMALIA", "RDO marcado para revisão estatística"),
        
        ("RDO_TANQUE_INCOMPLETO", "Tanque com dados incompletos no RDO"),
    ]

    rdo = models.ForeignKey(
        "GO.RDO",
        on_delete=models.CASCADE,
        related_name="alertas_inteligentes"
    )

    tipo = models.CharField(max_length=100, choices=TIPOS)
    mensagem = models.TextField()

    prioridade = models.CharField(
        max_length=20,
        choices=PRIORIDADES,
        default="media"
    )

    equipe_responsavel = models.CharField(
        max_length=50,
        choices=EQUIPES,
        default="operacao"
    )

    status = models.CharField(
        max_length=30,
        choices=STATUS,
        default="pendente"
    )

    referencia = models.CharField(
        max_length=100,
        null=True,
        blank=True
    )

    # Fields to store anomaly detection metadata (Fase 2)
    anomaly_score = models.FloatField(null=True, blank=True)
    anomaly_flags = models.JSONField(
        null=True,
        blank=True,
        help_text="Flags técnicas que explicam o motivo da anomalia."
    )
    baseline_snapshot = models.JSONField(
        null=True,
        blank=True,
        help_text="Resumo estatístico usado na análise."
    )
    
    resolvido_por = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alertas_resolvidos"
    )
    
    ignorado_por = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alertas_ignorados"
    )

    justificativa = models.TextField(null=True, blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    resolvido_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["tipo"]),
            models.Index(fields=["prioridade"]),
            models.Index(fields=["equipe_responsavel"]),
            models.Index(fields=["referencia"]),
        ]

    @property
    def identificacao_operacional(self):
        rdo = self.rdo

        numero_rdo = getattr(rdo, "numero_rdo", None) or getattr(rdo, "rdo", None) or rdo.id
        os_obj = getattr(rdo, "ordem_servico", None) or getattr(rdo, "os", None)
        numero_os = None

        if os_obj:
            numero_os = (
                getattr(os_obj, "numero_os", None)
                or getattr(os_obj, "numero", None)
                or getattr(os_obj, "codigo", None)
                or os_obj.id
            )

        if numero_os:
            return f"OS {numero_os} | RDO {numero_rdo}"

        return f"RDO {numero_rdo}"

    @property
    def explicacao_curta(self):
        explicacoes = {
            "RDO_DATA_PULADA": "Existe uma lacuna de datas entre este RDO e o anterior da mesma OS.",
            "PT_SEM_TURNO": "O RDO informou abertura de PT, mas nao marcou o turno correspondente.",
            "PT_SEM_NUMERO": "O RDO indicou abertura de PT, mas faltou numero em pelo menos um turno.",
            "PT_INCOERENTE": "Os dados de PT registrados no RDO estao incoerentes e precisam de revisao.",
            "ATIVIDADE_SEM_HORARIO": "Existe atividade registrada sem horario de inicio ou fim.",
            "ATIVIDADE_SOBREPOSTA": "Existem atividades com horario sobreposto no mesmo RDO.",
            "ESPACO_CONFINADO_SEM_HORARIO": "O RDO indica espaco confinado, mas faltam horarios de entrada ou saida.",
            "ESPACO_CONFINADO_INCOERENTE": "Os horarios ou campos de espaco confinado nao estao coerentes.",
            "OPERADORES_MAIOR_EQUIPE": "O total de operadores simultaneos esta maior que a equipe informada.",
            "VALOR_DIARIO_MAIOR_PREVISAO": "O valor diario lancado ultrapassa a previsao informada.",
            "AVANCO_INVALIDO": "O avancao ou percentual informado esta fora do limite esperado.",
            "FOTO_AUSENTE": "O RDO indica execucao, mas nao traz evidencia fotografica ou anexo esperado.",
            "OBSERVACAO_INCOERENTE": "A observacao registrada nao parece coerente com os demais campos do RDO.",
            "RDO_TANQUE_INCOMPLETO": "O RDO possui tanque com dados principais faltando para calculo e rastreio operacional.",
            "RDO_OUTLIER": "Este RDO esta fora do padrao recente da propria OS no mesmo tanque.",
            "RDO_REVISAR_ANOMALIA": "Este RDO apresentou desvio relevante em relacao ao historico recente da OS e merece revisao.",
        }
        return explicacoes.get(self.tipo)

    @property
    def acao_recomendada(self):
        acoes = {
            "RDO_DATA_PULADA": "Confirme se faltou lancar algum RDO intermediario ou se a sequencia de datas foi preenchida incorretamente.",
            "PT_SEM_TURNO": "Revise o bloco de PT e marque corretamente o turno de abertura.",
            "PT_SEM_NUMERO": "Preencha o numero da PT no turno correspondente ou remova a marcacao indevida.",
            "PT_INCOERENTE": "Revise os dados de PT comparando turno, numero e contexto operacional do dia.",
            "ATIVIDADE_SEM_HORARIO": "Preencha os horarios faltantes ou remova a atividade que nao ocorreu.",
            "ATIVIDADE_SOBREPOSTA": "Revise a sequencia das atividades e ajuste horarios que se sobrepoem sem justificativa.",
            "ESPACO_CONFINADO_SEM_HORARIO": "Preencha os horarios de entrada e saida do espaco confinado.",
            "ESPACO_CONFINADO_INCOERENTE": "Revise os horarios e os campos de espaco confinado antes de validar o RDO.",
            "OPERADORES_MAIOR_EQUIPE": "Confirme se a equipe foi preenchida corretamente ou se o total de operadores simultaneos esta superestimado.",
            "VALOR_DIARIO_MAIOR_PREVISAO": "Confira se o valor lancado esta correto ou se a previsao precisa ser atualizada.",
            "AVANCO_INVALIDO": "Revise os percentuais e cumulativos do tanque antes de concluir a analise.",
            "FOTO_AUSENTE": "Verifique se houve foto pendente de upload ou se a execucao do dia precisa de evidencia complementar.",
            "OBSERVACAO_INCOERENTE": "Ajuste a observacao para refletir o que realmente ocorreu na operacao.",
            "RDO_TANQUE_INCOMPLETO": "Complete os dados do tanque para permitir calculo de avancos, compartimentos e demais validacoes.",
            "RDO_OUTLIER": "Confirme se houve uma condicao operacional excepcional ou se algum valor do tanque foi preenchido fora do esperado.",
            "RDO_REVISAR_ANOMALIA": "Compare este RDO com os ultimos do mesmo tanque e valide se o desvio faz sentido operacionalmente.",
        }
        return acoes.get(self.tipo)

    @property
    def anomalia_titulo_operacional(self):
        if self.tipo not in {"RDO_OUTLIER", "RDO_REVISAR_ANOMALIA"}:
            return ""
        return "RDO fora do padrao da OS" if self.tipo == "RDO_OUTLIER" else "RDO com desvio relevante para revisao"

    @property
    def anomalia_contexto(self):
        if self.tipo not in {"RDO_OUTLIER", "RDO_REVISAR_ANOMALIA"}:
            return ""
        tanques = (self.anomaly_flags or {}).get("tanques") or []
        nomes = [str(item.get("tank") or "").strip() for item in tanques if str(item.get("tank") or "").strip()]
        if not nomes:
            return ""
        if len(nomes) == 1:
            return f"Tanque {nomes[0]}"
        return "Tanques " + ", ".join(nomes)

    @property
    def anomalia_metricas_principais(self):
        if self.tipo not in {"RDO_OUTLIER", "RDO_REVISAR_ANOMALIA"}:
            return []
        tanques = (self.anomaly_flags or {}).get("tanques") or []
        itens = []
        for tanque in tanques:
            nome_tanque = tanque.get("tank") or "tanque nao identificado"
            metricas = sorted(
                (tanque.get("metric_flags") or {}).values(),
                key=lambda item: item.get("severity", 0),
                reverse=True,
            )
            for metrica in metricas[:3]:
                baseline = metrica.get("baseline") or {}
                itens.append(
                    f"{nome_tanque} - {metrica.get('label')}: valor deste RDO {self._format_metric_value(metrica.get('valor'))}. "
                    f"Historico recente entre {self._format_metric_value(baseline.get('min'))} e {self._format_metric_value(baseline.get('max'))}."
                )
            compartimentos = tanque.get("compartment_flags") or {}
            for compartimento, categorias in list(compartimentos.items())[:2]:
                categorias_ordenadas = sorted(
                    categorias.items(),
                    key=lambda item: item[1].get("severity", 0),
                    reverse=True,
                )
                for categoria, dados in categorias_ordenadas[:2]:
                    baseline = dados.get("baseline") or {}
                    label = "limpeza fina" if categoria == "fina" else "limpeza mecanizada"
                    itens.append(
                        f"{nome_tanque} - Compartimento {compartimento} ({label}): valor deste RDO {self._format_metric_value(dados.get('valor'))}%. "
                        f"Historico recente entre {self._format_metric_value(baseline.get('min'))}% e {self._format_metric_value(baseline.get('max'))}%."
                    )
        return itens[:6]

    @property
    def anomalia_base_comparacao(self):
        if self.tipo not in {"RDO_OUTLIER", "RDO_REVISAR_ANOMALIA"}:
            return ""
        tanques = (self.anomaly_flags or {}).get("tanques") or []
        partes = []
        for tanque in tanques:
            referencia = (tanque.get("baseline") or {}).get("rdos_referencia") or []
            nome_tanque = tanque.get("tank") or "tanque nao identificado"
            if referencia:
                partes.append(
                    f"{nome_tanque}: ultimos {len(referencia)} RDOs ({', '.join(str(item) for item in referencia)})"
                )
        return " | ".join(partes)

    @staticmethod
    def _format_metric_value(value):
        if value in (None, ""):
            return "n/d"
        try:
            value = float(value)
        except Exception:
            try:
                value = float(str(value).replace(",", "."))
            except Exception:
                return str(value)
        if value.is_integer():
            return str(int(value))
        return str(round(value, 2)).replace(".", ",")

    def __str__(self):
        rdo = self.rdo

        numero_rdo = getattr(rdo, "numero_rdo", None) or getattr(rdo, "rdo", None) or rdo.id
        os_obj = getattr(rdo, "ordem_servico", None) or getattr(rdo, "os", None)

        numero_os = None

        if os_obj:
            numero_os = (
                getattr(os_obj, "numero_os", None)
                or getattr(os_obj, "numero", None)
                or getattr(os_obj, "codigo", None)
                or os_obj.id
            )

        if numero_os:
            return f"OS {numero_os} | RDO {numero_rdo} - {self.tipo}"

        return f"RDO {numero_rdo} - {self.tipo}"

class AlertaOperacionalInteligente(models.Model):
    PRIORIDADES = [
        ("baixa", "Baixa"),
        ("media", "Média"),
        ("alta", "Alta"),
        ("critica", "Critica")
    ]
    
    STATUS = [
        ("pendente", "Pendente"),
        ("resolvido", "Resolvido"),
        ("ignorado", "Ignorado"),
    ]
    
    TIPOS = [
        ("OS_SEM_RDO_RECENTE", "OS em andamento sem RDO recente"),
        ("SUPERVISOR_EM_OS_SIMULTANEAS", "Supervisor em OS simultâneas"),
        ("OS_SEM_SUPERVISOR", "Os em andamento sem supervisor"),
        ("OS_FINALIZADA_MOVIMENTACAO_ABERTA", "OS finalizada com movimentação aberta"),
        ("OS_PROGRAMADA_ATRASADA", "OS programada atrasada"),
        ("POUCOS_RDOS_PARA_DIAS_OPERACAO", "Poucos RDOs para dias de operação"),
        ("OPERACAO_SEM_DATA_INICIO", "Operação sem data de início"),
        ("MOVIMENTACAO_SEM_DATA", "Movimentação sem data"),
    ]
    
    ordem_servico = models.ForeignKey(
        OrdemServico,
        on_delete=models.CASCADE,
        related_name="alertas_operacionais_ia"
    )

    tipo = models.CharField(max_length=100, choices=TIPOS)
    referencia = models.CharField(max_length=120, null=True, blank=True)

    mensagem = models.TextField()

    prioridade = models.CharField(
        max_length=20,
        choices=PRIORIDADES,
        default="media"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS,
        default="pendente"
    )

    justificativa = models.TextField(null=True, blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    resolvido_em = models.DateTimeField(null=True, blank=True)

    resolvido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alertas_operacionais_resolvidos"
    )

    ignorado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alertas_operacionais_ignorados"
    )

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["tipo"]),
            models.Index(fields=["prioridade"]),
            models.Index(fields=["referencia"]),
        ]

    def __str__(self):
        return f"{self.identificacao_operacional} - {self.tipo}"

    @property
    def identificacao_operacional(self):
        os_obj = self.ordem_servico

        numero_os = (
            getattr(os_obj, "numero_os", None)
            or getattr(os_obj, "os", None)
            or getattr(os_obj, "numero", None)
            or os_obj.id
        )

        unidade = getattr(os_obj, "unidade", None)
        tanque = getattr(os_obj, "tanque", None)
        supervisor = (
            getattr(os_obj, "supervisor", None)
            or getattr(os_obj, "supervisor_responsavel", None)
        )

        sequencia = (
            getattr(os_obj, "sequencia_movimentacao", None)
            or getattr(os_obj, "sequencia_da_movimentacao", None)
            or getattr(os_obj, "seq_movimentacao", None)
        )

        data_inicio_mov = (
            getattr(os_obj, "data_inicio_movimentacao", None)
            or getattr(os_obj, "data_inicio_da_movimentacao", None)
        )

        partes = [f"OS {numero_os}"]

        if sequencia:
            partes.append(f"Mov. {sequencia}")

        partes.append(f"Linha {os_obj.id}")

        if unidade:
            partes.append(str(unidade))

        if tanque:
            partes.append(f"Tanque {tanque}")

        if supervisor:
            partes.append(f"Supervisor: {supervisor}")

        if data_inicio_mov:
            partes.append(f"Início Mov.: {data_inicio_mov}")

        return " | ".join(partes)

    @property
    def explicacao_curta(self):
        explicacoes = {
            "OS_SEM_RDO_RECENTE": "A linha operacional está em andamento, mas não recebeu RDO recente.",
            "SUPERVISOR_EM_OS_SIMULTANEAS": "O supervisor aparece em mais de uma linha operacional aberta.",
            "OS_SEM_SUPERVISOR": "A linha operacional está em andamento sem supervisor definido.",
            "OS_FINALIZADA_MOVIMENTACAO_ABERTA": "A operação foi finalizada, mas a movimentação ainda não consta como finalizada.",
            "OS_PROGRAMADA_ATRASADA": "A linha está programada, mas há indício de atraso no início da operação.",
            "POUCOS_RDOS_PARA_DIAS_OPERACAO": "A quantidade de RDOs parece baixa em relação aos dias de operação.",
            "OPERACAO_SEM_DATA_INICIO": "A operação não possui data de início registrada.",
            "MOVIMENTACAO_SEM_DATA": "A movimentação está sem data relevante preenchida.",
        }

        return explicacoes.get(
            self.tipo,
            "Alerta operacional identificado pela análise inteligente.",
        )

    @property
    def acao_recomendada(self):
        acoes = {
            "OS_SEM_RDO_RECENTE": "Verifique se a operação ainda está ativa. Se estiver, confirme se há RDO pendente de lançamento. Caso contrário, atualize o status da linha.",
            "SUPERVISOR_EM_OS_SIMULTANEAS": "Confirme se o supervisor realmente está alocado nessas linhas ou se alguma movimentação anterior precisa ser finalizada.",
            "OS_SEM_SUPERVISOR": "Defina o supervisor responsável pela linha operacional.",
            "OS_FINALIZADA_MOVIMENTACAO_ABERTA": "Revise a movimentação e finalize a linha, se a operação já foi encerrada.",
            "OS_PROGRAMADA_ATRASADA": "Confirme se a operação iniciou ou se a programação precisa ser reagendada.",
            "POUCOS_RDOS_PARA_DIAS_OPERACAO": "Verifique se existem RDOs pendentes ou se a contagem de dias da operação está correta.",
        }

        return acoes.get(
            self.tipo,
            "Revise os dados da linha operacional e confirme se a informação está correta.",
        )
