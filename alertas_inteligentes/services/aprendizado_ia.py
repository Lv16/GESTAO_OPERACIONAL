from difflib import SequenceMatcher

from django.utils import timezone
from unidecode import unidecode

from alertas_inteligentes.models import ExemploIntencaoIA, PerguntaAssistenteIA


LIMIAR_SIMILARIDADE_EXEMPLO = 0.88


def normalizar_frase(texto):
    texto = unidecode(str(texto or "").strip().lower())
    return " ".join(texto.split())


def registrar_pergunta(pergunta, contexto=None, intencao_detectada=None, entendida=False):
    return PerguntaAssistenteIA.objects.create(
        pergunta=pergunta,
        pergunta_normalizada=normalizar_frase(pergunta),
        contexto=contexto or {},
        intencao_detectada=intencao_detectada,
        status="entendida" if entendida else "nao_entendida",
    )


def buscar_intencao_aprendida(pergunta):
    normalizada = normalizar_frase(pergunta)
    if not normalizada:
        return None

    melhor = None
    melhor_score = 0
    for exemplo in ExemploIntencaoIA.objects.filter(ativo=True):
        score = SequenceMatcher(
            None,
            normalizada,
            exemplo.frase_normalizada,
        ).ratio()
        if score > melhor_score:
            melhor = exemplo
            melhor_score = score

    if melhor and melhor_score >= LIMIAR_SIMILARIDADE_EXEMPLO:
        return melhor.intencao
    return None


def aprovar_pergunta_como_exemplo(pergunta_obj, intencao, usuario=None):
    exemplo, _ = ExemploIntencaoIA.objects.get_or_create(
        frase_normalizada=pergunta_obj.pergunta_normalizada,
        defaults={
            "frase": pergunta_obj.pergunta,
            "intencao": intencao,
            "criado_por": usuario,
        },
    )
    if exemplo.intencao != intencao or not exemplo.ativo:
        exemplo.intencao = intencao
        exemplo.ativo = True
        if usuario and not exemplo.criado_por_id:
            exemplo.criado_por = usuario
        exemplo.save(update_fields=["intencao", "ativo", "criado_por", "atualizado_em"])

    pergunta_obj.status = "revisada"
    pergunta_obj.intencao_detectada = intencao
    pergunta_obj.revisada_por = usuario
    pergunta_obj.revisada_em = timezone.now()
    pergunta_obj.exemplo_aprovado = exemplo
    pergunta_obj.save(
        update_fields=[
            "status",
            "intencao_detectada",
            "revisada_por",
            "revisada_em",
            "exemplo_aprovado",
        ]
    )
    return exemplo
