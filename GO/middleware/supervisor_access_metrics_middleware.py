from ..supervisor_access_metrics import record_supervisor_access


class SupervisorAccessMetricsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        try:
            if request.method in {'HEAD', 'OPTIONS'}:
                return response

            user = getattr(request, 'user', None)
            path = str(getattr(request, 'path', '') or '')
            if not path or path.startswith(
                (
                    '/static/',
                    '/media/',
                    '/fotos_rdo/',
                    '/admin/',
                    '/api/mobile/',
                )
            ):
                return response

            session_key = ''
            try:
                session_key = str(getattr(getattr(request, 'session', None), 'session_key', '') or '')
            except Exception:
                session_key = ''

            record_supervisor_access(
                user=user,
                channel='web',
                path=path,
                session_key=session_key,
            )
        except Exception:
            pass

        return response
