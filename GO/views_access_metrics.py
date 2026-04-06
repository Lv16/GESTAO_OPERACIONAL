from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render

from .rdo_access import user_can_manage_rdo_permission_users
from .supervisor_access_metrics import build_supervisor_access_dashboard_context


@login_required(login_url='/login/')
def supervisor_access_dashboard(request):
    if not user_can_manage_rdo_permission_users(getattr(request, 'user', None)):
        return HttpResponseForbidden('Sem permissao para visualizar metricas de acesso.')

    context = build_supervisor_access_dashboard_context(request)
    return render(request, 'supervisor_access_dashboard.html', context)
