from django.db import models

# Create your models here.
class OrdemServico(models.Model):
    TAG_CHOICES = [
        ('LTA', 'LTA'),
        ('SIR', 'SIR'),
        ('LTL', 'LTL'),
        ('LDC', 'LDC'),
        ('LDV', 'LDV'),
        ('LMC', 'LMC'),
        ('LTO', 'LTO'),
        ('LTC', 'LTC'),
        ('LRB', 'LRB'),
        ('LDA', 'LDA'),
        ('LDE', 'LDE'),
        ('LCC', 'LCC'),
        ('CAA', 'CAA'),
    ]

    SERVICO_CHOICES = [
        ('limpeza de tanque de água', 'limpeza de tanque de água'),
        ('serviço de irata', 'serviço de irata'),
        ('limpeza de tanque de lama', 'limpeza de tanque de lama'),
        ('limpeza de duto e coifa', 'limpeza de duto e coifa'),
        ('limpeza de vaso', 'limpeza de vaso'),
        ('limpeza mecanizada', 'limpeza mecanizada'),
        ('limpeza tanque de óleo', 'limpeza tanque de óleo'),
        ('limpeza tanque de carga', 'limpeza tanque de carga'),
        ('limpeza robotizada', 'limpeza robotizada'),
        ('limpeza de dutos de ar condicionado', 'limpeza de dutos de ar condicionado'),
        ('limpeza de dutos de exaustão', 'limpeza de dutos de exaustão'),
        ('limpeza de coifa da cozinha', 'limpeza de coifa da cozinha'),
        ('coleta e análise do ar ambiente', 'coleta e análise do ar ambiente'),
    ]

    TIPO_OP_CHOICES = [
        ('Onshore', 'Onshore'),
        ('Offshore', 'Offshore'),
        ('Spot Onshore', 'Spot Onshore'),
        ('Spot Offshore', 'Spot Offshore'),
    ]

    STATUS_CHOICES = [
        ('Programada', 'Programada'),
        ('Em Andamento', 'Em Andamento'),
        ('Paralizada', 'Paralizada'),
        ('Finalizada', 'Finalizada'),
    ]

    METODO_CHOICES = [
        ('Manual', 'Manual'),
        ('Mecanizada', 'Mecanizada'),
        ('Robotizada', 'Robotizada'),
        ('Roto rooter', 'Roto rooter'),
        ('Demais', 'Demais'),
    ]
    CLIENTE_CHOICES = [
        ('Petrobras', 'Petrobras'),
    ]
    STATUS_COMERCIAL_CHOICES = [
        ('Faturado', 'Faturado'),
        ('Em aberto', 'Em aberto'),
        ('Cancelado', 'Cancelado'),
    ]

    tag = models.CharField(max_length=3, choices=TAG_CHOICES)
    numero_os = models.IntegerField()
    codigo_os = models.CharField(max_length=20)
    especificacao = models.CharField(max_length=255, null=True, blank=True)
    data_inicio = models.DateField()
    data_fim = models.DateField(null=True, blank=True)
    dias_de_operacao = models.IntegerField()
    servico = models.CharField(max_length=50, choices=SERVICO_CHOICES)
    metodo = models.CharField(max_length=20, choices=METODO_CHOICES)
    observacao = models.TextField(blank=True)
    pob = models.IntegerField()
    tanque = models.CharField(max_length=50, blank=True)
    volume_tanque = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cliente = models.CharField(max_length=50, choices=CLIENTE_CHOICES)
    unidade = models.CharField(max_length=50)
    tipo_operacao = models.CharField(max_length=50, choices=TIPO_OP_CHOICES)
    solicitante = models.CharField(max_length=50)
    coordenador = models.CharField(max_length=50)
    supervisor = models.CharField(max_length=50)
    status_operacao = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Programada')
    # Coluna para colocar um botão que leva para o link do RDO
    link_rdo = models.URLField(blank=True, null=True)
    # Coluna para colocar um botão para abrir uma janela com detalhes da operação
    detalhes = models.TextField(blank=True, null=True)
    status_comercial = models.CharField(max_length=20, choices=STATUS_COMERCIAL_CHOICES, default='Em aberto')
    
    # Calculo de dias de operação
    def save(self, *args, **kwargs):
        if self.data_fim and self.data_inicio:
            self.dias_de_operacao = (self.data_fim - self.data_inicio).days
        else:
            self.dias_de_operacao = 0
        super().save(*args, **kwargs)


    def __str__(self):
        return self.codigo_os
