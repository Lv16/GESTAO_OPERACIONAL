from django.shortcuts import render
from django.views.decorators.csrf import csrf_protect

@csrf_protect
def cadastrar_usuario(request):
    if request.method == 'POST':
        from django.contrib.auth.models import User
        from django.contrib.auth.models import Group
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        is_supervisor = request.POST.get('is_supervisor')
        if username and password and (is_supervisor or email):
            if not User.objects.filter(username=username).exists():
                user = User.objects.create_user(username=username, email=email or '', password=password)
                if is_supervisor:
                    group_name = 'Supervisor'
                    try:
                        grp, created = Group.objects.get_or_create(name=group_name)
                        user.groups.add(grp)
                    except Exception:
                        pass
                return render(request, 'cadastrar_usuario.html', {'success': True})
            else:
                return render(request, 'cadastrar_usuario.html', {'error': 'Usuário já existe.'})
        else:
            return render(request, 'cadastrar_usuario.html', {'error': 'Preencha todos os campos (email opcional para Supervisor). '})
    return render(request, 'cadastrar_usuario.html')
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

@csrf_protect
def cadastrar_pessoa(request):
    from .models import Pessoa, OrdemServico
    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        if not nome:
            return render(request, 'cadastrar_pessoas.html', {'error': 'Preencha o nome da pessoa.'})
        if Pessoa.objects.filter(nome__iexact=nome).exists():
            return render(request, 'cadastrar_pessoas.html', {'error': 'Pessoa já cadastrada.'})
        funcao_default = OrdemServico.FUNCOES[0][0] if getattr(OrdemServico, 'FUNCOES', None) else 'Ajudante'
        Pessoa.objects.create(nome=nome, funcao=funcao_default)
        return render(request, 'cadastrar_pessoas.html', {'success': True})

    return render(request, 'cadastrar_pessoas.html')

@csrf_protect
def cadastrar_funcao(request):
    from .models import Funcao
    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        if not nome:
            return render(request, 'cadastrar_funcao.html', {'error': 'Preencha o nome da função.'})
        if Funcao.objects.filter(nome__iexact=nome).exists():
            return render(request, 'cadastrar_funcao.html', {'error': 'Função já cadastrada.'})
        Funcao.objects.create(nome=nome)
        return render(request, 'cadastrar_funcao.html', {'success': True})
    return render(request, 'cadastrar_funcao.html')