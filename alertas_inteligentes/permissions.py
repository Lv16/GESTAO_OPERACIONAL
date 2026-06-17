from django.contrib import messages
from django.shortcuts import redirect

from GO.rdo_access import user_can_manage_rdo_permission_users


def usuario_pode_usar_ia_rdo(user):
    return user_can_manage_rdo_permission_users(user)


def permissao_ia_rdo_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not usuario_pode_usar_ia_rdo(request.user):
            messages.error(
                request,
                "Voce nao possui permissao para acessar o Assistente Inteligente de RDO.",
            )
            return redirect("home")

        return view_func(request, *args, **kwargs)

    return wrapper


def superuser_ia_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not getattr(request.user, "is_superuser", False):
            messages.error(
                request,
                "Apenas administradores podem acessar a supervisao de aprendizado da IA.",
            )
            return redirect("home")

        return view_func(request, *args, **kwargs)

    return wrapper
