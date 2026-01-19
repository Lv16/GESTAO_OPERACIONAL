from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from .models import Tanque, Unidade
from decimal import Decimal
from django.db.models import Q

@login_required
def cadastrar_tanque(request):
    if request.method == 'POST':
        try:
            codigo = request.POST.get('codigo')
            nome = request.POST.get('nome')
            tipo = request.POST.get('tipo')
            volume = request.POST.get('volume')
            unidade_id = request.POST.get('unidade')
            
            numero_compartimentos = request.POST.get('numero_compartimentos')
            gavetas = request.POST.get('gavetas')
            patamares = request.POST.get('patamares')
            
            if not all([codigo, nome, tipo, volume, unidade_id]):
                raise ValidationError("Todos os campos obrigatórios devem ser preenchidos.")
            
            try:
                volume = Decimal(volume.replace(',', '.'))
            except:
                raise ValidationError("Volume inválido")
                
            unidade = get_object_or_404(Unidade, id=unidade_id)
            
            tanque = Tanque(
                codigo=codigo,
                nome=nome,
                tipo=tipo,
                volume=volume,
                unidade=unidade
            )
            
            if tipo == 'Compartimento':
                if numero_compartimentos:
                    tanque.numero_compartimentos = int(numero_compartimentos)
                if gavetas:
                    tanque.gavetas = int(gavetas)
                if patamares:
                    tanque.patamares = int(patamares)
            
            tanque.save()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'id': tanque.id})
            return redirect('lista_tanques')
            
        except ValidationError as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': str(e)})
            unidades = Unidade.objects.all()
            return render(request, 'cadastrar_tanque.html', {
                'error': str(e),
                'unidades': unidades
            })
    
    unidades = Unidade.objects.all()
    return render(request, 'cadastrar_tanque.html', {'unidades': unidades})

@login_required
def lista_tanques(request):
    tanques = Tanque.objects.all().order_by('codigo')
    return render(request, 'lista_tanques.html', {'tanques': tanques})

@login_required
def api_buscar_tanques(request):
    q = request.GET.get('q', '').strip()
    unidade_id = request.GET.get('unidade')
    
    tanques = Tanque.objects.all()
    
    if q:
        tanques = tanques.filter(Q(codigo__icontains=q) | Q(nome__icontains=q))
    
    if unidade_id:
        tanques = tanques.filter(unidade_id=unidade_id)
    
    results = [{'id': t.id, 'text': f"{t.codigo} - {t.nome}"} for t in tanques[:10]]
    return JsonResponse({'results': results})

@login_required
def api_detalhe_tanque(request):
    tid = request.GET.get('id') or request.GET.get('tanque_id')
    if not tid:
        return JsonResponse({'success': False, 'error': 'Parâmetro id é obrigatório.'}, status=400)
    try:
        tanque = get_object_or_404(Tanque, id=int(str(tid).strip()))
    except Exception:
        return JsonResponse({'success': False, 'error': 'ID inválido.'}, status=400)

    data = {
        'success': True,
        'id': tanque.id,
        'codigo': tanque.codigo,
        'nome': tanque.nome,
        'tipo': getattr(tanque, 'tipo', None),
        'volume': str(getattr(tanque, 'volume', '')) if getattr(tanque, 'volume', None) is not None else None,
        'numero_compartimentos': getattr(tanque, 'numero_compartimentos', None),
        'gavetas': getattr(tanque, 'gavetas', None),
        'patamares': getattr(tanque, 'patamares', None),
        'unidade_id': getattr(tanque, 'unidade_id', None),
    }
    return JsonResponse(data)