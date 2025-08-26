from django.http import JsonResponse
from django.shortcuts import render, redirect
from .models import OrdemServico
from .forms import OrdemServicoForm
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q


def lista_servicos(request):
    if request.method == 'POST':
        form = OrdemServicoForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                form.save()
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': True, 'message': 'OS criada com sucesso!'})
                return redirect('home')
            except Exception as e:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'errors': {'__all__': [f'Erro ao salvar no banco de dados: {str(e)}']}}, status=400)
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                errors = {}
                for field, field_errors in form.errors.items():
                    errors[field] = [str(error) for error in field_errors]
                return JsonResponse({'success': False, 'errors': errors}, status=400)

    else:
        form = OrdemServicoForm()

    
    numero_os = request.GET.get('numero_os', '')
    tag = request.GET.get('tag', '')
    codigo_os = request.GET.get('codigo_os', '')
    cliente = request.GET.get('cliente', '')
    unidade = request.GET.get('unidade', '')
    solicitante = request.GET.get('solicitante', '')
    
  
    servicos_list = OrdemServico.objects.all().order_by('-pk')
    
    
    if numero_os:
        servicos_list = servicos_list.filter(numero_os__icontains=numero_os)
    if tag:
        servicos_list = servicos_list.filter(tag__icontains=tag)
    if codigo_os:
        servicos_list = servicos_list.filter(codigo_os__icontains=codigo_os)
    if cliente:
        servicos_list = servicos_list.filter(cliente__icontains=cliente)
    if unidade:
        servicos_list = servicos_list.filter(unidade__icontains=unidade)
    if solicitante:
        servicos_list = servicos_list.filter(solicitante__icontains=solicitante)
    
    
    paginator = Paginator(servicos_list, 6)
    page = request.GET.get('page')
    
    try:
        servicos = paginator.page(page)
    except PageNotAnInteger:
       
        servicos = paginator.page(1)
    except EmptyPage:
    
        servicos = paginator.page(paginator.num_pages)
    
    return render(request, 'home.html', {
        'servicos': servicos,
        'form': form,
        'paginator': paginator
    })

def detalhes_os(request, os_id):
    try:
        os_instance = OrdemServico.objects.get(pk=os_id)
        data = {
            'id': os_instance.pk,
            'numero_os': os_instance.numero_os,
            'tag': os_instance.tag,
            'codigo_os': os_instance.codigo_os,
            'data_inicio': os_instance.data_inicio.strftime('%d/%m/%Y') if os_instance.data_inicio else '',
            'data_fim': os_instance.data_fim.strftime('%d/%m/%Y') if os_instance.data_fim else '',
            'dias_de_operacao': os_instance.dias_de_operacao,
            'cliente': os_instance.cliente,
            'unidade': os_instance.unidade,
            'solicitante': os_instance.solicitante,
            'tipo_operacao': os_instance.tipo_operacao,
            'servico': os_instance.servico,
            'metodo': os_instance.metodo,
            'tanque': os_instance.tanque,
            'volume_tanque': str(os_instance.volume_tanque),
            'especificacao': os_instance.especificacao,
            'pob': os_instance.pob,
            'coordenador': os_instance.coordenador,
            'supervisor': os_instance.supervisor,
            'status_operacao': os_instance.status_operacao,
            'observacao': os_instance.observacao,
        }
        return JsonResponse(data)
    except OrdemServico.DoesNotExist:
        return JsonResponse({'error': 'Ordem de Serviço não encontrada.'}, status=404)

def get_os_id_by_number(request, numero_os):
    try:
        os_instance = OrdemServico.objects.get(numero_os=numero_os)
        return JsonResponse({'id': os_instance.pk})
    except OrdemServico.DoesNotExist:
        return JsonResponse({'error': 'Ordem de Serviço não encontrada.'}, status=404)
    except ValueError:
        return JsonResponse({'error': 'Número de OS inválido.'}, status=400)

def home(request):
    if request.method == 'POST':
        form = OrdemServicoForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('home')
    else:
        form = OrdemServicoForm()
    
    servicos = OrdemServico.objects.all().order_by('-id')
    return render(request, 'home.html', {'form': form, 'servicos': servicos})

