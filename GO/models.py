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
        ('LIMPEZA DE TANQUE DE ÁGUA', 'LIMPEZA DE TANQUE DE ÁGUA'),
        ('SERVIÇO DE IRATA', 'SERVIÇO DE IRATA'),
        ('LIMPEZA DE TANQUE DE LAMA', 'LIMPEZA DE TANQUE DE LAMA'),
        ('LIMPEZA DE DUTO E COIFA', 'LIMPEZA DE DUTO E COIFA'),
        ('LIMPEZA DE VASO', 'LIMPEZA DE VASO'),
        ('LIMPEZA MECANIZADA', ' LIMPEZA MECANIZADA'),
        ('LIMPEZA TANQUE DE ÓLEO', 'LIMPEZA TANQUE DE ÓLEO'),
        ('LIMPEZA TANQUE DE CARGA', 'LIMPEZA TANQUE DE CARGA'),
        ('LIMPEZA ROBOTIZADA', 'LIMPEZA ROBOTIZADA'),
        ('LIMPEZA DE DUTOS DE AR CONDICIONADO', 'LIMPEZA DE DUTOS DE AR CONDICIONADO'),
        ('LIMPEZA DE DUTOS DE EXAUSTÃO', 'LIMPEZA DE DUTOS DE EXAUSTÃO'),
        ('LIMPEZA DE COIFA DA COZINHA', 'LIMPEZA DE COIFA DA COZINHA'),
        ('COLETA E ANÁLISE DO AR AMBIENTE', 'COLETA E ANÁLISE DO AR AMBIENTE'),
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

    tag = models.CharField(max_length=3, choices=TAG_CHOICES)
    numero_os = models.IntegerField(unique=True)
    codigo_os = models.CharField(max_length=20, unique=True)
    especificacao = models.TextField()
    data_inicio = models.DateField()
    data_fim = models.DateField(null=True, blank=True)
    dias_de_operacao = models.IntegerField()
    servico = models.CharField(max_length=50, choices=SERVICO_CHOICES)
    metodo = models.CharField(max_length=20, choices=METODO_CHOICES)
    observacao = models.TextField(blank=True)
    pob = models.IntegerField()
    tanque = models.CharField(max_length=50, blank=True)
    volume_tanque = models.DecimalField(max_digits=10, decimal_places=2)
    cliente = models.CharField(max_length=50)
    unidade = models.CharField(max_length=50)
    tipo_operacao = models.CharField(max_length=50, choices=TIPO_OP_CHOICES)
    solicitante = models.CharField(max_length=50)
    coordenador = models.CharField(max_length=50)
    supervisor = models.CharField(max_length=50)
    status_operacao = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Programada')

    # Calculo de dias de operação
    def save(self, *args, **kwargs):
        if self.data_fim and self.data_inicio:
            self.dias_de_operacao = (self.data_fim - self.data_inicio).days
        else:
            self.dias_de_operacao = 0
        super().save(*args, **kwargs)


    def __str__(self):
        return self.codigo_os
