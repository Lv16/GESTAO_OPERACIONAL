from django.shortcuts import redirect
from django.urls import reverse

class SupervisorForceRdoMiddleware:
    """Middleware simples que força usuários do grupo 'Supervisor' a acessar apenas
    a página RDO. Se o usuário estiver no grupo, qualquer requisição que não seja
    para a rota RDO ou para arquivos estáticos/media será redirecionada para
    '/rdo/?mobile=1'.

    Observações:
    - Este middleware é intencionalmente restritivo conforme solicitado.
    - Em ambientes reais, ajustes finos podem ser necessários (ex.: permitir /logout/,
      /admin/ para determinados usuários etc.).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            user = getattr(request, 'user', None)
            if user and user.is_authenticated:
                # verificar se pertence ao grupo Supervisor
                try:
                    is_sup = user.groups.filter(name='Supervisor').exists()
                except Exception:
                    is_sup = False

                if is_sup:
                    path = request.path or ''
                    # permitir acesso a /rdo/ (tanto /rdo como /rdo/), static, media, logout, admin
                    allowed_prefixes = ['/static/', '/media/', '/admin/', '/logout', '/api/']
                    # Se já estiver acessando /rdo (com ou sem querystring), permitir normalmente.
                    if path.startswith(tuple(allowed_prefixes)) or path.startswith(reverse('rdo')) or path == reverse('rdo'):
                        return self.get_response(request)
                    else:
                        # redirecionar qualquer outra rota para RDO (sem forçar flag em sessão).
                        url = reverse('rdo')
                        return redirect(url)
        except Exception:
            # falha segura: apenas prossiga
            pass

        return self.get_response(request)
