from django import forms
from decimal import Decimal
from .models import OrdemServico, RDO, Cliente, Unidade
# Formulário para criar ou atualizar um RDO
class RDOForm(forms.ModelForm):
    class Meta:
        model = RDO
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        confinado_value = self.initial.get('confinado')
        if confinado_value is None and self.instance:
            confinado_value = self.instance.confinado
        if not confinado_value:
            for field in [
                'entrada_confinado_1', 'saida_confinado_1',
                'entrada_confinado_2', 'saida_confinado_2',
                'entrada_confinado_3', 'saida_confinado_3',
                'entrada_confinado_4', 'saida_confinado_4',
                'entrada_confinado_5', 'saida_confinado_5',
                'entrada_confinado_6', 'saida_confinado_6',
                'operadores_simultaneos', 'H2S_ppm', 'LEL', 'CO_ppm', 'O2_percent'
            ]:
                if field in self.fields:
                    self.fields[field].widget.attrs['disabled'] = True

        exist_pt_value = self.initial.get('exist_pt')
        if exist_pt_value is None and self.instance:
            exist_pt_value = self.instance.exist_pt
        if not exist_pt_value:
            for field in ['pt_manha', 'pt_tarde', 'pt_noite']:
                if field in self.fields:
                    self.fields[field].widget.attrs['disabled'] = True
        if 'pessoas' in self.fields:
            self.fields['pessoas'].widget = forms.Select(attrs={'class': 'form-control'})
            self.fields['pessoas'].queryset = self.fields['pessoas'].queryset.order_by('nome')

# Formulário para criar ou atualizar uma Ordem de Serviço
class OrdemServicoForm(forms.ModelForm):
    NOVA_OS = 'nova'
    EXISTENTE_OS = 'existente'
    BOX_CHOICES = [
        (NOVA_OS, 'Nova OS'),
        (EXISTENTE_OS, 'OS já existente'),
    ]
    box_opcao = forms.ChoiceField(
        choices=BOX_CHOICES,
        widget=forms.RadioSelect(attrs={'id': 'box_opcao_radio'}),
        label="Tipo de OS",
        initial='nova'
    )
    
    os_existente = forms.ChoiceField(
        choices=[],
        required=False,
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'os_existente_select'}),
        label="OS Existente"
    )

    # Campo 'servico' como texto livre (aceita múltiplos separados por vírgula)
    servico = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'id': 'id_servico',
            'list': 'servicos_datalist',
            'placeholder': 'Selecione ou digite serviços (separe por vírgula)'
        })
    )
    class Meta:
        model = OrdemServico
        # não expor dias calculados no formulário (calculados automaticamente no save)
        exclude = ['dias_de_operacao', 'dias_de_operacao_frente']
        widgets = {
            'metodo_secundario': forms.Select(attrs={'class': 'form-control'}),
            'numero_os': forms.NumberInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
            'especificacao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'data_inicio': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'data_fim': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'data_inicio_frente': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'data_fim_frente': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'metodo': forms.Select(attrs={'class': 'form-control'}),
            'observacao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'pob': forms.NumberInput(attrs={'class': 'form-control'}),
            'tanque': forms.TextInput(attrs={'class': 'form-control'}),
            'volume_tanque': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'status_comercial': forms.Select(attrs={'class': 'form-control'}),
            'cliente': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_cliente', 'list': 'clientes_datalist', 'placeholder': 'Selecione um cliente cadastrado'}),
            'unidade': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_unidade', 'list': 'unidades_datalist', 'placeholder': 'Selecione uma unidade cadastrada'}),
            'tipo_operacao': forms.Select(attrs={'class': 'form-control'}),
            'solicitante': forms.TextInput(attrs={'class': 'form-control'}),
            'coordenador': forms.TextInput(attrs={'class': 'form-control'}),
            'supervisor': forms.TextInput(attrs={'class': 'form-control'}),
            'status_operacao': forms.Select(attrs={'class': 'form-control'}),
            'status_geral': forms.Select(attrs={'class': 'form-control'}),
            'controle_de_atividades': forms.URLInput(attrs={'class': 'form-control'}),
            'materiais_equipamentos': forms.URLInput(attrs={'class': 'form-control'}),
            'po': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_po', 'placeholder': 'PO'}),
            'material': forms.Select(attrs={'class': 'form-control', 'id': 'id_material'}),
            'turno': forms.Select(attrs={'class': 'form-control', 'id': 'id_turno'}),
            'status_planejamento': forms.Select(attrs={'class': 'form-control', 'id': 'id_status_planejamento'}),
        }
    # Inicializa o formulário e configura os campos dinâmicos
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['numero_os'].required = False
        self.fields['numero_os'].widget.attrs['readonly'] = True
        # Permitir volume/tanque em branco (servidor normaliza conforme necessário)
        if 'volume_tanque' in self.fields:
            self.fields['volume_tanque'].required = False
        if 'tanque' in self.fields:
            self.fields['tanque'].required = False

        # Status planejamento é opcional no formulário
        if 'status_planejamento' in self.fields:
            try:
                self.fields['status_planejamento'].required = False
            except Exception:
                pass

        # PO e material são opcionais no formulário
        if 'po' in self.fields:
            self.fields['po'].required = False
            try:
                self.fields['po'].widget.attrs.update({'class': 'form-control', 'id': 'id_po'})
            except Exception:
                pass
        if 'material' in self.fields:
            self.fields['material'].required = False
            try:
                # manter o Select para aproveitar as choices do modelo
                self.fields['material'].widget.attrs.update({'class': 'form-control', 'id': 'id_material'})
            except Exception:
                pass

        # Garantir que o campo 'servico' seja CharField (sem validação por choices)
        self.fields['servico'] = forms.CharField(
            required=True,
            widget=forms.TextInput(attrs={
                'class': 'form-control',
                'id': 'id_servico',
                'list': 'servicos_datalist',
                'placeholder': 'Selecione ou digite serviços (separe por vírgula)'
            })
        )
        # Fornecer a lista de opções para o datalist (sem impor validação por choices)
        try:
            self.fields['servico'].choices = OrdemServico.SERVICO_CHOICES
        except Exception:
            pass

        # Preenche os campos obrigatórios no self.data se for OS existente ou nova
        if hasattr(self, 'data') and self.data:
            data = self.data.copy()
            # Normaliza volume_tanque com vírgula para ponto (ex.: 10,5 -> 10.5)
            if 'volume_tanque' in data and isinstance(data.get('volume_tanque'), str):
                data['volume_tanque'] = data['volume_tanque'].replace(',', '.')
            box_opcao = data.get('box_opcao')
            os_existente = data.get('os_existente')
            if box_opcao == self.EXISTENTE_OS and os_existente:
                try:
                    os_obj = OrdemServico.objects.get(pk=int(os_existente))
                    # preencher tanto chaves lowercase (usadas pelo template) quanto
                    # as chaves capitalizadas (usadas internamente pelo ModelForm compat)
                    data['cliente'] = os_obj.cliente
                    data['unidade'] = os_obj.unidade
                    data['Cliente'] = os_obj.Cliente.pk if getattr(os_obj, 'Cliente', None) else os_obj.cliente
                    data['Unidade'] = os_obj.Unidade.pk if getattr(os_obj, 'Unidade', None) else os_obj.unidade
                    data['numero_os'] = os_obj.numero_os
                    data['codigo_os'] = os_obj.codigo_os
                    self.data = data
                except Exception:
                    pass
            # Para nova OS, o número pode ser atribuído no save()

        unique_os = {}
        for os in OrdemServico.objects.all().order_by('-numero_os'):
            if os.numero_os not in unique_os:
                unique_os[os.numero_os] = os
        os_choices = [(os.pk, f"OS {os.numero_os}") for os in unique_os.values()]
        if not os_choices:
            pass
        self.fields['os_existente'].choices = [('', 'Selecione uma OS existente')] + os_choices
        self.os_objects = {os.numero_os: os for os in unique_os.values()}
        
        # Substituir o campo supervisor por ModelChoiceField quando possível
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            from django.contrib.auth.models import Group
            try:
                sup_group = Group.objects.get(name='Supervisor')
                sup_qs = User.objects.filter(groups=sup_group).order_by('username')
            except Exception:
                sup_qs = User.objects.none()
            # trocar campo por ModelChoiceField para exibir select com Supervisores
            from django import forms as django_forms
            if 'supervisor' in self.fields:
                self.fields['supervisor'] = django_forms.ModelChoiceField(queryset=sup_qs, required=True, widget=django_forms.Select(attrs={'class': 'form-control'}))
        except Exception:
            # ambiente sem User model disponível — manter como estava
            pass

        # Tornar os campos Cliente/Unidade em CharField com TextInput para
        # aceitar nomes enviados pelo datalist (evita validação "Select a valid choice"
        # que acontece em ModelChoiceField antes do clean()).
        try:
            from django import forms as django_forms
            if 'Cliente' in self.fields:
                # tornar não obrigatório aqui para permitir preenchimento via lógica de 'os existente'
                self.fields['Cliente'] = django_forms.CharField(required=False, widget=django_forms.TextInput(attrs={'class': 'form-control', 'id': 'id_cliente', 'list': 'clientes_datalist', 'placeholder': 'Selecione um cliente cadastrado'}))
            if 'Unidade' in self.fields:
                # tornar não obrigatório aqui para permitir preenchimento via lógica de 'os existente'
                self.fields['Unidade'] = django_forms.CharField(required=False, widget=django_forms.TextInput(attrs={'class': 'form-control', 'id': 'id_unidade', 'list': 'unidades_datalist', 'placeholder': 'Selecione uma unidade cadastrada'}))
        except Exception:
            pass

        # Limpeza e normalização de campos
    def clean(self):
        cleaned_data = super().clean()
        # Normalizar entradas de Cliente/Unidade quando o front-end envia nomes
        try:
            # Cliente: aceitar string com nome e converter para instância
            cliente_val = cleaned_data.get('Cliente') or cleaned_data.get('cliente')
            if cliente_val and not isinstance(cliente_val, Cliente):
                try:
                    # tenta por PK primeiro
                    if isinstance(cliente_val, str) and cliente_val.isdigit():
                        cliente_obj = Cliente.objects.get(pk=int(cliente_val))
                    else:
                        cliente_obj = Cliente.objects.get(nome__iexact=str(cliente_val).strip())
                    cleaned_data['Cliente'] = cliente_obj
                    cleaned_data['cliente'] = cliente_obj
                except Cliente.DoesNotExist:
                    self.add_error('Cliente', 'Cliente não encontrado. Selecione um cliente cadastrado.')
        except Exception:
            pass
        try:
            unidade_val = cleaned_data.get('Unidade') or cleaned_data.get('unidade')
            if unidade_val and not isinstance(unidade_val, Unidade):
                try:
                    if isinstance(unidade_val, str) and unidade_val.isdigit():
                        unidade_obj = Unidade.objects.get(pk=int(unidade_val))
                    else:
                        unidade_obj = Unidade.objects.get(nome__iexact=str(unidade_val).strip())
                    cleaned_data['Unidade'] = unidade_obj
                    cleaned_data['unidade'] = unidade_obj
                except Unidade.DoesNotExist:
                    self.add_error('Unidade', 'Unidade não encontrada. Selecione uma unidade cadastrada.')
        except Exception:
            pass
        box_opcao = cleaned_data.get('box_opcao')
        os_existente = cleaned_data.get('os_existente')
        servico = cleaned_data.get('servico')

        # Se múltiplos serviços foram enviados, definir o primário no campo 'servico' (para satisfazer choices)
        # e manter a lista completa em 'servicos' (campo TextField no modelo)
        if servico and isinstance(servico, str):
            raw = servico
            parts = [p.strip() for p in raw.split(',') if p.strip()] if ',' in raw else [raw.strip()]
            primary = parts[0] if parts else raw.strip()
            # validar que o serviço primário é um dos choices do modelo (rótulos são idênticos aos valores)
            try:
                valid_choices = {v for v, _ in OrdemServico.SERVICO_CHOICES}
            except Exception:
                valid_choices = set()
            if valid_choices and primary not in valid_choices:
                self.add_error('servico', 'Selecione um serviço válido da lista.')
            cleaned_data['servico'] = primary
            cleaned_data['servicos'] = raw

        # Parse dos campos de tanques vinculados a cada serviço (enviados pelo JS)
        try:
            tanques_raw = self.data.get('tanques') or self.data.get('tanques_hidden') or self.data.get('edit_tanques_hidden')
            if tanques_raw and isinstance(tanques_raw, str):
                tanques_list = [t.strip() for t in tanques_raw.split(',') if t.strip()]
            else:
                tanques_list = []
            # Normalizar tokens que representam 'Não aplicável' para string vazia
            normalized = []
            for t in tanques_list:
                low = (t or '').lower().strip()
                if low in ['-', 'n/a', 'na', 'n.a.', 'não aplicável', 'nao aplicavel', 'none']:
                    normalized.append('')
                else:
                    normalized.append(t)
            # Fallback: se ainda estiver vazio, usar campo legado 'tanque'
            if not normalized:
                try:
                    legacy = cleaned_data.get('tanque') or self.data.get('tanque')
                    if isinstance(legacy, str) and legacy.strip():
                        normalized = [legacy.strip()]
                except Exception:
                    pass
            cleaned_data['tanques'] = normalized
        except Exception:
            cleaned_data['tanques'] = []

        if box_opcao == self.EXISTENTE_OS:
            if not os_existente:
                raise forms.ValidationError("Por favor, selecione uma OS existente.")
            try:
                os_obj = OrdemServico.objects.get(pk=int(os_existente))
                cleaned_data['cliente'] = os_obj.cliente
                cleaned_data['unidade'] = os_obj.unidade
            except Exception as e:
                raise forms.ValidationError("Erro ao buscar dados da OS existente.")
        # Não forçar campos de compatibilidade tanque/volume — dados mantidos em cleaned_data['tanques']
        return cleaned_data

    # Salva a Ordem de Serviço
    def save(self, commit=True):
        from django.db import IntegrityError
        instance = super().save(commit=False)
        box_opcao = self.cleaned_data.get('box_opcao')
        os_existente = self.cleaned_data.get('os_existente')

        # Determinar serviço primário (primeiro da lista se for string com vírgulas)
        servico_raw = self.cleaned_data.get('servico') or instance.servico
        if isinstance(servico_raw, str) and ',' in servico_raw:
            servico_primary = servico_raw.split(',')[0].strip()
        else:
            servico_primary = servico_raw

        if box_opcao == self.NOVA_OS:
            ultimo = OrdemServico.objects.order_by('-numero_os').first()
            instance.numero_os = (ultimo.numero_os + 1) if ultimo else 1

        elif box_opcao == self.EXISTENTE_OS and os_existente:
            os_existente_obj = OrdemServico.objects.get(pk=int(os_existente))
            # Copia apenas cliente e unidade da OS existente
            instance.cliente = os_existente_obj.cliente
            instance.unidade = os_existente_obj.unidade
            # Mantém o numero_os da OS existente
            instance.numero_os = os_existente_obj.numero_os

        # Atribuir campos derivados SEMPRE, independente de commit, para funcionar com save(commit=False)
        try:
            full_list = self.cleaned_data.get('servicos')
            if not full_list:
                full_list = servico_raw
            instance.servico = servico_primary or instance.servico
            instance.servicos = full_list
            # Persistir tanques como CSV se fornecidos
            try:
                tanques_list = self.cleaned_data.get('tanques') or []
                if isinstance(tanques_list, list):
                    # filtrar valores vazios e normalizar espaços
                    filtered = [t.strip() for t in tanques_list if t is not None and str(t).strip()]
                    instance.tanques = ', '.join(filtered) if filtered else None
                elif isinstance(tanques_list, str):
                    # normalizar string crua (vinda de fallback)
                    filtered = [t.strip() for t in tanques_list.split(',') if str(t).strip()]
                    instance.tanques = ', '.join(filtered) if filtered else None
            except Exception:
                pass
            # Compatibilidade: volume_tanque não nulo
            try:
                if getattr(instance, 'volume_tanque', None) in [None, '']:
                    instance.volume_tanque = Decimal('0.00')
            except Exception:
                try:
                    instance.volume_tanque = Decimal(0)
                except Exception:
                    pass
        except Exception:
            pass

        if commit:
            try:
                instance.save()
            except IntegrityError as e:
                from django.core.exceptions import ValidationError
                raise ValidationError("Já existe uma Ordem de Serviço com este número e código. Não é possível duplicar.")
        return instance


