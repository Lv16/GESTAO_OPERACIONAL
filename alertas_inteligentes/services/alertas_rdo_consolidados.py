from collections import Counter, defaultdict
from dataclasses import dataclass

from alertas_inteligentes.models import AlertaInteligente
from alertas_inteligentes.services.lancamento_atrasado_rdo import (
    listar_rdos_lancados_fora_do_dia,
)
from alertas_inteligentes.services.rdos_preenchimento_ruim import (
    listar_rdos_preenchimento_ruim,
)
from alertas_inteligentes.services.rdos_sem_foto import listar_rdos_sem_foto
from alertas_inteligentes.services.rdos_tanque_incompleto import (
    listar_achados_dinamicos_tanque_incompleto,
)


TIPO_LABELS = dict(AlertaInteligente.TIPOS)
TIPO_LABELS.update(
    {
        "RDO_PREENCHIMENTO_RUIM": "RDO com preenchimento critico ou incompleto",
        "RDO_LANCADO_FORA_DO_DIA": "RDO lancado fora do dia da operacao",
    }
)

PRIORIDADE_LABELS = dict(AlertaInteligente.PRIORIDADES)
STATUS_LABELS = dict(AlertaInteligente.STATUS)
EQUIPE_LABELS = dict(AlertaInteligente.EQUIPES)

PRIORIDADE_ORDEM = {
    "critica": 0,
    "alta": 1,
    "media": 2,
    "baixa": 3,
}

TIPO_ORDEM_EXIBICAO = [
    "PT_SEM_NUMERO",
    "PT_SEM_TURNO",
    "PT_INCOERENTE",
    "RDO_DATA_PULADA",
    "RDO_DUPLICADO",
    "ATIVIDADE_SOBREPOSTA",
    "ATIVIDADE_SEM_HORARIO",
    "ESPACO_CONFINADO_INCOERENTE",
    "ESPACO_CONFINADO_SEM_HORARIO",
    "RDO_TANQUE_INCOMPLETO",
    "AVANCO_INVALIDO",
    "OPERADORES_MAIOR_EQUIPE",
    "VALOR_DIARIO_MAIOR_PREVISAO",
    "RDO_PREENCHIMENTO_RUIM",
    "RDO_LANCADO_FORA_DO_DIA",
    "FOTO_AUSENTE",
    "OBSERVACAO_INCOERENTE",
    "RDO_OUTLIER",
    "RDO_REVISAR_ANOMALIA",
    "RDO_SEM_TURNO",
]


@dataclass
class AlertaRdoSintetico:
    rdo: object
    tipo: str
    mensagem: str
    prioridade: str = "media"
    equipe_responsavel: str = "operacao"
    status: str = "pendente"
    explicacao_curta: str = ""
    acao_recomendada: str = ""
    origem: str = "varredura_dinamica"

    @property
    def id(self):
        return None

    @property
    def rdo_id(self):
        return getattr(self.rdo, "id", None)

    @property
    def identificacao_operacional(self):
        numero_rdo = getattr(self.rdo, "numero_rdo", None) or getattr(self.rdo, "rdo", None) or getattr(self.rdo, "id", "")
        os_obj = getattr(self.rdo, "ordem_servico", None) or getattr(self.rdo, "os", None)
        numero_os = None
        if os_obj:
            numero_os = (
                getattr(os_obj, "numero_os", None)
                or getattr(os_obj, "numero", None)
                or getattr(os_obj, "codigo", None)
                or getattr(os_obj, "id", None)
            )
        if numero_os:
            return f"OS {numero_os} | RDO {numero_rdo}"
        return f"RDO {numero_rdo}"

    def get_tipo_display(self):
        return TIPO_LABELS.get(self.tipo, self.tipo.replace("_", " ").title())

    def get_prioridade_display(self):
        return PRIORIDADE_LABELS.get(self.prioridade, self.prioridade.title())

    def get_status_display(self):
        return STATUS_LABELS.get(self.status, self.status.title())

    def get_equipe_responsavel_display(self):
        return EQUIPE_LABELS.get(self.equipe_responsavel, self.equipe_responsavel.title())


def criar_alerta_sem_foto(item):
    return AlertaRdoSintetico(
        rdo=item["rdo"],
        tipo="FOTO_AUSENTE",
        prioridade=item["prioridade"],
        mensagem="Nao identifiquei foto ou anexo vinculado a este RDO na varredura atual.",
        explicacao_curta="Este RDO apareceu sem foto ou anexo associado.",
        acao_recomendada="Abra o RDO, confirme se a evidencia foi anexada e inclua as fotos ou anexos faltantes.",
    )


def criar_alerta_preenchimento_ruim(item):
    avaliacao = item["avaliacao"]
    nivel = avaliacao.get("nivel") or "incompleto"
    prioridade = "alta" if nivel == "critico" else "media"
    problemas = avaliacao.get("problemas") or []
    detalhe = "; ".join(problemas[:4]) or "Foram identificados sinais de preenchimento critico ou incompleto."
    explicacao = (
        "Este RDO tem falhas de preenchimento com impacto operacional direto."
        if nivel == "critico"
        else "Este RDO tem campos importantes incompletos para a execucao registrada."
    )
    return AlertaRdoSintetico(
        rdo=item["rdo"],
        tipo="RDO_PREENCHIMENTO_RUIM",
        prioridade=prioridade,
        mensagem=detalhe,
        explicacao_curta=explicacao,
        acao_recomendada="Revise atividade, observacoes, planejamento, fotos, PT, espaco confinado e dados do tanque para completar o lancamento.",
    )


def criar_alerta_lancado_fora_do_dia(item):
    prioridade = {
        "alto": "alta",
        "medio": "media",
        "baixo": "baixa",
    }.get(item.get("nivel"), "media")
    data_operacional = item["data_operacional"].strftime("%d/%m/%Y")
    data_lancamento = item["data_lancamento"].strftime("%d/%m/%Y")
    dias_atraso = item["dias_atraso"]
    return AlertaRdoSintetico(
        rdo=item["rdo"],
        tipo="RDO_LANCADO_FORA_DO_DIA",
        prioridade=prioridade,
        mensagem=(
            f"Este RDO foi registrado no sistema em {data_lancamento}, mas a data operacional informada e {data_operacional}. "
            f"O lancamento ocorreu {dias_atraso} dia(s) depois da operacao."
        ),
        explicacao_curta=(
            "Este RDO foi feito depois do dia da operacao. Isso pode indicar que o supervisor deixou o RDO anterior para ser lancado depois."
        ),
        acao_recomendada=(
            "Confirme se o RDO foi lancado retroativamente e alinhe o preenchimento diario para evitar lacunas entre a operacao e o registro."
        ),
    )


def criar_alerta_tanque_incompleto(item):
    return AlertaRdoSintetico(
        rdo=item["rdo"],
        tipo="RDO_TANQUE_INCOMPLETO",
        prioridade="alta",
        equipe_responsavel="rdo",
        mensagem=item["mensagem"],
        explicacao_curta="Este RDO tem tanque com dados obrigatorios incompletos.",
        acao_recomendada=(
            "Revise o cadastro do tanque no RDO e preencha tipo de tanque, numero de compartimentos e volume para manter os calculos operacionais consistentes."
        ),
    )


def _sort_alerta(alerta):
    prioridade = getattr(alerta, "prioridade", "media")
    persistido = 0 if getattr(alerta, "id", None) else 1
    rdo_id = getattr(alerta, "rdo_id", 0) or 0
    return (PRIORIDADE_ORDEM.get(prioridade, 9), persistido, -rdo_id)


def _ordem_tipo(tipo):
    try:
        return TIPO_ORDEM_EXIBICAO.index(tipo)
    except ValueError:
        return len(TIPO_ORDEM_EXIBICAO)


def _selecionar_alertas_sortidos(alertas, limite_exibicao):
    grupos = defaultdict(list)
    for alerta in alertas:
        grupos[getattr(alerta, "tipo", "OUTRO")].append(alerta)

    for tipo in grupos:
        grupos[tipo].sort(key=_sort_alerta)

    tipos_ordenados = sorted(grupos.keys(), key=lambda tipo: (_ordem_tipo(tipo), tipo))
    selecionados = []

    while len(selecionados) < limite_exibicao:
        adicionou = False
        for tipo in tipos_ordenados:
            if not grupos[tipo]:
                continue
            selecionados.append(grupos[tipo].pop(0))
            adicionou = True
            if len(selecionados) >= limite_exibicao:
                break
        if not adicionou:
            break

    return selecionados


def listar_alertas_rdo_consolidados(limit_exibicao=28, limit_scan=None):
    persistidos = list(
        AlertaInteligente.objects
        .filter(status="pendente")
        .select_related("rdo", "rdo__ordem_servico")
        .order_by("-criado_em")
    )

    vistos = {(alerta.rdo_id, alerta.tipo) for alerta in persistidos}
    contagem = Counter(alerta.tipo for alerta in persistidos)
    sinteticos = []

    for item in listar_rdos_sem_foto(limite=limit_scan):
        chave = (item["rdo"].id, "FOTO_AUSENTE")
        if chave in vistos:
            continue
        sinteticos.append(criar_alerta_sem_foto(item))
        vistos.add(chave)
        contagem["FOTO_AUSENTE"] += 1

    for item in listar_rdos_preenchimento_ruim(limite=limit_scan):
        chave = (item["rdo"].id, "RDO_PREENCHIMENTO_RUIM")
        if chave in vistos:
            continue
        sinteticos.append(criar_alerta_preenchimento_ruim(item))
        vistos.add(chave)
        contagem["RDO_PREENCHIMENTO_RUIM"] += 1

    for item in listar_achados_dinamicos_tanque_incompleto(limite=limit_scan):
        chave = (item["rdo"].id, "RDO_TANQUE_INCOMPLETO")
        if chave in vistos:
            continue
        sinteticos.append(criar_alerta_tanque_incompleto(item))
        vistos.add(chave)
        contagem["RDO_TANQUE_INCOMPLETO"] += 1

    for item in listar_rdos_lancados_fora_do_dia(limite=limit_scan):
        chave = (item["rdo"].id, "RDO_LANCADO_FORA_DO_DIA")
        if chave in vistos:
            continue
        sinteticos.append(criar_alerta_lancado_fora_do_dia(item))
        vistos.add(chave)
        contagem["RDO_LANCADO_FORA_DO_DIA"] += 1

    alertas = persistidos + sinteticos
    alertas.sort(key=_sort_alerta)

    return {
        "alertas": _selecionar_alertas_sortidos(alertas, limit_exibicao),
        "total": len(alertas),
        "persistidos": len(persistidos),
        "sinteticos": len(sinteticos),
        "contagem_por_tipo": contagem,
    }
