from django.db import models
from deep_translator import GoogleTranslator
from multiselectfield import MultiSelectField
from django.conf import settings
from django.db.models import SET_NULL, Q
from decimal import Decimal
from datetime import datetime, date, timedelta, time as dt_time
from django.core.exceptions import ValidationError
from decimal import Decimal as _D
import secrets
import re
import unicodedata


def _canonical_tank_alias_for_os(os_num, raw_value):
    """
    Canonicaliza aliases específicos de tanque por OS para manter KPIs acumulativos consistentes.
    """
    try:
        token = re.sub(r'\s+', ' ', str(raw_value or '')).strip().casefold()
    except Exception:
        token = ''
    if not token:
        return None
    try:
        os_int = int(os_num)
    except Exception:
        os_int = None

    if os_int == 6044 and token in {'7p', '7p tank', '7p cot'}:
        return '7P COT'
    if os_int == 5292 and token in {'5s', 'cot-5s', 'cot 5s'}:
        return 'COT-5s'
    return None


def _normalize_activity_choice_token(raw_value):
    try:
        token = str(raw_value or '').strip()
    except Exception:
        token = ''
    if not token:
        return ''
    try:
        token = ''.join(
            ch for ch in unicodedata.normalize('NFKD', token)
            if not unicodedata.combining(ch)
        )
    except Exception:
        pass
    token = token.lower().strip()
    token = re.sub(r'\s*/\s*', '/', token)
    token = re.sub(r'\s+', ' ', token).strip()
    return token


_SETUP_ACTIVITY_TOKENS = {
    _normalize_activity_choice_token('Instalação / Preparação / Montagem / Setup '),
    _normalize_activity_choice_token('Instalação / Preparação / Montagem / Setup'),
    _normalize_activity_choice_token('instalação/preparação/montagem'),
    _normalize_activity_choice_token('Instalação / Preparação / Montagem'),
    _normalize_activity_choice_token('setup'),
}


_OFFLOADING_ACTIVITY_VALUES = (
    'offloading',
    'Offloading',
    'conferência do material e equipamento no container',
    'Conferência do Material e Equipamento no Container / Checking the material and equipment in the container',
    'conferencia do material e equipamento no container',
    'conferencia do material e equipamento no conteiner',
)


def _is_setup_activity_value(raw_value):
    normalized_value = _normalize_activity_choice_token(raw_value)
    if not normalized_value:
        return False
    if normalized_value in _SETUP_ACTIVITY_TOKENS:
        return True
    probe = re.sub(r'[^a-z0-9]+', ' ', normalized_value).strip()
    if 'setup' in probe:
        return True
    return (
        'instalacao' in probe
        and 'preparacao' in probe
        and 'montagem' in probe
    )


def _rdo_has_setup_activity(rdo_obj):
    try:
        activity_manager = getattr(rdo_obj, 'atividades_rdo', None)
        if activity_manager is None:
            return False
        for activity in activity_manager.all():
            if _is_setup_activity_value(getattr(activity, 'atividade', None)):
                return True
    except Exception:
        return False
    return False


def _normalize_decimal_field_value(raw_value, field=None):
    try:
        if raw_value is None:
            return None
        if isinstance(raw_value, bool):
            return raw_value
        if isinstance(raw_value, Decimal):
            dec = raw_value
        elif isinstance(raw_value, (int, float)):
            try:
                if isinstance(raw_value, float) and (raw_value != raw_value or raw_value in (float('inf'), float('-inf'))):
                    return raw_value
            except Exception:
                return raw_value
            dec = Decimal(str(raw_value))
        elif isinstance(raw_value, str):
            s = raw_value.strip()
            if s == '':
                return None
            if s.endswith('%'):
                s = s[:-1].strip()
            s = s.replace(',', '.')
            low = s.lower()
            if low in ('nan', '+nan', '-nan', 'inf', '+inf', '-inf', 'infinity', '+infinity', '-infinity'):
                return raw_value
            dec = Decimal(str(s))
        else:
            return raw_value

        if field is not None:
            try:
                places = int(getattr(field, 'decimal_places', 0) or 0)
                quant = Decimal('1').scaleb(-places)
                dec = dec.quantize(quant)
            except Exception:
                pass
        return dec
    except Exception:
        return raw_value


def _normalize_instance_decimal_fields(instance):
    try:
        for field in getattr(instance._meta, 'fields', []):
            if not isinstance(field, models.DecimalField):
                continue
            try:
                current = getattr(instance, field.attname, None)
            except Exception:
                continue
            normalized = _normalize_decimal_field_value(current, field=field)
            if normalized is current:
                continue
            try:
                setattr(instance, field.attname, normalized)
            except Exception:
                continue
    except Exception:
        pass

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
        ('ADEQUAÇÃO DE EQUIPAMENTOS', 'ADEQUAÇÃO DE EQUPAMENTOS / EQUIPAMENT ADJUSTMENTS'),
        ("COLETA DE AR", "COLETA DE AR"),
        ("COLETA DE ÁGUA", "COLETA DE ÁGUA"),
        ("DELINEAMENTO DE ATIVIDADES", "DELINEAMENTO DE ATIVIDADES"),
        ("DESOBSTRUÇÃO DE LINHAS", "DESOBSTRUÇÃO DE LINHAS"),
        ("DESOBSTRUÇÃO DE RALOS", "DESOBSTRUÇÃO DE RALOS"),
        ("DRENAGEM", "DRENAGEM"),
        ("EMISSÃO DE FREE FOR FIRE", "EMISSÃO DE FREE FOR FIRE"),
        ("LIMPEZA DA SALA DE MÁQUINA", "LIMPEZA DA SALA DE MÁQUINA"),
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
        ("LIMPEZA DE TANQUE DE LASTRO", "LIMPEZA DE TANQUE DE LASTRO"),
        ("LIMPEZA DE TANQUE SEWAGE", "LIMPEZA DE TANQUE SEWAGE"),
        ("LIMPEZA DE VASO", "LIMPEZA DE VASO"),
        ("LIMPEZA DE TANQUE DE VOID", "LIMPEZA DE TANQUE DE VOID"),
        ("LIMPEZA DE TANQUE OFFSPEC", "LIMPEZA DE TANQUE OFFSPEC"),
        ("LIMPEZA TROCADOR DE CALOR", "LIMPEZA TROCADOR DE CALOR"),
        ("LIMPEZA QUÍMICA DE TUBULAÇÃO", "LIMPEZA QUÍMICA DE TUBULAÇÃO"),
        ("LIMPEZA DE REDE", "LIMPEZA DE REDE"),
        ("LIMPEZA HVAC", "LIMPEZA HVAC"),
        ("MOBILIZAÇÃO/DESMOBILIZAÇÃO DE TANQUE", "MOBILIZAÇÃO/DESMOBILIZAÇÃO DE TANQUE"),
        ("MOBILIZAÇÃO E COMISSIONAMENTO DE HVAC", "MOBILIZAÇÃO E COMISSIONAMENTO DE HVAC"),
        ("SERVIÇO DE MONITORAMENTO OCUPACIONAL", "SERVIÇO DE MONITORAMENTO OCUPACIONAL"),
        ("SERVIÇO DE RÁDIO PROTEÇÃO", "SERVIÇO DE RÁDIO PROTEÇÃO"),
        ("TRATAMENTO E PINTURA", "TRATAMENTO E PINTURA"),
        ("VISITA TÉCNICA", "VISITA TÉCNICA"),
    ]

    TIPO_OP_CHOICES = [
        ('Onshore', 'Onshore'),
        ('Offshore', 'Offshore'),
        ('Serviços internos', 'Serviços internos'),
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
        ('MARCOS CORREIA', 'MARCOS CORREIA'),
        ('GABRIEL DELAIA', 'GABRIEL DELAIA'),
        ('ANDRE SANTIAGO', 'ANDRE SANTIAGO'),
        ('IVONEI DE SOUZA', 'IVONEI DE SOUZA'),
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
    po = models.CharField(max_length=100, null=True, blank=True)
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
                    delta_days = (self.data_fim - self.data_inicio).days
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
        ('offloading', 'Offloading'),
        ('coleta de água', 'Coleta de Água / Water sampling'),
        ('dds', 'DDS / Work Safety Dialog'),
        ("Desobstrução de linhas", " Desobstrução de linhas / Drain line clearing "),
        ("Drenagem inicial do tanque ", " Drenagem inicial do tanque / Tank draining started"),
        ('em espera', 'Em Espera / Stand-by'),
        ('equipe chegou no aeroporto', 'Equipe Chegou no Aeroporto / Team arrived at the airport'),
        ('vôo com destino a unidade', 'Vôo com Destino à Unidade / Flight to unity'),
        ('vôo postergado', 'Vôo Postergado / Flight postponed'),
        ('triagem', 'Triagem / Security screening'),
        ('check-in, pesagem, briefing', 'Check-in, Pesagem, Briefing / Check-in, weighing, briefing'),
        ('saída da base', 'Saída da Base / Departure from base'),
        ('equipe se apresenta ao responsável da unidade', 'Equipe se Apresenta ao Responsável da Unidade / The team presents itself to the person in charge of the unit'),
        ('jantar', 'Jantar / Dinner'),
        ('limpeza da área', 'Limpeza da Área / Housekeep'),
        ('treinamento de abandono', 'Treinamento de Abandono / Drill'),
        ('alarme real', 'Alarme Real / Real alarm'),
        ('instrução de segurança', 'Instrução de Segurança / Security instructions'),
        ('Instalação / Preparação / Montagem / Setup ', 'Instalação / Preparação / Montagem / Setup'),
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

    def _time_value_to_minutes(self, value):
        try:
            if value in (None, ''):
                return None
            if isinstance(value, str):
                s = value.strip()
                if not s:
                    return None
                if ':' in s:
                    parts = s.split(':')
                    try:
                        hours = int(parts[0])
                        minutes = int(parts[1]) if len(parts) > 1 else 0
                        return (hours * 60) + minutes
                    except Exception:
                        return None
                try:
                    return int(float(s))
                except Exception:
                    return None

            hours = int(getattr(value, 'hour', 0) or 0)
            minutes = int(getattr(value, 'minute', 0) or 0)
            return (hours * 60) + minutes
        except Exception:
            return None

    def compute_total_hh_cumulativo_real(self):
        try:
            total_minutes = 0
            has_any = False

            def _consume_time_value(raw_value):
                nonlocal total_minutes, has_any
                minutes = self._time_value_to_minutes(raw_value)
                if minutes is None:
                    return
                total_minutes += minutes
                has_any = True

            data_ref = getattr(self, 'data', None)
            ord_obj = getattr(self, 'ordem_servico', None)
            current_pk = getattr(self, 'pk', None)

            if ord_obj is not None and data_ref is not None:
                qs = self.__class__.objects.filter(
                    ordem_servico=ord_obj,
                    data__isnull=False,
                    data__lte=data_ref,
                ).order_by('data', 'id')

                current_seen = False
                for item in qs:
                    daily_value = getattr(item, 'total_hh_frente_real', None)
                    if current_pk is not None and getattr(item, 'pk', None) == current_pk:
                        current_seen = True
                        daily_value = getattr(self, 'total_hh_frente_real', None) or daily_value
                        if daily_value in (None, ''):
                            try:
                                daily_value = self.compute_total_hh_frente_real()
                            except Exception:
                                daily_value = None
                    elif daily_value in (None, ''):
                        try:
                            daily_value = item.compute_total_hh_frente_real()
                        except Exception:
                            daily_value = None
                    _consume_time_value(daily_value)

                if current_pk is None or not current_seen:
                    daily_value = getattr(self, 'total_hh_frente_real', None)
                    if daily_value in (None, ''):
                        try:
                            daily_value = self.compute_total_hh_frente_real()
                        except Exception:
                            daily_value = None
                    _consume_time_value(daily_value)
            else:
                daily_value = getattr(self, 'total_hh_frente_real', None)
                if daily_value in (None, ''):
                    try:
                        daily_value = self.compute_total_hh_frente_real()
                    except Exception:
                        daily_value = None
                _consume_time_value(daily_value)

            if not has_any:
                self.total_hh_cumulativo_real = None
                return None

            hours = (total_minutes // 60) % 24
            minutes = total_minutes % 60
            self.total_hh_cumulativo_real = dt_time(hour=int(hours), minute=int(minutes))
            return self.total_hh_cumulativo_real
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
    
    COMPARTIMENTO_CATEGORIES = ('mecanizada', 'fina')

    def _get_matching_tank_snapshot(self):
        try:
            qs = self.tanques.all().order_by('id')
        except Exception:
            return None
        try:
            tanks = list(qs)
        except Exception:
            tanks = []
        if not tanks:
            return None

        aliases = set()
        for raw_value in (getattr(self, 'tanque_codigo', None), getattr(self, 'nome_tanque', None)):
            try:
                if raw_value not in (None, ''):
                    aliases.add(str(raw_value).strip())
            except Exception:
                continue

        try:
            os_num = getattr(getattr(self, 'ordem_servico', None), 'numero_os', None)
        except Exception:
            os_num = None
        for raw_value in list(aliases):
            try:
                canon = _canonical_tank_alias_for_os(os_num, raw_value)
                if canon:
                    aliases.add(str(canon).strip())
            except Exception:
                continue

        if aliases:
            for tank in tanks:
                try:
                    tank_code = str(getattr(tank, 'tanque_codigo', None) or '').strip()
                    tank_name = str(getattr(tank, 'nome_tanque', None) or '').strip()
                    if tank_code in aliases or tank_name in aliases:
                        return tank
                except Exception:
                    continue
        return tanks[0]

    def _get_total_compartimentos_for_progress(self, raw_payload=None):
        candidates = []
        for raw_value in (getattr(self, 'numero_compartimentos', None),):
            try:
                num = int(raw_value or 0)
                if num > 0:
                    candidates.append(num)
            except Exception:
                continue

        tank = self._get_matching_tank_snapshot()
        if tank is not None:
            for raw_value in (
                getattr(tank, 'numero_compartimentos', None),
                tank.get_total_compartimentos() if hasattr(tank, 'get_total_compartimentos') else None,
            ):
                try:
                    num = int(raw_value or 0)
                    if num > 0:
                        candidates.append(num)
                except Exception:
                    continue

        try:
            import json as _json
            parsed = raw_payload
            if isinstance(raw_payload, str):
                parsed = _json.loads(raw_payload) if raw_payload.strip() else {}
            if isinstance(parsed, dict):
                inferred = 0
                for key in parsed.keys():
                    try:
                        idx = int(str(key).strip())
                    except Exception:
                        continue
                    if idx > inferred:
                        inferred = idx
                if inferred > 0:
                    candidates.append(inferred)
        except Exception:
            pass

        return max(candidates) if candidates else 0

    def _build_local_compartimento_progress_snapshot(self, current_payload=None, total_compartimentos=None):
        from django.db.models import Q

        total = total_compartimentos
        try:
            total = int(total or 0)
        except Exception:
            total = 0
        if total <= 0:
            total = self._get_total_compartimentos_for_progress(
                getattr(self, 'compartimentos_avanco_json', None) if current_payload is None else current_payload
            )

        empty = {
            'total_compartimentos': total,
            'payload': {},
            'rows': [],
            'daily': {'mecanizada': 0.0, 'fina': 0.0},
            'cumulative': {'mecanizada': 0.0, 'fina': 0.0},
            'completed': {'mecanizada': 0, 'fina': 0},
        }
        if total <= 0:
            return empty

        normalizer = RdoTanque.normalize_compartimentos_payload
        previous = {
            str(i): {'mecanizada': 0, 'fina': 0}
            for i in range(1, total + 1)
        }

        qs = self.__class__.objects.none()
        try:
            ordem_atual = getattr(self, 'ordem_servico', None)
            os_num = getattr(ordem_atual, 'numero_os', None) if ordem_atual is not None else None
            if os_num not in (None, ''):
                qs = self.__class__.objects.filter(ordem_servico__numero_os=os_num)
            elif ordem_atual is not None:
                qs = self.__class__.objects.filter(ordem_servico=ordem_atual)
            else:
                qs = self.__class__.objects.filter(ordem_servico__isnull=True)

            if getattr(self, 'data', None) and getattr(self, 'pk', None):
                qs = qs.filter(Q(data__lt=self.data) | (Q(data=self.data) & Q(pk__lt=self.pk)))
            elif getattr(self, 'data', None):
                qs = qs.filter(data__lt=self.data)
            elif getattr(self, 'pk', None):
                qs = qs.exclude(pk=self.pk)

            aliases = set()
            for raw_value in (getattr(self, 'tanque_codigo', None), getattr(self, 'nome_tanque', None)):
                try:
                    if raw_value not in (None, ''):
                        aliases.add(str(raw_value).strip())
                except Exception:
                    continue
            for raw_value in list(aliases):
                try:
                    canon = _canonical_tank_alias_for_os(os_num, raw_value)
                    if canon:
                        aliases.add(str(canon).strip())
                except Exception:
                    continue
            if aliases:
                alias_q = Q()
                for alias in aliases:
                    alias_q |= Q(tanque_codigo__iexact=alias)
                    alias_q |= Q(nome_tanque__iexact=alias)
                qs = qs.filter(alias_q)
        except Exception:
            qs = self.__class__.objects.none()

        for prior in qs.order_by('data', 'pk'):
            prior_payload = normalizer(getattr(prior, 'compartimentos_avanco_json', None), total)
            for key, values in prior_payload.items():
                for category in self.COMPARTIMENTO_CATEGORIES:
                    new_total = previous[key][category] + values.get(category, 0)
                    previous[key][category] = max(0, min(100, new_total))

        effective_payload = normalizer(
            getattr(self, 'compartimentos_avanco_json', None) if current_payload is None else current_payload,
            total,
        )

        rows = []
        day_sum = {'mecanizada': 0, 'fina': 0}
        cumulative_sum = {'mecanizada': 0, 'fina': 0}
        completed = {'mecanizada': 0, 'fina': 0}

        for i in range(1, total + 1):
            key = str(i)
            row = {'index': i}
            for category in self.COMPARTIMENTO_CATEGORIES:
                previous_value = max(0, min(100, int(previous[key].get(category, 0) or 0)))
                today_value = max(0, min(100, int(effective_payload[key].get(category, 0) or 0)))
                remaining_before = max(0, 100 - previous_value)
                final_value = max(0, min(100, previous_value + today_value))
                remaining_after = max(0, 100 - final_value)
                row[category] = {
                    'anterior': previous_value,
                    'hoje': today_value,
                    'solicitado': today_value,
                    'final': final_value,
                    'restante': remaining_before,
                    'saldo_apos': remaining_after,
                    'bloqueado': remaining_before <= 0,
                }
                day_sum[category] += today_value
                cumulative_sum[category] += final_value
                if final_value >= 100:
                    completed[category] += 1
            rows.append(row)

        empty['payload'] = effective_payload
        empty['rows'] = rows
        empty['daily'] = {
            'mecanizada': round(day_sum['mecanizada'] / float(total), 2),
            'fina': round(day_sum['fina'] / float(total), 2),
        }
        empty['cumulative'] = {
            'mecanizada': round(cumulative_sum['mecanizada'] / float(total), 2),
            'fina': round(cumulative_sum['fina'] / float(total), 2),
        }
        empty['completed'] = completed
        return empty

    def _build_compartimento_progress_snapshot(self, current_payload=None, total_compartimentos=None):
        tank = self._get_matching_tank_snapshot()
        total = total_compartimentos
        try:
            total = int(total or 0)
        except Exception:
            total = 0
        if total <= 0:
            total = self._get_total_compartimentos_for_progress(
                getattr(self, 'compartimentos_avanco_json', None) if current_payload is None else current_payload
            )

        if tank is not None and hasattr(tank, 'build_compartimento_progress_snapshot'):
            try:
                return tank.build_compartimento_progress_snapshot(
                    current_payload=getattr(self, 'compartimentos_avanco_json', None) if current_payload is None else current_payload,
                    total_compartimentos=total if total > 0 else None,
                )
            except Exception:
                pass
        return self._build_local_compartimento_progress_snapshot(
            current_payload=current_payload,
            total_compartimentos=total if total > 0 else None,
        )

    def calcula_percentuais(self):
        try:
            if self.ensacamento_cumulativo not in (None, '') and self.ensacamento_previsao not in (None, '') and float(self.ensacamento_previsao) != 0:
                self.percentual_ensacamento = min((self.ensacamento_cumulativo / self.ensacamento_previsao) * 100, 100)
        except Exception:
            pass
        try:
            if self.icamento_cumulativo not in (None, '') and self.icamento_previsao not in (None, '') and float(self.icamento_previsao) != 0:
                self.percentual_icamento = min((self.icamento_cumulativo / self.icamento_previsao) * 100, 100)
        except Exception:
            pass
        try:
            if self.cambagem_cumulativo not in (None, '') and self.cambagem_previsao not in (None, '') and float(self.cambagem_previsao) != 0:
                self.percentual_cambagem = min((self.cambagem_cumulativo / self.cambagem_previsao) * 100, 100)
        except Exception:
            pass
        try:
            if getattr(self, 'percentual_limpeza_diario', None) in (None, '') and getattr(self, 'limpeza_mecanizada_diaria', None) in (None, ''):
                self.compute_limpeza_from_compartimentos()
        except Exception:
            pass
        try:
            if getattr(self, 'percentual_limpeza_diario_cumulativo', None) in (None, '') and getattr(self, 'limpeza_mecanizada_cumulativa', None) in (None, ''):
                self.compute_limpeza_cumulativa()
        except Exception:
            pass
        try:
            from decimal import Decimal as _D, ROUND_HALF_UP as _RH

            setup_day_pct = 100.0 if _rdo_has_setup_activity(self) else 0.0
            setup_cum_pct = setup_day_pct
            if not setup_cum_pct:
                try:
                    qs = self.__class__.objects.none()
                    ordem_atual = getattr(self, 'ordem_servico', None)
                    os_num = getattr(ordem_atual, 'numero_os', None) if ordem_atual is not None else None
                    if os_num not in (None, ''):
                        qs = self.__class__.objects.filter(ordem_servico__numero_os=os_num)
                    elif ordem_atual is not None:
                        qs = self.__class__.objects.filter(ordem_servico=ordem_atual)
                    else:
                        qs = self.__class__.objects.filter(ordem_servico__isnull=True)

                    if getattr(self, 'data', None) and getattr(self, 'pk', None):
                        qs = qs.filter(Q(data__lt=self.data) | (Q(data=self.data) & Q(pk__lt=self.pk)))
                    elif getattr(self, 'data', None):
                        qs = qs.filter(data__lt=self.data)
                    elif getattr(self, 'pk', None):
                        qs = qs.exclude(pk=self.pk)

                    for prior in qs.order_by('data', 'pk').prefetch_related('atividades_rdo'):
                        if _rdo_has_setup_activity(prior):
                            setup_cum_pct = 100.0
                            break
                except Exception:
                    setup_cum_pct = setup_day_pct

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

            if getattr(self, 'limpeza_fina_cumulativa', None) not in [None, '']:
                try:
                    val = _D(str(self.limpeza_fina_cumulativa))
                    self.percentual_limpeza_fina_cumulativo = val.quantize(_D('0.01'), rounding=_RH)
                except Exception:
                    pass

            pesos_day = {
                'percentual_setup': 5.0,
                'percentual_icamento': 7.0,
                'percentual_ensacamento': 7.0,
                'percentual_cambagem': 5.0,
                'percentual_limpeza_diario': 70.0,
                'percentual_limpeza_fina': 6.0,
            }
            pesos_cum = {
                'percentual_setup_cumulativo': 5.0,
                'percentual_icamento': 7.0,
                'percentual_ensacamento': 7.0,
                'percentual_cambagem': 5.0,
                'percentual_limpeza_diario_cumulativo': 70.0,
                'percentual_limpeza_fina_cumulativo': 6.0,
            }

            def valor(p):
                try:
                    if p == 'percentual_setup':
                        v = setup_day_pct
                    elif p == 'percentual_setup_cumulativo':
                        v = setup_cum_pct
                    elif p == 'percentual_limpeza_diario':
                        v = getattr(self, 'percentual_limpeza_diario', None)
                        if v in (None, ''):
                            v = getattr(self, 'limpeza_mecanizada_diaria', None)
                    elif p == 'percentual_limpeza_diario_cumulativo':
                        v = getattr(self, 'percentual_limpeza_diario_cumulativo', None)
                        if v in (None, ''):
                            v = getattr(self, 'limpeza_mecanizada_cumulativa', None)
                    elif p == 'percentual_limpeza_fina_cumulativo':
                        v = getattr(self, 'percentual_limpeza_fina_cumulativo', None)
                        if v in (None, ''):
                            v = getattr(self, 'limpeza_fina_cumulativa', None)
                    else:
                        v = getattr(self, p, None)
                    if v is None or v == '':
                        return 0.0
                    return float(v)
                except Exception:
                    return 0.0

            total_w_day = sum(pesos_day.values()) or 1.0
            total_day = sum(valor(campo) * peso for campo, peso in pesos_day.items())
            percentual_calc = total_day / total_w_day
            pct = _D(str(round(percentual_calc, 2)))
            if pct < _D('0'):
                pct = _D('0')
            if pct > _D('100'):
                pct = _D('100')
            self.percentual_avanco = pct.quantize(_D('0.01'), rounding=_RH)

            total_w_cum = sum(pesos_cum.values()) or 1.0
            total_cum = sum(valor(campo) * peso for campo, peso in pesos_cum.items())
            percentual_cum_calc = total_cum / total_w_cum
            pct_cum = _D(str(round(percentual_cum_calc, 2)))
            if pct_cum < _D('0'):
                pct_cum = _D('0')
            if pct_cum > _D('100'):
                pct_cum = _D('100')
            self.percentual_avanco_cumulativo = pct_cum.quantize(_D('0.01'), rounding=_RH)
        except Exception:
            pass

    def compute_limpeza_from_compartimentos(self):
        try:
            from decimal import Decimal as _D, ROUND_HALF_UP as _RH

            snapshot = self._build_compartimento_progress_snapshot()
            total = snapshot.get('total_compartimentos') or 0
            if total <= 0:
                return None

            day_mec = snapshot.get('daily', {}).get('mecanizada', 0.0)
            day_fina = snapshot.get('daily', {}).get('fina', 0.0)

            day_mec_dec = _D(str(round(day_mec, 2))).quantize(_D('0.01'), rounding=_RH)
            day_fina_dec = _D(str(round(day_fina, 2))).quantize(_D('0.01'), rounding=_RH)

            try:
                self.limpeza_mecanizada_diaria = day_mec_dec
            except Exception:
                pass
            try:
                self.percentual_limpeza_diario = day_mec_dec
            except Exception:
                pass
            try:
                self.avanco_limpeza = f'{day_mec_dec:.2f}'
            except Exception:
                pass
            try:
                self.limpeza_fina_diaria = day_fina_dec
            except Exception:
                pass
            try:
                self.percentual_limpeza_fina_diario = day_fina_dec
            except Exception:
                pass
            try:
                self.percentual_limpeza_fina = day_fina_dec
            except Exception:
                pass
            try:
                self.avanco_limpeza_fina = f'{day_fina_dec:.2f}'
            except Exception:
                pass
            return day_mec_dec
        except Exception:
            return None

    def compute_limpeza_cumulativa(self):
        try:
            from decimal import Decimal as _D, ROUND_HALF_UP as _RH

            snapshot = self._build_compartimento_progress_snapshot()
            total = snapshot.get('total_compartimentos') or 0
            if total <= 0:
                return None

            cum_mec = snapshot.get('cumulative', {}).get('mecanizada', 0.0)
            cum_fina = snapshot.get('cumulative', {}).get('fina', 0.0)

            cum_mec_dec = _D(str(round(cum_mec, 2))).quantize(_D('0.01'), rounding=_RH)
            cum_fina_dec = _D(str(round(cum_fina, 2))).quantize(_D('0.01'), rounding=_RH)

            try:
                self.limpeza_mecanizada_cumulativa = cum_mec_dec
            except Exception:
                pass
            try:
                self.percentual_limpeza_diario_cumulativo = cum_mec_dec
            except Exception:
                pass
            try:
                self.limpeza_fina_cumulativa = cum_fina_dec
            except Exception:
                pass
            try:
                self.percentual_limpeza_fina_cumulativo = cum_fina_dec
            except Exception:
                pass
            return cum_mec_dec
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
        def _to_date(value):
            try:
                if value in (None, ''):
                    return None
                if isinstance(value, date):
                    return value
                text = str(value).strip()
                if not text:
                    return None
                return datetime.strptime(text[:10], '%Y-%m-%d').date()
            except Exception:
                return None
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
            'previsao_termino': _to_date(data.get('previsao_termino')),
            'ensacamento_prev': _to_int(data.get('ensacamento_prev')),
            'icamento_prev': _to_int(data.get('icamento_prev')),
            'cambagem_prev': _to_int(data.get('cambagem_prev')),
            'tambores_dia': _to_int(data.get('tambores_dia')),
            'tambores_cumulativo': _to_int(data.get('tambores_cumulativo') or data.get('tambores_acu')),
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
        try:
            if getattr(self, 'data', None) and not getattr(self, 'data_inicio', None):
                self.data_inicio = self.data
            elif getattr(self, 'data_inicio', None) and not getattr(self, 'data', None):
                self.data = self.data_inicio
        except Exception:
            pass

        try:
            _normalize_instance_decimal_fields(self)
        except Exception:
            pass

        try:
            os_num = getattr(getattr(self, 'ordem_servico', None), 'numero_os', None)
            canon_code = _canonical_tank_alias_for_os(os_num, getattr(self, 'tanque_codigo', None))
            if canon_code:
                self.tanque_codigo = canon_code
            canon_name = _canonical_tank_alias_for_os(os_num, getattr(self, 'nome_tanque', None))
            if canon_name:
                self.nome_tanque = canon_name
        except Exception:
            pass

        self.validate_tanque_compartimentos_consistency()

        try:
            if getattr(self, 'total_hh_frente_real', None) in (None, ''):
                try:
                    self.compute_total_hh_frente_real()
                except Exception:
                    pass
        except Exception:
            pass

        try:
            if getattr(self, 'total_hh_cumulativo_real', None) in (None, ''):
                try:
                    self.compute_total_hh_cumulativo_real()
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
            *_OFFLOADING_ACTIVITY_VALUES,
            'Desobstrução de linhas', 'Desobstrução de linhas / Drain line clearing',
            'Drenagem inicial do tanque', 'Drenagem inicial do tanque / Tank draining started',
            'acesso ao tanque', 'Acesso ao Tanque / Tank access',
            'mobilização de material - dentro do tanque', 'Mobilização de Material - Dentro do Tanque / Material mobilization - Inside the tank',
            'mobilização de material - fora do tanque', 'Mobilização de Material - Fora do Tanque / Material mobilization - Outside the tank',
            'desmobilização do material - dentro do tanque', 'Desmobilização do Material - Dentro do Tanque / Material demobilization - Inside the tank',
            'desmobilização do material - fora do tanque', 'Desmobilização do Material - Fora do Tanque / Material demobilization - Outside the tank',
            'avaliação inicial da área de trabalho', 'Avaliação Inicial da Área de Trabalho / Pre-setup of the work area',
            'Instalação / Preparação / Montagem / Setup ', 'Instalação / Preparação / Montagem / Setup',
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
                'avaliação inicial da área de trabalho', 'Avaliação Inicial da Área de Trabalho / Pre-setup of the work area',
                *_OFFLOADING_ACTIVITY_VALUES,
                'Desobstrução de linhas', 'Desobstrução de linhas / Drain line clearing',
                'Instalação / Preparação / Montagem / Setup ', 'Instalação / Preparação / Montagem / Setup',
                'Drenagem inicial do tanque', 'Drenagem inicial do tanque / Tank draining started',
                'acesso ao tanque', 'Acesso ao Tanque / Tank access',
                'mobilização de material - dentro do tanque', 'Mobilização de Material - Dentro do Tanque / Material mobilization - Inside the tank',
                'mobilização de material - fora do tanque', 'Mobilização de Material - Fora do Tanque / Material mobilization - Outside the tank',
                'desmobilização do material - dentro do tanque', 'Desmobilização do Material - Dentro do Tanque / Material demobilization - Inside the tank',
                'desmobilização do material - fora do tanque', 'Desmobilização do Material - Fora do Tanque / Material demobilization - Outside the tank',
                'Jateamento, Jateamento/Blasting'
                'teste tubo a tubo', 'teste tubo a tubo / Tube-to-tube test',
                'teste hidrostático', 'teste hidrostático / Hydrostatic test',
                'limpeza mecânica', 'limpeza mecânica / Mechanical cleaning',
                'Limpeza de caixa d\'água / bebedouro', 'Limpeza de caixa d\'água / bebedouro / Water tank / water cooler cleaning',
                'Limpeza e higienização de coifas', 'Limpeza e Higienização de Coifas / Hoods cleaning and sanitization',
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
    SITUACAO_CHOICES = [
        ('embarcardo', 'Embarcado'),
        ('trocou_unidade', 'Trocou de Unidade'),
        ('retornou_base', 'Retornou para Base'),
    ]
    situacao = models.CharField(max_length=30, choices=SITUACAO_CHOICES, null=True, blank=True)

    def __str__(self):
        try:
            if self.modelo:
                return str(self.modelo)
        except Exception:
            pass
        return self.numero_serie or self.numero_tag or f"Equipamento {self.pk}"

    def save(self, *args, **kwargs):
        try:
            # Normalize identifiers to avoid case/whitespace duplicates.
            try:
                if self.numero_tag is not None:
                    self.numero_tag = str(self.numero_tag).strip().upper() or None
            except Exception:
                pass
            try:
                if self.numero_serie is not None:
                    self.numero_serie = str(self.numero_serie).strip().upper() or None
            except Exception:
                pass

            src_model = self.modelo_fk or self.modelo
            if src_model is not None:
                try:
                    if (not getattr(self, 'descricao', None) or str(self.descricao).strip() == '') and getattr(src_model, 'descricao', None):
                        desc = str(src_model.descricao)
                        max_len = self._meta.get_field('descricao').max_length or len(desc)
                        self.descricao = desc[:max_len]
                except Exception:
                    pass
            is_container = str(getattr(self, 'descricao', '') or '').strip().lower() == 'container'
            if is_container:
                self.fabricante = None
            elif src_model is not None:
                try:
                    if (not getattr(self, 'fabricante', None) or str(self.fabricante).strip() == '') and getattr(src_model, 'fabricante', None):
                        self.fabricante = src_model.fabricante
                except Exception:
                    pass
        except Exception:
            pass
        super().save(*args, **kwargs)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['numero_tag'],
                condition=(
                    Q(numero_tag__isnull=False)
                    & ~Q(numero_tag='')
                    & ~Q(situacao='trocou_unidade')
                    & ~Q(situacao='retornou_base')
                ),
                name='uniq_equip_numero_tag_active',
            ),
            models.UniqueConstraint(
                fields=['numero_serie'],
                condition=(
                    Q(numero_serie__isnull=False)
                    & ~Q(numero_serie='')
                    & ~Q(situacao='trocou_unidade')
                    & ~Q(situacao='retornou_base')
                ),
                name='uniq_equip_numero_serie_active',
            ),
        ]
        verbose_name_plural = "Equipamentos"

class EquipamentoFoto(models.Model):
    equipamento = models.ForeignKey('Equipamentos', on_delete=models.CASCADE, related_name='fotos_equipamento')
    foto = models.ImageField(upload_to='fotos_equipamento/', null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Foto {self.pk} - Equipamento {self.equipamento_id}"

    class Meta:

        verbose_name_plural = 'Fotos de Equipamento'


class EquipamentoSituacaoLog(models.Model):
    equipamento = models.ForeignKey('Equipamentos', on_delete=models.CASCADE, related_name='situacao_logs')
    previous = models.CharField(max_length=30, null=True, blank=True)
    current = models.CharField(max_length=30, null=True, blank=True)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    note = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Equip {getattr(self.equipamento, 'pk', '?')} {self.previous} → {self.current} @ {self.created_at.isoformat()}"


class EquipamentoIdentificadorLog(models.Model):
    TIPO_TAG = 'tag'
    TIPO_SERIE = 'serie'
    IDENTIFIER_CHOICES = [
        (TIPO_TAG, 'TAG'),
        (TIPO_SERIE, 'Número de Série'),
    ]

    equipamento = models.ForeignKey('Equipamentos', on_delete=models.CASCADE, related_name='identificador_logs')
    identifier_type = models.CharField(max_length=10, choices=IDENTIFIER_CHOICES)
    previous_value = models.CharField(max_length=100, null=True, blank=True)
    current_value = models.CharField(max_length=100, null=True, blank=True)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    note = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        tipo = 'TAG' if self.identifier_type == self.TIPO_TAG else 'SERIE'
        return f"Equip {getattr(self.equipamento, 'pk', '?')} {tipo}: {self.previous_value} -> {self.current_value} @ {self.created_at.isoformat()}"

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
    previsao_termino = models.DateField(null=True, blank=True)
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

    COMPARTIMENTO_CATEGORIES = ('mecanizada', 'fina')

    @staticmethod
    def _coerce_compartimento_percent(raw_value):
        try:
            if raw_value in (None, ''):
                return 0
            if isinstance(raw_value, str):
                text = raw_value.strip()
                if not text:
                    return 0
                if text.endswith('%'):
                    text = text[:-1].strip()
                text = text.replace(',', '.')
                num = float(text)
            else:
                num = float(raw_value)
        except Exception:
            return 0
        try:
            num = int(num)
        except Exception:
            num = 0
        if num < 0:
            return 0
        if num > 100:
            return 100
        return num

    def get_total_compartimentos(self):
        try:
            if getattr(self, 'numero_compartimentos', None):
                return int(self.numero_compartimentos)
        except Exception:
            pass
        try:
            if getattr(getattr(self, 'rdo', None), 'numero_compartimentos', None):
                return int(self.rdo.numero_compartimentos)
        except Exception:
            pass
        return 0

    def _get_tank_aliases(self):
        tank_aliases = set()
        for owner in (self, getattr(self, 'rdo', None)):
            if owner is None:
                continue
            try:
                raw_code = getattr(owner, 'tanque_codigo', None)
                if raw_code not in (None, ''):
                    tank_aliases.add(str(raw_code).strip())
            except Exception:
                pass
            try:
                raw_name = getattr(owner, 'nome_tanque', None)
                if raw_name not in (None, ''):
                    tank_aliases.add(str(raw_name).strip())
            except Exception:
                pass
        try:
            os_num_curr = getattr(getattr(self, 'rdo', None), 'ordem_servico', None)
            os_num_curr = getattr(os_num_curr, 'numero_os', None)
        except Exception:
            os_num_curr = None
        try:
            canon = _canonical_tank_alias_for_os(os_num_curr, getattr(self, 'tanque_codigo', None))
            if canon:
                tank_aliases.add(str(canon).strip())
        except Exception:
            pass
        try:
            canon_name = _canonical_tank_alias_for_os(os_num_curr, getattr(self, 'nome_tanque', None))
            if canon_name:
                tank_aliases.add(str(canon_name).strip())
        except Exception:
            pass
        try:
            canon_rdo_code = _canonical_tank_alias_for_os(
                os_num_curr,
                getattr(getattr(self, 'rdo', None), 'tanque_codigo', None),
            )
            if canon_rdo_code:
                tank_aliases.add(str(canon_rdo_code).strip())
        except Exception:
            pass
        try:
            canon_rdo_name = _canonical_tank_alias_for_os(
                os_num_curr,
                getattr(getattr(self, 'rdo', None), 'nome_tanque', None),
            )
            if canon_rdo_name:
                tank_aliases.add(str(canon_rdo_name).strip())
        except Exception:
            pass
        return {alias for alias in tank_aliases if alias}

    @classmethod
    def normalize_compartimentos_payload(cls, raw_payload, total_compartimentos):
        import json as _json

        total = 0
        try:
            total = int(total_compartimentos or 0)
        except Exception:
            total = 0

        normalized = {
            str(i): {'mecanizada': 0, 'fina': 0}
            for i in range(1, max(0, total) + 1)
        }
        if total <= 0:
            return normalized

        parsed = raw_payload
        try:
            if isinstance(raw_payload, str):
                parsed = _json.loads(raw_payload) if raw_payload.strip() else {}
            elif raw_payload is None:
                parsed = {}
        except Exception:
            parsed = {}

        if not isinstance(parsed, dict):
            return normalized

        for i in range(1, total + 1):
            key = str(i)
            item = parsed.get(key)
            if isinstance(item, dict):
                mec_raw = item.get('mecanizada', item.get('m', 0))
                fina_raw = item.get('fina', item.get('f', 0))
            else:
                mec_raw = item
                fina_raw = 0
            normalized[key] = {
                'mecanizada': cls._coerce_compartimento_percent(mec_raw),
                'fina': cls._coerce_compartimento_percent(fina_raw),
            }
        return normalized

    def get_prior_tank_snapshots(self):
        from django.db.models import Q

        try:
            if getattr(self, 'rdo', None) is None:
                return self.__class__.objects.none()
        except Exception:
            return self.__class__.objects.none()

        aliases = self._get_tank_aliases()
        if not aliases:
            return self.__class__.objects.none()

        ordem_atual = getattr(self.rdo, 'ordem_servico', None)
        os_num = getattr(ordem_atual, 'numero_os', None) if ordem_atual is not None else None

        qs = self.__class__.objects.select_related('rdo', 'rdo__ordem_servico')
        if os_num not in (None, ''):
            qs = qs.filter(rdo__ordem_servico__numero_os=os_num)
        else:
            qs = qs.filter(rdo__ordem_servico=ordem_atual)

        if getattr(self.rdo, 'data', None) and getattr(self.rdo, 'pk', None):
            qs = qs.filter(Q(rdo__data__lt=self.rdo.data) | (Q(rdo__data=self.rdo.data) & Q(rdo__pk__lt=self.rdo.pk)))
        elif getattr(self.rdo, 'data', None):
            qs = qs.filter(rdo__data__lt=self.rdo.data)

        tank_q = Q()
        for alias in aliases:
            tank_q |= Q(tanque_codigo__iexact=alias)
            tank_q |= Q(nome_tanque__iexact=alias)
        if tank_q:
            qs = qs.filter(tank_q)

        if getattr(self, 'pk', None):
            qs = qs.exclude(pk=self.pk)

        return qs.order_by('rdo__data', 'rdo__pk', 'pk')

    def build_compartimento_progress_snapshot(self, current_payload=None, total_compartimentos=None):
        total = self.get_total_compartimentos() if total_compartimentos is None else total_compartimentos
        try:
            total = int(total or 0)
        except Exception:
            total = 0

        empty = {
            'total_compartimentos': total,
            'payload': {},
            'rows': [],
            'daily': {'mecanizada': 0.0, 'fina': 0.0},
            'cumulative': {'mecanizada': 0.0, 'fina': 0.0},
            'completed': {'mecanizada': 0, 'fina': 0},
        }
        if total <= 0:
            return empty

        previous = {
            str(i): {'mecanizada': 0, 'fina': 0}
            for i in range(1, total + 1)
        }
        for prior in self.get_prior_tank_snapshots():
            prior_payload = self.normalize_compartimentos_payload(
                getattr(prior, 'compartimentos_avanco_json', None),
                total,
            )
            for key, values in prior_payload.items():
                for category in self.COMPARTIMENTO_CATEGORIES:
                    new_total = previous[key][category] + values.get(category, 0)
                    previous[key][category] = max(0, min(100, new_total))

        effective_payload = self.normalize_compartimentos_payload(
            getattr(self, 'compartimentos_avanco_json', None) if current_payload is None else current_payload,
            total,
        )

        rows = []
        day_sum = {'mecanizada': 0, 'fina': 0}
        cumulative_sum = {'mecanizada': 0, 'fina': 0}
        completed = {'mecanizada': 0, 'fina': 0}

        for i in range(1, total + 1):
            key = str(i)
            row = {'index': i}
            for category in self.COMPARTIMENTO_CATEGORIES:
                previous_value = max(0, min(100, int(previous[key].get(category, 0) or 0)))
                today_value = max(0, min(100, int(effective_payload[key].get(category, 0) or 0)))
                remaining_before = max(0, 100 - previous_value)
                final_value = max(0, min(100, previous_value + today_value))
                remaining_after = max(0, 100 - final_value)
                row[category] = {
                    'anterior': previous_value,
                    'hoje': today_value,
                    'solicitado': today_value,
                    'final': final_value,
                    'restante': remaining_before,
                    'saldo_apos': remaining_after,
                    'bloqueado': remaining_before <= 0,
                }
                day_sum[category] += today_value
                cumulative_sum[category] += final_value
                if final_value >= 100:
                    completed[category] += 1
            rows.append(row)

        empty['payload'] = effective_payload
        empty['rows'] = rows
        empty['daily'] = {
            'mecanizada': round(day_sum['mecanizada'] / float(total), 2),
            'fina': round(day_sum['fina'] / float(total), 2),
        }
        empty['cumulative'] = {
            'mecanizada': round(cumulative_sum['mecanizada'] / float(total), 2),
            'fina': round(cumulative_sum['fina'] / float(total), 2),
        }
        empty['completed'] = completed
        return empty

    def validate_compartimentos_payload(self, raw_payload, total_compartimentos=None):
        import json as _json

        requested_snapshot = self.build_compartimento_progress_snapshot(
            current_payload=raw_payload,
            total_compartimentos=total_compartimentos,
        )
        total = requested_snapshot.get('total_compartimentos') or 0
        payload = {
            str(i): {'mecanizada': 0, 'fina': 0}
            for i in range(1, int(total or 0) + 1)
        }
        errors = []

        for row in requested_snapshot.get('rows', []):
            key = str(row.get('index'))
            for category in self.COMPARTIMENTO_CATEGORIES:
                meta = row.get(category) or {}
                requested = int(meta.get('solicitado') or 0)
                remaining = int(meta.get('restante') or 0)
                accepted = requested
                if requested > remaining:
                    accepted = remaining
                    label = 'Limpeza fina' if category == 'fina' else 'Limpeza mecanizada/manual/robotizada'
                    if remaining <= 0:
                        msg = f'Compartimento {key} ({label}) já está concluído e não aceita novo avanço.'
                    else:
                        msg = f'Compartimento {key} ({label}) aceita no máximo {remaining}% hoje.'
                    errors.append({
                        'index': row.get('index'),
                        'category': category,
                        'remaining': remaining,
                        'requested': requested,
                        'message': msg,
                    })
                payload[key][category] = accepted

        sanitized_snapshot = self.build_compartimento_progress_snapshot(
            current_payload=payload,
            total_compartimentos=total_compartimentos,
        )
        return {
            'is_valid': not errors,
            'errors': errors,
            'payload': payload,
            'json': _json.dumps(payload, ensure_ascii=False),
            'snapshot': sanitized_snapshot,
        }

    def get_previous_compartimentos_payload(self):
        snapshot = self.build_compartimento_progress_snapshot(current_payload={})
        rows = []
        for row in snapshot.get('rows', []):
            mec = row.get('mecanizada') or {}
            fina = row.get('fina') or {}
            rows.append({
                'index': row.get('index'),
                'mecanizada': mec.get('anterior', 0),
                'fina': fina.get('anterior', 0),
                'mecanizada_restante': mec.get('restante', 0),
                'fina_restante': fina.get('restante', 0),
                'mecanizada_final': mec.get('anterior', 0),
                'fina_final': fina.get('anterior', 0),
                'mecanizada_saldo_apos': mec.get('restante', 0),
                'fina_saldo_apos': fina.get('restante', 0),
                'mecanizada_bloqueado': bool(mec.get('bloqueado')),
                'fina_bloqueado': bool(fina.get('bloqueado')),
            })
        return rows

    def compute_limpeza_from_compartimentos(self):
        try:
            from decimal import Decimal as _D, ROUND_HALF_UP as _RH

            snapshot = self.build_compartimento_progress_snapshot()
            total = snapshot.get('total_compartimentos') or 0
            if total <= 0:
                return None

            day_mec = snapshot.get('daily', {}).get('mecanizada', 0.0)
            day_fina = snapshot.get('daily', {}).get('fina', 0.0)

            day_mec_dec = _D(str(round(day_mec, 2))).quantize(_D('0.01'), rounding=_RH)
            day_fina_dec = _D(str(round(day_fina, 2))).quantize(_D('0.01'), rounding=_RH)

            try:
                self.limpeza_mecanizada_diaria = day_mec_dec
            except Exception:
                pass
            try:
                self.percentual_limpeza_diario = day_mec_dec
            except Exception:
                pass
            try:
                self.avanco_limpeza = f'{day_mec_dec:.2f}'
            except Exception:
                pass
            try:
                self.limpeza_fina_diaria = day_fina_dec
            except Exception:
                pass
            try:
                self.percentual_limpeza_fina_diario = day_fina_dec
            except Exception:
                pass
            try:
                self.percentual_limpeza_fina = day_fina_dec
            except Exception:
                pass
            try:
                self.avanco_limpeza_fina = f'{day_fina_dec:.2f}'
            except Exception:
                pass
            return day_mec_dec
        except Exception:
            return None

    def recompute_metrics(self, only_when_missing=True):
        try:
            import json as _json
            tank_code = getattr(self, 'tanque_codigo', None) or getattr(self, 'nome_tanque', None)
            if not tank_code:
                return None
            tank_code = str(tank_code).strip()

            from django.db.models import Q

            tank_aliases = set()
            try:
                tank_aliases.add(str(tank_code).strip())
            except Exception:
                pass
            try:
                raw_name = getattr(self, 'nome_tanque', None)
                if raw_name not in (None, ''):
                    tank_aliases.add(str(raw_name).strip())
            except Exception:
                pass
            try:
                os_num_curr = getattr(getattr(self, 'rdo', None), 'ordem_servico', None)
                os_num_curr = getattr(os_num_curr, 'numero_os', None)
            except Exception:
                os_num_curr = None
            try:
                canon = _canonical_tank_alias_for_os(os_num_curr, tank_code)
                if canon:
                    tank_aliases.add(str(canon).strip())
            except Exception:
                pass
            try:
                canon_name = _canonical_tank_alias_for_os(os_num_curr, getattr(self, 'nome_tanque', None))
                if canon_name:
                    tank_aliases.add(str(canon_name).strip())
            except Exception:
                pass

            tank_filter_q = Q()
            for alias in list(tank_aliases):
                if alias:
                    tank_filter_q |= Q(tanques__tanque_codigo__iexact=alias)
                    tank_filter_q |= Q(tanques__nome_tanque__iexact=alias)
            if not tank_filter_q:
                tank_filter_q = Q(tanques__tanque_codigo__iexact=tank_code)

            def _pick_prior_tank(prior):
                try:
                    q = Q()
                    for alias in list(tank_aliases):
                        if alias:
                            q |= Q(tanque_codigo__iexact=alias)
                            q |= Q(nome_tanque__iexact=alias)
                    if q:
                        pt = prior.tanques.filter(q).order_by('-id').first()
                    else:
                        pt = prior.tanques.filter(tanque_codigo__iexact=tank_code).order_by('-id').first()
                    return pt
                except Exception:
                    try:
                        return prior.tanques.filter(tanque_codigo__iexact=tank_code).order_by('-id').first()
                    except Exception:
                        return None

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

            prior_tanks_qs = self.get_prior_tank_snapshots()
            for prior in prior_tanks_qs:
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

            RDOModel = self.rdo.__class__
            ordem_atual = getattr(self.rdo, 'ordem_servico', None)
            os_num = getattr(ordem_atual, 'numero_os', None) if ordem_atual is not None else None
            if os_num not in (None, ''):
                qs = RDOModel.objects.filter(ordem_servico__numero_os=os_num)
            else:
                qs = RDOModel.objects.filter(ordem_servico=ordem_atual)
            if getattr(self.rdo, 'data', None) and getattr(self.rdo, 'pk', None):
                # Pegar apenas RDOs de dias anteriores OU do mesmo dia mas com ID menor
                qs = qs.filter(Q(data__lt=self.rdo.data) | (Q(data=self.rdo.data) & Q(pk__lt=self.rdo.pk)))
            elif getattr(self.rdo, 'data', None):
                qs = qs.filter(data__lt=self.rdo.data)
            qs = qs.filter(tank_filter_q).distinct().order_by('data', 'pk')

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

                if not only_when_missing or getattr(self, 'limpeza_mecanizada_diaria', None) in (None, ''):
                    self.limpeza_mecanizada_diaria = _D(str(round(day_avg_m or 0.0, 2))).quantize(_D('0.01'), rounding=_RH)
                if not only_when_missing or getattr(self, 'percentual_limpeza_diario', None) in (None, ''):
                    self.percentual_limpeza_diario = _D(str(round(day_avg_m or 0.0, 2))).quantize(_D('0.01'), rounding=_RH)
                if not only_when_missing or getattr(self, 'limpeza_fina_diaria', None) in (None, ''):
                    self.limpeza_fina_diaria = _D(str(round(day_avg_f or 0.0, 2))).quantize(_D('0.01'), rounding=_RH)
                if not only_when_missing or getattr(self, 'percentual_limpeza_fina_diario', None) in (None, ''):
                    self.percentual_limpeza_fina_diario = _D(str(round(day_avg_f or 0.0, 2))).quantize(_D('0.01'), rounding=_RH)
                if not only_when_missing or getattr(self, 'percentual_limpeza_fina', None) in (None, ''):
                    self.percentual_limpeza_fina = _D(str(round(day_avg_f or 0.0, 2))).quantize(_D('0.01'), rounding=_RH)
                if not only_when_missing or getattr(self, 'avanco_limpeza', None) in (None, ''):
                    self.avanco_limpeza = f"{round(day_avg_m or 0.0, 2):.2f}"
                if not only_when_missing or getattr(self, 'avanco_limpeza_fina', None) in (None, ''):
                    self.avanco_limpeza_fina = f"{round(day_avg_f or 0.0, 2):.2f}"

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

                setup_day = 100.0 if _rdo_has_setup_activity(self.rdo) else None
                ens_day = _clamp01_opt(_to_num(getattr(self, 'percentual_ensacamento', None)))
                ic_day = _clamp01_opt(_to_num(getattr(self, 'percentual_icamento', None)))
                camb_day = _clamp01_opt(_to_num(getattr(self, 'percentual_cambagem', None)))

                has_any_day_component = any(v is not None for v in (setup_day, lim_mec_day, ens_day, ic_day, camb_day, lim_fina_day))
                if has_any_day_component:
                    def _v0(x):
                        return 0.0 if x is None else float(x)

                    total_w = 5.0 + 70.0 + 7.0 + 7.0 + 5.0 + 6.0
                    day_weighted = (
                        (_v0(setup_day) * 5.0)
                        + (_v0(lim_mec_day) * 70.0)
                        + (_v0(ens_day) * 7.0)
                        + (_v0(ic_day) * 7.0)
                        + (_v0(camb_day) * 5.0)
                        + (_v0(lim_fina_day) * 6.0)
                    ) / total_w
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
                setup_c = 100.0 if _rdo_has_setup_activity(self.rdo) else 0.0
                if not setup_c:
                    for prior in qs:
                        if _rdo_has_setup_activity(prior):
                            setup_c = 100.0
                            break

                total_w = 5.0 + 70.0 + 7.0 + 7.0 + 5.0 + 6.0
                cum_weighted = (
                    (setup_c * 5.0)
                    + (lim_mec_cum * 70.0)
                    + (ens_c * 7.0)
                    + (ic_c * 7.0)
                    + (camb_c * 5.0)
                    + (lim_fina_cum * 6.0)
                ) / total_w
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
                        pt = _pick_prior_tank(prior)
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

                # Cumulativo deve refletir historico + dia atual.
                try:
                    total_ensac += int(getattr(self, 'ensacamento_dia', 0) or 0)
                except Exception:
                    pass
                try:
                    total_ic += int(getattr(self, 'icamento_dia', 0) or 0)
                except Exception:
                    pass
                try:
                    total_camb += int(getattr(self, 'cambagem_dia', 0) or 0)
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
                            pt = _pick_prior_tank(prior)
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
                            pt = _pick_prior_tank(prior)
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
                            cum = int(getattr(self, 'ensacamento_cumulativo', 0) or 0)
                            num = _D(str(int(cum)))
                            den = _D(str(int(prev)))
                            pct = _clamp((num / den) * _D('100'))
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
                            cum = int(getattr(self, 'icamento_cumulativo', 0) or 0)
                            num = _D(str(int(cum)))
                            den = _D(str(int(prev)))
                            pct = _clamp((num / den) * _D('100'))
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
                            cum = int(getattr(self, 'cambagem_cumulativo', 0) or 0)
                            num = _D(str(int(cum)))
                            den = _D(str(int(prev)))
                            pct = _clamp((num / den) * _D('100'))
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
                    if prev not in (None, '') and float(prev) != 0:
                        cum = getattr(self, 'ensacamento_cumulativo', 0) or 0
                        num = Decimal(str(int(cum)))
                        den = Decimal(str(int(prev)))
                        pct = min((num / den) * Decimal('100'), Decimal('100'))
                        self.percentual_ensacamento = _q2(pct)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if hasattr(self, 'percentual_icamento') and getattr(self, 'percentual_icamento', None) in (None, ''):
                prev = getattr(self, 'icamento_prev', None)
                try:
                    if prev not in (None, '') and float(prev) != 0:
                        cum = getattr(self, 'icamento_cumulativo', 0) or 0
                        num = Decimal(str(int(cum)))
                        den = Decimal(str(int(prev)))
                        pct = min((num / den) * Decimal('100'), Decimal('100'))
                        self.percentual_icamento = _q2(pct)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if hasattr(self, 'percentual_cambagem') and getattr(self, 'percentual_cambagem', None) in (None, ''):
                prev = getattr(self, 'cambagem_prev', None)
                try:
                    if prev not in (None, '') and float(prev) != 0:
                        cum = getattr(self, 'cambagem_cumulativo', 0) or 0
                        num = Decimal(str(int(cum)))
                        den = Decimal(str(int(prev)))
                        pct = min((num / den) * Decimal('100'), Decimal('100'))
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
        try:
            if hasattr(self, 'tambores_cumulativo'):
                self.tambores_cumulativo = _to_int(getattr(self, 'tambores_cumulativo'))
        except Exception:
            pass
    def save(self, *args, **kwargs):
        try:
            os_num = getattr(getattr(getattr(self, 'rdo', None), 'ordem_servico', None), 'numero_os', None)
            canon_code = _canonical_tank_alias_for_os(os_num, getattr(self, 'tanque_codigo', None))
            if canon_code:
                self.tanque_codigo = canon_code
            canon_name = _canonical_tank_alias_for_os(os_num, getattr(self, 'nome_tanque', None))
            if canon_name:
                self.nome_tanque = canon_name
        except Exception:
            pass

        try:
            _normalize_instance_decimal_fields(self)
        except Exception:
            pass

        try:
            self._normalize_cleaning_and_predictions()
        except Exception:
            pass
        try:
            self.recompute_metrics(only_when_missing=False)
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


class MobileSyncEvent(models.Model):
    STATE_PROCESSING = 'processing'
    STATE_DONE = 'done'
    STATE_ERROR = 'error'
    STATE_CHOICES = (
        (STATE_PROCESSING, 'Processing'),
        (STATE_DONE, 'Done'),
        (STATE_ERROR, 'Error'),
    )

    client_uuid = models.CharField(max_length=64, unique=True, db_index=True)
    operation = models.CharField(max_length=64, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mobile_sync_events',
    )
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    state = models.CharField(max_length=16, choices=STATE_CHOICES, default=STATE_PROCESSING)
    http_status = models.PositiveSmallIntegerField(default=202)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-id']
        verbose_name_plural = 'Mobile Sync Events'

    def __str__(self):
        return f'{self.client_uuid} [{self.operation}] {self.state}'


class MobileApiToken(models.Model):
    key = models.CharField(max_length=64, unique=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='mobile_api_tokens',
    )
    device_name = models.CharField(max_length=120, blank=True, null=True)
    platform = models.CharField(max_length=30, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    last_used_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-id']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['expires_at']),
        ]
        verbose_name_plural = 'Mobile API Tokens'

    def __str__(self):
        return f'{self.user_id}:{self.device_name or "device"} ({ "ativo" if self.is_active else "inativo" })'

    def is_expired(self):
        try:
            if self.expires_at is None:
                return False
            from django.utils import timezone
            return self.expires_at <= timezone.now()
        except Exception:
            return False

    @classmethod
    def generate_key(cls):
        for _ in range(8):
            candidate = secrets.token_hex(32)
            if not cls.objects.filter(key=candidate).exists():
                return candidate
        return secrets.token_hex(32)


class SupervisorAccessHeartbeat(models.Model):
    CHANNEL_WEB = 'web'
    CHANNEL_MOBILE = 'mobile'
    CHANNEL_CHOICES = (
        (CHANNEL_WEB, 'Web'),
        (CHANNEL_MOBILE, 'Mobile'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='supervisor_access_heartbeats',
    )
    channel = models.CharField(max_length=16, choices=CHANNEL_CHOICES, db_index=True)
    window_start = models.DateTimeField(db_index=True)
    path = models.CharField(max_length=255, blank=True, null=True)
    session_key = models.CharField(max_length=64, blank=True, null=True)
    device_name = models.CharField(max_length=120, blank=True, null=True)
    platform = models.CharField(max_length=30, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-window_start', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'channel', 'window_start'],
                name='uniq_supervisor_access_heartbeat_window',
            ),
        ]
        indexes = [
            models.Index(fields=['channel', 'window_start']),
            models.Index(fields=['user', 'channel', 'window_start']),
        ]
        verbose_name = 'Supervisor Access Heartbeat'
        verbose_name_plural = 'Supervisor Access Heartbeats'

    def __str__(self):
        return f'{self.user_id}:{self.channel}@{self.window_start}'


class RDOChannelEvent(models.Model):
    CHANNEL_WEB = 'web'
    CHANNEL_MOBILE = 'mobile'
    CHANNEL_CHOICES = (
        (CHANNEL_WEB, 'Web'),
        (CHANNEL_MOBILE, 'Mobile'),
    )

    EVENT_CREATE = 'create'
    EVENT_UPDATE = 'update'
    EVENT_CHOICES = (
        (EVENT_CREATE, 'Create'),
        (EVENT_UPDATE, 'Update'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rdo_channel_events',
    )
    rdo = models.ForeignKey(
        'RDO',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='channel_events',
    )
    ordem_servico = models.ForeignKey(
        'OrdemServico',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rdo_channel_events',
    )
    channel = models.CharField(max_length=16, choices=CHANNEL_CHOICES, db_index=True)
    event_type = models.CharField(max_length=16, choices=EVENT_CHOICES, db_index=True)
    source_path = models.CharField(max_length=255, blank=True, null=True)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-occurred_at', '-id']
        indexes = [
            models.Index(fields=['channel', 'event_type', 'occurred_at']),
            models.Index(fields=['user', 'channel', 'occurred_at']),
            models.Index(fields=['rdo', 'channel', 'event_type']),
        ]
        verbose_name = 'RDO Channel Event'
        verbose_name_plural = 'RDO Channel Events'

    def __str__(self):
        return f'{self.channel}:{self.event_type}:rdo={self.rdo_id or "?"}@{self.occurred_at}'
