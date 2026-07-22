import re
import os

from .rdo_access import user_can_manage_rdo_permission_users

MOBILE_UA_RE = re.compile(r"Mobile|Android|iPhone|iPad|iPod|Opera Mini|IEMobile|WPDesktop", re.I)

def mobile_detector(request):
    force_mobile = False
    try:
        q = request.GET.get('force_mobile') or request.POST.get('force_mobile')
        if q in ('1', 'true', 'yes'):
            force_mobile = True

        ua = ''
        try:
            ua = request.META.get('HTTP_USER_AGENT','') or ''
        except Exception:
            ua = ''

        if ua and MOBILE_UA_RE.search(ua):
            force_mobile = True
    except Exception:
        pass

    android_url = (os.environ.get('MOBILE_APP_ANDROID_URL') or '').strip()
    ios_url = (os.environ.get('MOBILE_APP_IOS_URL') or '').strip()
    enabled_flag = (os.environ.get('MOBILE_APP_DOWNLOAD_ENABLED') or '').strip().lower()
    enabled = enabled_flag in ('1', 'true', 'yes', 'on') or bool(android_url or ios_url)

    return {
        'force_mobile': force_mobile,
        'mobile_app_download_enabled': enabled,
        'mobile_app_android_url': android_url,
        'mobile_app_ios_url': ios_url,
    }


def rdo_permission_flags(request):
    user = getattr(request, 'user', None)
    return {
        'can_manage_rdo_permission_users': user_can_manage_rdo_permission_users(user),
    }
