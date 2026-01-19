from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        lookup = username if username is not None else kwargs.get('email')

        if lookup is None:
            return None

        user = None
        try:
            if '@' in str(lookup):
                user = UserModel.objects.filter(email__iexact=lookup).first()
        except Exception:
            user = None

        if user is None:
            try:
                user = UserModel.objects.filter(username__iexact=lookup).first()
            except Exception:
                user = None

        if user is None:
            return None

        try:
            is_supervisor = user.groups.filter(name='Supervisor').exists()
        except Exception:
            is_supervisor = False

        if not is_supervisor:
            try:
                if str(lookup).lower() != (user.email or '').lower():
                    return None
            except Exception:
                return None

        try:
            if user.check_password(password) and self.user_can_authenticate(user):
                return user
        except Exception:
            return None

        return None