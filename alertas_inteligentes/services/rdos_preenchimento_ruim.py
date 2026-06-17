from GO.models import RDO
from alertas_inteligentes.models import AlertaInteligente
from alertas_inteligentes.services.rdos_sem_foto import rdo_tem_foto
from alertas_inteligentes.services.field_utils import get_field_safe


def normalizar(texto):
    return str(texto or "").strip().lower()


def get_field(obj, *names, default=None):
    return get_field_safe(obj, *names, default=default)


def texto_curto(valor, minimo=25):
    texto = str(valor or "").strip()
    return len(texto) < minimo


def campo_vazio(valor):
    if valor is None:
        return True

    texto = str(valor).strip().lower()

    return texto in [
        "",
        "-",
        "n/a",
        "na",
        "não informado",
        "nao informado",
        "sem informação",
        "sem informacao",
    ]


def bool_true(valor):
    if valor is True:
        return True

    texto = str(valor or "").strip().lower()
    return texto in ["sim", "true", "1", "yes"]


def _float_or_zero(valor):
    try:
        if valor in (None, ""):
            return 0.0
        return float(str(valor).replace(",", "."))
    except Exception:
        return 0.0


def _listar_tanques(rdo):
    try:
        return list(rdo.tanques.all())
    except Exception:
        return []


def _tem_execucao_tanque(rdo, tanques):
    if _float_or_zero(get_field(rdo, "percentual_avanco", default=0)) > 0:
        return True

    for tanque in tanques:
        sinais = [
            get_field(tanque, "tempo_bomba", default=0),
            get_field(tanque, "ensacamento_dia", default=0),
            get_field(tanque, "icamento_dia", default=0),
            get_field(tanque, "cambagem_dia", default=0),
            get_field(tanque, "limpeza_mecanizada_diaria", default=0),
            get_field(tanque, "limpeza_fina_diaria", default=0),
            get_field(tanque, "percentual_avanco", default=0),
        ]
        if any(_float_or_zero(sinal) > 0 for sinal in sinais):
            return True

    return False


def _tem_atividade_real(rdo):
    try:
        if getattr(rdo, "total_atividades_efetivas_min", 0) > 0:
            return True
    except Exception:
        pass

    try:
        atividades = list(rdo.atividades_rdo.all())
    except Exception:
        atividades = []

    for atividade in atividades:
        nome = str(getattr(atividade, "atividade", "") or "").strip()
        comentario = str(getattr(atividade, "comentario_pt", "") or "").strip()
        if nome or comentario:
            return True

    return False


def _pt_indicado(rdo):
    if bool_true(get_field(rdo, "exist_pt", "houve_abertura_pt", "abertura_pt", "teve_pt", default=False)):
        return True

    for campo in ("pt_manha", "pt_tarde", "pt_noite"):
        if not campo_vazio(get_field(rdo, campo, default="")):
            return True

    try:
        return getattr(rdo, "total_abertura_pt_min", 0) > 0
    except Exception:
        return False


def _espaco_confinado_indicado(rdo):
    if bool_true(get_field(rdo, "confinado", "houve_acesso_espaco_confinado", "acesso_espaco_confinado", "espaco_confinado", default=False)):
        return True

    if not campo_vazio(get_field(rdo, "ec_times_json", default="")):
        return True

    for campo in (
        "entrada_confinado",
        "saida_confinado",
        "entrada_confinado_1",
        "saida_confinado_1",
        "entrada_confinado_2",
        "saida_confinado_2",
        "entrada_confinado_3",
        "saida_confinado_3",
        "entrada_confinado_4",
        "saida_confinado_4",
        "entrada_confinado_5",
        "saida_confinado_5",
        "entrada_confinado_6",
        "saida_confinado_6",
    ):
        if get_field(rdo, campo, default=None):
            return True

    return False


def _faltas_espaco_confinado(rdo):
    faltas = []
    pares = [
        ("entrada_confinado", "saida_confinado"),
        ("entrada_confinado_1", "saida_confinado_1"),
        ("entrada_confinado_2", "saida_confinado_2"),
        ("entrada_confinado_3", "saida_confinado_3"),
        ("entrada_confinado_4", "saida_confinado_4"),
        ("entrada_confinado_5", "saida_confinado_5"),
        ("entrada_confinado_6", "saida_confinado_6"),
    ]
    tem_qualquer_horario = False
    for entrada, saida in pares:
        ent = get_field(rdo, entrada, default=None)
        sai = get_field(rdo, saida, default=None)
        if ent or sai:
            tem_qualquer_horario = True
        if ent and not sai:
            faltas.append("Espaco confinado com entrada informada e saida ausente.")
        if sai and not ent:
            faltas.append("Espaco confinado com saida informada e entrada ausente.")

    if not tem_qualquer_horario:
        faltas.append("Espaco confinado informado sem horarios de entrada e saida.")

    if campo_vazio(get_field(rdo, "total_n_efetivo_confinado", "equipe_espaco_confinado", "quantidade_pessoas_espaco_confinado", "pessoas_espaco_confinado", default="")):
        faltas.append("Espaco confinado informado sem equipe ou quantidade de pessoas.")

    return faltas


def _observacoes_principais(rdo):
    return (
        get_field(
            rdo,
            "observacoes_rdo_pt",
            "observacoes",
            "observacao",
            "comentarios",
            "comentario",
            default="",
        )
        or ""
    )


def _planejamento_principal(rdo):
    return (
        get_field(
            rdo,
            "planejamento_pt",
            "planejamento_proximo_turno",
            "planejamento",
            "proximo_turno",
            "observacao_proximo_turno",
            default="",
        )
        or ""
    )


def _atividade_descritiva_curta(rdo):
    try:
        atividades = list(rdo.atividades_rdo.all())
    except Exception:
        atividades = []

    if not atividades:
        return True

    nomes = [str(getattr(atividade, "atividade", "") or "").strip() for atividade in atividades]
    comentarios = [str(getattr(atividade, "comentario_pt", "") or "").strip() for atividade in atividades]
    texto = " ".join([parte for parte in nomes + comentarios if parte])
    return texto_curto(texto, minimo=30)


def avaliar_preenchimento_rdo(rdo):
    problemas = []
    subtipos = []
    pontos = 0

    tanques = _listar_tanques(rdo)
    tem_execucao_tanque = _tem_execucao_tanque(rdo, tanques)
    tem_atividade_real = _tem_atividade_real(rdo)
    contexto_execucao = tem_execucao_tanque or tem_atividade_real

    observacoes = _observacoes_principais(rdo)
    planejamento = _planejamento_principal(rdo)
    tem_pt = _pt_indicado(rdo)
    tem_confinado = _espaco_confinado_indicado(rdo)

    if contexto_execucao and not tem_atividade_real:
        pontos += 4
        subtipos.append("execucao_sem_atividade")
        problemas.append("Houve sinal de execucao operacional, mas nao encontrei atividade relevante registrada no RDO.")

    if contexto_execucao and texto_curto(observacoes, minimo=35):
        pontos += 1
        subtipos.append("observacao_fraca")
        problemas.append("Observacoes da execucao estao muito curtas ou ausentes.")

    if contexto_execucao and _atividade_descritiva_curta(rdo):
        pontos += 1
        subtipos.append("atividade_pouco_detalhada")
        problemas.append("Atividades registradas com pouco detalhe para explicar o que foi feito.")

    status_operacao = normalizar(get_field(get_field(rdo, "ordem_servico", default=None), "status_operacao", default=""))
    if status_operacao == "em andamento" and contexto_execucao and texto_curto(planejamento, minimo=20):
        pontos += 1
        subtipos.append("planejamento_curto")
        problemas.append("Planejamento do proximo turno ausente ou pouco detalhado.")

    if contexto_execucao and not rdo_tem_foto(rdo):
        pontos += 2
        subtipos.append("sem_foto_execucao")
        problemas.append("Nao identifiquei foto ou anexo em um RDO com execucao operacional.")

    if tem_pt and all(campo_vazio(get_field(rdo, campo, default="")) for campo in ("pt_manha", "pt_tarde", "pt_noite")):
        pontos += 4
        subtipos.append("pt_sem_numero")
        problemas.append("Foi informada abertura de PT, mas nenhum numero de PT foi preenchido.")

    if tem_confinado:
        faltas_confinado = _faltas_espaco_confinado(rdo)
        if faltas_confinado:
            pontos += 4
            subtipos.append("confinado_incompleto")
            problemas.extend(faltas_confinado[:2])

    if tem_execucao_tanque:
        faltas_tanque = []
        for tanque in tanques:
            if campo_vazio(get_field(tanque, "tipo_tanque", default="")):
                faltas_tanque.append("tipo do tanque")
            if get_field(tanque, "numero_compartimentos", default=None) in (None, ""):
                faltas_tanque.append("numero de compartimentos")
            if get_field(tanque, "volume_tanque_exec", "volume_tanque", "volume", default=None) in (None, ""):
                faltas_tanque.append("volume do tanque")
            if faltas_tanque:
                break
        if faltas_tanque:
            pontos += 4
            subtipos.append("tanque_incompleto_execucao")
            problemas.append(
                "O RDO teve execucao no tanque, mas faltam dados principais: " + ", ".join(faltas_tanque[:3]) + "."
            )

    if pontos >= 6:
        nivel = "critico"
    elif pontos >= 3:
        nivel = "incompleto"
    elif pontos > 0:
        nivel = "leve"
    else:
        nivel = "normal"

    return {
        "pontos": pontos,
        "nivel": nivel,
        "problemas": problemas,
        "subtipos": subtipos,
        "contexto_execucao": contexto_execucao,
    }


def identificar_rdo(rdo):
    os_obj = get_field(rdo, "ordem_servico", default=None)

    numero_os = get_field(os_obj, "numero_os", "os", "numero", default="Nao informada")
    numero_rdo = get_field(rdo, "rdo", "numero_rdo", "numero", "id", default=getattr(rdo, "id", ""))
    data = get_field(rdo, "data", "data_rdo", "data_operacao", default=None)

    supervisor = (
        get_field(rdo, "supervisor", default=None)
        or get_field(os_obj, "supervisor", "supervisor_responsavel", default=None)
        or "Nao informado"
    )

    unidade = get_field(os_obj, "unidade", default=None)
    tanque = get_field(os_obj, "tanque", default=None)

    partes = [f"OS {numero_os}", f"RDO {numero_rdo}"]

    if data:
        try:
            partes.append(data.strftime("%d/%m/%Y"))
        except Exception:
            pass

    if unidade:
        partes.append(str(unidade))

    if tanque:
        partes.append(f"Tanque {tanque}")

    partes.append(f"Supervisor: {supervisor}")

    return " | ".join(partes)


def listar_rdos_preenchimento_ruim(limite=None):
    rdos = RDO.objects.select_related("ordem_servico").order_by("-id")

    if limite is not None:
        rdos = rdos[:limite]

    resultados = []

    for rdo in rdos:
        avaliacao = avaliar_preenchimento_rdo(rdo)

        if avaliacao["nivel"] in ["critico", "incompleto"]:
            resultados.append(
                {
                    "rdo": rdo,
                    "identificacao": identificar_rdo(rdo),
                    "avaliacao": avaliacao,
                }
            )

    ordem_nivel = {"critico": 0, "incompleto": 1}
    resultados.sort(
        key=lambda item: (
            ordem_nivel.get(item["avaliacao"]["nivel"], 9),
            -item["avaliacao"]["pontos"],
            -item["rdo"].id,
        )
    )
    return resultados


def gerar_resposta_rdos_preenchimento_ruim(limite=None):
    resultados = listar_rdos_preenchimento_ruim(limite=limite)
    escopo = f"os ultimos {limite} RDOs" if limite is not None else "todos os RDOs disponiveis"

    if not resultados:
        return {
            "introducao": f"Analisei {escopo} e nao encontrei RDOs com preenchimento critico ou incompleto.",
            "alertas": [],
            "alertas_operacionais": [],
            "recomendacao": "Nenhuma acao imediata e necessaria para esse ponto no momento.",
            "fontes": ["RDOs", "Campos de preenchimento"],
            "confianca": "media",
            "tipo_resposta": "rdos_preenchimento_ruim",
        }

    total_criticos = sum(1 for item in resultados if item["avaliacao"]["nivel"] == "critico")
    total_incompletos = sum(1 for item in resultados if item["avaliacao"]["nivel"] == "incompleto")

    linhas = [
        f"Analisei {escopo} e encontrei {len(resultados)} RDO(s) com preenchimento critico ou incompleto.",
        "",
        "Resumo:",
        f"- {total_criticos} RDO(s) com preenchimento critico",
        f"- {total_incompletos} RDO(s) com preenchimento incompleto",
        "",
        "Critérios avaliados:",
        "- execucao operacional sem atividade relevante",
        "- PT informada sem numero preenchido",
        "- espaco confinado sem horarios ou equipe",
        "- execucao de tanque com dados principais faltando",
        "- execucao operacional sem foto ou anexo",
        "- observacoes e planejamento muito fracos em contexto de execucao",
        "",
        "Principais RDOs encontrados:",
    ]

    for idx, item in enumerate(resultados[:15], start=1):
        avaliacao = item["avaliacao"]

        linhas.append("")
        linhas.append(f"{idx}. {item['identificacao']}")
        linhas.append(f"   Nivel: {avaliacao['nivel'].upper()} | Pontuacao: {avaliacao['pontos']}")

        for problema in avaliacao["problemas"][:5]:
            linhas.append(f"   - {problema}")

    alertas = AlertaInteligente.objects.filter(
        rdo__in=[item["rdo"] for item in resultados[:20]],
        status="pendente"
    ).select_related("rdo")[:20]

    return {
        "introducao": "\n".join(linhas),
        "alertas": alertas,
        "alertas_operacionais": [],
        "recomendacao": (
            "Recomendo revisar primeiro os RDOs criticos. A prioridade deve ser completar atividade, PT, espaco confinado, dados do tanque e evidencias da execucao."
        ),
        "fontes": ["RDOs", "Campos de preenchimento", "Alertas inteligentes"],
        "confianca": "media",
        "tipo_resposta": "rdos_preenchimento_ruim",
    }
