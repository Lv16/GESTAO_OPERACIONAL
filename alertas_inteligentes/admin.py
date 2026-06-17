from django.contrib import admin

from .models import (
    AlertaInteligente,
    ExemploIntencaoIA,
    PerguntaAssistenteIA,
)
from .services.aprendizado_ia import aprovar_pergunta_como_exemplo


@admin.register(AlertaInteligente)
class AlertaInteligenteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "rdo",
        "tipo",
        "prioridade",
        "equipe_responsavel",
        "status",
        "criado_em",
    )
    list_filter = (
        "tipo",
        "prioridade",
        "equipe_responsavel",
        "status",
        "criado_em",
    )
    search_fields = ("mensagem", "rdo__id")
    readonly_fields = ("criado_em", "resolvido_em")


@admin.register(ExemploIntencaoIA)
class ExemploIntencaoIAAdmin(admin.ModelAdmin):
    list_display = ("id", "intencao", "ativo", "criado_por", "atualizado_em")
    list_filter = ("intencao", "ativo", "atualizado_em")
    search_fields = ("frase", "frase_normalizada")
    readonly_fields = ("frase_normalizada", "criado_em", "atualizado_em")


@admin.register(PerguntaAssistenteIA)
class PerguntaAssistenteIAAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "status",
        "intencao_detectada",
        "criada_em",
        "revisada_por",
    )
    list_filter = ("status", "intencao_detectada", "criada_em", "revisada_em")
    search_fields = ("pergunta", "pergunta_normalizada")
    readonly_fields = (
        "pergunta",
        "pergunta_normalizada",
        "contexto",
        "criada_em",
        "revisada_em",
        "exemplo_aprovado",
    )
    actions = ["aprovar_como_exemplo"]

    @admin.action(description="Aprovar perguntas selecionadas como exemplo da intencao detectada")
    def aprovar_como_exemplo(self, request, queryset):
        aprovadas = 0
        for pergunta in queryset.exclude(intencao_detectada__isnull=True).exclude(intencao_detectada=""):
            aprovar_pergunta_como_exemplo(
                pergunta,
                pergunta.intencao_detectada,
                usuario=request.user,
            )
            aprovadas += 1
        self.message_user(request, f"{aprovadas} pergunta(s) aprovada(s) como exemplo.")
