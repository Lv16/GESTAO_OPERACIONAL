from django import forms
from .models import OrdemServico

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

    # Campo adicional para exibir a tag associada ao serviço
    class Meta:
        model = OrdemServico
        exclude = ['dias_de_operacao']
        widgets = {
            'metodo_secundario': forms.Select(attrs={'class': 'form-control'}),
            'tag': forms.Select(attrs={'class': 'form-control'}),
            'numero_os': forms.NumberInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
            'codigo_os': forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
            'especificacao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'data_inicio': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'data_fim': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'servico': forms.Select(attrs={'class': 'form-control'}),
            'metodo': forms.Select(attrs={'class': 'form-control'}),
            'observacao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'pob': forms.NumberInput(attrs={'class': 'form-control'}),
            'tanque': forms.TextInput(attrs={'class': 'form-control'}),
            'volume_tanque': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'status_comercial': forms.Select(attrs={'class': 'form-control'}),
            'cliente': forms.Select(attrs={'class': 'form-control', 'id': 'id_cliente'}),
            'unidade': forms.Select(attrs={'class': 'form-control', 'id': 'id_unidade'}),
            'tipo_operacao': forms.Select(attrs={'class': 'form-control'}),
            'solicitante': forms.TextInput(attrs={'class': 'form-control'}),
            'coordenador': forms.TextInput(attrs={'class': 'form-control'}),
            'supervisor': forms.TextInput(attrs={'class': 'form-control'}),
            'status_operacao': forms.Select(attrs={'class': 'form-control'}),
            'controle_de_atividades': forms.URLInput(attrs={'class': 'form-control'}),
            'materiais_equipamentos': forms.URLInput(attrs={'class': 'form-control'}),
        }
    # Inicializa o formulário e configura os campos dinâmicos
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['numero_os'].required = False
        self.fields['numero_os'].widget.attrs['readonly'] = True

        # Preenche os campos obrigatórios no self.data se for OS existente ou nova
        if hasattr(self, 'data') and self.data:
            data = self.data.copy()
            box_opcao = data.get('box_opcao')
            os_existente = data.get('os_existente')
            if box_opcao == self.EXISTENTE_OS and os_existente:
                try:
                    os_obj = OrdemServico.objects.get(pk=int(os_existente))
                    data['cliente'] = os_obj.cliente
                    data['unidade'] = os_obj.unidade
                    data['numero_os'] = os_obj.numero_os
                    data['codigo_os'] = os_obj.codigo_os
                    self.data = data
                    # print('DEBUG: Campos obrigatórios injetados no self.data via __init__')
                except Exception as e:
                    # print('DEBUG: Erro ao buscar OS existente no __init__:', e)
                    pass
            elif box_opcao == self.NOVA_OS:
                if 'servico' in data and data['servico']:
                    tag = OrdemServico.SERVICO_TAG_MAP.get(data['servico'])
                    if tag:
                        ultimo = OrdemServico.objects.order_by('-numero_os').first()
                        numero_os = (ultimo.numero_os + 1) if ultimo else 1
                        data['numero_os'] = numero_os
                        data['codigo_os'] = f"{tag}-{numero_os}"
                        self.data = data
                        # print('DEBUG: Campos numero_os e codigo_os injetados para nova OS')

        unique_os = {}
        for os in OrdemServico.objects.all().order_by('-numero_os'):
            if os.numero_os not in unique_os:
                unique_os[os.numero_os] = os
        os_choices = [(os.pk, f"OS {os.numero_os}") for os in unique_os.values()]
        # print('DEBUG os_choices:', os_choices)
        if not os_choices:
            # print('DEBUG: Nenhuma OS encontrada para os_choices!')
            pass
        self.fields['os_existente'].choices = [('', 'Selecione uma OS existente')] + os_choices
        self.os_objects = {os.numero_os: os for os in unique_os.values()}
        # print('DEBUG self.os_objects:', self.os_objects)

    # Associa a tag ao serviço automaticamente ao limpar o formulário
    def clean(self):
        cleaned_data = super().clean()
        box_opcao = cleaned_data.get('box_opcao')
        os_existente = cleaned_data.get('os_existente')
        servico = cleaned_data.get('servico')

        # Associa a tag ao serviço automaticamente
        if servico in OrdemServico.SERVICO_TAG_MAP:
            cleaned_data['tag'] = OrdemServico.SERVICO_TAG_MAP[servico]

        if box_opcao == self.EXISTENTE_OS:
            if not os_existente:
                raise forms.ValidationError("Por favor, selecione uma OS existente.")
            try:
                os_obj = OrdemServico.objects.get(pk=int(os_existente))
                cleaned_data['cliente'] = os_obj.cliente
                cleaned_data['unidade'] = os_obj.unidade
                cleaned_data['codigo_os'] = f"{cleaned_data['tag']}-{os_obj.numero_os}"
            except Exception as e:
                # print('DEBUG: Erro ao buscar OS existente no clean:', e)
                raise forms.ValidationError("Erro ao buscar dados da OS existente.")
        return cleaned_data

    # Salva a Ordem de Serviço, gerando número e código conforme a opção selecionada
    def save(self, commit=True):
        from django.db import IntegrityError
    # print('DEBUG: Entrou no save do OrdemServicoForm')
        instance = super().save(commit=False)
        box_opcao = self.cleaned_data.get('box_opcao')
        os_existente = self.cleaned_data.get('os_existente')
    # print(f'DEBUG: box_opcao={box_opcao}, os_existente={os_existente}')

        if box_opcao == self.NOVA_OS:
            ultimo = OrdemServico.objects.order_by('-numero_os').first()
            instance.numero_os = (ultimo.numero_os + 1) if ultimo else 1
            instance.codigo_os = f"{instance.tag}-{instance.numero_os}"
            # print(f'DEBUG: Criando nova OS: numero_os={instance.numero_os}, codigo_os={instance.codigo_os}')


        elif box_opcao == self.EXISTENTE_OS and os_existente:
            os_existente_obj = OrdemServico.objects.get(pk=int(os_existente))
            # Copia apenas cliente e unidade da OS existente
            instance.cliente = os_existente_obj.cliente
            instance.unidade = os_existente_obj.unidade
            # Mantém o numero_os da OS existente e atualiza codigo_os com nova tag
            instance.numero_os = os_existente_obj.numero_os
            instance.codigo_os = f"{instance.tag}-{instance.numero_os}"
            # print(f'DEBUG: Criando OS baseada em existente: cliente={instance.cliente}, unidade={instance.unidade}, numero_os={instance.numero_os}, codigo_os={instance.codigo_os}')

    # print(f'DEBUG: Campos finais antes de salvar: {instance.__dict__}')
        if commit:
            try:
                instance.save()
                # print('DEBUG: OS salva com sucesso!')
            except IntegrityError as e:
                # print(f'DEBUG: IntegrityError: {e}')
                from django.core.exceptions import ValidationError
                raise ValidationError("Já existe uma Ordem de Serviço com este número e código. Não é possível duplicar.")
        return instance
