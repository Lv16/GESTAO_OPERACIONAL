from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.utils.dateparse import parse_date
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Q
import os
import logging
import time
import requests

from .models import Equipamentos, Modelo, Formulario_de_inspeção, EquipamentoFoto, EquipamentoSituacaoLog, EquipamentoIdentificadorLog
from django.http import HttpResponse, Http404
from django.conf import settings
from django.contrib.staticfiles import finders
from io import BytesIO
import hashlib
import PIL.Image

openssl_md5 = getattr(hashlib, 'openssl_md5', None)
if openssl_md5 is not None:
	def _openssl_md5_compat(data=b'', *args, **kwargs):
		try:
			return openssl_md5(data)
		except TypeError:
			return openssl_md5()
	hashlib.openssl_md5 = _openssl_md5_compat

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Image, Spacer, PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from datetime import datetime
import uuid

from .rdo_access import build_read_only_json_response, user_has_read_only_access


logger = logging.getLogger(__name__)


def _normalize_identifier(value):
	if value is None:
		return None
	try:
		v = str(value).strip().upper()
		return v or None
	except Exception:
		return None


def _serialize_identifier_history(equipamento, limit=30):
	history = []
	try:
		logs = EquipamentoIdentificadorLog.objects.filter(equipamento=equipamento).order_by('-created_at')[:limit]
		for l in logs:
			history.append({
				'identifier_type': l.identifier_type,
				'previous': l.previous_value,
				'current': l.current_value,
				'changed_by': (l.changed_by.get_full_name() if (l.changed_by and hasattr(l.changed_by, 'get_full_name')) else (l.changed_by.username if l.changed_by else None)),
				'created_at': l.created_at.isoformat(),
				'note': l.note,
			})
	except Exception:
		pass
	return history


def _normalize_unit_value(value):
	try:
		return str(value or '').strip().upper()
	except Exception:
		return ''


def _unit_key(cliente, embarcacao, numero_os):
	return (
		_normalize_unit_value(cliente),
		_normalize_unit_value(embarcacao),
		_normalize_unit_value(numero_os),
	)


def _situacao_permite_movimentacao(situacao):
	key = str(situacao or '').strip().lower()
	return key in ('trocou_unidade', 'retornou_base')


def _queryset_identificador_ativo(qs):
	return qs.exclude(situacao__in=['trocou_unidade', 'retornou_base'])


def _situacao_para_manutencao(value):
	key = str(value or '').strip().lower()
	if key in ('retornou_base', 'retornou para base', 'retornou para a base'):
		return 'Retornou para a base'
	return value


def _unit_display(cliente, embarcacao, numero_os):
	parts = []
	if cliente:
		parts.append(f"Cliente: {cliente}")
	if embarcacao:
		parts.append(f"Unidade: {embarcacao}")
	if numero_os:
		parts.append(f"OS: {numero_os}")
	return ' | '.join(parts) if parts else 'unidade atual não informada'


def _build_equipamento_choice_label(equipamento):
	tag = str(getattr(equipamento, 'numero_tag', '') or '').strip()
	serie = str(getattr(equipamento, 'numero_serie', '') or '').strip()
	descricao = str(getattr(equipamento, 'descricao', '') or '').strip()
	partes = [p for p in (tag, serie, descricao) if p]
	if partes:
		return ' - '.join(partes)
	return f"Equipamento {getattr(equipamento, 'pk', '')}"


def _is_container_descricao(value):
	return str(value or '').strip().lower() == 'container'


def _delete_storage_file_silently(name):
	if not name:
		return
	try:
		default_storage.delete(name)
	except Exception:
		logger.warning('Falha ao remover arquivo de storage: %s', name, exc_info=True)


def _delete_storage_files(names):
	for name in names or []:
		_delete_storage_file_silently(name)


def _append_photo_payload(photo_urls, saved_photo_basenames, foto_field):
	try:
		photo_urls.append(foto_field.url)
	except Exception:
		try:
			photo_urls.append(default_storage.url(foto_field.name))
		except Exception:
			photo_urls.append(foto_field.name)
	try:
		saved_photo_basenames.add(os.path.basename(getattr(foto_field, 'name', '') or ''))
	except Exception:
		pass


def _save_equipamento_photo(equipamento, uploaded_file, original_name=None, max_attempts=3):
	filename = os.path.basename(original_name or getattr(uploaded_file, 'name', 'upload'))
	filename = filename or 'upload'
	last_exc = None

	for attempt in range(1, max_attempts + 1):
		ef = EquipamentoFoto(equipamento=equipamento)
		saved_name = ''
		try:
			if hasattr(uploaded_file, 'seek'):
				try:
					uploaded_file.seek(0)
				except Exception:
					pass

			# `upload_to` do campo já adiciona `fotos_equipamento/`.
			target_name = f'{uuid.uuid4().hex[:8]}_{filename}'
			ef.foto.save(target_name, uploaded_file, save=False)
			saved_name = getattr(ef.foto, 'name', '') or ''
			ef.save()
			return ef
		except OperationalError as exc:
			last_exc = exc
			_delete_storage_file_silently(saved_name)
			if 'locked' in str(exc).lower() and attempt < max_attempts:
				time.sleep(0.15 * attempt)
				continue
			raise
		except Exception:
			_delete_storage_file_silently(saved_name)
			raise

	if last_exc is not None:
		raise last_exc
	raise RuntimeError('Falha ao salvar foto do equipamento.')


def _identifier_terms_for_descricao(value):
	if _is_container_descricao(value):
		return {
			'tag': 'Número do Container',
			'serie': 'Número da Eslinga',
			'pair': 'Número do Container ou Número da Eslinga',
			'updated_message': 'Dados do container atualizados em todas as linhas relacionadas ao equipamento.',
			'unchanged_message': 'Nenhuma alteração dos dados do container foi detectada.',
		}
	return {
		'tag': 'TAG',
		'serie': 'Número de Série',
		'pair': 'TAG ou Número de Série',
		'updated_message': 'TAG/Série atualizadas em todas as linhas relacionadas ao equipamento.',
		'unchanged_message': 'Nenhuma alteração de identificadores foi detectada.',
	}

def enviar_para_manutencao(equipamento):
    try:
        payload = {
			"tipoEquipamentoNome": str(getattr(equipamento, "descricao", "") or "").strip() or None,
			"modeloEquipamento": str(getattr(equipamento, "modelo_fk", None) or getattr(equipamento, "modelo", "") or "").strip() or None,
	        "numeroSerie": getattr(equipamento, "numero_serie", None),
			"tag": getattr(equipamento, "numero_tag", None),
            "situacaoEquipamento": _situacao_para_manutencao(getattr(equipamento, "situacao", None)),
            "dataRetornoBase": datetime.now().strftime('%Y-%m-%d'),
		}
        
        headers = {
			"Content-Type": "application/json",
            "x-integration-key": settings.SYNCHRO_INTEGRATION_KEY,
		}
        
        response = requests.post(
			settings.MANUTENCAO_API_URL,
            json=payload,
            headers=headers,
            timeout=10,
		)
        
        if response.status_code in [200, 201]:
            return True

        if response.status_code == 409:
            logger.info(
				"Equipamento %s já possui manutenção aberta. Status=%s Resposta=%s",
                getattr(equipamento, "pk", None),
                response.status_code,
                response.text,
			)
            return True

        if response.status_code not in [200, 201]:
            logger.error(
				"Erro ao enviar equipamento para manutenção. Status=%s Resposta=%s",
                response.status_code,
                response.text,
			)
            return False
    except Exception:
        logger.exception(
            "Falha ao enviar equipamento %s para manutencao",
            getattr(equipamento, "pk", None),
        )
        return False

@login_required
@require_POST
@transaction.atomic
def save_equipamento_ajax(request):
	if user_has_read_only_access(getattr(request, 'user', None)):
		return build_read_only_json_response('salvar equipamentos')

	saved_storage_names = []
	files_to_delete_after_commit = []
	try:
		cliente = request.POST.get('cliente', '').strip()
		embarcacao = request.POST.get('embarcacao', '').strip()
		responsavel = request.POST.get('responsavel', '').strip()
		numero_os = request.POST.get('numero_os', '').strip()
		data_inspecao_raw = request.POST.get('data_inspecao', '').strip()
		local = request.POST.get('local', '').strip()
		previsao_retorno_raw = request.POST.get('previsao_retorno', '').strip()

		modelo_name = request.POST.get('modelo', '').strip()
		serie = (request.POST.get('serie', '') or '').strip().upper()
		tag = (request.POST.get('tag', '') or '').strip().upper()
		fabricante = request.POST.get('fabricante', '').strip()
		descricao = request.POST.get('descricao', '').strip()
		situacao = request.POST.get('situacao', '').strip()

		data_inspecao = parse_date(data_inspecao_raw) if data_inspecao_raw else None
		previsao_retorno = parse_date(previsao_retorno_raw) if previsao_retorno_raw else None

		modelo_obj = None
		if modelo_name:
			modelo_obj = Modelo.objects.filter(nome__iexact=modelo_name).first()
			if modelo_obj is None:
				try:
					modelo_obj = Modelo.objects.create(nome=modelo_name)
				except Exception:
					modelo_obj = None

		equipamento_id = request.POST.get('equipamento_id') or request.POST.get('id')
		source_equipamento_id = request.POST.get('source_equipamento_id')
		equipamento = None
		source_equipamento = None
		if equipamento_id:
			try:
				equipamento = Equipamentos.objects.filter(pk=int(equipamento_id)).first()
			except Exception:
				equipamento = None

		if source_equipamento_id and not equipamento:
			try:
				source_equipamento = Equipamentos.objects.filter(pk=int(source_equipamento_id)).first()
			except Exception:
				source_equipamento = None

		descricao_contexto = (
			descricao
			or (equipamento.descricao if equipamento else '')
			or (source_equipamento.descricao if source_equipamento else '')
		)
		identifier_terms = _identifier_terms_for_descricao(descricao_contexto)

		# For quick updates (e.g., situação via table), reuse current identifiers
		# when TAG/Série are not explicitly posted.
		if equipamento and not tag and not serie:
			tag = (equipamento.numero_tag or '').strip().upper()
			serie = (equipamento.numero_serie or '').strip().upper()

		# Business rule: new cadastro must include at least one identifier.
		if not equipamento and not tag and not serie:
			return JsonResponse({'success': False, 'error': f'Informe {identifier_terms["pair"]}.'}, status=400)

		# Guard against duplicates before DB write for friendly feedback.
		exclude_pk = equipamento.pk if equipamento else None
		incoming_key = _unit_key(cliente, embarcacao, numero_os)
		if tag:
			q_tag = Equipamentos.objects.filter(numero_tag__iexact=tag)
			if exclude_pk:
				q_tag = q_tag.exclude(pk=exclude_pk)
			active_tag = _queryset_identificador_ativo(q_tag).order_by('-id').first()
			if active_tag:
				existing_key = _unit_key(active_tag.cliente, active_tag.embarcacao, active_tag.numero_os)
				allow_from_source = bool(
					source_equipamento
					and active_tag.pk == source_equipamento.pk
					and not equipamento
					and any(incoming_key)
					and incoming_key != existing_key
				)
				if not allow_from_source:
						return JsonResponse({
							'success': False,
							'error': (
								'Equipamento já está ativo nesta operação. '
								if incoming_key == existing_key else
								'Equipamento já está ativo em outra operação e não pode ficar em duas unidades ao mesmo tempo. '
								'Para movimentar, altere antes a situação para "Trocou de Unidade" ou "Retornou para Base". '
								f'Local atual: {_unit_display(active_tag.cliente, active_tag.embarcacao, active_tag.numero_os)}.'
							),
						}, status=400)
		if serie:
			q_serie = Equipamentos.objects.filter(numero_serie__iexact=serie)
			if exclude_pk:
				q_serie = q_serie.exclude(pk=exclude_pk)
			active_serie = _queryset_identificador_ativo(q_serie).order_by('-id').first()
			if active_serie:
				existing_key = _unit_key(active_serie.cliente, active_serie.embarcacao, active_serie.numero_os)
				allow_from_source = bool(
					source_equipamento
					and active_serie.pk == source_equipamento.pk
					and not equipamento
					and any(incoming_key)
					and incoming_key != existing_key
				)
				if not allow_from_source:
						return JsonResponse({
							'success': False,
							'error': (
								'Equipamento já está ativo nesta operação. '
								if incoming_key == existing_key else
								'Equipamento já está ativo em outra operação e não pode ficar em duas unidades ao mesmo tempo. '
								'Para movimentar, altere antes a situação para "Trocou de Unidade" ou "Retornou para Base". '
								f'Local atual: {_unit_display(active_serie.cliente, active_serie.embarcacao, active_serie.numero_os)}.'
							),
						}, status=400)
		# capture previous values before any updates so we can log changes reliably
		old_situacao = None
		old_tag = None
		old_serie = None
		if equipamento:
			try:
				old_situacao = equipamento.situacao
			except Exception:
				old_situacao = None
			try:
				old_tag = equipamento.numero_tag
			except Exception:
				old_tag = None
			try:
				old_serie = equipamento.numero_serie
			except Exception:
				old_serie = None

		if equipamento:
			new_cliente = cliente or equipamento.cliente
			new_embarcacao = embarcacao or equipamento.embarcacao
			new_numero_os = numero_os or equipamento.numero_os
			new_descricao = descricao or equipamento.descricao
			current_key = _unit_key(equipamento.cliente, equipamento.embarcacao, equipamento.numero_os)
			new_key = _unit_key(new_cliente, new_embarcacao, new_numero_os)
			if current_key != new_key and (not _situacao_permite_movimentacao(old_situacao)):
				return JsonResponse({
					'success': False,
					'error': (
						'Equipamento já está ativo em outra operação e não pode ficar em duas unidades ao mesmo tempo. '
						'Para movimentar, altere antes a situação para "Trocou de Unidade" ou "Retornou para Base". '
						f'Local atual: {_unit_display(equipamento.cliente, equipamento.embarcacao, equipamento.numero_os)}.'
					),
				}, status=400)

			if modelo_obj is not None:
				equipamento.modelo = modelo_obj
				try:
					equipamento.modelo_fk = modelo_obj
				except Exception:
					pass
			equipamento.descricao = new_descricao
			if _is_container_descricao(new_descricao):
				equipamento.fabricante = None
			else:
				equipamento.fabricante = fabricante or equipamento.fabricante
			equipamento.numero_serie = serie or equipamento.numero_serie
			equipamento.numero_tag = tag or equipamento.numero_tag
			equipamento.cliente = cliente or equipamento.cliente
			equipamento.embarcacao = embarcacao or equipamento.embarcacao
			if situacao:
				equipamento.situacao = situacao
			equipamento.numero_os = numero_os or equipamento.numero_os
			try:
				equipamento.save()
			except IntegrityError:
				return JsonResponse({'success': False, 'error': f'{identifier_terms["pair"]} já está em uso por outro equipamento.'}, status=400)
			try:
				nova_situacao = (equipamento.situacao or '').strip().lower()
				situacao_anterior = (old_situacao or '').strip().lower()

				if (
					nova_situacao == 'retornou_base'
					and situacao_anterior != 'retornou_base'
				):
					transaction.on_commit(lambda eq_id=equipamento.pk: enviar_para_manutencao(
						Equipamentos.objects.get(pk=eq_id)
					))
			except Exception:
				logger.exception('Falha ao agendar integração com manutenção.')
		else:
			if source_equipamento:
				source_key = _unit_key(source_equipamento.cliente, source_equipamento.embarcacao, source_equipamento.numero_os)
				if any(incoming_key) and incoming_key != source_key and not _situacao_permite_movimentacao(source_equipamento.situacao):
					prev_source_situacao = source_equipamento.situacao
					source_equipamento.situacao = 'trocou_unidade'
					source_equipamento.save(update_fields=['situacao'])
					try:
						log = EquipamentoSituacaoLog(equipamento=source_equipamento, previous=prev_source_situacao, current='trocou_unidade', note='Movimentado para nova OS')
						try:
							log.changed_by = request.user
						except Exception:
							pass
						log.save()
					except Exception:
						pass

			source_modelo = None
			if source_equipamento:
				source_modelo = source_equipamento.modelo_fk or source_equipamento.modelo
			create_modelo = modelo_obj or source_modelo
			create_descricao = descricao or (source_equipamento.descricao if source_equipamento else None)
			create_fabricante = None if _is_container_descricao(create_descricao) else (fabricante or (source_equipamento.fabricante if source_equipamento else None))
			create_tag = tag or (source_equipamento.numero_tag if source_equipamento else None)
			create_serie = serie or (source_equipamento.numero_serie if source_equipamento else None)

			try:
				equipamento = Equipamentos.objects.create(
					modelo=create_modelo,
					modelo_fk=create_modelo,
					fabricante=create_fabricante or None,
					descricao=create_descricao or None,
					numero_serie=create_serie or None,
					numero_tag=create_tag or None,
					cliente=cliente or None,
					embarcacao=embarcacao or None,
					situacao=situacao or None,
					numero_os=numero_os or None,
				)
			except IntegrityError:
				return JsonResponse({'success': False, 'error': f'{identifier_terms["pair"]} já está em uso por outro equipamento.'}, status=400)

		formulario = None
		last_form = Formulario_de_inspeção.objects.filter(equipamentos=equipamento).order_by('-id').first()
		if last_form:
			last_form.responsável = responsavel or last_form.responsável
			last_form.data_inspecao_material = data_inspecao or last_form.data_inspecao_material
			last_form.local_inspecao = local or last_form.local_inspecao
			last_form.previsao_retorno = previsao_retorno or last_form.previsao_retorno
			last_form.save()
			formulario = last_form
		else:
			formulario = Formulario_de_inspeção.objects.create(
				responsável=responsavel or None,
				equipamentos=equipamento,
				data_inspecao_material=data_inspecao,
				local_inspecao=local or None,
				previsao_retorno=previsao_retorno,
			)

		photo_urls = []
		saved_photo_basenames = set()
		photos = []
		existing_photo_urls_raw = request.POST.get('existing_photo_urls')
		existing_photo_basenames = None
		if existing_photo_urls_raw:
			try:
				import json
				_existing = json.loads(existing_photo_urls_raw)
				if isinstance(_existing, list):
					existing_photo_basenames = set()
					for u in _existing:
						try:
							bn = os.path.basename(str(u).split('?')[0])
							if bn:
								existing_photo_basenames.add(bn)
						except Exception:
							continue
			except Exception:
				existing_photo_basenames = None
		if hasattr(request, 'FILES'):
			for key in ('photos', 'fotos', 'fotos[]'):
				if key in request.FILES:
					photos.extend(request.FILES.getlist(key))
			if not photos:
				for key in request.FILES:
					photos.extend(request.FILES.getlist(key))
		seen = set()
		filtered = []
		for f in photos:
			ident = (getattr(f, 'name', None), getattr(f, 'size', None))
			if ident in seen:
				continue
			seen.add(ident)
			filtered.append(f)
		photos = filtered

		for f in photos:
			ef = _save_equipamento_photo(equipamento, f)
			if getattr(ef.foto, 'name', None):
				saved_storage_names.append(ef.foto.name)
			_append_photo_payload(photo_urls, saved_photo_basenames, ef.foto)

		# Removido: não clonar fotos do equipamento de origem ao criar novo equipamento.

		try:
			if equipamento and existing_photo_basenames is not None:
				kept_basenames = set(existing_photo_basenames or ()) | set(saved_photo_basenames or ())
				qs = EquipamentoFoto.objects.filter(equipamento=equipamento).order_by('id')
				for old in qs:
					try:
						old_basename = os.path.basename(getattr(old.foto, 'name', '') or '')
						if old_basename and (old_basename not in kept_basenames):
							old_storage_name = getattr(old.foto, 'name', '') or ''
							old.delete()
							if old_storage_name:
								files_to_delete_after_commit.append(old_storage_name)
					except Exception:
						continue
		except Exception:
			pass

		result = {
			'keep_open': True if (request.POST.get('keep_open') in ('1', 'true', 'True')) else False,
			'success': True,
			'equipamento': {
				'id': equipamento.pk,
				'situacao': equipamento.situacao or '',
				'modelo': str(equipamento.modelo_fk or equipamento.modelo) if (equipamento.modelo_fk or equipamento.modelo) else '',
				'fabricante': equipamento.fabricante or '',
				'descricao': equipamento.descricao or '',
				'numero_serie': equipamento.numero_serie or '',
				'numero_tag': equipamento.numero_tag or '',
			},
			'formulario': {
				'id': formulario.pk,
				'responsavel': formulario.responsável or '',
				'data_inspecao': formulario.data_inspecao_material.isoformat() if formulario.data_inspecao_material else '',
				'local_inspecao': formulario.local_inspecao or '',
				'previsao_retorno': formulario.previsao_retorno.isoformat() if formulario.previsao_retorno else '',
				'photo_urls': photo_urls,
			},
			'situacao_history': [],
			'identifier_history': []
		}

		# create identifier logs for TAG/Série changes (including first set on create)
		try:
			note = (request.POST.get('identificador_motivo') or '').strip() or None
			new_tag = _normalize_identifier(getattr(equipamento, 'numero_tag', None))
			new_serie = _normalize_identifier(getattr(equipamento, 'numero_serie', None))
			old_tag_n = _normalize_identifier(old_tag)
			old_serie_n = _normalize_identifier(old_serie)

			if old_tag_n != new_tag and (old_tag_n or new_tag):
				log = EquipamentoIdentificadorLog(
					equipamento=equipamento,
					identifier_type=EquipamentoIdentificadorLog.TIPO_TAG,
					previous_value=old_tag_n,
					current_value=new_tag,
					note=note,
				)
				try:
					log.changed_by = request.user
				except Exception:
					pass
				log.save()

			if old_serie_n != new_serie and (old_serie_n or new_serie):
				log = EquipamentoIdentificadorLog(
					equipamento=equipamento,
					identifier_type=EquipamentoIdentificadorLog.TIPO_SERIE,
					previous_value=old_serie_n,
					current_value=new_serie,
					note=note,
				)
				try:
					log.changed_by = request.user
				except Exception:
					pass
				log.save()
		except Exception:
			pass

		# create situacao log if situacao changed or set
		log_created = False
		try:
			# use captured previous situação (old_situacao) from before we updated o equipamento
			old = old_situacao
			new = equipamento.situacao if equipamento else None
			if new is not None and str(new) != str(old):
				try:
					log = EquipamentoSituacaoLog(equipamento=equipamento, previous=old, current=new)
					try:
						log.changed_by = request.user
					except Exception:
						pass
					log.save()
					log_created = True
				except Exception:
					pass
		except Exception:
			pass

		# attach recent situacao log entries (after possibly creating a new one)
		try:
			result['situacao_history'] = []
			logs = EquipamentoSituacaoLog.objects.filter(equipamento=equipamento).order_by('-created_at')[:10]
			for l in logs:
				result['situacao_history'].append({
					'previous': l.previous,
					'current': l.current,
					'changed_by': (l.changed_by.get_full_name() if (l.changed_by and hasattr(l.changed_by, 'get_full_name')) else (l.changed_by.username if l.changed_by else None)),
					'created_at': l.created_at.isoformat(),
					'note': l.note,
				})
		except Exception:
			pass

		# attach recent identifier history entries
		try:
			result['identifier_history'] = _serialize_identifier_history(equipamento, limit=30)
		except Exception:
			pass

		if files_to_delete_after_commit:
			transaction.on_commit(lambda names=list(files_to_delete_after_commit): _delete_storage_files(names))

		return JsonResponse(result)

	except Exception as e:
		try:
			transaction.set_rollback(True)
		except Exception:
			pass
		_delete_storage_files(saved_storage_names)
		logger.exception(
			'Falha ao salvar equipamento via AJAX (equipamento_id=%s, source_equipamento_id=%s, numero_os=%s)',
			request.POST.get('equipamento_id') or request.POST.get('id'),
			request.POST.get('source_equipamento_id'),
			request.POST.get('numero_os'),
		)
		return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
def relatorio_equipamento_pdf(request, pk):
	try:
		openssl_md5 = getattr(hashlib, 'openssl_md5', None)
		if openssl_md5 is not None:
			def _openssl_md5_compat(data=b'', *args, **kwargs):
				try:
					return openssl_md5(data)
				except TypeError:
					return openssl_md5()
			hashlib.openssl_md5 = _openssl_md5_compat

		equipamento = Equipamentos.objects.filter(pk=pk).first()
		if not equipamento:
			raise Http404("Equipamento não encontrado")

		formulario = Formulario_de_inspeção.objects.filter(equipamentos=equipamento).order_by('-id').first()

		foto_obj = EquipamentoFoto.objects.filter(equipamento=equipamento).order_by('id').first()

		buf = BytesIO()
		margin = 18 * mm
		doc = SimpleDocTemplate(buf, pagesize=A4,
								leftMargin=margin, rightMargin=margin,
								topMargin=margin, bottomMargin=margin)

		styles = getSampleStyleSheet()
		title_style = ParagraphStyle('title', parent=styles['Heading1'], alignment=TA_CENTER, fontName='Helvetica-Bold', fontSize=18, leading=22, spaceAfter=6)
		subtitle_style = ParagraphStyle('subtitle', parent=styles['Normal'], fontName='Helvetica', fontSize=10, textColor=colors.grey, alignment=TA_CENTER, spaceAfter=8)
		label_style = ParagraphStyle('label', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, alignment=TA_LEFT)
		value_style = ParagraphStyle('value', parent=styles['Normal'], fontName='Helvetica', fontSize=10, alignment=TA_LEFT)
		field_label_style = ParagraphStyle('field_label', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#444444'))
		field_value_style = ParagraphStyle('field_value', parent=styles['Normal'], fontName='Helvetica', fontSize=10, textColor=colors.HexColor('#222222'))

		story = []

		logo_path = None
		try:
			candidate = (
				finders.find('js/img/Logo_Preto.png')
				or finders.find('js/img/logo_home.png')
				or finders.find('img/Logo_Preto.png')
				or finders.find('img/logo_home.png')
				or finders.find('img/logo_home.jpg')
				or finders.find('logo_home.png')
			)
		except Exception:
			candidate = None
		if not candidate and getattr(settings, 'STATIC_ROOT', None):
			p0 = os.path.join(settings.STATIC_ROOT, 'js', 'img', 'Logo_Preto.png')
			p0b = os.path.join(settings.STATIC_ROOT, 'js', 'img', 'logo_home.png')
			p1 = os.path.join(settings.STATIC_ROOT, 'img', 'Logo_Preto.png')
			p2 = os.path.join(settings.STATIC_ROOT, 'img', 'logo_home.png')
			if os.path.exists(p0):
				candidate = p0
			elif os.path.exists(p0b):
				candidate = p0b
			elif os.path.exists(p1):
				candidate = p1
			elif os.path.exists(p2):
				candidate = p2

		if candidate:
			logo_path = candidate

		if logo_path:
			try:
				img_logo = Image(logo_path)
				img_logo.drawHeight = 34 * mm
				img_logo.drawWidth = img_logo.drawHeight * (img_logo.imageWidth / img_logo.imageHeight)
			except Exception:
				img_logo = None
		else:
			img_logo = None

		if img_logo:
			try:
				img_logo.drawHeight = 18 * mm
				img_logo.drawWidth = img_logo.drawHeight * (img_logo.imageWidth / img_logo.imageHeight)
			except Exception:
				pass
			header_data = []
			logo_cell = img_logo
			title_cell = [Paragraph('Relatório do Equipamento', title_style), Paragraph(f'Equipamento ID: {equipamento.pk} — Gerado em {datetime.now().strftime("%d/%m/%Y %H:%M")}', subtitle_style)]
			header_data.append([logo_cell, title_cell])
			row_h = (getattr(img_logo, 'drawHeight', 18 * mm) + (4 * mm))
			header_table = Table(header_data, colWidths=[20 * mm, doc.width - (20 * mm)], rowHeights=[row_h])
			header_table.setStyle(TableStyle([
				('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
				('LEFTPADDING',(0,0),(-1,-1),0), ('RIGHTPADDING',(0,0),(-1,-1),0),
				('ALIGN', (0,0), (0,0), 'LEFT'),
				('ALIGN', (1,0), (1,0), 'CENTER'),
				('VALIGN', (1,0), (1,0), 'MIDDLE'),
			]))
			story.append(header_table)
			hr = Table([[" "]], colWidths=[doc.width])
			hr.setStyle(TableStyle([
				('LINEBELOW', (0,0), (-1,-1), 0.7, colors.HexColor('#e0e0e0')),
				('LEFTPADDING',(0,0),(-1,-1),0), ('RIGHTPADDING',(0,0),(-1,-1),0), ('TOPPADDING',(0,0),(-1,-1),0), ('BOTTOMPADDING',(0,0),(-1,-1),0),
			]))
			story.append(hr)
			story.append(Spacer(1, 5 * mm))

		section_title_style = ParagraphStyle('section', parent=styles['Heading2'], alignment=TA_LEFT, fontName='Helvetica-Bold', fontSize=14, spaceAfter=6)
		story.append(Paragraph('Dados do Equipamento', section_title_style))

		fields = []
		fields.append(('Descrição', equipamento.descricao or ''))
		fields.append(('Modelo', str(equipamento.modelo) if equipamento.modelo else ''))
		fields.append(('Fabricante', equipamento.fabricante or ''))
		fields.append(('Série', equipamento.numero_serie or ''))
		fields.append(('TAG', equipamento.numero_tag or ''))
		fields.append(('Cliente', equipamento.cliente or ''))
		fields.append(('Embarcação', equipamento.embarcacao or ''))
		fields.append(('Nº OS', equipamento.numero_os or ''))
		fields.append(('Data da Inspeção', formulario.data_inspecao_material.strftime('%d/%m/%Y') if (formulario and formulario.data_inspecao_material) else ''))
		fields.append(('Local', (formulario.local_inspecao if formulario else '') or ''))
		fields.append(('Previsão Retorno', formulario.previsao_retorno.strftime('%d/%m/%Y') if (formulario and formulario.previsao_retorno) else ''))

		rows = []
		spanned_rows = []
		row_idx = 0
		for i in range(0, len(fields), 2):
			left_label, left_value = fields[i]
			if i + 1 < len(fields):
				right_label, right_value = fields[i+1]
				missing_right = False
			else:
				right_label, right_value = ('', '')
				missing_right = True
			rows.append([
				Paragraph(left_label, label_style), Paragraph(left_value, value_style),
				Paragraph(right_label, label_style), Paragraph(right_value, value_style)
			])
			if missing_right:
				spanned_rows.append(row_idx)
			row_idx += 1

		label_w = 30 * mm
		value_w = (doc.width - (label_w * 2)) / 2
		grid = Table(rows, colWidths=[label_w, value_w, label_w, value_w])
		grid_style = [
			('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
			('LEFTPADDING', (0,0), (-1,-1), 4),
			('RIGHTPADDING', (0,0), (-1,-1), 6),
			('TOPPADDING', (0,0), (-1,-1), 4),
			('BOTTOMPADDING', (0,0), (-1,-1), 6),
		]
		for r in spanned_rows:
			grid_style.append(('SPAN', (1, r), (3, r)))

		grid_style.extend([
			('GRID', (0,0), (-1,-1), 0.25, colors.HexColor('#eaeaea')),
			('BACKGROUND', (0,0), (0,-1), colors.HexColor('#f9f9f9')),
			('BACKGROUND', (2,0), (2,-1), colors.HexColor('#f9f9f9')),
		])
		for r in spanned_rows:
			grid_style.append(('BACKGROUND', (2, r), (2, r), colors.white))
			grid_style.append(('BACKGROUND', (3, r), (3, r), colors.white))
		grid.setStyle(TableStyle(grid_style))
		story.append(grid)
		story.append(Spacer(1, 6 * mm))

		photo_w = 70 * mm
		photo_h = 55 * mm
		fotos_qs = EquipamentoFoto.objects.filter(equipamento=equipamento).order_by('id')
		photo_objs = []
		for fobj in fotos_qs:
			try:
				fpath = fobj.foto.path if hasattr(fobj.foto, 'path') else None
				if fpath and os.path.exists(fpath):
					photo_objs.append((fpath, True))
				else:
					try:
						with default_storage.open(fobj.foto.name, 'rb') as fh:
							data = fh.read()
							photo_objs.append((data, False))
					except Exception:
						continue
			except Exception:
				continue

		if len(photo_objs) > 0:
			story.append(Spacer(1, 8 * mm))
			story.append(Paragraph('Registro fotográfico', ParagraphStyle('subhead', parent=styles['Heading2'], alignment=TA_LEFT, fontName='Helvetica-Bold', fontSize=13, spaceAfter=6)))
			img_cells = []
			row = []
			per_row = 3
			thumb_w = (doc.width - (per_row - 1) * (6 * mm)) / per_row
			thumb_w = min(thumb_w, 80 * mm)
			thumb_h = thumb_w * 0.66
			caption_style = ParagraphStyle('caption', parent=styles['Normal'], alignment=TA_CENTER, fontSize=8, textColor=colors.grey)
			for idx, (p, is_path) in enumerate(photo_objs):
				try:
					if is_path:
						ir = ImageReader(p)
						iw, ih = ir.getSize()
						ratio = ih / float(iw) if iw else 0.66
						h = thumb_w * ratio
						h = min(h, thumb_h)
						img_flow = Image(p, width=thumb_w, height=h)
					else:
						ir = ImageReader(BytesIO(p))
						iw, ih = ir.getSize()
						ratio = ih / float(iw) if iw else 0.66
						h = thumb_w * ratio
						h = min(h, thumb_h)
						img_flow = Image(BytesIO(p), width=thumb_w, height=h)
				except Exception:
					img_flow = Spacer(thumb_w, thumb_h)
				cell = Table([[img_flow],[Paragraph(f'Foto {idx+1}', caption_style)]], colWidths=[thumb_w])
				cell.setStyle(TableStyle([
					('ALIGN',(0,0),(-1,-1),'CENTER'),
					('VALIGN',(0,0),(-1,-1),'MIDDLE'),
					('LEFTPADDING',(0,0),(-1,-1),0), ('RIGHTPADDING',(0,0),(-1,-1),0), ('TOPPADDING',(0,0),(-1,-1),0), ('BOTTOMPADDING',(0,0),(-1,-1),2),
				]))
				row.append(cell)
				if (idx + 1) % per_row == 0:
					img_cells.append(row)
					row = []
			if row:
				while len(row) < per_row:
					row.append(Spacer(thumb_w, thumb_h))
				img_cells.append(row)
			photos_table = Table(img_cells, colWidths=[thumb_w] * per_row, hAlign='LEFT')
			photos_table.setStyle(TableStyle([
				('LEFTPADDING', (0, 0), (-1, -1), 0),
				('RIGHTPADDING', (0, 0), (-1, -1), 6),
				('BOTTOMPADDING', (0, 0), (-1, -1), 6),
				('VALIGN', (0, 0), (-1, -1), 'TOP'),
			]))
			story.append(photos_table)
		story.append(Spacer(1, 8 * mm))

		def on_page(canvas_obj, doc_obj):
			footer_text = f'Gerado por: {request.user.get_full_name() or request.user.username} — {request.user.email or ""} — {datetime.now().strftime("%d/%m/%Y %H:%M")}'
			canvas_obj.setFont('Helvetica-Oblique', 8)
			canvas_obj.setFillColor(colors.grey)
			canvas_obj.drawString(margin, 12 * mm, footer_text)
			canvas_obj.drawRightString(doc_obj.pagesize[0] - margin, 12 * mm, f'Página {canvas_obj.getPageNumber()}')

		doc.build(story, onFirstPage=on_page, onLaterPages=on_page)

		buf.seek(0)
		resp = HttpResponse(buf.read(), content_type='application/pdf')
		resp['Content-Disposition'] = f'attachment; filename="relatorio_equipamento_{equipamento.pk}.pdf"'
		return resp
	except Http404:
		raise
	except Exception as e:
		raise
 

@login_required
def relatorios_equipamentos_por_os_pdf(request, numero_os):
	try:
		equipamentos_qs = Equipamentos.objects.filter(numero_os=numero_os).order_by('id')
		equipamentos = list(equipamentos_qs)
		if not equipamentos:
			raise Http404('Nenhum equipamento encontrado para a OS informada')

		buf = BytesIO()
		margin = 18 * mm
		doc = SimpleDocTemplate(buf, pagesize=A4,
								leftMargin=margin, rightMargin=margin,
								topMargin=margin, bottomMargin=margin)

		styles = getSampleStyleSheet()
		title_style = ParagraphStyle('title', parent=styles['Heading1'], alignment=TA_CENTER, fontName='Helvetica-Bold', fontSize=16, leading=20, spaceAfter=6)
		subtitle_style = ParagraphStyle('subtitle', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=colors.grey, alignment=TA_CENTER, spaceAfter=8)
		label_style = ParagraphStyle('label', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, alignment=TA_LEFT)
		value_style = ParagraphStyle('value', parent=styles['Normal'], fontName='Helvetica', fontSize=9, alignment=TA_LEFT)

		story = []
		for idx, equipamento in enumerate(equipamentos):
			story.append(Paragraph('Relatórios da OS: %s' % str(numero_os), subtitle_style))
			story.append(Paragraph(f'Equipamento ID: {equipamento.pk} — {equipamento.descricao or ""}', title_style))
			story.append(Spacer(1, 4 * mm))

			formulario = Formulario_de_inspeção.objects.filter(equipamentos=equipamento).order_by('-id').first()

			def pdf_text(value):
				return '' if value is None else str(value)

			fields = []
			fields.append(('Descrição', equipamento.descricao or ''))
			fields.append(('Modelo', str(equipamento.modelo) if equipamento.modelo else ''))
			fields.append(('Fabricante', equipamento.fabricante or ''))
			fields.append(('Série', equipamento.numero_serie or ''))
			fields.append(('TAG', equipamento.numero_tag or ''))
			fields.append(('Cliente', equipamento.cliente or ''))
			fields.append(('Embarcação', equipamento.embarcacao or ''))
			fields.append(('Responsável', formulario.responsável if formulario else ''))
			fields.append(('Data Inspeção', formulario.data_inspecao_material.strftime('%d/%m/%Y') if (formulario and formulario.data_inspecao_material) else ''))
			fields.append(('Local', formulario.local_inspecao if formulario else ''))

			rows = []
			for i in range(0, len(fields), 2):
				left_label, left_value = fields[i]
				if i + 1 < len(fields):
					right_label, right_value = fields[i+1]
				else:
					right_label, right_value = ('', '')
				rows.append([
					Paragraph(pdf_text(left_label), label_style), Paragraph(pdf_text(left_value), value_style),
					Paragraph(pdf_text(right_label), label_style), Paragraph(pdf_text(right_value), value_style)
				])

			label_w = 30 * mm
			value_w = (doc.width - (label_w * 2)) / 2
			grid = Table(rows, colWidths=[label_w, value_w, label_w, value_w])
			grid.setStyle(TableStyle([
				('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
				('LEFTPADDING', (0,0), (-1,-1), 4), ('RIGHTPADDING', (0,0), (-1,-1), 6),
				('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 6),
				('GRID', (0,0), (-1,-1), 0.25, colors.HexColor('#f0f0f0')),
			]))
			story.append(grid)
			story.append(Spacer(1, 6 * mm))

			# incluir todas as fotos do equipamento (igual ao relatório individual)
			fotos_qs = EquipamentoFoto.objects.filter(equipamento=equipamento).order_by('id')
			photo_objs = []
			for fobj in fotos_qs:
				try:
					fpath = fobj.foto.path if hasattr(fobj.foto, 'path') else None
					if fpath and os.path.exists(fpath):
						photo_objs.append((fpath, True))
					else:
						try:
							with default_storage.open(fobj.foto.name, 'rb') as fh:
								data = fh.read()
								photo_objs.append((data, False))
						except Exception:
							continue
				except Exception:
					continue

			if len(photo_objs) > 0:
				story.append(Spacer(1, 4 * mm))
				story.append(Paragraph('Registro fotográfico', ParagraphStyle('subhead_os', parent=styles['Heading2'], alignment=TA_LEFT, fontName='Helvetica-Bold', fontSize=12, spaceAfter=5)))
				img_cells = []
				row = []
				per_row = 3
				thumb_w = (doc.width - (per_row - 1) * (6 * mm)) / per_row
				thumb_w = min(thumb_w, 72 * mm)
				thumb_h = thumb_w * 0.66
				caption_style = ParagraphStyle('caption_os', parent=styles['Normal'], alignment=TA_CENTER, fontSize=8, textColor=colors.grey)

				for photo_idx, (p, is_path) in enumerate(photo_objs):
					try:
						if is_path:
							ir = ImageReader(p)
							iw, ih = ir.getSize()
							ratio = ih / float(iw) if iw else 0.66
							h = min(thumb_w * ratio, thumb_h)
							img_flow = Image(p, width=thumb_w, height=h)
						else:
							ir = ImageReader(BytesIO(p))
							iw, ih = ir.getSize()
							ratio = ih / float(iw) if iw else 0.66
							h = min(thumb_w * ratio, thumb_h)
							img_flow = Image(BytesIO(p), width=thumb_w, height=h)
					except Exception:
						img_flow = Spacer(thumb_w, thumb_h)

					cell = Table([[img_flow], [Paragraph(f'Foto {photo_idx + 1}', caption_style)]], colWidths=[thumb_w])
					cell.setStyle(TableStyle([
						('ALIGN', (0, 0), (-1, -1), 'CENTER'),
						('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
						('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
						('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
					]))
					row.append(cell)

					if (photo_idx + 1) % per_row == 0:
						img_cells.append(row)
						row = []

				if row:
					while len(row) < per_row:
						row.append(Spacer(thumb_w, thumb_h))
					img_cells.append(row)

				photos_table = Table(img_cells, colWidths=[thumb_w] * per_row, hAlign='LEFT')
				photos_table.setStyle(TableStyle([
					('LEFTPADDING', (0, 0), (-1, -1), 0),
					('RIGHTPADDING', (0, 0), (-1, -1), 6),
					('BOTTOMPADDING', (0, 0), (-1, -1), 6),
					('VALIGN', (0, 0), (-1, -1), 'TOP'),
				]))
				story.append(photos_table)
				story.append(Spacer(1, 4 * mm))

			if idx < len(equipamentos) - 1:
				story.append(PageBreak())

		def on_page(canvas_obj, doc_obj):
			footer_text = f'Gerado por: {request.user.get_full_name() or request.user.username} — {datetime.now().strftime("%d/%m/%Y %H:%M")}'
			canvas_obj.setFont('Helvetica-Oblique', 8)
			canvas_obj.setFillColor(colors.grey)
			canvas_obj.drawString(margin, 12 * mm, footer_text)
			canvas_obj.drawRightString(doc_obj.pagesize[0] - margin, 12 * mm, f'Página {canvas_obj.getPageNumber()}')

		doc.build(story, onFirstPage=on_page, onLaterPages=on_page)

		buf.seek(0)
		resp = HttpResponse(buf.read(), content_type='application/pdf')
		resp['Content-Disposition'] = f'attachment; filename="relatorios_os_{numero_os}.pdf"'
		return resp
	except Http404:
		raise
	except Exception as e:
		raise

@login_required
def get_equipamento_ajax(request, pk=None):
	try:
		equipamento = None
		if pk is None:
			qid = request.GET.get('id')
			tag_q = (request.GET.get('tag') or '').strip().upper()
			serie_q = (request.GET.get('serie') or '').strip().upper()

			if qid:
				try:
					pk = int(qid)
				except Exception:
					return JsonResponse({'success': False, 'error': 'invalid id'}, status=400)
				equipamento = Equipamentos.objects.filter(pk=pk).first()
			elif tag_q:
				equipamento = Equipamentos.objects.filter(numero_tag__iexact=tag_q).order_by('-id').first()
			elif serie_q:
				equipamento = Equipamentos.objects.filter(numero_serie__iexact=serie_q).order_by('-id').first()
			else:
				return JsonResponse({'success': False, 'error': 'id/tag/serie not provided'}, status=400)
		else:
			equipamento = Equipamentos.objects.filter(pk=pk).first()
		if not equipamento:
			return JsonResponse({'success': False, 'error': 'Equipamento not found'}, status=404)

		formulario = Formulario_de_inspeção.objects.filter(equipamentos=equipamento).order_by('-id').first()

		photo_urls = []
		fotos_qs = EquipamentoFoto.objects.filter(equipamento=equipamento).order_by('id')
		for fobj in fotos_qs:
			try:
				photo_urls.append(fobj.foto.url)
			except Exception:
				try:
					photo_urls.append(default_storage.url(fobj.foto.name))
				except Exception:
					photo_urls.append(getattr(fobj.foto, 'name', ''))

		result = {
			'success': True,
			'equipamento': {
				'id': equipamento.pk,
				'situacao': equipamento.situacao or '',
				'modelo': str(equipamento.modelo_fk or equipamento.modelo) if (equipamento.modelo_fk or equipamento.modelo) else '',
				'fabricante': equipamento.fabricante or '',
				'descricao': equipamento.descricao or '',
				'numero_serie': equipamento.numero_serie or '',
				'numero_tag': equipamento.numero_tag or '',
				'cliente': equipamento.cliente or '',
				'embarcacao': equipamento.embarcacao or '',
				'numero_os': equipamento.numero_os or '',
			},
			'formulario': {
				'id': formulario.pk if formulario else None,
				'responsavel': formulario.responsável if formulario else '',
				'data_inspecao': formulario.data_inspecao_material.isoformat() if (formulario and formulario.data_inspecao_material) else '',
				'local_inspecao': formulario.local_inspecao if formulario else '',
				'previsao_retorno': formulario.previsao_retorno.isoformat() if (formulario and formulario.previsao_retorno) else '',
				'photo_urls': photo_urls,
			}
		}

		# attach recent situacao log entries for history
		try:
			result['situacao_history'] = []
			logs = EquipamentoSituacaoLog.objects.filter(equipamento=equipamento).order_by('-created_at')[:20]
			for l in logs:
				result['situacao_history'].append({
					'previous': l.previous,
					'current': l.current,
					'changed_by': (l.changed_by.get_full_name() if (l.changed_by and hasattr(l.changed_by, 'get_full_name')) else (l.changed_by.username if l.changed_by else None)),
					'created_at': l.created_at.isoformat(),
					'note': l.note,
				})
		except Exception:
			pass

		# attach identifier logs for full TAG/Série traceability
		try:
			result['identifier_history'] = _serialize_identifier_history(equipamento, limit=30)
		except Exception:
			pass
		return JsonResponse(result)
	except Exception as e:
		return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def list_equipamentos_choices_ajax(request):
	try:
		q = (request.GET.get('q') or '').strip()
		limit_raw = request.GET.get('limit')
		try:
			limit = int(limit_raw) if limit_raw else 200
		except Exception:
			limit = 200
		limit = max(20, min(limit, 1000))

		qs = Equipamentos.objects.all().order_by('-id')
		if q:
			q_u = q.upper()
			qs = qs.filter(
				Q(numero_tag__icontains=q_u) |
				Q(numero_serie__icontains=q_u) |
				Q(descricao__icontains=q)
			)

		items = []
		seen_keys = set()
		for e in qs:
			tag_n = _normalize_identifier(getattr(e, 'numero_tag', None)) or ''
			serie_n = _normalize_identifier(getattr(e, 'numero_serie', None)) or ''
			# Show one option per logical equipment identifier pair.
			# If both identifiers are empty, fallback to row id key.
			key = (tag_n, serie_n) if (tag_n or serie_n) else (f"id:{e.pk}", '')
			if key in seen_keys:
				continue
			seen_keys.add(key)

			items.append({
				'id': e.pk,
				'label': _build_equipamento_choice_label(e),
				'tag': e.numero_tag or '',
				'serie': e.numero_serie or '',
				'descricao': e.descricao or '',
			})
			if len(items) >= limit:
				break

		return JsonResponse({'success': True, 'items': items})
	except Exception as e:
		return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def swap_identificadores_ajax(request):
	if user_has_read_only_access(getattr(request, 'user', None)):
		return build_read_only_json_response('alterar identificadores de equipamentos')

	try:
		equipamento_id = request.POST.get('equipamento_id') or request.POST.get('id')
		if not equipamento_id:
			return JsonResponse({'success': False, 'error': 'Equipamento não informado.'}, status=400)

		try:
			equipamento = Equipamentos.objects.filter(pk=int(equipamento_id)).first()
		except Exception:
			equipamento = None
		if not equipamento:
			return JsonResponse({'success': False, 'error': 'Equipamento não encontrado.'}, status=404)

		new_tag = _normalize_identifier(request.POST.get('tag'))
		new_serie = _normalize_identifier(request.POST.get('serie'))
		note = (request.POST.get('motivo') or request.POST.get('identificador_motivo') or '').strip() or None
		identifier_terms = _identifier_terms_for_descricao(equipamento.descricao)

		if not new_tag and not new_serie:
			return JsonResponse({'success': False, 'error': f'Informe {identifier_terms["pair"]}.'}, status=400)

		old_tag = _normalize_identifier(equipamento.numero_tag)
		old_serie = _normalize_identifier(equipamento.numero_serie)

		if old_tag == new_tag and old_serie == new_serie:
			return JsonResponse({
				'success': True,
				'message': identifier_terms['unchanged_message'],
				'equipamento': {
					'id': equipamento.pk,
					'numero_tag': equipamento.numero_tag or '',
					'numero_serie': equipamento.numero_serie or '',
				},
				'identifier_history': _serialize_identifier_history(equipamento, limit=30),
			})

		related_ids = {equipamento.pk}

		if old_tag:
			for eq_id in Equipamentos.objects.filter(numero_tag__iexact=old_tag).values_list('pk', flat=True):
				related_ids.add(eq_id)
			for eq_id in EquipamentoIdentificadorLog.objects.filter(
				Q(identifier_type=EquipamentoIdentificadorLog.TIPO_TAG),
				Q(previous_value__iexact=old_tag) | Q(current_value__iexact=old_tag),
			).values_list('equipamento_id', flat=True):
				related_ids.add(eq_id)

		if old_serie:
			for eq_id in Equipamentos.objects.filter(numero_serie__iexact=old_serie).values_list('pk', flat=True):
				related_ids.add(eq_id)
			for eq_id in EquipamentoIdentificadorLog.objects.filter(
				Q(identifier_type=EquipamentoIdentificadorLog.TIPO_SERIE),
				Q(previous_value__iexact=old_serie) | Q(current_value__iexact=old_serie),
			).values_list('equipamento_id', flat=True):
				related_ids.add(eq_id)

		related_equipamentos = list(Equipamentos.objects.filter(pk__in=related_ids).order_by('id'))

		exclude_ids = [e.pk for e in related_equipamentos]
		if new_tag:
			dup_tag = Equipamentos.objects.filter(numero_tag__iexact=new_tag).exclude(pk__in=exclude_ids)
			if dup_tag.exists():
				return JsonResponse({'success': False, 'error': f'{identifier_terms["tag"]} já cadastrado: {new_tag}.'}, status=400)
		if new_serie:
			dup_serie = Equipamentos.objects.filter(numero_serie__iexact=new_serie).exclude(pk__in=exclude_ids)
			if dup_serie.exists():
				return JsonResponse({'success': False, 'error': f'{identifier_terms["serie"]} já cadastrado: {new_serie}.'}, status=400)

		try:
			with transaction.atomic():
				for eq in related_equipamentos:
					eq_old_tag = _normalize_identifier(eq.numero_tag)
					eq_old_serie = _normalize_identifier(eq.numero_serie)
					changed = False

					if eq_old_tag != new_tag:
						eq.numero_tag = new_tag
						changed = True
					if eq_old_serie != new_serie:
						eq.numero_serie = new_serie
						changed = True

					if not changed:
						continue

					eq.save()

					if eq_old_tag != new_tag:
						log = EquipamentoIdentificadorLog(
							equipamento=eq,
							identifier_type=EquipamentoIdentificadorLog.TIPO_TAG,
							previous_value=eq_old_tag,
							current_value=new_tag,
							note=note,
						)
						try:
							log.changed_by = request.user
						except Exception:
							pass
						log.save()

					if eq_old_serie != new_serie:
						log = EquipamentoIdentificadorLog(
							equipamento=eq,
							identifier_type=EquipamentoIdentificadorLog.TIPO_SERIE,
							previous_value=eq_old_serie,
							current_value=new_serie,
							note=note,
						)
						try:
							log.changed_by = request.user
						except Exception:
							pass
						log.save()
		except IntegrityError:
			return JsonResponse({'success': False, 'error': f'{identifier_terms["pair"]} já está em uso por outro equipamento.'}, status=400)

		return JsonResponse({
			'success': True,
			'message': identifier_terms['updated_message'],
			'equipamento': {
				'id': equipamento.pk,
				'numero_tag': new_tag or '',
				'numero_serie': new_serie or '',
			},
			'updated_equipamento_ids': [e.pk for e in related_equipamentos],
			'identifier_history': _serialize_identifier_history(equipamento, limit=30),
		})
	except Exception as e:
		return JsonResponse({'success': False, 'error': str(e)}, status=500)
