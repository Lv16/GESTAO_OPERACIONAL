from django.shortcuts import render
from django.views.decorators.csrf import csrf_protect

# View para cadastrar um novo usuário
@csrf_protect
def cadastrar_usuario(request):
    if request.method == 'POST':
        
        pass
    return render(request, 'cadastrar_usuario.html')
# View para cadastrar um novo cliente
@csrf_protect
def cadastrar_cliente(request):
    if request.method == 'POST':
        
        pass
    return render(request, 'cadastrar_cliente.html')
# View para cadastrar uma nova unidade
@csrf_protect
def cadastrar_unidade(request):
    if request.method == 'POST':
        
        pass
    return render(request, 'cadastrar_unidade.html')
