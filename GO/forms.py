from django import forms
from .models import OrdemServico

class OrdemServicoForm(forms.ModelForm):
    NOVA_OS = 'nova'
    EXISTENTE_OS = 'existente'
    BOX_CHOICES = [
        (NOVA_OS, 'Nova OS'),
        (EXISTENTE_OS, 'OS já existente'),
    ]
    box_opcao = forms.ChoiceField(choices=BOX_CHOICES, widget=forms.RadioSelect, label="Tipo de OS", initial='nova')
    
    os_existente = forms.ChoiceField(
        choices=[],
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="OS Existente"
    )

    class Meta:
        model = OrdemServico
        exclude = ['codigo_os', 'dias_de_operacao']
        widgets = {
            'tag': forms.Select(attrs={'class': 'form-control'}),
            'numero_os': forms.NumberInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
            'especificacao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'data_inicio': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'data_fim': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'servico': forms.Select(attrs={'class': 'form-control'}),
            'metodo': forms.Select(attrs={'class': 'form-control'}),
            'observacao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'pob': forms.NumberInput(attrs={'class': 'form-control'}),
            'tanque': forms.TextInput(attrs={'class': 'form-control'}),
            'volume_tanque': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'cliente': forms.Select(attrs={'class': 'form-control'}),
            'unidade': forms.TextInput(attrs={'class': 'form-control'}),
            'tipo_operacao': forms.Select(attrs={'class': 'form-control'}),
            'solicitante': forms.TextInput(attrs={'class': 'form-control'}),
            'coordenador': forms.TextInput(attrs={'class': 'form-control'}),
            'supervisor': forms.TextInput(attrs={'class': 'form-control'}),
            'status_operacao': forms.Select(attrs={'class': 'form-control'}),
            'link_rdo': forms.URLInput(attrs={'class': 'form-control'}),
            'detalhes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['numero_os'].required = False
        self.fields['numero_os'].widget.attrs['readonly'] = True

        os_choices = [(os.numero_os, f"OS {os.numero_os}") for os in OrdemServico.objects.all().order_by('-numero_os')]
        self.fields['os_existente'].choices = [('', 'Selecione uma OS existente')] + os_choices
        
        
        self.os_objects = {os.numero_os: os for os in OrdemServico.objects.all()}

    def clean(self):
        cleaned_data = super().clean()
        box_opcao = cleaned_data.get('box_opcao')
        os_existente = cleaned_data.get('os_existente')
        
        if box_opcao == self.EXISTENTE_OS and not os_existente:
            raise forms.ValidationError("Por favor, selecione uma OS existente.")
        
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        box_opcao = self.cleaned_data.get('box_opcao')
        os_existente = self.cleaned_data.get('os_existente')
        
        if box_opcao == self.NOVA_OS:
            ultimo = OrdemServico.objects.order_by('-numero_os').first()
            instance.numero_os = (ultimo.numero_os + 1) if ultimo else 1

        elif box_opcao == self.EXISTENTE_OS and os_existente:
            instance.numero_os = int(os_existente)
            

        
        instance.codigo_os = f"{instance.tag}-{instance.numero_os}"

        if commit:
            instance.save()
        return instance
