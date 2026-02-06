from django.db import models
from deep_translator import GoogleTranslator
from multiselectfield import MultiSelectField
from django.conf import settings
from django.db.models import SET_NULL, Q
from decimal import Decimal
from datetime import datetime, date, timedelta, time as dt_time
from django.core.exceptions import ValidationError
from decimal import Decimal as _D

class Cliente(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    def __str__(self):
        return self.nome
    class Meta:

        verbose_name_plural = 'Clientes'
        ordering = ['nome']
    
class Unidade(models.Model):
    nome = models.CharField(max_length=50, unique=True)
    def __str__(self):
        return self.nome
    
    class Meta:

        verbose_name_plural = "Unidades"
        ordering = ['nome']

class OrdemServico(models.Model):
    SERVICO_CHOICES = [
        ("COLETA DE AR", "COLETA DE AR"),
        ("COLETA DE ÁGUA", "COLETA DE ÁGUA"),
        ("DELINEAMENTO DE ATIVIDADES", "DELINEAMENTO DE ATIVIDADES"),
        ("DESOBSTRUÇÃO DE LINHAS", "DESOBSTRUÇÃO DE LINHAS"),
        ("DESOBSTRUÇÃO DE RALOS", "DESOBSTRUÇÃO DE RALOS"),
        ("EMISSÃO DE FREE FOR FIRE", "EMISSÃO DE FREE FOR FIRE"),
        ("LIMPEZA DE CAIXA D'ÁGUA/BEBEDOURO", "LIMPEZA DE CAIXA D'ÁGUA/BEBEDOURO"),
        ("LIMPEZA DE COIFA", "LIMPEZA DE COIFA"),
        ("LIMPEZA DE COSTADO", "LIMPEZA DE COSTADO"),
        ("LIMPEZA DE DUTO", "LIMPEZA DE DUTO"),
        ("LIMPEZA DE DUTO, COIFA", "LIMPEZA DE DUTO, COIFA"),
        ("LIMPEZA DE DUTO, COIFA, COLETA DE AR", "LIMPEZA DE DUTO, COIFA, COLETA DE AR"),
        ("LIMPEZA DE SILO", "LIMPEZA DE SILO"),
        ("LIMPEZA DE SILO CIMENTO", "LIMPEZA DE SILO CIMENTO"),
        ("LIMPEZA DE TANQUE DE ÁGUA", "LIMPEZA DE TANQUE DE ÁGUA"),
        ("LIMPEZA DE TANQUE DE ÁGUA PRODUZIDA", "LIMPEZA DE TANQUE DE ÁGUA PRODUZIDA"),
        ("LIMPEZA DE TANQUE DE CARGA", "LIMPEZA DE TANQUE DE CARGA"),
        ("LIMPEZA DE TANQUE DE DIESEL", "LIMPEZA DE TANQUE DE DIESEL"),
        ("LIMPEZA DE TANQUE DE DRENO", "LIMPEZA DE TANQUE DE DRENO"),
        ("LIMPEZA DE TANQUE DE ÓLEO", "LIMPEZA DE TANQUE DE ÓLEO"),
        ("LIMPEZA DE TANQUE DE PRODUTO QUÍMICO", "LIMPEZA DE TANQUE DE PRODUTO QUÍMICO"),
        ("LIMPEZA DE TANQUE DE LAMA", "LIMPEZA DE TANQUE DE LAMA"),
        ("LIMPEZA DE TANQUE SEWAGE", "LIMPEZA DE TANQUE SEWAGE"),
        ("LIMPEZA DE VASO", "LIMPEZA DE VASO"),
        ("LIMPEZA DE TANQUE OFFSPEC", "LIMPEZA DE TANQUE OFFSPEC"),
        ("LIMPEZA TROCADOR DE CALOR", "LIMPEZA TROCADOR DE CALOR"),
        ("LIMPEZA QUÍMICA DE TUBULAÇÃO", "LIMPEZA QUÍMICA DE TUBULAÇÃO"),
        ("LIMPEZA DE REDE", "LIMPEZA DE REDE"),
        ("LIMPEZA HVAC", "LIMPEZA HVAC"),
        ("MOBILIZAÇÃO/DESMOBILIZAÇÃO DE TANQUE", "MOBILIZAÇÃO/DESMOBILIZAÇÃO DE TANQUE"),
        ("SERVIÇO DE MONITORAMENTO OCUPACIONAL", "SERVIÇO DE MONITORAMENTO OCUPACIONAL"),
        ("SERVIÇO DE RÁDIO PROTEÇÃO", "SERVIÇO DE RÁDIO PROTEÇÃO"),
        ("VISITA TÉCNICA", "VISITA TÉCNICA"),
    ]

    TIPO_OP_CHOICES = [
        ('Onshore', 'Onshore'),
        ('Offshore', 'Offshore'),
        ('Spot', 'Spot'),
    ]

    STATUS_CHOICES = [
        ('Programada', 'Programada'),
        ('Em Andamento', 'Em Andamento'),
        ('Paralizada', 'Paralizada'),
        ('Finalizada', 'Finalizada'),
        ('Cancelada', 'Cancelada'),
    ]

    METODO_CHOICES = [
        ('Manual', 'Manual'),
        ('Mecanizada', 'Mecanizada'),
        ('Robotizada', 'Robotizada'),
        ('N/A', 'N/A')
    ]
    
    STATUS_COMERCIAL_CHOICES = [
        ('Em aberto', 'Em aberto'),
        ('Não Realizada', 'Não Realizada'),
        ('Periódica', 'Periódica'),
        ('Realizada', 'Realizada'),
    ]

    MATERIAL = [
        ('A Bordo', 'A Bordo'),
        ('Embarcar', 'Embarcar'),
        ('Desembarcar', 'Desembarcar'),
    ]

    FUNCOES = [
        ('SUPERVISOR', 'SUPERVISOR'),
        ('SUPERVISOR IRATA', 'SUPERVISOR IRATA'),
        ('ELETRICISTA', 'ELETRICISTA'),
        ('TÉCNICO DE SEGURANÇA', 'TÉCNICO DE SEGURANÇA'),
        ('AJUDANTE', 'AJUDANTE'),
        ('RESGATISTA', 'RESGATISTA'),
        ('MECÂNICO', 'MECÂNICO'),
    ]

    COORDENADORES = [
        ('', '--- Selecione um coordenador ---'),
        ('JORGE VINICIUS SIQUEIRA LUCAS SILVA', 'JORGE VINICIUS SIQUEIRA LUCAS SILVA'),
        ('RICARDO PIRES DE MOURA JUNIOR', 'RICARDO PIRES DE MOURA JUNIOR'),
        ('KETLEY BARBOSA', 'KETLEY BARBOSA'),
        ('THALES MENEZES', 'THALES MENEZES'),
        ('MARCOS CORREIA', 'MARCOS CORREIA'),
        ('GABRIEL DELAIA', 'GABRIEL DELAIA'),
        ('AILTON OLIVEIRA', 'AILTON OLIVEIRA'),
        ('ANDRE SANTIAGO', 'ANDRE SANTIAGO'),
        ('JONATHAN LIMA LOUZADA', 'JONATHAN LIMA LOUZADA'),
        ('C-SAFETY / LOCAÇÃO', 'C-SAFETY / LOCAÇÃO'),
        ("MARCOS DELGADO", "MARCOS DELGADO"),
    ]

    STATUS_PLANEJAMENTO = [
        ('Pendente', 'Pendente'),
        ('Em andamento', 'Em andamento'),
        ('Concluído', 'Concluído'),
    ]

    STATUS_DATABOOK = [
        ('Não Aplicável', 'Não Aplicável'),
        ('Em Andamento', 'Em Andamento'),
        ('Finalizado', 'Finalizado'),
    ]

    numero_os = models.IntegerField()
    especificacao = models.CharField(max_length=255, null=True, blank=True)
    data_inicio_frente = models.DateField(null=True, blank=True)
    data_fim_frente = models.DateField(null=True, blank=True)
    dias_de_operacao_frente = models.IntegerField(default=0)
    data_inicio = models.DateField()
    data_fim = models.DateField(null=True, blank=True)
    dias_de_operacao = models.IntegerField()
    servico = models.CharField(max_length=100, choices=SERVICO_CHOICES)
    servicos = models.TextField(null=True, blank=True)
    tanques = models.TextField(null=True, blank=True)
    turno = models.CharField(max_length=20, null=True, blank=True, choices=[('Diurno', 'Diurno'), ('Noturno', 'Noturno')])
    metodo = models.CharField(max_length=20, choices=METODO_CHOICES)
    metodo_secundario = models.CharField(max_length=20, choices=METODO_CHOICES, null=True, blank=True)
    observacao = models.TextField(blank=True)
    pob = models.IntegerField()
    tanque = models.CharField(max_length=50, blank=True)
    volume_tanque = models.DecimalField(max_digits=10, decimal_places=2)
    Cliente = models.ForeignKey('Cliente', on_delete=models.PROTECT, default="")
    Unidade = models.ForeignKey('Unidade', on_delete=models.PROTECT, default="")
    tipo_operacao = models.CharField(max_length=50, choices=TIPO_OP_CHOICES)
    solicitante = models.CharField(max_length=50)
    coordenador = models.CharField(max_length=50, choices = COORDENADORES, null = True)
    supervisor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,blank=True, on_delete=models.PROTECT, related_name='ordens_supervisionadas')
    status_operacao = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Programada')
    status_geral = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Programada', null=True, blank=True)
    status_comercial = models.CharField(max_length=20, choices=STATUS_COMERCIAL_CHOICES, default='Em aberto')
    po = models.CharField(max_length=10, null=True, blank=True)
    material = models.CharField(max_length=20, choices=MATERIAL, null=True, blank=True)
    frente = models.CharField(max_length=100, null=True, blank=True)
    status_planejamento = models.CharField(max_length=50, null=True, blank=True, choices=STATUS_PLANEJAMENTO, default="Pendente")
    status_databook = models.TextField(null = True, blank = True, choices = STATUS_DATABOOK)
    numero_certificado = models.CharField(max_length = 100, null = True, blank = True)
    @property
    def cliente(self):
        try:
            val = getattr(self, 'Cliente', None)
            if val is None:
                return ''
            try:
                return val.nome
            except Exception:
                return str(val)
        except Exception:
            return ''

    @cliente.setter
    def cliente(self, value):
        try:
            if value is None:
                self.Cliente = None
                return
            from .models import Cliente as ClienteModel
        except Exception:
            self.Cliente = value
            return
        try:
            if isinstance(value, ClienteModel):
                self.Cliente = value
                return
        except Exception:
            pass
        try:
            if isinstance(value, (int,)) or (isinstance(value, str) and value.isdigit()):
                self.Cliente = ClienteModel.objects.get(pk=int(value))
                return
        except Exception:
            pass
        try:
            self.Cliente = ClienteModel.objects.get(nome__iexact=str(value).strip())
            return
        except Exception:
            self.Cliente = value

    @property
    def unidade(self):
        try:
            val = getattr(self, 'Unidade', None)
            if val is None:
                return ''
            try:
                return val.nome
            except Exception:
                return str(val)
        except Exception:
            return ''

    @unidade.setter
    def unidade(self, value):
        try:
            if value is None:
                self.Unidade = None
                return
            from .models import Unidade as UnidadeModel
        except Exception:
            self.Unidade = value
            return
        try:
            if isinstance(value, UnidadeModel):
                self.Unidade = value
                return
        except Exception:
            pass
        try:
            if isinstance(value, (int,)) or (isinstance(value, str) and value.isdigit()):
                self.Unidade = UnidadeModel.objects.get(pk=int(value))
                return
        except Exception:
            pass
        try:
            self.Unidade = UnidadeModel.objects.get(nome__iexact=str(value).strip())
            return
        except Exception:
            self.Unidade = value

    def calc_hh_disponivel_cumulativo(self):
        try:
            rdo1 = self.rdos.filter(rdo__in=['1', '01']).order_by('pk').first()
            if not rdo1:
                rdo1 = self.rdos.order_by('data_inicio').first()
            if not rdo1:
                return None

            start = getattr(rdo1, 'data_inicio', None)
            if not start:
                return None
            try:
                if isinstance(start, datetime):
                    start_date = start.date()
                else:
                    start_date = start
            except Exception:
                start_date = start

            days = (date.today() - start_date).days
            if days < 0:
                days = 0
            hours = 11 * int(days)
            return timedelta(hours=hours)
        except Exception:
            return None
        
    def calc_hh_disponivel_cumulativo_time(self):
        td = self.calc_hh_disponivel_cumulativo()
        if not td:
            return None
        try:
            total_seconds = int(td.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            hours_mod = hours % 24
            return dt_time(hour=hours_mod, minute=minutes)
        except Exception:
            return None

    def save(self, *args, **kwargs):
        try:
            if getattr(self, 'data_inicio_frente', None) and getattr(self, 'data_fim_frente', None):
                try:
                    delta_days = (self.data_fim_frente - self.data_inicio_frente).days
                    self.dias_de_operacao_frente = delta_days + 1 if delta_days >= 0 else 0
                except Exception:
                    self.dias_de_operacao_frente = 0
            else:
                if getattr(self, 'dias_de_operacao_frente', None) is None:
                    self.dias_de_operacao_frente = 0
        except Exception:
            try:
                self.dias_de_operacao_frente = 0
            except Exception:
                pass
        try:
            if getattr(self, 'data_inicio', None) and getattr(self, 'data_fim', None):
                try:
                    delta_days = (self.data_fim - self.data_inicio).day
                    self.dias_de_operacao = delta_days + 1 if delta_days >= 0 else 0
                except Exception:
                    self.dias_de_operacao = 0
            else:
                if getattr(self, 'dias_de_operacao', None) is None:
                    self.dias_de_operacao = 0
        except Exception:
            try:
                self.dias_de_operacao = 0
            except Exception:
                pass
        try:
            if getattr(self, 'volume_tanque', None) in [None, '']:
                try:
                    self.volume_tanque = Decimal('0.00')
                except Exception:
                    self.volume_tanque = 0
        except Exception:
            pass
        super().save(*args, **kwargs)

    class CoordenadorCanonical(models.Model):
        canonical_name = models.CharField(max_length=150, unique=True)
        variants = models.JSONField(default=list, blank=True)
        notes = models.TextField(blank=True, null=True)
        created_at = models.DateTimeField(auto_now_add=True)
        updated_at = models.DateTimeField(auto_now=True)

        class Meta:

            verbose_name_plural = 'Coordenadores Canônicos'

        def __str__(self):
            return self.canonical_name

    class Meta:
        ordering = ["-data_inicio", "numero_os"]

        verbose_name_plural = "Ordens de Serviço"

class Pessoa(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    funcao = models.CharField(max_length=100, choices=OrdemServico.FUNCOES)

    def __str__(self):
        return self.nome

    class Meta:

        verbose_name_plural = "Pessoas"
        ordering = ['nome']

class Funcao(models.Model):
    nome = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nome

    class Meta:

        verbose_name_plural = "Funções"

class RDO(models.Model):

    ATIVIDADES_CHOICES = [
        ('abertura pt', 'Abertura PT / Opening pt'),
        ('acesso ao tanque', 'Acesso ao Tanque / Tank access'),
        ('aferição de pressão arterial', 'Aferição de Pressão Arterial / Arterial Pressure Measurement'),
        ('almoço', 'Almoço / Lunch'),
        ('avaliação inicial da área de trabalho', 'Avaliação Inicial da Área de Trabalho / Pre-setup of the work area'),
        ('conferência do material e equipamento no container', 'Conferência do Material e Equipamento no Container / Checking the material and equipment in the container'),
        ('coleta de água', 'Coleta de Água / Water sampling'),
        ('dds', 'DDS / Work Safety Dialog'),
        ("Desobstrução de linhas", " Desobstrução de linhas / Drain line clearing "),
        ("Drenagem do tanque ", " Drenagem do tanque / Tank draining "),
        ('em espera', 'Em Espera / Stand-by'),
        ('acesso ao tanque', 'Acesso ao Tanque / Tank access'),
        ('equipe chegou no aeroporto', 'Equipe Chegou no Aeroporto / Team arrived at the airport'),
        ('vôo com destino a unidade', 'Vôo com Destino à Unidade / Flight to unity'),
        ('vôo postergado', 'Vôo Postergado / Flight postponed'),
        ('triagem', 'Triagem / Security screening'),
        ('check-in, pesagem, briefing', 'Check-in, Pesagem, Briefing / Check-in, weighing, briefing'),
        ('saída da base', 'Saída da Base / Departure from base'),
        ('equipe se apresenta ao responsável da unidade', 'Equipe se Apresenta ao Responsável da Unidade / The team presents itself to the person in charge of the unit'),
        ('instalação/preparação/montagem', 'Instalação/Preparação/Montagem / Setup'),
        ('jantar', 'Jantar / Dinner'),
        ('limpeza da área', 'Limpeza da Área / Housekeep'),
        ('treinamento de abandono', 'Treinamento de Abandono / Drill'),
        ('alarme real', 'Alarme Real / Real alarm'),
        ('instrução de segurança', 'Instrução de Segurança / Security instructions'),
        ('apoio à equipe de bordo nas atividades da unidade', 'Apoio à Equipe de Bordo nas Atividades da Unidade / Support to the onboard team in unit activities'),
        ('desmobilização do material - dentro do tanque', 'Desmobilização do Material - Dentro do Tanque / Material demobilization - Inside the tank'),
        ('desmobilização do material - fora do tanque', 'Desmobilização do Material - Fora do Tanque / Material demobilization - Outside the tank'),
        ('inventário', 'Inventário / Inventory'),
        ('mobilização de material - dentro do tanque', 'Mobilização de Material - Dentro do Tanque / Material mobilization - Inside the tank'),
        ('mobilização de material - fora do tanque', 'Mobilização de Material - Fora do Tanque / Material mobilization - Outside the tank'),
        ('realização de simulado de resgate', 'Realização de Simulado de Resgate / Execution of rescue drill'),
        ('reunião', 'Reunião / Meeting'),
        ('limpeza e higienização de coifa', 'Limpeza e Higienização de Coifa / Cleaning and sanitization of the hood'),
        ('limpeza de dutos', 'Limpeza de Dutos / Duct cleaning'),
        ('coleta e análise de ar', 'Coleta e Análise de Ar / Air sampling and analysis'),
        ('manutenção de equipamentos - dentro do tanque', 'Manutenção de Equipamentos - Dentro do Tanque / Maintenance equipments - Inside the tank'),
        ('manutenção de equipamentos - fora do tanque', 'Manutenção de Equipamentos - Fora do Tanque / Maintenance equipments - Outside the tank'),
        ('jateamento', 'Jateamento / Blasting'),
        ("chegada na unidade", "chegada na unidade / Arrival at the unit"),
        ("chegada a bordo", "chegada a bordo / Arrival at the port"),
        ("operação com robô", "operação com robô / Robot operation"),
        ("Renovação de PT/PET", "Renovação de PT/PET / PT/PET Renewal"),
        ("limpeza mecânica", "limpeza mecânica / Mechanical cleaning"),
        ("teste tubo a tubo", "teste tubo a tubo / Tube-to-tube test"),
        ("teste hidrostático", "teste hidrostático / Hydrostatic test"),
        ("treinamento na unidade", "treinamento na unidade / Training at the unit"),
        ("desmontagem de equipamento", "desmontagem de equipamento / Equipment disassembly"),
        ("montagem de equipamento", "montagem de equipamento / Equipment assembly"),
        ("Limpeza do convès", "Limpeza do convès / Deck cleaning"),
        ('Limpeza de caixa d\'água / bebedouro', 'Limpeza de caixa d\'água / bebedouro / Water tank / water cooler cleaning'),
    ]

    TURNOS_CHOICES = [
        ('Manhã', 'Manhã'),
        ('Tarde', 'Tarde'),
        ('Noite', 'Noite'),
    ]
    SENTIDO_LIMPEZA = [
        ('vante > ré', 'vante > ré'),
        ('ré > vante', 'ré > vante'),
        ('bombordo > boreste', 'bombordo > boreste'),
        ('boreste < bombordo', 'boreste < bombordo')
    ]

    ordem_servico = models.ForeignKey('OrdemServico', on_delete=models.PROTECT, null=True, blank=True, related_name='rdos')
    data = models.DateField(blank=True, null=True)
    data_inicio = models.DateField(blank=True, null=True)
    rdo = models.CharField(max_length=20, null=True, blank=True)
    turno = models.CharField(max_length=20, null=True, blank=True, choices=[('Diurno', 'Diurno'), ('Noturno', 'Noturno')])
    contrato_po = models.CharField(max_length=30, null=True, blank=True)
    exist_pt = models.BooleanField(choices=[(True, 'Sim'), (False, 'Não')], null=True, blank=True)
    select_turnos = MultiSelectField(choices=TURNOS_CHOICES, blank=True)
    pt_manha = models.CharField(max_length=50, null=True, blank=True)
    pt_tarde = models.CharField(max_length=50, null=True, blank=True)
    pt_noite = models.CharField(max_length=50, null=True, blank=True)
    tipo_tanque = models.CharField(max_length=50, choices = [('Salão', 'Salão'), ('Compartimento', 'Compartimento')], null=True, blank=True)
    numero_compartimentos = models.IntegerField(choices = [(i, str(i)) for i in range(1, 15)], null=True, blank=True)
    nome_tanque = models.CharField(max_length=30, null=True, blank=True)
    tanque_codigo = models.CharField(max_length=20, null=True, blank=True)
    volume_tanque_exec = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    servico_exec = models.CharField(max_length=100, null=True, blank=True)
    metodo_exec = models.CharField(max_length=20, null=True, blank=True, choices=[('Manual', 'Manual'), ('Mecanizada', 'Mecanizada')])
    gavetas = models.IntegerField(null=True, blank=True)
    patamares = models.IntegerField(null=True, blank=True)
    confinado = models.BooleanField(choices=[(True, 'Sim'), (False, 'Não')], default=False)
    entrada_confinado = models.TimeField(null=True, blank=True)
    saida_confinado = models.TimeField(null=True, blank=True)
    entrada_confinado_1 = models.TimeField(null=True, blank=True)
    saida_confinado_1 = models.TimeField(null=True, blank=True)
    entrada_confinado_2 = models.TimeField(null=True, blank=True)
    saida_confinado_2 = models.TimeField(null=True, blank=True)
    entrada_confinado_3 = models.TimeField(null=True, blank=True)
    saida_confinado_3 = models.TimeField(null=True, blank=True)
    entrada_confinado_4 = models.TimeField(null=True, blank=True)
    saida_confinado_4 = models.TimeField(null=True, blank=True)
    entrada_confinado_5 = models.TimeField(null=True, blank=True)
    saida_confinado_5 = models.TimeField(null=True, blank=True)
    entrada_confinado_6 = models.TimeField(null=True, blank=True)
    saida_confinado_6 = models.TimeField(null=True, blank=True)
    ec_times_json = models.TextField(null=True, blank=True)
    operadores_simultaneos = models.IntegerField(null=True, blank=True)
    h2s_ppm = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    lel = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    co_ppm = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    o2_percent = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    sentido_limpeza = models.CharField(max_length=30,null=True,blank=True, choices=SENTIDO_LIMPEZA)
    tempo_uso_bomba = models.DurationField(null=True, blank=True)
    quantidade_bombeada = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    bombeio = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    total_liquido = models.IntegerField(null=True, blank=True)
    tambores = models.IntegerField(null=True, blank=True, editable=True)
    total_solidos = models.IntegerField(null=True, blank=True)
    total_residuos = models.IntegerField(null=True, blank=True)
    observacoes_rdo_pt = models.TextField(null=True, blank=True)
    observacoes_rdo_en = models.TextField(null=True, blank=True)
    ciente_observacoes_pt = models.TextField(null=True, blank=True)
    ciente_observacoes_en = models.TextField(null=True, blank=True)
    fotos_img = models.ImageField(upload_to='rdos/', null=True, blank=True)
    fotos_1 = models.ImageField(upload_to='rdos/', null=True, blank=True)
    fotos_2 = models.ImageField(upload_to='rdos/', null=True, blank=True)
    fotos_3 = models.ImageField(upload_to='rdos/', null=True, blank=True)
    fotos_4 = models.ImageField(upload_to='rdos/', null=True, blank=True)
    fotos_5 = models.ImageField(upload_to='rdos/', null=True, blank=True)
    fotos_json = models.TextField(null=True, blank=True)
    compartimentos_avanco_json = models.TextField(null=True, blank=True)
    planejamento_pt = models.TextField(null=True, blank=True)
    planejamento_en = models.TextField(null=True, blank=True)
    pessoas = models.ForeignKey(Pessoa, on_delete=models.PROTECT, null=True, blank=True, related_name='rdos', default=None)
    funcoes = models.CharField(max_length=300, null=True, blank=True)
    membros = models.TextField(null=True, blank=True)
    funcoes_list = models.TextField(null=True, blank=True)
    servico_rdo = models.CharField(max_length=100, null=True, blank=True, choices=OrdemServico.SERVICO_CHOICES)
    total_n_efetivo_confinado = models.IntegerField(null=True, blank=True, default=0)
    ensacamento = models.IntegerField(null=True, blank=True)
    percentual_avanco = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    percentual_avanco_cumulativo = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    total_hh_cumulativo_real = models.TimeField(blank=True, null=True)
    total_hh_frente_real = models.TimeField(blank=True, null=True)
    hh_disponivel_cumulativo = models.TimeField(blank=True, null=True)
    ultimo_status = models.CharField(max_length=500, blank=True, null=True)
    percentual_limpeza_fina = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    percentual_limpeza_fina_cumulativo = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    limpeza_mecanizada_diaria = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,)
    limpeza_mecanizada_cumulativa = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    limpeza_fina_diaria = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    limpeza_fina_cumulativa = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    percentual_limpeza_diario = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    percentual_limpeza_diario_cumulativo = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ensacamento_cumulativo = models.IntegerField(blank=True, null=True)
    ensacamento_previsao = models.IntegerField(blank=True, null=True)
    percentual_ensacamento = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    icamento = models.IntegerField(blank=True, null=True)
    icamento_cumulativo = models.IntegerField(blank=True, null=True)
    icamento_previsao = models.IntegerField(blank=True, null=True)
    percentual_icamento = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    cambagem = models.IntegerField(blank=True, null=True)
    cambagem_cumulativo = models.IntegerField(blank=True, null=True)
    cambagem_previsao = models.IntegerField(blank=True, null=True)
    percentual_cambagem = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    pob = models.IntegerField(blank=True, null=True)

    def compute_total_hh_frente_real(self):
        try:
            if not getattr(self, 'ordem_servico', None) or not getattr(self, 'data', None):
                return None

            from .models import RDOAtividade
            ativ_qs = RDOAtividade.objects.filter(rdo__ordem_servico=self.ordem_servico, rdo__data=self.data)
            if not ativ_qs.exists():
                return None

            inicios = list(ativ_qs.exclude(inicio__isnull=True).values_list('inicio', flat=True))
            fins = list(ativ_qs.exclude(fim__isnull=True).values_list('fim', flat=True))
            if not inicios or not fins:
                return None

            inicio_time = min(inicios)
            fim_time = max(fins)

            inicio = datetime.combine(self.data, inicio_time)
            fim = datetime.combine(self.data, fim_time)
            total_horas = fim - inicio

            try:
                atividades_nomes = list(ativ_qs.values_list('atividade', flat=True))
                nomes_norm = [str(x or '').strip().lower() for x in atividades_nomes]
                if any(n in ('almoço', 'almoco') for n in nomes_norm):
                    total_horas -= timedelta(hours=1)
                if any(n == 'jantar' for n in nomes_norm):
                    total_horas -= timedelta(hours=1)
            except Exception:
            
                pass

            if total_horas.total_seconds() < 0:
                total_horas = timedelta(0)

            horas = int(total_horas.seconds // 3600)
            minutos = int((total_horas.seconds % 3600) // 60)
            try:
                self.total_hh_frente_real = dt_time(hour=horas, minute=minutos)
            except Exception:
                self.total_hh_frente_real = None
            return self.total_hh_frente_real
        except Exception:
            return None
    
    def calc_hh_disponivel_cumulativo(self):
        try:
            
            if getattr(self, 'hh_disponivel_cumulativo', None):
                t = self.hh_disponivel_cumulativo
                try:
                    secs = (getattr(t, 'hour', 0) * 3600) + (getattr(t, 'minute', 0) * 60) + (getattr(t, 'second', 0) or 0)
                    return timedelta(seconds=secs)
                except Exception:
                    return None

            if getattr(self, 'total_hh_cumulativo_real', None):
                t = self.total_hh_cumulativo_real
                try:
                    secs = (getattr(t, 'hour', 0) * 3600) + (getattr(t, 'minute', 0) * 60) + (getattr(t, 'second', 0) or 0)
                    return timedelta(seconds=secs)
                except Exception:
                    return None

            ord_obj = getattr(self, 'ordem_servico', None)
            if ord_obj is not None and hasattr(ord_obj, 'calc_hh_disponivel_cumulativo'):
                try:
                    res = ord_obj.calc_hh_disponivel_cumulativo()
                    if isinstance(res, timedelta):
                        return res
                except Exception:
                    pass
        except Exception:
            return None
        return None

    def calc_hh_disponivel_cumulativo_time(self):
        try:
            td = self.calc_hh_disponivel_cumulativo()
            if not td:
                return None
            total_seconds = int(td.total_seconds())
            hours = (total_seconds // 3600) % 24
            minutes = (total_seconds % 3600) // 60
            return dt_time(hour=int(hours), minute=int(minutes))
        except Exception:
            return None
    
    def calcula_percentuais(self):
        try:
            if self.ensacamento and self.ensacamento_cumulativo and self.ensacamento_previsao:
                self.percentual_ensacamento = (self.ensacamento_cumulativo / self.ensacamento_previsao) * 100
        except Exception:
            pass
        try:
            if self.icamento and self.icamento_cumulativo and self.icamento_previsao:
                self.percentual_icamento = (self.icamento_cumulativo / self.icamento_previsao) * 100
        except Exception:
            pass
        try:
            if self.cambagem and self.cambagem_cumulativo and self.cambagem_previsao:
                self.percentual_cambagem = (self.cambagem_cumulativo / self.cambagem_previsao) * 100
        except Exception:
            pass
        try:
            try:
               
                if getattr(self, 'percentual_limpeza_diario', None) not in [None, '']:
                    try:
                        daily_limpeza = float(self.percentual_limpeza_diario)
                    except Exception:
                        daily_limpeza = 0.0
                elif getattr(self, 'limpeza_mecanizada_diaria', None) not in [None, '']:
                    try:
                        daily_limpeza = float(self.limpeza_mecanizada_diaria)
                    except Exception:
                        daily_limpeza = 0.0
                else:
                    daily_limpeza = 0.0
            except Exception:
                daily_limpeza = 0.0
            try:

                if getattr(self, 'limpeza_mecanizada_cumulativa', None) not in [None, '']:
                    try:
                        from decimal import Decimal as _D, ROUND_HALF_UP as _RH
                        limpeza_acu = _D(str(self.limpeza_mecanizada_cumulativa)).quantize(_D('0.01'), rounding=_RH)
                    except Exception:
                        limpeza_acu = None
                else:
                    limpeza_acu = None
            except Exception:
                limpeza_acu = None
            try:
                from decimal import Decimal as _D, ROUND_HALF_UP as _RH
                if getattr(self, 'percentual_limpeza_fina_diario', None) not in [None, '']:
                    try:
                        val = _D(str(self.percentual_limpeza_fina_diario))
                        self.percentual_limpeza_fina = val.quantize(_D('0.01'), rounding=_RH)
                    except Exception:
                        pass
                elif getattr(self, 'limpeza_fina_diaria', None) not in [None, '']:
                    try:
                        val = _D(str(self.limpeza_fina_diaria))
                        self.percentual_limpeza_fina = val.quantize(_D('0.01'), rounding=_RH)
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                if getattr(self, 'limpeza_fina_cumulativa', None) not in [None, '']:
                    try:
                        from decimal import Decimal as _D, ROUND_HALF_UP as _RH
                        val = _D(str(self.limpeza_fina_cumulativa))
                        self.percentual_limpeza_fina_cumulativo = val.quantize(_D('0.01'), rounding=_RH)
                    except Exception:
                        pass
            except Exception:
                pass

            pesos = {
                'percentual_icamento': 7.0,
                'percentual_ensacamento': 7.0,
                'percentual_cambagem': 5.0,
                'percentual_limpeza_diario': 70.0,
                'percentual_limpeza_fina': 6.0,
            }
            def valor(p):
                try:
                    if p == 'percentual_limpeza_diario':
                        v = getattr(self, 'percentual_limpeza_diario', None)
                        if v in (None, ''):
                            v = getattr(self, 'limpeza_mecanizada_diaria', None)
                    else:
                        v = getattr(self, p, None)
                    if v is None or v == '':
                        return 0.0
                    return float(v)
                except Exception:
                    return 0.0

            total = 0.0
            for campo, peso in pesos.items():
                total += valor(campo) * peso
            percentual_calc = total / 100.0
            try:
                from decimal import Decimal as _D, ROUND_HALF_UP as _RH
                pct = _D(str(round(percentual_calc, 2)))
                if pct < _D('0'):
                    pct = _D('0')
                if pct > _D('100'):
                    pct = _D('100')
                pct_q = pct.quantize(_D('0.01'), rounding=_RH)
                self.percentual_avanco = pct_q
            except Exception:
                try:
                    val = max(0, min(100, int(round(percentual_calc))))
                    from decimal import Decimal as _D
                    self.percentual_avanco = _D(str(val))
                except Exception:
                    pass
            try:
                if limpeza_acu is not None and hasattr(self, 'limpeza_mecanizada_cumulativa'):
                    self.limpeza_mecanizada_cumulativa = limpeza_acu
            except Exception:
                pass
        except Exception:
            pass

    def compute_limpeza_from_compartimentos(self):
        try:
            import json as _json
            from decimal import Decimal as _D
            raw = getattr(self, 'compartimentos_avanco_json', None)
            if not raw:
                return None

            parsed = None
            try:
                parsed = _json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                parsed = None

            if not isinstance(parsed, dict):
                return None

            sum_mec = 0.0
            count = 0
            for k, v in parsed.items():
                try:
                    if isinstance(v, dict):
                        mv = v.get('mecanizada', 0)
                    else:
                        mv = 0
                    if mv is None:
                        mv = 0
                    if isinstance(mv, str):
                        mv_s = mv.strip().replace('%', '')
                        try:
                            mv_val = float(mv_s) if mv_s != '' else 0.0
                        except Exception:
                            mv_val = 0.0
                    else:
                        try:
                            mv_val = float(mv)
                        except Exception:
                            mv_val = 0.0
                    if mv_val > 0:
                        sum_mec += mv_val
                        count += 1
                except Exception:
                    continue

            if count > 0:
                avg = round((sum_mec / float(count)), 2)
                dec = _D(str(avg))
                try:
                    self.limpeza_mecanizada_diaria = dec
                except Exception:
                    pass
                try:
                    self.percentual_limpeza_diario = dec
                except Exception:
                    pass
                return dec
            else:
                return None
        except Exception:
            return None

    def compute_limpeza_cumulativa(self):
        try:
            if not getattr(self, 'ordem_servico', None):
                return None

            tank_code = None
            tank_n_comp = None
            try:
                for rt in (self.tanques.all() or []):
                    if getattr(rt, 'tanque_codigo', None):
                        tank_code = str(rt.tanque_codigo).strip()
                        if getattr(rt, 'numero_compartimentos', None):
                            try:
                                tank_n_comp = int(rt.numero_compartimentos)
                            except Exception:
                                tank_n_comp = None
                        break
            except Exception:
                tank_code = None
                tank_n_comp = None

            n_comp = None
            if tank_n_comp:
                n_comp = tank_n_comp
            else:
                n_comp = getattr(self, 'numero_compartimentos', None)
                try:
                    n_comp = int(n_comp) if n_comp is not None else 0
                except Exception:
                    n_comp = 0

            if not n_comp or n_comp <= 0:
                return None

            sums = {str(i): 0 for i in range(1, n_comp + 1)}

            qs = self.__class__.objects.filter(ordem_servico=self.ordem_servico)
            if getattr(self, 'data', None):
                qs = qs.filter(data__lte=self.data)
            if getattr(self, 'pk', None):
                qs = qs.exclude(pk=self.pk)

            if tank_code:
                qs = qs.filter(tanques__tanque_codigo__iexact=tank_code).distinct()

            import json as _json
            for prior in qs.order_by('data', 'pk'):
                raw = getattr(prior, 'compartimentos_avanco_json', None)
                if not raw:
                    continue
                try:
                    parsed = _json.loads(raw) if isinstance(raw, str) else raw
                except Exception:
                    parsed = None
                if not isinstance(parsed, dict):
                    continue
                for i in range(1, n_comp + 1):
                    key = str(i)
                    item = parsed.get(key) if isinstance(parsed, dict) else None
                    if not item:
                        continue
                    try:
                        mv = item.get('mecanizada', 0) if isinstance(item, dict) else 0
                        if mv is None:
                            mv = 0
                        if isinstance(mv, str):
                            mv = mv.strip().replace('%', '')
                            mv = float(mv) if mv != '' else 0.0
                        else:
                            mv = float(mv)
                    except Exception:
                        mv = 0.0
                    try:
                        sums[key] = sums.get(key, 0) + float(mv)
                    except Exception:
                        pass

            try:
                raw_self = getattr(self, 'compartimentos_avanco_json', None)
                if raw_self:
                    parsed_self = _json.loads(raw_self) if isinstance(raw_self, str) else raw_self
                else:
                    parsed_self = None
            except Exception:
                parsed_self = None
            if isinstance(parsed_self, dict):
                for i in range(1, n_comp + 1):
                    key = str(i)
                    item = parsed_self.get(key)
                    if not item:
                        continue
                    try:
                        mv = item.get('mecanizada', 0) if isinstance(item, dict) else 0
                        if mv is None:
                            mv = 0
                        if isinstance(mv, str):
                            mv = mv.strip().replace('%', '')
                            mv = float(mv) if mv != '' else 0.0
                        else:
                            mv = float(mv)
                    except Exception:
                        mv = 0.0
                    try:
                        sums[key] = sums.get(key, 0) + float(mv)
                    except Exception:
                        pass

            caps = []
            for i in range(1, n_comp + 1):
                key = str(i)
                try:
                    v = float(sums.get(key, 0) or 0)
                except Exception:
                    v = 0.0
                if v < 0:
                    v = 0.0
                if v > 100.0:
                    v = 100.0
                caps.append(v)

            if not caps:
                return None

            avg = sum(caps) / float(len(caps))
            try:
                from decimal import Decimal as _D, ROUND_HALF_UP as _RH
                dec = _D(str(round(avg, 2)))
                dec_q = dec.quantize(_D(' '), rounding=_RH)
                self.limpeza_mecanizada_cumulativa = dec_q
            except Exception:
                pass
            try:
                from decimal import Decimal as _D, ROUND_HALF_UP as _RH
                self.percentual_limpeza_diario_cumulativo = _D(str(round(avg, 2))).quantize(_D('0.01'), rounding=_RH)
            except Exception:
                pass
            return avg
        except Exception:
            return None

    def validate_tanque_compartimentos_consistency(self):
        try:
            tank_code = None
            tank_n_comp = None
            try:
                for rt in (self.tanques.all() or []):
                    if getattr(rt, 'tanque_codigo', None):
                        tank_code = str(rt.tanque_codigo).strip()
                        if getattr(rt, 'numero_compartimentos', None):
                            try:
                                tank_n_comp = int(rt.numero_compartimentos)
                            except Exception:
                                tank_n_comp = None
                        break
            except Exception:
                tank_code = None
                tank_n_comp = None

            if not tank_code:
                return None

            rt_model = self.tanques.model
            conflicts = rt_model.objects.filter(rdo__ordem_servico=self.ordem_servico,
                                                tanque_codigo__iexact=tank_code)

            if getattr(self, 'pk', None):
                conflicts = conflicts.exclude(rdo_id=self.pk)

            diffs = conflicts.exclude(numero_compartimentos__in=[tank_n_comp, None]) if tank_n_comp is not None else conflicts.exclude(numero_compartimentos__isnull=True)
            if diffs.exists():
                ids = list(diffs.values_list('rdo_id', flat=True)[:5])
                raise ValidationError(f"Inconsistência: outro(s) RDO(s) desta OS para o tanque '{tank_code}' têm um número de compartimentos diferente (ex.: RDO ids {ids}). Não é permitido alterar o número de compartimentos para o mesmo tanque.")

            if tank_n_comp is None:
                prior_with_value = conflicts.filter(numero_compartimentos__isnull=False).order_by('rdo__data', 'rdo_id').first()
                if prior_with_value and getattr(prior_with_value, 'numero_compartimentos', None):
                    try:
                        inferred = int(prior_with_value.numero_compartimentos)
                        for rt in self.tanques.all():
                            if not getattr(rt, 'numero_compartimentos', None):
                                try:
                                    rt.numero_compartimentos = inferred
                                except Exception:
                                    pass
                        try:
                            self.numero_compartimentos = inferred
                        except Exception:
                            pass
                    except Exception:
                        pass
            else:
                try:
                    if getattr(self, 'numero_compartimentos', None) is None:
                        self.numero_compartimentos = int(tank_n_comp)
                    else:
                        if int(self.numero_compartimentos) != int(tank_n_comp):
                            raise ValidationError(f"O número de compartimentos do RDO ({self.numero_compartimentos}) diverge do número definido para o tanque '{tank_code}' ({tank_n_comp}). Não é permitido alterar.")
                except ValidationError:
                    raise
                except Exception:
                    pass
        except ValidationError:
            raise
        except Exception:
            return None

    def add_tank(self, tank_payload):
        from django.db import transaction
        from django.core.exceptions import ValidationError
        def _to_int(v):
            try:
                if v is None or v == '':
                    return None
                if isinstance(v, str):
                    v = v.strip().replace('%', '').replace(',', '.')
                return int(float(v))
            except Exception:
                return None

        def _to_decimal(v):
            try:
                if v is None or v == '':
                    return None
                if isinstance(v, str):
                    v = v.strip().replace('%', '').replace(',', '.')
                return Decimal(str(v))
            except Exception:
                return None

        def _to_bool(v):
            try:
                if v is None or v == '':
                    return None
                if isinstance(v, bool):
                    return v
                s = str(v).strip().lower()
                if s in ('1', 'true', 't', 'sim', 'yes', 'y', 'vante', 'vante>ré', 'vante > ré'):
                    return True
                if s in ('0', 'false', 'f', 'nao', 'não', 'no', 'n', 'ré', 'ré>vante', 'ré > vante', 're', 're>vante'):
                    return False
                try:
                    return bool(int(float(s)))
                except Exception:
                    return None
            except Exception:
                return None

        def _to_jsontext(v):
            try:
                if v is None or v == '':
                    return None
                import json as _json
                if isinstance(v, (dict, list)):
                    return _json.dumps(v)
                s = str(v).strip()
                try:
                    _json.loads(s)
                    return s
                except Exception:
                    return s
            except Exception:
                return None

        data = dict(tank_payload or {})

        from django.apps import apps as _apps
        try:
            TanqueModel = _apps.get_model(self._meta.app_label, 'Tanque')
        except Exception:
            TanqueModel = None
        tanq = None
        try:
            tid = data.get('tanque_id') or data.get('tank_id') or data.get('tanque')
            if tid not in (None, ''):
                try:
                    tid_int = int(str(tid).strip())
                    if TanqueModel is not None:
                        tanq = TanqueModel.objects.filter(pk=tid_int).first()
                except Exception:
                    tanq = None
        except Exception:
            tanq = None
        if tanq is None:
            try:
                code = data.get('tanque_codigo') or data.get('tanque_code')
                if code not in (None, ''):
                    if TanqueModel is not None:
                        tanq = TanqueModel.objects.filter(codigo__iexact=str(code).strip()).first()
            except Exception:
                tanq = None
        fields = {
            'tanque_codigo': data.get('tanque_codigo') or data.get('tanque_code') or None,
            'nome_tanque': data.get('tanque_nome') or data.get('nome_tanque') or None,
            'tipo_tanque': data.get('tipo_tanque') or None,
            'numero_compartimentos': _to_int(data.get('numero_compartimento') or data.get('numero_compartimentos')),
            'gavetas': _to_int(data.get('gavetas')),
            'patamares': _to_int(data.get('patamar') or data.get('patamares')),
            'volume_tanque_exec': _to_decimal(data.get('volume_tanque_exec')),
            'servico_exec': data.get('servico_exec') or None,
            'metodo_exec': data.get('metodo_exec') or None,
            'espaco_confinado': data.get('espaco_confinado') or None,
            'operadores_simultaneos': _to_int(data.get('operadores_simultaneos')),
            'h2s_ppm': _to_decimal(data.get('h2s_ppm')),
            'lel': _to_decimal(data.get('lel')),
            'co_ppm': _to_decimal(data.get('co_ppm')),
            'o2_percent': _to_decimal(data.get('o2_percent')),
            'total_n_efetivo_confinado': _to_int(data.get('total_n_efetivo_confinado')),
            'sentido_limpeza': data.get('sentido_limpeza'),
            'tempo_bomba': _to_decimal(data.get('tempo_bomba')),
            'ensacamento_dia': _to_int(data.get('ensacamento_dia')),
            'icamento_dia': _to_int(data.get('icamento_dia')),
            'cambagem_dia': _to_int(data.get('cambagem_dia')),
            'ensacamento_cumulativo': _to_int(data.get('ensacamento_cumulativo') or data.get('ensacamento_acu')),
            'icamento_cumulativo': _to_int(data.get('icamento_cumulativo') or data.get('icamento_acu')),
            'cambagem_cumulativo': _to_int(data.get('cambagem_cumulativo') or data.get('cambagem_acu')),
            'ensacamento_prev': _to_int(data.get('ensacamento_prev')),
            'icamento_prev': _to_int(data.get('icamento_prev')),
            'cambagem_prev': _to_int(data.get('cambagem_prev')),
            'tambores_dia': _to_int(data.get('tambores_dia')),
            'residuos_solidos': _to_decimal(data.get('residuos_solidos')),
            'residuos_totais': _to_decimal(data.get('residuos_totais')),
            'bombeio': _to_decimal(data.get('bombeio')),
            'total_liquido': _to_int(data.get('total_liquido') or data.get('residuo_liquido') or data.get('residuo')),
            'total_liquido_cumulativo': _to_int(data.get('total_liquido_cumulativo') or data.get('total_liquido_acu') or data.get('residuo_liquido_cumulativo') or data.get('residuo_liquido_acu')),
            'residuos_solidos_cumulativo': _to_decimal(data.get('residuos_solidos_cumulativo') or data.get('residuos_solidos_acu')),
            'avanco_limpeza': data.get('avanco_limpeza') or None,
            'avanco_limpeza_fina': data.get('avanco_limpeza_fina') or None,
            'percentual_limpeza_diario': _to_decimal(data.get('percentual_limpeza_diario')),
            'percentual_limpeza_fina': _to_decimal(data.get('percentual_limpeza_fina')),
            'percentual_limpeza_fina_diario': _to_decimal(data.get('percentual_limpeza_fina_diario')),
            'percentual_limpeza_cumulativo': _to_decimal(data.get('percentual_limpeza_cumulativo')),
            'percentual_limpeza_fina_cumulativo': _to_decimal(data.get('percentual_limpeza_fina_cumulativo')),
            'percentual_ensacamento': _to_decimal(data.get('percentual_ensacamento')),
            'percentual_icamento': _to_decimal(data.get('percentual_icamento')),
            'percentual_cambagem': _to_decimal(data.get('percentual_cambagem')),
            'percentual_avanco': _to_decimal(data.get('percentual_avanco')),
            'compartimentos_avanco_json': _to_jsontext(data.get('compartimentos_avanco_json')),
        }

        try:
            if fields.get('sentido_limpeza') is None and getattr(self, 'sentido_limpeza', None) is not None:
                fields['sentido_limpeza'] = getattr(self, 'sentido_limpeza')
        except Exception:
            pass

        try:
            if tanq is not None:
                if not fields.get('tanque_codigo') and getattr(tanq, 'codigo', None):
                    fields['tanque_codigo'] = str(tanq.codigo)
                if not fields.get('nome_tanque') and getattr(tanq, 'nome', None):
                    fields['nome_tanque'] = str(tanq.nome)
                if not fields.get('tipo_tanque') and getattr(tanq, 'tipo', None):
                    fields['tipo_tanque'] = str(tanq.tipo)
                if fields.get('numero_compartimentos') in (None, '') and getattr(tanq, 'numero_compartimentos', None) is not None:
                    try:
                        fields['numero_compartimentos'] = int(tanq.numero_compartimentos)
                    except Exception:
                        pass
                if fields.get('gavetas') in (None, '') and getattr(tanq, 'gavetas', None) is not None:
                    try:
                        fields['gavetas'] = int(tanq.gavetas)
                    except Exception:
                        pass
                if fields.get('patamares') in (None, '') and getattr(tanq, 'patamares', None) is not None:
                    try:
                        fields['patamares'] = int(tanq.patamares)
                    except Exception:
                        pass
                if fields.get('volume_tanque_exec') in (None, '') and getattr(tanq, 'volume', None) is not None:
                    try:
                        fields['volume_tanque_exec'] = Decimal(str(tanq.volume))
                    except Exception:
                        pass
        except Exception:
            pass

        try:
            with transaction.atomic():
                tank = RdoTanque.objects.create(rdo=self, **fields)
                try:
                    self.validate_tanque_compartimentos_consistency()
                except ValidationError:
                    raise
        except ValidationError:
            raise
        except Exception:
            raise

        return tank

    def save(self, *args, **kwargs):
        self.validate_tanque_compartimentos_consistency()

        try:
            if getattr(self, 'total_hh_frente_real', None) in (None, ''):
                try:
                    self.compute_total_hh_frente_real()
                except Exception:
                    pass
        except Exception:
            pass

        if getattr(self, 'comentario_pt', None):
            try:
                if not getattr(self, 'comentario_en', None) or not str(self.comentario_en).strip():
                    self.comentario_en = GoogleTranslator(source='pt', target='en').translate(self.comentario_pt)
            except Exception:
                self.comentario_en = getattr(self, 'comentario_en', '')
        if self.tipo_tanque == 'Salão':
                self.numero_compartimentos = None
                self.gavetas = None
                self.patamares = None
        if self.observacoes_rdo_pt:
            try:
                if not getattr(self, 'observacoes_rdo_en', None) or not str(self.observacoes_rdo_en).strip():
                    self.observacoes_rdo_en = GoogleTranslator(source='pt', target='en').translate(self.observacoes_rdo_pt)
            except Exception:
                self.observacoes_rdo_en = getattr(self, 'observacoes_rdo_en', None)
        if self.planejamento_pt:
            try:
                if not getattr(self, 'planejamento_en', None) or not str(self.planejamento_en).strip():
                    self.planejamento_en = GoogleTranslator(source='pt', target='en').translate(self.planejamento_pt)
            except Exception:
                self.planejamento_en = getattr(self, 'planejamento_en', None)

        try:
            has_daily = False
            try:
                if getattr(self, 'limpeza_mecanizada_diaria', None) not in (None, ''):
                    has_daily = True
                elif getattr(self, 'percentual_limpeza_diario', None) not in (None, ''):
                    has_daily = True
            except Exception:
                has_daily = False
            if not has_daily:
                self.compute_limpeza_from_compartimentos()
        except Exception:
            pass

        try:
            self.compute_limpeza_cumulativa()
        except Exception:
            pass

        try:
            import json as _json
            fotos_paths = []
            for attr in ('fotos_img', 'fotos_1', 'fotos_2', 'fotos_3', 'fotos_4', 'fotos_5'):
                try:
                    ff = getattr(self, attr, None)
                except Exception:
                    ff = None
                if not ff:
                    continue
                try:
                    name = getattr(ff, 'name', None) or str(ff)
                    if name:
                        name = str(name).replace('\\', '/').lstrip('/')
                        if name not in fotos_paths:
                            fotos_paths.append(name)
                except Exception:
                    continue
            try:
                self.fotos_json = _json.dumps(fotos_paths, ensure_ascii=False)
            except Exception:
                self.fotos_json = str(fotos_paths)
        except Exception:
            pass

        try:
            ord_obj = getattr(self, 'ordem_servico', None)
            hh_time = None
            if ord_obj is not None:
                try:
                    if hasattr(ord_obj, 'calc_hh_disponivel_cumulativo_time'):
                        hh_time = ord_obj.calc_hh_disponivel_cumulativo_time()
                    else:
                        td = ord_obj.calc_hh_disponivel_cumulativo() if hasattr(ord_obj, 'calc_hh_disponivel_cumulativo') else None
                        if isinstance(td, timedelta):
                            total_seconds = int(td.total_seconds())
                            hours = (total_seconds // 3600) % 24
                            minutes = (total_seconds % 3600) // 60
                            hh_time = dt_time(hour=int(hours), minute=int(minutes))
                except Exception:
                    hh_time = None

            if hh_time is None:
                try:
                    hh_time = self.calc_hh_disponivel_cumulativo_time()
                except Exception:
                    hh_time = None

            try:
                if getattr(self, 'hh_disponivel_cumulativo', None) in (None, '') and hh_time is not None:
                    self.hh_disponivel_cumulativo = hh_time
            except Exception:
                pass
        except Exception:
            pass

        super().save(*args, **kwargs)
    
    @property
    def fotos_list(self):
        out = []
        try:
            for attr in ('fotos_1','fotos_2','fotos_3','fotos_4','fotos_5'):
                try:
                    val = getattr(self, attr, None)
                    if val:
                        out.append(val)
                except Exception:
                    continue
            try:
                if getattr(self, 'fotos_img', None):
                    out.insert(0, getattr(self, 'fotos_img'))
            except Exception:
                pass
        except Exception:
            return []
        return out

    @property
    def fotos(self):
        import json
        try:
            if self.fotos_json:
                try:
                    parsed = json.loads(self.fotos_json)
                    if isinstance(parsed, (list, tuple)):
                        return [str(x) for x in parsed if x]
                except Exception:
                    pass
            urls = []
            try:
                if getattr(self, 'fotos_img', None):
                    fi = getattr(self, 'fotos_img')
                    try:
                        url = fi.url if hasattr(fi, 'url') else str(fi)
                        urls.append(url)
                    except Exception:
                        urls.append(str(fi))
            except Exception:
                pass
            for attr in ('fotos_1','fotos_2','fotos_3','fotos_4','fotos_5'):
                try:
                    ff = getattr(self, attr, None)
                    if ff:
                        try:
                            url = ff.url if hasattr(ff, 'url') else str(ff)
                            urls.append(url)
                        except Exception:
                            urls.append(str(ff))
                except Exception:
                    continue
            return urls
        except Exception:
            return []
    @property
    def total_atividade_min(self):
        def _dur_minutes(a):
            try:
                if not (a.inicio and a.fim):
                    return 0
                s = (getattr(a.inicio, 'hour', 0) * 3600) + (getattr(a.inicio, 'minute', 0) * 60) + (getattr(a.inicio, 'second', 0) or 0)
                e = (getattr(a.fim, 'hour', 0) * 3600) + (getattr(a.fim, 'minute', 0) * 60) + (getattr(a.fim, 'second', 0) or 0)
                diff = e - s
                if diff < 0:
                    diff += 24 * 3600
                return int(round(diff / 60.0))
            except Exception:
                return 0

        try:
            return int(sum(_dur_minutes(a) for a in self.atividades_rdo.all()))
        except Exception:
            return 0

    @property
    def total_confinado_min(self):
        def _min(t):
            try:
                return t.hour * 60 + t.minute if t else None
            except Exception:
                return None

        try:
            pares = []
            for i in range(1, 7):
                e = getattr(self, f'entrada_confinado_{i}', None)
                s = getattr(self, f'saida_confinado_{i}', None)
                em = _min(e); sm = _min(s)
                if em is not None and sm is not None:
                    d = sm - em
                    if d < 0:
                        d += 24 * 60
                    if d > 0:
                        pares.append(d)
            if pares:
                return int(sum(pares))
            em = _min(getattr(self, 'entrada_confinado', None))
            sm = _min(getattr(self, 'saida_confinado', None))
            if em is not None and sm is not None:
                d = sm - em
                if d < 0:
                    d += 24 * 60
                return int(max(0, d))
        except Exception:
            return 0
        return 0

    @property
    def total_abertura_pt_min(self):
        def _dur_minutes(a):
            try:
                if not (a.inicio and a.fim):
                    return 0
                s = (getattr(a.inicio, 'hour', 0) * 3600) + (getattr(a.inicio, 'minute', 0) * 60) + (getattr(a.inicio, 'second', 0) or 0)
                e = (getattr(a.fim, 'hour', 0) * 3600) + (getattr(a.fim, 'minute', 0) * 60) + (getattr(a.fim, 'second', 0) or 0)
                diff = e - s
                if diff < 0:
                    diff += 24 * 3600
                return int(round(diff / 60.0))
            except Exception:
                return 0

        try:
            try:
                qs = self.atividades_rdo.filter(
                    Q(atividade__iexact='abertura pt') | (Q(atividade__icontains='renov') & Q(atividade__icontains='pt'))
                )
            except Exception:
                qs = self.atividades_rdo.filter(atividade__in=['abertura pt'])
            return int(sum(_dur_minutes(a) for a in qs))
        except Exception:
            return 0

    @property
    def total_atividades_efetivas_min(self):

        ATIVIDADES_EFETIVAS = [
            'conferência do material e equipamento no container', 'Conferência do Material e Equipamento no Container / Checking the material and equipment in the container',
            'Desobstrução de linhas', 'Desobstrução de linhas / Drain line clearing',
            'Drenagem do tanque', 'Drenagem do tanque / Tank draining',
            'acesso ao tanque', 'Acesso ao Tanque / Tank access',
            'instalação/preparação/montagem', 'Instalação/Preparação/Montagem / Setup',
            'mobilização de material - dentro do tanque', 'Mobilização de Material - Dentro do Tanque / Material mobilization - Inside the tank',
            'mobilização de material - fora do tanque', 'Mobilização de Material - Fora do Tanque / Material mobilization - Outside the tank',
            'desmobilização do material - dentro do tanque', 'Desmobilização do Material - Dentro do Tanque / Material demobilization - Inside the tank',
            'desmobilização do material - fora do tanque', 'Desmobilização do Material - Fora do Tanque / Material demobilization - Outside the tank',
            'avaliação inicial da área de trabalho', 'Avaliação Inicial da Área de Trabalho / Pre-setup of the work area',
            'teste tubo a tubo', 'teste tubo a tubo / Tube-to-tube test',
            'teste hidrostático', 'teste hidrostático / Hydrostatic test',
            'limpeza mecânica', 'limpeza mecânica / Mechanical cleaning',
            'Limpeza de caixa d\'água / bebedouro', 'Limpeza de caixa d\'água / bebedouro / Water tank / water cooler cleaning',
            'operação com robô', 'operação com robô / Robot operation',
            'coleta e análise de ar', 'Coleta e Análise de Ar / Air sampling and analysis',
            'limpeza de dutos', 'Limpeza de Dutos / Duct cleaning',
            'coleta de água', 'Coleta de Água / Water sampling'
        ]

        def _dur_minutes(a):
            try:
                if not (a.inicio and a.fim):
                    return 0
                s = (getattr(a.inicio, 'hour', 0) * 3600) + (getattr(a.inicio, 'minute', 0) * 60) + (getattr(a.inicio, 'second', 0) or 0)
                e = (getattr(a.fim, 'hour', 0) * 3600) + (getattr(a.fim, 'minute', 0) * 60) + (getattr(a.fim, 'second', 0) or 0)
                diff = e - s
                if diff < 0:
                    diff += 24 * 3600
                return int(round(diff / 60.0))
            except Exception:
                return 0

        try:
            qs = self.atividades_rdo.filter(atividade__in=ATIVIDADES_EFETIVAS)
            total = sum(_dur_minutes(a) for a in qs)
            return int(max(0, total))
        except Exception:
            return 0

    @property
    def total_atividades_nao_efetivas_fora_min(self):
        try:
            ATIVIDADES_EFETIVAS = [
                'conferência do material e equipamento no container', 'Conferência do Material e Equipamento no Container / Checking the material and equipment in the container',
                'Desobstrução de linhas', 'Desobstrução de linhas / Drain line clearing',
                'Drenagem do tanque', 'Drenagem do tanque / Tank draining',
                'acesso ao tanque', 'Acesso ao Tanque / Tank access',
                'instalação/preparação/montagem', 'Instalação/Preparação/Montagem / Setup',
                'mobilização de material - dentro do tanque', 'Mobilização de Material - Dentro do Tanque / Material mobilization - Inside the tank',
                'mobilização de material - fora do tanque', 'Mobilização de Material - Fora do Tanque / Material mobilization - Outside the tank',
                'desmobilização do material - dentro do tanque', 'Desmobilização do Material - Dentro do Tanque / Material demobilization - Inside the tank',
                'desmobilização do material - fora do tanque', 'Desmobilização do Material - Fora do Tanque / Material demobilization - Outside the tank',
                'avaliação inicial da área de trabalho', 'Avaliação Inicial da Área de Trabalho / Pre-setup of the work area',
                'teste tubo a tubo', 'teste tubo a tubo / Tube-to-tube test',
                'teste hidrostático', 'teste hidrostático / Hydrostatic test',
                'limpeza mecânica', 'limpeza mecânica / Mechanical cleaning',
                'Limpeza de caixa d\'água / bebedouro', 'Limpeza de caixa d\'água / bebedouro / Water tank / water cooler cleaning',
                'operação com robô', 'operação com robô / Robot operation',
                'coleta e análise de ar', 'Coleta e Análise de Ar / Air sampling and analysis',
                'limpeza de dutos', 'Limpeza de Dutos / Duct cleaning',
                'coleta de água', 'Coleta de Água / Water sampling'
            ]
            def _dur_minutes(a):
                try:
                    if not (a.inicio and a.fim):
                        return 0
                    s = (getattr(a.inicio, 'hour', 0) * 3600) + (getattr(a.inicio, 'minute', 0) * 60) + (getattr(a.inicio, 'second', 0) or 0)
                    e = (getattr(a.fim, 'hour', 0) * 3600) + (getattr(a.fim, 'minute', 0) * 60) + (getattr(a.fim, 'second', 0) or 0)
                    diff = e - s
                    if diff < 0:
                        diff += 24 * 3600
                    return int(round(diff / 60.0))
                except Exception:
                    return 0

            nao_efetivas_qs = self.atividades_rdo.exclude(atividade__in=ATIVIDADES_EFETIVAS)
            total = sum(_dur_minutes(a) for a in nao_efetivas_qs)
            try:
                lunch_names = set(['almoço', 'almoco', 'almôco', 'jantar'])
                lunch_min = 0
                for a in self.atividades_rdo.all():
                    try:
                        name = (getattr(a, 'atividade', '') or '').strip().lower()
                        if name in lunch_names:
                            lunch_min += _dur_minutes(a)
                    except Exception:
                        continue
                total = max(0, int(total) - int(lunch_min))
            except Exception:
                pass
            return int(max(0, total))
        except Exception:
            try:
                return max(0, int(self.total_atividade_min - self.total_atividades_efetivas_min))
            except Exception:
                return 0

    def __str__(self):
        return f"RDO {self.rdo}" if self.rdo else f"RDO {self.pk}"

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['ordem_servico', 'rdo'], name='unique_ordemservico_rdo')
        ]

class RDOMembroEquipe(models.Model):
    rdo = models.ForeignKey('RDO', on_delete=models.CASCADE, related_name='membros_equipe', null=True, blank=True)
    pessoa = models.ForeignKey('Pessoa', on_delete=models.SET_NULL, null=True, blank=True, related_name='participacoes_rdo')
    nome = models.CharField(max_length=100, null=True, blank=True)
    funcao = models.CharField(max_length=100, null=True, blank=True)
    em_servico = models.BooleanField(default=True)
    ordem = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        label = None
        try:
            label = self.pessoa.nome if self.pessoa else self.nome
        except Exception:
            label = self.nome
        return f"{label or 'Membro'} - {self.funcao or ''} (RDO {self.rdo_id})"

    class Meta:
        ordering = ['ordem', 'id']

        verbose_name_plural = 'Membros da Equipe do RDO'

class RDOAtividade(models.Model):
    rdo = models.ForeignKey(RDO, on_delete=models.CASCADE, related_name='atividades_rdo')
    ordem = models.PositiveSmallIntegerField(default=0, blank=True, null=True)
    atividade = models.CharField(max_length=100, choices=RDO.ATIVIDADES_CHOICES, blank=True, null=True)
    inicio = models.TimeField(null=True, blank=True)
    fim = models.TimeField(null=True, blank=True)
    comentario_pt = models.TextField(null=True, blank=True)
    comentario_en = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['ordem']
        unique_together = ('rdo', 'ordem')

        verbose_name_plural = "Atividades de RDO"

    def save(self, *args, **kwargs):
        if getattr(self, 'comentario_pt', None):
            try:
                from deep_translator import GoogleTranslator
                if not getattr(self, 'comentario_en', None) or not str(self.comentario_en).strip():
                    self.comentario_en = GoogleTranslator(source='pt', target='en').translate(self.comentario_pt)
            except Exception:
                self.comentario_en = getattr(self, 'comentario_en', '')
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Atividade {self.ordem} - {self.get_atividade_display()} (RDO {self.rdo_id})"

    @property
    def dias_a_bordo_frente(self):
        try:
            if self.ordem_servico and getattr(self.ordem_servico, 'data_inicio_frente', None):
                return (date.today() - self.ordem_servico.data_inicio_frente).days
        except Exception:
            return None
        return None
    
    def save(self, *args, **kwargs):
       
        try:
            previous = None
            if self.pk:
                try:
                    previous = self.__class__.objects.get(pk=self.pk)
                except self.__class__.DoesNotExist:
                    previous = None

            for field in self._meta.get_fields():
                if not hasattr(field, 'name'):
                    continue
                name = field.name
                if not name.endswith('_frente'):
                    continue

                op_name = name.replace('_frente', '_op')
                try:
                    op_field = self._meta.get_field(op_name)
                except Exception:
                    continue

                new_frente = getattr(self, name, None)
                old_frente = getattr(previous, name, None) if previous else None

                if isinstance(op_field, models.DecimalField):
                    try:
                        new_frente_val = Decimal(new_frente) if new_frente is not None else Decimal(0)
                    except Exception:
                        new_frente_val = Decimal(0)
                    try:
                        old_frente_val = Decimal(old_frente) if old_frente is not None else Decimal(0)
                    except Exception:
                        old_frente_val = Decimal(0)
                    try:
                        base_op = Decimal(getattr(previous, op_name, None)) if previous and getattr(previous, op_name, None) is not None else Decimal(getattr(self, op_name, 0) or 0)
                    except Exception:
                        base_op = Decimal(0)

                    delta = new_frente_val - old_frente_val
                    setattr(self, op_name, base_op + delta)

                elif isinstance(op_field, models.IntegerField):
                    try:
                        new_frente_val = int(new_frente) if new_frente is not None else 0
                    except Exception:
                        new_frente_val = 0
                    try:
                        old_frente_val = int(old_frente) if old_frente is not None else 0
                    except Exception:
                        old_frente_val = 0
                    try:
                        base_op = int(getattr(previous, op_name, None)) if previous and getattr(previous, op_name, None) is not None else int(getattr(self, op_name, 0) or 0)
                    except Exception:
                        base_op = 0

                    delta = new_frente_val - old_frente_val
                    setattr(self, op_name, base_op + delta)

                elif isinstance(op_field, models.FloatField):
                    try:
                        new_frente_val = float(new_frente) if new_frente is not None else 0.0
                    except Exception:
                        new_frente_val = 0.0
                    try:
                        old_frente_val = float(old_frente) if old_frente is not None else 0.0
                    except Exception:
                        old_frente_val = 0.0
                    try:
                        base_op = float(getattr(previous, op_name, None)) if previous and getattr(previous, op_name, None) is not None else float(getattr(self, op_name, 0) or 0)
                    except Exception:
                        base_op = 0.0

                    delta = new_frente_val - old_frente_val
                    setattr(self, op_name, base_op + delta)
                else:
                    continue
        except Exception:
            pass

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Relatorio_tecnico {self.pk}"

class Formulario_de_inspeção(models.Model):
    responsável = models.CharField(max_length=100, null=True, blank=True)
    equipamentos = models.ForeignKey('Equipamentos', on_delete=models.PROTECT, null=True, blank=True, related_name='formularios_de_inspecao')
    data_inspecao_material = models.DateField(blank=True, null=True)
    local_inspecao = models.CharField(max_length=100, null=True, blank=True)
    previsao_retorno = models.DateField(blank=True, null=True)
    fotos = models.ImageField(upload_to='fotos_formulario_inspecao/', null=True, blank=True)

class Modelo(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    fabricante = models.CharField(max_length=100, null=True, blank=True)
    descricao = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return self.nome

    class Meta:

        verbose_name_plural = "Modelos de Equipamento"

class Equipamentos(models.Model):
    modelo = models.ForeignKey('Modelo', on_delete=models.PROTECT, null=True, blank=True, related_name='equipamentos')
    modelo_fk = models.ForeignKey('Modelo', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    fabricante = models.CharField(max_length=100, null=True, blank=True)
    descricao = models.CharField(max_length=100, null=True, blank=True)
    numero_serie = models.CharField(max_length=100, null=True, blank=True)
    numero_tag = models.CharField(max_length=100, null=True, blank=True)
    cliente = models.CharField(max_length=100, null=True, blank=True)
    embarcacao = models.CharField(max_length=100, null=True, blank=True)
    numero_os = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        try:
            if self.modelo:
                return str(self.modelo)
        except Exception:
            pass
        return self.numero_serie or self.numero_tag or f"Equipamento {self.pk}"

    def save(self, *args, **kwargs):
        try:
            src_model = self.modelo_fk or self.modelo
            if src_model is not None:
                try:
                    if (not getattr(self, 'fabricante', None) or str(self.fabricante).strip() == '') and getattr(src_model, 'fabricante', None):
                        self.fabricante = src_model.fabricante
                except Exception:
                    pass
                try:
                    if (not getattr(self, 'descricao', None) or str(self.descricao).strip() == '') and getattr(src_model, 'descricao', None):
                        desc = str(src_model.descricao)
                        max_len = self._meta.get_field('descricao').max_length or len(desc)
                        self.descricao = desc[:max_len]
                except Exception:
                    pass
        except Exception:
            pass
        super().save(*args, **kwargs)

    class Meta:

        verbose_name_plural = "Equipamentos"

class EquipamentoFoto(models.Model):
    equipamento = models.ForeignKey('Equipamentos', on_delete=models.CASCADE, related_name='fotos_equipamento')
    foto = models.ImageField(upload_to='fotos_equipamento/', null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Foto {self.pk} - Equipamento {self.equipamento_id}"

    class Meta:

        verbose_name_plural = 'Fotos de Equipamento'

class RdoTanque(models.Model):
    from django.utils import timezone

    SENTIDO_VANTE_RE = 'vante > ré'
    SENTIDO_RE_VANTE = 'ré > vante'
    SENTIDO_BOMBORDO_BORESTE = 'bombordo > boreste'
    SENTIDO_BORESTE_BOMBORDO = 'boreste < bombordo'

    SENTIDO_CHOICES = (
        (SENTIDO_VANTE_RE, 'Vante > Ré'),
        (SENTIDO_RE_VANTE, 'Ré > Vante'),
        (SENTIDO_BOMBORDO_BORESTE, 'Bombordo > Boreste'),
        (SENTIDO_BORESTE_BOMBORDO, 'Boreste < Bombordo'),
    )

    @staticmethod
    def _canonicalize_sentido_model(raw):
        try:
            if raw is None:
                return None
            if isinstance(raw, bool):
                return RdoTanque.SENTIDO_VANTE_RE if raw else RdoTanque.SENTIDO_RE_VANTE
            if isinstance(raw, (int, float)):
                try:
                    if int(raw) == 1:
                        return RdoTanque.SENTIDO_VANTE_RE
                    if int(raw) == 0:
                        return RdoTanque.SENTIDO_RE_VANTE
                except Exception:
                    pass
            s = str(raw).strip()
            if not s:
                return None
            low = s.lower()
            if 'vante' in low and ('re' in low or 'ré' in low):
                return RdoTanque.SENTIDO_VANTE_RE
            if ('re' in low or 'ré' in low) and 'vante' in low:
                return RdoTanque.SENTIDO_RE_VANTE
            if 'bombordo' in low and 'boreste' in low:
                if low.index('boreste') < low.index('bombordo'):
                    return RdoTanque.SENTIDO_BORESTE_BOMBORDO
                return RdoTanque.SENTIDO_BOMBORDO_BORESTE
            if '>' in low or '<' in low or '->' in low:
                if 'vante' in low:
                    return RdoTanque.SENTIDO_VANTE_RE
                if 'ré' in low or 're' in low:
                    return RdoTanque.SENTIDO_RE_VANTE
            return None
        except Exception:
            return None

    rdo = models.ForeignKey('RDO', related_name='tanques', on_delete=models.CASCADE)
    tanque_codigo = models.CharField(max_length=120, null=True, blank=True)
    nome_tanque = models.CharField(max_length=200, null=True, blank=True)
    tipo_tanque = models.CharField(max_length=60, null=True, blank=True)
    numero_compartimentos = models.IntegerField(null=True, blank=True)
    gavetas = models.IntegerField(null=True, blank=True)
    patamares = models.IntegerField(null=True, blank=True)
    volume_tanque_exec = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    servico_exec = models.CharField(max_length=80, null=True, blank=True)
    metodo_exec = models.CharField(max_length=80, null=True, blank=True)
    espaco_confinado = models.CharField(max_length=20, null=True, blank=True)
    operadores_simultaneos = models.IntegerField(null=True, blank=True)
    h2s_ppm = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    lel = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    co_ppm = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    o2_percent = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    total_n_efetivo_confinado = models.IntegerField(null=True, blank=True)
    sentido_limpeza = models.CharField(null=True, blank=True, max_length=30, choices=SENTIDO_CHOICES)
    tempo_bomba = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    ensacamento_dia = models.IntegerField(null=True, blank=True)
    icamento_dia = models.IntegerField(null=True, blank=True)
    cambagem_dia = models.IntegerField(null=True, blank=True)
    ensacamento_prev = models.IntegerField(null=True, blank=True)
    icamento_prev = models.IntegerField(null=True, blank=True)
    cambagem_prev = models.IntegerField(null=True, blank=True)
    tambores_dia = models.IntegerField(null=True, blank=True)
    tambores_cumulativo = models.IntegerField(null=True, blank=True)
    residuos_solidos = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    residuos_totais = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    bombeio = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    total_liquido = models.IntegerField(null=True, blank=True)
    total_liquido_cumulativo = models.IntegerField(null=True, blank=True)
    residuos_solidos_cumulativo = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    avanco_limpeza = models.CharField(max_length=30, null=True, blank=True)
    avanco_limpeza_fina = models.CharField(max_length=30, null=True, blank=True)
    limpeza_mecanizada_diaria = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    limpeza_mecanizada_cumulativa = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    limpeza_fina_diaria = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    limpeza_fina_cumulativa = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    percentual_limpeza_fina = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    percentual_limpeza_diario = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    percentual_limpeza_fina_diario = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    percentual_limpeza_cumulativo = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    percentual_limpeza_fina_cumulativo = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    percentual_avanco = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    percentual_avanco_cumulativo = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    percentual_ensacamento = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    percentual_icamento = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    percentual_cambagem = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ensacamento_cumulativo = models.IntegerField(null=True, blank=True)
    icamento_cumulativo = models.IntegerField(null=True, blank=True)
    cambagem_cumulativo = models.IntegerField(null=True, blank=True)

    compartimentos_avanco_json = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"Tanque {self.tanque_codigo or self.nome_tanque or self.id} (RDO {getattr(self.rdo, 'rdo', self.rdo_id)})"

    def recompute_metrics(self, only_when_missing=True):
        try:
            import json as _json
            tank_code = getattr(self, 'tanque_codigo', None)
            if not tank_code:
                return None
            tank_code = str(tank_code).strip()

            n_comp = None
            try:
                if getattr(self, 'numero_compartimentos', None):
                    n_comp = int(self.numero_compartimentos)
                else:
                    n_comp = int(getattr(self.rdo, 'numero_compartimentos', 0) or 0)
            except Exception:
                n_comp = 0
            if not n_comp or n_comp <= 0:
                return None

            sums = {str(i): 0.0 for i in range(1, n_comp + 1)}
            sums_fina = {str(i): 0.0 for i in range(1, n_comp + 1)}

            RDOModel = self.rdo.__class__
            qs = RDOModel.objects.filter(ordem_servico=self.rdo.ordem_servico)
            if getattr(self.rdo, 'data', None) and getattr(self.rdo, 'pk', None):
                from django.db.models import Q
                # Pegar apenas RDOs de dias anteriores OU do mesmo dia mas com ID menor
                qs = qs.filter(Q(data__lt=self.rdo.data) | (Q(data=self.rdo.data) & Q(pk__lt=self.rdo.pk)))
            elif getattr(self.rdo, 'data', None):
                qs = qs.filter(data__lt=self.rdo.data)
            qs = qs.filter(tanques__tanque_codigo__iexact=tank_code).distinct().order_by('data', 'pk')

            for prior in qs:
                raw = getattr(prior, 'compartimentos_avanco_json', None)
                if not raw:
                    continue
                try:
                    parsed = _json.loads(raw) if isinstance(raw, str) else raw
                except Exception:
                    parsed = None
                if not isinstance(parsed, dict):
                    continue
                for i in range(1, n_comp + 1):
                    key = str(i)
                    item = parsed.get(key) if isinstance(parsed, dict) else None
                    if not item:
                        continue
                    try:
                        mv = item.get('mecanizada', 0) if isinstance(item, dict) else 0
                        fv = item.get('fina', 0) if isinstance(item, dict) else 0
                        if mv is None:
                            mv = 0
                        if isinstance(mv, str):
                            mv = mv.strip().replace('%', '')
                            mv = float(mv) if mv != '' else 0.0
                        else:
                            mv = float(mv)
                    except Exception:
                        mv = 0.0
                        fv = 0.0
                    try:
                        if fv is None:
                            fv = 0
                        if isinstance(fv, str):
                            fv = fv.strip().replace('%', '')
                            fv = float(fv) if fv != '' else 0.0
                        else:
                            fv = float(fv)
                    except Exception:
                        fv = 0.0
                    try:
                        sums[key] = sums.get(key, 0.0) + float(mv)
                    except Exception:
                        pass
                    try:
                        sums_fina[key] = sums_fina.get(key, 0.0) + float(fv)
                    except Exception:
                        pass

            try:
                raw_self = getattr(self, 'compartimentos_avanco_json', None)
                if raw_self:
                    parsed_self = _json.loads(raw_self) if isinstance(raw_self, str) else raw_self
                else:
                    parsed_self = None
            except Exception:
                parsed_self = None
            if isinstance(parsed_self, dict):
                for i in range(1, n_comp + 1):
                    key = str(i)
                    item = parsed_self.get(key)
                    if not item:
                        continue
                    try:
                        mv = item.get('mecanizada', 0) if isinstance(item, dict) else 0
                        fv = item.get('fina', 0) if isinstance(item, dict) else 0
                        if mv is None:
                            mv = 0
                        if isinstance(mv, str):
                            mv = mv.strip().replace('%', '')
                            mv = float(mv) if mv != '' else 0.0
                        else:
                            mv = float(mv)
                    except Exception:
                        mv = 0.0
                        fv = 0.0
                    try:
                        if fv is None:
                            fv = 0
                        if isinstance(fv, str):
                            fv = fv.strip().replace('%', '')
                            fv = float(fv) if fv != '' else 0.0
                        else:
                            fv = float(fv)
                    except Exception:
                        fv = 0.0
                    try:
                        sums[key] = sums.get(key, 0.0) + float(mv)
                    except Exception:
                        pass
                    try:
                        sums_fina[key] = sums_fina.get(key, 0.0) + float(fv)
                    except Exception:
                        pass

            caps = []
            caps_fina = []
            for i in range(1, n_comp + 1):
                key = str(i)
                try:
                    v = float(sums.get(key, 0) or 0)
                except Exception:
                    v = 0.0
                try:
                    fv = float(sums_fina.get(key, 0) or 0)
                except Exception:
                    fv = 0.0
                if v < 0:
                    v = 0.0
                if fv < 0:
                    fv = 0.0
                if v > 100.0:
                    v = 100.0
                if fv > 100.0:
                    fv = 100.0
                caps.append(v)
                caps_fina.append(fv)

            if not caps:
                return None

            avg = sum(caps) / float(len(caps))
            avg_fina = sum(caps_fina) / float(len(caps_fina))

            try:
                from decimal import Decimal as _D, ROUND_HALF_UP as _RH
                if not only_when_missing or getattr(self, 'limpeza_mecanizada_cumulativa', None) in (None, ''):
                    dec = _D(str(round(avg, 2))).quantize(_D('0.01'), rounding=_RH)
                    self.limpeza_mecanizada_cumulativa = dec
            except Exception:
                pass
            try:
                from decimal import Decimal as _D, ROUND_HALF_UP as _RH
                if not only_when_missing or getattr(self, 'percentual_limpeza_cumulativo', None) in (None, ''):
                    dec = _D(str(round(avg, 2))).quantize(_D('0.01'), rounding=_RH)
                    self.percentual_limpeza_cumulativo = dec
            except Exception:
                pass
            try:
                from decimal import Decimal as _D, ROUND_HALF_UP as _RH
                if not only_when_missing or getattr(self, 'limpeza_fina_cumulativa', None) in (None, ''):
                    decf = _D(str(round(avg_fina, 2))).quantize(_D('0.01'), rounding=_RH)
                    self.limpeza_fina_cumulativa = decf
            except Exception:
                pass
            try:
                from decimal import Decimal as _D, ROUND_HALF_UP as _RH
                if not only_when_missing or getattr(self, 'percentual_limpeza_fina_cumulativo', None) in (None, ''):
                    decf = _D(str(round(avg_fina, 2))).quantize(_D('0.01'), rounding=_RH)
                    self.percentual_limpeza_fina_cumulativo = decf
            except Exception:
                pass

            try:
                from decimal import Decimal as _D, ROUND_HALF_UP as _RH

                def _to_num(v):
                    try:
                        if v is None or v == '':
                            return None
                        if isinstance(v, (int, float)):
                            return float(v)
                        s = str(v).strip().replace('%', '').replace(',', '.')
                        if s == '':
                            return None
                        return float(s)
                    except Exception:
                        return None

                def _clamp01(v):
                    try:
                        if v is None:
                            return 0.0
                        if v < 0:
                            return 0.0
                        if v > 100.0:
                            return 100.0
                        return v
                    except Exception:
                        return 0.0

                def _clamp01_opt(v):
                    try:
                        if v is None:
                            return None
                        if v < 0:
                            return 0.0
                        if v > 100.0:
                            return 100.0
                        return v
                    except Exception:
                        return None

                day_vals_m = []
                day_vals_f = []
                if isinstance(parsed_self, dict):
                    for i in range(1, n_comp + 1):
                        key = str(i)
                        item = parsed_self.get(key)
                        mv = _to_num(item.get('mecanizada', 0) if isinstance(item, dict) else 0) or 0.0
                        fv = _to_num(item.get('fina', 0) if isinstance(item, dict) else 0) or 0.0
                        day_vals_m.append(_clamp01(mv))
                        day_vals_f.append(_clamp01(fv))
                day_avg_m = (sum(day_vals_m) / float(len(day_vals_m))) if day_vals_m else None
                day_avg_f = (sum(day_vals_f) / float(len(day_vals_f))) if day_vals_f else None

                lim_mec_day = _to_num(getattr(self, 'percentual_limpeza_diario', None))
                if lim_mec_day is None:
                    lim_mec_day = _to_num(getattr(self, 'limpeza_mecanizada_diaria', None))
                if lim_mec_day is None:
                    lim_mec_day = day_avg_m
                lim_mec_day = _clamp01_opt(lim_mec_day)

                lim_fina_day = _to_num(getattr(self, 'avanco_limpeza_fina', None))
                if lim_fina_day is None:
                    lim_fina_day = _to_num(getattr(self, 'percentual_limpeza_fina_diario', None))
                if lim_fina_day is None:
                    lim_fina_day = _to_num(getattr(self, 'limpeza_fina_diaria', None))
                if lim_fina_day is None:
                    lim_fina_day = day_avg_f
                lim_fina_day = _clamp01_opt(lim_fina_day)

                ens_day = _clamp01_opt(_to_num(getattr(self, 'percentual_ensacamento', None)))
                ic_day = _clamp01_opt(_to_num(getattr(self, 'percentual_icamento', None)))
                camb_day = _clamp01_opt(_to_num(getattr(self, 'percentual_cambagem', None)))

                has_any_day_component = any(v is not None for v in (lim_mec_day, ens_day, ic_day, camb_day, lim_fina_day))
                if has_any_day_component:
                    def _v0(x):
                        return 0.0 if x is None else float(x)

                    day_weighted = (_v0(lim_mec_day) * 70.0 + _v0(ens_day) * 7.0 + _v0(ic_day) * 7.0 + _v0(camb_day) * 5.0 + _v0(lim_fina_day) * 6.0) / 100.0
                    if not only_when_missing or getattr(self, 'percentual_avanco', None) in (None, ''):
                        self.percentual_avanco = _D(str(round(day_weighted, 2))).quantize(_D('0.01'), rounding=_RH)

                lim_mec_cum = _to_num(getattr(self, 'percentual_limpeza_cumulativo', None))
                if lim_mec_cum is None:
                    lim_mec_cum = _to_num(getattr(self, 'limpeza_mecanizada_cumulativa', None))
                if lim_mec_cum is None:
                    lim_mec_cum = _to_num(avg)
                lim_mec_cum = _clamp01(lim_mec_cum)

                lim_fina_cum = _to_num(getattr(self, 'percentual_limpeza_fina_cumulativo', None))
                if lim_fina_cum is None:
                    lim_fina_cum = _to_num(getattr(self, 'limpeza_fina_cumulativa', None))
                if lim_fina_cum is None:
                    lim_fina_cum = _to_num(avg_fina)
                lim_fina_cum = _clamp01(lim_fina_cum)

                ens_c = _clamp01(_to_num(getattr(self, 'percentual_ensacamento', None)))
                ic_c = _clamp01(_to_num(getattr(self, 'percentual_icamento', None)))
                camb_c = _clamp01(_to_num(getattr(self, 'percentual_cambagem', None)))

                cum_weighted = (lim_mec_cum * 70.0 + ens_c * 7.0 + ic_c * 7.0 + camb_c * 5.0 + lim_fina_cum * 6.0) / 100.0
                if not only_when_missing or getattr(self, 'percentual_avanco_cumulativo', None) in (None, ''):
                    self.percentual_avanco_cumulativo = _D(str(round(cum_weighted, 2))).quantize(_D('0.01'), rounding=_RH)
            except Exception:
                pass
            try:
                total_ensac = 0
                total_ic = 0
                total_camb = 0
                for prior in qs:
                    try:
                        pt = prior.tanques.filter(tanque_codigo__iexact=tank_code).order_by('-id').first()
                        if pt is not None:
                            try:
                                total_ensac += int(getattr(pt, 'ensacamento_dia', 0) or 0)
                            except Exception:
                                pass
                            try:
                                total_ic += int(getattr(pt, 'icamento_dia', 0) or 0)
                            except Exception:
                                pass
                            try:
                                total_camb += int(getattr(pt, 'cambagem_dia', 0) or 0)
                            except Exception:
                                pass
                    except Exception:
                        pass

                if not only_when_missing or getattr(self, 'ensacamento_cumulativo', None) in (None, ''):
                    self.ensacamento_cumulativo = int(total_ensac)
                if not only_when_missing or getattr(self, 'icamento_cumulativo', None) in (None, ''):
                    self.icamento_cumulativo = int(total_ic)
                if not only_when_missing or getattr(self, 'cambagem_cumulativo', None) in (None, ''):
                    self.cambagem_cumulativo = int(total_camb)

                try:
                    total_tambores = 0
                    for prior in qs:
                        try:
                            pt = prior.tanques.filter(tanque_codigo__iexact=tank_code).order_by('-id').first()
                            if pt is not None:
                                try:
                                    total_tambores += int(getattr(pt, 'tambores_dia', 0) or 0)
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    try:
                        total_tambores += int(getattr(self, 'tambores_dia', 0) or 0)
                    except Exception:
                        pass
                    if not only_when_missing or getattr(self, 'tambores_cumulativo', None) in (None, ''):
                        self.tambores_cumulativo = int(total_tambores)
                except Exception:
                    pass

                try:
                    from decimal import Decimal as _D, ROUND_HALF_UP as _RH

                    total_res_liq = 0
                    total_res_sol = _D('0')

                    for prior in qs:
                        try:
                            pt = prior.tanques.filter(tanque_codigo__iexact=tank_code).order_by('-id').first()
                            if pt is not None:
                                try:
                                    total_res_liq += int(getattr(pt, 'total_liquido', 0) or 0)
                                except Exception:
                                    pass
                                try:
                                    v = getattr(pt, 'residuos_solidos', None)
                                    if v not in (None, ''):
                                        total_res_sol += _D(str(v))
                                except Exception:
                                    pass
                        except Exception:
                            pass

                    try:
                        total_res_liq += int(getattr(self, 'total_liquido', 0) or 0)
                    except Exception:
                        pass
                    try:
                        v = getattr(self, 'residuos_solidos', None)
                        if v not in (None, ''):
                            total_res_sol += _D(str(v))
                    except Exception:
                        pass

                    if not only_when_missing or getattr(self, 'total_liquido_cumulativo', None) in (None, ''):
                        self.total_liquido_cumulativo = int(total_res_liq)
                    if not only_when_missing or getattr(self, 'residuos_solidos_cumulativo', None) in (None, ''):
                        try:
                            self.residuos_solidos_cumulativo = total_res_sol.quantize(_D('0.001'), rounding=_RH)
                        except Exception:
                            self.residuos_solidos_cumulativo = total_res_sol
                except Exception:
                    pass
            except Exception:
                pass
                try:
                    from decimal import Decimal as _D, ROUND_HALF_UP as _RH
                    def _to_dec_safe(v):
                        try:
                            if v is None:
                                return _D('0')
                            return _D(str(v))
                        except Exception:
                            try:
                                return _D(float(v))
                            except Exception:
                                return _D('0')

                    def _clamp(d):
                        try:
                            if d is None:
                                return _D('0')
                            if d < 0:
                                return _D('0')
                            if d > 100:
                                return _D('100')
                            return d
                        except Exception:
                            return _D('0')

                    try:
                        prev = getattr(self, 'ensacamento_prev', None) or getattr(self.rdo, 'ensacamento_previsao', None) if getattr(self, 'rdo', None) else None
                        if prev not in (None, '') and float(prev) != 0:
                            dia = int(getattr(self, 'ensacamento_dia', 0) or 0)
                            cum = int(getattr(self, 'ensacamento_cumulativo', 0) or 0)
                            num = _D(str(int(dia) + int(cum)))
                            den = _D(str(int(prev)))
                            pct = (num / den) * _D('100')
                            pct = pct.quantize(_D('0.01'), rounding=_RH)
                            if not only_when_missing or getattr(self, 'percentual_ensacamento', None) in (None, ''):
                                try:
                                    self.percentual_ensacamento = pct
                                except Exception:
                                    pass
                    except Exception:
                        pass

                    try:
                        prev = getattr(self, 'icamento_prev', None) or getattr(self.rdo, 'icamento_previsao', None) if getattr(self, 'rdo', None) else None
                        if prev not in (None, '') and float(prev) != 0:
                            dia = int(getattr(self, 'icamento_dia', 0) or 0)
                            cum = int(getattr(self, 'icamento_cumulativo', 0) or 0)
                            num = _D(str(int(dia) + int(cum)))
                            den = _D(str(int(prev)))
                            pct = (num / den) * _D('100')
                            pct = pct.quantize(_D('0.01'), rounding=_RH)
                            if not only_when_missing or getattr(self, 'percentual_icamento', None) in (None, ''):
                                try:
                                    self.percentual_icamento = pct
                                except Exception:
                                    pass
                    except Exception:
                        pass

                    try:
                        prev = getattr(self, 'cambagem_prev', None) or getattr(self.rdo, 'cambagem_previsao', None) if getattr(self, 'rdo', None) else None
                        if prev not in (None, '') and float(prev) != 0:
                            dia = int(getattr(self, 'cambagem_dia', 0) or 0)
                            cum = int(getattr(self, 'cambagem_cumulativo', 0) or 0)
                            num = _D(str(int(dia) + int(cum)))
                            den = _D(str(int(prev)))
                            pct = (num / den) * _D('100')
                            pct = pct.quantize(_D('0.01'), rounding=_RH)
                            if not only_when_missing or getattr(self, 'percentual_cambagem', None) in (None, ''):
                                try:
                                    self.percentual_cambagem = pct
                                except Exception:
                                    pass
                    except Exception:
                        pass

                    try:
                        pesos = {
                            'percentual_limpeza': _D('70'),
                            'percentual_ensacamento': _D('7'),
                            'percentual_icamento': _D('7'),
                            'percentual_cambagem': _D('5'),
                            'percentual_limpeza_fina': _D('6'),
                        }

                        try:
                            lim_day = _to_dec_safe(getattr(self, 'percentual_limpeza_diario', None) or getattr(self, 'limpeza_mecanizada_diaria', None) or 0)
                        except Exception:
                            lim_day = _D('0')
                        try:
                            lim_fina_day = _to_dec_safe(getattr(self, 'percentual_limpeza_fina_diario', None) or getattr(self, 'limpeza_fina_diaria', None) or 0)
                        except Exception:
                            lim_fina_day = _D('0')
                        try:
                            ens_day = _to_dec_safe(getattr(self, 'percentual_ensacamento', None) or 0)
                        except Exception:
                            ens_day = _D('0')
                        try:
                            ic_day = _to_dec_safe(getattr(self, 'percentual_icamento', None) or 0)
                        except Exception:
                            ic_day = _D('0')
                        try:
                            camb_day = _to_dec_safe(getattr(self, 'percentual_cambagem', None) or 0)
                        except Exception:
                            camb_day = _D('0')

                        vals_day = {
                            'percentual_limpeza': lim_day,
                            'percentual_ensacamento': ens_day,
                            'percentual_icamento': ic_day,
                            'percentual_cambagem': camb_day,
                            'percentual_limpeza_fina': lim_fina_day,
                        }
                        weighted = _D('0')
                        total_w = _D('0')
                        for k, w in pesos.items():
                            try:
                                v = vals_day.get(k, _D('0')) or _D('0')
                                weighted += (v * w)
                                total_w += w
                            except Exception:
                                continue
                        perc_av_day = _D('0')
                        if total_w > 0:
                            try:
                                perc_av_day = (weighted / total_w)
                            except Exception:
                                perc_av_day = _D('0')
                        perc_av_day = _clamp(perc_av_day)
                        try:
                            perc_av_day_q = perc_av_day.quantize(_D('0.01'), rounding=_RH)
                        except Exception:
                            perc_av_day_q = perc_av_day
                        if not only_when_missing or getattr(self, 'percentual_avanco', None) in (None, ''):
                            try:
                                self.percentual_avanco = perc_av_day_q
                            except Exception:
                                pass

                        try:
                            lim_cum = _to_dec_safe(getattr(self, 'percentual_limpeza_cumulativo', None) or getattr(self, 'limpeza_mecanizada_cumulativa', None) or 0)
                        except Exception:
                            lim_cum = _D('0')
                        try:
                            lim_fina_cum = _to_dec_safe(getattr(self, 'percentual_limpeza_fina_cumulativo', None) or getattr(self, 'limpeza_fina_cumulativa', None) or 0)
                        except Exception:
                            lim_fina_cum = _D('0')
                        try:
                            ens_cum = _to_dec_safe(getattr(self, 'percentual_ensacamento', None) or _D('0'))
                        except Exception:
                            ens_cum = _D('0')
                        try:
                            ic_cum = _to_dec_safe(getattr(self, 'percentual_icamento', None) or _D('0'))
                        except Exception:
                            ic_cum = _D('0')
                        try:
                            camb_cum = _to_dec_safe(getattr(self, 'percentual_cambagem', None) or _D('0'))
                        except Exception:
                            camb_cum = _D('0')

                        vals_cum = {
                            'percentual_limpeza': lim_cum,
                            'percentual_ensacamento': ens_cum,
                            'percentual_icamento': ic_cum,
                            'percentual_cambagem': camb_cum,
                            'percentual_limpeza_fina': lim_fina_cum,
                        }
                        weighted_c = _D('0')
                        total_wc = _D('0')
                        for k, w in pesos.items():
                            try:
                                v = vals_cum.get(k, _D('0')) or _D('0')
                                weighted_c += (v * w)
                                total_wc += w
                            except Exception:
                                continue
                        perc_av_cum = _D('0')
                        if total_wc > 0:
                            try:
                                perc_av_cum = (weighted_c / total_wc)
                            except Exception:
                                perc_av_cum = _D('0')
                        perc_av_cum = _clamp(perc_av_cum)
                        try:
                            pvci = perc_av_cum.quantize(_D('0.01'), rounding=_RH)
                        except Exception:
                            try:
                                pvci = _D(str(round(float(perc_av_cum), 2)))
                            except Exception:
                                pvci = _D('0.00')
                        if not only_when_missing or getattr(self, 'percentual_avanco_cumulativo', None) in (None, ''):
                            try:
                                self.percentual_avanco_cumulativo = pvci
                            except Exception:
                                pass
                    except Exception:
                        pass
                except Exception:
                    pass
            return avg
        except Exception:
            return None

    def _normalize_cleaning_and_predictions(self):
        try:
            from decimal import Decimal, ROUND_HALF_UP
        except Exception:
            Decimal = None; ROUND_HALF_UP = None

        def _to_int(v):
            try:
                if v is None or v == '':
                    return None
                return int(v)
            except Exception:
                try:
                    return int(float(v))
                except Exception:
                    return None

        def _q2(v):
            if v is None:
                return None
            if Decimal is None:
                return v
            try:
                d = Decimal(str(v))
                return d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            except Exception:
                return v

        try:
            if hasattr(self, 'limpeza_mecanizada_diaria'):
                self.limpeza_mecanizada_diaria = _q2(getattr(self, 'limpeza_mecanizada_diaria'))
        except Exception:
            pass
        try:
            if hasattr(self, 'limpeza_fina_diaria'):
                self.limpeza_fina_diaria = _q2(getattr(self, 'limpeza_fina_diaria'))
        except Exception:
            pass
        try:
            if hasattr(self, 'percentual_limpeza_diario'):
                self.percentual_limpeza_diario = _q2(getattr(self, 'percentual_limpeza_diario'))
        except Exception:
            pass
        try:
            if hasattr(self, 'percentual_limpeza_fina_diario'):
                self.percentual_limpeza_fina_diario = _q2(getattr(self, 'percentual_limpeza_fina_diario'))
        except Exception:
            pass

        try:
            if hasattr(self, 'limpeza_mecanizada_cumulativa'):
                self.limpeza_mecanizada_cumulativa = _q2(getattr(self, 'limpeza_mecanizada_cumulativa'))
        except Exception:
            pass
        try:
            if hasattr(self, 'limpeza_fina_cumulativa'):
                self.limpeza_fina_cumulativa = _q2(getattr(self, 'limpeza_fina_cumulativa'))
        except Exception:
            pass
        try:
            if hasattr(self, 'percentual_limpeza_cumulativo'):
                self.percentual_limpeza_cumulativo = _q2(getattr(self, 'percentual_limpeza_cumulativo'))
        except Exception:
            pass
        try:
            if hasattr(self, 'percentual_limpeza_fina'):
                self.percentual_limpeza_fina = _q2(getattr(self, 'percentual_limpeza_fina'))
        except Exception:
            pass
        try:
            if hasattr(self, 'percentual_limpeza_fina_cumulativo'):
                self.percentual_limpeza_fina_cumulativo = _q2(getattr(self, 'percentual_limpeza_fina_cumulativo'))
        except Exception:
            pass
        try:
            if hasattr(self, 'percentual_avanco_cumulativo'):
                self.percentual_avanco_cumulativo = _q2(getattr(self, 'percentual_avanco_cumulativo'))
        except Exception:
            pass

        try:
            if hasattr(self, 'ensacamento_prev'):
                self.ensacamento_prev = _to_int(getattr(self, 'ensacamento_prev'))
        except Exception:
            pass
        try:
            if hasattr(self, 'icamento_prev'):
                self.icamento_prev = _to_int(getattr(self, 'icamento_prev'))
        except Exception:
            pass
        try:
            if hasattr(self, 'cambagem_prev'):
                self.cambagem_prev = _to_int(getattr(self, 'cambagem_prev'))
        except Exception:
            pass

        try:
            if hasattr(self, 'percentual_ensacamento'):
                self.percentual_ensacamento = _q2(getattr(self, 'percentual_ensacamento'))
        except Exception:
            pass
        try:
            if hasattr(self, 'percentual_icamento'):
                self.percentual_icamento = _q2(getattr(self, 'percentual_icamento'))
        except Exception:
            pass
        try:
            if hasattr(self, 'percentual_cambagem'):
                self.percentual_cambagem = _q2(getattr(self, 'percentual_cambagem'))
        except Exception:
            pass
        try:
            if hasattr(self, 'percentual_avanco'):
                self.percentual_avanco = _q2(getattr(self, 'percentual_avanco'))
        except Exception:
            pass

        try:
            if hasattr(self, 'percentual_ensacamento') and getattr(self, 'percentual_ensacamento', None) in (None, ''):
                prev = getattr(self, 'ensacamento_prev', None)
                try:
                    dia_raw = getattr(self, 'ensacamento_dia', None)
                    if dia_raw is not None and prev not in (None, '') and float(prev) != 0:
                        dia = dia_raw
                        cum = getattr(self, 'ensacamento_cumulativo', 0) or 0
                        num = Decimal(str(int(dia) + int(cum)))
                        den = Decimal(str(int(prev)))
                        pct = (num / den) * Decimal('100')
                        self.percentual_ensacamento = _q2(pct)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if hasattr(self, 'percentual_icamento') and getattr(self, 'percentual_icamento', None) in (None, ''):
                prev = getattr(self, 'icamento_prev', None)
                try:
                    dia_raw = getattr(self, 'icamento_dia', None)
                    if dia_raw is not None and prev not in (None, '') and float(prev) != 0:
                        dia = dia_raw
                        cum = getattr(self, 'icamento_cumulativo', 0) or 0
                        num = Decimal(str(int(dia) + int(cum)))
                        den = Decimal(str(int(prev)))
                        pct = (num / den) * Decimal('100')
                        self.percentual_icamento = _q2(pct)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if hasattr(self, 'percentual_cambagem') and getattr(self, 'percentual_cambagem', None) in (None, ''):
                prev = getattr(self, 'cambagem_prev', None)
                try:
                    dia_raw = getattr(self, 'cambagem_dia', None)
                    if dia_raw is not None and prev not in (None, '') and float(prev) != 0:
                        dia = dia_raw
                        cum = getattr(self, 'cambagem_cumulativo', 0) or 0
                        num = Decimal(str(int(dia) + int(cum)))
                        den = Decimal(str(int(prev)))
                        pct = (num / den) * Decimal('100')
                        self.percentual_cambagem = _q2(pct)
                except Exception:
                    pass
        except Exception:
            pass

        try:
            if hasattr(self, 'ensacamento_cumulativo'):
                self.ensacamento_cumulativo = _to_int(getattr(self, 'ensacamento_cumulativo'))
        except Exception:
            pass
        try:
            if hasattr(self, 'icamento_cumulativo'):
                self.icamento_cumulativo = _to_int(getattr(self, 'icamento_cumulativo'))
        except Exception:
            pass
        try:
            if hasattr(self, 'cambagem_cumulativo'):
                self.cambagem_cumulativo = _to_int(getattr(self, 'cambagem_cumulativo'))
        except Exception:
            pass
    def save(self, *args, **kwargs):
        try:
            self._normalize_cleaning_and_predictions()
        except Exception:
            pass
        try:
            self.recompute_metrics(only_when_missing=True)
        except Exception:
            pass
        try:
            if hasattr(self, 'sentido_limpeza'):
                raw = getattr(self, 'sentido_limpeza', None)
                try:
                    canon = RdoTanque._canonicalize_sentido_model(raw)
                    if canon:
                        self.sentido_limpeza = canon
                except Exception:
                    pass
        except Exception:
            pass
        super().save(*args, **kwargs)
