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

    class Meta:
        model = OrdemServico
        exclude = ['codigo_os', 'dias_de_operacao']
        widgets = {
            'tag': forms.Select(attrs={'class': 'form-control'}),
            'numero_os': forms.NumberInput(attrs={'class': 'form-control'}),
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

    def save(self, commit=True):
        instance = super().save(commit=False)
        box_opcao = self.cleaned_data.get('box_opcao')
        
        if box_opcao == self.NOVA_OS:
            # For new OS, generate next number
            ultimo = OrdemServico.objects.order_by('-numero_os').first()
            instance.numero_os = (ultimo.numero_os + 1) if ultimo else 1
        elif box_opcao == self.EXISTENTE_OS:
            # For existing OS, keep the same number as the last one
            ultimo = OrdemServico.objects.order_by('-numero_os').first()
            instance.numero_os = ultimo.numero_os if ultimo else 1
        
        if commit:
            instance.save()
        return instance
