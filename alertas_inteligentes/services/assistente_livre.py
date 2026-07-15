import re
from datetime import datetime, timedelta

from django.db.models import Q, Count
from django.utils import timezone
from django.conf import settings
import logging
import os
from django.core.exceptions import FieldError
from unidecode import unidecode

from GO.models import Cliente, RDO, RdoTanque, OrdemServico, Unidade
from GO.views_rdo import _tank_identity_key
from alertas_inteligentes.models import (
    AlertaInteligente,
    AlertaOperacionalInteligente,
)
from alertas_inteligentes.services.ollama_client import (
    classificar_intencao_com_ollama,
    melhorar_resposta_com_ollama,
)
from alertas_inteligentes.services.aprendizado_ia import (
    buscar_intencao_aprendida,
    registrar_pergunta,
)
from alertas_inteligentes.services.analise_supervisores_os import (
    analisar_supervisores_por_os,
    buscar_os_por_tanque,
)
from alertas_inteligentes.services.analise_mudancas import gerar_resposta_mudancas_desde_ontem
from alertas_inteligentes.services.operacoes_sem_movimentacao import (
    gerar_resposta_operacoes_sem_movimentacao,
)
from alertas_inteligentes.services.rdos_preenchimento_ruim import (
    gerar_resposta_rdos_preenchimento_ruim,
)
from alertas_inteligentes.services.rdos_sem_foto import (
    gerar_resposta_rdos_sem_foto,
)
from alertas_inteligentes.services.rdos_tanque_incompleto import (
    gerar_resposta_rdos_tanque_incompleto,
)
from alertas_inteligentes.services.resumo_empresa_unidade import (
    gerar_resumo_contexto_operacional,
    gerar_resumo_empresa,
    gerar_resumo_unidade,
)
from alertas_inteligentes.services import extractors
from alertas_inteligentes.services.lancamento_atrasado_rdo import (
    gerar_resposta_lancamento_atrasado,
)
from alertas_inteligentes.services.supervisores_pendencias import (
    gerar_resposta_supervisores_com_pendencias,
)
from alertas_inteligentes.services.alertas_rdo_consolidados import (
    TIPO_LABELS as TIPO_LABELS_RDO_CONSOLIDADOS,
    listar_alertas_rdo_consolidados,
)
from alertas_inteligentes.services import intent_router

logger = logging.getLogger(__name__)


def normalizar(texto):
    return str(texto or "").strip().lower()


def normalizar_busca(texto):
    return unidecode(normalizar(texto))


def extrair_numero_os(texto):
    for padrao in (
        r"^\s*0*(\d+)\s*$",
        r"\bos\s*0*(\d+)\b",
        r"ordem\s*de\s*servi[cç]o\s*0*(\d+)\b",
    ):
        match = re.search(padrao, normalizar(texto))
        if match:
            return match.group(1)
    return None


def extrair_numero_rdo(texto):
    for padrao in (
        r"\brdo\s*0*(\d+)\b",
        r"relat[oó]rio\s*di[aá]rio\s*0*(\d+)\b",
    ):
        match = re.search(padrao, normalizar(texto))
        if match:
            return match.group(1)
    return None


def extrair_numeros_rdo_comparacao(texto):
    numeros = re.findall(r"\brdo\s*0*(\d+)\b", normalizar(texto))
    if len(numeros) >= 2:
        return numeros[0], numeros[1]
    return None, None


def extrair_nome_supervisor(texto):
    return extractors.extrair_supervisor(texto)


def extrair_nome_empresa(texto):
    return extractors.extrair_nome_empresa(texto)


def extrair_nome_unidade(texto):
    return extractors.extrair_nome_unidade(texto)


def extrair_nome_tanque(texto):
    return extractors.extrair_nome_tanque(texto)


def parse_data_br(data_texto):
    try:
        return datetime.strptime(data_texto, "%d/%m/%Y").date()
    except (TypeError, ValueError):
        return None


def extrair_intervalo_datas(texto):
    texto_normalizado = normalizar(texto)

    hoje = timezone.localdate()

    datas = re.findall(r"\b\d{2}/\d{2}/\d{4}\b", texto_normalizado)

    if len(datas) >= 2:
        data_inicio = parse_data_br(datas[0])
        data_fim = parse_data_br(datas[1])

        if data_inicio and data_fim:
            return data_inicio, data_fim

    if len(datas) == 1:
        data_inicio = parse_data_br(datas[0])

        if data_inicio and ("hoje" in texto_normalizado or "até hoje" in texto_normalizado or "ate hoje" in texto_normalizado):
            return data_inicio, hoje

        if data_inicio:
            return data_inicio, data_inicio

    if "hoje" in texto_normalizado:
        return hoje, hoje

    if "ontem" in texto_normalizado:
        ontem = hoje - timedelta(days=1)
        return ontem, ontem

    if "semana passada" in texto_normalizado:
        inicio = hoje - timedelta(days=7)
        return inicio, hoje

    if "últimos 7 dias" in texto_normalizado or "ultimos 7 dias" in texto_normalizado:
        inicio = hoje - timedelta(days=7)
        return inicio, hoje

    if "últimos 30 dias" in texto_normalizado or "ultimos 30 dias" in texto_normalizado:
        inicio = hoje - timedelta(days=30)
        return inicio, hoje

    return None, None


def aplicar_filtro_intervalo(queryset, inicio, fim):
    """Tenta filtrar o queryset de RDOs por um campo de data conhecido.

    Prioridade: `data`, depois `data_rdo`. Se nenhum existir, retorna queryset.none().
    """
    try:
        return queryset.filter(data__range=[inicio, fim])
    except FieldError:
        try:
            return queryset.filter(data_rdo__range=[inicio, fim])
        except FieldError:
            return queryset.none()




def pergunta_menciona_pt(texto):
    texto = normalizar(texto)

    termos = [
        "com pt",
        "abertura de pt",
        "pt aberta",
        "pt informado",
        "pt informada",
        "permissão de trabalho",
        "permissao de trabalho",
    ]

    return any(termo in texto for termo in termos)


def pergunta_menciona_espaco_confinado(texto):
    texto = normalizar(texto)

    termos = [
        "espaço confinado",
        "espaco confinado",
        "acesso ao espaço",
        "acesso ao espaco",
        "entrada em tanque",
        "entrada no tanque",
        "confinado",
    ]

    return any(termo in texto for termo in termos)


def pergunta_menciona_alertas(texto):
    texto = normalizar(texto)

    termos = [
        "alerta",
        "alertas",
        "pendência",
        "pendencias",
        "pendência inteligente",
        "pendencia inteligente",
        "inconsistência",
        "inconsistencia",
    ]

    return any(termo in texto for termo in termos)


def pergunta_menciona_anomalia(texto):
    texto = normalizar(texto)

    termos = [
        "anomalia",
        "anomalias",
        "fora do padrão",
        "fora do padrao",
        "outlier",
        "estatística",
        "estatistica",
        "comportamento estranho",
        "valor estranho",
    ]

    return any(termo in texto for termo in termos)


def pergunta_pede_mudancas_desde_ontem(texto):
    texto = normalizar(texto)

    if "rdo" in texto and "entre" in texto:
        return False

    termos = [
        "o que mudou desde ontem",
        "mudou desde ontem",
        "mudanças desde ontem",
        "mudancas desde ontem",
        "mudança desde ontem",
        "mudanca desde ontem",
        "de ontem para hoje",
        "comparar ontem com hoje",
        "resumo desde ontem",
        "novidades desde ontem",
        "teve alguma mudança",
        "teve alguma mudanca",
        "o que mudou",
        "resumo das mudanças",
    ]

    return any(termo in texto for termo in termos)


def pergunta_pede_operacoes_sem_movimentacao(texto):
    texto = normalizar(texto)

    termos = [
        "operações sem movimentação",
        "operacoes sem movimentacao",
        "operação sem movimentação",
        "operacao sem movimentacao",
        "sem movimentação",
        "sem movimentacao",
        "operações paradas",
        "operacoes paradas",
        "operação parada",
        "operacao parada",
        "sem avanço",
        "sem avanco",
        "sem avanço recente",
        "sem avanco recente",
        "não tiveram avanço",
        "nao tiveram avanco",
        "sem progresso",
        "paradas",
        "parada",
    ]

    return any(termo in texto for termo in termos)


def pergunta_pede_rdos_preenchimento_ruim(texto):
    texto = normalizar(texto)

    termos = [
        "preenchimento ruim",
        "preenchimento fraco",
        "mal preenchido",
        "mal preenchidos",
        "rdos ruins",
        "rdo ruim",
        "rdos incompletos",
        "rdo incompleto",
        "pouca informação",
        "pouca informacao",
        "sem informação suficiente",
        "sem informacao suficiente",
        "qualidade do preenchimento",
        "preenchimento do supervisor",
        "supervisor preencheu mal",
        "supervisor preencheu ruim",
        "rdos com pouca informação",
        "rdos com pouca informacao",
    ]

    return any(termo in texto for termo in termos)


def pergunta_pede_rdos_sem_foto(texto):
    texto = normalizar(texto)

    termos = [
        "rdos sem foto",
        "rdo sem foto",
        "sem foto",
        "sem fotos",
        "sem anexo",
        "sem anexos",
        "sem evidência",
        "sem evidencia",
        "sem evidência fotográfica",
        "sem evidencia fotografica",
        "rdos sem evidência",
        "rdos sem evidencia",
        "rdos sem anexo",
        "rdos sem anexos",
        "rdo sem evidência fotográfica",
        "rdo sem evidencia fotografica",
        "quais rdos não têm foto",
        "quais rdos nao tem foto",
        "quais rdos não possuem foto",
        "quais rdos nao possuem foto",
        "fotos pendentes",
        "anexos pendentes",
    ]

    return any(termo in texto for termo in termos)


def pergunta_pede_lancamento_atrasado(texto):
    texto = normalizar(texto)

    termos = [
        "lançamento atrasado",
        "lancamento atrasado",
        "rdos lançados atrasados",
        "rdos lancados atrasados",
        "rdo lançado atrasado",
        "rdo lancado atrasado",
        "preenchimento retroativo",
        "rdos retroativos",
        "rdo retroativo",
        "lançado depois",
        "lancado depois",
        "lançados depois",
        "lancados depois",
        "atraso no lançamento",
        "atraso no lancamento",
        "data operacional diferente",
        "data da operação diferente",
        "data da operacao diferente",
    ]

    return any(termo in texto for termo in termos)


def pergunta_pede_supervisores_com_pendencias(texto):
    texto = normalizar(texto)

    termos = [
        "supervisores com pendência",
        "supervisores com pendencia",
        "supervisores com pendências",
        "supervisores com pendencias",
        "supervisores com rdos pendentes",
        "supervisor com rdo pendente",
        "supervisores com mais alertas",
        "supervisores com alerta",
        "supervisores precisam revisar",
        "supervisores para revisar",
        "quais supervisores têm mais rdos",
        "quais supervisores tem mais rdos",
        "ranking de supervisores",
        "supervisores com rdo para revisar",
        "rdo pendente por supervisor",
        "pendências por supervisor",
        "pendencias por supervisor",
    ]

    return any(termo in texto for termo in termos)


def pergunta_pede_rdos_tanque_incompleto(texto):
    texto = normalizar(texto)

    termos = [
        "rdo com tanque incompleto",
        "rdos com tanque incompleto",
        "rdo tem tanque incompleto",
        "rdos tem tanque incompleto",
        "rdo têm tanque incompleto",
        "rdos têm tanque incompleto",
        "tanque incompleto no rdo",
        "tanques incompletos no rdo",
        "rdo com tanque sem volume",
        "tanque sem volume",
        "rdo com tanque sem tipo",
        "tanque sem tipo",
        "sem número de compartimentos",
        "sem numero de compartimentos",
        "tanque sem compartimentos",
        "tanque preenchido incorretamente",
        "tanques preenchidos incorretamente",
        "dados do tanque incompletos",
        "configuração do tanque incompleta",
        "configuracao do tanque incompleta",
        "quais rdo tem tanque incompleto",
        "quais rdos tem tanque incompleto",
        "quais rdo têm tanque incompleto",
        "quais rdos têm tanque incompleto",
        "rdo sem volume",
        "rdo sem tipo",
        "tanque sem dados",
        "tanques sem dados",
    ]

    return any(termo in texto for termo in termos)


def pergunta_pede_resumo_empresa(texto):
    texto = normalizar(texto)

    termos = [
        "resumo por cliente",
        "resumo do cliente",
        "resumo da cliente",
        "resuma o cliente",
        "resuma a cliente",
        "resumo por empresa",
        "resumo da empresa",
        "resumo do cliente",
        "como estão as operações da empresa",
        "como estao as operacoes da empresa",
        "como estão as operações do cliente",
        "como estao as operacoes do cliente",
        "operações da empresa",
        "operacoes da empresa",
        "operações do cliente",
        "operacoes do cliente",
    ]

    # Termos adicionais para capturar variações diretas
    termos_extra = [
        "resuma as operações",
        "resuma as operacoes",
        "como estão as operações",
        "como estao as operacoes",
        "resuma as operações da",
        "resuma as operacoes da",
        "resuma as operações do",
        "resuma as operacoes do",
    ]

    termos.extend(termos_extra)

    return any(termo in texto for termo in termos)


def pergunta_pede_resumo_unidade(texto):
    texto = normalizar(texto)

    termos = [
        "resumo por unidade",
        "resumo da unidade",
        "resumo do ativo",
        "resuma a unidade",
        "resuma o ativo",
        "como estão as operações da unidade",
        "como estao as operacoes da unidade",
        "como estão as operações do ativo",
        "como estao as operacoes do ativo",
        "operações da unidade",
        "operacoes da unidade",
        "operações do ativo",
        "operacoes do ativo",
    ]

    # Termos adicionais para capturar variações diretas
    termos_extra = [
        "resuma as operações",
        "resuma as operacoes",
        "como estão as operações",
        "como estao as operacoes",
        "como estão as operações da",
        "como estao as operacoes da",
    ]

    termos.extend(termos_extra)

    return any(termo in texto for termo in termos)


def extrair_unidade(texto):
    return extractors.extrair_unidade(texto)


def extrair_empresa(texto):
    return extractors.extrair_empresa(texto)


def extrair_filtros_periodo(pergunta):
    texto = normalizar(pergunta)

    return {
        "numero_os": extrair_numero_os(texto),
        "numero_rdo": extrair_numero_rdo(texto),
        "supervisor": extrair_nome_supervisor(texto),
        "unidade": extrair_unidade(texto),
        "empresa": extrair_empresa(texto),
        "com_pt": pergunta_menciona_pt(texto),
        "com_espaco_confinado": pergunta_menciona_espaco_confinado(texto),
        "com_alertas": pergunta_menciona_alertas(texto),
        "com_anomalia": pergunta_menciona_anomalia(texto),
    }


def descrever_filtros_periodo(filtros):
    descricoes = []

    if filtros["numero_os"]:
        descricoes.append(f"OS {filtros['numero_os']}")

    if filtros["numero_rdo"]:
        descricoes.append(f"RDO {filtros['numero_rdo']}")

    if filtros["supervisor"]:
        descricoes.append(f"supervisor contendo '{filtros['supervisor']}'")

    if filtros["unidade"]:
        descricoes.append(f"unidade {filtros['unidade']}")

    if filtros.get("empresa"):
        descricoes.append(f"empresa {filtros['empresa']}")

    if filtros["com_pt"]:
        descricoes.append("com abertura de PT")

    if filtros["com_espaco_confinado"]:
        descricoes.append("com acesso ao espaço confinado")

    if filtros["com_alertas"]:
        descricoes.append("com alertas pendentes")

    if filtros["com_anomalia"]:
        descricoes.append("com anomalia estatística")

    if not descricoes:
        return "sem filtros adicionais"

    return ", ".join(descricoes)


def pergunta_pede_rdos_por_periodo(texto):
    texto = normalizar(texto)

    termos_rdo = [
        "rdo",
        "rdos",
        "relatório diário",
        "relatorio diario",
        "relatórios diários",
        "relatorios diarios",
    ]

    termos_periodo = [
        "data",
        "período",
        "periodo",
        "entre",
        "de ",
        "até",
        "ate",
        "hoje",
        "ontem",
        "semana passada",
        "últimos",
        "ultimos",
    ]

    tem_rdo = any(termo in texto for termo in termos_rdo)
    tem_periodo = any(termo in texto for termo in termos_periodo)

    data_inicio, data_fim = extrair_intervalo_datas(texto)

    return tem_rdo and tem_periodo and data_inicio and data_fim


def responder_rdos_por_periodo(pergunta):
    data_inicio, data_fim = extrair_intervalo_datas(pergunta)
    filtros = extrair_filtros_periodo(pergunta)

    if not data_inicio or not data_fim:
        return {
            "introducao": (
                "Entendi que você quer analisar RDOs por período, "
                "mas não consegui identificar corretamente as datas."
            ),
            "alertas": [],
            "alertas_operacionais": [],
            "recomendacao": "Tente perguntar assim: analise os RDOs de 20/05/2026 até hoje.",
            "fontes": ["Pergunta do usuário"],
            "confianca": "baixa",
        }

    if data_inicio > data_fim:
        data_inicio, data_fim = data_fim, data_inicio

    rdos = aplicar_filtro_intervalo(RDO.objects.all(), data_inicio, data_fim)

    # Aplicar filtros seguros
    if filtros.get("numero_os"):
        rdos = rdos.filter(ordem_servico__numero_os=filtros["numero_os"])

    if filtros.get("numero_rdo"):
        try:
            rdos = rdos.filter(rdo=filtros["numero_rdo"])
        except FieldError:
            try:
                rdos = rdos.filter(numero_rdo=filtros["numero_rdo"])
            except FieldError:
                pass

    if filtros.get("supervisor"):
        try:
            rdos = rdos.filter(ordem_servico__supervisor__username__icontains=filtros["supervisor"])
        except FieldError:
            try:
                rdos = rdos.filter(ordem_servico__supervisor__icontains=filtros["supervisor"])
            except FieldError:
                pass

    if filtros.get("unidade"):
        try:
            rdos = rdos.filter(ordem_servico__Unidade__nome__icontains=filtros["unidade"])
        except FieldError:
            try:
                rdos = rdos.filter(ordem_servico__unidade__icontains=filtros["unidade"])
            except FieldError:
                pass

    if filtros.get("empresa"):
        try:
            rdos = rdos.filter(ordem_servico__Cliente__nome__icontains=filtros["empresa"])
        except FieldError:
            try:
                rdos = rdos.filter(ordem_servico__empresa__icontains=filtros["empresa"])
            except FieldError:
                pass

    if filtros.get("com_pt"):
        try:
            rdos = rdos.filter(houve_abertura_pt=True)
        except FieldError:
            pass

    if filtros.get("com_espaco_confinado"):
        try:
            rdos = rdos.filter(houve_acesso_espaco_confinado=True)
        except FieldError:
            pass

    # Filtrar por alertas e anomalias usando a tabela de alertas (não depende do related_name)
    if filtros.get("com_alertas"):
        rdo_ids = AlertaInteligente.objects.filter(status="pendente", rdo__in=rdos).values_list("rdo_id", flat=True)
        rdos = rdos.filter(id__in=rdo_ids).distinct()

    if filtros.get("com_anomalia"):
        rdo_ids = AlertaInteligente.objects.filter(
            status="pendente",
            tipo__in=["RDO_OUTLIER", "RDO_REVISAR_ANOMALIA"],
            rdo__in=rdos,
        ).values_list("rdo_id", flat=True)
        rdos = rdos.filter(id__in=rdo_ids).distinct()

    # Otimizar query final
    try:
        rdos = rdos.select_related("ordem_servico").order_by("data", "id")
    except FieldError:
        rdos = rdos.select_related("ordem_servico").order_by("data_rdo", "id")

    total_rdos = rdos.count()

    if total_rdos == 0:
        descricao_filtros = descrever_filtros_periodo(filtros)
        return {
            "introducao": (
                f"Analisei os RDOs no período de {data_inicio.strftime('%d/%m/%Y')} "
                f"até {data_fim.strftime('%d/%m/%Y')}.\n\n"
                f"Filtros aplicados: {descricao_filtros}.\n\n"
                "Nao encontrei RDOs lancados com esses filtros."
            ),
            "alertas": [],
            "alertas_operacionais": [],
            "recomendacao": "Verifique se os filtros e o período estao corretos.",
            "fontes": ["RDOs"],
            "confianca": "alta",
        }

    alertas = (
        AlertaInteligente.objects
        .filter(
            rdo__in=rdos,
            status="pendente"
        )
        .select_related("rdo")
        .order_by("-prioridade", "-criado_em")
    )

    alertas_resolvidos = AlertaInteligente.objects.filter(
        rdo__in=rdos,
        status="resolvido"
    ).count()

    alertas_ignorados = AlertaInteligente.objects.filter(
        rdo__in=rdos,
        status="ignorado"
    ).count()

    total_os = (
        rdos
        .values("ordem_servico")
        .distinct()
        .count()
    )

    rdos_com_anomalia = alertas.filter(
        tipo__in=["RDO_OUTLIER", "RDO_REVISAR_ANOMALIA"]
    ).count()

    try:
        rdos_com_pt = rdos.filter(houve_abertura_pt=True).count()
    except FieldError:
        rdos_com_pt = 0

    try:
        rdos_espaco_confinado = rdos.filter(houve_acesso_espaco_confinado=True).count()
    except FieldError:
        rdos_espaco_confinado = 0

    descricao_filtros = descrever_filtros_periodo(filtros)

    introducao = (
        f"Analisei os RDOs no período de {data_inicio.strftime('%d/%m/%Y')} "
        f"até {data_fim.strftime('%d/%m/%Y')}.\n\n"
        f"Filtros aplicados: {descricao_filtros}.\n\n"
        f"Encontrei:\n"
        f"- {total_rdos} RDO(s) lancado(s)\n"
        f"- {total_os} OS relacionada(s)\n"
        f"- {alertas.count()} alerta(s) inteligente(s) pendente(s)\n"
        f"- {alertas_resolvidos} alerta(s) resolvido(s)\n"
        f"- {alertas_ignorados} alerta(s) ignorado(s)\n"
        f"- {rdos_com_anomalia} RDO(s) com possivel anomalia estatistica\n"
        f"- {rdos_com_pt} RDO(s) com abertura de PT informada\n"
        f"- {rdos_espaco_confinado} RDO(s) com acesso ao espaco confinado informado"
    )

    # Resumo por OS
    resumo_por_os = (
        rdos
        .values("ordem_servico__numero_os")
        .annotate(total=Count("id"))
        .order_by("-total")[:10]
    )

    if resumo_por_os:
        linhas_os = ["", "Resumo por OS:"]
        for item in resumo_por_os:
            linhas_os.append(f"- OS {item['ordem_servico__numero_os']}: {item['total']} RDO(s)")
        introducao += "\n" + "\n".join(linhas_os)

    # Recomendações inteligentes
    if filtros.get("com_anomalia") and total_rdos > 0:
        recomendacao = (
            "Recomendo revisar os RDOs com anomalia estatistica antes de considerar o periodo validado, "
            "principalmente verificando valores de avanco, ensacamento, cambagem, icamento e tempo de bomba."
        )
    elif filtros.get("com_alertas") and total_rdos > 0:
        recomendacao = (
            "Recomendo priorizar os alertas pendentes encontrados nesse periodo, começando pelos de maior prioridade."
        )
    elif filtros.get("com_pt") and total_rdos > 0:
        recomendacao = (
            "Recomendo conferir se os RDOs com PT possuem numero de PT e turno de abertura preenchidos corretamente."
        )
    elif filtros.get("com_espaco_confinado") and total_rdos > 0:
        recomendacao = (
            "Recomendo validar se os RDOs com espaco confinado possuem horarios de entrada e saida, equipe e medicões preenchidas corretamente."
        )
    elif alertas.exists():
        recomendacao = (
            "Recomendo priorizar os alertas pendentes desse periodo, principalmente os de alta prioridade, "
            "anomalias estatisticas e inconsistencias envolvendo PT ou espaco confinado."
        )
    else:
        recomendacao = (
            "Nao encontrei alertas pendentes relevantes com esses filtros. Ainda assim, vale conferir se os RDOs representam corretamente o avanco operacional informado."
        )

    return {
        "introducao": introducao,
        "alertas": alertas[:20],
        "alertas_operacionais": [],
        "recomendacao": recomendacao,
        "fontes": ["RDOs", "Alertas inteligentes", "Analise estatistica"],
        "confianca": "alta",
    }
def extrair_entidade_por_padrao(texto, padroes):
    for padrao in padroes:
        match = re.search(padrao, str(texto or ""), flags=re.IGNORECASE)
        if not match:
            continue
        valor = match.group(1).strip()
        valor = re.sub(
            r"\b(tem|possui|com|quais|qual|em|na|no|acontecendo|atualmente|hoje|esta|estao)\b.*",
            "",
            valor,
            flags=re.IGNORECASE,
        ).strip()
        if valor:
            return valor
    return None


def extrair_status_operacao(texto):
    texto_busca = normalizar_busca(texto)
    correspondencias = {
        "em andamento": "Em Andamento",
        "andamento": "Em Andamento",
        "programada": "Programada",
        "programadas": "Programada",
        "finalizada": "Finalizada",
        "finalizadas": "Finalizada",
        "paralizada": "Paralizada",
        "paralizadas": "Paralizada",
        "cancelada": "Cancelada",
        "canceladas": "Cancelada",
    }
    for termo, status in correspondencias.items():
        if termo in texto_busca:
            return status
    return None


def resposta_vazia(introducao, recomendacao):
    return {
        "introducao": introducao,
        "alertas": [],
        "alertas_operacionais": [],
        "recomendacao": recomendacao,
    }


ALERTAS_RDO_POR_TERMO = (
    ("RDO_DATA_PULADA", ("data pulada", "datas puladas", "lacuna de data", "pulou data", "sequencia de data")),
    ("RDO_SEM_TURNO", ("rdo sem turno", "sem turno no rdo", "turno ausente no rdo")),
    ("PT_SEM_NUMERO", ("pt sem numero", "permissao sem numero", "numero da pt", "pt sem n")),
    ("PT_SEM_TURNO", ("pt sem turno", "turno da pt", "pt sem turno informado")),
    ("PT_INCOERENTE", ("pt incoerente", "pt inconsistente")),
    ("ATIVIDADE_SOBREPOSTA", ("atividade sobreposta", "atividades sobrepostas", "horarios sobrepostos")),
    ("ATIVIDADE_SEM_HORARIO", ("atividade sem horario", "atividades sem horario")),
    ("ESPACO_CONFINADO_SEM_HORARIO", ("espaco confinado sem horario", "confinado sem horario")),
    ("ESPACO_CONFINADO_INCOERENTE", ("espaco confinado incoerente", "confinado incoerente")),
    ("OPERADORES_MAIOR_EQUIPE", ("operadores maior que equipe", "operadores acima da equipe")),
    ("VALOR_DIARIO_MAIOR_PREVISAO", ("valor diario maior que previsao", "diario maior que previsao")),
    ("AVANCO_INVALIDO", ("avanco invalido", "percentual invalido", "avanco incoerente")),
    ("OBSERVACAO_INCOERENTE", ("observacao incoerente", "observacao inconsistente")),
    ("RDO_OUTLIER", ("rdo outlier", "fora do padrao", "comportamento fora do padrao")),
    ("RDO_REVISAR_ANOMALIA", ("revisao estatistica", "anomalia estatistica", "marcado para revisao")),
    ("RDO_TANQUE_INCOMPLETO", ("tanque incompleto", "dados incompletos no tanque", "rdo tanque incompleto")),
    ("RDO_LANCADO_FORA_DO_DIA", ("lancado fora do dia", "rdo de ontem feito hoje", "feito hoje com data de ontem", "lancado no dia seguinte")),
)


def identificar_tipo_alerta_rdo(texto_busca):
    for tipo, termos in ALERTAS_RDO_POR_TERMO:
        if any(termo in texto_busca for termo in termos):
            return tipo
    return None


def responder_alertas_rdo_por_tipo(tipo, numero_os=None):
    if tipo == "RDO_TANQUE_INCOMPLETO":
        return gerar_resposta_rdos_tanque_incompleto(numero_os=numero_os)
    if tipo == "RDO_LANCADO_FORA_DO_DIA":
        return gerar_resposta_lancamento_atrasado(limite=None, limite_dias=0)

    label = TIPO_LABELS_RDO_CONSOLIDADOS.get(tipo, tipo.replace("_", " ").title())
    escopo = f" na OS {numero_os}" if numero_os else ""
    alertas = (
        AlertaInteligente.objects
        .filter(status="pendente", tipo=tipo)
        .select_related("rdo", "rdo__ordem_servico")
        .order_by("-criado_em")
    )
    if numero_os:
        alertas = alertas.filter(rdo__ordem_servico__numero_os=numero_os)

    total = alertas.count()

    if total == 0:
        pendentes_analise = RDO.objects.filter(status_analise_ia="pendente").count()
        linhas = [
            f"Nao encontrei alertas pendentes de '{label}'{escopo} entre os RDOs ja analisados pela IA.",
        ]
        if pendentes_analise:
            linhas.extend(
                [
                    "",
                    f"Observacao: ainda existem {pendentes_analise} RDO(s) pendentes de analise inteligente. "
                    "Esse tipo de alerta pode aparecer depois que a fila for processada.",
                ]
            )
        return resposta_vazia(
            "\n".join(linhas),
            "Se quiser, eu posso listar os RDOs pendentes de analise ou detalhar outro tipo de alerta de RDO.",
        )

    linhas = [
        f"Encontrei {total} alerta(s) pendente(s) de {label.lower()}{escopo}.",
        "",
        "Separei os principais abaixo para revisao.",
    ]

    return {
        "introducao": "\n".join(linhas),
        "alertas": alertas[:20],
        "alertas_operacionais": [],
        "recomendacao": (
            "Abra os RDOs listados, confirme a inconsistência e trate os casos pendentes diretamente no lancamento."
        ),
    }


def montar_linhas_resumo_alertas_rdo(alertas_info):
    contagem = alertas_info["contagem_por_tipo"]
    linhas = []
    tipos_ordenados = [
        "PT_SEM_NUMERO",
        "PT_SEM_TURNO",
        "PT_INCOERENTE",
        "RDO_DATA_PULADA",
        "RDO_TANQUE_INCOMPLETO",
        "RDO_PREENCHIMENTO_RUIM",
        "RDO_LANCADO_FORA_DO_DIA",
        "RDO_LANCAMENTO_ATRASADO",
        "FOTO_AUSENTE",
    ]

    vistos = set()
    for tipo in tipos_ordenados:
        total = contagem.get(tipo)
        if not total:
            continue
        vistos.add(tipo)
        linhas.append(f"- {total} caso(s) de {TIPO_LABELS_RDO_CONSOLIDADOS.get(tipo, tipo)}")

    outros_tipos = sorted(tipo for tipo in contagem.keys() if tipo not in vistos)
    for tipo in outros_tipos:
        linhas.append(f"- {contagem[tipo]} caso(s) de {TIPO_LABELS_RDO_CONSOLIDADOS.get(tipo, tipo)}")

    return linhas


def montar_resposta_pendencias_inteligentes(limit_operacionais=20, limit_rdo=20):
    alertas_operacionais = (
        AlertaOperacionalInteligente.objects
        .filter(status="pendente")
        .select_related("ordem_servico")
        .order_by("-criado_em")[:limit_operacionais]
    )
    total_operacionais = AlertaOperacionalInteligente.objects.filter(status="pendente").count()
    alertas_rdo_info = listar_alertas_rdo_consolidados(limit_exibicao=limit_rdo, limit_scan=None)
    alertas_rdo = alertas_rdo_info["alertas"]
    total_rdo = alertas_rdo_info["total"]

    if total_operacionais == 0 and total_rdo == 0:
        return resposta_vazia(
            "Nao encontrei pendencias inteligentes abertas no momento.",
            "A IA nao identificou alertas de RDO nem pendencias operacionais agora.",
        )

    if total_operacionais and total_rdo:
        introducao = (
            f"Encontrei {total_operacionais} pendencia(s) operacional(is) e "
            f"{total_rdo} alerta(s) pendente(s) de RDO."
        )
        recomendacao = (
            "Comece pelas pendencias operacionais de maior impacto e depois revise os alertas "
            "especificos dos RDOs."
        )
    elif total_operacionais:
        introducao = (
            f"Encontrei {total_operacionais} pendencia(s) operacional(is) aberta(s) na Home Operacional."
        )
        recomendacao = (
            "Priorize primeiro as pendencias operacionais de maior impacto e, depois, confirme "
            "se os RDOs relacionados estao coerentes."
        )
    else:
        introducao = (
            f"Nao encontrei pendencias operacionais abertas agora, mas existem {total_rdo} "
            f"alerta(s) pendente(s) de RDO."
        )
        recomendacao = (
            "Nao ha pendencias operacionais na Home neste momento. Foque nos alertas "
            "especificos dos RDOs pendentes."
        )

    linhas_resumo_rdo = montar_linhas_resumo_alertas_rdo(alertas_rdo_info)
    if linhas_resumo_rdo:
        introducao = "\n".join([introducao, "", "Resumo dos alertas de RDO:", *linhas_resumo_rdo])

    return {
        "introducao": introducao,
        "alertas": alertas_rdo,
        "alertas_operacionais": alertas_operacionais,
        "recomendacao": recomendacao,
    }


def bloco_texto(titulo, linhas):
    linhas_validas = [str(linha).strip() for linha in linhas if str(linha or "").strip()]
    if not linhas_validas:
        return ""
    return "\n".join([titulo, *linhas_validas])


def montar_texto_estruturado(*blocos):
    blocos_validos = [bloco.strip() for bloco in blocos if str(bloco or "").strip()]
    return "\n\n".join(blocos_validos)


def formatar_usuario(usuario):
    if not usuario:
        return "Nao informado"
    nome_completo = getattr(usuario, "get_full_name", lambda: "")()
    return nome_completo.strip() or str(usuario)


def responder_pergunta_livre(pergunta, contexto=None):
    contexto = contexto or {}
    texto = normalizar(pergunta)
    texto_busca = normalizar_busca(pergunta)
    numero_os = extrair_numero_os(pergunta)
    numero_rdo = extrair_numero_rdo(pergunta)
    rdo_a, rdo_b = extrair_numeros_rdo_comparacao(pergunta)
    supervisor = extrair_nome_supervisor(pergunta)
    empresa = extrair_nome_empresa(pergunta)
    unidade = extrair_nome_unidade(pergunta)
    tanque = extrair_nome_tanque(pergunta)
    status_operacao = extrair_status_operacao(pergunta)
    consulta_sem_rdo_recente = pergunta_indica_sem_rdo_recente(texto_busca)
    metricas_tanque = identificar_metricas_tanque(texto_busca)
    pergunta_sobre_tanque = "tanque" in texto_busca or bool(metricas_tanque)
    tipo_alerta_rdo = identificar_tipo_alerta_rdo(texto_busca)
    intencao_aprendida = buscar_intencao_aprendida(pergunta)

    try:
        intent_info = intent_router.classify_intent(pergunta, contexto)
    except Exception:
        intent_info = {"intent": None, "source": "error", "confidence": 0.0}

    logger.info("intent_router: %s", intent_info)
    intent_name = intent_info.get("intent") if intent_info else None
    if intencao_aprendida and intent_name in {None, "consulta_os", "consulta_rdo", "consulta_supervisor"}:
        intent_name = intencao_aprendida

    if getattr(settings, "INTENT_ROUTER_REGISTRAR_PERGUNTA", False):
        try:
            registrar_pergunta(
                pergunta,
                contexto=contexto or {},
                intencao_detectada=intent_name,
                entendida=bool(intent_name),
            )
        except Exception:
            logger.exception("Falha ao registrar pergunta classificada pelo intent_router")

    log_file = getattr(settings, "INTENT_ROUTER_LOG_FILE", None)
    if log_file:
        try:
            abs_path = os.path.abspath(log_file)
            if not any(getattr(h, "baseFilename", None) == abs_path for h in logger.handlers if hasattr(h, "baseFilename")):
                fh = logging.FileHandler(abs_path)
                fh.setLevel(logging.INFO)
                fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
                logger.addHandler(fh)
        except Exception:
            logger.exception("Falha ao inicializar handler de log do intent_router")

    try:
        unidade_explicita = extractors.extrair_unidade(pergunta) or extractors.extrair_unidade_da_pergunta(pergunta)
    except Exception:
        unidade_explicita = None

    try:
        empresa_explicita = extractors.extrair_empresa_da_pergunta(pergunta)
    except Exception:
        empresa_explicita = None

    unidade_contexto = unidade or unidade_explicita
    empresa_contexto = empresa or empresa_explicita

    if not numero_os and pergunta_sobre_tanque:
        numero_os = contexto.get("numero_os")

    if not tanque and pergunta_sobre_tanque:
        tanque = contexto.get("tanque")

    termos_metricas_supervisor_os = (
        "ensacamento",
        "icamento",
        "i?amento",
        "cambagem",
        "tempo de bomba",
        "bomba",
        "avan?o percentual",
        "avanco percentual",
        "por compartimento",
        "compartimento",
    )
    termos_diretos_supervisor_os = (
        "quais supervisores passaram",
        "quais supervisores atuaram",
        "supervisores que passaram",
        "supervisores que atuaram",
        "quais supervisores da os",
        "supervisores da os",
        "supervisor da os",
        "supervisora da os",
        "rdo por supervisor",
        "rdos por supervisor",
        "por supervisor",
        "por supervisora",
        "periodo de atuacao",
        "periodo de atua??o",
        "resumo final da operacao",
        "resumo final da opera??o",
        "resumo da operacao por supervisor",
        "resumo da opera??o por supervisor",
    )
    pede_supervisores_os = (
        numero_os
        and (
            any(termo in texto_busca for termo in termos_diretos_supervisor_os)
            or (
                (
                    "supervisor" in texto_busca
                    or "supervisora" in texto_busca
                    or "supervisores" in texto_busca
                )
                and (
                    any(termo in texto_busca for termo in termos_metricas_supervisor_os)
                    or bool(tanque)
                    or "da os" in texto_busca
                    or "na os" in texto_busca
                    or "nessa os" in texto_busca
                    or "dessa os" in texto_busca
                )
            )
        )
    )

    # 1. Intencoes especificas com multiplas entidades
    if numero_os and rdo_a and rdo_b and pergunta_indica_comparacao_rdos(texto_busca):
        resposta = responder_comparacao_rdos(numero_os, rdo_a, rdo_b)
        return resposta_registrada(pergunta, contexto, "comparacao_rdos", resposta)

    if numero_os and pergunta_indica_linha_tempo(texto_busca):
        resposta = responder_linha_tempo_os(numero_os)
        return resposta_registrada(pergunta, contexto, "linha_tempo_os", resposta)

    if pede_supervisores_os:
        resposta = analisar_supervisores_por_os(numero_os, tanque)
        return resposta_registrada(
            pergunta,
            contexto,
            "analise_supervisores_os",
            resposta,
            melhorar=False,
        )

    if numero_os and pergunta_sobre_tanque:
        resposta = responder_sobre_tanque_os(
            numero_os=numero_os,
            nome_tanque=tanque,
            metricas=metricas_tanque,
        )
        return resposta_registrada(pergunta, contexto, "consulta_os", resposta, melhorar=False)

    if supervisor and metricas_tanque:
        resposta = responder_producao_supervisor(
            nome_supervisor=supervisor,
            metricas=metricas_tanque,
        )
        return resposta_registrada(pergunta, contexto, "consulta_supervisor", resposta, melhorar=False)

    if numero_os and pergunta_indica_operacao_parada(texto_busca):
        resposta = responder_operacao_parada(numero_os)
        return resposta_registrada(pergunta, contexto, "operacao_parada", resposta)

    if pergunta_indica_resumo_diario(texto_busca):
        resposta = responder_resumo_diario()
        return resposta_registrada(pergunta, contexto, "resumo_diario", resposta)

    if pergunta_indica_priorizacao(texto_busca):
        resposta = responder_prioridades_recomendadas()
        return resposta_registrada(pergunta, contexto, "priorizacao", resposta)

    if pergunta_pede_mudancas_desde_ontem(texto):
        resposta = gerar_resposta_mudancas_desde_ontem()
        return resposta_registrada(pergunta, contexto, "mudancas_desde_ontem", resposta)

    if pergunta_pede_operacoes_sem_movimentacao(texto):
        resposta = gerar_resposta_operacoes_sem_movimentacao()
        return resposta_registrada(pergunta, contexto, "operacoes_sem_movimentacao", resposta)

    # 2. Consultas por tipo de alerta
    if pergunta_pede_rdos_sem_foto(texto):
        resposta = gerar_resposta_rdos_sem_foto()
        return resposta_registrada(pergunta, contexto, "rdos_sem_foto", resposta)

    if pergunta_pede_rdos_tanque_incompleto(texto_busca):
        resposta = gerar_resposta_rdos_tanque_incompleto(numero_os=numero_os)
        return resposta_registrada(pergunta, contexto, "rdos_tanque_incompleto", resposta)

    if pergunta_pede_rdos_preenchimento_ruim(texto):
        resposta = gerar_resposta_rdos_preenchimento_ruim()
        return resposta_registrada(pergunta, contexto, "rdos_preenchimento_ruim", resposta)

    if pergunta_pede_lancamento_atrasado(texto):
        resposta = gerar_resposta_lancamento_atrasado()
        return resposta_registrada(pergunta, contexto, "lancamento_atrasado", resposta)

    if tipo_alerta_rdo:
        resposta = responder_alertas_rdo_por_tipo(tipo_alerta_rdo, numero_os=numero_os)
        return resposta_registrada(pergunta, contexto, f"alerta_rdo_{tipo_alerta_rdo.lower()}", resposta)

    # 3. Consultas por agrupamento
    if unidade_contexto and pergunta_indica_analise_unidade(texto_busca):
        resposta = responder_analise_unidade(unidade_contexto)
        return resposta_registrada(pergunta, contexto, "analise_unidade", resposta)

    if unidade_contexto and (
        pergunta_pede_resumo_unidade(texto)
        or ("operacao" in texto_busca and unidade_contexto)
        or ("resuma" in texto_busca and unidade_contexto)
    ):
        resposta = responder_contexto_operacional(unidade=unidade_contexto)
        return resposta_registrada(pergunta, contexto, "resumo_unidade", resposta)

    if empresa_contexto and pergunta_pede_resumo_empresa(texto):
        resposta = responder_contexto_operacional(empresa=empresa_contexto)
        return resposta_registrada(pergunta, contexto, "resumo_empresa", resposta)

    if pergunta_pede_supervisores_com_pendencias(texto):
        resposta = gerar_resposta_supervisores_com_pendencias()
        return resposta_registrada(pergunta, contexto, "supervisores_com_pendencias", resposta)

    if supervisor and pergunta_indica_analise_supervisor(texto_busca):
        resposta = responder_analise_supervisor(supervisor)
        return resposta_registrada(pergunta, contexto, "analise_supervisor", resposta)

    if supervisor and intent_name not in {"analise_supervisor"}:
        resposta = responder_sobre_supervisor(supervisor)
        return resposta_registrada(pergunta, contexto, "consulta_supervisor", resposta)

    # Coordenador ainda nao tem extrator/roteador dedicado.
    if (
        empresa_contexto or unidade_contexto or status_operacao
    ) and intent_name not in {"analise_unidade", "resumo_unidade", "resumo_empresa"}:
        resposta = responder_linhas_filtradas(
            empresa=empresa_contexto,
            unidade=unidade_contexto,
            status_operacao=status_operacao,
            sem_rdo_recente=consulta_sem_rdo_recente,
        )
        return resposta_registrada(pergunta, contexto, "linhas_filtradas", resposta)

    if consulta_sem_rdo_recente:
        resposta = responder_os_sem_rdo_recente()
        return resposta_registrada(pergunta, contexto, "os_sem_rdo_recente", resposta)

    # 4. Consultas genericas
    if numero_os and numero_rdo and intent_name not in {"comparacao_rdos", "consulta_rdo"}:
        resposta = responder_sobre_rdo(numero_os, numero_rdo)
        return resposta_registrada(pergunta, contexto, "consulta_rdo", resposta)

    if pergunta_pede_rdos_por_periodo(texto):
        resposta = responder_rdos_por_periodo(pergunta)
        return resposta_registrada(pergunta, contexto, "rdos_por_periodo", resposta)

    if numero_os and pergunta_indica_resumo_os(texto_busca):
        resposta = responder_resumo_os(numero_os)
        return resposta_registrada(pergunta, contexto, "resumo_os", resposta)

    if numero_os and intent_name not in {
        "resumo_os",
        "linha_tempo_os",
        "operacao_parada",
        "comparacao_rdos",
        "consulta_rdo",
        "supervisores_por_tanque",
        "analise_supervisores_os",
    }:
        resposta = responder_sobre_os(numero_os)
        return resposta_registrada(pergunta, contexto, "consulta_os", resposta)

    if pergunta_indica_alertas_pendentes(texto_busca):
        resposta = responder_alertas_pendentes()
        return resposta_registrada(pergunta, contexto, "alertas_pendentes", resposta)

    if "supervisor" in texto_busca and any(
        termo in texto_busca for termo in ("conflito", "duas os", "mais de uma", "vinculado")
    ):
        resposta = responder_supervisores_em_conflito()
        return resposta_registrada(pergunta, contexto, "supervisores_conflito", resposta)

    if any(
        termo in texto_busca
        for termo in (
            "pendencia",
            "alerta",
            "problema operacional",
            "problemas operacionais",
            "o que ha de errado",
        )
    ):
        resposta = responder_pendencias_gerais()
        return resposta_registrada(pergunta, contexto, "pendencias_gerais", resposta)

    # 5. Aprendizado / intent router / Ollama / fallback
    if intent_name == "comparacao_rdos" and numero_os and rdo_a and rdo_b:
        resposta = responder_comparacao_rdos(numero_os, rdo_a, rdo_b)
        return resposta_registrada(pergunta, contexto, intent_name, resposta)

    if intent_name == "linha_tempo_os" and numero_os:
        resposta = responder_linha_tempo_os(numero_os)
        return resposta_registrada(pergunta, contexto, intent_name, resposta)

    if intent_name == "resumo_os" and numero_os:
        resposta = responder_resumo_os(numero_os)
        return resposta_registrada(pergunta, contexto, intent_name, resposta)

    if intent_name == "operacao_parada" and numero_os:
        resposta = responder_operacao_parada(numero_os)
        return resposta_registrada(pergunta, contexto, intent_name, resposta)

    if intent_name == "resumo_diario":
        resposta = responder_resumo_diario()
        return resposta_registrada(pergunta, contexto, intent_name, resposta)

    if intent_name == "priorizacao":
        resposta = responder_prioridades_recomendadas()
        return resposta_registrada(pergunta, contexto, intent_name, resposta)

    if intent_name == "mudancas_desde_ontem":
        resposta = gerar_resposta_mudancas_desde_ontem()
        return resposta_registrada(pergunta, contexto, intent_name, resposta)

    if intent_name == "operacoes_sem_movimentacao":
        resposta = gerar_resposta_operacoes_sem_movimentacao()
        return resposta_registrada(pergunta, contexto, intent_name, resposta)

    if intent_name == "rdos_preenchimento_ruim":
        resposta = gerar_resposta_rdos_preenchimento_ruim()
        return resposta_registrada(pergunta, contexto, intent_name, resposta)

    if intent_name == "lancamento_atrasado":
        resposta = gerar_resposta_lancamento_atrasado()
        return resposta_registrada(pergunta, contexto, intent_name, resposta)

    if intent_name == "rdos_tanque_incompleto":
        resposta = gerar_resposta_rdos_tanque_incompleto(numero_os=numero_os)
        return resposta_registrada(pergunta, contexto, intent_name, resposta)

    if intent_name == "supervisores_com_pendencias":
        resposta = gerar_resposta_supervisores_com_pendencias()
        return resposta_registrada(pergunta, contexto, intent_name, resposta)

    if intent_name == "resumo_unidade" and unidade_contexto:
        resposta = responder_contexto_operacional(unidade=unidade_contexto)
        return resposta_registrada(pergunta, contexto, intent_name, resposta)

    if intent_name == "resumo_empresa" and empresa_contexto:
        resposta = responder_contexto_operacional(empresa=empresa_contexto)
        return resposta_registrada(pergunta, contexto, intent_name, resposta)

    if intent_name == "analise_unidade" and unidade_contexto:
        resposta = responder_analise_unidade(unidade_contexto)
        return resposta_registrada(pergunta, contexto, intent_name, resposta)

    if intent_name == "analise_supervisor" and supervisor:
        resposta = responder_analise_supervisor(supervisor)
        return resposta_registrada(pergunta, contexto, intent_name, resposta)

    if intent_name == "consulta_rdo" and numero_os and numero_rdo:
        resposta = responder_sobre_rdo(numero_os, numero_rdo)
        return resposta_registrada(pergunta, contexto, intent_name, resposta)

    if intent_name == "consulta_os" and numero_os:
        resposta = responder_sobre_os(numero_os)
        return resposta_registrada(pergunta, contexto, intent_name, resposta)

    if intent_name == "consulta_supervisor" and supervisor:
        resposta = responder_sobre_supervisor(supervisor)
        return resposta_registrada(pergunta, contexto, intent_name, resposta)

    if intent_name == "rdos_por_periodo":
        resposta = responder_rdos_por_periodo(pergunta)
        return resposta_registrada(pergunta, contexto, intent_name, resposta)

    if intent_name == "supervisores_por_tanque":
        if numero_os:
            resposta = analisar_supervisores_por_os(numero_os, tanque or extractors.extrair_tanque(pergunta))
            return resposta_registrada(pergunta, contexto, intent_name, resposta)

        if not tanque:
            return resposta_vazia(
                (
                    "Nao consegui identificar o tanque na sua pergunta. "
                    "Tente: 'Compare os supervisores no tanque 03P COT' ou especifique a OS: 'na OS 6298'."
                ),
                "Informe o tanque e, se quiser, a OS para comparar supervisores.",
            )

        os_encontradas = buscar_os_por_tanque(tanque)
        if not os_encontradas:
            return resposta_vazia(
                f"Nao encontrei o tanque '{tanque}' em nenhuma OS.",
                "Verifique o nome/codigo do tanque ou use outra variacao do nome.",
            )

        if len(os_encontradas) == 1:
            item = os_encontradas[0]
            resposta = analisar_supervisores_por_os(item["numero_os"], tanque)
            return resposta_registrada(pergunta, contexto, intent_name, resposta)

        linhas = [f"Encontrei o tanque {tanque} nas seguintes OSs:"]
        for item in os_encontradas:
            linhas.append(
                f"- OS {item['numero_os']}: {item['rdos_count']} RDO(s) (ultima data: {item['ultima_data']})"
            )
        linhas.extend(
            [
                "",
                "Escolha a OS para comparar supervisores: pergunte 'Compare os supervisores na OS 6298' "
                "ou peca um resumo agregado: 'Compare os supervisores no tanque 03P COT entre todas as OSs'.",
            ]
        )
        return resposta_registrada(
            pergunta,
            contexto,
            intent_name,
            {
                "introducao": "\\n".join(linhas),
                "alertas": [],
                "alertas_operacionais": [],
                "recomendacao": "Diga qual OS deseja analisar ou solicite agregacao entre OSs.",
                "confianca": "media",
            },
        )

    resposta_fallback = responder_por_intencao_ollama(pergunta)
    if resposta_fallback:
        return resposta_fallback

    registrar_pergunta(pergunta, contexto=contexto, entendida=False)
    return resposta_nao_entendida()


def responder_por_intencao_ollama(pergunta):
    intencao = classificar_intencao_com_ollama(pergunta)

    if intencao == "os_sem_rdo_recente":
        return melhorar_resposta_livre(pergunta, responder_os_sem_rdo_recente())

    if intencao == "supervisores_conflito":
        return melhorar_resposta_livre(pergunta, responder_supervisores_em_conflito())

    if intencao == "pendencias_gerais":
        return melhorar_resposta_livre(pergunta, responder_pendencias_gerais())

    return None


def resposta_registrada(pergunta, contexto, intencao, resposta, melhorar=True):
    registrar_pergunta(
        pergunta,
        contexto=contexto,
        intencao_detectada=intencao,
        entendida=True,
    )
    return melhorar_resposta_livre(pergunta, resposta) if melhorar else resposta


def resposta_nao_entendida():
    return resposta_vazia(
        (
            "Nao consegui identificar com seguranca o que voce quer consultar. "
            "Tente reformular a pergunta incluindo uma OS, um RDO, um supervisor ou o tipo de pendencia. "
            "Por exemplo:\n\n"
            "- me fale sobre a OS 6295\n"
            "- resuma o RDO 12 da OS 6295\n"
            "- quais OS estao sem RDO recente?\n"
            "- o supervisor Eduardo esta em alguma OS?\n"
            "- a empresa Modec tem quais OS acontecendo atualmente?\n"
            "- quais OS existem na unidade P-77?\n"
            "- quais OS estao em andamento?\n"
            "- qual o ensacamento total da OS 6231 no tanque TQ 3P Lastro?\n"
            "- qual o avanco diario da OS 6231 no tanque TQ 3P Lastro?\n"
            "- quanto a supervisora Carolina Machado teve de ensacamento?\n"
            "- resuma a OS 6295\n"
            "- mostre a linha do tempo da OS 6295\n"
            "- o que mudou entre o RDO 10 e o RDO 11 da OS 6295?\n"
            "- a operacao da OS 6295 parece parada?\n"
            "- como esta o desempenho operacional do supervisor Eduardo?\n"
            "- como estao as operacoes da unidade P-77?\n"
            "- o que devo priorizar agora?\n"
            "- resumo de hoje\n"
            "- quais pendencias operacionais existem?"
        ),
        "Tente informar uma OS, RDO, supervisor, empresa, unidade, status, tanque ou tipo de pendencia operacional.",
    )


def melhorar_resposta_livre(pergunta, resposta):
    resposta_base = "\n\n".join(
        trecho for trecho in (
            resposta.get("introducao", ""),
            resposta.get("recomendacao", ""),
        )
        if trecho
    )
    texto_melhorado = melhorar_resposta_com_ollama(
        pergunta=pergunta,
        dados_contexto=montar_contexto_ollama(resposta),
        resposta_base=resposta_base,
    )

    if texto_melhorado == resposta_base:
        return resposta

    resposta = dict(resposta)
    resposta["introducao"] = texto_melhorado
    resposta["recomendacao"] = ""
    return resposta


def montar_contexto_ollama(resposta):
    return {
        "resumo_base": resposta.get("introducao", ""),
        "recomendacao_base": resposta.get("recomendacao", ""),
        "quantidade_alertas_rdo": len(resposta.get("alertas", [])),
        "quantidade_alertas_operacionais": len(resposta.get("alertas_operacionais", [])),
    }


def responder_os_sem_rdo_recente():
    alertas = (
        AlertaOperacionalInteligente.objects
        .filter(status="pendente", tipo="OS_SEM_RDO_RECENTE")
        .select_related("ordem_servico")
        .order_by("-criado_em")[:15]
    )
    total = AlertaOperacionalInteligente.objects.filter(
        status="pendente",
        tipo="OS_SEM_RDO_RECENTE",
    ).count()

    if total == 0:
        return resposta_vazia(
            "Nao encontrei linhas operacionais em andamento sem RDO recente.",
            "Nenhuma acao operacional e necessaria para esse ponto no momento.",
        )

    return {
        "introducao": (
            f"Encontrei {total} linha(s) operacional(is) em andamento sem RDO recente. "
            "Listei abaixo as principais para revisao:"
        ),
        "alertas": [],
        "alertas_operacionais": alertas,
        "recomendacao": (
            "Verifique se essas operacoes continuam ativas. Se continuarem, confirme se ha RDO "
            "pendente de lancamento. Caso contrario, atualize o status da linha operacional."
        ),
    }


def responder_supervisores_em_conflito():
    alertas = (
        AlertaOperacionalInteligente.objects
        .filter(status="pendente", tipo="SUPERVISOR_EM_OS_SIMULTANEAS")
        .select_related("ordem_servico")
        .order_by("-criado_em")
    )

    if not alertas.exists():
        return resposta_vazia(
            "Nao encontrei supervisores vinculados em linhas operacionais conflitantes.",
            "Nenhuma acao e necessaria para alocacao de supervisores no momento.",
        )

    return {
        "introducao": (
            f"Encontrei {alertas.count()} alerta(s) de possivel conflito de supervisor. "
            "Isso indica que o mesmo supervisor aparece em linhas operacionais abertas de OS diferentes:"
        ),
        "alertas": [],
        "alertas_operacionais": alertas,
        "recomendacao": (
            "Confirme se o supervisor realmente esta alocado nessas operacoes ou se alguma "
            "movimentacao anterior precisa ser finalizada."
        ),
    }


def responder_alertas_pendentes():
    alertas_info = listar_alertas_rdo_consolidados(limit_exibicao=28, limit_scan=None)
    alertas = alertas_info["alertas"]
    total = alertas_info["total"]

    if total == 0:
        return resposta_vazia(
            "Olhei os RDOs disponiveis e, no momento, nao encontrei alertas pendentes.",
            "Mantenha a rotina de revisao dos RDOs para que novos problemas sejam tratados assim que aparecerem.",
        )

    linhas = [
        f"Eu encontrei {total} alerta(s) e achado(s) pendente(s) relacionados aos RDOs.",
        "",
        "Resumo do que esta aberto agora:",
        *montar_linhas_resumo_alertas_rdo(alertas_info),
        "",
        "Separei ate 28 itens distribuidos por tipo para a revisao ficar mais objetiva. Em cada item, mostro onde esta o problema, qual ponto revisar e qual equipe deve tratar.",
    ]

    return {
        "introducao": "\n".join(linhas),
        "alertas": alertas,
        "alertas_operacionais": [],
        "recomendacao": (
            "Comece por PT, data pulada, tanque incompleto e lancamentos fora do dia. Depois trate preenchimento fraco e fotos ou anexos ausentes."
        ),
    }


def responder_pendencias_gerais():
    return montar_resposta_pendencias_inteligentes(limit_operacionais=20, limit_rdo=20)


def responder_os_canonico(numero_os, titulo, frase_abertura):
    linhas_os = OrdemServico.objects.filter(numero_os=numero_os).select_related("supervisor").order_by("-id")
    if not linhas_os.exists():
        return resposta_vazia(
            f"Nao encontrei registros para a OS {numero_os}.",
            "Verifique se o numero da OS foi digitado corretamente.",
        )

    rdos = RDO.objects.filter(ordem_servico__numero_os=numero_os).order_by("data", "id")
    alertas_rdo = AlertaInteligente.objects.filter(
        rdo__ordem_servico__numero_os=numero_os,
        status="pendente",
    )
    alertas_operacionais = AlertaOperacionalInteligente.objects.filter(
        ordem_servico__numero_os=numero_os,
        status="pendente",
    )
    linha_atual = linhas_os.first()
    tanques = listar_tanques_distintos(
        RdoTanque.objects.filter(rdo__ordem_servico__numero_os=numero_os),
        numero_os,
    )
    ultimo_rdo = rdos.last()
    ultimo_tanque = (
        RdoTanque.objects
        .filter(rdo__ordem_servico__numero_os=numero_os)
        .select_related("rdo")
        .order_by("-rdo__data", "-rdo__pk", "-pk")
        .first()
    )
    supervisores = {
        str(linha.supervisor)
        for linha in linhas_os
        if getattr(linha, "supervisor", None)
    }

    detalhes = [
        bloco_texto(titulo, [frase_abertura]),
        bloco_texto(
            "Panorama atual",
            [
                f"Cliente: {getattr(linha_atual, 'cliente', None) or 'Nao informado'}",
                f"Unidade: {getattr(linha_atual, 'unidade', None) or 'Nao informada'}",
                f"Servico: {getattr(linha_atual, 'servico', None) or 'Nao informado'}",
                f"Metodo: {getattr(linha_atual, 'metodo', None) or 'Nao informado'}",
                f"Status atual: {getattr(linha_atual, 'status_operacao', None) or 'Nao informado'}",
                f"Tanques registrados: {', '.join(tanques) if tanques else (getattr(linha_atual, 'tanque', None) or 'Nao informado')}",
                f"Supervisor atual: {formatar_usuario(getattr(linha_atual, 'supervisor', None))}",
            ],
        ),
        bloco_texto(
            "Numeros consolidados",
            [
                f"Linhas operacionais encontradas: {linhas_os.count()}",
                f"RDOs lancados: {rdos.count()}",
                f"Supervisores vinculados: {len(supervisores)}",
                f"Alertas de RDO pendentes: {alertas_rdo.count()}",
                f"Alertas operacionais pendentes: {alertas_operacionais.count()}",
            ],
        ),
    ]
    if ultimo_rdo:
        detalhes.append(
            bloco_texto(
                "Ultima movimentacao identificada",
                [f"Ultimo RDO: {ultimo_rdo.rdo or 'sem numero'} em {ultimo_rdo.data or 'data nao informada'}."],
            )
        )
    if ultimo_tanque:
        detalhes.append(
            bloco_texto(
                "Avanco mais recente",
                [
                    f"Ultimo avanco de tanque registrado: {formatar_percentual(obter_valor_preferido(ultimo_tanque, 'percentual_avanco_cumulativo'))}."
                ],
            )
        )
    detalhes.append(
        bloco_texto(
            "Proximo passo sugerido",
            [
                "Se quiser, eu posso detalhar a linha do tempo, os tanques, os RDOs ou os alertas dessa OS.",
            ],
        )
    )

    return {
        "introducao": montar_texto_estruturado(*detalhes),
        "alertas": alertas_rdo.order_by("-criado_em")[:10],
        "alertas_operacionais": alertas_operacionais.order_by("-criado_em")[:10],
        "recomendacao": (
            "Comece pelos alertas pendentes e consulte a linha do tempo se quiser entender a evolucao operacional."
            if alertas_rdo.exists() or alertas_operacionais.exists()
            else "Nao encontrei alertas inteligentes pendentes para essa OS no momento."
        ),
        "contexto": {"numero_os": str(numero_os)},
    }


def responder_sobre_os(numero_os):
    return responder_os_canonico(
        numero_os,
        titulo=f"Visao geral da OS {numero_os}",
        frase_abertura="Eu localizei essa OS e consolidei os dados operacionais mais importantes abaixo.",
    )


def responder_resumo_os(numero_os):
    return responder_os_canonico(
        numero_os,
        titulo=f"Resumo da OS {numero_os}",
        frase_abertura="Eu consolidei o estado atual da operacao para voce entender rapidamente onde essa OS esta.",
    )


def responder_linha_tempo_os(numero_os):
    linhas_os = OrdemServico.objects.filter(numero_os=numero_os).select_related("supervisor").order_by("data_inicio", "id")
    if not linhas_os.exists():
        return resposta_vazia(
            f"Nao encontrei registros para a OS {numero_os}.",
            "Verifique se o numero da OS foi digitado corretamente.",
        )

    eventos = []
    inicio = min((linha.data_inicio for linha in linhas_os if linha.data_inicio), default=None)
    if inicio:
        eventos.append((inicio, "Inicio da operacao registrado."))

    supervisor_anterior = None
    for linha in linhas_os:
        supervisor_atual = getattr(linha, "supervisor", None)
        supervisor_label = str(supervisor_atual) if supervisor_atual else ""
        if supervisor_label and supervisor_label != supervisor_anterior:
            eventos.append(
                (
                    linha.data_inicio or inicio or timezone.localdate(),
                    f"Supervisor vinculado: {supervisor_label}.",
                )
            )
            supervisor_anterior = supervisor_label

    rdos = list(
        RDO.objects
        .filter(ordem_servico__numero_os=numero_os)
        .prefetch_related("atividades_rdo")
        .order_by("data", "id")
    )
    for rdo in rdos:
        if rdo.data:
            eventos.append((rdo.data, f"RDO {rdo.rdo or 'sem numero'} lancado."))
            if rdo.confinado or possui_acesso_confinado(rdo):
                eventos.append((rdo.data, f"Acesso a espaco confinado registrado no RDO {rdo.rdo or 'sem numero'}."))

    ultimo_rdo = rdos[-1] if rdos else None
    if ultimo_rdo and ultimo_rdo.data and ultimo_rdo.data < timezone.localdate():
        dias_sem_rdo = (timezone.localdate() - ultimo_rdo.data).days
        eventos.append(
            (
                timezone.localdate(),
                f"Sem novo RDO ha {dias_sem_rdo} dia(s) desde {ultimo_rdo.data}.",
            )
        )

    if not eventos:
        return resposta_vazia(
            f"Nao encontrei eventos suficientes para montar a linha do tempo da OS {numero_os}.",
            "Cadastre datas e RDOs para que a IA consiga reconstruir a evolucao da operacao.",
        )

    eventos_unicos = []
    vistos = set()
    for evento in eventos:
        chave = (evento[0], evento[1])
        if chave in vistos:
            continue
        vistos.add(chave)
        eventos_unicos.append(evento)

    eventos_ordenados = sorted(eventos_unicos, key=lambda item: (item[0], item[1]))
    detalhes = [f"Linha do tempo da OS {numero_os}:", ""]

    # Construir linha do tempo estruturada (data + descricao) para renderizacao segura
    linha_tempo = []
    for data_evento, descricao in eventos_ordenados:
        data_str = formatar_data(data_evento)
        desc = (descricao or "").strip()
        if not desc:
            # Se descricao estiver vazia, evitar linha sem texto no frontend
            desc = "Evento registrado."
        linha_tempo.append({"data": data_str, "descricao": desc})
        detalhes.append(f"- {data_str} - {desc}")

    return {
        "introducao": "\n".join(detalhes),
        "linha_tempo": linha_tempo,
        "alertas": [],
        "alertas_operacionais": [],
        "recomendacao": "Use a linha do tempo para identificar lacunas, mudancas de responsavel e periodos sem atualizacao.",
        "contexto": {"numero_os": str(numero_os)},
    }


def responder_comparacao_rdos(numero_os, rdo_a, rdo_b):
    rdos = {
        str(rdo.rdo): rdo
        for rdo in (
            RDO.objects
            .filter(ordem_servico__numero_os=numero_os, rdo__in=[rdo_a, rdo_b])
            .prefetch_related("atividades_rdo")
            .order_by("data", "id")
        )
    }
    primeiro = rdos.get(str(rdo_a))
    segundo = rdos.get(str(rdo_b))
    if not primeiro or not segundo:
        return resposta_vazia(
            f"Nao consegui comparar os RDOs {rdo_a} e {rdo_b} da OS {numero_os} porque um deles nao foi encontrado.",
            "Confira se os dois numeros de RDO pertencem a essa OS.",
        )

    mudancas = []
    comparar_campo(mudancas, "Data", primeiro.data, segundo.data)
    comparar_campo(mudancas, "Turno", primeiro.turno, segundo.turno)
    comparar_campo(mudancas, "PT manha", primeiro.pt_manha, segundo.pt_manha)
    comparar_campo(mudancas, "PT tarde", primeiro.pt_tarde, segundo.pt_tarde)
    comparar_campo(mudancas, "PT noite", primeiro.pt_noite, segundo.pt_noite)
    comparar_campo(mudancas, "Espaco confinado", bool(primeiro.confinado), bool(segundo.confinado))
    comparar_campo(mudancas, "Volume do tanque", primeiro.volume_tanque_exec, segundo.volume_tanque_exec)

    atividades_a = set(primeiro.atividades_rdo.values_list("atividade", flat=True))
    atividades_b = set(segundo.atividades_rdo.values_list("atividade", flat=True))
    novas_atividades = sorted(item for item in atividades_b - atividades_a if item)
    atividades_removidas = sorted(item for item in atividades_a - atividades_b if item)
    if novas_atividades:
        mudancas.append(f"Novas atividades registradas: {', '.join(novas_atividades)}.")
    if atividades_removidas:
        mudancas.append(f"Atividades que deixaram de aparecer: {', '.join(atividades_removidas)}.")

    tanque_a = ultimo_tanque_do_rdo(primeiro)
    tanque_b = ultimo_tanque_do_rdo(segundo)
    if tanque_a or tanque_b:
        comparar_campo(
            mudancas,
            "Avanco do tanque",
            getattr(tanque_a, "percentual_avanco_cumulativo", None),
            getattr(tanque_b, "percentual_avanco_cumulativo", None),
            percentual=True,
        )
        comparar_campo(
            mudancas,
            "Ensacamento acumulado",
            getattr(tanque_a, "ensacamento_cumulativo", None),
            getattr(tanque_b, "ensacamento_cumulativo", None),
        )

    if not mudancas:
        mudancas.append("Nao identifiquei mudancas relevantes entre os campos comparados.")

    detalhes = [
        f"Comparacao entre o RDO {rdo_a} e o RDO {rdo_b} da OS {numero_os}:",
        "",
    ]
    detalhes.extend(f"- {mudanca}" for mudanca in mudancas)
    return {
        "introducao": "\n".join(detalhes),
        "alertas": [],
        "alertas_operacionais": [],
        "recomendacao": "Use essa comparacao para revisar mudancas operacionais sem precisar abrir os dois RDOs lado a lado.",
        "contexto": {"numero_os": str(numero_os)},
    }


def responder_operacao_parada(numero_os):
    linhas_os = OrdemServico.objects.filter(numero_os=numero_os).order_by("-id")
    if not linhas_os.exists():
        return resposta_vazia(
            f"Nao encontrei registros para a OS {numero_os}.",
            "Verifique se o numero da OS foi digitado corretamente.",
        )

    linha_atual = linhas_os.first()
    status = getattr(linha_atual, "status_operacao", None)
    ultimo_rdo = (
        RDO.objects
        .filter(ordem_servico__numero_os=numero_os, data__isnull=False)
        .order_by("-data", "-id")
        .first()
    )
    tanques = list(
        RdoTanque.objects
        .filter(rdo__ordem_servico__numero_os=numero_os, rdo__data__isnull=False)
        .select_related("rdo")
        .order_by("-rdo__data", "-rdo__pk", "-pk")[:2]
    )

    sinais = []
    if status == "Em Andamento":
        sinais.append("a linha continua com status Em Andamento")
    if ultimo_rdo and ultimo_rdo.data:
        dias_sem_rdo = (timezone.localdate() - ultimo_rdo.data).days
        if dias_sem_rdo >= 2:
            sinais.append(f"nao ha novo RDO ha {dias_sem_rdo} dia(s)")
    if len(tanques) >= 2:
        atual, anterior = tanques[0], tanques[1]
        avanco_atual = float(getattr(atual, "percentual_avanco_cumulativo", None) or 0)
        avanco_anterior = float(getattr(anterior, "percentual_avanco_cumulativo", None) or 0)
        if avanco_atual <= avanco_anterior:
            sinais.append("nao houve aumento de avanco entre os dois ultimos registros de tanque")

    parece_parada = status == "Em Andamento" and len(sinais) >= 2
    if parece_parada:
        introducao = (
            f"A operacao da OS {numero_os} apresenta sinais de possivel parada.\n\n"
            + "\n".join(f"- {sinal.capitalize()}." for sinal in sinais)
        )
        recomendacao = (
            "Confirme se a operacao realmente continua ativa, se existe RDO pendente de lancamento "
            "ou se o status da linha precisa ser atualizado."
        )
    else:
        introducao = (
            f"Nao encontrei indicios suficientes para afirmar que a operacao da OS {numero_os} esta parada."
        )
        if sinais:
            introducao += "\n\nSinais observados:\n" + "\n".join(f"- {sinal.capitalize()}." for sinal in sinais)
        recomendacao = "Acompanhe novos RDOs e o avanco do tanque para confirmar a evolucao da operacao."

    return {
        "introducao": introducao,
        "alertas": [],
        "alertas_operacionais": [],
        "recomendacao": recomendacao,
        "contexto": {"numero_os": str(numero_os)},
    }


def responder_sobre_rdo(numero_os, numero_rdo):
    rdo = (
        RDO.objects
        .filter(ordem_servico__numero_os=numero_os, rdo=numero_rdo)
        .select_related("ordem_servico")
        .order_by("-id")
        .first()
    )

    if not rdo:
        return resposta_vazia(
            f"Nao encontrei o RDO {numero_rdo} vinculado a OS {numero_os}.",
            "Confira se a OS e o numero do RDO foram digitados corretamente.",
        )

    alertas = (
        AlertaInteligente.objects
        .filter(rdo=rdo, status="pendente")
        .select_related("rdo", "rdo__ordem_servico")
        .order_by("-criado_em")
    )
    status_analise = getattr(rdo, "status_analise_ia", None)

    return {
        "introducao": (
            f"Encontrei o RDO {numero_rdo} da OS {numero_os}.\n\n"
            f"Data: {getattr(rdo, 'data', None) or 'Nao informada'}\n"
            f"Turno: {getattr(rdo, 'turno', None) or 'Nao informado'}\n"
            f"Status da analise inteligente: {status_analise or 'Nao informado'}\n"
            f"Alertas pendentes: {alertas.count()}"
        ),
        "alertas": alertas,
        "alertas_operacionais": [],
        "recomendacao": (
            "Esse RDO possui pendencias inteligentes. Recomendo revisar os pontos listados abaixo."
            if alertas.exists()
            else "Esse RDO nao possui alertas inteligentes pendentes no momento."
        ),
        "contexto": {
            "numero_os": str(numero_os),
        },
    } 


def responder_supervisor_canonico(nome_supervisor, metricas=None):
    linhas = buscar_linhas_supervisor(nome_supervisor).order_by("-id")
    if not linhas.exists():
        return resposta_vazia(
            f"Nao encontrei linhas operacionais vinculadas ao supervisor '{nome_supervisor}'.",
            "Verifique se o nome foi digitado corretamente ou pesquise apenas pelo primeiro nome.",
        )

    status_counts = contar_por_status(linhas)
    alertas_operacionais = (
        AlertaOperacionalInteligente.objects
        .filter(ordem_servico__in=linhas, status="pendente")
        .select_related("ordem_servico")
        .order_by("-criado_em")
    )
    alertas_rdo = (
        AlertaInteligente.objects
        .filter(rdo__ordem_servico__in=linhas, status="pendente")
        .select_related("rdo", "rdo__ordem_servico")
        .order_by("-criado_em")
    )
    sem_rdo_recente = alertas_operacionais.filter(tipo="OS_SEM_RDO_RECENTE").count()
    detalhes = [
        bloco_texto(
            f"Resumo do supervisor '{nome_supervisor}'",
            [
                "Eu consolidei as linhas operacionais, os alertas e, quando aplicavel, a producao registrada nesse escopo.",
            ],
        ),
        bloco_texto(
            "Panorama atual",
            [
                f"Linhas vinculadas: {linhas.count()}",
                f"Em andamento: {status_counts.get('Em Andamento', 0)}",
                f"Programadas: {status_counts.get('Programada', 0)}",
                f"Finalizadas: {status_counts.get('Finalizada', 0)}",
                f"Linhas sem RDO recente: {sem_rdo_recente}",
                f"Alertas operacionais pendentes: {alertas_operacionais.count()}",
                f"Alertas de RDO pendentes: {alertas_rdo.count()}",
            ],
        ),
    ]

    if metricas:
        rows = RdoTanque.objects.filter(rdo__ordem_servico__in=linhas)
        linhas_metricas = []
        if "ensacamento" in metricas:
            linhas_metricas.append(f"Ensacamento: {formatar_numero(somar_campo_diario(rows, 'ensacamento_dia'))} saco(s).")
        if "icamento" in metricas:
            linhas_metricas.append(f"Icamento: {formatar_numero(somar_campo_diario(rows, 'icamento_dia'))}.")
        if "cambagem" in metricas:
            linhas_metricas.append(f"Cambagem: {formatar_numero(somar_campo_diario(rows, 'cambagem_dia'))}.")
        if "tempo_bomba" in metricas:
            linhas_metricas.append(f"Tempo total de bomba: {formatar_numero(somar_campo_diario(rows, 'tempo_bomba'))} hora(s).")
        if linhas_metricas:
            detalhes.append(bloco_texto("Producao registrada", linhas_metricas))

    linhas_destaque = []
    for linha in linhas[:8]:
        linhas_destaque.append(
            f"- OS {linha.numero_os} | {getattr(linha, 'unidade', None) or 'Unidade nao informada'} | "
            f"Tanque: {getattr(linha, 'tanque', None) or 'Nao informado'} | "
            f"Status: {getattr(linha, 'status_operacao', None) or 'Nao informado'}"
        )
    detalhes.append(bloco_texto("Linhas em destaque", linhas_destaque))
    detalhes.append(
        bloco_texto(
            "Proximo passo sugerido",
            [
                "Revise primeiro as linhas em andamento sem RDO recente e depois os alertas pendentes associados a esse supervisor."
                if sem_rdo_recente or alertas_operacionais.exists() or alertas_rdo.exists()
                else "Nao encontrei pendencias inteligentes associadas a esse supervisor no momento.",
            ],
        )
    )

    recomendacao = (
        "Revise primeiro as linhas em andamento sem RDO recente e depois os alertas pendentes associados a esse supervisor."
        if sem_rdo_recente or alertas_operacionais.exists() or alertas_rdo.exists()
        else "Nao encontrei pendencias inteligentes associadas a esse supervisor no momento."
    )

    return {
        "introducao": montar_texto_estruturado(*detalhes),
        "alertas": alertas_rdo[:10],
        "alertas_operacionais": alertas_operacionais[:10],
        "recomendacao": recomendacao,
        "contexto": {"supervisor": nome_supervisor},
    }


def responder_sobre_supervisor(nome_supervisor):
    return responder_supervisor_canonico(nome_supervisor)


def responder_sobre_tanque_os(numero_os, nome_tanque=None, metricas=None):
    metricas = metricas or set()
    resolucao = resolver_tanque_os(numero_os, nome_tanque)
    if resolucao["erro"]:
        return resposta_vazia(resolucao["erro"], resolucao["recomendacao"])

    tanque_label = resolucao["label"]
    rows = resolucao["rows"]
    ultimo_tanque = rows.order_by("-rdo__data", "-rdo__pk", "-pk").first()
    if not ultimo_tanque:
        return resposta_vazia(
            f"Nao encontrei dados de tanque para a OS {numero_os}.",
            "Verifique se ja existe algum RDO com informacoes de tanque nessa OS.",
        )

    snapshot = ultimo_tanque.build_compartimento_progress_snapshot()
    metricas_exibir = metricas or {
        "ensacamento",
        "icamento",
        "cambagem",
        "tempo_bomba",
        "avanco_total",
        "avanco_diario",
        "limpeza_mecanizada",
        "limpeza_fina",
        "compartimentos",
    }

    detalhes = [
        f"Encontrei dados do tanque {tanque_label} na OS {numero_os}.",
        "",
        f"Ultimo RDO considerado: {getattr(ultimo_tanque.rdo, 'rdo', 'Nao informado')} "
        f"em {getattr(ultimo_tanque.rdo, 'data', None) or 'data nao informada'}.",
    ]

    if "ensacamento" in metricas_exibir:
        detalhes.append(
            f"Ensacamento total: {formatar_numero(obter_valor_preferido(ultimo_tanque, 'ensacamento_cumulativo'))} saco(s)."
        )
    if "icamento" in metricas_exibir:
        detalhes.append(
            f"Icamento total: {formatar_numero(obter_valor_preferido(ultimo_tanque, 'icamento_cumulativo'))}."
        )
    if "cambagem" in metricas_exibir:
        detalhes.append(
            f"Cambagem total: {formatar_numero(obter_valor_preferido(ultimo_tanque, 'cambagem_cumulativo'))}."
        )
    if "tempo_bomba" in metricas_exibir:
        detalhes.append(
            f"Tempo total de bomba: {formatar_numero(somar_campo_diario(rows, 'tempo_bomba'))} hora(s)."
        )
    if "avanco_total" in metricas_exibir:
        detalhes.append(
            f"Avanco total do tanque: {formatar_percentual(obter_valor_preferido(ultimo_tanque, 'percentual_avanco_cumulativo'))}."
        )
    if "avanco_diario" in metricas_exibir:
        detalhes.append(
            f"Avanco diario no ultimo RDO: {formatar_percentual(obter_valor_preferido(ultimo_tanque, 'percentual_avanco'))}."
        )
    if "limpeza_mecanizada" in metricas_exibir:
        detalhes.append(
            "Limpeza mecanizada: "
            f"{formatar_percentual(valor_limpeza_diaria(ultimo_tanque, snapshot, 'mecanizada'))} no dia e "
            f"{formatar_percentual(valor_limpeza_acumulada(ultimo_tanque, snapshot, 'mecanizada'))} acumulado."
        )
    if "limpeza_fina" in metricas_exibir:
        detalhes.append(
            "Limpeza fina: "
            f"{formatar_percentual(valor_limpeza_diaria(ultimo_tanque, snapshot, 'fina'))} no dia e "
            f"{formatar_percentual(valor_limpeza_acumulada(ultimo_tanque, snapshot, 'fina'))} acumulado."
        )
    if "compartimentos" in metricas_exibir:
        linhas_compartimentos = montar_linhas_compartimentos(snapshot)
        if linhas_compartimentos:
            detalhes.extend(["", "Avanco por compartimento:"])
            detalhes.extend(linhas_compartimentos)
        else:
            detalhes.append("Nao encontrei avancos por compartimento registrados para esse tanque.")

    tanque_resp = {
        "introducao": "\n".join(detalhes),
        "alertas": [],
        "alertas_operacionais": [],
        "recomendacao": (
            "Se quiser, voce pode perguntar por um indicador especifico desse tanque, "
            "como ensacamento, icamento, cambagem, tempo de bomba ou avanco por compartimento."
        ),
        "contexto": {
            "numero_os": str(numero_os),
            "tanque": tanque_label,
        },
    }

    return tanque_resp


def responder_producao_supervisor(nome_supervisor, metricas):
    return responder_supervisor_canonico(
        nome_supervisor,
        metricas=metricas or {"ensacamento", "icamento", "cambagem", "tempo_bomba"},
    )


def responder_analise_supervisor(nome_supervisor):
    return responder_supervisor_canonico(nome_supervisor)


def responder_contexto_operacional(empresa=None, unidade=None, status_operacao=None, sem_rdo_recente=False):
    linhas = OrdemServico.objects.select_related("Cliente", "Unidade", "supervisor")
    filtros = []

    if empresa:
        clientes = Cliente.objects.filter(nome__icontains=empresa)
        linhas = linhas.filter(Cliente__in=clientes)
        filtros.append(f"empresa '{empresa}'")

    if unidade:
        unidades = Unidade.objects.filter(nome__icontains=unidade)
        linhas = linhas.filter(Unidade__in=unidades)
        filtros.append(f"unidade '{unidade}'")

    if status_operacao:
        linhas = linhas.filter(status_operacao=status_operacao)
        filtros.append(f"status '{status_operacao}'")

    if sem_rdo_recente:
        ids_sem_rdo = AlertaOperacionalInteligente.objects.filter(
            status="pendente",
            tipo="OS_SEM_RDO_RECENTE",
        ).values_list("ordem_servico_id", flat=True)
        linhas = linhas.filter(id__in=ids_sem_rdo)
        filtros.append("sem RDO recente")

    linhas = linhas.order_by("-id")
    if not linhas.exists():
        descricao = formatar_descricao_filtros(filtros)
        return resposta_vazia(
            f"Nao encontrei linhas operacionais para {descricao}.",
            "Tente remover algum filtro ou verificar se os nomes foram digitados corretamente.",
        )

    if empresa and not unidade and not status_operacao and not sem_rdo_recente:
        return gerar_resumo_contexto_operacional("empresa", empresa, linhas)

    if unidade and not empresa and not status_operacao and not sem_rdo_recente:
        return gerar_resumo_contexto_operacional("unidade", unidade, linhas)

    descricao = formatar_descricao_filtros(filtros)
    status_counts = contar_por_status(linhas)
    alertas_operacionais = (
        AlertaOperacionalInteligente.objects
        .filter(ordem_servico__in=linhas, status="pendente")
        .select_related("ordem_servico")
        .order_by("-criado_em")
    )
    alertas_rdo = (
        AlertaInteligente.objects
        .filter(rdo__ordem_servico__in=linhas, status="pendente")
        .select_related("rdo", "rdo__ordem_servico")
        .order_by("-criado_em")
    )
    # Deduplicate OSs (numero_os) to avoid showing same OS multiple times
    # when there are multiple OrdemServico records (linhas operacionais) for the same OS number
    oses_vistas = set()
    linhas_destaque = []
    for linha in linhas:
        numero_os = linha.numero_os
        if numero_os in oses_vistas:
            continue
        if len(linhas_destaque) >= 8:
            break
        oses_vistas.add(numero_os)
        linhas_destaque.append(
            f"- OS {numero_os} | {getattr(linha, 'unidade', None) or 'Unidade nao informada'} | "
            f"Cliente: {getattr(linha, 'cliente', None) or 'Cliente nao informado'} | "
            f"Status: {getattr(linha, 'status_operacao', None) or 'Nao informado'}"
        )

    introducao = montar_texto_estruturado(
        bloco_texto(
            "Resumo do contexto operacional",
            [f"Eu consolidei as linhas operacionais para {descricao}."],
        ),
        bloco_texto(
            "Panorama atual",
            [
                f"Linhas operacionais encontradas: {linhas.count()}",
                f"Em andamento: {status_counts.get('Em Andamento', 0)}",
                f"Programadas: {status_counts.get('Programada', 0)}",
                f"Finalizadas: {status_counts.get('Finalizada', 0)}",
                f"Alertas operacionais pendentes: {alertas_operacionais.count()}",
                f"Alertas de RDO pendentes: {alertas_rdo.count()}",
            ],
        ),
        bloco_texto("Linhas em destaque", linhas_destaque),
        bloco_texto(
            "Proximo passo sugerido",
            ["Se quiser, eu posso detalhar uma OS especifica, filtrar por supervisor ou aprofundar os alertas desse contexto."],
        ),
    )

    return {
        "introducao": introducao,
        "alertas": alertas_rdo[:10],
        "alertas_operacionais": alertas_operacionais[:10],
        "recomendacao": (
            "Priorize as linhas em andamento com alertas operacionais e os RDOs pendentes de revisao inteligente."
            if alertas_operacionais.exists() or alertas_rdo.exists()
            else "Nao encontrei pendencias inteligentes relevantes nesse contexto no momento."
        ),
    }


def responder_analise_unidade(nome_unidade):
    return responder_contexto_operacional(unidade=nome_unidade)


def responder_prioridades_recomendadas():
    candidatos = []
    for alerta in (
        AlertaOperacionalInteligente.objects
        .filter(status="pendente")
        .select_related("ordem_servico")
    ):
        candidatos.append(
            {
                "prioridade": alerta.prioridade,
                "rotulo": alerta.identificacao_operacional,
                "motivo": alerta.explicacao_curta,
                "tipo": alerta.get_tipo_display(),
            }
        )
    for alerta in (
        AlertaInteligente.objects
        .filter(status="pendente")
        .select_related("rdo", "rdo__ordem_servico")
    ):
        candidatos.append(
            {
                "prioridade": alerta.prioridade,
                "rotulo": alerta.identificacao_operacional,
                "motivo": alerta.explicacao_curta if hasattr(alerta, "explicacao_curta") else alerta.mensagem,
                "tipo": alerta.get_tipo_display(),
            }
        )

    if not candidatos:
        return resposta_vazia(
            "Nao encontrei alertas pendentes para priorizar agora.",
            "A fila inteligente esta limpa neste momento.",
        )

    candidatos.sort(key=lambda item: (ordem_prioridade_texto(item["prioridade"]), item["rotulo"]))
    selecionados = candidatos[:5]
    detalhes = ["Eu recomendo priorizar estes pontos agora:", ""]
    for indice, item in enumerate(selecionados, start=1):
        detalhes.append(
            f"{indice}. {item['rotulo']} - {item['tipo']} ({rotular_prioridade(item['prioridade'])})."
        )
        detalhes.append(f"   Motivo: {item['motivo']}")

    return {
        "introducao": "\n".join(detalhes),
        "alertas": [],
        "alertas_operacionais": [],
        "recomendacao": "Comece pelos itens criticos e de alta prioridade; depois siga para os demais apontamentos pendentes.",
    }


def responder_resumo_diario():
    hoje = timezone.localdate()
    rdos_analisados = RDO.objects.filter(data_analise_ia__date=hoje).count()
    alertas_rdo_criados = AlertaInteligente.objects.filter(criado_em__date=hoje).count()
    alertas_operacionais_criados = AlertaOperacionalInteligente.objects.filter(criado_em__date=hoje).count()
    linhas_sem_rdo = AlertaOperacionalInteligente.objects.filter(
        status="pendente",
        tipo="OS_SEM_RDO_RECENTE",
    ).count()
    conflitos_supervisor = AlertaOperacionalInteligente.objects.filter(
        status="pendente",
        tipo="SUPERVISOR_EM_OS_SIMULTANEAS",
    ).count()
    alertas_resolvidos = (
        AlertaInteligente.objects.filter(resolvido_em__date=hoje).count()
        + AlertaOperacionalInteligente.objects.filter(resolvido_em__date=hoje).count()
    )
    top_prioridades = montar_top_prioridades(limit=2)

    detalhes = [
        f"Resumo inteligente de hoje ({formatar_data(hoje)}):",
        "",
        f"RDOs analisados: {rdos_analisados}",
        f"Alertas de RDO criados hoje: {alertas_rdo_criados}",
        f"Alertas operacionais criados hoje: {alertas_operacionais_criados}",
        f"Linhas sem RDO recente neste momento: {linhas_sem_rdo}",
        f"Possiveis conflitos de supervisor pendentes: {conflitos_supervisor}",
        f"Alertas resolvidos hoje: {alertas_resolvidos}",
    ]
    if top_prioridades:
        detalhes.extend(["", "Pontos que eu priorizaria agora:"])
        detalhes.extend(f"- {item}" for item in top_prioridades)

    return {
        "introducao": "\n".join(detalhes),
        "alertas": [],
        "alertas_operacionais": [],
        "recomendacao": (
            "Use esse resumo para abrir a rotina diaria e tratar primeiro os pontos de maior prioridade."
        ),
    }


def responder_sobre_empresa(nome_empresa):
    return responder_contexto_operacional(empresa=nome_empresa)


def responder_sobre_unidade(nome_unidade):
    return responder_contexto_operacional(unidade=nome_unidade)


def responder_sobre_status(status_operacao):
    return responder_contexto_operacional(status_operacao=status_operacao)


def responder_linhas_filtradas(
    empresa=None,
    unidade=None,
    status_operacao=None,
    sem_rdo_recente=False,
):
    return responder_contexto_operacional(
        empresa=empresa,
        unidade=unidade,
        status_operacao=status_operacao,
        sem_rdo_recente=sem_rdo_recente,
    )


def montar_resposta_linhas(titulo, linhas, recomendacao):
    linhas_exibidas = linhas[:10]
    detalhes = [
        bloco_texto(
            "Resultado da consulta",
            [titulo],
        )
    ]
    linhas_formatadas = []
    for linha in linhas_exibidas:
        linhas_formatadas.append(
            f"- OS {linha.numero_os} | {getattr(linha, 'unidade', None) or 'Unidade nao informada'} | "
            f"Cliente: {getattr(linha, 'cliente', None) or 'Cliente nao informado'} | "
            f"Status: {getattr(linha, 'status_operacao', None) or 'Nao informado'}"
        )
    detalhes.append(bloco_texto("Linhas encontradas", linhas_formatadas))
    detalhes.append(
        bloco_texto(
            "Proximo passo sugerido",
            [recomendacao],
        )
    )

    return {
        "introducao": montar_texto_estruturado(*detalhes),
        "alertas": [],
        "alertas_operacionais": [],
        "recomendacao": recomendacao,
    }


def pergunta_indica_sem_rdo_recente(texto_busca):
    return (
        "sem rdo" in texto_busca
        or "rdo recente" in texto_busca
        or "sem relatorio diario recente" in texto_busca
        or ("relatorio diario recente" in texto_busca and "sem" in texto_busca)
    )


def pergunta_indica_alertas_pendentes(texto_busca):
    if "operacional" in texto_busca or "operacionais" in texto_busca:
        return False

    return any(
        termo in texto_busca
        for termo in (
            "alertas pendentes",
            "alerta pendente",
            "alertas inteligentes",
            "alertas de rdo",
            "alertas do rdo",
            "rdo com alerta",
            "rdos com alerta",
        )
    )


def pergunta_indica_resumo_os(texto_busca):
    return (
        "resuma a os" in texto_busca
        or "resumo da os" in texto_busca
        or "resumo da ordem" in texto_busca
    )


def pergunta_indica_linha_tempo(texto_busca):
    return "linha do tempo" in texto_busca or "historico da os" in texto_busca


def pergunta_indica_comparacao_rdos(texto_busca):
    return any(
        termo in texto_busca
        for termo in (
            "o que mudou entre",
            "compare",
            "comparacao",
            "diferença entre",
            "diferenca entre",
        )
    )


def pergunta_indica_operacao_parada(texto_busca):
    return any(
        termo in texto_busca
        for termo in (
            "operacao parada",
            "operação parada",
            "parece parada",
            "sem avanco",
            "sem avanço",
            "esta parada",
            "está parada",
        )
    )


def pergunta_indica_analise_supervisor(texto_busca):
    return any(
        termo in texto_busca
        for termo in (
            "desempenho operacional",
            "como esta o desempenho",
            "como está o desempenho",
            "analise do supervisor",
            "análise do supervisor",
        )
    )


def pergunta_indica_analise_unidade(texto_busca):
    return any(
        termo in texto_busca
        for termo in (
            "como estao as operacoes",
            "como estão as operações",
            "analise da unidade",
            "análise da unidade",
        )
    )


def pergunta_indica_priorizacao(texto_busca):
    return any(
        termo in texto_busca
        for termo in (
            "o que devo priorizar",
            "priorizar agora",
            "prioridades",
            "recomenda priorizar",
        )
    )


def pergunta_indica_resumo_diario(texto_busca):
    return any(
        termo in texto_busca
        for termo in (
            "resumo de hoje",
            "resumo diario",
            "resumo diário",
            "resumo inteligente de hoje",
        )
    )


def identificar_metricas_tanque(texto_busca):
    metricas = set()
    if "ensacamento" in texto_busca:
        metricas.add("ensacamento")
    if "icamento" in texto_busca or "içamento" in texto_busca:
        metricas.add("icamento")
    if "cambagem" in texto_busca:
        metricas.add("cambagem")
    if "tempo total de bomba" in texto_busca or "tempo de bomba" in texto_busca or "bomba" in texto_busca:
        metricas.add("tempo_bomba")
    if "avanco total" in texto_busca or "avanço total" in texto_busca:
        metricas.add("avanco_total")
    if "avanco diario" in texto_busca or "avanço diario" in texto_busca or "avanço diário" in texto_busca:
        metricas.add("avanco_diario")
    if "limpeza mecanizada" in texto_busca or "mecanizada" in texto_busca:
        metricas.add("limpeza_mecanizada")
    if "limpeza fina" in texto_busca or "fina" in texto_busca:
        metricas.add("limpeza_fina")
    if "compartimento" in texto_busca:
        metricas.add("compartimentos")
    if ("avanco" in texto_busca or "avanço" in texto_busca) and not (
        {"avanco_total", "avanco_diario"} & metricas
    ):
        metricas.update({"avanco_total", "avanco_diario"})
    return metricas


def resolver_tanque_os(numero_os, nome_tanque=None):
    rows = RdoTanque.objects.filter(rdo__ordem_servico__numero_os=numero_os).select_related("rdo")
    labels = listar_tanques_distintos(rows, numero_os)

    if not labels:
        return {
            "erro": f"Nao encontrei tanques registrados para a OS {numero_os}.",
            "recomendacao": "Verifique se ja existe algum RDO com dados de tanque nessa OS.",
            "label": None,
            "rows": rows.none(),
        }

    if not nome_tanque:
        if len(labels) == 1:
            label = labels[0]
            return {"erro": None, "recomendacao": "", "label": label, "rows": filtrar_rows_tanque(rows, label, numero_os)}
        return {
            "erro": (
                f"A OS {numero_os} possui mais de um tanque registrado: {', '.join(labels)}. "
                "Informe qual tanque deseja consultar."
            ),
            "recomendacao": "Exemplo: qual o ensacamento total da OS 6231 no tanque TQ 3P Lastro?",
            "label": None,
            "rows": rows.none(),
        }

    candidatos = [
        label for label in labels
        if normalizar_identificador_tanque(nome_tanque) == normalizar_identificador_tanque(label)
        or nome_tanque.lower().strip() == label.lower().strip()
    ]
    if not candidatos:
        # Fallback: try substring matching as secondary option
        candidatos = [
            label for label in labels
            if normalizar_identificador_tanque(nome_tanque) in normalizar_identificador_tanque(label)
            or normalizar_identificador_tanque(label) in normalizar_identificador_tanque(nome_tanque)
        ]
    if not candidatos:
        return {
            "erro": (
                f"Nao encontrei o tanque '{nome_tanque}' na OS {numero_os}. "
                f"Tanques disponiveis: {', '.join(labels)}."
            ),
            "recomendacao": "Digite o nome do tanque como aparece no RDO.",
            "label": None,
            "rows": rows.none(),
        }
    if len(candidatos) > 1:
        # If we got here from substring matching, keep only the best matches
        exact_matches = [
            label for label in candidatos
            if normalizar_identificador_tanque(nome_tanque) == normalizar_identificador_tanque(label)
        ]
        if exact_matches:
            candidatos = exact_matches
        if len(candidatos) > 1:
            return {
                "erro": (
                    f"Encontrei mais de um tanque parecido com '{nome_tanque}' na OS {numero_os}: "
                    f"{', '.join(candidatos)}. Informe um nome mais especifico."
                ),
                "recomendacao": "Use o nome completo do tanque para evitar ambiguidade.",
                "label": None,
                "rows": rows.none(),
            }

    label = candidatos[0]
    return {"erro": None, "recomendacao": "", "label": label, "rows": filtrar_rows_tanque(rows, label, numero_os)}


def listar_tanques_distintos(rows, numero_os):
    labels_por_chave = {}
    for tanque_codigo, nome_tanque in rows.values_list("tanque_codigo", "nome_tanque"):
        label = str(tanque_codigo or nome_tanque or "").strip()
        if not label:
            continue
        chave = _tank_identity_key(tanque_codigo, nome_tanque, os_num=numero_os) or normalizar_identificador_tanque(label)
        labels_por_chave.setdefault(chave, label)
    return sorted(labels_por_chave.values(), key=lambda item: normalizar_busca(item))


def filtrar_rows_tanque(rows, label, numero_os):
    # Use normalizar_identificador_tanque consistently to avoid mismatches
    # between _tank_identity_key (which removes markers like 'cot') and
    # the simpler normalization used elsewhere.
    chave_alvo = normalizar_identificador_tanque(label)
    ids = []
    for tank_id, tanque_codigo, nome_tanque in rows.values_list("id", "tanque_codigo", "nome_tanque"):
        # Also check with _tank_identity_key as fallback for DB compatibility
        chave_simple = normalizar_identificador_tanque(tanque_codigo or nome_tanque)
        chave_advanced = _tank_identity_key(tanque_codigo, nome_tanque, os_num=numero_os)
        
        if chave_alvo == chave_simple:
            ids.append(tank_id)
        elif chave_advanced:
            # If advanced key matches, also include
            chave_alvo_advanced = _tank_identity_key(label, label, os_num=numero_os)
            if chave_alvo_advanced and chave_advanced == chave_alvo_advanced:
                ids.append(tank_id)
    return rows.filter(id__in=ids)


def buscar_linhas_supervisor(nome_supervisor):
    nome_normalizado = normalizar_identificador_supervisor(nome_supervisor)
    filtros_supervisor = (
        Q(supervisor__username__icontains=nome_supervisor)
        | Q(supervisor__first_name__icontains=nome_supervisor)
        | Q(supervisor__last_name__icontains=nome_supervisor)
        | Q(supervisor__email__icontains=nome_supervisor)
    )
    linhas = OrdemServico.objects.filter(filtros_supervisor).select_related("supervisor")
    if linhas.exists() or not nome_normalizado:
        return linhas
    ids_normalizados = [
        linha.id
        for linha in OrdemServico.objects.select_related("supervisor")
        if normalizar_identificador_supervisor(
            getattr(getattr(linha, "supervisor", None), "username", "")
        ) == nome_normalizado
    ]
    return OrdemServico.objects.filter(id__in=ids_normalizados).select_related("supervisor")


def somar_campo_diario(rows, campo):
    total = 0
    encontrou = False
    for valor in rows.values_list(campo, flat=True):
        if valor in (None, ""):
            continue
        total += valor
        encontrou = True
    return total if encontrou else 0


def obter_valor_preferido(obj, campo):
    valor = getattr(obj, campo, None)
    return valor if valor not in (None, "") else 0


def valor_limpeza_diaria(tanque, snapshot, categoria):
    campos = {
        "mecanizada": ("limpeza_mecanizada_diaria", "percentual_limpeza_diario"),
        "fina": ("limpeza_fina_diaria", "percentual_limpeza_fina_diario"),
    }
    for campo in campos[categoria]:
        valor = getattr(tanque, campo, None)
        if valor not in (None, ""):
            return valor
    return snapshot.get("daily", {}).get(categoria, 0)


def valor_limpeza_acumulada(tanque, snapshot, categoria):
    campos = {
        "mecanizada": ("limpeza_mecanizada_cumulativa", "percentual_limpeza_cumulativo"),
        "fina": ("limpeza_fina_cumulativa", "percentual_limpeza_fina_cumulativo"),
    }
    for campo in campos[categoria]:
        valor = getattr(tanque, campo, None)
        if valor not in (None, ""):
            return valor
    return snapshot.get("cumulative", {}).get(categoria, 0)


def montar_linhas_compartimentos(snapshot):
    linhas = []
    for row in snapshot.get("rows", []):
        indice = row.get("index")
        mecanizada = float((row.get("mecanizada") or {}).get("final") or 0)
        fina = float((row.get("fina") or {}).get("final") or 0)
        avanco = round((mecanizada * 0.85) + (fina * 0.15), 1)
        linhas.append(
            f"- Compartimento {indice}: avanco {formatar_percentual(avanco)} "
            f"(mecanizada {formatar_percentual(mecanizada)}; fina {formatar_percentual(fina)})."
        )
    return linhas


def possui_acesso_confinado(rdo):
    return any(
        getattr(rdo, campo, None)
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
        )
    )


def ultimo_tanque_do_rdo(rdo):
    return (
        RdoTanque.objects
        .filter(rdo=rdo)
        .order_by("-pk")
        .first()
    )


def comparar_campo(mudancas, rotulo, valor_a, valor_b, percentual=False):
    if normalizar_valor_comparacao(valor_a) == normalizar_valor_comparacao(valor_b):
        return
    if percentual:
        mudancas.append(
            f"{rotulo}: {formatar_percentual(valor_a)} para {formatar_percentual(valor_b)}."
        )
        return
    mudancas.append(f"{rotulo}: {formatar_valor(valor_a)} para {formatar_valor(valor_b)}.")


def normalizar_valor_comparacao(valor):
    if valor in (None, ""):
        return None
    return str(valor)


def formatar_valor(valor):
    if valor in (None, ""):
        return "nao informado"
    return str(valor)


def formatar_data(valor):
    try:
        return valor.strftime("%d/%m/%Y")
    except Exception:
        return str(valor or "data nao informada")


def contar_por_status(linhas):
    contagem = {}
    for status in linhas.values_list("status_operacao", flat=True):
        chave = status or "Nao informado"
        contagem[chave] = contagem.get(chave, 0) + 1
    return contagem


def ordem_prioridade_texto(prioridade):
    return {
        "critica": 0,
        "alta": 1,
        "media": 2,
        "baixa": 3,
    }.get(prioridade, 4)


def rotular_prioridade(prioridade):
    return {
        "critica": "Critica",
        "alta": "Alta",
        "media": "Media",
        "baixa": "Baixa",
    }.get(prioridade, str(prioridade or "Nao informada"))


def montar_top_prioridades(limit=2):
    itens = []
    for alerta in (
        AlertaOperacionalInteligente.objects
        .filter(status="pendente")
        .select_related("ordem_servico")
    ):
        itens.append(
            (
                ordem_prioridade_texto(alerta.prioridade),
                f"{alerta.identificacao_operacional} - {alerta.get_tipo_display()}",
            )
        )
    for alerta in (
        AlertaInteligente.objects
        .filter(status="pendente")
        .select_related("rdo", "rdo__ordem_servico")
    ):
        itens.append(
            (
                ordem_prioridade_texto(alerta.prioridade),
                f"{alerta.identificacao_operacional} - {alerta.get_tipo_display()}",
            )
        )
    itens.sort(key=lambda item: (item[0], item[1]))
    return [texto for _, texto in itens[:limit]]


def formatar_numero(valor):
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        numero = 0
    if numero.is_integer():
        return str(int(numero))
    return f"{numero:.2f}".rstrip("0").rstrip(".")


def formatar_percentual(valor):
    return f"{formatar_numero(valor)}%"


def normalizar_identificador_tanque(valor):
    return re.sub(r"[^a-z0-9]+", "", unidecode(normalizar(valor)))


def formatar_descricao_filtros(filtros):
    if not filtros:
        return "os filtros informados"
    if len(filtros) == 1:
        return filtros[0]
    return ", ".join(filtros[:-1]) + " e " + filtros[-1]


def normalizar_identificador_supervisor(valor):
    return re.sub(r"[^a-z0-9]+", "", unidecode(normalizar(valor)))
