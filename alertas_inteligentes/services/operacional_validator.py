import re

from django.utils import timezone

from alertas_inteligentes.models import AlertaOperacionalInteligente
from alertas_inteligentes.services.field_utils import get_field_safe, has_field_safe
from GO.models import RDO, OrdemServico


def get_field(obj, *names, default=None):
    return get_field_safe(obj, *names, default=default)


def normalizar_texto(valor):
    return str(valor or "").strip().lower()


def eh_status_em_andamento(valor):
    return normalizar_texto(valor) in [
        "em andamento",
        "andamento",
        "em_andamento",
    ]


def eh_status_finalizado(valor):
    return normalizar_texto(valor) in [
        "finalizado",
        "finalizada",
        "concluido",
        "concluído",
        "realizada",
    ]


def eh_status_programado(valor):
    return normalizar_texto(valor) in [
        "programado",
        "programada",
    ]


def supervisor_vazio(valor):
    texto = normalizar_texto(valor)

    return texto in [
        "",
        "-",
        "a definir",
        "indefinido",
        "sem supervisor",
        "não informado",
        "nao informado",
    ]


def algum_campo_existe(obj, *names):
    return has_field_safe(obj, *names)


def obter_periodo_linha(os_obj):
    inicio = get_field(
        os_obj,
        "data_inicio_frente",
        "data_inicio_movimentacao",
        "data_inicio_da_movimentacao",
        "data_inicio",
        default=None,
    )
    fim = get_field(
        os_obj,
        "data_fim_frente",
        "data_fim_movimentacao",
        "data_fim_da_movimentacao",
        "data_fim",
        default=None,
    )
    return inicio, fim


def intervalos_se_sobrepoem(inicio_a, fim_a, inicio_b, fim_b):
    hoje = timezone.localdate()

    if not inicio_a:
        inicio_a = hoje

    if not inicio_b:
        inicio_b = hoje

    if not fim_a:
        fim_a = hoje

    if not fim_b:
        fim_b = hoje

    return inicio_a <= fim_b and inicio_b <= fim_a


def identificar_os(os_obj):
    numero_os = (
        get_field(os_obj, "numero_os", "os", "numero", "codigo", default=None)
        or os_obj.id
    )

    unidade = get_field(os_obj, "unidade", default=None)
    tanque = get_field(os_obj, "tanque", default=None)
    supervisor = get_field(os_obj, "supervisor", "supervisor_responsavel", default=None)

    sequencia = get_field(
        os_obj,
        "sequencia_movimentacao",
        "sequencia_da_movimentacao",
        "seq_movimentacao",
        default=None
    )

    data_inicio_mov = get_field(
        os_obj,
        "data_inicio_movimentacao",
        "data_inicio_da_movimentacao",
        default=None
    )

    partes = [f"OS {numero_os}"]

    if sequencia:
        partes.append(f"Mov. {sequencia}")

    if os_obj.id:
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

def slug_operacional(valor):
    texto = normalizar_texto(valor)
    texto = re.sub(r"[^a-z0-9]+", "_", texto).strip("_")
    return texto or "na"


def build_operational_reference(prefixo, os_obj, extra=None):
    partes = [prefixo]

    if extra:
        partes.append(slug_operacional(extra))

    partes.append(f"linha_{getattr(os_obj, 'id', 'sem_id')}")
    return "_".join(partes)


def _resolver_alertas_operacionais_duplicados(alerta_principal):
    AlertaOperacionalInteligente.objects.filter(
        ordem_servico=alerta_principal.ordem_servico,
        tipo=alerta_principal.tipo,
        referencia=alerta_principal.referencia,
        status="pendente",
    ).exclude(pk=alerta_principal.pk).update(
        status="resolvido",
        resolvido_em=timezone.now(),
        justificativa="Resolvido automaticamente durante consolidacao de alerta operacional duplicado.",
    )


def criar_alerta_operacional(
    os_obj,
    tipo,
    mensagem,
    prioridade="media",
    referencia=None,
):
    identificacao = identificar_os(os_obj)
    mensagem_final = f"{identificacao} - {mensagem}"

    alertas_existentes = list(
        AlertaOperacionalInteligente.objects.filter(
            ordem_servico=os_obj,
            tipo=tipo,
            referencia=referencia,
        ).order_by("-criado_em", "-id")
    )

    alerta = next(
        (item for item in alertas_existentes if item.status == "pendente"),
        alertas_existentes[0] if alertas_existentes else None,
    )

    if alerta:
        alerta.mensagem = mensagem_final
        alerta.prioridade = prioridade
        alerta.status = "pendente"
        alerta.justificativa = None
        alerta.resolvido_em = None
        alerta.resolvido_por = None
        alerta.ignorado_por = None
        alerta.save(
            update_fields=[
                "mensagem",
                "prioridade",
                "status",
                "justificativa",
                "resolvido_em",
                "resolvido_por",
                "ignorado_por",
            ]
        )
        _resolver_alertas_operacionais_duplicados(alerta)
        return alerta

    alerta = AlertaOperacionalInteligente.objects.create(
        ordem_servico=os_obj,
        tipo=tipo,
        referencia=referencia,
        mensagem=mensagem_final,
        prioridade=prioridade,
    )
    _resolver_alertas_operacionais_duplicados(alerta)
    return alerta


def resolver_alertas_operacionais_obsoletos(
    os_obj,
    alertas_ativos,
    justificativa="Resolvido automaticamente apos nova analise operacional.",
):
    chaves_ativas = {
        (alerta.tipo, alerta.referencia or "")
        for alerta in alertas_ativos
    }

    pendentes = AlertaOperacionalInteligente.objects.filter(
        ordem_servico=os_obj,
        status="pendente",
    )

    ids_para_resolver = [
        alerta.id
        for alerta in pendentes
        if (alerta.tipo, alerta.referencia or "") not in chaves_ativas
    ]

    if ids_para_resolver:
        AlertaOperacionalInteligente.objects.filter(
            id__in=ids_para_resolver
        ).update(
            status="resolvido",
            resolvido_em=timezone.now(),
            justificativa=justificativa,
        )


def resolver_alertas_operacionais_por_tipo_nao_mapeados(
    tipo,
    chaves_ativas,
    justificativa="Resolvido automaticamente apos nova analise operacional.",
):
    pendentes = AlertaOperacionalInteligente.objects.filter(
        tipo=tipo,
        status="pendente",
    )

    ids_para_resolver = [
        alerta.id
        for alerta in pendentes
        if (alerta.ordem_servico_id, alerta.referencia or "") not in chaves_ativas
    ]

    if ids_para_resolver:
        AlertaOperacionalInteligente.objects.filter(
            id__in=ids_para_resolver
        ).update(
            status="resolvido",
            resolvido_em=timezone.now(),
            justificativa=justificativa,
        )
    
def validar_os_sem_rdo_recente(os_obj):
    alertas = []

    status_operacao = get_field(
        os_obj,
        "status_operacao",
        "status_da_operacao",
        "status",
        default=""
    )

    if not eh_status_em_andamento(status_operacao):
        return alertas

    hoje = timezone.localdate()

    ultimo_rdo = (
        RDO.objects
        .filter(ordem_servico=os_obj)
        .order_by("-data", "-id")
        .first()
    )

    if not ultimo_rdo:
        alertas.append(
            criar_alerta_operacional(
                os_obj,
                "OS_SEM_RDO_RECENTE",
                'Esta linha operacional está com status "Em Andamento", mas ainda não possui nenhum RDO lançado. Verifique se a operação continua ativa ou se o status da linha precisa ser atualizado.',
                "alta",
                referencia=build_operational_reference("os_sem_rdo", os_obj)
            )
        )
        return alertas

    data_ultimo_rdo = get_field(ultimo_rdo, "data", "data_rdo", "data_operacao")

    if not data_ultimo_rdo:
        return alertas

    dias_sem_rdo = (hoje - data_ultimo_rdo).days

    if dias_sem_rdo >= 2:
        mensagem = (
            'Esta linha operacional está com status "Em Andamento", '
            f"mas está há {dias_sem_rdo} dia(s) sem novo RDO lançado. "
            f"Último RDO registrado em {data_ultimo_rdo}. "
            "Verifique se a operação continua ativa ou se o status da linha precisa ser atualizado."
        )

        alertas.append(
            criar_alerta_operacional(
                os_obj,
                "OS_SEM_RDO_RECENTE",
                mensagem,
                "alta" if dias_sem_rdo >= 3 else "media",
                referencia=build_operational_reference("os_sem_rdo_recente", os_obj)
            )
        )

    return alertas


def validar_os_sem_supervisor(os_obj):
    alertas = []

    status_operacao = get_field(
        os_obj,
        "status_operacao",
        "status_da_operacao",
        "status",
        default=""
    )

    if not eh_status_em_andamento(status_operacao):
        return alertas

    supervisor = get_field(
        os_obj,
        "supervisor",
        "supervisor_responsavel",
        default=""
    )

    if supervisor_vazio(supervisor):
        alertas.append(
            criar_alerta_operacional(
                os_obj,
                "OS_SEM_SUPERVISOR",
                "Esta linha operacional da OS está em andamento, mas não possui supervisor definido.",
                "alta",
                referencia=build_operational_reference("os_sem_supervisor", os_obj)
            )
        )

    return alertas


def validar_os_finalizada_movimentacao_aberta(os_obj):
    alertas = []

    if not algum_campo_existe(
        os_obj,
        "status_lista_movimentacao",
        "status_movimentacao",
    ):
        return alertas

    status_operacao = get_field(
        os_obj,
        "status_operacao",
        "status_da_operacao",
        "status",
        default=""
    )

    status_movimentacao = get_field(
        os_obj,
        "status_lista_movimentacao",
        "status_movimentacao",
        default=""
    )

    if eh_status_finalizado(status_operacao) and not eh_status_finalizado(status_movimentacao):
        alertas.append(
            criar_alerta_operacional(
                os_obj,
                "OS_FINALIZADA_MOVIMENTACAO_ABERTA",
                "Esta linha operacional da OS está finalizada, mas a lista de movimentação ainda não consta como finalizada.",
                "media",
                referencia=build_operational_reference("os_finalizada_movimentacao_aberta", os_obj)
            )
        )

    return alertas


def validar_os_programada_atrasada(os_obj):
    alertas = []

    status_operacao = get_field(
        os_obj,
        "status_operacao",
        "status_da_operacao",
        "status",
        default=""
    )

    if not eh_status_programado(status_operacao):
        return alertas

    hoje = timezone.localdate()

    data_inicio_movimentacao = get_field(
        os_obj,
        "data_inicio_movimentacao",
        "data_inicio_da_movimentacao",
        default=None
    )

    data_inicio_operacao = get_field(
        os_obj,
        "data_inicio_operacao",
        "data_inicio_da_operacao",
        default=None
    )

    if data_inicio_movimentacao and not data_inicio_operacao:
        dias_atraso = (hoje - data_inicio_movimentacao).days

        if dias_atraso >= 1:
            alertas.append(
                criar_alerta_operacional(
                    os_obj,
                    "OS_PROGRAMADA_ATRASADA",
                    f"Esta linha operacional da OS está programada, a movimentação iniciou em {data_inicio_movimentacao}, mas ainda não há data de início da operação registrada.",
                    "media",
                    referencia=build_operational_reference("os_programada_atrasada", os_obj)
                )
            )

    return alertas

def validar_poucos_rdos_para_dias_operacao(os_obj):
    alertas = []

    status_operacao = get_field(
        os_obj,
        "status_operacao",
        "status_da_operacao",
        "status",
        default=""
    )

    if not eh_status_em_andamento(status_operacao):
        return alertas

    qtd_dias_operacao = get_field(
        os_obj,
        "qtd_dias_operacao",
        "qtd_dias_da_operacao",
        "dias_operacao",
        default=None
    )

    try:
        qtd_dias_operacao = int(qtd_dias_operacao)
    except (TypeError, ValueError):
        return alertas

    qtd_rdos = RDO.objects.filter(ordem_servico=os_obj).count()

    if qtd_dias_operacao >= 3 and qtd_rdos < qtd_dias_operacao - 1:
        alertas.append(
            criar_alerta_operacional(
                os_obj,
                "POUCOS_RDOS_PARA_DIAS_OPERACAO",
                f"Esta linha operacional da OS possui {qtd_dias_operacao} dia(s) de operação, mas apenas {qtd_rdos} RDO(s) lançado(s). Verifique se há RDOs pendentes ou se a contagem de dias está correta.",
                "media",
                referencia=build_operational_reference("poucos_rdos_para_dias_operacao", os_obj)
            )
        )

    return alertas


def validar_supervisores_em_os_simultaneas():
    alertas = []
    chaves_ativas = set()

    linhas_abertas = []

    todas_os = OrdemServico.objects.all()

    for os_obj in todas_os:
        status_operacao = get_field(
            os_obj,
            "status_operacao",
            "status_da_operacao",
            "status",
            default=""
        )

        status_movimentacao = get_field(
            os_obj,
            "status_lista_movimentacao",
            "status_movimentacao",
            default=""
        )

        linha_ainda_aberta = not eh_status_finalizado(status_movimentacao)

        if eh_status_em_andamento(status_operacao) and linha_ainda_aberta:
            supervisor = get_field(
                os_obj,
                "supervisor",
                "supervisor_responsavel",
                default=""
            )

            if not supervisor_vazio(supervisor):
                numero_os = (
                    get_field(os_obj, "numero_os", "os", "numero", "codigo", default=None)
                    or os_obj.id
                )
                inicio_linha, fim_linha = obter_periodo_linha(os_obj)

                linhas_abertas.append({
                    "os_obj": os_obj,
                    "supervisor": str(supervisor).strip(),
                    "numero_os": str(numero_os),
                    "identificacao": identificar_os(os_obj),
                    "inicio": inicio_linha,
                    "fim": fim_linha,
                })

    mapa_supervisores = {}

    for item in linhas_abertas:
        chave = item["supervisor"].lower()
        mapa_supervisores.setdefault(chave, []).append(item)

    for supervisor, itens in mapa_supervisores.items():
        if len(itens) <= 1:
            continue

        itens_sobrepostos = []

        for indice, item in enumerate(itens):
            for outro_item in itens[indice + 1:]:
                if intervalos_se_sobrepoem(
                    item["inicio"],
                    item["fim"],
                    outro_item["inicio"],
                    outro_item["fim"],
                ):
                    if item not in itens_sobrepostos:
                        itens_sobrepostos.append(item)
                    if outro_item not in itens_sobrepostos:
                        itens_sobrepostos.append(outro_item)

        if len(itens_sobrepostos) <= 1:
            continue

        numeros_os_distintos = {item["numero_os"] for item in itens_sobrepostos}
        descricoes_linhas = [item["identificacao"] for item in itens_sobrepostos]

        mesma_os = len(numeros_os_distintos) == 1

        if mesma_os:
            prioridade = "media"
            mensagem_base = (
                f"O supervisor {supervisor.title()} aparece em mais de uma linha operacional aberta da mesma OS. "
                "Isso pode representar uma troca ou continuidade operacional, mas vale verificar se alguma linha antiga deveria estar finalizada."
            )
        else:
            prioridade = "alta"
            mensagem_base = (
                f"O supervisor {supervisor.title()} aparece em linhas operacionais abertas de OS diferentes. "
                "Verifique se o vínculo está correto ou se alguma operação ou movimentação precisa ser finalizada."
            )

        mensagem_linhas = " Linhas identificadas: " + " | ".join(descricoes_linhas)

        for item in itens_sobrepostos:
            referencia = build_operational_reference(
                "supervisor_conflito",
                item["os_obj"],
                extra=supervisor,
            )
            chaves_ativas.add((item["os_obj"].id, referencia))
            alertas.append(
                criar_alerta_operacional(
                    item["os_obj"],
                    "SUPERVISOR_EM_OS_SIMULTANEAS",
                    mensagem_base + mensagem_linhas,
                    prioridade,
                    referencia=referencia
                )
            )

    resolver_alertas_operacionais_por_tipo_nao_mapeados(
        "SUPERVISOR_EM_OS_SIMULTANEAS",
        chaves_ativas,
        justificativa="Resolvido automaticamente apos nova validacao de conflito de supervisor.",
    )

    return alertas

def validar_os_operacional(os_obj):
    alertas = []

    alertas += validar_os_sem_rdo_recente(os_obj)
    alertas += validar_os_sem_supervisor(os_obj)
    alertas += validar_os_finalizada_movimentacao_aberta(os_obj)
    alertas += validar_os_programada_atrasada(os_obj)
    alertas += validar_poucos_rdos_para_dias_operacao(os_obj)
    return alertas
