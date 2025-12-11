from django import template
from GO.models import Pessoa, Funcao

register = template.Library()


@register.simple_tag
def get_pessoas():
    """Retorna queryset de pessoas para popular selects."""
    try:
        return Pessoa.objects.all()
    except Exception:
        return []


@register.simple_tag
def get_funcoes():
    """Retorna queryset de funcoes para popular selects."""
    try:
        return Funcao.objects.all()
    except Exception:
        return []
