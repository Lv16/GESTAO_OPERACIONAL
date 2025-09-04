from django.shortcuts import render
from django.views.decorators.csrf import csrf_protect

# Cadastrar novo usuário
@csrf_protect
def cadastrar_usuario(request):
    if request.method == 'POST':
        from django.contrib.auth.models import User
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        if username and email and password:
            if not User.objects.filter(username=username).exists():
                User.objects.create_user(username=username, email=email, password=password)
                return render(request, 'cadastrar_usuario.html', {'success': True})
            else:
                return render(request, 'cadastrar_usuario.html', {'error': 'Usuário já existe.'})
        else:
            return render(request, 'cadastrar_usuario.html', {'error': 'Preencha todos os campos.'})
    return render(request, 'cadastrar_usuario.html')
# Cadastrar um novo cliente
@csrf_protect
def cadastrar_cliente(request):
    if request.method == 'POST':
        from .models import Cliente
        nome = request.POST.get('nome')
        if nome:
            if not Cliente.objects.filter(nome=nome).exists():
                Cliente.objects.create(nome=nome)
                return render(request, 'cadastrar_cliente.html', {'success': True})
            else:
                return render(request, 'cadastrar_cliente.html', {'error': 'Cliente já existe.'})
        else:
            return render(request, 'cadastrar_cliente.html', {'error': 'Preencha o nome do cliente.'})
    return render(request, 'cadastrar_cliente.html')
# Cadastrar uma nova unidade
@csrf_protect
def cadastrar_unidade(request):
    if request.method == 'POST':
        from .models import Unidade
        nome = request.POST.get('nome')
        if nome:
            if not Unidade.objects.filter(nome=nome).exists():
                Unidade.objects.create(nome=nome)
                return render(request, 'cadastrar_unidade.html', {'success': True})
            else:
                return render(request, 'cadastrar_unidade.html', {'error': 'Unidade já existe.'})
        else:
            return render(request, 'cadastrar_unidade.html', {'error': 'Preencha o nome da unidade.'})
    return render(request, 'cadastrar_unidade.html')
