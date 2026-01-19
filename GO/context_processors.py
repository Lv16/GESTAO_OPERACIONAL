import re

MOBILE_UA_RE = re.compile(r"Mobile|Android|iPhone|iPad|iPod|Opera Mini|IEMobile|WPDesktop", re.I)

def mobile_detector(request):
    try:
        q = request.GET.get('force_mobile') or request.POST.get('force_mobile')
        if q in ('1', 'true', 'yes'):
            return {'force_mobile': True}

        ua = ''
        try:
            ua = request.META.get('HTTP_USER_AGENT','') or ''
        except Exception:
            ua = ''

        if ua and MOBILE_UA_RE.search(ua):
            return {'force_mobile': True}
    except Exception:
        pass
    return {'force_mobile': False}