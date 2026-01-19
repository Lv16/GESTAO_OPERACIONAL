from django.shortcuts import redirect
from django.urls import reverse

class SupervisorForceRdoMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            user = getattr(request, 'user', None)
            if user and user.is_authenticated:
                try:
                    is_sup = user.groups.filter(name='Supervisor').exists()
                except Exception:
                    is_sup = False

                if is_sup:
                    path = request.path or ''
                    allowed_prefixes = ['/static/', '/media/', '/fotos_rdo/', '/admin/', '/logout', '/api/']
                    if path.startswith(tuple(allowed_prefixes)) or path.startswith(reverse('rdo')) or path == reverse('rdo'):
                        return self.get_response(request)
                    else:
                        url = reverse('rdo')
                        return redirect(url)
        except Exception:
            pass

        return self.get_response(request)