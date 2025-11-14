
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.utils.dateparse import parse_date
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import os

from .models import Equipamentos, Modelo, Formulario_de_inspeção, EquipamentoFoto
from django.http import HttpResponse, Http404
from django.conf import settings
from django.contrib.staticfiles import finders
from io import BytesIO
import hashlib
import PIL.Image

# Aplicar shim de compatibilidade para hashlib.openssl_md5 antes de carregar reportlab
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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Image, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from datetime import datetime
import uuid


@login_required
@require_POST
def save_equipamento_ajax(request):
	"""Recebe o formulário do modal (FormData), cria/atualiza Equipamentos e Formulario_de_inspecao.
	Aceita múltiplas fotos (qualquer quantidade) — procura por chaves comuns
	como 'photos', 'fotos' ou 'fotos[]' no FormData e salva cada arquivo recebido.
	Retorna JSON com sucesso e os URLs das fotos salvas.
	"""
	try:
		# campos do modal
		cliente = request.POST.get('cliente', '').strip()
		embarcacao = request.POST.get('embarcacao', '').strip()
		responsavel = request.POST.get('responsavel', '').strip()
		numero_os = request.POST.get('numero_os', '').strip()
		data_inspecao_raw = request.POST.get('data_inspecao', '').strip()
		local = request.POST.get('local', '').strip()
		previsao_retorno_raw = request.POST.get('previsao_retorno', '').strip()

		modelo_name = request.POST.get('modelo', '').strip()
		serie = request.POST.get('serie', '').strip()
		tag = request.POST.get('tag', '').strip()
		fabricante = request.POST.get('fabricante', '').strip()
		descricao = request.POST.get('descricao', '').strip()

		# parse dates (expectando YYYY-MM-DD)
		data_inspecao = parse_date(data_inspecao_raw) if data_inspecao_raw else None
		previsao_retorno = parse_date(previsao_retorno_raw) if previsao_retorno_raw else None

		# localizar ou criar modelo
		modelo_obj = None
		if modelo_name:
			modelo_obj = Modelo.objects.filter(nome__iexact=modelo_name).first()
			# se não existir, não criamos automaticamente aqui — preferimos criar explicitamente
			# via admin ou através de um fluxo separado; no entanto, podemos criar se necessário:
			if modelo_obj is None:
				try:
					modelo_obj = Modelo.objects.create(nome=modelo_name)
				except Exception:
					modelo_obj = None

		# se foi enviado equipamento_id, tentar atualizar esse registro em vez de criar novo
		equipamento_id = request.POST.get('equipamento_id') or request.POST.get('id')
		equipamento = None
		if equipamento_id:
			try:
				equipamento = Equipamentos.objects.filter(pk=int(equipamento_id)).first()
			except Exception:
				equipamento = None

		if equipamento:
			# atualizar campos do equipamento existente
			if modelo_obj is not None:
				equipamento.modelo = modelo_obj
				try:
					equipamento.modelo_fk = modelo_obj
				except Exception:
					pass
			equipamento.fabricante = fabricante or equipamento.fabricante
			equipamento.descricao = descricao or equipamento.descricao
			equipamento.numero_serie = serie or equipamento.numero_serie
			equipamento.numero_tag = tag or equipamento.numero_tag
			equipamento.cliente = cliente or equipamento.cliente
			equipamento.embarcacao = embarcacao or equipamento.embarcacao
			equipamento.numero_os = numero_os or equipamento.numero_os
			equipamento.save()
		else:
			# criar equipamento (preencher também campos operacionais para exibição na tabela)
			equipamento = Equipamentos.objects.create(
				modelo=modelo_obj,
				modelo_fk=modelo_obj,
				fabricante=fabricante or None,
				descricao=descricao or None,
				numero_serie=serie or None,
				numero_tag=tag or None,
				cliente=cliente or None,
				embarcacao=embarcacao or None,
				numero_os=numero_os or None,
			)

		# criar ou atualizar formulário de inspeção vinculado ao equipamento
		# preferir atualizar o último formulário existente para este equipamento (comportamento de edição)
		formulario = None
		last_form = Formulario_de_inspeção.objects.filter(equipamentos=equipamento).order_by('-id').first()
		if last_form:
			# atualizar os campos do último formulário
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

		# lidar com fotos: criar um EquipamentoFoto para cada arquivo enviado
		photo_urls = []
		# track basenames of photos saved in this request so we don't delete them immediately
		saved_photo_basenames = set()
		photos = []
		# interpretar lista de URLs remotas que o cliente declara como 'mantidas'
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
				# não conseguir parsear -> tratar como None (não deletar)
				existing_photo_basenames = None
		if hasattr(request, 'FILES'):
			# Prefer common keys, preserving order if present
			for key in ('photos', 'fotos', 'fotos[]'):
				if key in request.FILES:
					photos.extend(request.FILES.getlist(key))
			# fallback: append any files present in request.FILES
			if not photos:
				for key in request.FILES:
					photos.extend(request.FILES.getlist(key))
		# simple dedupe by (name, size) to avoid accidental duplicates appended twice
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
			try:
				# sanitize original filename and prepend a short uuid to avoid collisions
				original_name = os.path.basename(getattr(f, 'name', 'upload'))
				unique_prefix = uuid.uuid4().hex[:8]
				target_name = os.path.join('fotos_equipamento', f"{unique_prefix}_{original_name}")
				ef = EquipamentoFoto(equipamento=equipamento)
				# Use FileField.save with the uploaded file object so storage backends
				# can manage naming and streaming efficiently.
				ef.foto.save(target_name, f)
				ef.save()
				try:
					# prefer the public URL
					photo_urls.append(ef.foto.url)
					# record basename so deletion pass won't remove this newly saved file
					try:
						saved_photo_basenames.add(os.path.basename(getattr(ef.foto, 'name', '') or ''))
					except Exception:
						pass
				except Exception:
					# fallback to storage url or raw name
					try:
						photo_urls.append(default_storage.url(ef.foto.name))
						try:
							saved_photo_basenames.add(os.path.basename(getattr(ef.foto, 'name', '') or ''))
						except Exception:
							pass
					except Exception:
						photo_urls.append(ef.foto.name)
						try:
							saved_photo_basenames.add(os.path.basename(str(ef.foto.name) or ''))
						except Exception:
							pass
			except Exception:
				# if one photo fails to save, continue with others
				continue

		# Se o cliente informou explicitamente quais fotos manteve, remover as demais
		try:
			if equipamento and existing_photo_basenames is not None:
				# fotos mantidas = as que o cliente declarou + as que salvamos agora nesta requisição
				kept_basenames = set(existing_photo_basenames or ()) | set(saved_photo_basenames or ())
				qs = EquipamentoFoto.objects.filter(equipamento=equipamento).order_by('id')
				for old in qs:
					try:
						old_basename = os.path.basename(getattr(old.foto, 'name', '') or '')
						# se o arquivo existe e o cliente não o listou como mantido, apagar
						if old_basename and (old_basename not in kept_basenames):
							try:
								old.foto.delete(save=False)
							except Exception:
								pass
							try:
								old.delete()
							except Exception:
								pass
					except Exception:
						# continuar se falhar ao processar este registro
						continue
		except Exception:
			# ignorar erros de exclusão para não bloquear o fluxo principal
			pass

		# responder com payload mínimo necessário para atualizar a tabela
		result = {
			'success': True,
			'equipamento': {
				'id': equipamento.pk,
				# preferir modelo_fk quando presente (transição gradual)
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
		}
		return JsonResponse(result)

	except Exception as e:
		return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def relatorio_equipamento_pdf(request, pk):
	"""Gera um PDF compacto com as informações do equipamento, incluindo logo e a primeira foto disponível.
	Layout:
	- Logo da empresa no topo à esquerda
	- Título/ID central
	- Coluna com foto à direita (se houver)
	- Lista compacta de campos (descrição, modelo, fabricante, série, tag, cliente, embarcação, nº OS, data inspeção, local, previsão)
	"""
	try:
		# Compat shim: algumas builds/travas de OpenSSL expõem
		# hashlib.openssl_md5 que não aceita o kwarg `usedforsecurity`.
		# ReportLab pode chamar md5(usedforsecurity=False) em alguns ambientes;
		# aqui garantimos que a chamada não quebre substituindo a função por um wrapper
		# que aceita kwargs extras e as ignora.
		openssl_md5 = getattr(hashlib, 'openssl_md5', None)
		if openssl_md5 is not None:
			def _openssl_md5_compat(data=b'', *args, **kwargs):
				try:
					return openssl_md5(data)
				except TypeError:
					# última tentativa: invocar sem argumentos e depois atualizar com data
					return openssl_md5()
			hashlib.openssl_md5 = _openssl_md5_compat

		equipamento = Equipamentos.objects.filter(pk=pk).first()
		if not equipamento:
			raise Http404("Equipamento não encontrado")

		# Buscar último formulário de inspeção relacionado
		formulario = Formulario_de_inspeção.objects.filter(equipamentos=equipamento).order_by('-id').first()

		# buscar foto principal (se houver)
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

		# Logo: usar preferencialmente o logo já presente no template
		logo_path = None
		try:
			candidate = finders.find('img/Logo_Preto.png') or finders.find('img/logo_home.png') or finders.find('img/logo_home.jpg') or finders.find('logo_home.png')
		except Exception:
			candidate = None
		if not candidate and getattr(settings, 'STATIC_ROOT', None):
			p1 = os.path.join(settings.STATIC_ROOT, 'img', 'Logo_Preto.png')
			p2 = os.path.join(settings.STATIC_ROOT, 'img', 'logo_home.png')
			if os.path.exists(p1):
				candidate = p1
			elif os.path.exists(p2):
				candidate = p2

		if candidate:
			logo_path = candidate

		if logo_path:
			try:
				img_logo = Image(logo_path)
				# ampliar um pouco a logo para ficar proporcional ao layout
				img_logo.drawHeight = 34 * mm
				img_logo.drawWidth = img_logo.drawHeight * (img_logo.imageWidth / img_logo.imageHeight)
			except Exception:
				img_logo = None
		else:
			img_logo = None

		# Logo centered above title
		if img_logo:
			# Make logo smaller and place it in the top-left corner of the header
			try:
				# resize logo to be visually smaller (approx. 18mm height)
				img_logo.drawHeight = 18 * mm
				img_logo.drawWidth = img_logo.drawHeight * (img_logo.imageWidth / img_logo.imageHeight)
			except Exception:
				pass
			# build a header table with a narrow left column for the logo and
			# the title centered in the remaining space. Force the row height
			# to match the logo height (plus small padding) so the title will
			# be vertically centered next to the logo.
			header_data = []
			logo_cell = img_logo
			# combine title + subtitle as separate flowables in a single cell
			title_cell = [Paragraph('Relatório do Equipamento', title_style), Paragraph(f'Equipamento ID: {equipamento.pk} — Gerado em {datetime.now().strftime("%d/%m/%Y %H:%M")}', subtitle_style)]
			header_data.append([logo_cell, title_cell])
			# narrow logo column to keep logo in top-left corner and set row height
			row_h = (getattr(img_logo, 'drawHeight', 18 * mm) + (4 * mm))
			header_table = Table(header_data, colWidths=[20 * mm, doc.width - (20 * mm)], rowHeights=[row_h])
			header_table.setStyle(TableStyle([
				('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
				('LEFTPADDING',(0,0),(-1,-1),0), ('RIGHTPADDING',(0,0),(-1,-1),0),
				('ALIGN', (0,0), (0,0), 'LEFT'),
				('ALIGN', (1,0), (1,0), 'CENTER'),
				# ensure the title cell contents are vertically centered
				('VALIGN', (1,0), (1,0), 'MIDDLE'),
			]))
			story.append(header_table)
			# thin horizontal rule to separate header from body
			hr = Table([[" "]], colWidths=[doc.width])
			hr.setStyle(TableStyle([
				('LINEBELOW', (0,0), (-1,-1), 0.7, colors.HexColor('#e0e0e0')),
				('LEFTPADDING',(0,0),(-1,-1),0), ('RIGHTPADDING',(0,0),(-1,-1),0), ('TOPPADDING',(0,0),(-1,-1),0), ('BOTTOMPADDING',(0,0),(-1,-1),0),
			]))
			story.append(hr)
			story.append(Spacer(1, 5 * mm))


		# Section title
		section_title_style = ParagraphStyle('section', parent=styles['Heading2'], alignment=TA_LEFT, fontName='Helvetica-Bold', fontSize=14, spaceAfter=6)
		story.append(Paragraph('Dados do Equipamento', section_title_style))

		# Build fields list
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

		# Build a two-column grid: [label, value, label, value]
		rows = []
		spanned_rows = []  # keep index of rows where there is no right-hand pair
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

		# Column widths: labels narrow, values wider
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
		# If an odd number of fields, span the left value across remaining columns on the last row
		for r in spanned_rows:
			grid_style.append(('SPAN', (1, r), (3, r)))

		# Then apply borders and label backgrounds
		grid_style.extend([
			('GRID', (0,0), (-1,-1), 0.25, colors.HexColor('#eaeaea')),
			('BACKGROUND', (0,0), (0,-1), colors.HexColor('#f9f9f9')),
			('BACKGROUND', (2,0), (2,-1), colors.HexColor('#f9f9f9')),
		])
		# Clear label background on column 2 for any spanned row (cosmetic)
		for r in spanned_rows:
			grid_style.append(('BACKGROUND', (2, r), (2, r), colors.white))
			grid_style.append(('BACKGROUND', (3, r), (3, r), colors.white))
		grid.setStyle(TableStyle(grid_style))
		story.append(grid)
		story.append(Spacer(1, 6 * mm))

		# Photo (right column) - parameters reused for grid below
		photo_w = 70 * mm
		photo_h = 55 * mm
		# gather all photos for registro fotografico
		fotos_qs = EquipamentoFoto.objects.filter(equipamento=equipamento).order_by('id')
		photo_objs = []
		for fobj in fotos_qs:
			try:
				fpath = fobj.foto.path if hasattr(fobj.foto, 'path') else None
				if fpath and os.path.exists(fpath):
					photo_objs.append((fpath, True))
				else:
					# try to read from storage into bytes
					try:
						with default_storage.open(fobj.foto.name, 'rb') as fh:
							data = fh.read()
							photo_objs.append((data, False))
					except Exception:
						# skip if cannot read
						continue
			except Exception:
				continue

		# The main grid above already added

		# Registro fotográfico: show all photos in a grid beneath

		if len(photo_objs) > 0:
			story.append(Spacer(1, 8 * mm))
			story.append(Paragraph('Registro fotográfico', ParagraphStyle('subhead', parent=styles['Heading2'], alignment=TA_LEFT, fontName='Helvetica-Bold', fontSize=13, spaceAfter=6)))
			# build image cells (3 columns) with better proportional thumbs
			img_cells = []
			row = []
			per_row = 3
			# calculate thumb size based on available width, keep aspect ratio
			thumb_w = (doc.width - (per_row - 1) * (6 * mm)) / per_row
			thumb_w = min(thumb_w, 80 * mm)
			thumb_h = thumb_w * 0.66
			caption_style = ParagraphStyle('caption', parent=styles['Normal'], alignment=TA_CENTER, fontSize=8, textColor=colors.grey)
			for idx, (p, is_path) in enumerate(photo_objs):
				try:
					if is_path:
						# use ImageReader to preserve aspect when only width given
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
				# wrap image + caption in a small inner table for centered layout
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
				# fill remaining cols with spacers
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

		# Footer will be drawn using onPage
		def on_page(canvas_obj, doc_obj):
			footer_text = f'Gerado por: {request.user.get_full_name() or request.user.username} — {request.user.email or ""} — {datetime.now().strftime("%d/%m/%Y %H:%M")}'
			canvas_obj.setFont('Helvetica-Oblique', 8)
			canvas_obj.setFillColor(colors.grey)
			canvas_obj.drawString(margin, 12 * mm, footer_text)
			# page number
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
def get_equipamento_ajax(request, pk=None):
	"""Retorna JSON com dados do equipamento, último formulário e URLs de fotos.
	Suporta chamadas em três formatos para compatibilidade com o frontend antigo:
	- GET /api/equipamentos/<pk>/
	- GET /api/equipamentos/<pk>/json/
	- GET /api/equipamentos/get/?id=<pk>
	"""
	try:
		# permitir id via query param 'id' para /api/equipamentos/get/?id=2
		if pk is None:
			qid = request.GET.get('id')
			if not qid:
				return JsonResponse({'success': False, 'error': 'id not provided'}, status=400)
			try:
				pk = int(qid)
			except Exception:
				return JsonResponse({'success': False, 'error': 'invalid id'}, status=400)
		equipamento = Equipamentos.objects.filter(pk=pk).first()
		if not equipamento:
			return JsonResponse({'success': False, 'error': 'Equipamento not found'}, status=404)

		formulario = Formulario_de_inspeção.objects.filter(equipamentos=equipamento).order_by('-id').first()

		# coletar URLs das fotos
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
		return JsonResponse(result)
	except Exception as e:
		return JsonResponse({'success': False, 'error': str(e)}, status=500)
