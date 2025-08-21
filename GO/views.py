from django.shortcuts import render
from .models import OrdemServico
from django import forms


def lista_servicos(request):
    servicos = OrdemServico.objects.all()
    return render(request, 'home.html', {'servicos': servicos})

class OrdemServicoForm(forms.ModelForm):
    NOVA_OS = 'nova'
    EXISTENTE_OS = 'existente'
    BOX_CHOICES = [
        (NOVA_OS, 'Nova OS'),
        (EXISTENTE_OS, 'OS já existente'),
    ]
    box_opcao = forms.ChoiceField(choices=BOX_CHOICES, widget=forms.RadioSelect, label="Tipo de OS")

    class Meta:
        model = OrdemServico
        fields = '__all__'

    def save(self, commit=True):
        instance = super().save(commit=False)
        box_opcao = self.cleaned_data.get('box_opcao')
        if box_opcao == self.NOVA_OS:
            ultimo = OrdemServico.objects.order_by('-numero_os').first()
            instance.numero_os = (ultimo.numero_os + 1) if ultimo else 1
        elif box_opcao == self.EXISTENTE_OS:
            ultimo = OrdemServico.objects.order_by('-numero_os').first()
            instance.numero_os = ultimo.numero_os if ultimo else 1
        if commit:
            instance.save()
        return instance
def home(request):
    return render(request, 'home.html')