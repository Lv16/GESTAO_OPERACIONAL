from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from .models import OrdemServico
from .forms import OrdemServicoForm
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from datetime import datetime


def lista_servicos(request):
    if request.method == 'POST':
        form = OrdemServicoForm(request.POST, request.FILES)
        if form.is_valid():
            ordem_servico = form.save()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': f'OS {ordem_servico.numero_os} criada com sucesso!',
                    'redirect': '/'
                })
            return redirect('home')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                errors = {}
                for field, field_errors in form.errors.items():
                    errors[field] = [str(error) for error in field_errors]
                return JsonResponse({
                    'success': False,
                    'errors': errors
                }, status=400)
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
            'status_comercial': os_instance.status_comercial,
            'observacao': os_instance.observacao,
            'link_rdo': os_instance.link_rdo,
            'materiais_equipamentos': os_instance.materiais_equipamentos
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


def buscar_os(request, os_id):
    """Busca uma OS específica para edição"""
    try:
        os_instance = OrdemServico.objects.get(pk=os_id)
        data = {
            'success': True,
            'os': {
                'id': os_instance.pk,
                'numero_os': os_instance.numero_os,
                'codigo_os': os_instance.codigo_os,
                'cliente': os_instance.cliente,
                'unidade': os_instance.unidade,
                'solicitante': os_instance.solicitante,
                'servico': os_instance.servico,
                'tag': os_instance.tag,
                'metodo': os_instance.metodo,
                'tanque': os_instance.tanque,
                'volume_tanque': os_instance.volume_tanque,
                'especificacao': os_instance.especificacao,
                'tipo_operacao': os_instance.tipo_operacao,
                'status_operacao': os_instance.status_operacao,
                'status_comercial': os_instance.status_comercial,
                'data_inicio': os_instance.data_inicio.strftime('%Y-%m-%d') if os_instance.data_inicio else '',
                'data_fim': os_instance.data_fim.strftime('%Y-%m-%d') if os_instance.data_fim else '',
                'pob': os_instance.pob,
                'coordenador': os_instance.coordenador,
                'supervisor': os_instance.supervisor,
                'observacao': os_instance.observacao,
                'link_rdo': os_instance.link_rdo,
            }
        }
        return JsonResponse(data)
    except OrdemServico.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Ordem de Serviço não encontrada.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def editar_os(request, os_id=None):
    """Atualiza uma OS existente"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método não permitido'}, status=405)

    try:
        if os_id is None:
            os_id = request.POST.get('os_id')
            if not os_id:
                return JsonResponse({'success': False, 'error': 'ID da OS não fornecido'}, status=400)

        os_instance = OrdemServico.objects.get(pk=os_id)

        os_instance.cliente = request.POST.get('cliente', os_instance.cliente)
        os_instance.unidade = request.POST.get('unidade', os_instance.unidade)
        os_instance.solicitante = request.POST.get('solicitante', os_instance.solicitante)
        os_instance.servico = request.POST.get('servico', os_instance.servico)
        os_instance.tag = request.POST.get('tag', os_instance.tag)
        os_instance.metodo = request.POST.get('metodo', os_instance.metodo)
        os_instance.tanque = request.POST.get('tanque', os_instance.tanque)

        volume_tanque = request.POST.get('volume_tanque')
        if volume_tanque:
            try:
                from decimal import Decimal
                os_instance.volume_tanque = Decimal(volume_tanque)
            except ValueError:
                return JsonResponse({'success': False, 'error': 'Volume do tanque deve ser um número válido'}, status=400)

        os_instance.especificacao = request.POST.get('especificacao', os_instance.especificacao)
        os_instance.tipo_operacao = request.POST.get('tipo_operacao', os_instance.tipo_operacao)
        os_instance.status_operacao = request.POST.get('status_operacao', os_instance.status_operacao)
        os_instance.status_comercial = request.POST.get('status_comercial', os_instance.status_comercial)
        os_instance.observacao = request.POST.get('observacao', os_instance.observacao)

        data_inicio = request.POST.get('data_inicio')
        if data_inicio:
            try:
                os_instance.data_inicio = datetime.strptime(data_inicio, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({'success': False, 'error': 'Data de início inválida'}, status=400)

        data_fim = request.POST.get('data_fim')
        if data_fim:
            try:
                os_instance.data_fim = datetime.strptime(data_fim, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({'success': False, 'error': 'Data de fim inválida'}, status=400)

        pob = request.POST.get('pob')
        if pob:
            try:
                os_instance.pob = int(pob)
            except ValueError:
                return JsonResponse({'success': False, 'error': 'POB deve ser um número inteiro válido'}, status=400)

        os_instance.coordenador = request.POST.get('coordenador', os_instance.coordenador)
        os_instance.supervisor = request.POST.get('supervisor', os_instance.supervisor)
        os_instance.link_rdo = request.POST.get('link_rdo', os_instance.link_rdo)
        os_instance.materiais_equipamentos = request.POST.get('materiais_equipamentos', os_instance.materiais_equipamentos)

        os_instance.save()

        return JsonResponse({'success': True, 'message': 'OS atualizada com sucesso!'})

    except OrdemServico.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Ordem de Serviço não encontrada'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Erro ao atualizar OS: {str(e)}'}, status=500)


@login_required(login_url='/login/')
def home(request):
    if request.method == 'POST':
        form = OrdemServicoForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('home')
    else:
        form = OrdemServicoForm()


    numero_os = request.GET.get('numero_os', '')
    tag = request.GET.get('tag', '')
    codigo_os = request.GET.get('codigo_os', '')
    cliente = request.GET.get('cliente', '')
    unidade = request.GET.get('unidade', '')
    solicitante = request.GET.get('solicitante', '')
    servico = request.GET.get('servico', '')
    especificacao = request.GET.get('especificacao', '')
    metodo = request.GET.get('metodo', '')
    status_operacao = request.GET.get('status_operacao', '')
    status_comercial = request.GET.get('status_comercial', '')
    data_inicial = request.GET.get('data_inicial', '')
    data_final = request.GET.get('data_final', '')

    servicos_list = OrdemServico.objects.all().order_by('-id')

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
    if servico:
        servicos_list = servicos_list.filter(servico__icontains=servico)
    if especificacao:
        servicos_list = servicos_list.filter(especificacao__icontains=especificacao)
    if metodo:
        servicos_list = servicos_list.filter(metodo__icontains=metodo)
    if status_operacao:
        servicos_list = servicos_list.filter(status_operacao__icontains=status_operacao)
    if status_comercial:
        servicos_list = servicos_list.filter(status_comercial__icontains=status_comercial)

    from datetime import datetime
    if data_inicial:
        try:
            data_inicial_obj = datetime.strptime(data_inicial, '%Y-%m-%d').date()
            servicos_list = servicos_list.filter(data_inicio__gte=data_inicial_obj)
        except ValueError:
            pass
    if data_final:
        try:
            data_final_obj = datetime.strptime(data_final, '%Y-%m-%d').date()
            servicos_list = servicos_list.filter(data_fim__lte=data_final_obj)
        except ValueError:
            pass

    paginator = Paginator(servicos_list, 6)
    page = request.GET.get('page')

    try:
        servicos = paginator.page(page)
    except PageNotAnInteger:
        servicos = paginator.page(1)
    except EmptyPage:
        servicos = paginator.page(paginator.num_pages)

    return render(request, 'home.html', {
        'form': form,
        'servicos': servicos,
        'paginator': paginator
    })

def logout_view(request):
    logout(request)
    return redirect('login')
