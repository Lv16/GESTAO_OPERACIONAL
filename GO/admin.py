from django.contrib import admin
from django import forms
from decimal import Decimal, ROUND_HALF_UP
from .models import OrdemServico, RDO, RDOAtividade, Cliente, Unidade, Pessoa, Funcao
from .models import Equipamentos, EquipamentoFoto, Formulario_de_inspeção, Modelo
from .models import RdoTanque
try:
	from .models import CoordenadorCanonical
except Exception:
	CoordenadorCanonical = None


class RdoTanqueInline(admin.TabularInline):
	model = RdoTanque
	extra = 0
	fields = (
		'tanque_codigo', 'nome_tanque', 'tipo_tanque', 'numero_compartimentos',
		'gavetas', 'patamares', 'volume_tanque_exec', 'servico_exec', 'metodo_exec',
		'operadores_simultaneos', 'h2s_ppm', 'lel', 'co_ppm', 'o2_percent', 'sentido_limpeza',
		'tempo_bomba', 'ensacamento_dia', 'icamento_dia', 'cambagem_dia',
		'tambores_dia', 'residuos_solidos', 'residuos_totais',
		'total_liquido',
		# cumulativos operacionais (readonly in usage, but editable in admin if needed)
		'ensacamento_cumulativo', 'icamento_cumulativo', 'cambagem_cumulativo',
		'total_liquido_cumulativo', 'residuos_solidos_cumulativo',
		# percentuais operacionais cumulativos
		'percentual_ensacamento', 'percentual_icamento', 'percentual_cambagem',
		'percentual_avanco', 'percentual_avanco_cumulativo',
		# limpeza fina cumulativa (supervisor can provide/override)
		'limpeza_fina_cumulativa',
		# campos de limpeza solicitados
		'percentual_limpeza_diario', 'percentual_limpeza_cumulativo', 'percentual_limpeza_fina_cumulativo',
	)
	readonly_fields = ('percentual_ensacamento', 'percentual_icamento', 'percentual_cambagem', 'percentual_avanco', 'percentual_avanco_cumulativo')

	def _fmt_pct(self, val):
		try:
			if val is None or val == '':
				return ''
			return f"{float(val):.2f}%"
		except Exception:
			return val


@admin.register(RDO)
class RDOAdmin(admin.ModelAdmin):

	class RDOAdminForm(forms.ModelForm):
		"""Formulário de admin estendido para RDO com opção de propagar campos para os tanques.

		`propagar_tanques` é um campo virtual (não persistido) que, quando marcado,
		copia os campos de limpeza do `RDO` para cada `RdoTanque` associado.
		"""
		propagar_tanques = forms.BooleanField(required=False, label='Propagar campos de limpeza para tanques')

		class Meta:
			model = RDO
			fields = '__all__'

	form = RDOAdminForm

	def save_model(self, request, obj, form, change):
		"""Salva o RDO e, se o checkbox `propagar_tanques` estiver marcado,
		replica os campos canônicos de limpeza para cada RdoTanque associado.

		A replicação aplica quantização para decimais (2 casas) e valida limites
		para percentuais (0..100)."""
		super().save_model(request, obj, form, change)

		try:
			if not form.cleaned_data.get('propagar_tanques'):
				return
		except Exception:
			return

		# Helpers locais para conversão
		def _to_decimal_q(v):
			if v in (None, ''):
				return None
			try:
				if isinstance(v, Decimal):
					return v.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
				s = str(v).strip().replace(',', '.')
				d = Decimal(str(float(s)))
				return d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
			except Exception:
				try:
					d = Decimal(str(v))
					return d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
				except Exception:
					return None

		def _to_int_safe(v):
			if v in (None, ''):
				return None
			try:
				return int(float(v))
			except Exception:
				try:
					return int(v)
				except Exception:
					return None

		# Campos a replicar (similar ao comportamento do endpoint supervisor)
		try:
			tanks_qs = obj.tanques.all()
		except Exception:
			tanks_qs = []

		for tank in tanks_qs:
			updated = False
			try:
				# mecanizada diário (decimal)
				m_daily = getattr(obj, 'limpeza_mecanizada_diaria', None)
				mq = _to_decimal_q(m_daily)
				if mq is not None and hasattr(tank, 'limpeza_mecanizada_diaria'):
					try:
						tank.limpeza_mecanizada_diaria = mq
						updated = True
					except Exception:
						pass

				# mecanizada cumulativa (int)
				m_acu = getattr(obj, 'limpeza_mecanizada_cumulativa', None)
				mac = _to_int_safe(m_acu)
				if mac is not None and hasattr(tank, 'limpeza_mecanizada_cumulativa'):
					try:
						tank.limpeza_mecanizada_cumulativa = max(0, min(100, int(mac)))
						updated = True
					except Exception:
						pass

				# fina diário (decimal + int mapping to percentual)
				f_daily = getattr(obj, 'limpeza_fina_diaria', None)
				fq = _to_decimal_q(f_daily)
				if fq is not None and hasattr(tank, 'limpeza_fina_diaria'):
					try:
						tank.limpeza_fina_diaria = fq
						updated = True
					except Exception:
						pass
				if fq is not None and hasattr(tank, 'percentual_limpeza_fina'):
					try:
						tank.percentual_limpeza_fina = max(0, min(100, int(round(float(fq)))))
						updated = True
					except Exception:
						pass

				# fina cumulativa (int -> percentual_limpeza_fina_cumulativo)
				f_acu = getattr(obj, 'limpeza_fina_cumulativa', None) or getattr(obj, 'percentual_limpeza_fina_cumulativo', None)
				fac = _to_int_safe(f_acu)
				if fac is not None and hasattr(tank, 'percentual_limpeza_fina_cumulativo'):
					try:
						tank.percentual_limpeza_fina_cumulativo = max(0, min(100, int(fac)))
						updated = True
					except Exception:
						pass

				# outros espelhos / percentuais
				try:
					if hasattr(tank, 'percentual_limpeza_diario'):
						src = getattr(obj, 'percentual_limpeza_diario', None) or getattr(obj, 'limpeza_mecanizada_diaria', None)
						sd = _to_decimal_q(src)
						if sd is not None:
							tank.percentual_limpeza_diario = sd
							updated = True
				except Exception:
					pass

				if updated:
					try:
						tank.save()
					except Exception:
						# swallow to avoid breaking admin save
						pass
			except Exception:
				continue
	def ec_times_display(self, obj):
		try:
			j = getattr(obj, 'ec_times_json', None)
			if not j:
				# fallback to legacy fields
				ent = getattr(obj, 'entrada_confinado', None)
				sai = getattr(obj, 'saida_confinado', None)
				if ent or sai:
					return f"{str(ent) or ''} → {str(sai) or ''}"
				return ''
			import json
			parsed = json.loads(j)
			entr = parsed.get('entrada') or []
			sai = parsed.get('saida') or []
			pairs = []
			for i in range(max(len(entr), len(sai))):
				pairs.append(f"{entr[i] if i < len(entr) else ''}→{sai[i] if i < len(sai) else ''}")
			return '; '.join(pairs)
		except Exception:
			return ''

	list_display = ('id', 'rdo', 'data_inicio', 'nome_tanque', 'turno', 'ordem_servico', 'ec_times_display')
	search_fields = ('rdo', 'nome_tanque', 'ordem_servico__numero_os')
	list_filter = ('turno', 'confinado', 'data_inicio')
	date_hierarchy = 'data_inicio'
	# Exibir tambores como somente leitura (preenchido automaticamente a partir de ensacamento)
	readonly_fields = ('ec_times_json', 'tambores', 'fotos_json')


if CoordenadorCanonical is not None:
	@admin.register(CoordenadorCanonical)
	class CoordenadorCanonicalAdmin(admin.ModelAdmin):
		list_display = ('canonical_name', 'variants', 'created_at', 'updated_at')
		search_fields = ('canonical_name', 'variants')
		ordering = ('canonical_name',)

	# Mostrar tanques relacionados diretamente na página do RDO
	inlines = (RdoTanqueInline,)


@admin.register(RDOAtividade)
class RDOAtividadeAdmin(admin.ModelAdmin):
	list_display = ('id', 'rdo', 'ordem', 'atividade', 'inicio', 'fim')
	search_fields = ('atividade', 'ordem', 'rdo__rdo')


@admin.register(OrdemServico)
class OrdemServicoAdmin(admin.ModelAdmin):
	list_display = (
		'id', 'numero_os', 'frente', 'cliente', 'unidade', 'servico', 'metodo',
		'tanque', 'tanques', 'status_operacao', 'status_geral', 'status_comercial', 'pob'
	)
	search_fields = ('numero_os', 'Cliente__nome', 'Unidade__nome', 'servico', 'servicos', 'tanques', 'pob')
	list_filter = ('status_operacao', 'status_geral', 'status_comercial', 'metodo', 'metodo_secundario')
	readonly_fields = ()
	ordering = ('-numero_os', 'frente')

admin.site.register(Cliente)
admin.site.register(Unidade)
admin.site.register(Pessoa)
admin.site.register(Funcao)
# Registrar modelos de equipamentos para administração
@admin.register(Equipamentos)
class EquipamentosAdmin(admin.ModelAdmin):
	# Mostrar nome do modelo preferindo `modelo_fk` quando preenchido
	def modelo_display(self, obj):
		try:
			if getattr(obj, 'modelo_fk', None):
				return str(obj.modelo_fk)
		except Exception:
			pass
		return str(obj.modelo) if obj.modelo else ''
	modelo_display.short_description = 'Modelo'

	list_display = ('id', 'modelo_display', 'numero_serie', 'numero_tag', 'fabricante')
	search_fields = ('numero_serie', 'numero_tag', 'fabricante', 'modelo__nome')
	autocomplete_fields = ('modelo', 'modelo_fk')


@admin.register(Modelo)
class ModeloAdmin(admin.ModelAdmin):
	list_display = ('id', 'nome', 'fabricante')
	search_fields = ('nome', 'fabricante')


@admin.register(EquipamentoFoto)
class EquipamentoFotoAdmin(admin.ModelAdmin):
	list_display = ('id', 'equipamento', 'foto', 'criado_em')
	search_fields = ('equipamento__numero_serie', 'equipamento__numero_tag')


@admin.register(Formulario_de_inspeção)
class FormularioInspecaoAdmin(admin.ModelAdmin):
	list_display = ('id', 'responsável', 'equipamentos', 'data_inspecao_material', 'local_inspecao', 'previsao_retorno')
	search_fields = ('responsável', 'equipamentos__numero_serie', 'equipamentos__numero_tag')


@admin.register(RdoTanque)
class RdoTanqueAdmin(admin.ModelAdmin):
	# Helpers de exibição de percentuais diários (calculados on-the-fly)
	def pct_ensacamento_dia(self, obj):
		try:
			prev = getattr(obj, 'ensacamento_prev', None) or getattr(getattr(obj, 'rdo', None), 'ensacamento_prev', None)
			val = getattr(obj, 'ensacamento_dia', None) or 0
			if not prev or float(prev) <= 0:
				return None
			pct = (float(val) / float(prev)) * 100.0
			pct = 0.0 if pct < 0 else (100.0 if pct > 100.0 else pct)
			return round(pct, 2)
		except Exception:
			return None
	pct_ensacamento_dia.short_description = 'Ensac. dia %'

	def pct_icamento_dia(self, obj):
		try:
			prev = getattr(obj, 'icamento_prev', None) or getattr(getattr(obj, 'rdo', None), 'icamento_prev', None)
			val = getattr(obj, 'icamento_dia', None) or 0
			if not prev or float(prev) <= 0:
				return None
			pct = (float(val) / float(prev)) * 100.0
			pct = 0.0 if pct < 0 else (100.0 if pct > 100.0 else pct)
			return round(pct, 2)
		except Exception:
			return None
	pct_icamento_dia.short_description = 'Içamento dia %'

	def pct_cambagem_dia(self, obj):
		try:
			prev = getattr(obj, 'cambagem_prev', None) or getattr(getattr(obj, 'rdo', None), 'cambagem_prev', None)
			val = getattr(obj, 'cambagem_dia', None) or 0
			if not prev or float(prev) <= 0:
				return None
			pct = (float(val) / float(prev)) * 100.0
			pct = 0.0 if pct < 0 else (100.0 if pct > 100.0 else pct)
			return round(pct, 2)
		except Exception:
			return None
	pct_cambagem_dia.short_description = 'Cambagem dia %'

	def pct_avanco(self, obj):
		try:
			v = getattr(obj, 'percentual_avanco', None)
			if v in (None, ''):
				return ''
			return f"{float(v):.2f}%"
		except Exception:
			return ''
	pct_avanco.short_description = 'Avanço %'

	def pct_avanco_cum(self, obj):
		try:
			v = getattr(obj, 'percentual_avanco_cumulativo', None)
			if v in (None, ''):
				return ''
			return f"{float(v):.2f}%"
		except Exception:
			return ''
	pct_avanco_cum.short_description = 'Avanço cum. %'

	list_display = (
		'id', 'rdo', 'tanque_codigo', 'nome_tanque', 'tipo_tanque',
		'numero_compartimentos', 'gavetas', 'patamares', 'volume_tanque_exec',
		'servico_exec', 'metodo_exec', 'avanco_limpeza_fina', 'tambores_dia', 'residuos_solidos', 'residuos_totais',
		'percentual_limpeza_diario', 'percentual_limpeza_cumulativo', 'percentual_limpeza_fina_cumulativo',
		# percentuais diários (calc.) e cumulativos operacionais
		'pct_ensacamento_dia', 'pct_icamento_dia', 'pct_cambagem_dia',
		'percentual_ensacamento', 'percentual_icamento', 'percentual_cambagem', 'pct_avanco', 'pct_avanco_cum',
		'limpeza_fina_cumulativa', 'ensacamento_cumulativo', 'icamento_cumulativo', 'cambagem_cumulativo',
		'total_liquido_cumulativo', 'residuos_solidos_cumulativo',
		'created_at'
	)
	search_fields = ('tanque_codigo', 'nome_tanque', 'rdo__rdo', 'rdo__ordem_servico__numero_os')
	list_filter = ('tipo_tanque',)
	# Esconder campos legados/antigos no admin (mantidos por compatibilidade no modelo)
	exclude = (
		'limpeza_mecanizada_diaria',
		'limpeza_mecanizada_cumulativa',
		'percentual_limpeza_fina',
		'percentual_limpeza_fina_diario',
		# 'percentual_avanco' removido para tornar o campo visível no admin
	)
	readonly_fields = (
		'created_at', 'updated_at',
		# exibir percentuais como somente leitura (computados)
		'pct_ensacamento_dia', 'pct_icamento_dia', 'pct_cambagem_dia',
		'percentual_ensacamento', 'percentual_icamento', 'percentual_cambagem', 'percentual_avanco', 'percentual_avanco_cumulativo',
		# formatted helpers
		'pct_avanco', 'pct_avanco_cum',
	)

	fieldsets = (
		('Identificação', {
			'fields': (
				'rdo', 'tanque_codigo', 'nome_tanque', 'tipo_tanque',
				'numero_compartimentos', 'gavetas', 'patamares', 'volume_tanque_exec',
			)
		}),
		('Operação', {
			'fields': (
				'servico_exec', 'metodo_exec', 'espaco_confinado', 'operadores_simultaneos',
				'h2s_ppm', 'lel', 'co_ppm', 'o2_percent', 'sentido_limpeza', 'tempo_bomba', 'bombeio', 'total_liquido',
				'tambores_dia', 'residuos_solidos', 'residuos_totais', 'compartimentos_avanco_json',
			)
		}),
		('Previsões por tanque', {
			'fields': ('ensacamento_prev', 'icamento_prev', 'cambagem_prev')
		}),
		('Valores diários por tanque', {
			'fields': (
				'percentual_limpeza_diario', 'limpeza_fina_diaria', 'avanco_limpeza_fina',
				'ensacamento_dia', 'icamento_dia', 'cambagem_dia',
				# percentuais diários calculados
				'pct_ensacamento_dia', 'pct_icamento_dia', 'pct_cambagem_dia',
			)
		}),
		('Cumulativos por tanque', {
			'fields': (
				'percentual_limpeza_cumulativo', 'percentual_limpeza_fina_cumulativo',
				'limpeza_fina_cumulativa',
				'ensacamento_cumulativo', 'icamento_cumulativo', 'cambagem_cumulativo',
				'total_liquido_cumulativo', 'residuos_solidos_cumulativo',
				# percentuais de avanço (diário e cumulativo)
				'percentual_avanco', 'percentual_avanco_cumulativo',
				# visualizações formatadas
				'pct_avanco', 'pct_avanco_cum',
				'percentual_ensacamento', 'percentual_icamento', 'percentual_cambagem',
			)
		}),
		('Meta', {
			'fields': ('created_at', 'updated_at')
		}),
	)