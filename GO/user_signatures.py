import io
import os

from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from PIL import Image, ImageChops, ImageOps, UnidentifiedImageError


ALLOWED_SIGNATURE_EXTENSIONS = {'.jpg', '.jpeg', '.jfif', '.png', '.webp', '.pdf'}
MAX_SIGNATURE_FILE_SIZE = 15 * 1024 * 1024


def _crop_signature(image):
    image = ImageOps.exif_transpose(image).convert('RGBA')
    white = Image.new('RGBA', image.size, (255, 255, 255, 255))
    flattened = Image.alpha_composite(white, image).convert('RGB')
    grayscale = ImageOps.grayscale(flattened)
    ink_mask = grayscale.point(lambda value: 255 if value < 245 else 0)
    bbox = ink_mask.getbbox()
    if not bbox:
        raise ValidationError('O arquivo não contém uma assinatura visível.')
    margin = max(4, int(min(image.size) * 0.015))
    left, top, right, bottom = bbox
    bbox = (
        max(0, left - margin),
        max(0, top - margin),
        min(image.width, right + margin),
        min(image.height, bottom + margin),
    )
    return _make_white_background_transparent(flattened.crop(bbox))


def _make_white_background_transparent(image):
    rgba = image.convert('RGBA')
    grayscale = ImageOps.grayscale(rgba)
    alpha = grayscale.point(
        lambda value: 0 if value >= 250 else min(255, (255 - value) * 3)
    )
    rgba.putalpha(alpha)
    return rgba


def transparent_signature_png(contents):
    """Normaliza também imagens antigas que ainda tenham fundo branco."""
    image = Image.open(io.BytesIO(contents))
    transparent = _make_white_background_transparent(image)
    output = io.BytesIO()
    transparent.save(output, format='PNG', optimize=True)
    return output.getvalue()


def _image_from_pdf(contents):
    try:
        import fitz
    except ImportError as exc:
        raise ValidationError('O servidor não está preparado para processar assinaturas em PDF.') from exc

    try:
        document = fitz.open(stream=contents, filetype='pdf')
        if document.page_count < 1:
            raise ValidationError('O PDF enviado não possui páginas.')
        page = document.load_page(0)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        return Image.open(io.BytesIO(pixmap.tobytes('png'))).copy()
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError('Não foi possível ler o PDF enviado.') from exc


def prepare_signature_upload(uploaded_file):
    filename = uploaded_file.name or ''
    extension = os.path.splitext(filename)[1].lower()
    if extension not in ALLOWED_SIGNATURE_EXTENSIONS:
        raise ValidationError('Envie a assinatura em PDF, JPG, JPEG, JFIF, PNG ou WebP.')
    if uploaded_file.size > MAX_SIGNATURE_FILE_SIZE:
        raise ValidationError('A assinatura deve ter no máximo 15 MB.')

    contents = uploaded_file.read()
    if not contents:
        raise ValidationError('O arquivo enviado está vazio.')
    try:
        if extension == '.pdf':
            image = _image_from_pdf(contents)
        else:
            image = Image.open(io.BytesIO(contents))
            image.verify()
            image = Image.open(io.BytesIO(contents))
        image = _crop_signature(image)
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError('Não foi possível ler a imagem enviada.') from exc

    output = io.BytesIO()
    image.save(output, format='PNG', optimize=True)
    return ContentFile(contents, name=filename), ContentFile(output.getvalue(), name='assinatura.png')
