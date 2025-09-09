from django.template.loader import render_to_string
from weasyprint import HTML
import tempfile
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from .models import OrdemServico
from .forms import OrdemServicoForm
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from datetime import datetime
from django.http import HttpResponse
import pandas as pd
from io import BytesIO
from datetime import datetime

# Cria uma nova OS ou lista as existentes com paginação e filtros
def lista_servicos(request):
    if request.method == 'POST':
        print('DEBUG: INICIO POST lista_servicos')
        try:
            form = OrdemServicoForm(request.POST, request.FILES)
            print('DEBUG: Form criado')
            if form.is_valid():
                print('DEBUG: Form válido')
                try:
                    ordem_servico = form.save()
                    print('DEBUG: OS criada, retornando sucesso')
                    return JsonResponse({
                        'success': True,
                        'message': f'OS {ordem_servico.numero_os} criada com sucesso!',
                        'redirect': '/'
                    })
                except Exception as e:
                    import traceback
                    print('DEBUG: Erro ao salvar OS:', e)
                    return JsonResponse({
                        'success': False,
                        'errors': {'__all__': [str(e), traceback.format_exc()]}
                    }, status=400)
            else:
                print('DEBUG: Form inválido')
                errors = {}
                for field, field_errors in form.errors.items():
                    errors[field] = [str(error) for error in field_errors]
                errors['__debug_post'] = dict(request.POST)
                print('DEBUG: Retornando erros do form', errors)
                return JsonResponse({
                    'success': False,
                    'errors': errors
                }, status=400)
        except Exception as e:
            import traceback
            print('DEBUG: Exceção geral no POST:', e)
            return JsonResponse({
                'success': False,
                'errors': {'__all__': [str(e), traceback.format_exc()]}
            }, status=500)
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

# Detalhes de uma OS específica
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
            'metodo_secundario': os_instance.metodo_secundario,
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

# Obtém o ID da OS com base no número da OS
def get_os_id_by_number(request, numero_os):
    try:
        os_instance = OrdemServico.objects.get(numero_os=numero_os)
        return JsonResponse({'id': os_instance.pk})
    except OrdemServico.DoesNotExist:
        return JsonResponse({'error': 'Ordem de Serviço não encontrada.'}, status=404)
    except ValueError:
        return JsonResponse({'error': 'Número de OS inválido.'}, status=400)

# Busca uma OS específica para edição
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
                'metodo_secundario': os_instance.metodo_secundario,
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

# Atualiza uma OS existente
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

        # Atualização dos campos básicos
        os_instance.cliente = request.POST.get('cliente', os_instance.cliente)
        os_instance.unidade = request.POST.get('unidade', os_instance.unidade)
        os_instance.solicitante = request.POST.get('solicitante', os_instance.solicitante)
        os_instance.servico = request.POST.get('servico', os_instance.servico)
        os_instance.tag = request.POST.get('tag', os_instance.tag)
        os_instance.metodo = request.POST.get('metodo', os_instance.metodo)
        os_instance.metodo_secundario = request.POST.get('metodo_secundario', os_instance.metodo_secundario)

        # Atualização dos campos de data
        from datetime import datetime
        data_inicio = request.POST.get('data_inicio')
        if data_inicio:
            try:
                os_instance.data_inicio = datetime.strptime(data_inicio, '%Y-%m-%d').date()
            except Exception:
                pass
        data_fim = request.POST.get('data_fim')
        if data_fim:
            try:
                os_instance.data_fim = datetime.strptime(data_fim, '%Y-%m-%d').date()
            except Exception:
                os_instance.data_fim = None
        else:
            os_instance.data_fim = None

        volume_tanque = request.POST.get('volume_tanque')
        if volume_tanque is not None and volume_tanque != '':
            try:
                from decimal import Decimal
                os_instance.volume_tanque = Decimal(str(volume_tanque).replace(',', '.'))
            except Exception:
                return JsonResponse({'success': False, 'error': 'Volume do tanque deve ser um número válido'}, status=400)

        # Atualização dos demais campos
        os_instance.especificacao = request.POST.get('especificacao', os_instance.especificacao)
        os_instance.tipo_operacao = request.POST.get('tipo_operacao', os_instance.tipo_operacao)
        novo_status_operacao = request.POST.get('status_operacao', os_instance.status_operacao)
        os_instance.status_operacao = novo_status_operacao

        # Se o novo status for 'Finalizada - 100%', atualiza todas as OS com o mesmo numero_os
        if novo_status_operacao == 'Finalizada - 100%':
            numero_os_atual = os_instance.numero_os
            OrdemServico.objects.filter(numero_os=numero_os_atual).update(status_operacao='Finalizada - 100%')
        os_instance.status_comercial = request.POST.get('status_comercial', os_instance.status_comercial)

        # Adicionar nova observação, nunca sobrescrever
        nova_observacao = request.POST.get('nova_observacao', None)
        if nova_observacao is not None and nova_observacao.strip():
            usuario = request.user.username if request.user.is_authenticated else 'Sistema'
            timestamp = datetime.now().strftime('%d/%m/%Y %H:%M')
            nova_entrada = f"\n[{timestamp} - {usuario}]: {nova_observacao.strip()}"
            if os_instance.observacao:
                os_instance.observacao += nova_entrada
            else:
                os_instance.observacao = nova_entrada

        # Salva a OS
        os_instance.save()

        # Se for AJAX, retorna JSON. Se não, retorna status 204 para evitar redirecionamento
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'OS atualizada com sucesso!'})
        else:
            from django.http import HttpResponse
            return HttpResponse(status=204)

    except OrdemServico.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Ordem de Serviço não encontrada'}, status=404)
    except Exception as e:
        import traceback
        return JsonResponse({'success': False, 'error': f'Erro ao atualizar OS: {str(e)}', 'traceback': traceback.format_exc()}, status=500)

# Página inicial com formulário de criação e lista de OS
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
    coordenador = request.GET.get('coordenador', '')
    data_inicial = request.GET.get('data_inicial', '')
    data_final = request.GET.get('data_final', '')

    filtros_ativos = {}
    if numero_os:
        filtros_ativos['Número OS'] = numero_os
    if tag:
        filtros_ativos['Tag'] = tag
    if codigo_os:
        filtros_ativos['Código OS'] = codigo_os
    if cliente:
        filtros_ativos['Cliente'] = cliente
    if unidade:
        filtros_ativos['Unidade'] = unidade
    if solicitante:
        filtros_ativos['Solicitante'] = solicitante
    if servico:
        filtros_ativos['Serviço'] = servico
    if especificacao:
        filtros_ativos['Especificação'] = especificacao
    if metodo:
        filtros_ativos['Método'] = metodo
    if status_operacao:
        filtros_ativos['Status Operação'] = status_operacao
    if status_comercial:
        filtros_ativos['Status Comercial'] = status_comercial
    if coordenador:
        filtros_ativos['Coordenador'] = coordenador
    if data_inicial:
        filtros_ativos['data_inicial'] = data_inicial
    if data_final:
        filtros_ativos['data_final'] = data_final

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
    if coordenador:
        servicos_list = servicos_list.filter(coordenador__icontains=coordenador)

    # Filtragem por intervalo de datas
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
        'paginator': paginator,
        'filtros_ativos': filtros_ativos
    })

# Logout do usuário
def logout_view(request):
    logout(request)
    return redirect('login')

# Exporta tabela o para Excel
def exportar_ordens_excel(request):
    queryset = OrdemServico.objects.all()
    df = pd.DataFrame(list(queryset.values()))
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    response = HttpResponse(output.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=ordens_servico.xlsx'
    return response

# Exporta detalhes da OS para PDF
def exportar_os_pdf(request, os_id):
    try:
        os_instance = OrdemServico.objects.get(pk=os_id)
        context = {
            'os': os_instance
        }
        html_string = render_to_string('os_pdf.html', context)
        from io import BytesIO
        pdf_io = BytesIO()
        HTML(string=html_string, base_url=request.build_absolute_uri('/')).write_pdf(pdf_io)
        pdf_io.seek(0)
        response = HttpResponse(pdf_io.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="os_{os_instance.numero_os}.pdf"'
        return response
    except OrdemServico.DoesNotExist:
        return HttpResponse('Ordem de Serviço não encontrada.', status=404)
