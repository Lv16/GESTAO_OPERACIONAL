from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required(login_url='/login/')
def ajuda(request):
    return render(request, 'ajuda.html')

@login_required(login_url='/login/')
def relatorio_diario_operacao(request):
    return render(request, 'rdo.html')