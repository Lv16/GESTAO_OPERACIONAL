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
    
def criar_os(request):
    if request.method == 'POST':
        form = OrdemServicoForm(request.POST)
        if form.is_valid():
            os_instance = form.save(commit=False)
            
            ultimo_numero = OrdemServico.objects.all().order_by('-numero_os').first()
            if ultimo_numero:
                os_instance.numero_os = ultimo_numero.numero_os + 1
            else:
                os_instance.numero_os = 1

            os_instance.codigo_os = f"{os_instance.numero_os}{os_instance.tag}"
            
            os_instance.save()
            return redirect('lista_os')
    else:
        form = OrdemServicoForm()
    
    return render(request, 'home.html', {'form': form})

def home(request):
    return render(request, 'home.html')