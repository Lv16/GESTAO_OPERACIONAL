import json
from datetime import datetime, timedelta

from django.core.serializers.json import DjangoJSONEncoder

from alertas_inteligentes.models import AlertaInteligente
from alertas_inteligentes.services.anomaly_detector import detectar_anomalia_rdo, montar_mensagem_anomalia
from alertas_inteligentes.services.field_utils import get_field_safe

def identificar_rdo(rdo):
    os_obj = get_field(rdo, "ordem_servico", "os", "ordem", default=None)

    numero_os = None

    if os_obj:
        numero_os = get_field(
            os_obj,
            "numero_os",
            "numero",
            "codigo",
            "id",
            default=None
        )

    numero_rdo = get_field(
        rdo,
        "numero_rdo",
        "rdo",
        "numero",
        "id",
        default=rdo.id
    )

    cliente = None

    if os_obj:
        cliente_obj = get_field(os_obj, "cliente", default=None)
        if cliente_obj:
            cliente = str(cliente_obj)
    
    partes = []

    if numero_os:
        partes.append(f"OS{numero_os}")
    
    if numero_rdo:
        partes.append(f"RDO {numero_rdo}")

    if cliente:
        partes.append(f"Cliente: {cliente}")

    return " | ".join(partes) or f"RDO ID {rdo.id}"



PALAVRAS_ESPACO_CONFINADO = [
    "espaço confinado",
    "espaco confinado",
    "entrada no tanque",
    "entrou no tanque",
    "interior do tanque",
    "limpeza interna",
    "acesso interno",
    "trabalho interno",
    "inspeção interna",
    "inspecao interna",
]

PALAVRAS_PENDENCIA = [
    "pendente",
    "aguardando",
    "não finalizado",
    "nao finalizado",
    "não concluído",
    "nao concluido",
    "retorno necessário",
    "retorno necessario",
    "sem liberação",
    "sem liberacao",
    "sem acesso",
]

PALAVRAS_PT = [
    "pt",
    "permissão de trabalho",
    "permissao de trabalho",
    "liberação",
    "liberacao",
]


def get_field(obj, *names, default=None):
    return get_field_safe(obj, *names, default=default)


def sanitize_json_value(value):
    if value is None:
        return None

    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def text(value):
    return str(value or "").strip()


def lower(value):
    return text(value).lower()


def to_number(value):
    if value in [None, ""]:
        return None

    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def get_tanques(rdo):
    try:
        return list(rdo.tanques.all())
    except Exception:
        return []


def get_atividades(rdo):
    try:
        return list(rdo.atividades_rdo.all())
    except Exception:
        return []


def get_equipe_count(rdo):
    try:
        count = rdo.membros_equipe.filter(em_servico=True).count()
        if count:
            return count
    except Exception:
        pass

    membros = get_field(rdo, "membros", default="")
    if membros:
        try:
            parsed = json.loads(membros)
            if isinstance(parsed, list):
                return len(parsed)
        except Exception:
            pass
        return len([item for item in str(membros).splitlines() if item.strip()])

    return None


def get_fotos_count(rdo):
    count = 0
    for field_name in ["fotos_img", "fotos_1", "fotos_2", "fotos_3", "fotos_4", "fotos_5"]:
        value = get_field(rdo, field_name)
        if getattr(value, "name", None):
            count += 1

    fotos_json = get_field(rdo, "fotos_json")
    if fotos_json:
        try:
            parsed = json.loads(fotos_json)
            if isinstance(parsed, list):
                count += len([item for item in parsed if item])
        except Exception:
            pass

    return count


def get_tanque_label(tanque):
    return text(
        get_field(tanque, "tanque_codigo", "nome_tanque", default=getattr(tanque, "id", ""))
    )


def criar_alerta(
    rdo,
    tipo,
    mensagem,
    prioridade="media",
    equipe="operacao",
    referencia=None,
    anomaly_score=None,
    anomaly_flags=None,
    baseline_snapshot=None,
):
    """
    Evita duplicar alerta pendente do mesmo tipo para o mesmo RDO.
    Aceita metadados opcionais de anomalia para persistência.
    """
    identificacao = identificar_rdo(rdo)

    mensagem_final = f"{identificacao} - {mensagem}"

    alerta = AlertaInteligente.objects.filter(
        rdo=rdo,
        tipo=tipo,
        referencia=referencia,
        status__in=["pendente", "em_analise"]
    ).first()

    if alerta:
        alerta.mensagem = mensagem_final
        alerta.prioridade = prioridade
        alerta.equipe_responsavel = equipe
        # update anomaly fields when provided
        update_fields = ["mensagem", "prioridade", "equipe_responsavel"]
        if anomaly_score is not None:
            alerta.anomaly_score = anomaly_score
            update_fields.append("anomaly_score")
        if anomaly_flags is not None:
            alerta.anomaly_flags = sanitize_json_value(anomaly_flags)
            update_fields.append("anomaly_flags")
        if baseline_snapshot is not None:
            alerta.baseline_snapshot = sanitize_json_value(baseline_snapshot)
            update_fields.append("baseline_snapshot")

        alerta.save(update_fields=update_fields)
        return alerta

    create_kwargs = {
        "rdo": rdo,
        "tipo": tipo,
        "mensagem": mensagem_final,
        "prioridade": prioridade,
        "equipe_responsavel": equipe,
        "referencia": referencia,
    }
    if anomaly_score is not None:
        create_kwargs["anomaly_score"] = anomaly_score
    if anomaly_flags is not None:
        create_kwargs["anomaly_flags"] = sanitize_json_value(anomaly_flags)
    if baseline_snapshot is not None:
        create_kwargs["baseline_snapshot"] = sanitize_json_value(baseline_snapshot)

    return AlertaInteligente.objects.create(**create_kwargs)
    


def sim(valor):
    return lower(valor) in ["sim", "s", "true", "1", "yes"]


def nao(valor):
    return lower(valor) in ["não", "nao", "n", "false", "0", "no"]


def contem_alguma_palavra(texto_base, palavras):
    texto_base = lower(texto_base)
    return any(palavra in texto_base for palavra in palavras)


def formatar_data_br(data):
    try:
        return data.strftime("%d/%m/%Y")
    except Exception:
        return text(data)


def parse_numero_rdo(valor):
    try:
        return int(str(valor or "").strip())
    except Exception:
        return None


def listar_datas_entre(data_inicio, data_fim):
    datas = []
    atual = data_inicio + timedelta(days=1)
    while atual < data_fim:
        datas.append(atual)
        atual += timedelta(days=1)
    return datas


def validar_campos_basicos(rdo):
    alertas = []

    # This is a persisted, structured field. Normalize only surrounding
    # whitespace so a valid choice is never treated as missing.
    turno = text(get_field(rdo, "turno"))

    if not turno:
        alertas.append(
            criar_alerta(
                rdo,
                "RDO_SEM_TURNO",
                "O RDO foi registrado sem turno informado.",
                "media",
                "operacao"
            )
        )

    return alertas


def _rdo_duplicate_snapshot(rdo):
    atividades = 0
    equipe = 0
    tanques = 0
    try:
        atividades = rdo.atividades_rdo.count()
    except Exception:
        pass
    try:
        equipe = rdo.membros_equipe.count()
    except Exception:
        pass
    try:
        tanques = rdo.tanques.count()
    except Exception:
        pass

    fotos = get_fotos_count(rdo)
    observacao = text(get_field(rdo, "observacoes_rdo_pt", "observacoes"))
    pob = to_number(get_field(rdo, "pob")) or 0
    preenchimentos = sum([
        bool(observacao),
        atividades > 0,
        equipe > 0,
        tanques > 0,
        fotos > 0,
        pob > 0,
        get_field(rdo, "exist_pt") is not None,
    ])
    return {
        "score": preenchimentos,
        "observacao": lower(observacao),
        "atividades": atividades,
        "equipe": equipe,
        "tanques": tanques,
        "fotos": fotos,
        "pob": pob,
    }


def validar_rdo_duplicado(rdo):
    """Identifica provável duplicidade sem excluir ou alterar nenhum RDO."""
    data = get_field(rdo, "data", "data_inicio")
    turno = lower(get_field(rdo, "turno"))
    os_obj = get_field(rdo, "ordem_servico", default=None)
    if not data or not os_obj:
        return []

    numero_os = get_field(os_obj, "numero_os", default=None)
    queryset = rdo.__class__.objects.filter(data=data).exclude(pk=getattr(rdo, "pk", None))
    if numero_os not in (None, ""):
        queryset = queryset.filter(ordem_servico__numero_os=numero_os)
    else:
        queryset = queryset.filter(ordem_servico=os_obj)

    candidatos = [
        candidato
        for candidato in queryset.select_related("ordem_servico")
        if lower(get_field(candidato, "turno")) == turno
    ]
    if not candidatos:
        return []

    atual = _rdo_duplicate_snapshot(rdo)
    alertas = []
    for candidato in candidatos:
        comparado = _rdo_duplicate_snapshot(candidato)
        if atual["score"] < comparado["score"]:
            suspeito, completo = rdo, candidato
            dados_suspeito, dados_completo = atual, comparado
        elif comparado["score"] < atual["score"]:
            suspeito, completo = candidato, rdo
            dados_suspeito, dados_completo = comparado, atual
        else:
            suspeito, completo = (
                (rdo, candidato)
                if (getattr(rdo, "id", 0) or 0) > (getattr(candidato, "id", 0) or 0)
                else (candidato, rdo)
            )
            dados_suspeito, dados_completo = (
                (atual, comparado) if suspeito.pk == rdo.pk else (comparado, atual)
            )

        ids = sorted([int(rdo.pk), int(candidato.pk)])
        mesma_observacao = bool(
            dados_suspeito["observacao"]
            and dados_suspeito["observacao"] == dados_completo["observacao"]
        )
        data_br = formatar_data_br(data)
        turno_label = text(get_field(rdo, "turno")) or "não informado"
        evidencias = []
        if mesma_observacao:
            evidencias.append("os dois registros possuem a mesma observação")
        ausencias = []
        if dados_suspeito["atividades"] == 0:
            ausencias.append("atividades")
        if dados_suspeito["equipe"] == 0:
            ausencias.append("equipe")
        if dados_suspeito["tanques"] == 0:
            ausencias.append("tanque")
        if dados_suspeito["fotos"] == 0:
            ausencias.append("fotos")
        if dados_suspeito["pob"] <= 0:
            ausencias.append("POB")
        if ausencias:
            evidencias.append(
                f"o RDO {get_field(suspeito, 'rdo', default=suspeito.pk)} está sem "
                + ", ".join(ausencias)
            )

        numero_suspeito = get_field(suspeito, "rdo", default=suspeito.pk)
        numero_completo = get_field(completo, "rdo", default=completo.pk)
        mensagem = (
            f"Possível duplicidade: os RDOs {numero_suspeito} e {numero_completo} são da mesma OS, "
            f"foram registrados em {data_br} e estão no turno {turno_label}."
        )
        if evidencias:
            mensagem += " O Synchro destacou este caso porque " + "; e ".join(evidencias) + "."
        mensagem += (
            f" Compare os dois registros antes de decidir. Nenhum RDO foi excluído automaticamente."
        )
        alertas.append(
            criar_alerta(
                suspeito,
                "RDO_DUPLICADO",
                mensagem,
                "alta" if mesma_observacao and len(ausencias) >= 2 else "media",
                "coordenacao",
                referencia=f"duplicidade_rdos_{ids[0]}_{ids[1]}",
            )
        )

    return alertas


def validar_sequencia_datas(rdo):
    alertas = []
    data_atual = get_field(rdo, "data", "data_rdo", "data_operacao")
    ordem_servico = get_field(rdo, "ordem_servico", "os", "ordem", default=None)

    if not data_atual or not ordem_servico:
        return alertas

    numero_atual = parse_numero_rdo(get_field(rdo, "rdo", "numero_rdo", "numero"))
    rdo_model = rdo.__class__
    qs = (
        rdo_model.objects
        .filter(ordem_servico=ordem_servico, data__isnull=False)
        .exclude(pk=getattr(rdo, "pk", None))
    )

    anterior = None
    if numero_atual is not None:
        candidatos = []
        for candidato in qs.only("id", "rdo", "data"):
            numero_candidato = parse_numero_rdo(get_field(candidato, "rdo", "numero_rdo", "numero"))
            if numero_candidato is not None and numero_candidato < numero_atual:
                candidatos.append((numero_candidato, candidato))
        if candidatos:
            anterior = sorted(candidatos, key=lambda item: item[0])[-1][1]

    if anterior is None:
        anterior = qs.filter(data__lt=data_atual).order_by("-data", "-id").first()

    if anterior is None:
        return alertas

    data_anterior = get_field(anterior, "data", "data_rdo", "data_operacao")
    if not data_anterior or data_anterior >= data_atual:
        return alertas

    datas_faltantes = listar_datas_entre(data_anterior, data_atual)
    if not datas_faltantes:
        return alertas

    if len(datas_faltantes) == 1:
        trecho_datas = formatar_data_br(datas_faltantes[0])
    else:
        trecho_datas = f"{formatar_data_br(datas_faltantes[0])} a {formatar_data_br(datas_faltantes[-1])}"

    alertas.append(
        criar_alerta(
            rdo,
            "RDO_DATA_PULADA",
            (
                f"Ha lacuna de data entre o RDO anterior ({formatar_data_br(data_anterior)}) "
                f"e este RDO ({formatar_data_br(data_atual)}). Data(s) sem RDO: {trecho_datas}."
            ),
            "media",
            "coordenacao",
        )
    )

    return alertas


def validar_pt(rdo):
    alertas = []

    houve_pt = get_field(rdo, "exist_pt", "houve_abertura_pt", "abertura_pt", "houve_pt")

    pt_manha = get_field(rdo, "pt_manha", "numero_pt_manha")
    pt_tarde = get_field(rdo, "pt_tarde", "numero_pt_tarde")
    pt_noite = get_field(rdo, "pt_noite", "numero_pt_noite")

    turnos_pt = get_field(rdo, "select_turnos", default=[])
    turnos_pt_text = lower(" ".join(turnos_pt) if isinstance(turnos_pt, (list, tuple)) else turnos_pt)
    turno_pt_manha = get_field(rdo, "turno_pt_manha", "pt_turno_manha") or "manha" in turnos_pt_text or "manh" in turnos_pt_text
    turno_pt_tarde = get_field(rdo, "turno_pt_tarde", "pt_turno_tarde") or "tarde" in turnos_pt_text
    turno_pt_noite = get_field(rdo, "turno_pt_noite", "pt_turno_noite") or "noite" in turnos_pt_text

    if sim(houve_pt):
        marcou_algum_turno = any([
            bool(turno_pt_manha),
            bool(turno_pt_tarde),
            bool(turno_pt_noite),
        ])

        if not marcou_algum_turno:
            alertas.append(
                criar_alerta(
                    rdo,
                    "PT_SEM_TURNO",
                    "Foi informado que houve abertura de PT, mas nenhum turno de abertura foi marcado.",
                    "alta",
                    "operacao"
                )
            )

        if turno_pt_manha and not pt_manha:
            alertas.append(
                criar_alerta(
                    rdo,
                    "PT_SEM_NUMERO",
                    "Foi marcada abertura de PT no turno da manhã, mas o número da PT Manhã não foi preenchido.",
                    "alta",
                    "operacao",
                    referencia="pt_manha"
                )
            )

        if turno_pt_tarde and not pt_tarde:
            alertas.append(
                criar_alerta(
                    rdo,
                    "PT_SEM_NUMERO",
                    "Foi marcada abertura de PT no turno da tarde, mas o número da PT Tarde não foi preenchido.",
                    "alta",
                    "operacao",
                    referencia="pt_tarde"
                )
            )

        if turno_pt_noite and not pt_noite:
            alertas.append(
                criar_alerta(
                    rdo,
                    "PT_SEM_NUMERO",
                    "Foi marcada abertura de PT no turno da noite, mas o número da PT Noite não foi preenchido.",
                    "alta",
                    "operacao",
                    referencia="pt_noite"
                )
            )

    if nao(houve_pt) and any([pt_manha, pt_tarde, pt_noite]):
        alertas.append(
            criar_alerta(
                rdo,
                "PT_INCOERENTE",
                "Foi informado que não houve abertura de PT, mas existe número de PT preenchido.",
                "media",
                "operacao"
            )
        )

    return alertas


def validar_espaco_confinado(rdo):
    alertas = []
    tanques = get_tanques(rdo)

    houve_ec = get_field(
        rdo,
        "confinado",
        "houve_acesso_espaco_confinado",
        "acesso_espaco_confinado",
        "houve_espaco_confinado"
    )
    if not houve_ec and any(sim(get_field(tanque, "espaco_confinado")) for tanque in tanques):
        houve_ec = True

    observacoes = get_field(rdo, "observacoes_rdo_pt", "observacoes", "observacoes_pt", default="")
    planejamento = get_field(rdo, "planejamento_pt", "planejamento", "planejamento_pt", default="")
    comentarios_atividades = " ".join(
        text(get_field(atividade, "comentario_pt", "comentario_en", default=""))
        for atividade in get_atividades(rdo)
    )

    texto_contexto = " ".join([
        text(observacoes),
        text(planejamento),
        text(comentarios_atividades),
    ])

    entradas_ec = [
        get_field(rdo, "entrada_confinado", "entrada_espaco_confinado", "entrada_ec")
    ] + [get_field(rdo, f"entrada_confinado_{i}") for i in range(1, 7)]
    saidas_ec = [
        get_field(rdo, "saida_confinado", "saida_espaco_confinado", "saida_ec")
    ] + [get_field(rdo, f"saida_confinado_{i}") for i in range(1, 7)]
    entrada_ec = any(entradas_ec)
    saida_ec = any(saidas_ec)
    tempo_nao_efetivo = get_field(rdo, "total_n_efetivo_confinado", "tempo_nao_efetivo_ec", "tempo_nao_efetivo_espaco_confinado")

    if sim(houve_ec) and not entrada_ec and not saida_ec:
        alertas.append(
            criar_alerta(
                rdo,
                "ESPACO_CONFINADO_SEM_HORARIO",
                "Foi informado acesso ao espaço confinado, mas não há horários de entrada e saída preenchidos.",
                "alta",
                "qsms"
            )
        )

    if nao(houve_ec) and (entrada_ec or saida_ec):
        alertas.append(
            criar_alerta(
                rdo,
                "ESPACO_CONFINADO_INCOERENTE",
                "Foi informado que não houve acesso ao espaço confinado, mas existem horários de entrada/saída preenchidos.",
                "alta",
                "qsms"
            )
        )

    if nao(houve_ec) and contem_alguma_palavra(texto_contexto, PALAVRAS_ESPACO_CONFINADO):
        alertas.append(
            criar_alerta(
                rdo,
                "ESPACO_CONFINADO_INCOERENTE",
                "O RDO informa que não houve acesso ao espaço confinado, porém observações/atividades indicam possível entrada no tanque ou trabalho interno.",
                "alta",
                "qsms"
            )
        )

    if tempo_nao_efetivo:
        tempo_nao_efetivo_num = to_number(tempo_nao_efetivo)
        if tempo_nao_efetivo_num is not None and tempo_nao_efetivo_num < 0:
            alertas.append(
                criar_alerta(
                    rdo,
                    "ESPACO_CONFINADO_INCOERENTE",
                    "O tempo não-efetivo em espaço confinado está com valor negativo.",
                    "media",
                    "operacao"
                )
            )

    return alertas


def validar_dados_operacionais(rdo):
    alertas = []
    tanques = get_tanques(rdo)

    comparacoes = [
        (
            "ensacamento",
            None,
            to_number(get_field(rdo, "ensacamento_diario", "ensacamento")),
            to_number(get_field(rdo, "ensacamento_previsao_total", "previsao_ensacamento", "ensacamento_previsao")),
        ),
        (
            "icamento",
            None,
            to_number(get_field(rdo, "icamento_diario", "icamento")),
            to_number(get_field(rdo, "icamento_previsao_total", "previsao_icamento", "icamento_previsao")),
        ),
        (
            "cambagem",
            None,
            to_number(get_field(rdo, "cambagem_diario", "cambagem")),
            to_number(get_field(rdo, "cambagem_previsao_total", "previsao_cambagem", "cambagem_previsao")),
        ),
    ]

    for tanque in tanques:
        label = get_tanque_label(tanque)
        comparacoes.extend([
            (
                "ensacamento",
                label,
                to_number(get_field(tanque, "ensacamento_dia", "ensacamento_diario")),
                to_number(get_field(tanque, "ensacamento_prev", "ensacamento_previsao_total", "previsao_ensacamento")),
            ),
            (
                "icamento",
                label,
                to_number(get_field(tanque, "icamento_dia", "icamento_diario")),
                to_number(get_field(tanque, "icamento_prev", "icamento_previsao_total", "previsao_icamento")),
            ),
            (
                "cambagem",
                label,
                to_number(get_field(tanque, "cambagem_dia", "cambagem_diario")),
                to_number(get_field(tanque, "cambagem_prev", "cambagem_previsao_total", "previsao_cambagem")),
            ),
        ])

    for nome, label, valor_diario, valor_previsto in comparacoes:
        if valor_previsto is None or valor_diario is None or valor_diario <= valor_previsto:
            continue

        mensagem = (
            f"O {nome} diario do tanque {label} e maior que a previsao total."
            if label
            else f"O {nome} diario informado e maior que a previsao total da operacao."
        )
        alertas.append(
            criar_alerta(
                rdo,
                "VALOR_DIARIO_MAIOR_PREVISAO",
                mensagem,
                "media",
                "coordenacao"
            )
        )

    for field_name in [
        "avanco_limpeza",
        "avanco_limpeza_mecanizada_manual_robotizada",
        "limpeza_mecanizada_diaria",
        "limpeza_fina_diaria",
        "percentual_limpeza_diario",
        "percentual_limpeza_fina_diario",
        "percentual_avanco",
        "percentual_ensacamento",
        "percentual_icamento",
        "percentual_cambagem",
    ]:
        avanco = to_number(get_field(rdo, field_name))
        if avanco is not None and (avanco < 0 or avanco > 100):
            alertas.append(
                criar_alerta(
                    rdo,
                    "AVANCO_INVALIDO",
                    f"O campo {field_name} informado no RDO esta fora do intervalo permitido de 0% a 100%.",
                    "alta",
                    "operacao"
                )
            )

    for tanque in tanques:
        label = get_tanque_label(tanque)
        for field_name in [
            "avanco_limpeza",
            "avanco_limpeza_fina",
            "limpeza_mecanizada_diaria",
            "limpeza_fina_diaria",
            "percentual_limpeza_diario",
            "percentual_limpeza_fina_diario",
            "percentual_avanco",
            "percentual_ensacamento",
            "percentual_icamento",
            "percentual_cambagem",
        ]:
            avanco = to_number(get_field(tanque, field_name))
            if avanco is not None and (avanco < 0 or avanco > 100):
                alertas.append(
                    criar_alerta(
                        rdo,
                        "AVANCO_INVALIDO",
                        f"O campo {field_name} do tanque {label} esta fora do intervalo permitido de 0% a 100%.",
                        "alta",
                        "operacao"
                    )
                )

    qtd_equipe_num = to_number(get_field(rdo, "quantidade_equipe", "qtd_equipe", default=get_equipe_count(rdo)))
    operadores_por_tanque = [
        to_number(get_field(tanque, "operadores_simultaneos"))
        for tanque in tanques
    ]
    operadores_por_tanque = [valor for valor in operadores_por_tanque if valor is not None]

    if not operadores_por_tanque:
        operadores = to_number(get_field(rdo, "operadores_simultaneos"))
        operadores_por_tanque = [operadores] if operadores is not None else []

    for operadores in operadores_por_tanque:
        if qtd_equipe_num is not None and operadores > qtd_equipe_num:
            alertas.append(
                criar_alerta(
                    rdo,
                    "OPERADORES_MAIOR_EQUIPE",
                    "A quantidade de operadores simultaneos e maior que a quantidade de membros informados na equipe.",
                    "alta",
                    "operacao"
                )
            )
            break

    return alertas


def validar_observacoes(rdo):
    alertas = []

    observacoes = get_field(rdo, "observacoes_rdo_pt", "observacoes", "observacoes_pt", default="")
    planejamento = get_field(rdo, "planejamento_pt", "planejamento", default="")
    status = lower(get_field(rdo, "status", default=""))

    texto_contexto = " ".join([
        text(observacoes),
        text(planejamento),
    ])

    if "concl" in status and contem_alguma_palavra(texto_contexto, PALAVRAS_PENDENCIA):
        alertas.append(
            criar_alerta(
                rdo,
                "OBSERVACAO_INCOERENTE",
                "O RDO esta como concluido, mas as observacoes indicam possivel pendencia, falta de acesso, liberacao ou continuidade da atividade.",
                "media",
                "coordenacao"
            )
        )

    return alertas


def validar_fotos(rdo):
    alertas = []

    status = lower(get_field(rdo, "status", default=""))
    quantidade_fotos = get_fotos_count(rdo)
    quantidade_fotos_informada = to_number(get_field(rdo, "quantidade_fotos", "qtd_fotos", default=0))
    if quantidade_fotos_informada is not None:
        quantidade_fotos = max(quantidade_fotos, int(quantidade_fotos_informada))

    tanques = get_tanques(rdo)
    houve_avanco_tanque = any([
        (
            to_number(get_field(tanque, "ensacamento_dia")) and to_number(get_field(tanque, "ensacamento_dia")) > 0
        ) or (
            to_number(get_field(tanque, "cambagem_dia")) and to_number(get_field(tanque, "cambagem_dia")) > 0
        ) or (
            to_number(get_field(tanque, "icamento_dia")) and to_number(get_field(tanque, "icamento_dia")) > 0
        ) or (
            to_number(get_field(tanque, "limpeza_mecanizada_diaria")) and to_number(get_field(tanque, "limpeza_mecanizada_diaria")) > 0
        ) or (
            to_number(get_field(tanque, "limpeza_fina_diaria")) and to_number(get_field(tanque, "limpeza_fina_diaria")) > 0
        )
        for tanque in tanques
    ])
    houve_avanco_rdo = any([
        to_number(get_field(rdo, "ensacamento_diario", "ensacamento")) and to_number(get_field(rdo, "ensacamento_diario", "ensacamento")) > 0,
        to_number(get_field(rdo, "cambagem_diario", "cambagem")) and to_number(get_field(rdo, "cambagem_diario", "cambagem")) > 0,
        to_number(get_field(rdo, "icamento_diario", "icamento")) and to_number(get_field(rdo, "icamento_diario", "icamento")) > 0,
        to_number(get_field(rdo, "limpeza_mecanizada_diaria")) and to_number(get_field(rdo, "limpeza_mecanizada_diaria")) > 0,
        to_number(get_field(rdo, "limpeza_fina_diaria")) and to_number(get_field(rdo, "limpeza_fina_diaria")) > 0,
        to_number(get_field(rdo, "percentual_avanco")) and to_number(get_field(rdo, "percentual_avanco")) > 0,
    ])
    houve_avanco = houve_avanco_tanque or houve_avanco_rdo

    if "concl" in status and quantidade_fotos == 0 and houve_avanco:
        alertas.append(
            criar_alerta(
                rdo,
                "FOTO_AUSENTE",
                "O RDO possui avanco operacional informado, mas nenhuma foto foi anexada como evidencia.",
                "media",
                "operacao"
            )
        )

    return alertas


def validar_atividades(rdo):
    alertas = []
    atividades = get_atividades(rdo)
    intervalos = []

    for atividade in atividades:
        inicio = get_field(atividade, "inicio")
        fim = get_field(atividade, "fim")
        if bool(inicio) != bool(fim):
            alertas.append(
                criar_alerta(
                    rdo,
                    "ATIVIDADE_SEM_HORARIO",
                    "Existe atividade com horario de inicio ou fim incompleto.",
                    "media",
                    "operacao"
                )
            )

        if inicio and fim:
            intervalos.append((inicio, fim))

    intervalos.sort(key=lambda item: item[0])
    for index in range(1, len(intervalos)):
        inicio_atual, _ = intervalos[index]
        _, fim_anterior = intervalos[index - 1]
        if inicio_atual < fim_anterior:
            alertas.append(
                criar_alerta(
                    rdo,
                    "ATIVIDADE_SOBREPOSTA",
                    "Existem atividades com horarios sobrepostos.",
                    "media",
                    "operacao"
                )
            )
            break

    return alertas


def valor_vazio(valor):
    """
    Verifica se um valor é considerado vazio ou não informado.
    """
    if valor is None:
        return True

    texto = str(valor).strip().lower()

    return texto in [
        "",
        "-",
        "none",
        "null",
        "não informado",
        "nao informado",
        "não informada",
        "nao informada",
    ]


def validar_tanque_incompleto_rdo(rdo):
    """
    Valida tanques preenchidos no RDO que estão com informações obrigatórias incompletas.
    Esse alerta é de RDO, pois quem preenche é o supervisor.
    """
    alertas = []

    # Tenta obter tanques do RDO - pode ser rdo.tanques ou rdo.rdotanque_set
    tanques = []
    try:
        # Primeira tentativa: relação reversa
        tanques = list(rdo.tanques.all())
    except Exception:
        pass
    
    try:
        # Segunda tentativa: método get_tanques
        tanques_alt = get_tanques(rdo)
        if tanques_alt:
            tanques = tanques_alt
    except Exception:
        pass

    # Se não encontrou tanques relacionados, verifica se o próprio RDO tem dados de tanque
    if not tanques:
        # RDO pode ter dados de tanque diretamente
        nome_tanque = get_field(rdo, "nome_tanque")
        if nome_tanque:
            tanques = [rdo]  # Trata o RDO como o próprio tanque

    for tanque in tanques:
        # Extrai nome do tanque com fallbacks
        nome_tanque = (
            get_field(tanque, "nome_tanque")
            or get_field(tanque, "tanque_codigo")
            or get_field(tanque, "tanque")
            or get_field(tanque, "identificacao")
            or "Tanque não informado"
        )

        # Extrai tipo do tanque
        tipo_tanque = get_field(tanque, "tipo_tanque")

        # Extrai número de compartimentos com múltiplas variações de nome
        numero_compartimentos = (
            get_field(tanque, "numero_compartimentos")
            or get_field(tanque, "n_compartimentos")
            or get_field(tanque, "qtd_compartimentos")
            or get_field(tanque, "num_compartimentos")
        )

        # Extrai volume do tanque com múltiplas variações
        volume_tanque = (
            get_field(tanque, "volume_tanque_exec")
            or get_field(tanque, "volume_tanque")
            or get_field(tanque, "volume")
        )

        campos_faltando = []

        if valor_vazio(tipo_tanque):
            campos_faltando.append("tipo de tanque")

        if valor_vazio(numero_compartimentos):
            campos_faltando.append("nº de compartimentos")

        if valor_vazio(volume_tanque):
            campos_faltando.append("volume do tanque")

        # Só cria alerta se houver campos faltando
        if campos_faltando:
            # Sanitiza nome do tanque para usar como referência
            nome_ref = str(nome_tanque or "").replace(" ", "_").replace("/", "_")[:50]
            
            alertas.append(
                criar_alerta(
                    rdo,
                    "RDO_TANQUE_INCOMPLETO",
                    (
                        f"O tanque {nome_tanque} está com dados incompletos no RDO. "
                        f"Campos faltando: {', '.join(campos_faltando)}. "
                        f"Essas informações são necessárias para cálculos de avanço, "
                        f"análise por compartimento e validações operacionais."
                    ),
                    "alta",
                    "rdo",
                    f"tanque_incompleto_{nome_ref}"
                )
            )

    return alertas


def validar_rdo(rdo):
    """
    Função principal da validação inteligente.
    """
    alertas = []

    alertas += validar_campos_basicos(rdo)
    alertas += validar_rdo_duplicado(rdo)
    alertas += validar_sequencia_datas(rdo)
    alertas += validar_pt(rdo)
    alertas += validar_espaco_confinado(rdo)
    alertas += validar_atividades(rdo)
    alertas += validar_dados_operacionais(rdo)
    alertas += validar_observacoes(rdo)
    alertas += validar_fotos(rdo)
    alertas += validar_tanque_incompleto_rdo(rdo)

    # Estatística simples: detectar anomalias nos RDOs com base no histórico da mesma OS
    resultado_anomalia = detectar_anomalia_rdo(rdo)
    nivel = resultado_anomalia.get("nivel")
    score = resultado_anomalia.get("score", 0.0)
    flags = resultado_anomalia.get("flags", {})
    baseline = resultado_anomalia.get("baseline_snapshot", {})

    if nivel == "alerta":
        mensagem = montar_mensagem_anomalia(rdo, resultado_anomalia)
        alertas.append(
            criar_alerta(
                rdo=rdo,
                tipo="RDO_OUTLIER",
                mensagem=mensagem,
                prioridade="alta" if score >= 0.85 else "media",
                equipe="operacao",
                referencia="anomalia_estatistica",
                anomaly_score=score,
                anomaly_flags=flags,
                baseline_snapshot=baseline,
            )
        )
    elif nivel == "revisao":
        mensagem = montar_mensagem_anomalia(rdo, resultado_anomalia)
        alertas.append(
            criar_alerta(
                rdo=rdo,
                tipo="RDO_REVISAR_ANOMALIA",
                mensagem=mensagem,
                prioridade="baixa",
                equipe="operacao",
                referencia="revisao_estatistica",
                anomaly_score=score,
                anomaly_flags=flags,
                baseline_snapshot=baseline,
            )
        )

    return alertas
