from collections import defaultdict
from decimal import Decimal, InvalidOperation
import json
import re

from django.db import models

from GO.models import OrdemServico, RDO, RdoTanque
from alertas_inteligentes.services import extractors
from alertas_inteligentes.services.field_utils import get_field_safe


def normalizar(texto):
    return str(texto or "").strip().lower()


def get_field(obj, *names, default=None):
    return get_field_safe(obj, *names, default=default)


def to_decimal(valor):
    if valor in [None, ""]:
        return Decimal("0")

    try:
        return Decimal(str(valor).replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def extrair_numero_os(texto):
    texto = normalizar(texto)
    match = re.search(r"os\s*0*(\d+)", texto)
    if match:
        return match.group(1)
    return None


def extrair_tanque(texto):
    return extractors.extrair_tanque(texto)


def normalizar_tanque_valor(valor):
    return str(valor or "").strip().upper()


def _bool_verdadeiro(valor):
    if isinstance(valor, bool):
        return valor
    if valor in (None, ""):
        return False
    texto = normalizar(valor)
    return texto in {"1", "true", "t", "sim", "s", "yes", "y"}


def obter_chave_tanque(tanque_obj):
    return (
        normalizar_tanque_valor(get_field(tanque_obj, "tanque_codigo", default=None))
        or normalizar_tanque_valor(get_field(tanque_obj, "nome_tanque", default=None))
        or f"TANQUE_{getattr(tanque_obj, 'id', 'SEM_ID')}"
    )


def obter_rotulo_tanque(tanque_obj):
    return (
        str(get_field(tanque_obj, "nome_tanque", default=None) or "").strip()
        or str(get_field(tanque_obj, "tanque_codigo", default=None) or "").strip()
        or obter_chave_tanque(tanque_obj)
    )


def tanque_corresponde(tanque_obj, filtro_tanque):
    if not filtro_tanque:
        return True

    filtro = normalizar_tanque_valor(filtro_tanque)
    codigo = normalizar_tanque_valor(get_field(tanque_obj, "tanque_codigo", default=None))
    nome = normalizar_tanque_valor(get_field(tanque_obj, "nome_tanque", default=None))

    return filtro in codigo or filtro in nome


def buscar_rdos_os(numero_os, tanque=None):
    rdos = (
        RDO.objects.filter(ordem_servico__numero_os=numero_os)
        .select_related("ordem_servico")
        .prefetch_related("tanques")
        .order_by("data", "id")
    )

    if tanque:
        rdos = rdos.filter(
            models.Q(tanques__tanque_codigo__icontains=tanque)
            | models.Q(tanques__nome_tanque__icontains=tanque)
        ).distinct()

    return rdos


def calcular_deltas_compartimentos(tanque_atual, tanque_anterior=None):
    resultado = {}

    def parse_compartimentos(obj):
        raw = getattr(obj, "compartimentos_avanco_json", None)
        if not raw:
            return {}

        try:
            parsed = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except Exception:
            return {}

        normalizado = {}
        for key, val in parsed.items():
            try:
                mecanizada = to_decimal(val.get("mecanizada") or val.get("m") or 0)
            except Exception:
                mecanizada = Decimal("0")
            try:
                fina = to_decimal(val.get("fina") or val.get("f") or 0)
            except Exception:
                fina = Decimal("0")
            normalizado[str(key).upper()] = {
                "mecanizada": mecanizada,
                "fina": fina,
            }
        return normalizado

    atual_map = parse_compartimentos(tanque_atual)
    anterior_map = parse_compartimentos(tanque_anterior) if tanque_anterior else {}

    for chave in set(atual_map) | set(anterior_map):
        atual = atual_map.get(chave, {"mecanizada": Decimal("0"), "fina": Decimal("0")})
        anterior = anterior_map.get(chave, {"mecanizada": Decimal("0"), "fina": Decimal("0")})
        if tanque_anterior:
            resultado[chave] = {
                "mecanizada": atual["mecanizada"] - anterior["mecanizada"],
                "fina": atual["fina"] - anterior["fina"],
            }
        else:
            resultado[chave] = {
                "mecanizada": atual["mecanizada"],
                "fina": atual["fina"],
            }

    return resultado


def tanque_tem_movimentacao_operacional(tanque_obj, rdo=None):
    sinais_tanque = [
        to_decimal(getattr(tanque_obj, "tempo_bomba", 0)),
        to_decimal(getattr(tanque_obj, "ensacamento_dia", 0)),
        to_decimal(getattr(tanque_obj, "icamento_dia", 0)),
        to_decimal(getattr(tanque_obj, "cambagem_dia", 0)),
        to_decimal(getattr(tanque_obj, "limpeza_mecanizada_diaria", 0)),
        to_decimal(getattr(tanque_obj, "limpeza_fina_diaria", 0)),
    ]
    if any(valor > 0 for valor in sinais_tanque):
        return True

    if rdo is None:
        return False

    if _bool_verdadeiro(getattr(rdo, "houve_acesso_espaco_confinado", None)):
        return True

    entrada_saida = str(getattr(rdo, "entrada_saida_espaco_confinado", "") or "").strip()
    if entrada_saida:
        return True

    atividades = str(getattr(rdo, "atividades", "") or "").strip()
    return bool(atividades)


def calcular_deltas_rdo(rdo, tanques_anteriores=None, filtro_tanque=None):
    campos_cumulativos = {
        "ensacamento": "ensacamento_cumulativo",
        "cambagem": "cambagem_cumulativo",
        "icamento": "icamento_cumulativo",
        "avanco_percentual": "percentual_avanco_cumulativo",
    }
    resultado = {
        "ensacamento": Decimal("0"),
        "cambagem": Decimal("0"),
        "icamento": Decimal("0"),
        "tempo_bomba": Decimal("0"),
        "avanco_percentual": Decimal("0"),
        "avanco_tanques": {},
        "compartimentos": {},
    }

    tanques_atuais = [
        tanque for tanque in rdo.tanques.all()
        if tanque_corresponde(tanque, filtro_tanque)
    ]
    tanques_anteriores = tanques_anteriores or {}

    compartimentos_total = defaultdict(
        lambda: {
            "mecanizada": Decimal("0"),
            "fina": Decimal("0"),
        }
    )

    for tanque_atual in tanques_atuais:
        tanque_anterior = tanques_anteriores.get(obter_chave_tanque(tanque_atual))
        houve_movimentacao = tanque_tem_movimentacao_operacional(tanque_atual, rdo)

        for nome_logico, campo_model in campos_cumulativos.items():
            atual = to_decimal(getattr(tanque_atual, campo_model, 0))
            anterior = (
                to_decimal(getattr(tanque_anterior, campo_model, 0))
                if tanque_anterior
                else Decimal("0")
            )
            delta = atual - anterior if tanque_anterior else atual
            if delta < 0 and not houve_movimentacao:
                delta = Decimal("0")
            resultado[nome_logico] += delta
            if nome_logico == "avanco_percentual":
                resultado["avanco_tanques"][obter_rotulo_tanque(tanque_atual)] = (
                    resultado["avanco_tanques"].get(obter_rotulo_tanque(tanque_atual), Decimal("0")) + delta
                )

        resultado["tempo_bomba"] += to_decimal(getattr(tanque_atual, "tempo_bomba", 0))

        for compartimento, delta in calcular_deltas_compartimentos(tanque_atual, tanque_anterior).items():
            mecanizada = Decimal(delta.get("mecanizada", 0) or 0)
            fina = Decimal(delta.get("fina", 0) or 0)
            if not houve_movimentacao and mecanizada < 0:
                mecanizada = Decimal("0")
            if not houve_movimentacao and fina < 0:
                fina = Decimal("0")
            compartimentos_total[compartimento]["mecanizada"] += mecanizada
            compartimentos_total[compartimento]["fina"] += fina

    resultado["compartimentos"] = dict(compartimentos_total)
    return resultado


def formatar_decimal(valor):
    valor = Decimal(valor)

    if valor == valor.to_integral():
        return str(int(valor))

    return str(round(valor, 2)).replace(".", ",")


def identificar_rdo(rdo):
    numero_rdo = get_field(rdo, "rdo", default=None)
    return str(numero_rdo).strip() or str(getattr(rdo, "id", ""))


def montar_texto_compartimento(nome_compartimento, dados):
    mecanizada = min(Decimal("100"), max(Decimal("0"), Decimal(dados.get("mecanizada", 0) or 0)))
    fina = min(Decimal("100"), max(Decimal("0"), Decimal(dados.get("fina", 0) or 0)))

    if mecanizada <= 0 and fina <= 0:
        return None

    if mecanizada > fina:
        destaque = "mecanizada"
    elif fina > mecanizada:
        destaque = "fina"
    else:
        destaque = "mecanizada e fina"

    return (
        f"  - {nome_compartimento}: "
        f"{formatar_decimal(mecanizada)}% de limpeza mecanizada e "
        f"{formatar_decimal(fina)}% de limpeza fina. "
        f"Maior avanco em {destaque}."
    )


def formatar_percentual_supervisor_tanque(valor):
    percentual = min(Decimal("100"), max(Decimal("0"), Decimal(valor or 0)))
    return f"{formatar_decimal(percentual)}%"


def montar_resposta_supervisores_os(numero_os, tanque, resumo, rdos):
    escopo = f" no tanque {tanque}" if tanque else ""
    linhas = [
        f"Analisei a OS {numero_os}{escopo} com base nos RDOs lancados.",
        "",
        f"Total de RDOs analisados: {len(rdos)}",
        f"Supervisores identificados: {len(resumo)}",
        "",
        "Resumo por supervisor:",
    ]

    for supervisor, dados in resumo.items():
        linhas.append("")
        linhas.append(f"Supervisor: {supervisor}")
        linhas.append(f"- RDOs lancados/acompanhados: {dados['rdos']}")

        if dados["data_inicio"] and dados["data_fim"]:
            linhas.append(
                f"- Periodo identificado: {dados['data_inicio'].strftime('%d/%m/%Y')} ate {dados['data_fim'].strftime('%d/%m/%Y')}"
            )

        linhas.append(f"- Ensacamento atribuido: {formatar_decimal(dados['ensacamento'])}")
        linhas.append(f"- Icamento atribuido: {formatar_decimal(dados['icamento'])}")
        linhas.append(f"- Cambagem atribuida: {formatar_decimal(dados['cambagem'])}")
        linhas.append(f"- Tempo de bomba atribuido: {formatar_decimal(dados['tempo_bomba'])}")
        avanco_tanques = dict(dados.get("avanco_tanques") or {})
        if tanque or len(avanco_tanques) <= 1:
            linhas.append(f"- Avanco percentual atribuido: {formatar_decimal(dados['avanco_percentual'])}%")
        elif avanco_tanques:
            linhas.append("- Avanco percentual por tanque:")
            for nome_tanque, valor_tanque in sorted(avanco_tanques.items()):
                linhas.append(
                    f"  - {nome_tanque}: {formatar_percentual_supervisor_tanque(valor_tanque)}"
                )

        if dados["compartimentos"]:
            linhas.append("- Avanco por compartimento:")
            for compartimento, valores in dados["compartimentos"].items():
                texto_compartimento = montar_texto_compartimento(compartimento, valores)
                if texto_compartimento:
                    linhas.append(texto_compartimento)

        if dados["observacoes"]:
            linhas.append("- Observacoes:")
            for obs in dados["observacoes"][:3]:
                linhas.append(f"  - {obs}")

    linhas.append("")
    linhas.append(
        "Observacao: como o Synchro nao separa os acumulados por supervisor originalmente, "
        "a IA atribuiu os avancos calculando a diferenca entre RDOs consecutivos e vinculando o delta ao supervisor do RDO atual."
    )

    return {
        "introducao": "\n".join(linhas),
        "alertas": [],
        "alertas_operacionais": [],
        "recomendacao": (
            "Use essa analise como apoio operacional. Caso algum acumulado tenha sido corrigido manualmente no RDO, "
            "valide as observacoes destacadas pela IA."
        ),
        "confianca": "media",
        "fontes": ["RDOs", "RdoTanque", "Home Operacional", "Calculo por diferenca entre acumulados"],
    }


def analisar_supervisores_por_os(numero_os, tanque=None):
    rdos = list(buscar_rdos_os(numero_os, tanque))

    if not rdos:
        escopo = f" no tanque {tanque}" if tanque else ""
        return {
            "introducao": f"Nao encontrei RDOs da OS {numero_os}{escopo}.",
            "alertas": [],
            "alertas_operacionais": [],
            "recomendacao": "Verifique se o numero da OS e o tanque foram informados corretamente.",
            "confianca": "alta",
            "fontes": ["RDOs", "Home Operacional"],
        }

    resumo = defaultdict(
        lambda: {
            "rdos": 0,
            "data_inicio": None,
            "data_fim": None,
            "ensacamento": Decimal("0"),
            "cambagem": Decimal("0"),
            "icamento": Decimal("0"),
            "tempo_bomba": Decimal("0"),
            "avanco_percentual": Decimal("0"),
            "avanco_tanques": defaultdict(Decimal),
            "compartimentos": defaultdict(
                lambda: {
                    "mecanizada": Decimal("0"),
                    "fina": Decimal("0"),
                }
            ),
            "observacoes": [],
        }
    )

    ultimos_tanques_por_chave = {}

    for rdo in rdos:
        supervisor = (
            get_field(rdo, "supervisor", default=None)
            or get_field(rdo.ordem_servico, "supervisor", "supervisor_responsavel", default=None)
            or "Nao informado"
        )
        supervisor = str(supervisor).strip()
        data_rdo = get_field(rdo, "data", "data_rdo", "data_operacao", default=None)

        dados = resumo[supervisor]
        dados["rdos"] += 1

        if data_rdo:
            if not dados["data_inicio"] or data_rdo < dados["data_inicio"]:
                dados["data_inicio"] = data_rdo
            if not dados["data_fim"] or data_rdo > dados["data_fim"]:
                dados["data_fim"] = data_rdo

        deltas = calcular_deltas_rdo(
            rdo,
            tanques_anteriores=ultimos_tanques_por_chave,
            filtro_tanque=tanque,
        )

        for campo in ["ensacamento", "cambagem", "icamento", "tempo_bomba", "avanco_percentual"]:
            valor = deltas.get(campo, Decimal("0"))
            if valor < 0:
                dados["observacoes"].append(
                    f"O campo {campo} apresentou reducao no RDO {identificar_rdo(rdo)}. Pode indicar correcao ou reset."
                )
                continue
            dados[campo] += valor

        for nome_tanque, delta_tanque in deltas.get("avanco_tanques", {}).items():
            if delta_tanque < 0:
                dados["observacoes"].append(
                    f"O tanque {nome_tanque} apresentou reducao de avanco no RDO {identificar_rdo(rdo)}."
                )
                continue
            dados["avanco_tanques"][nome_tanque] += delta_tanque

        for compartimento, delta in deltas.get("compartimentos", {}).items():
            mecanizada = Decimal(delta.get("mecanizada", 0) or 0)
            fina = Decimal(delta.get("fina", 0) or 0)

            if mecanizada < 0:
                dados["observacoes"].append(
                    f"O compartimento {compartimento} apresentou reducao de limpeza mecanizada no RDO {identificar_rdo(rdo)}."
                )
            else:
                dados["compartimentos"][compartimento]["mecanizada"] += mecanizada

            if fina < 0:
                dados["observacoes"].append(
                    f"O compartimento {compartimento} apresentou reducao de limpeza fina no RDO {identificar_rdo(rdo)}."
                )
            else:
                dados["compartimentos"][compartimento]["fina"] += fina

        for tanque_atual in rdo.tanques.all():
            if tanque_corresponde(tanque_atual, tanque):
                ultimos_tanques_por_chave[obter_chave_tanque(tanque_atual)] = tanque_atual

    return montar_resposta_supervisores_os(numero_os, tanque, resumo, rdos)


def buscar_os_por_tanque(tanque):
    """Retorna lista de OSs que possuem RDOs com o tanque informado.

    Cada item: { 'numero_os': int, 'ordem_servico_id': int, 'rdos_count': int, 'ultima_data': date }
    """
    if not tanque:
        return []

    qs = RdoTanque.objects.filter(
        models.Q(tanque_codigo__icontains=tanque) | models.Q(nome_tanque__icontains=tanque)
    ).select_related('rdo', 'rdo__ordem_servico').order_by('-rdo__data')

    agrup = {}
    for item in qs:
        try:
            rdo = getattr(item, 'rdo', None)
            ordem = getattr(rdo, 'ordem_servico', None)
            if ordem is None:
                continue
            numero = getattr(ordem, 'numero_os', None)
            if numero is None:
                continue
            key = int(numero)
        except Exception:
            continue

        entry = agrup.get(key)
        if entry is None:
            agrup[key] = {
                'numero_os': key,
                'ordem_servico_id': getattr(ordem, 'id', None),
                'rdos_count': 0,
                'ultima_data': None,
            }
            entry = agrup[key]

        entry['rdos_count'] += 1
        data_rdo = getattr(getattr(item, 'rdo', None), 'data', None)
        if data_rdo and (entry['ultima_data'] is None or data_rdo > entry['ultima_data']):
            entry['ultima_data'] = data_rdo

    resultados = sorted(agrup.values(), key=lambda x: (x['ultima_data'] is not None, x['ultima_data']), reverse=True)
    return resultados
