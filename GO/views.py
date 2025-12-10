from django.template.loader import render_to_string
import tempfile
from django.http import JsonResponse
import logging
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.contrib.auth import views as auth_views
from django.urls import reverse


class CustomLoginView(auth_views.LoginView):
    """LoginView customizada que redireciona Supervisores para a tela RDO (versão mobile).

    Comportamento:
    - Após autenticação bem-sucedida, se o usuário pertence ao grupo 'Supervisor',
      redireciona para '/rdo/?mobile=1'.
    - Caso contrário, segue o comportamento padrão (LOGIN_REDIRECT_URL ou next).
    """

    def form_valid(self, form):
        # chama o comportamento padrão que faz login
        response = super().form_valid(form)
        try:
            user = getattr(self.request, 'user', None)
            if user and user.is_authenticated:
                try:
                    is_sup = user.groups.filter(name='Supervisor').exists()
                except Exception:
                    is_sup = False
                if is_sup:
                    # redirecionar supervisor para a página RDO (a view/template
                    # lidarão com exibir a versão mobile conforme query param/manual)
                    return redirect(reverse('rdo'))
        except Exception:
            pass
        return response
from .models import OrdemServico, Cliente, Unidade
import unicodedata
from django.db.models import Func, F
from django.db import connection
from django.db.models.functions import Lower
from django.contrib.auth import get_user_model
from django.db.models import Q
from .forms import OrdemServicoForm
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from datetime import datetime
from django.http import HttpResponse
from io import BytesIO
import os
import tempfile
import subprocess
from datetime import datetime
from django.conf import settings
from django.views.decorators.http import require_GET
from django.db.models import Sum
from decimal import Decimal
from .models import Equipamentos
from urllib.parse import urlencode


# Helper para ler campos que podem ter nomes diferentes (ex: 'cliente' vs 'Cliente')
def _get_field_value(obj, *names):
    for name in names:
        if hasattr(obj, name):
            try:
                val = getattr(obj, name)
                # Se for FK para Cliente/Unidade, preferir o atributo nome
                if val is None:
                    return ''
                # tentar acessar nome se existir
                if hasattr(val, 'nome'):
                    return getattr(val, 'nome')
                # se for um model user, tentar full_name ou username
                try:
                    if hasattr(val, 'get_full_name'):
                        full = val.get_full_name()
                        if full:
                            return full
                except Exception:
                    pass
                return str(val)
            except Exception:
                continue
    return ''


# Remove acentos de uma string (usado para normalizar buscas)
def remove_accents(s):
    try:
        s = str(s)
    except Exception:
        return s
    nkfd = unicodedata.normalize('NFKD', s)
    return ''.join([c for c in nkfd if not unicodedata.combining(c)])


# Helper genérico: tenta aplicar filter insensível a acentos usando SQL
# (unaccent + lower) e faz fallback para __icontains simples.
def safe_icontains(queryset, field_name, value):
    if not value:
        return queryset
    # Normalizar localmente (remoção de acentos + lower)
    try:
        norm_value = remove_accents(value).lower()
    except Exception:
        norm_value = value.lower() if isinstance(value, str) else value

    # Só tentar usar a função SQL `unaccent` quando o backend for Postgres
    if connection.vendor == 'postgresql':
        annot_name = f"_norm_{abs(hash(field_name)) % 100000}"
        try:
            return queryset.annotate(**{
                annot_name: Lower(Func(F(field_name), function='unaccent'))
            }).filter(**{f"{annot_name}__contains": norm_value})
        except Exception:
            # se falhar, cair para o fallback abaixo
            pass

    # Se não for Postgres, tentar um filtro em Python sobre um subconjunto
    # mínimo de colunas (pk + campo) para fazer busca insensível a acentos.
    if connection.vendor != 'postgresql':
        try:
            # valores mínimos para evitar carregar objetos inteiros
            rows = list(queryset.values_list('pk', field_name))
            matching_pks = []
            for pk, raw_val in rows:
                try:
                    text = '' if raw_val is None else str(raw_val)
                except Exception:
                    text = ''
                if remove_accents(text).lower().find(norm_value) != -1:
                    matching_pks.append(pk)
            if matching_pks:
                return queryset.filter(pk__in=matching_pks)
            # se não há correspondentes, retornar queryset vazio
            return queryset.none()
        except Exception:
            # fallback final: usar icontains normal
            try:
                return queryset.filter(**{f"{field_name}__icontains": value})
            except Exception:
                return queryset

    # Fallback para Postgres caso unaccent falhe: usar icontains
    try:
        return queryset.filter(**{f"{field_name}__icontains": value})
    except Exception:
        return queryset


# --- Adicionar helper resiliente de filtro por nome de FK ---
def _safe_apply_name_filter(queryset, fk_field_name, legacy_field_name, value):
        """
        Aplica filtro de maneira resiliente:
        - Tenta primeiro filtrar por <FKField>__nome__icontains (ex: Cliente__nome__icontains)
        - Se isso falhar (FieldError / schema diferente), tenta variações (lower/capitalize) e o campo legado
        - Retorna o queryset possivelmente filtrado (ou o queryset original se nada funcionar)
        """
        if not value:
            return queryset
        candidates = []
        # prefira filtrar pelo campo relacionado 'nome'
        candidates.append(f"{fk_field_name}__nome__icontains")
        # variantes em lowercase/capitalized
        if fk_field_name.lower() != fk_field_name:
            candidates.append(f"{fk_field_name.lower()}__nome__icontains")
        if fk_field_name.capitalize() != fk_field_name:
            candidates.append(f"{fk_field_name.capitalize()}__nome__icontains")
        # fallback: procurar pelo campo legado direto
        candidates.append(f"{legacy_field_name}__icontains")
        if legacy_field_name.lower() != legacy_field_name:
            candidates.append(f"{legacy_field_name.lower()}__icontains")
        if legacy_field_name.capitalize() != legacy_field_name:
            candidates.append(f"{legacy_field_name.capitalize()}__icontains")

        # Primeiro tentar aplicar filtro usando a função SQL unaccent (Postgres)
        # para tornar a busca insensível a acentos e caixa. Se o banco não
        # suportar, cairá no fallback abaixo.
        def _remove_accents(s):
            try:
                s = str(s)
            except Exception:
                return s
            nkfd = unicodedata.normalize('NFKD', s)
            return ''.join([c for c in nkfd if not unicodedata.combining(c)])

        try:
            norm_value = _remove_accents(value).lower()
        except Exception:
            norm_value = value.lower() if isinstance(value, str) else value

        # 1) Se for Postgres, tentar anotar + unaccent sobre cada candidato
        if connection.vendor == 'postgresql':
            for cand in candidates:
                try:
                    # cand tem formato '<field>__nome__icontains' ou similar; extrair lookup base
                    lookup_base = cand.replace('__icontains', '')
                    annot_name = f"_norm_{abs(hash(lookup_base)) % 100000}"
                    qs = queryset.annotate(**{
                        annot_name: Lower(Func(F(lookup_base), function='unaccent'))
                    }).filter(**{f"{annot_name}__contains": norm_value})
                    # se encontrou resultados, retornar imediatamente
                    if qs.exists():
                        return qs
                except Exception:
                    # ignorar e tentar próximo candidato
                    continue

        # 2) Tentar aplicar filtros simples __icontains para cada candidato
        for cand in candidates:
            try:
                qs = queryset.filter(**{cand: value})
                if qs.exists():
                    return qs
            except Exception:
                continue

        # 3) Tentar usar safe_icontains no campo legado como fallback
        try:
            return safe_icontains(queryset, legacy_field_name, value)
        except Exception:
            # por fim, retornar o queryset original (sem alterações)
            return queryset
def lista_servicos(request):
    if request.method == 'POST':
        try:
            # Alguns campos podem estar desabilitados no form (cliente/unidade)
            # quando a opção 'existente' é escolhida; garantir que estejam
            # presentes na cópia do POST para validação.
            post_data = request.POST.copy()
            try:
                if post_data.get('box_opcao') == 'existente' and post_data.get('os_existente'):
                    try:
                        existing = OrdemServico.objects.get(pk=int(post_data.get('os_existente')))
                        # preencher chaves esperadas pelo Form (maiúsculas e minúsculas)
                        if getattr(existing, 'Cliente', None):
                            post_data['Cliente'] = str(existing.Cliente.pk)
                            post_data['cliente'] = str(existing.Cliente.nome)
                        else:
                            post_data['Cliente'] = str(existing.cliente)
                            post_data['cliente'] = str(existing.cliente)
                        if getattr(existing, 'Unidade', None):
                            post_data['Unidade'] = str(existing.Unidade.pk)
                            post_data['unidade'] = str(existing.Unidade.nome)
                        else:
                            post_data['Unidade'] = str(existing.unidade)
                            post_data['unidade'] = str(existing.unidade)
                    except Exception:
                        pass
            except Exception:
                pass

            # Se front não enviar 'servicos', replicar a partir de 'servico' (consistência)
            try:
                if 'servico' in post_data and 'servicos' not in post_data:
                    post_data['servicos'] = post_data.get('servico')
            except Exception:
                pass
            form = OrdemServicoForm(post_data, request.FILES)

            if form.is_valid():
                # Salvar a instância manualmente para calcular a frente automaticamente
                ordem_servico = form.save(commit=False)
                try:
                    from django.db import transaction
                    with transaction.atomic():
                        # contar quantas OSs já existem com o mesmo número
                        existing_count = OrdemServico.objects.filter(numero_os=ordem_servico.numero_os).count()
                        ordem_servico.frente = (existing_count or 0) + 1
                        ordem_servico.save()
                except Exception:
                    # fallback simples
                    ordem_servico.save()
                # preparar representação reduzida da OS para retorno AJAX
                try:
                    try:
                        sup_val = ordem_servico.supervisor.get_full_name() or ordem_servico.supervisor.username
                    except Exception:
                        sup_val = str(ordem_servico.supervisor) if ordem_servico.supervisor else ''
                except Exception:
                    sup_val = ''

                os_data = {
                    'id': ordem_servico.pk,
                    'numero_os': ordem_servico.numero_os,
                    'data_inicio_frente': ordem_servico.data_inicio_frente.strftime('%d/%m/%Y') if getattr(ordem_servico, 'data_inicio_frente', None) else '',
                    'data_fim_frente': ordem_servico.data_fim_frente.strftime('%d/%m/%Y') if getattr(ordem_servico, 'data_fim_frente', None) else '',
                    'dias_de_operacao_frente': getattr(ordem_servico, 'dias_de_operacao_frente', 0),
                    'frente': getattr(ordem_servico, 'frente', '') or '',
                    'data_inicio': ordem_servico.data_inicio.strftime('%d/%m/%Y') if ordem_servico.data_inicio else '',
                    'data_fim': ordem_servico.data_fim.strftime('%d/%m/%Y') if ordem_servico.data_fim else '',
                    'dias_de_operacao': ordem_servico.dias_de_operacao,
                    'cliente': _get_field_value(ordem_servico, 'cliente', 'Cliente'),
                    'unidade': _get_field_value(ordem_servico, 'unidade', 'Unidade'),
                    'solicitante': ordem_servico.solicitante,
                    'tipo_operacao': ordem_servico.tipo_operacao,
                    'servico': ordem_servico.servico,
                    # 'servicos' mantém a lista completa enviada pelo usuário (se houver)
                    'servicos': getattr(ordem_servico, 'servicos', ordem_servico.servico),
                    'metodo': ordem_servico.metodo,
                    'metodo_secundario': ordem_servico.metodo_secundario,
                    'turno': getattr(ordem_servico, 'turno', '') or '',
                    'tanque': ordem_servico.tanque,
                    'tanques': getattr(ordem_servico, 'tanques', None),
                    'po': ordem_servico.po,
                    'material': ordem_servico.material,
                    'volume_tanque': str(ordem_servico.volume_tanque) if ordem_servico.volume_tanque is not None else '',
                    'especificacao': ordem_servico.especificacao,
                    'pob': ordem_servico.pob,
                    'coordenador': ordem_servico.coordenador,
                    'supervisor': sup_val,
                    'supervisor_id': ordem_servico.supervisor.pk if getattr(ordem_servico, 'supervisor', None) and hasattr(ordem_servico.supervisor, 'pk') else None,
                    'status_operacao': ordem_servico.status_operacao,
                    'status_geral': ordem_servico.status_geral,
                    'status_planejamento': ordem_servico.status_planejamento,
                    'status_comercial': ordem_servico.status_comercial,
                    'observacao': ordem_servico.observacao,
                }

                # Sincronizar campo PO na(s) RDO(s) associadas, quando aplicável.
                try:
                    if getattr(ordem_servico, 'po', None):
                        from .models import RDO
                        try:
                            # Atualizar o(s) RDO(s) vinculados à OS para refletir o PO/contrato atual
                            RDO.objects.filter(ordem_servico=ordem_servico).update(po=ordem_servico.po, contrato_po=ordem_servico.po)
                        except Exception:
                            # Não bloquear a criação da OS por falha na sincronização
                            pass
                except Exception:
                    pass

                return JsonResponse({
                    'success': True,
                    'message': f'OS {ordem_servico.numero_os} criada com sucesso!',
                    'redirect': '/',
                    'os': os_data
                })
            else:
                errors = {field: [str(error) for error in field_errors] for field, field_errors in form.errors.items()}
                if settings.DEBUG:
                    try:
                        safe_post = {k: v for k, v in request.POST.items() if k.lower() != 'csrfmiddlewaretoken'}
                        logging.warning('POST /nova_os/ inválido. Erros: %s | Payload: %s', errors, safe_post)
                    except Exception:
                        logging.warning('POST /nova_os/ inválido, falha ao logar payload. Erros: %s', errors)

                return JsonResponse({
                    'success': False,
                    'errors': errors
                }, status=400)
        except Exception as e:
                if settings.DEBUG:
                    logging.exception('Erro inesperado ao processar POST /nova_os/: %s', e)
                return JsonResponse({
                    'success': False,
                    'errors': {'__all__': ['Erro interno no servidor.']}
                }, status=500)
    else:
        form = OrdemServicoForm()

    # Coleta todos os filtros possíveis do GET
    numero_os = request.GET.get('numero_os', '')
    # 'tag' e 'codigo_os' removidos do modelo; não coletamos esses filtros
    cliente = request.GET.get('cliente', '')
    unidade = request.GET.get('unidade', '')
    solicitante = request.GET.get('solicitante', '')
    servico = request.GET.get('servico', '')
    especificacao = request.GET.get('especificacao', '')
    metodo = request.GET.get('metodo', '')
    status_operacao = request.GET.get('status_operacao', '')
    status_geral = request.GET.get('status_geral', '')
    status_comercial = request.GET.get('status_comercial', '')
    status_planejamento = request.GET.get('status_planejamento', '')
    coordenador = request.GET.get('coordenador', '')
    data_inicial = request.GET.get('data_inicial', '')
    turno = request.GET.get('turno', '')
    data_final = request.GET.get('data_final', '')

    # Monta dicionário de filtros ativos apenas se houver valor
    filtros_ativos = {}
    if numero_os:
        filtros_ativos['Número OS'] = numero_os
    # não adicionamos filtros relacionados a tag/codigo_os
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
    if status_planejamento:
        filtros_ativos['Status Planejamento'] = status_planejamento
    if status_comercial:
        filtros_ativos['Status Comercial'] = status_comercial
    if coordenador:
        filtros_ativos['Coordenador'] = coordenador
    if turno:
        filtros_ativos['Turno'] = turno
    if data_inicial:
        filtros_ativos['data_inicial'] = data_inicial
    if data_final:
        filtros_ativos['data_final'] = data_final

    servicos_list = OrdemServico.objects.all().order_by('-id')
    if numero_os:
        servicos_list = safe_icontains(servicos_list, 'numero_os', numero_os)
    # filtros por tag/codigo_os removidos
    # Substituir filtros diretos por aplicação segura:
    if cliente:
        servicos_list = _safe_apply_name_filter(servicos_list, 'Cliente', 'cliente', cliente)
    if unidade:
        servicos_list = _safe_apply_name_filter(servicos_list, 'Unidade', 'unidade', unidade)
    if solicitante:
        servicos_list = safe_icontains(servicos_list, 'solicitante', solicitante)
    if servico:
        servicos_list = safe_icontains(servicos_list, 'servico', servico)
    if especificacao:
        servicos_list = safe_icontains(servicos_list, 'especificacao', especificacao)
    if metodo:
        servicos_list = safe_icontains(servicos_list, 'metodo', metodo)
    if status_operacao:
        servicos_list = safe_icontains(servicos_list, 'status_operacao', status_operacao)
    if status_geral:
        servicos_list = safe_icontains(servicos_list, 'status_geral', status_geral)
    if status_planejamento:
        servicos_list = safe_icontains(servicos_list, 'status_planejamento', status_planejamento)
    if status_comercial:
        servicos_list = safe_icontains(servicos_list, 'status_comercial', status_comercial)
    if coordenador:
        servicos_list = safe_icontains(servicos_list, 'coordenador', coordenador)
    if turno:
        servicos_list = safe_icontains(servicos_list, 'turno', turno)
    # Filtro por datas
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
        'filtros_ativos': filtros_ativos,
        # Listas para validação/sugestão de dados
        'clientes': Cliente.objects.all().order_by('nome'),
        'unidades': Unidade.objects.all().order_by('nome'),
    })

# Página de Relatório Diário de Operação (RDO)
@login_required(login_url='/login/')
def relatorio_diario_operacao(request):
    return render(request, 'relatorio_diario_operacao.html')


# Página de Equipamentos
@login_required(login_url='/login/')
def equipamentos(request):
    """Renderiza a página de Equipamentos."""
    # enviar lista de equipamentos para o template para que a tabela seja populada a partir do DB
    # Anotar o queryset com os campos do último Formulario_de_inspecao relacionado
    from django.db.models import OuterRef, Subquery, DateField, CharField
    from .models import Formulario_de_inspeção
    last_form_qs = Formulario_de_inspeção.objects.filter(equipamentos=OuterRef('pk')).order_by('-id')
    responsavel_sub = Subquery(last_form_qs.values('responsável')[:1], output_field=CharField())
    data_inspecao_sub = Subquery(last_form_qs.values('data_inspecao_material')[:1], output_field=DateField())
    local_sub = Subquery(last_form_qs.values('local_inspecao')[:1], output_field=CharField())
    previsao_sub = Subquery(last_form_qs.values('previsao_retorno')[:1], output_field=DateField())

    equipamentos_qs = Equipamentos.objects.all().order_by('-pk').annotate(
        responsavel=responsavel_sub,
        data_inspecao=data_inspecao_sub,
        local_inspecao=local_sub,
        previsao_retorno=previsao_sub
    )

    # Aplicar filtros (mesma lógica da view `equipamentos`)
    filter_cliente = request.GET.get('filter_cliente', '').strip()
    filter_embarcacao = request.GET.get('filter_embarcacao', '').strip()
    filter_numero_os = request.GET.get('filter_numero_os', '').strip()
    filter_data_inspecao = request.GET.get('filter_data_inspecao', '').strip()
    filter_local = request.GET.get('filter_local', '').strip()

    if filter_cliente:
        equipamentos_qs = _safe_apply_name_filter(equipamentos_qs, 'Cliente', 'cliente', filter_cliente)
    if filter_embarcacao:
        equipamentos_qs = safe_icontains(equipamentos_qs, 'embarcacao', filter_embarcacao)
    if filter_numero_os:
        equipamentos_qs = safe_icontains(equipamentos_qs, 'numero_os', filter_numero_os)
    if filter_local:
        equipamentos_qs = safe_icontains(equipamentos_qs, 'local_inspecao', filter_local)
    if filter_data_inspecao:
        try:
            from datetime import datetime as _dt
            data_obj = _dt.strptime(filter_data_inspecao, '%Y-%m-%d').date()
            equipamentos_qs = equipamentos_qs.filter(data_inspecao=data_obj)
        except Exception:
            pass
    # Ler filtros do GET (nomes correspondem aos inputs do template)
    filter_cliente = request.GET.get('filter_cliente', '').strip()
    filter_embarcacao = request.GET.get('filter_embarcacao', '').strip()
    filter_numero_os = request.GET.get('filter_numero_os', '').strip()
    filter_data_inspecao = request.GET.get('filter_data_inspecao', '').strip()
    filter_local = request.GET.get('filter_local', '').strip()

    # Aplicar filtros ao queryset ANTES da paginação — assim todos os registros
    # são considerados e a paginação será aplicada sobre o resultado filtrado.
    if filter_cliente:
        equipamentos_qs = _safe_apply_name_filter(equipamentos_qs, 'Cliente', 'cliente', filter_cliente)
    if filter_embarcacao:
        equipamentos_qs = safe_icontains(equipamentos_qs, 'embarcacao', filter_embarcacao)
    if filter_numero_os:
        equipamentos_qs = safe_icontains(equipamentos_qs, 'numero_os', filter_numero_os)
    if filter_local:
        # local_inspecao é uma anotação a partir do último formulário
        equipamentos_qs = safe_icontains(equipamentos_qs, 'local_inspecao', filter_local)
    if filter_data_inspecao:
        try:
            from datetime import datetime as _dt
            data_obj = _dt.strptime(filter_data_inspecao, '%Y-%m-%d').date()
            equipamentos_qs = equipamentos_qs.filter(data_inspecao=data_obj)
        except Exception:
            # falha silenciosa no parse da data (não aplicamos o filtro)
            pass
    # Paginação: permitir que o usuário escolha o tamanho da página via GET (page-size)
    page_size_raw = request.GET.get('page-size') or request.GET.get('page_size') or '6'
    try:
        page_size = int(page_size_raw)
        if page_size <= 0:
            page_size = 6
    except Exception:
        page_size = 6

    paginator = Paginator(equipamentos_qs, page_size)
    page = request.GET.get('page')
    try:
        equipamentos_page = paginator.page(page)
    except PageNotAnInteger:
        equipamentos_page = paginator.page(1)
    except EmptyPage:
        equipamentos_page = paginator.page(paginator.num_pages)

    # construir querystring preservando outros parâmetros (exceto page e page-size)
    params = request.GET.copy()
    params.pop('page', None)
    params.pop('page-size', None)
    params.pop('page_size', None)
    qs = ''
    if params:
        qs = '&' + urlencode(params, doseq=True)

    return render(request, 'equipamentos.html', {
        'equipamentos': equipamentos_page,
        'paginator': paginator,
        'page_size': page_size,
        'qs': qs,
    })

# Detalhes de uma OS específica
def detalhes_os(request, os_id):
    try:
        os_instance = OrdemServico.objects.get(pk=os_id)
        try:
            sup_val = os_instance.supervisor.get_full_name() or os_instance.supervisor.username
        except Exception:
            sup_val = str(os_instance.supervisor) if os_instance.supervisor else ''

        # Derivar campos "primários" a partir das listas CSV quando necessário
        def first_from_csv(raw):
            try:
                if not raw:
                    return ''
                parts = [p.strip() for p in str(raw).split(',') if str(p).strip()]
                return parts[0] if parts else ''
            except Exception:
                return ''

        servico_primary = getattr(os_instance, 'servico', '') or first_from_csv(getattr(os_instance, 'servicos', ''))
        tanque_primary = getattr(os_instance, 'tanque', '') or first_from_csv(getattr(os_instance, 'tanques', ''))
        volume_str = ''
        try:
            volume_val = getattr(os_instance, 'volume_tanque', None)
            volume_str = str(volume_val) if volume_val is not None else ''
        except Exception:
            volume_str = ''

        data = {
            'id': os_instance.pk,
            'numero_os': os_instance.numero_os,
            'data_inicio_frente': os_instance.data_inicio_frente.strftime('%d/%m/%Y') if getattr(os_instance, 'data_inicio_frente', None) else '',
            'data_fim_frente': os_instance.data_fim_frente.strftime('%d/%m/%Y') if getattr(os_instance, 'data_fim_frente', None) else '',
            'dias_de_operacao_frente': getattr(os_instance, 'dias_de_operacao_frente', 0),
            'frente': getattr(os_instance, 'frente', '') or '',
            'data_inicio': os_instance.data_inicio.strftime('%d/%m/%Y') if os_instance.data_inicio else '',
            'data_fim': os_instance.data_fim.strftime('%d/%m/%Y') if os_instance.data_fim else '',
            'dias_de_operacao': os_instance.dias_de_operacao,
            'cliente': _get_field_value(os_instance, 'cliente', 'Cliente'),
            'unidade': _get_field_value(os_instance, 'unidade', 'Unidade'),
            'solicitante': os_instance.solicitante,
            'tipo_operacao': os_instance.tipo_operacao,
            # sempre fornecer um serviço primário coerente
            'servico': servico_primary,
            # incluir lista completa de serviços quando disponível (CSV); fallback para o primário
            'servicos': getattr(os_instance, 'servicos', os_instance.servico),
            'metodo': os_instance.metodo,
            'metodo_secundario': os_instance.metodo_secundario,
            'turno': getattr(os_instance, 'turno', '') or '',
            # fornecer tanque "primário" (primeiro da lista) para compatibilidade com UI
            'tanque': tanque_primary,
            'tanques': getattr(os_instance, 'tanques', None),
            'po': os_instance.po,
            'material': os_instance.material or '',
            'volume_tanque': volume_str,
            'especificacao': os_instance.especificacao,
            'pob': os_instance.pob,
            'coordenador': os_instance.coordenador,
            'supervisor': sup_val,
            'supervisor_id': os_instance.supervisor.pk if getattr(os_instance, 'supervisor', None) and hasattr(os_instance.supervisor, 'pk') else None,
            'status_operacao': os_instance.status_operacao,
            'status_geral': os_instance.status_geral,
            'status_planejamento': os_instance.status_planejamento,
            'status_comercial': os_instance.status_comercial,
            'observacao': os_instance.observacao
            ,
        }
        # Retorno padronizado para chamadas AJAX
        return JsonResponse({'success': True, 'os': data})
    except OrdemServico.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Ordem de Serviço não encontrada.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

# Obtém o ID da OS com base no número da OS
def get_os_id_by_number(request, numero_os):
    try:
        os_instance = OrdemServico.objects.get(numero_os=numero_os)
        return JsonResponse({'success': True, 'id': os_instance.pk})
    except OrdemServico.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Ordem de Serviço não encontrada.'}, status=404)
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Número de OS inválido.'}, status=400)

# Busca uma OS específica para edição
def buscar_os(request, os_id):
    """Busca uma OS específica para edição"""
    try:
        os_instance = OrdemServico.objects.get(pk=os_id)
        try:
            sup_val = os_instance.supervisor.get_full_name() or os_instance.supervisor.username
        except Exception:
            sup_val = str(os_instance.supervisor) if os_instance.supervisor else ''
        
        # Buscar dados da primeira OS do mesmo cliente para pré-preenchimento
        first_os_data = {
            'data_inicio_from_first': '',
            'solicitante_from_first': '',
            'po_from_first': '',
            'tipo_operacao_from_first': '',
        }
        try:
            # Buscar a primeira OS (por data_inicio ou id) do mesmo cliente
            # Exclusão de OS sem PO (None, '', '-') para melhorar fallback
            from django.db.models import Q
            first_os = OrdemServico.objects.filter(
                Cliente=os_instance.Cliente
            ).exclude(
                Q(po__isnull=True) | Q(po__exact='') | Q(po__exact='-')
            ).order_by('data_inicio', 'id').first()
            
            # Se não encontrou com PO preenchido, pegar apenas a primeira do cliente
            if not first_os:
                first_os = OrdemServico.objects.filter(
                    Cliente=os_instance.Cliente
                ).order_by('data_inicio', 'id').first()
            
            if first_os and first_os.pk != os_instance.pk:
                # Se encontrou uma OS anterior diferente, extrair dados
                first_os_data['data_inicio_from_first'] = first_os.data_inicio.strftime('%Y-%m-%d') if first_os.data_inicio else ''
                first_os_data['solicitante_from_first'] = first_os.solicitante or ''
                first_os_data['po_from_first'] = first_os.po or ''
                first_os_data['tipo_operacao_from_first'] = first_os.tipo_operacao or ''
        except Exception:
            # Se algo falhar ao buscar a primeira OS, continuar sem esses dados
            pass
        
        data = {
            'success': True,
            'os': {
                'id': os_instance.pk,
                'numero_os': os_instance.numero_os,
                # fornecer formato ISO para facilitar preenchimento de inputs type=date
                'data_inicio_frente': os_instance.data_inicio_frente.strftime('%Y-%m-%d') if getattr(os_instance, 'data_inicio_frente', None) else '',
                'data_fim_frente': os_instance.data_fim_frente.strftime('%Y-%m-%d') if getattr(os_instance, 'data_fim_frente', None) else '',
                'dias_de_operacao_frente': getattr(os_instance, 'dias_de_operacao_frente', 0),
                'frente': getattr(os_instance, 'frente', '') or '',
                'cliente': _get_field_value(os_instance, 'cliente', 'Cliente'),
                'unidade': _get_field_value(os_instance, 'unidade', 'Unidade'),
                'solicitante': os_instance.solicitante,
                'servico': os_instance.servico,
                'servicos': getattr(os_instance, 'servicos', os_instance.servico),
                'metodo': os_instance.metodo,
                'metodo_secundario': os_instance.metodo_secundario,
                'turno': getattr(os_instance, 'turno', '') or '',
                'tanque': os_instance.tanque,
                # incluir lista completa de tanques (csv) para pré-preencher modal de edição
                'tanques': getattr(os_instance, 'tanques', None),
                'po': os_instance.po,
                'material': os_instance.material,
                'volume_tanque': os_instance.volume_tanque,
                'especificacao': os_instance.especificacao,
                'tipo_operacao': os_instance.tipo_operacao,
                'status_operacao': os_instance.status_operacao,
                'status_geral': os_instance.status_geral,
                'status_planejamento': os_instance.status_planejamento,
                'status_comercial': os_instance.status_comercial,
                'data_inicio': os_instance.data_inicio.strftime('%Y-%m-%d') if os_instance.data_inicio else '',
                'data_fim': os_instance.data_fim.strftime('%Y-%m-%d') if os_instance.data_fim else '',
                'pob': os_instance.pob,
                'coordenador': os_instance.coordenador,
                'supervisor': sup_val,
                'supervisor_id': os_instance.supervisor.pk if getattr(os_instance, 'supervisor', None) and hasattr(os_instance.supervisor, 'pk') else None,
                'observacao': os_instance.observacao,
                # Adicionar dados da primeira OS para pré-preenchimento
                'data_inicio_from_first': first_os_data['data_inicio_from_first'],
                'solicitante_from_first': first_os_data['solicitante_from_first'],
                'po_from_first': first_os_data['po_from_first'],
                'tipo_operacao_from_first': first_os_data['tipo_operacao_from_first'],
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
        # PO e material (accept empty to clear)
        po_val = request.POST.get('po')
        if po_val is not None:
            os_instance.po = po_val if po_val != '' else None
        material_val = request.POST.get('material')
        if material_val is not None:
            os_instance.material = material_val if material_val != '' else None
        # Atualizar serviço primário e lista completa
        servico_raw = request.POST.get('servico', None)
        if servico_raw is not None:
            # definir primário como o primeiro item da lista
            if isinstance(servico_raw, str) and ',' in servico_raw:
                os_instance.servico = servico_raw.split(',')[0].strip()
            else:
                os_instance.servico = servico_raw
        os_instance.metodo = request.POST.get('metodo', os_instance.metodo)
        os_instance.metodo_secundario = request.POST.get('metodo_secundario', os_instance.metodo_secundario)
        # Turno: aceitar valor enviado (Diurno / Noturno) ou string vazia para limpar
        try:
            turno_val = request.POST.get('turno')
            if turno_val is not None:
                os_instance.turno = turno_val if turno_val != '' else None
        except Exception:
            pass
        # Persistir lista completa de serviços, quando enviada
        servicos_full = request.POST.get('servicos')
        if servicos_full is not None:
            os_instance.servicos = servicos_full
        else:
            # fallback: se não vier 'servicos', usar 'servico_raw' como lista única
            if servico_raw is not None:
                os_instance.servicos = servico_raw

        # Persistir tanques: aceitar 'tanques', 'tanques_hidden' ou 'edit_tanques_hidden'
        try:
            tanques_raw = request.POST.get('tanques') or request.POST.get('tanques_hidden') or request.POST.get('edit_tanques_hidden')
            if tanques_raw is not None:
                # normalizar espaços e remover entradas vazias
                tanques_list = [t.strip() for t in str(tanques_raw).split(',') if str(t).strip()]
                os_instance.tanques = ', '.join(tanques_list) if tanques_list else None
        except Exception:
            pass

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

        # Campos da "frente" (adicionados recentemente): garantir leitura e atribuição
        data_inicio_frente = request.POST.get('data_inicio_frente')
        if data_inicio_frente:
            try:
                os_instance.data_inicio_frente = datetime.strptime(data_inicio_frente, '%Y-%m-%d').date()
            except Exception:
                # não bloquear a edição por parsing inválido
                pass
        else:
            # se não enviado ou vazio, limpar
            os_instance.data_inicio_frente = None

        data_fim_frente = request.POST.get('data_fim_frente')
        if data_fim_frente:
            try:
                os_instance.data_fim_frente = datetime.strptime(data_fim_frente, '%Y-%m-%d').date()
            except Exception:
                os_instance.data_fim_frente = None
        else:
            os_instance.data_fim_frente = None

        # Campo 'frente' agora é gerenciado automaticamente; não permitir alteração via POST

        volume_tanque = request.POST.get('volume_tanque')
        if volume_tanque is not None and volume_tanque != '':
            try:
                from decimal import Decimal
                os_instance.volume_tanque = Decimal(str(volume_tanque).replace(',', '.'))
            except Exception:

                return JsonResponse({'success': False, 'error': 'Erro ao atualizar OS.'}, status=500)

 
        os_instance.especificacao = request.POST.get('especificacao', os_instance.especificacao)
        os_instance.tipo_operacao = request.POST.get('tipo_operacao', os_instance.tipo_operacao)
        novo_status_operacao = request.POST.get('status_operacao', os_instance.status_operacao)
        os_instance.status_operacao = novo_status_operacao
        novo_status_geral = request.POST.get('status_geral', os_instance.status_geral)
        os_instance.status_geral = novo_status_geral
        # Status planejamento (opcional)
        try:
            novo_status_planejamento = request.POST.get('status_planejamento')
            if novo_status_planejamento is not None:
                os_instance.status_planejamento = novo_status_planejamento if novo_status_planejamento != '' else None
        except Exception:
            pass


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

    # Note: campos link_rdo e materiais_equipamentos foram removidos do projeto
    # Link logística agora é fixo (não mais editável via formulário)

        # Atualiza supervisor: aceita PK do User (quando enviado por select) ou username (fallback);
        # se vazio, limpa o supervisor
        try:
            sup_val = request.POST.get('supervisor')
            if sup_val is None or str(sup_val).strip() == '':
                os_instance.supervisor = None
            else:
                try:
                    sup_pk = int(sup_val)
                    try:
                        os_instance.supervisor = get_user_model().objects.get(pk=sup_pk)
                    except Exception:
                        # fallback: tentar por username
                        try:
                            os_instance.supervisor = get_user_model().objects.get(username=str(sup_val))
                        except Exception:
                            os_instance.supervisor = None
                except (ValueError, TypeError):
                    # não é PK, tentar buscar por username
                    try:
                        os_instance.supervisor = get_user_model().objects.get(username=str(sup_val))
                    except Exception:
                        os_instance.supervisor = None
        except Exception:
            # não bloquear atualização por erro inesperado no supervisor
            pass

        # Salva a OS
        os_instance.save()
        # Sincronizar PO para RDOs relacionados (manter consistência entre home.html e rdo.html)
        try:
            if getattr(os_instance, 'po', None) is not None:
                from .models import RDO
                try:
                    RDO.objects.filter(ordem_servico=os_instance).update(po=os_instance.po, contrato_po=os_instance.po)
                except Exception:
                    pass
        except Exception:
            pass
        # Preparar dados reduzidos da OS atualizada para uso em AJAX
        try:
            try:
                sup_val = os_instance.supervisor.get_full_name() or os_instance.supervisor.username
            except Exception:
                sup_val = str(os_instance.supervisor) if os_instance.supervisor else ''
            os_data = {
                'id': os_instance.pk,
                'numero_os': os_instance.numero_os,
                'data_inicio_frente': os_instance.data_inicio_frente.strftime('%d/%m/%Y') if getattr(os_instance, 'data_inicio_frente', None) else '',
                'data_fim_frente': os_instance.data_fim_frente.strftime('%d/%m/%Y') if getattr(os_instance, 'data_fim_frente', None) else '',
                'dias_de_operacao_frente': getattr(os_instance, 'dias_de_operacao_frente', 0),
                'frente': getattr(os_instance, 'frente', '') or '',
                'data_inicio': os_instance.data_inicio.strftime('%d/%m/%Y') if os_instance.data_inicio else '',
                'data_fim': os_instance.data_fim.strftime('%d/%m/%Y') if os_instance.data_fim else '',
                'dias_de_operacao': os_instance.dias_de_operacao,
                'cliente': _get_field_value(os_instance, 'cliente', 'Cliente'),
                'unidade': _get_field_value(os_instance, 'unidade', 'Unidade'),
                'solicitante': os_instance.solicitante,
                'tipo_operacao': os_instance.tipo_operacao,
                'servico': os_instance.servico,
                'servicos': getattr(os_instance, 'servicos', os_instance.servico),
                'metodo': os_instance.metodo,
                'turno': getattr(os_instance, 'turno', '') or '',
                'metodo_secundario': os_instance.metodo_secundario,
                'tanque': os_instance.tanque,
                'tanques': getattr(os_instance, 'tanques', None),
                'volume_tanque': str(os_instance.volume_tanque) if os_instance.volume_tanque is not None else '',
                'especificacao': os_instance.especificacao,
                'pob': os_instance.pob,
                'coordenador': os_instance.coordenador,
                'supervisor': sup_val,
                'supervisor_id': os_instance.supervisor.pk if getattr(os_instance, 'supervisor', None) and hasattr(os_instance.supervisor, 'pk') else None,
                'status_operacao': os_instance.status_operacao,
                'status_planejamento': os_instance.status_planejamento,
                'status_geral': os_instance.status_geral,
                'status_comercial': os_instance.status_comercial,
                'observacao': os_instance.observacao,
            }
        except Exception:
            os_data = None

        # Se for AJAX, retorna JSON com os dados da OS atualizada para que o frontend atualize a linha dinamicamente.
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            resp = {'success': True, 'message': 'OS atualizada com sucesso!'}
            if os_data is not None:
                resp['os'] = os_data
            return JsonResponse(resp)
        else:
            from django.http import HttpResponse
            return HttpResponse(status=204)

    except OrdemServico.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Ordem de Serviço não encontrada'}, status=404)
    except Exception as e:
        # Em produção, não exponha detalhes do erro
        return JsonResponse({'success': False, 'error': 'Erro ao atualizar OS.'}, status=500)

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
    cliente = request.GET.get('cliente', '')
    unidade = request.GET.get('unidade', '')
    solicitante = request.GET.get('solicitante', '')
    servico = request.GET.get('servico', '')
    especificacao = request.GET.get('especificacao', '')
    metodo = request.GET.get('metodo', '')
    status_operacao = request.GET.get('status_operacao', '')
    status_geral = request.GET.get('status_geral', '')
    status_comercial = request.GET.get('status_comercial', '')
    status_planejamento = request.GET.get('status_planejamento', '')
    coordenador = request.GET.get('coordenador', '')
    turno = request.GET.get('turno', '')
    data_inicial = request.GET.get('data_inicial', '')
    data_final = request.GET.get('data_final', '')

    filtros_ativos = {}
    if numero_os:
        filtros_ativos['Número OS'] = numero_os
    # 'tag' and 'codigo_os' removed from models; no longer used as filters
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
    if status_planejamento:
        filtros_ativos['Status Planejamento'] = status_planejamento
    if status_geral:
        filtros_ativos['Status Geral'] = status_geral
    if status_comercial:
        filtros_ativos['Status Comercial'] = status_comercial
    if coordenador:
        filtros_ativos['Coordenador'] = coordenador
    if turno:
        filtros_ativos['Turno'] = turno
    if data_inicial:
        filtros_ativos['data_inicial'] = data_inicial
    if data_final:
        filtros_ativos['data_final'] = data_final

    servicos_list = OrdemServico.objects.all().order_by('-id')

    if numero_os:
        servicos_list = safe_icontains(servicos_list, 'numero_os', numero_os)
    # Aplicar filtros por cliente/unidade usando função segura
    if cliente:
        servicos_list = _safe_apply_name_filter(servicos_list, 'Cliente', 'cliente', cliente)
    if unidade:
        servicos_list = _safe_apply_name_filter(servicos_list, 'Unidade', 'unidade', unidade)
    if solicitante:
        servicos_list = safe_icontains(servicos_list, 'solicitante', solicitante)
    if servico:
        servicos_list = safe_icontains(servicos_list, 'servico', servico)
    if especificacao:
        servicos_list = safe_icontains(servicos_list, 'especificacao', especificacao)
    if metodo:
        servicos_list = safe_icontains(servicos_list, 'metodo', metodo)
    if status_operacao:
        servicos_list = safe_icontains(servicos_list, 'status_operacao', status_operacao)
    if status_geral:
        servicos_list = safe_icontains(servicos_list, 'status_geral', status_geral)
    if status_planejamento:
        servicos_list = safe_icontains(servicos_list, 'status_planejamento', status_planejamento)
    if status_comercial:
        servicos_list = safe_icontains(servicos_list, 'status_comercial', status_comercial)
    if coordenador:
        servicos_list = safe_icontains(servicos_list, 'coordenador', coordenador)
    if turno:
        servicos_list = safe_icontains(servicos_list, 'turno', turno)

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
        'filtros_ativos': filtros_ativos,
        # Listas para validação/sugestão de dados
        'clientes': Cliente.objects.all().order_by('nome'),
        'unidades': Unidade.objects.all().order_by('nome'),
    })

# Logout do usuário
def logout_view(request):
    logout(request)
    return redirect('login')

# Exporta tabela o para Excel
def exportar_ordens_excel(request):
    try:
        import pandas as pd
    except Exception:
        return HttpResponse('Dependência ausente: instale pandas para exportar Excel.', status=500)

    queryset = OrdemServico.objects.all()
    df = pd.DataFrame(list(queryset.values()))
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    response = HttpResponse(output.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=ordens_servico.xlsx'
    return response


@login_required(login_url='/login/')
@require_GET
def exportar_equipamentos_excel(request):
    """Gera um arquivo Excel (.xlsx) contendo os equipamentos (com campos do último formulário de inspeção).

    Atualmente exporta todos os equipamentos ordenados por PK desc. Aceita filtros por querystring no futuro.
    """
    try:
        import pandas as pd
    except Exception:
        return HttpResponse('Dependência ausente: instale pandas para exportar Excel.', status=500)

    # Recriar as anotações usadas pela view equipamentos para incluir dados do último formulário
    from django.db.models import OuterRef, Subquery, DateField, CharField
    from .models import Formulario_de_inspeção

    last_form_qs = Formulario_de_inspeção.objects.filter(equipamentos=OuterRef('pk')).order_by('-id')
    responsavel_sub = Subquery(last_form_qs.values('responsável')[:1], output_field=CharField())
    data_inspecao_sub = Subquery(last_form_qs.values('data_inspecao_material')[:1], output_field=DateField())
    local_sub = Subquery(last_form_qs.values('local_inspecao')[:1], output_field=CharField())
    previsao_sub = Subquery(last_form_qs.values('previsao_retorno')[:1], output_field=DateField())

    equipamentos_qs = Equipamentos.objects.all().order_by('-pk').annotate(
        responsavel=responsavel_sub,
        data_inspecao=data_inspecao_sub,
        local_inspecao=local_sub,
        previsao_retorno=previsao_sub
    )

    # Construir lista de dicionários para o DataFrame
    rows = []
    for e in equipamentos_qs:
        rows.append({
            'ID': e.pk,
            'Descrição': e.descricao or '',
            'Modelo': str(e.modelo) if getattr(e, 'modelo', None) else '',
            'Nº Série': e.numero_serie or '',
            'Nº TAG': e.numero_tag or '',
            'Fabricante': e.fabricante or '',
            'Cliente': e.cliente or '',
            'Embarcação': e.embarcacao or '',
            'Responsável': e.responsavel or '',
            'Nº OS': e.numero_os or '',
            'Data Inspeção': e.data_inspecao.isoformat() if getattr(e, 'data_inspecao', None) else '',
            'Local Inspeção': e.local_inspecao or '',
            'Previsão Retorno': e.previsao_retorno.isoformat() if getattr(e, 'previsao_retorno', None) else '',
        })

    df = pd.DataFrame(rows)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Equipamentos')
    output.seek(0)

    response = HttpResponse(output.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=equipamentos.xlsx'
    return response

# Exporta detalhes da OS para PDF
def exportar_os_pdf(request, os_id):
    try:
        # Garante que usamos o par compatível instalado em /usr/local (weasyprint 60.2 + pydyf 0.10.0)
        # evitando conflito com versões do sistema em /usr/lib
        try:
            import sys, importlib
            local_dist = '/usr/local/lib/python3.8/dist-packages'
            if local_dist not in sys.path:
                sys.path.insert(0, local_dist)
            for mod in ('weasyprint', 'pydyf'):
                if mod in sys.modules:
                    sys.modules.pop(mod)
            importlib.invalidate_caches()
            from weasyprint import HTML, CSS, __version__ as weasyprint_version
            import pydyf
            try:
                logging.getLogger(__name__).info(
                    'WeasyPrint/PyDyf usados: weasyprint=%s, pydyf=%s (path=%s)',
                    weasyprint_version, getattr(pydyf, '__version__', 'unknown'), getattr(pydyf, '__file__', 'n/a')
                )
            except Exception:
                pass
        except ImportError:
            return HttpResponse('Dependência ausente: instale weasyprint para exportar PDF.', status=500)

        os_instance = OrdemServico.objects.get(pk=os_id)
        # Monta lista de serviços a partir de campos existentes (CSV em os.servicos ou único em os.servico)
        def build_servicos_list(obj):
            raw = getattr(obj, 'servicos', None) or getattr(obj, 'servico', '') or ''
            if not raw:
                return []
            # tenta vírgula e ponto e vírgula como separadores
            parts = [p.strip() for p in raw.split(',') if p.strip()]
            if len(parts) <= 1 and (';' in raw):
                parts = [p.strip() for p in raw.split(';') if p.strip()]
            # remove duplicatas preservando ordem
            seen = set()
            unique = []
            for p in parts:
                if p not in seen:
                    seen.add(p)
                    unique.append(p)
            return unique

        context = {
            'os': os_instance,
            'servicos_list': build_servicos_list(os_instance),
        }
        html_string = render_to_string('os_pdf.html', context)

        from django.templatetags.static import static
        base_url = request.build_absolute_uri('/')
        css_url = request.build_absolute_uri(static('css/pdf.css'))

        from io import BytesIO
        pdf_io = BytesIO()
        try:
            # Tentativa in-processo
            HTML(string=html_string, base_url=base_url).write_pdf(pdf_io, stylesheets=[CSS(css_url)])
        except Exception as e:
            # Fallback robusto: gera PDF via subprocesso usando /bin/python3 (par de libs já validado)
            try:
                with tempfile.TemporaryDirectory() as td:
                    html_file = os.path.join(td, 'doc.html')
                    pdf_file = os.path.join(td, 'doc.pdf')
                    with open(html_file, 'w', encoding='utf-8') as f:
                        f.write(html_string)
                    code = (
                        "from weasyprint import HTML, CSS\n"
                        "import sys\n"
                        "html_path, base_url, css_url, out_path = sys.argv[1:5]\n"
                        "with open(html_path, 'r', encoding='utf-8') as f: html = f.read()\n"
                        "HTML(string=html, base_url=base_url).write_pdf(out_path, stylesheets=[CSS(css_url)])\n"
                    )
                    proc = subprocess.run(['/bin/python3', '-c', code, html_file, base_url, css_url, pdf_file],
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
                    if proc.returncode != 0 or not os.path.exists(pdf_file):
                        if settings.DEBUG:
                            logging.error('Fallback WeasyPrint subprocess falhou: rc=%s, stdout=%s, stderr=%s', proc.returncode, proc.stdout, proc.stderr)
                        return HttpResponse('Erro ao gerar PDF. Verifique os logs para detalhes.', status=500)
                    with open(pdf_file, 'rb') as pf:
                        pdf_bytes = pf.read()
                    pdf_io = BytesIO(pdf_bytes)
            except Exception:
                if settings.DEBUG:
                    logging.exception('Falha ao gerar PDF (fallback) da OS %s', os_id)
                return HttpResponse('Erro ao gerar PDF. Verifique os logs para detalhes.', status=500)

        pdf_io.seek(0)
        response = HttpResponse(pdf_io.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="os_{os_instance.numero_os}.pdf"'
        return response
    except OrdemServico.DoesNotExist:
        return HttpResponse('Ordem de Serviço não encontrada.', status=404)
