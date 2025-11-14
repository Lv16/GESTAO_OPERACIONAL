from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group


# Login via e-mail
class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        # Se veio None, tentar obter via email
        lookup = username if username is not None else kwargs.get('email')

        if lookup is None:
            return None

        # Primeiro tentar localizar um usuário por email (caso lookup pareça um email)
        user = None
        try:
            if '@' in str(lookup):
                user = UserModel.objects.filter(email__iexact=lookup).first()
        except Exception:
            user = None

        # Se não encontramos por email, tentar localizar por username
        if user is None:
            try:
                user = UserModel.objects.filter(username__iexact=lookup).first()
            except Exception:
                user = None

        # Se ainda não encontrou, não autentica
        if user is None:
            return None

        # Se usuário pertence ao grupo Supervisor, aceitar login por USERNAME (já coberto)
        # Para demais, assegurar que o lookup usado inicie por email (para impedir login por username)
        try:
            is_supervisor = user.groups.filter(name='Supervisor').exists()
        except Exception:
            is_supervisor = False

        # Se não supervisor e o lookup não é o email do usuário, recusar
        if not is_supervisor:
            try:
                if str(lookup).lower() != (user.email or '').lower():
                    return None
            except Exception:
                return None

        # Verificar senha e permissões
        try:
            if user.check_password(password) and self.user_can_authenticate(user):
                return user
        except Exception:
            return None

        return None
