from django import template
from GO.models import Pessoa, Funcao

register = template.Library()

@register.simple_tag
def get_pessoas():
    try:
        return Pessoa.objects.all()
    except Exception:
        return []

@register.simple_tag
def get_funcoes():
    try:
        return Funcao.objects.all()
    except Exception:
        return []