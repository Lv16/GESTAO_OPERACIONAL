from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.utils.dateparse import parse_date
from django.core.files.storage import default_storage
import os

from .models import Equipamentos, Modelo, Formulario_de_inspeção, EquipamentoFoto
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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Image, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from datetime import datetime
import uuid

@login_required
@require_POST
def save_equipamento_ajax(request):
	try:
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
		equipamento = None
		if equipamento_id:
			try:
				equipamento = Equipamentos.objects.filter(pk=int(equipamento_id)).first()
			except Exception:
				equipamento = None

		if equipamento:
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
			try:
				original_name = os.path.basename(getattr(f, 'name', 'upload'))
				unique_prefix = uuid.uuid4().hex[:8]
				target_name = os.path.join('fotos_equipamento', f"{unique_prefix}_{original_name}")
				ef = EquipamentoFoto(equipamento=equipamento)
				ef.foto.save(target_name, f)
				ef.save()
				try:
					photo_urls.append(ef.foto.url)
					try:
						saved_photo_basenames.add(os.path.basename(getattr(ef.foto, 'name', '') or ''))
					except Exception:
						pass
				except Exception:
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
				continue

		try:
			if equipamento and existing_photo_basenames is not None:
				kept_basenames = set(existing_photo_basenames or ()) | set(saved_photo_basenames or ())
				qs = EquipamentoFoto.objects.filter(equipamento=equipamento).order_by('id')
				for old in qs:
					try:
						old_basename = os.path.basename(getattr(old.foto, 'name', '') or '')
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
						continue
		except Exception:
			pass

		result = {
			'success': True,
			'equipamento': {
				'id': equipamento.pk,
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
def get_equipamento_ajax(request, pk=None):
	try:
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