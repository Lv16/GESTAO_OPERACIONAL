from django.views.decorators.http import require_POST, require_GET
from django.http import JsonResponse, Http404, HttpResponse
from django.conf import settings
import os
import glob
import traceback
from datetime import datetime, timedelta, time as dt_time
from decimal import Decimal, ROUND_HALF_UP
import json
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
import unicodedata
from .models import OrdemServico, RDO, RDOAtividade, Pessoa, Funcao, RDOMembroEquipe, RdoTanque
import logging
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import transaction, connections, close_old_connections
from django.db.models import Max, Q, Sum
from django.utils.safestring import mark_safe
import json as _json
from urllib.parse import urlparse
from django.template.loader import render_to_string
def _get_rdo_inline_css():
    """Retorna CSS inline encapsulado em <style>, pronto para injetar no template."""
    try:
        css = render_to_string('css/page_rdo.inline.css')
        css = css.strip()
        if not css:
            return ''
        return f'<style type="text/css">{css}</style>'
    except Exception:
        return ''


def _canonicalize_sentido(raw):
    """Normalize various legacy representations (bools, numbers, labels, short tokens)
    into the canonical token strings used by the model.

    Returns one of:
      - 'vante > ré'
      - 'ré > vante'
      - 'bombordo > boreste'
      - 'boreste < bombordo'
    or None when unknown.
    """
    try:
        if raw is None:
            return None
        # Direct boolean
        if isinstance(raw, bool):
            return 'vante > ré' if raw else 'ré > vante'
        # Numbers
        try:
            if isinstance(raw, (int, float)):
                if int(raw) == 1:
                    return 'vante > ré'
                if int(raw) == 0:
                    return 'ré > vante'
        except Exception:
            pass
        s = str(raw).strip()
        if not s:
            return None
        low = s.lower()
        # exact canonical matches (allow minor variants without accents)
        variants = {
            'vante > ré': ['vante > ré', 'vante > re', 'vante > ré'],
            'ré > vante': ['ré > vante', 're > vante', 're > vante'],
            'bombordo > boreste': ['bombordo > boreste', 'bombordo > boreste'],
            'boreste < bombordo': ['boreste < bombordo', 'boreste < bombordo'],
        }
        for canon, opts in variants.items():
            for opt in opts:
                if low == opt:
                    return canon
        # keywords
        if 'bombordo' in low and 'boreste' in low:
            # decide direction heuristically by token order (if present)
            if low.index('boreste') < low.index('bombordo'):
                return 'boreste < bombordo'
            return 'bombordo > boreste'
        if 'vante' in low and ('ré' in low or 're' in low):
            return 'vante > ré'
        if ('ré' in low or 're' in low) and 'vante' in low:
            return 'ré > vante'
        # fallback: if raw contains arrow-like tokens
        if '>' in low or '<' in low or '->' in low:
            if 'vante' in low:
                return 'vante > ré'
            if 'ré' in low or 're' in low:
                return 'ré > vante'
        return None
    except Exception:
        return None


# Global safe save helper para mitigar erros sqlite 'database is locked'
def _safe_save_global(obj, max_attempts=6, initial_delay=0.05):
    import time
    from django.db.utils import OperationalError as DjangoOperationalError, ProgrammingError as DjangoProgrammingError
    logger = logging.getLogger(__name__)
    attempt = 0
    delay = initial_delay
    last_exc = None
    while attempt < max_attempts:
        try:
            # Resolve DB alias for the object's connection (fallback to default)
            try:
                alias = getattr(getattr(obj, '_state', None), 'db', None) or 'default'
            except Exception:
                alias = 'default'

            # If the current transaction is marked for rollback on THIS connection,
            # abort early to preserve the original exception and avoid confusing
            # secondary errors. Try both the connection-specific and the generic
            # helpers for compatibility across Django versions.
            try:
                from django.db import connections
                conn = connections[alias]
            except Exception:
                conn = None

            try:
                # Prefer checking the transaction state on the specific connection
                rolled_back = False
                try:
                    if conn is not None and hasattr(conn, 'get_rollback'):
                        rolled_back = conn.get_rollback()
                except Exception:
                    rolled_back = False

                if not rolled_back:
                    # fall back to module-level helper if available
                    try:
                        rolled_back = transaction.get_rollback(using=alias)
                    except Exception:
                        try:
                            rolled_back = transaction.get_rollback()
                        except Exception:
                            rolled_back = False

                if rolled_back:
                    logger.error('Current DB transaction marked for rollback; aborting save for %s (alias=%s)', getattr(obj, '__class__', obj), alias)
                    raise transaction.TransactionManagementError('Current transaction marked for rollback; aborting save')
            except transaction.TransactionManagementError:
                # re-raise the expected type
                raise
            except Exception:
                # non-fatal: allow save attempt to proceed and fail naturally
                pass

            obj.save()
            return True
        except Exception as e:
            last_exc = e
            try:
                # If SQLite lock, retry with backoff. Avoid closing all
                # connections (connections.close_all()) because that can close
                # the active connection used by the current request and leave
                # Django in an inconsistent state. Prefer close_old_connections()
                # which politely closes stale connections and lets Django reopen
                # a fresh one when needed.
                msg = str(e).lower()
                if isinstance(e, DjangoOperationalError) and 'locked' in msg:
                    # If we're inside an atomic block on this connection, avoid
                    # closing the connection or sleeping/retrying because closing
                    # will mark the transaction for rollback. In that case,
                    # surface the original OperationalError to the caller.
                    try:
                        in_atomic = False
                        if conn is not None and hasattr(conn, 'in_atomic_block'):
                            in_atomic = bool(getattr(conn, 'in_atomic_block'))
                        else:
                            try:
                                in_atomic = bool(transaction.get_connection(using=alias).in_atomic_block)
                            except Exception:
                                in_atomic = False
                    except Exception:
                        in_atomic = False

                    if in_atomic:
                        logger.error('Database locked while in atomic block for %s; aborting save instead of retry to avoid marking transaction for rollback (alias=%s)', getattr(obj, '__class__', obj), alias)
                        raise

                    attempt += 1
                    logger.warning('Database locked when saving %s; retry %s/%s after %.2fs (alias=%s)', getattr(obj, '__class__', obj), attempt, max_attempts, delay, alias)
                    try:
                        # Prefer closing the specific connection if available
                        from django.db import connections
                        try:
                            if alias in connections:
                                connections[alias].close()
                        except Exception:
                            # fallback to conservative close_old_connections
                            try:
                                close_old_connections()
                            except Exception:
                                pass
                    except Exception:
                        try:
                            close_old_connections()
                        except Exception:
                            pass
                    time.sleep(delay)
                    delay = min(delay * 2, 1.0)
                    continue

                # If ProgrammingError complains about a closed DB, attempt a
                # single recovery: close old connections and retry once. This
                # may recover from situations where a stale/closed connection
                # object remained open in the pool.
                if isinstance(e, DjangoProgrammingError) and 'closed' in msg:
                    logger.exception('ProgrammingError while saving (closed DB) for %s; attempting single reconnect (alias=%s)', getattr(obj, '__class__', obj), alias)
                    # Try to close the specific connection and let Django reopen it
                    try:
                        from django.db import connections
                        try:
                            if alias in connections:
                                connections[alias].close()
                        except Exception:
                            # fallback
                            try:
                                close_old_connections()
                            except Exception:
                                logger.exception('close_old_connections() failed while handling closed DB')
                    except Exception:
                        try:
                            close_old_connections()
                        except Exception:
                            logger.exception('close_old_connections() failed while handling closed DB')

                    # If the current transaction is marked for rollback on this connection, abort
                    try:
                        rolled_back = False
                        try:
                            if conn is not None and hasattr(conn, 'get_rollback'):
                                rolled_back = conn.get_rollback()
                        except Exception:
                            rolled_back = False
                        if not rolled_back:
                            try:
                                rolled_back = transaction.get_rollback(using=alias)
                            except Exception:
                                try:
                                    rolled_back = transaction.get_rollback()
                                except Exception:
                                    rolled_back = False
                        if rolled_back:
                            logger.error('Current DB transaction marked for rollback after closed DB; aborting save for %s (alias=%s)', getattr(obj, '__class__', obj), alias)
                            raise transaction.TransactionManagementError('Current transaction marked for rollback; aborting save')
                    except Exception:
                        logger.exception('Failed checking transaction state after closed DB')
                        raise

                    # Try one final save attempt after reconnect
                    try:
                        obj.save()
                        return True
                    except Exception as final_e:
                        logger.exception('Retry after reconnect failed for %s; aborting', getattr(obj, '__class__', obj))
                        raise final_e
            except Exception:
                pass
            # re-raise original if not handled above
            raise
    try:
        # Before the final attempt, double-check transaction state.
        try:
            if transaction.get_rollback():
                logger.error('Current DB transaction marked for rollback; aborting final save for %s', getattr(obj, '__class__', obj))
                raise transaction.TransactionManagementError('Current transaction marked for rollback; aborting save')
        except Exception:
            pass
        obj.save()
        return True
    except Exception:
        logger.exception('Final save attempt failed for object %s', getattr(obj, '__class__', obj))
        raise last_exc


@login_required(login_url='/login/')
@require_GET
def rdo_print(request, rdo_id):
    """Renderiza a página de impressão do RDO totalmente pelo backend.
    Reaproveita o payload de rdo_detail (JSON) para montar o contexto do template.
    """
    rdo_payload = {}
    try:
        jr = rdo_detail(request, rdo_id)
        if getattr(jr, 'status_code', 500) == 200:
            data = _json.loads(jr.content.decode('utf-8'))
            if data.get('success'):
                rdo_payload = data.get('rdo', {}) or {}
    except Exception:
        rdo_payload = {}

    # Data formatada (opcional)
    try:
        if rdo_payload.get('data'):
            from datetime import datetime
            dt = datetime.fromisoformat(str(rdo_payload['data']).replace('Z','').replace('z',''))
            rdo_payload['data_fmt'] = dt.strftime('%d/%m/%Y')
        else:
            rdo_payload['data_fmt'] = ''
    except Exception:
        rdo_payload['data_fmt'] = rdo_payload.get('data', '')

    # Normalizar chaves em minúsculas (compat com templates que usam nomes lower-case)
    try:
        for k in list(rdo_payload.keys()):
            lk = k.lower()
            if lk not in rdo_payload:
                rdo_payload[lk] = rdo_payload.get(k)
    except Exception:
        pass

    # Equipe rows / EC / fotos
    equipe_rows, ec_entradas, ec_saidas, fotos_padded = [], [], [], []
    try:
        equipe = rdo_payload.get('equipe') or []
        # normalizar chaves dos membros para evitar falhas no template (ex.: nome_completo)
        if isinstance(equipe, list):
            for m in equipe:
                if not isinstance(m, dict):
                    continue
                # nome_completo preferencialmente, senão usar 'nome' ou 'display_name'
                m['nome_completo'] = m.get('nome_completo') or m.get('nome') or m.get('display_name') or ''
                # garantir campo funcao e variações usadas no template
                m['funcao'] = m.get('funcao') or m.get('funcao_label') or m.get('role') or m.get('funcao_nome') or ''
                m['funcao_label'] = m.get('funcao_label') or m.get('funcao') or m.get('funcao_nome') or ''
                m['funcao_nome'] = m.get('funcao_nome') or m.get('funcao') or m.get('funcao_label') or ''
                # alias explícito para 'role' (usado por alguns payloads/templating)
                m['role'] = m.get('role') or m.get('funcao') or m.get('funcao_label') or m.get('funcao_nome') or ''
                # garantir campos name/display_name usados pelo template (evita VariableDoesNotExist)
                m['name'] = m.get('name') or m.get('nome') or m.get('nome_completo') or ''
                m['display_name'] = m.get('display_name') or m.get('nome_completo') or m.get('name') or ''
                # padronizar flag de serviço
                if 'em_servico' not in m:
                    m['em_servico'] = bool(m.get('ativo') or m.get('emServico'))
            for i in range(0, len(equipe), 3):
                chunk = equipe[i:i+3]
                any_active = any(bool(m.get('em_servico') or m.get('ativo') or m.get('emServico')) for m in chunk)
                while len(chunk) < 3:
                    chunk.append({})
                equipe_rows.append({ 'members': chunk, 'em_servico': any_active })
        ec = rdo_payload.get('ec_times') or {}
        for idx in range(1, 7):
            ec_entradas.append(ec.get(f'entrada_{idx}', ''))
            ec_saidas.append(ec.get(f'saida_{idx}', ''))
        fotos = rdo_payload.get('fotos') or []
        try:
            # normalize and attempt to recover missing files by searching the media folder
            resolved = []
            media_root = getattr(settings, 'MEDIA_ROOT', None) or ''
            media_url = getattr(settings, 'MEDIA_URL', '/media/')
            for f in (fotos if isinstance(fotos, list) else []):
                try:
                    if not f:
                        resolved.append(None)
                        continue
                    f_str = str(f).strip()
                    # derive relative path inside MEDIA_ROOT
                    rel = f_str
                    # Normalizar caminhos gravados de forma inconsistente.
                    # Alguns registros têm '/media/fotos_rdo/rdos/..' (duplicando o
                    # segmento 'fotos_rdo') — nesse caso precisamos remover o
                    # segmento extra para que a URL resultante aponte para
                    # MEDIA_ROOT/rdos/.. (o local canônico).
                    try:
                        dup_prefix = (media_url.rstrip('/') + '/fotos_rdo/').replace('///', '/').replace('//', '/')
                    except Exception:
                        dup_prefix = media_url + 'fotos_rdo/'

                    if f_str.startswith(dup_prefix):
                        # remover '/media/fotos_rdo/' para ficar apenas 'rdos/...'
                        rel = f_str[len(dup_prefix):].lstrip('/')
                    elif f_str.startswith(media_url):
                        rel = f_str[len(media_url):].lstrip('/')
                    elif f_str.startswith('/'):
                        rel = f_str.lstrip('/')

                    rel_path = os.path.join(media_root, rel)

                    # if file exists and non-empty, build URL via '/fotos_rdo/' alias (works in dev/prod)
                    if os.path.exists(rel_path) and os.path.getsize(rel_path) > 0:
                        url = os.path.join('/fotos_rdo'.rstrip('/'), rel).replace('\\', '/')
                        resolved.append(url)
                        continue

                    # fallback: try to find a file with same suffix (e.g. '_capa_Limpeza_Industrial.jpg')
                    try:
                        basename = os.path.basename(rel)
                        parts = basename.split('_')
                        suffix = '_'.join(parts[1:]) if len(parts) > 1 else basename
                        # Search recursively across MEDIA_ROOT to cover nested paths like
                        # 'fotos_rdo/fotos_rdo/rdos'. Prefer a file in the same directory if available,
                        # otherwise fall back to a global recursive search.
                        candidates = []
                        try:
                            search_dir = os.path.dirname(rel_path) or os.path.join(media_root, 'rdos')
                            pattern_local = os.path.join(search_dir, '*' + suffix)
                            candidates = glob.glob(pattern_local)
                        except Exception:
                            candidates = []
                        if not candidates:
                            pattern_recursive = os.path.join(media_root, '**', '*' + suffix)
                            candidates = glob.glob(pattern_recursive, recursive=True)
                        # prefer non-empty files, choose largest by size then newest
                        candidates = [c for c in candidates if os.path.exists(c) and os.path.getsize(c) > 0]
                        if candidates:
                            candidates.sort(key=lambda p: (os.path.getsize(p), os.path.getmtime(p)), reverse=True)
                            pick = candidates[0]
                            rel_pick = os.path.relpath(pick, media_root)
                            # Preferir o alias '/fotos_rdo/' para ser servido tanto pelo Django (dev)
                            # quanto pelo Nginx (prod)
                            url = os.path.join('/fotos_rdo'.rstrip('/'), rel_pick).replace('\\', '/')
                            logging.getLogger(__name__).warning('Photo missing, using alternative %s for requested %s', rel_pick, rel)
                            resolved.append(url)
                            continue
                    except Exception:
                        pass

                    # last resort: leave None so template shows empty slot
                    resolved.append(None)
                except Exception:
                    resolved.append(None)

            # pad to 5 slots
            fotos_padded = resolved[:5]
            while len(fotos_padded) < 5:
                fotos_padded.append(None)
        except Exception:
            fotos_padded = [None, None, None, None, None]
    except Exception:
        fotos_padded = [None, None, None, None, None]

    context = {
        'rdo': rdo_payload,
        'equipe_rows': equipe_rows,
        'ec_entradas': ec_entradas,
        'ec_saidas': ec_saidas,
        'fotos_padded': fotos_padded,
        'inline_css': _get_rdo_inline_css(),
    }

    # Preferir cálculos/valores provenientes do próprio RDO (fonte canônica).
    # Aqui estamos no contexto de `rdo_print` — temos `rdo_payload` (serializado) mas
    # não necessariamente o objeto `RDO` em `rdo_obj`. Tentar usar o valor serializado
    # primeiro; se ausente, tentar buscar a instância e calcular com segurança.
    try:
        if not rdo_payload.get('hh_disponivel_cumulativo'):
            try:
                ro = RDO.objects.select_related('ordem_servico').get(pk=rdo_id)
            except Exception:
                ro = None

            if ro is not None:
                try:
                    if hasattr(ro, 'calc_hh_disponivel_cumulativo_time'):
                        hh_time = ro.calc_hh_disponivel_cumulativo_time()
                        if hh_time:
                            rdo_payload['hh_disponivel_cumulativo'] = hh_time
                    else:
                        hh_field = getattr(ro, 'hh_disponivel_cumulativo', None)
                        if hh_field:
                            rdo_payload['hh_disponivel_cumulativo'] = hh_field
                except Exception:
                    # não bloquear montagem do contexto/print se o cálculo falhar
                    pass
    except Exception:
        pass

    # Garantir chaves *_hhmm (strings 'HH:MM') para compatibilidade com inputs type=time
    try:
        from datetime import time as _dt_time
        def _time_to_hhmm(v):
            try:
                if v is None:
                    return None
                if isinstance(v, _dt_time):
                    return v.strftime('%H:%M')
                s = str(v)
                if not s:
                    return None
                if ':' in s:
                    parts = s.split(':')
                    try:
                        h = int(parts[0]); m = int(parts[1]) if len(parts) > 1 else 0
                        return f"{h:02d}:{m:02d}"
                    except Exception:
                        return s
                return s
            except Exception:
                return None

        rdo_payload['total_hh_cumulativo_real_hhmm'] = _time_to_hhmm(rdo_payload.get('total_hh_cumulativo_real'))
        rdo_payload['hh_disponivel_cumulativo_hhmm'] = _time_to_hhmm(rdo_payload.get('hh_disponivel_cumulativo'))
        rdo_payload['total_hh_frente_real_hhmm'] = _time_to_hhmm(rdo_payload.get('total_hh_frente_real'))
    except Exception:
        # não bloquear fluxo principal se formatação falhar
        pass

    return render(request, 'rdo_print.html', context)


@login_required(login_url='/login/')
@require_GET
def rdo_page(request, rdo_id):
    """Renderiza a página dedicada do RDO (versão navegável, usada pelo botão View).
    Reaproveita o payload JSON de rdo_detail para preencher o template `rdo_page.html`.
    """
    rdo_payload = {}
    try:
        jr = rdo_detail(request, rdo_id)
        if getattr(jr, 'status_code', 500) == 200:
            data = _json.loads(jr.content.decode('utf-8'))
            if data.get('success'):
                rdo_payload = data.get('rdo', {}) or {}
    except Exception:
        rdo_payload = {}
    # Normalizar algumas chaves e preparar contexto mínimo para o template
    try:
        if rdo_payload.get('data_inicio'):
            from datetime import datetime
            raw = str(rdo_payload.get('data_inicio'))
            try:
                # tenta ISO first (with optional time)
                dt = datetime.fromisoformat(raw.replace('Z','').replace('z',''))
                rdo_payload['data_inicio_fmt'] = dt.strftime('%d/%m/%Y')
            except Exception:
                try:
                    # tenta YYYY-MM-DD
                    dt = datetime.strptime(raw, '%Y-%m-%d')
                    rdo_payload['data_inicio_fmt'] = dt.strftime('%d/%m/%Y')
                except Exception:
                    # fallback: keep original string
                    rdo_payload['data_inicio_fmt'] = raw
        else:
            rdo_payload['data_inicio_fmt'] = rdo_payload.get('data_inicio', '')
    except Exception:
        rdo_payload['data_inicio_fmt'] = rdo_payload.get('data_inicio', '')

    # Ensure fotos list and resolve each entry to a valid URL under '/fotos_rdo/...'
    try:
        fotos = rdo_payload.get('fotos') or []
        if not isinstance(fotos, (list, tuple)):
            if isinstance(fotos, str):
                fotos = [ln for ln in fotos.splitlines() if ln.strip()]
            else:
                fotos = []

        resolved = []
        media_root = getattr(settings, 'MEDIA_ROOT', '') or ''
        media_url = getattr(settings, 'MEDIA_URL', '/media/')
        try:
            dup_prefix = (media_url.rstrip('/') + '/fotos_rdo/').replace('///', '/').replace('//', '/')
        except Exception:
            dup_prefix = media_url + 'fotos_rdo/'

        for f in fotos:
            try:
                if not f:
                    resolved.append(None)
                    continue
                f_str = str(f).strip()
                # derive relative path inside MEDIA_ROOT
                rel = f_str
                if f_str.startswith(dup_prefix):
                    rel = f_str[len(dup_prefix):].lstrip('/')
                elif f_str.startswith(media_url):
                    rel = f_str[len(media_url):].lstrip('/')
                elif f_str.startswith('/'):
                    rel = f_str.lstrip('/')
                rel_path = os.path.join(media_root, rel)

                # direct hit
                if os.path.exists(rel_path) and os.path.getsize(rel_path) > 0:
                    url = os.path.join('/fotos_rdo'.rstrip('/'), rel).replace('\\', '/')
                    resolved.append(url)
                    continue

                # fallback: recursive search for same suffix
                try:
                    basename = os.path.basename(rel)
                    parts = basename.split('_')
                    suffix = '_'.join(parts[1:]) if len(parts) > 1 else basename
                    candidates = []
                    try:
                        search_dir = os.path.dirname(rel_path) or os.path.join(media_root, 'rdos')
                        pattern_local = os.path.join(search_dir, '*' + suffix)
                        candidates = glob.glob(pattern_local)
                    except Exception:
                        candidates = []
                    if not candidates:
                        pattern_recursive = os.path.join(media_root, '**', '*' + suffix)
                        candidates = glob.glob(pattern_recursive, recursive=True)
                    candidates = [c for c in candidates if os.path.exists(c) and os.path.getsize(c) > 0]
                    if candidates:
                        candidates.sort(key=lambda p: (os.path.getsize(p), os.path.getmtime(p)), reverse=True)
                        pick = candidates[0]
                        rel_pick = os.path.relpath(pick, media_root)
                        url = os.path.join('/fotos_rdo'.rstrip('/'), rel_pick).replace('\\', '/')
                        logging.getLogger(__name__).warning('Photo missing (page), using alternative %s for requested %s', rel_pick, rel)
                        resolved.append(url)
                        continue
                except Exception:
                    pass

                resolved.append(None)
            except Exception:
                resolved.append(None)

        fotos_padded = resolved[:5]
        while len(fotos_padded) < 5:
            fotos_padded.append(None)
    except Exception:
        fotos_padded = [None, None, None, None, None]

    # EC times (entradas/saidas) - provide arrays of 6 entries for template
    ec_entradas, ec_saidas = [], []
    try:
        ec = rdo_payload.get('ec_times') or {}
        for idx in range(1, 7):
            ec_entradas.append(ec.get(f'entrada_{idx}', ''))
            ec_saidas.append(ec.get(f'saida_{idx}', ''))
    except Exception:
        ec_entradas = [''] * 6
        ec_saidas = [''] * 6

    # equipe_rows: normalize member dicts (ensure nome_completo, funcao_label, em_servico)
    # then build simple chunks of 3 members expected by the template
    equipe_rows = []
    try:
        equipe = rdo_payload.get('equipe') or []
        if isinstance(equipe, list):
            # normalize keys on each member dict to match templates that expect
            # nome_completo, funcao_label, name, display_name and em_servico
            for m in equipe:
                if not isinstance(m, dict):
                    continue
                m['nome_completo'] = m.get('nome_completo') or m.get('nome') or m.get('display_name') or ''
                m['funcao'] = m.get('funcao') or m.get('funcao_label') or m.get('role') or m.get('funcao_nome') or ''
                m['funcao_label'] = m.get('funcao_label') or m.get('funcao') or m.get('funcao_nome') or ''
                m['funcao_nome'] = m.get('funcao_nome') or m.get('funcao') or m.get('funcao_label') or ''
                m['role'] = m.get('role') or m.get('funcao') or m.get('funcao_label') or m.get('funcao_nome') or ''
                m['name'] = m.get('name') or m.get('nome') or m.get('nome_completo') or ''
                m['display_name'] = m.get('display_name') or m.get('nome_completo') or m.get('name') or ''
                if 'em_servico' not in m:
                    m['em_servico'] = bool(m.get('ativo') or m.get('emServico'))

            # chunk into rows of 3 members
            if equipe:
                for i in range(0, len(equipe), 3):
                    chunk = equipe[i:i+3]
                    while len(chunk) < 3:
                        chunk.append({})
                    any_active = any(bool(m.get('em_servico')) for m in chunk if isinstance(m, dict))
                    equipe_rows.append({'members': chunk, 'em_servico': any_active})
    except Exception:
        equipe_rows = []

    # Attempt to translate activity comments PT -> EN when EN is missing
    try:
        atividades = rdo_payload.get('atividades') or []
        if isinstance(atividades, list) and atividades:
            # try to import translator
            try:
                from deep_translator import GoogleTranslator
                _translator = GoogleTranslator(source='pt', target='en')
            except Exception:
                _translator = None
            for a in atividades:
                if not isinstance(a, dict):
                    continue
                pt = (a.get('comentario_pt') or '')
                en = (a.get('comentario_en') or '')
                if (not en) and pt:
                    if _translator is not None:
                        try:
                            tr = _translator.translate(pt)
                            a['comentario_en'] = tr or pt
                        except Exception:
                            a['comentario_en'] = pt
                    else:
                        # no translator available, keep pt as fallback
                        a['comentario_en'] = pt
            # ensure payload updated
            rdo_payload['atividades'] = atividades
    except Exception:
        pass

    # sanitize EC arrays: convert None or string 'None' to empty string for template
    try:
        ec_entradas = [ ('' if (t is None or (isinstance(t, str) and t.strip().lower() == 'none')) else t) for t in ec_entradas ]
        ec_saidas = [ ('' if (t is None or (isinstance(t, str) and t.strip().lower() == 'none')) else t) for t in ec_saidas ]
    except Exception:
        ec_entradas = [''] * 6
        ec_saidas = [''] * 6

    # Normalize and format 'confinado' display value: prefer various aliases
    try:
        conf_raw = None
        # possible keys in payload
        for key in ('confinado', 'espaco_confinado', 'espaco_confinado_bool', 'confinado_bool', 'espacoConfinado'):
            if key in rdo_payload and rdo_payload.get(key) is not None:
                conf_raw = rdo_payload.get(key)
                break

        def _to_sim_nao(v):
            if v is None:
                return ''
            if isinstance(v, bool):
                return 'Sim' if v else 'Não'
            s = str(v).strip()
            if not s:
                return ''
            low = s.lower()
            if low in ('1', 'true', 'sim', 's', 'yes', 'y'):
                return 'Sim'
            if low in ('0', 'false', 'nao', 'não', 'n', 'no'):
                return 'Não'
            # otherwise return original string (capitalized)
            return s

        # only set if not already present (don't override explicit expected value)
        if 'confinado' not in rdo_payload or rdo_payload.get('confinado') in (None, ''):
            rdo_payload['confinado'] = _to_sim_nao(conf_raw)
        else:
            # ensure human readable
            rdo_payload['confinado'] = _to_sim_nao(rdo_payload.get('confinado'))
    except Exception:
        try:
            if 'confinado' not in rdo_payload:
                rdo_payload['confinado'] = ''
        except Exception:
            pass

    # If 'ciente_observacoes_en' is missing but PT text exists, attempt server-side translation
    try:
        # support multiple possible keys/aliases
        ciente_pt = rdo_payload.get('ciente_observacoes_pt') or rdo_payload.get('ciente_observacoes') or rdo_payload.get('ciente') or ''
        ciente_en = rdo_payload.get('ciente_observacoes_en') or ''
        if (not ciente_en) and ciente_pt:
            try:
                from deep_translator import GoogleTranslator
                try:
                    tr = GoogleTranslator(source='pt', target='en').translate(str(ciente_pt))
                    if tr:
                        rdo_payload['ciente_observacoes_en'] = tr
                    else:
                        # fallback: mirror PT if translation returned empty
                        rdo_payload['ciente_observacoes_en'] = str(ciente_pt)
                except Exception:
                    # translator failed at runtime: fallback to PT
                    rdo_payload['ciente_observacoes_en'] = str(ciente_pt)
            except Exception:
                # deep_translator not available: fallback to PT as display
                rdo_payload['ciente_observacoes_en'] = str(ciente_pt)
    except Exception:
        pass

    # Normalizar chaves do payload para versões em lowercase (templates usam lowercase)
    try:
        for k in list(rdo_payload.keys()):
            lk = k.lower()
            if lk not in rdo_payload:
                rdo_payload[lk] = rdo_payload.get(k)
    except Exception:
        pass

    # Normalize exist_pt display to 'Sim'/'Não' if boolean or truthy string
    try:
        if 'exist_pt' in rdo_payload:
            val = rdo_payload.get('exist_pt')
            if isinstance(val, bool):
                rdo_payload['exist_pt'] = 'Sim' if val else 'Não'
            else:
                s = str(val).strip()
                if s.lower() in ('1', 'true', 'sim', 's', 'yes', 'y'):
                    rdo_payload['exist_pt'] = 'Sim'
                elif s.lower() in ('0', 'false', 'nao', 'não', 'n', 'no'):
                    rdo_payload['exist_pt'] = 'Não'
                else:
                    # keep original string if it's already user-friendly
                    rdo_payload['exist_pt'] = s
    except Exception:
        pass

    # Normalize select_turnos: if it's a list -> join with comma; if it's a string that looks like a list, clean it
    try:
        st = rdo_payload.get('select_turnos')
        def _uniq_preserve(seq):
            seen = set()
            out = []
            for it in seq:
                try:
                    s = ('' if it is None else str(it)).strip()
                except Exception:
                    s = str(it)
                if not s:
                    continue
                if s in seen:
                    continue
                seen.add(s)
                out.append(s)
            return out

        if isinstance(st, (list, tuple)):
            parts = _uniq_preserve(st)
            rdo_payload['select_turnos'] = ', '.join(parts)
        elif isinstance(st, str):
            s = st.strip()
            if s.startswith('[') and s.endswith(']'):
                inner = s[1:-1].strip()
                if inner:
                    parts = [p.strip().strip("'\"") for p in inner.split(',') if p.strip()]
                    parts = _uniq_preserve(parts)
                    rdo_payload['select_turnos'] = ', '.join(parts)
                else:
                    rdo_payload['select_turnos'] = ''
            elif ',' in s:
                # comma-separated string: split, clean and dedupe
                parts = [p.strip() for p in s.split(',') if p.strip()]
                parts = _uniq_preserve(parts)
                rdo_payload['select_turnos'] = ', '.join(parts)
            else:
                rdo_payload['select_turnos'] = s
        else:
            rdo_payload['select_turnos'] = rdo_payload.get('select_turnos') or ''
    except Exception:
        try:
            rdo_payload['select_turnos'] = rdo_payload.get('select_turnos') or ''
        except Exception:
            pass

    # Helper: recursively clean values like None or the literal string 'None' to empty string
    def _clean_none_values(obj):
        try:
            if obj is None:
                return ''
            if isinstance(obj, str):
                s = obj.strip()
                if s.lower() == 'none':
                    return ''
                return obj
            if isinstance(obj, dict):
                out = {}
                for kk, vv in obj.items():
                    out[kk] = _clean_none_values(vv)
                return out
            if isinstance(obj, (list, tuple)):
                out_list = []
                for vv in obj:
                    out_list.append(_clean_none_values(vv))
                return out_list
            # leave other types (numbers, bools, dates) as-is
            return obj
        except Exception:
            return obj

    try:
        # Clean payload and commonly used derived structures to avoid 'None' strings in templates
        rdo_payload = _clean_none_values(rdo_payload)
        # ensure ec arrays are strings or empty
        ec_entradas = [ ('' if (t is None or (isinstance(t, str) and str(t).strip().lower() == 'none')) else t) for t in ec_entradas ]
        ec_saidas = [ ('' if (t is None or (isinstance(t, str) and str(t).strip().lower() == 'none')) else t) for t in ec_saidas ]
        # clean activities list
        if 'atividades' in rdo_payload and isinstance(rdo_payload.get('atividades'), list):
            rdo_payload['atividades'] = _clean_none_values(rdo_payload.get('atividades'))
        # equipe_rows members
        try:
            cleaned_rows = []
            for row in equipe_rows:
                if isinstance(row, dict):
                    members = row.get('members', [])
                    cleaned_members = []
                    for m in members:
                        if isinstance(m, dict):
                            cleaned_members.append(_clean_none_values(m))
                        else:
                            cleaned_members.append(m)
                    cleaned_rows.append({'members': cleaned_members, 'em_servico': row.get('em_servico')})
                else:
                    cleaned_rows.append(row)
            equipe_rows = cleaned_rows
        except Exception:
            pass
        # fotos padding
        try:
            fotos_padded = [ ('' if (f is None or (isinstance(f, str) and str(f).strip().lower() == 'none')) else f) for f in fotos_padded ]
        except Exception:
            pass
    except Exception:
        pass

    context = {
        'rdo': rdo_payload,
        'equipe_rows': equipe_rows,
        'fotos_padded': fotos_padded,
        'ec_entradas': ec_entradas,
        'ec_saidas': ec_saidas,
        'inline_css': _get_rdo_inline_css(),
    }
    # Provide explicit `tanques` in context for templates that prefer a list
    try:
        tanques_list = rdo_payload.get('tanques') or []
        # Normalize when payload provides a dict mapping instead of list
        if isinstance(tanques_list, dict):
            try:
                tanques_list = list(tanques_list.values())
            except Exception:
                tanques_list = []
        # Enrich tanks when payload exists but misses structural fields (volume, patamar, tipo, etc.)
        if tanques_list and rdo_id:
            try:
                qs = RdoTanque.objects.filter(rdo_id=rdo_id)
                by_id = {getattr(t, 'id', None): t for t in qs}
                by_code = {}
                for t in qs:
                    code = getattr(t, 'tanque_codigo', None)
                    if code and code not in by_code:
                        by_code[code] = t

                def _is_placeholder(val):
                    try:
                        if val is None:
                            return True
                        if isinstance(val, str):
                            s = val.strip().lower()
                            return s in ('', '-', '—', 'none', 'null')
                        return False
                    except Exception:
                        return False
                def pick(*vals):
                    for v in vals:
                        if not _is_placeholder(v):
                            return v
                    return None

                enriched = []
                for d in tanques_list:
                    if not isinstance(d, dict):
                        enriched.append(d)
                        continue
                    did = d.get('id')
                    dcode = d.get('tanque_codigo') or d.get('codigo')
                    mt = by_id.get(did) if did in by_id else by_code.get(dcode)
                    # Helper getters from model t
                    def mget(attr):
                        return getattr(mt, attr, None) if mt else None

                    codigo = pick(d.get('codigo'), d.get('tanque_codigo'), mget('tanque_codigo'))
                    volume = pick(d.get('volume'), d.get('volume_tanque_exec'), mget('volume_tanque_exec'), mget('volume'))
                    patamar = pick(d.get('patamar'), d.get('patamares'), mget('patamar'), mget('patamares'))
                    tipo = pick(d.get('tipo_tanque'), d.get('tipo'), mget('tipo_tanque'), mget('tipo'))
                    ncomp = pick(d.get('numero_compartimentos'), d.get('numero_compartimento'), mget('numero_compartimentos'), mget('numero_compartimento'))
                    gavetas = pick(d.get('gavetas'), mget('gavetas'))
                    nome = pick(d.get('nome'), d.get('nome_tanque'), mget('nome'), mget('tanque_nome'))

                    nd = dict(d)
                    if codigo is not None:
                        nd.setdefault('codigo', codigo)
                        nd.setdefault('tanque_codigo', codigo)
                    if volume is not None:
                        nd.setdefault('volume', volume)
                        nd.setdefault('volume_tanque_exec', volume)
                    if patamar is not None:
                        nd.setdefault('patamar', patamar)
                        nd.setdefault('patamares', patamar)
                    if tipo is not None:
                        nd.setdefault('tipo_tanque', tipo)
                        nd.setdefault('tipo', tipo)
                    if ncomp is not None:
                        nd.setdefault('numero_compartimentos', ncomp)
                        nd.setdefault('numero_compartimento', ncomp)
                    if gavetas is not None:
                        nd.setdefault('gavetas', gavetas)
                    if nome is not None:
                        nd.setdefault('nome', nome)
                        nd.setdefault('tanque_nome', nome)
                    # Normalize and expose bombeio/total_liquido from payload or model
                    try:
                        def pick_tank(*names):
                            for n in names:
                                v = d.get(n) if isinstance(d, dict) else None
                                if v is None:
                                    try:
                                        v = mget(n)
                                    except Exception:
                                        v = None
                                if not _is_placeholder(v):
                                    return v
                            return None

                        bval = pick_tank('bombeio', 'quantidade_bombeada', 'quantidade_bombeio', 'bombeio_dia', 'bombeado')
                        if bval is not None:
                            # sobrescrever se ausente ou placeholder ('', None, '-')
                            if ('bombeio' not in nd) or _is_placeholder(nd.get('bombeio')):
                                nd['bombeio'] = bval

                        tlq = pick_tank('total_liquido', 'total_liquidos', 'total_liquido_dia', 'residuo_liquido')
                        if tlq is not None:
                            if ('total_liquido' not in nd) or _is_placeholder(nd.get('total_liquido')):
                                nd['total_liquido'] = tlq

                        # sentido: accept multiple aliases and normalize to canonical token + human label
                        sraw = pick_tank('sentido_limpeza', 'sentido', 'direcao', 'direcao_limpeza', 'sentido_exec')
                        if sraw is not None:
                            try:
                                token = _canonicalize_sentido(sraw)
                                if token:
                                    nd.setdefault('sentido_limpeza', token)
                                    # human-friendly label (keep accentuation/format)
                                    if token == 'vante > ré':
                                        nd['sentido_label'] = nd.get('sentido_label') or 'Vante > Ré'
                                    elif token == 'ré > vante':
                                        nd['sentido_label'] = nd.get('sentido_label') or 'Ré > Vante'
                                    elif token == 'bombordo > boreste':
                                        nd['sentido_label'] = nd.get('sentido_label') or 'Bombordo > Boreste'
                                    elif token == 'boreste < bombordo':
                                        nd['sentido_label'] = nd.get('sentido_label') or 'Boreste < Bombordo'
                                else:
                                    # keep original string as label when we can't canonicalize
                                    sval = sraw
                                    if isinstance(sval, str) and not _is_placeholder(sval):
                                        nd.setdefault('sentido_limpeza', None)
                                        nd['sentido_label'] = nd.get('sentido_label') or sval
                                    else:
                                        nd.setdefault('sentido_limpeza', None)
                            except Exception:
                                try:
                                    nd.setdefault('sentido_limpeza', None)
                                except Exception:
                                    pass

                        # Compatibilidade: originalmente copiávamos o label para `t.sentido`
                        # para templates legados. Para forçar que o "sentido" venha do RDO,
                        # desativamos essa cópia — preferimos que o template use `rdo.sentido_limpeza`.
                        # if nd.get('sentido_label') and (_is_placeholder(nd.get('sentido'))):
                        #     nd['sentido'] = nd.get('sentido_label')
                    except Exception:
                        pass
                    enriched.append(nd)
                tanques_list = enriched
                # Append tanks that exist in DB but are missing from payload
                try:
                    present_ids = set([x.get('id') for x in enriched if isinstance(x, dict) and x.get('id') is not None])
                    present_codes = set([ (x.get('tanque_codigo') or x.get('codigo')) for x in enriched if isinstance(x, dict) and (x.get('tanque_codigo') or x.get('codigo')) ])
                    for t in qs:
                        tid = getattr(t, 'id', None)
                        tcode = getattr(t, 'tanque_codigo', None)
                        if (tid in present_ids) or (tcode and tcode in present_codes):
                            continue
                        tanques_list.append({
                            'id': tid,
                            'codigo': getattr(t, 'tanque_codigo', None),
                            'tanque_codigo': getattr(t, 'tanque_codigo', None),
                            'volume': getattr(t, 'volume_tanque_exec', None) or getattr(t, 'volume', None),
                            'volume_tanque_exec': getattr(t, 'volume_tanque_exec', None),
                            'patamar': getattr(t, 'patamar', None) or getattr(t, 'patamares', None),
                            'patamares': getattr(t, 'patamar', None) or getattr(t, 'patamares', None),
                            'tipo_tanque': getattr(t, 'tipo_tanque', None) or getattr(t, 'tipo', None),
                            'tipo': getattr(t, 'tipo_tanque', None) or getattr(t, 'tipo', None),
                            'numero_compartimentos': getattr(t, 'numero_compartimentos', None) or getattr(t, 'numero_compartimento', None),
                            'numero_compartimento': getattr(t, 'numero_compartimento', None) or getattr(t, 'numero_compartimentos', None),
                            'gavetas': getattr(t, 'gavetas', None) or None,
                            'nome': getattr(t, 'nome', None) or getattr(t, 'tanque_nome', None),
                            'tanque_nome': getattr(t, 'tanque_nome', None) or getattr(t, 'nome', None),
                        })
                except Exception:
                    pass
            except Exception:
                pass

        # If backend payload didn't include tanques, try to load from DB as fallback
        if (not tanques_list) and rdo_id:
            try:
                qs = RdoTanque.objects.filter(rdo_id=rdo_id).order_by('tanque_codigo')
                tl = []
                for t in qs:
                        tl.append({
                        'id': getattr(t, 'id', None),
                        'codigo': getattr(t, 'tanque_codigo', None),
                        'tanque_codigo': getattr(t, 'tanque_codigo', None),
                        'volume': getattr(t, 'volume_tanque_exec', None) or getattr(t, 'volume', None),
                        'volume_tanque_exec': getattr(t, 'volume_tanque_exec', None),
                        'patamar': getattr(t, 'patamar', None) or getattr(t, 'patamares', None),
                        'patamares': getattr(t, 'patamar', None) or getattr(t, 'patamares', None),
                        'tipo_tanque': getattr(t, 'tipo_tanque', None) or getattr(t, 'tipo', None),
                        'tipo': getattr(t, 'tipo_tanque', None) or getattr(t, 'tipo', None),
                        'numero_compartimentos': getattr(t, 'numero_compartimento', None) or getattr(t, 'numero_compartimentos', None),
                        'numero_compartimento': getattr(t, 'numero_compartimento', None),
                        'gavetas': getattr(t, 'gavetas', None) or None,
                        'nome': getattr(t, 'nome', None) or getattr(t, 'tanque_nome', None),
                        'bombeio': getattr(t, 'bombeio', None),
                        'total_liquido': getattr(t, 'total_liquido', None),
                        'sentido_limpeza': getattr(t, 'sentido_limpeza', None),
                        'sentido_label': (lambda v: ('Vante > Ré' if _canonicalize_sentido(v) == 'vante > ré' else ('Ré > Vante' if _canonicalize_sentido(v) == 'ré > vante' else ('Bombordo > Boreste' if _canonicalize_sentido(v) == 'bombordo > boreste' else ('Boreste < Bombordo' if _canonicalize_sentido(v) == 'boreste < bombordo' else None)))))(getattr(t, 'sentido_limpeza', None)),
                        'sentido': (lambda v: (_canonicalize_sentido(v) or getattr(t, 'sentido_limpeza', None)))(getattr(t, 'sentido_limpeza', None)),
                    })
                if tl:
                    tanques_list = tl
            except Exception:
                tanques_list = tanques_list or []
        context['tanques'] = tanques_list
        # também reflita nos dados de rdo para que templates que usam rdo.tanques vejam a versão enriquecida
        try:
            rdo_payload['tanques'] = tanques_list
        except Exception:
            pass
    except Exception:
        context['tanques'] = rdo_payload.get('tanques') or []
    # DEBUG: log rdo payload / tanques to help diagnose missing per-tank fields
    try:
        logger = logging.getLogger(__name__)
        # Log top-level keys and a compact json of tanks for easier inspection in server logs
        try:
            logger.debug('rdo_page - rdo_payload keys: %s', list(rdo_payload.keys()))
        except Exception:
            logger.debug('rdo_page - unable to list rdo_payload keys')
        try:
            # use existing JSON alias `_json` if present in module
            tanks_json = _json.dumps(context.get('tanques', []), ensure_ascii=False)
        except Exception:
            try:
                import json as _tmp_json
                tanks_json = _tmp_json.dumps(context.get('tanques', []), ensure_ascii=False)
            except Exception:
                tanks_json = str(context.get('tanques', []))
        logger.debug('rdo_page - tanques payload: %s', tanks_json)
    except Exception:
        # never fail the page render due to logging
        pass

    return render(request, 'rdo_page.html', context)


@login_required(login_url='/login/')
@require_GET
def rdo_pdf(request, rdo_id):
    """Gera um PDF do RDO via WeasyPrint (se disponível)."""
    try:
        from weasyprint import HTML
    except Exception:
        return HttpResponse(
            'Exportação para PDF indisponível (WeasyPrint não instalado).',
            status=501,
            content_type='text/plain; charset=utf-8'
        )

    # Reaproveita mesma montagem de contexto de rdo_print
    # (duplicando lógica mínima para evitar acoplamento à resposta HttpResponse de rdo_print)
    rdo_payload = {}
    try:
        jr = rdo_detail(request, rdo_id)
        if getattr(jr, 'status_code', 500) == 200:
            data = _json.loads(jr.content.decode('utf-8'))
            if data.get('success'):
                rdo_payload = data.get('rdo', {}) or {}
    except Exception:
        rdo_payload = {}

    # Data formatada
    try:
        if rdo_payload.get('data'):
            from datetime import datetime
            dt = datetime.fromisoformat(str(rdo_payload['data']).replace('Z','').replace('z',''))
            rdo_payload['data_fmt'] = dt.strftime('%d/%m/%Y')
        else:
            rdo_payload['data_fmt'] = ''
    except Exception:
        rdo_payload['data_fmt'] = rdo_payload.get('data', '')

    # Normalizar chaves em minúsculas (compat com templates que usam nomes lower-case)
    try:
        for k in list(rdo_payload.keys()):
            lk = k.lower()
            if lk not in rdo_payload:
                rdo_payload[lk] = rdo_payload.get(k)
    except Exception:
        pass

    # Equipe rows / EC / fotos
    equipe_rows, ec_entradas, ec_saidas, fotos_padded = [], [], [], []
    try:
        equipe = rdo_payload.get('equipe') or []
        # normalizar chaves dos membros para evitar falhas no template (ex.: nome_completo)
        if isinstance(equipe, list):
            for m in equipe:
                if not isinstance(m, dict):
                    continue
                m['nome_completo'] = m.get('nome_completo') or m.get('nome') or m.get('display_name') or ''
                m['funcao'] = m.get('funcao') or m.get('funcao_label') or m.get('role') or m.get('funcao_nome') or ''
                m['funcao_label'] = m.get('funcao_label') or m.get('funcao') or m.get('funcao_nome') or ''
                m['funcao_nome'] = m.get('funcao_nome') or m.get('funcao') or m.get('funcao_label') or ''
                m['role'] = m.get('role') or m.get('funcao') or m.get('funcao_label') or m.get('funcao_nome') or ''
                m['name'] = m.get('name') or m.get('nome') or m.get('nome_completo') or ''
                m['display_name'] = m.get('display_name') or m.get('nome_completo') or m.get('name') or ''
                if 'em_servico' not in m:
                    m['em_servico'] = bool(m.get('ativo') or m.get('emServico'))
            for i in range(0, len(equipe), 3):
                chunk = equipe[i:i+3]
                any_active = any(bool(m.get('em_servico') or m.get('ativo') or m.get('emServico')) for m in chunk)
                while len(chunk) < 3:
                    chunk.append({})
                equipe_rows.append({ 'members': chunk, 'em_servico': any_active })
        ec = rdo_payload.get('ec_times') or {}
        for idx in range(1, 7):
            ec_entradas.append(ec.get(f'entrada_{idx}', ''))
            ec_saidas.append(ec.get(f'saida_{idx}', ''))
        fotos = rdo_payload.get('fotos') or []
        if isinstance(fotos, list):
            fotos_padded = fotos[:5]
            while len(fotos_padded) < 5:
                fotos_padded.append(None)
        else:
            fotos_padded = [None, None, None, None, None]
    except Exception:
        fotos_padded = [None, None, None, None, None]

    # Renderiza HTML do template
    html_str = render_to_string('rdo_print.html', {
        'rdo': rdo_payload,
        'equipe_rows': equipe_rows,
        'ec_entradas': ec_entradas,
        'ec_saidas': ec_saidas,
        'fotos_padded': fotos_padded,
        'inline_css': _get_rdo_inline_css(),
    }, request=request)

    # Gera PDF
    base_url = request.build_absolute_uri('/')
    try:
        pdf_bytes = HTML(string=html_str, base_url=base_url).write_pdf()
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.exception('Falha ao gerar PDF via WeasyPrint')
        # Retornar mensagem simples para o cliente; o log terá o traceback
        return HttpResponse(
            'Falha ao gerar PDF. Verifique os logs do servidor para mais detalhes.',
            status=500,
            content_type='text/plain; charset=utf-8'
        )

    filename = f"RDO_{rdo_payload.get('rdo') or rdo_id}.pdf"
    resp = HttpResponse(pdf_bytes, content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp


def _format_ec_time_value(value):
    try:
        if value is None:
            return None
        if isinstance(value, dt_time):
            return value.strftime('%H:%M')
        if isinstance(value, datetime):
            return value.strftime('%H:%M')
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return None
            for fmt in ('%H:%M', '%H:%M:%S'):
                try:
                    parsed = datetime.strptime(s, fmt)
                    return parsed.strftime('%H:%M')
                except Exception:
                    continue
            return s
        # tentar converter outros tipos (ex.: números) para string
        return str(value)
    except Exception:
        return None


def _normalize_ec_field_to_list(val):
    try:
        if val is None:
            return []
        if isinstance(val, (list, tuple)):
            return [v for v in (_format_ec_time_value(item) for item in val) if v]
        if isinstance(val, str):
            s = val.strip()
            if not s:
                return []
            if s.startswith('['):
                try:
                    parsed = json.loads(s)
                    return [v for v in (_format_ec_time_value(item) for item in parsed) if v]
                except Exception:
                    pass
            segments = [seg.strip() for seg in s.replace(';', '\n').splitlines() if seg.strip()]
            return [v for v in (_format_ec_time_value(seg) for seg in segments) if v]
        formatted = _format_ec_time_value(val)
        return [formatted] if formatted else []
    except Exception:
        return []


def _parse_time_to_minutes(t):
    """Accepts a time object or a 'HH:MM' string and returns minutes since midnight, or None."""
    if t is None:
        return None
    try:
        # Se a string for vazia ou None, retorna None
        if isinstance(t, str):
            s = t.strip()
            if not s:
                return None
            parts = s.split(':')
            if len(parts) >= 2:
                h = int(parts[0]); m = int(parts[1]); return h * 60 + m
            return None
        # time/datetime
        try:
            h = t.hour; m = t.minute; return h * 60 + m
        except Exception:
            return None
    except Exception:
        return None


def compute_rdo_aggregates(rdo_obj, atividades_payload, ec_times):
    """Compute aggregate totals in minutes similar to models.RDO.save().
    Returns dict with keys used by frontend.
    """
    # total_atividade: soma de duração (em minutos) de todas as atividades com início e fim
    total_atividade = 0
    for at in (atividades_payload or []):
        try:
            ini = _parse_time_to_minutes(at.get('inicio'))
            fim = _parse_time_to_minutes(at.get('fim'))
            if ini is not None and fim is not None and fim >= ini:
                total_atividade += (fim - ini)
        except Exception:
            continue

    # total_confinado: tenta calcular a partir dos campos entrada_confinado e saida_confinado do modelo
    total_confinado = 0
    try:
        ent = getattr(rdo_obj, 'entrada_confinado', None)
        sai = getattr(rdo_obj, 'saida_confinado', None)
        ent_m = _parse_time_to_minutes(ent)
        sai_m = _parse_time_to_minutes(sai)
        if ent_m is not None and sai_m is not None and sai_m >= ent_m:
            total_confinado = sai_m - ent_m
        else:
            if isinstance(ec_times, dict):
                e1 = _parse_time_to_minutes(ec_times.get('entrada_1'))
                s1 = _parse_time_to_minutes(ec_times.get('saida_1'))
                if e1 is not None and s1 is not None and s1 >= e1:
                    total_confinado = s1 - e1
    except Exception:
        total_confinado = 0

    # total_abertura_pt: soma (minutos) das atividades cuja chave é 'abertura pt'
    total_abertura_pt = 0
    for at in (atividades_payload or []):
        try:
            if (at.get('atividade') or '').strip().lower() == 'abertura pt':
                ini = _parse_time_to_minutes(at.get('inicio'))
                fim = _parse_time_to_minutes(at.get('fim'))
                if ini is not None and fim is not None and fim >= ini:
                    total_abertura_pt += (fim - ini)
        except Exception:
            continue

    # Atividades efetivas (models.py)
    ATIVIDADES_EFETIVAS = [
        'Acesso ao tanque',
        'avaliação inicial da área de trabalho',
        'bombeio',
        'instalação/preparação/montagem',
        'desmobilização do material - dentro do tanque',
        'desmobilização do material - fora do tanque',
        'mobilização de material - dentro do tanque',
        'mobilização de material - fora do tanque',
        'limpeza e higienização de coifa',
        'limpeza de dutos',
        'coleta e análise de ar',
        'cambagem',
        'içamento',
        'limpeza fina',
        'manutenção de equipamentos - dentro do tanque',
        'manutenção de equipamentos - fora do tanque',
        'jateamento',
    ]

    total_atividades_efetivas = 0
    for at in (atividades_payload or []):
        try:
            if (at.get('atividade') or '').strip().lower() in ATIVIDADES_EFETIVAS:
                ini = _parse_time_to_minutes(at.get('inicio'))
                fim = _parse_time_to_minutes(at.get('fim'))
                if ini is not None and fim is not None and fim >= ini:
                    total_atividades_efetivas += (fim - ini)
        except Exception:
            continue

    # total_n_efetivo_confinado: preferencia para campo no modelo, senão 0
    total_n_efetivo_confinado = 0
    try:
        val = getattr(rdo_obj, 'total_n_efetivo_confinado', None)
        if isinstance(val, int):
            total_n_efetivo_confinado = val
        else:
           
            try:
                total_n_efetivo_confinado = int(val) if val is not None else 0
            except Exception:
                total_n_efetivo_confinado = 0
    except Exception:
        total_n_efetivo_confinado = 0

    total_atividades_nao_efetivas_fora = max(0, total_atividade - total_atividades_efetivas - (total_n_efetivo_confinado or 0))

    return {
        'total_atividade_min': total_atividade,
        'total_confinado_min': total_confinado,
        'total_abertura_pt_min': total_abertura_pt,
        'total_atividades_efetivas_min': total_atividades_efetivas,
        'total_atividades_nao_efetivas_fora_min': total_atividades_nao_efetivas_fora,
        'total_n_efetivo_confinado_min': total_n_efetivo_confinado,
    }
    
            # Persistir listas completas de entrada/saida em campo JSON-text (se o modelo suportar)
    try:
        import json
        entrada_list_final = entrada_list or []
        saida_list_final = saida_list or []
        # Normalizar valores formatados
        entrada_norm = [_format_ec_time_value(v) for v in entrada_list_final if _format_ec_time_value(v) is not None]
        saida_norm = [_format_ec_time_value(v) for v in saida_list_final if _format_ec_time_value(v) is not None]
        ec_payload_obj = {'entrada': entrada_norm, 'saida': saida_norm}
        if hasattr(rdo_obj, 'ec_times_json'):
            try:
                rdo_obj.ec_times_json = json.dumps(ec_payload_obj, ensure_ascii=False)
                _safe_save_global(rdo_obj)
            except Exception:
                pass
    except Exception:
        pass
    
@login_required(login_url='/login/')
@require_POST
def translate_preview(request):
    """Endpoint leve para pré-visualização de tradução PT->EN em tempo (quase) real.
    Recebe 'text' via POST (application/x-www-form-urlencoded ou multipart) ou JSON body {'text': '...'}
    Retorna JSON {success: bool, en: str}
    Não persiste nada; apenas traduz se houver conteúdo (>2 chars) senão retorna vazio.
    """
    text = None

    if 'text' in request.POST:
        text = request.POST.get('text')
    else:
        import json
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
            text = payload.get('text')
        except Exception:
            text = None

    if text is None:
        return JsonResponse({'success': True, 'en': ''})
    clean = text.strip()
    if len(clean) < 3:
        return JsonResponse({'success': True, 'en': ''})
    try:
        from deep_translator import GoogleTranslator
        en = GoogleTranslator(source='pt', target='en').translate(clean)
    except Exception:
        logger = logging.getLogger(__name__)
        logger.exception('Erro ao traduzir texto no translate_preview')
        return JsonResponse({'success': False, 'en': '', 'error': 'Falha tradução'} , status=200)
    return JsonResponse({'success': True, 'en': en})


@login_required(login_url='/login/')
@require_GET
def find_rdo_by_number(request):
    """Procura um RDO pelo número exibido (rdo_contagem) e retorna o id.
    Query params: ?rdo=<number>
    Retorna JSON { success: bool, id: int|null, rdo: str|null, os: str|null }
    """
    try:
        rdo_val = request.GET.get('rdo') or request.GET.get('rdo_contagem')
        if not rdo_val:
            return JsonResponse({'success': False, 'error': 'missing rdo param'}, status=400)
        # tentar buscar por rdo_contagem (string) primeiro
        qs = RDO.objects.filter(rdo_contagem=str(rdo_val))
        # fallback: também tentar por id numérico
        if not qs.exists():
            try:
                nid = int(rdo_val)
                qs = RDO.objects.filter(id=nid)
            except Exception:
                qs = RDO.objects.none()
        rdo_obj = qs.order_by('-id').first()
        if not rdo_obj:
            return JsonResponse({'success': False, 'id': None})
        os_num = None
        try:
            os_num = getattr(rdo_obj.ordem_servico, 'numero_os', None)
        except Exception:
            os_num = None
        return JsonResponse({'success': True, 'id': rdo_obj.id, 'rdo': getattr(rdo_obj, 'rdo_contagem', None), 'os': os_num})
    except Exception:
        import logging
        logging.exception('find_rdo_by_number failed')
        return JsonResponse({'success': False, 'error': 'internal error'}, status=500)


@login_required(login_url='/login/')
@require_POST
def gerar_atividade(request):
    return JsonResponse({'success': False, 'error': 'Endpoint desativado. Use a nova API para criar RDOs.'}, status=410)

@login_required(login_url='/login/')
@require_GET
def lookup_os(request, os_id):
    try:
        os_obj = OrdemServico.objects.get(pk=os_id)
    except OrdemServico.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'OS não encontrada.'}, status=404)
    return JsonResponse({
        'success': True,
        'data': {
            'id': os_obj.id,
            'numero_os': os_obj.numero_os,
            'empresa': os_obj.cliente,
            'unidade': os_obj.unidade,
            'supervisor': os_obj.supervisor,
        }
    })


@login_required(login_url='/login/')
@require_GET
def tanks_for_os(request, os_id):
    """Retorna tanques associados a uma Ordem de Serviço (OS) para uso em autocomplete.

    Query params:
      - q: string opcional para filtrar por `tanque_codigo` ou nome

    Response JSON: { success: True, results: [ {id, tanque_codigo, numero_compartimentos, nome }, ... ] }
    """
    logger = logging.getLogger(__name__)
    try:
        q = (request.GET.get('q') or '').strip()
        # paginação: page (1-based) e page_size (limitado a 5)
        try:
            page = int(request.GET.get('page', 1))
        except Exception:
            page = 1
        try:
            page_size = int(request.GET.get('page_size', 5))
        except Exception:
            page_size = 5
        # garantir limites: mínimo 1, máximo 5 (solicitado)
        if page_size < 1:
            page_size = 1
        if page_size > 5:
            page_size = 5

        # Buscar RdoTanque vinculados a RDOs da OS (use distinct para evitar duplicados)
        tanks_qs = RdoTanque.objects.filter(rdo__ordem_servico__id=os_id)
        if q:
            tanks_qs = tanks_qs.filter(
                Q(tanque_codigo__icontains=q) |
                Q(nome__icontains=q) |
                Q(nome_tanque__icontains=q)
            )
        tanks_qs = tanks_qs.order_by('tanque_codigo').distinct()

        paginator = Paginator(tanks_qs, page_size)
        try:
            page_obj = paginator.page(page)
        except Exception:
            page_obj = paginator.page(1)

        results = []
        for t in page_obj.object_list:
            results.append({
                'id': getattr(t, 'id', None),
                'tanque_codigo': getattr(t, 'tanque_codigo', None),
                'numero_compartimentos': getattr(t, 'numero_compartimentos', None),
                'nome': getattr(t, 'nome', None) or getattr(t, 'nome_tanque', None) or None,
            })

        return JsonResponse({
            'success': True,
            'results': results,
            'page': page_obj.number,
            'page_size': page_size,
            'total': paginator.count,
            'total_pages': paginator.num_pages,
        })
    except Exception:
        logger.exception('Falha em tanks_for_os')
        return JsonResponse({'success': False, 'error': 'internal error'}, status=500)


@login_required(login_url='/login/')
@require_GET
def rdo_tank_detail(request, codigo):
    """Endpoint read-only que retorna metadados e acumulados de um tanque identificado por `codigo`.

    URL: /api/rdo/tank/<codigo>/
    Retorna JSON: { success: True, tank: { id, tanque_codigo, nome_tanque, tipo_tanque, numero_compartimentos, gavetas, patamares, volume_tanque_exec, servico_exec, metodo_exec, espaco_confinado, acumulados: {...}, created_at, updated_at } }
    """
    logger = logging.getLogger(__name__)
    try:
        codigo_q = (codigo or '').strip()
        if not codigo_q:
            return JsonResponse({'success': False, 'error': 'missing codigo'}, status=400)

        # 1) Tentar obter metadados diretamente do cadastro de Tanque (fonte canônica)
        tanq_model = None
        tanq_obj = None
        try:
            from django.apps import apps as _apps
            tanq_model = _apps.get_model('GO', 'Tanque')
        except Exception:
            tanq_model = None
        if tanq_model is not None:
            try:
                tanq_obj = tanq_model.objects.filter(codigo__iexact=codigo_q).first()
            except Exception:
                tanq_obj = None

        # 2) Buscar também o último RdoTanque conhecido para esse código (dados operacionais)
        tank_rt = None
        try:
            tank_rt = RdoTanque.objects.filter(tanque_codigo__iexact=codigo_q).order_by('-rdo__data', '-id').first()
        except Exception:
            tank_rt = None

        # Se existir um RdoTanque, garantir que cumulativos ausentes sejam
        # recomputados de forma conservadora (somente quando faltando). Isso
        # cobre dados antigos criados antes da regra no model.save(), evitando
        # payloads incompletos no frontend.
        try:
            if tank_rt is not None:
                before_tuple = (
                    getattr(tank_rt, 'ensacamento_cumulativo', None),
                    getattr(tank_rt, 'icamento_cumulativo', None),
                    getattr(tank_rt, 'cambagem_cumulativo', None),
                    getattr(tank_rt, 'percentual_limpeza_cumulativo', None),
                    getattr(tank_rt, 'percentual_limpeza_fina_cumulativo', None),
                    getattr(tank_rt, 'limpeza_fina_cumulativa', None),
                    getattr(tank_rt, 'limpeza_mecanizada_cumulativa', None),
                )
                try:
                    tank_rt.recompute_metrics(only_when_missing=True)
                except Exception:
                    pass
                after_tuple = (
                    getattr(tank_rt, 'ensacamento_cumulativo', None),
                    getattr(tank_rt, 'icamento_cumulativo', None),
                    getattr(tank_rt, 'cambagem_cumulativo', None),
                    getattr(tank_rt, 'percentual_limpeza_cumulativo', None),
                    getattr(tank_rt, 'percentual_limpeza_fina_cumulativo', None),
                    getattr(tank_rt, 'limpeza_fina_cumulativa', None),
                    getattr(tank_rt, 'limpeza_mecanizada_cumulativa', None),
                )
                if after_tuple != before_tuple:
                    try:
                        _safe_save_global(tank_rt)
                    except Exception:
                        # fallback para save simples caso helper não esteja disponível
                        try:
                            tank_rt.save()
                        except Exception:
                            pass
        except Exception:
            pass

        if not tanq_obj and not tank_rt:
            return JsonResponse({'success': False, 'error': 'tank not found'}, status=404)

        # Montar payload base a partir do Tanque (se existir)
        payload = {
            'id': getattr(tanq_obj, 'id', None) or (getattr(tank_rt, 'id', None) if tank_rt else None),
            'tanque_codigo': getattr(tanq_obj, 'codigo', None) or (getattr(tank_rt, 'tanque_codigo', None) if tank_rt else None),
            'nome_tanque': getattr(tanq_obj, 'nome', None) or (getattr(tank_rt, 'nome_tanque', None) if tank_rt else None),
            'tipo_tanque': getattr(tanq_obj, 'tipo', None) or (getattr(tank_rt, 'tipo_tanque', None) if tank_rt else None),
            'numero_compartimentos': getattr(tanq_obj, 'numero_compartimentos', None) or (getattr(tank_rt, 'numero_compartimentos', None) if tank_rt else None),
            'gavetas': getattr(tanq_obj, 'gavetas', None) or (getattr(tank_rt, 'gavetas', None) if tank_rt else None),
            'patamares': getattr(tanq_obj, 'patamares', None) or (getattr(tank_rt, 'patamares', None) if tank_rt else None),
            'volume_tanque_exec': (str(getattr(tanq_obj, 'volume', None)) if getattr(tanq_obj, 'volume', None) is not None else (str(getattr(tank_rt, 'volume_tanque_exec', None)) if tank_rt and getattr(tank_rt, 'volume_tanque_exec', None) is not None else None)),
            'servico_exec': getattr(tank_rt, 'servico_exec', None) if tank_rt else None,
            'metodo_exec': getattr(tank_rt, 'metodo_exec', None) if tank_rt else None,
            'espaco_confinado': getattr(tank_rt, 'espaco_confinado', None) if tank_rt else None,
            # se houver relação de unidade no Tanque, expor o id (auto-preenchimento no frontend)
            'unidade_id': getattr(tanq_obj, 'unidade_id', None) if tanq_obj is not None else None,
        }

        # Acumulados/percentuais mais recentes (baseado no último RdoTanque)
        acumulados = {
            'percentual_limpeza_cumulativo': getattr(tank_rt, 'percentual_limpeza_cumulativo', None) if tank_rt else None,
            'percentual_limpeza_fina_cumulativo': getattr(tank_rt, 'percentual_limpeza_fina_cumulativo', None) if tank_rt else None,
            'percentual_ensacamento': getattr(tank_rt, 'percentual_ensacamento', None) if tank_rt else None,
            'percentual_icamento': getattr(tank_rt, 'percentual_icamento', None) if tank_rt else None,
            'percentual_cambagem': getattr(tank_rt, 'percentual_cambagem', None) if tank_rt else None,
            'percentual_avanco': getattr(tank_rt, 'percentual_avanco', None) if tank_rt else None,
        }

        # Completar payload com dados operacionais do último RdoTanque (se existir)
        payload.update({
            'acumulados': acumulados,
            'ensacamento_prev': getattr(tank_rt, 'ensacamento_prev', None) if tank_rt else None,
            'icamento_prev': getattr(tank_rt, 'icamento_prev', None) if tank_rt else None,
            'cambagem_prev': getattr(tank_rt, 'cambagem_prev', None) if tank_rt else None,
            # Cumulativos operacionais por tanque (soma dos diários anteriores + atual quando aplicável)
            'ensacamento_cumulativo': getattr(tank_rt, 'ensacamento_cumulativo', None) if tank_rt else None,
            'icamento_cumulativo': getattr(tank_rt, 'icamento_cumulativo', None) if tank_rt else None,
            'cambagem_cumulativo': getattr(tank_rt, 'cambagem_cumulativo', None) if tank_rt else None,
            # Novos: cumulativos de resíduos por tanque
            'total_liquido_cumulativo': getattr(tank_rt, 'total_liquido_cumulativo', None) if tank_rt else None,
            'residuos_solidos_cumulativo': getattr(tank_rt, 'residuos_solidos_cumulativo', None) if tank_rt else None,
            # Aliases esperados pelo frontend (inputs *_acu)
            'total_liquido_acu': getattr(tank_rt, 'total_liquido_cumulativo', None) if tank_rt else None,
            'residuos_solidos_acu': getattr(tank_rt, 'residuos_solidos_cumulativo', None) if tank_rt else None,
            # Limpeza fina cumulativa (por compatibilidade/visão rápida)
            'limpeza_fina_cumulativa': getattr(tank_rt, 'limpeza_fina_cumulativa', None) if tank_rt else None,
            # NOTE: per-tank canonical limpeza fields intentionally omitted from payload (kept in model only)
            # Legacy (mecanizada) ainda exposto por compatibilidade
            'limpeza_mecanizada_diaria': getattr(tank_rt, 'limpeza_mecanizada_diaria', None) if tank_rt else None,
            'limpeza_mecanizada_cumulativa': getattr(tank_rt, 'limpeza_mecanizada_cumulativa', None) if tank_rt else None,
            'percentual_limpeza_fina': getattr(tank_rt, 'percentual_limpeza_fina', None) if tank_rt else None,
            'percentual_limpeza_fina_cumulativo': getattr(tank_rt, 'percentual_limpeza_fina_cumulativo', None) if tank_rt else None,
            # Fine daily (mantido) e novo campo cumulativo com nome distinto
            'limpeza_fina_diaria': getattr(tank_rt, 'limpeza_fina_diaria', None) if tank_rt else None,
            'compartimentos_avanco_json': getattr(tank_rt, 'compartimentos_avanco_json', None) if tank_rt else None,
            'created_at': (tank_rt.created_at.isoformat() if tank_rt and getattr(tank_rt, 'created_at', None) else None),
            'updated_at': (tank_rt.updated_at.isoformat() if tank_rt and getattr(tank_rt, 'updated_at', None) else None),
        })

        return JsonResponse({'success': True, 'tank': payload})
    except Exception:
        logger.exception('Falha em rdo_tank_detail')
        return JsonResponse({'success': False, 'error': 'internal error'}, status=500)


@login_required(login_url='/login/')
@require_GET
def rdo_detail(request, rdo_id):
    """Retorna os dados do RDO em JSON para preencher o modal de edição (supervisor)."""
    try:
        rdo_obj = RDO.objects.select_related('ordem_servico').get(pk=rdo_id)
    except RDO.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'RDO não encontrado.'}, status=404)

    # Restrição de acesso: se usuário for do grupo Supervisor, só pode acessar RDOs
    # ligados a OS cujo supervisor é o próprio usuário
    try:
        is_supervisor_user = (hasattr(request, 'user') and request.user.is_authenticated and request.user.groups.filter(name='Supervisor').exists())
        if is_supervisor_user:
            ordem = getattr(rdo_obj, 'ordem_servico', None)
            sup = getattr(ordem, 'supervisor', None) if ordem else None
            if sup is None or sup != request.user:
                # Permitir override por usuários selecionados (ex.: staff/superuser ou grupos configuráveis)
                try:
                    from django.conf import settings as _settings
                    allowed_override = False
                    # superuser/staff têm permissão para abrir o modal mesmo quando não forem o supervisor
                    if getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False):
                        allowed_override = True
                    # grupos configuráveis via settings.RDO_DETAIL_OVERRIDE_GROUPS (lista de nomes de grupos)
                    else:
                        try:
                            grp_names = getattr(_settings, 'RDO_DETAIL_OVERRIDE_GROUPS', []) or []
                            for g in grp_names:
                                if request.user.groups.filter(name=g).exists():
                                    allowed_override = True
                                    break
                        except Exception:
                            allowed_override = False
                    if not allowed_override:
                        return JsonResponse({'success': False, 'error': 'RDO não encontrado.'}, status=404)
                    # quando override permitido, permitimos continuar e retornar o payload vazio/parcial
                except Exception:
                    return JsonResponse({'success': False, 'error': 'RDO não encontrado.'}, status=404)
    except Exception:
        # Em caso de erro ao checar permissão, negar acesso
        return JsonResponse({'success': False, 'error': 'RDO não encontrado.'}, status=404)

    # Garantir que a Data do RDO fique fixa: se ainda não houver valor, define a data de hoje e persiste
    try:
        if not getattr(rdo_obj, 'data', None):
            rdo_obj.data = datetime.today().date()
            try:
                rdo_obj.save(update_fields=['data'])
            except Exception:
                # se update_fields falhar (ex.: campos obrigatórios), tenta save completo
                _safe_save_global(rdo_obj)
    except Exception:
        pass

    ordem = getattr(rdo_obj, 'ordem_servico', None)
    # Serializa atividades do RDO para retorno
    atividades_payload = []
    for atv in rdo_obj.atividades_rdo.all():
        atividades_payload.append({
            'ordem': atv.ordem,
            'atividade': atv.atividade,
            'atividade_label': atv.get_atividade_display(),
            'inicio': atv.inicio.strftime('%H:%M') if atv.inicio else None,
            'fim': atv.fim.strftime('%H:%M') if atv.fim else None,
            'comentario_pt': atv.comentario_pt,
            'comentario_en': atv.comentario_en,
        })
    # Serializa fotos (campo consolidado) em lista de URLs/paths
    fotos_list = []
    try:
        fotos_field = getattr(rdo_obj, 'fotos', None)

        def _coerce_fotos(value):
            if value is None:
                return []
            if isinstance(value, (list, tuple)):
                out = []
                for it in value:
                    if isinstance(it, dict):
                        # tentar chaves comuns
                        for k in ('url','src','path','name','file','arquivo'):
                            if it.get(k):
                                out.append(str(it.get(k)))
                                break
                    else:
                        out.append(it)
                return out
            if hasattr(value, 'name'):
                return _coerce_fotos(getattr(value, 'name', None))
            if isinstance(value, str):
                s = value.strip()
                if not s:
                    return []
                if s.startswith('['):
                    try:
                        parsed = json.loads(s)
                        if isinstance(parsed, (list, tuple)):
                            return _coerce_fotos(list(parsed))
                    except Exception:
                        return [ln for ln in s.splitlines() if ln.strip()]
                return [ln for ln in s.splitlines() if ln.strip()]
            return []

        fotos_list = _coerce_fotos(fotos_field)
    except Exception:
        fotos_list = []

    # Normalizar URLs para fotos existentes, preferindo o alias público '/fotos_rdo/'
    fotos_urls = []

    def _absolute_from_relative(rel_value):
        rel_clean = ('/' + rel_value.lstrip('/')) if rel_value else ''
        candidate = rel_clean or ''
        if not candidate:
            return ''
        try:
            return request.build_absolute_uri(candidate)
        except Exception:
            try:
                origin = request.build_absolute_uri('/')
                origin = origin[:-1] if origin.endswith('/') else origin
                return origin + candidate
            except Exception:
                return candidate

    for item in fotos_list:
        try:
            if not item:
                continue
            raw = str(item).strip()
            if not raw:
                continue

            # 1) URLs completas permanecem intocadas
            if raw.startswith('http://') or raw.startswith('https://'):
                fotos_urls.append(raw)
                continue
            if raw.startswith('//'):
                scheme = 'https:' if request.is_secure() else 'http:'
                fotos_urls.append(f'{scheme}{raw}')
                continue

            # 2) Normalizar para caminho relativo a MEDIA_ROOT
            try:
                media_root = getattr(settings, 'MEDIA_ROOT', '') or ''
            except Exception:
                media_root = ''

            val = raw
            try:
                # remover prefixos conhecidos para obter caminho relativo
                if val.startswith('/media/'):
                    val = val[len('/media/'):]
                elif val.startswith('/fotos_rdo/'):
                    val = val[len('/fotos_rdo/'):]
                # caminhos absolutos no FS
                if media_root and val.startswith(media_root):
                    val = val[len(media_root):].lstrip('/')
            except Exception:
                pass

            # 3) Resolver arquivo no disco; se não existir, buscar recursivamente por sufixo
            rel_candidate = val.lstrip('/')
            abs_candidate = os.path.join(media_root, rel_candidate) if media_root else None
            try:
                if media_root and (not abs_candidate or not os.path.exists(abs_candidate)):
                    dirname = os.path.dirname(rel_candidate)
                    basename = os.path.basename(rel_candidate)
                    matches = []
                    try:
                        if dirname:
                            matches = glob.glob(os.path.join(media_root, dirname, f'*{basename}'))
                    except Exception:
                        matches = []
                    if not matches:
                        try:
                            matches = glob.glob(os.path.join(media_root, '**', f'*{basename}'), recursive=True)
                        except Exception:
                            matches = []
                    if matches:
                        # escolher arquivo não-zero mais recente; senão primeiro
                        try:
                            matches = sorted(matches, key=lambda p: (os.path.getsize(p) > 0, os.path.getmtime(p)), reverse=True)
                        except Exception:
                            pass
                        chosen = matches[0]
                        rel_candidate = os.path.relpath(chosen, media_root).replace(os.path.sep, '/')
            except Exception:
                pass

            # 4) Construir URL usando alias público '/fotos_rdo/'
            public_path = '/fotos_rdo/' + rel_candidate.lstrip('/')
            fotos_urls.append(_absolute_from_relative(public_path))
        except Exception:
            fotos_urls.append(str(item))

    # Serializa equipe (membros / funcoes) a partir do modelo relacional quando disponível;
    # Fallback inteligente: se não houver membros gravados, inferir nomes a partir de Pessoa.funcao
    # Preferências: (1) Pessoa associada em rdo_obj.pessoas quando função compatível
    # (2) Supervisor da OS para função 'Supervisor'
    # (3) Quando houver exatamente 1 Pessoa para a função no banco, usar essa; caso contrário, deixar em branco
    equipe_list = []
    try:
        # 0) Tentar equipe persistida (novo modelo)
        try:
            rel_members = list(rdo_obj.membros_equipe.all().order_by('ordem', 'id'))
        except Exception:
            rel_members = []
        if rel_members:
            for em in rel_members:
                try:
                    nome = getattr(em.pessoa, 'nome', None) if getattr(em, 'pessoa', None) else getattr(em, 'nome', None)
                except Exception:
                    nome = getattr(em, 'nome', None)
                # tentar obter id da pessoa vinculada (quando existir relação)
                try:
                    pessoa_id = getattr(em, 'pessoa_id', None) or (getattr(em.pessoa, 'id', None) if getattr(em, 'pessoa', None) else None)
                except Exception:
                    pessoa_id = None
                # Normalizar o campo funcao para uma string de nome compatível com get_funcoes
                try:
                    raw_f = getattr(em, 'funcao', None)
                    def _funcao_to_name(val):
                        try:
                            if val is None:
                                return None
                            # se for objeto com atributo 'nome'
                            if hasattr(val, 'nome'):
                                return getattr(val, 'nome')
                            # se for um dict
                            if isinstance(val, dict):
                                return val.get('nome') or val.get('funcao') or None
                            s = str(val).strip()
                            if not s:
                                return None
                            # se for algo no formato 'id|nome', retornar parte direita
                            if '|' in s:
                                parts = s.split('|', 1)
                                return parts[1].strip() or parts[0].strip()
                            # se for dígito, tentar resolver por PK
                            if s.isdigit():
                                try:
                                    fobj = Funcao.objects.filter(pk=int(s)).first()
                                    return getattr(fobj, 'nome', s) if fobj else s
                                except Exception:
                                    return s
                            return s
                        except Exception:
                            return None

                    funcao_name = _funcao_to_name(raw_f)
                except Exception:
                    funcao_name = getattr(em, 'funcao', None)

                equipe_list.append({
                    'nome': nome,
                    'funcao': funcao_name,
                    'em_servico': bool(getattr(em, 'em_servico', True)),
                    'pessoa_id': pessoa_id,
                })
        else:
            # 1) Campos consolidados
            membros_field = getattr(rdo_obj, 'membros', None)
            funcoes_field = getattr(rdo_obj, 'funcoes_list', None) or getattr(rdo_obj, 'funcoes', None)
            # helpers para resolver nomes/descrições
            def _resolve_nome(val):
                try:
                    if val is None:
                        return None
                    if isinstance(val, dict):
                        return val.get('nome') or val.get('nome_completo') or val.get('name') or val.get('display_name') or None
                    s = str(val).strip()
                    if not s:
                        return None
                    # formatos "id|nome"
                    if '|' in s:
                        parts = s.split('|', 1)
                        left, right = parts[0].strip(), parts[1].strip()
                        if left.isdigit():
                            try:
                                p = Pessoa.objects.filter(pk=int(left)).first()
                                return p.nome if p and hasattr(p, 'nome') else (right or s)
                            except Exception:
                                return right or s
                        return right or s
                    # numérico => pk
                    if s.isdigit():
                        try:
                            p = Pessoa.objects.filter(pk=int(s)).first()
                            return p.nome if p and hasattr(p, 'nome') else s
                        except Exception:
                            return s
                    # fallback: retorna string como veio
                    return s
                except Exception:
                    return None

            def _resolve_funcao(val):
                try:
                    if val is None:
                        return None
                    if isinstance(val, dict):
                        return val.get('funcao') or val.get('nome') or val.get('label') or None
                    s = str(val).strip()
                    if not s:
                        return None
                    if '|' in s:
                        parts = s.split('|', 1)
                        left, right = parts[0].strip(), parts[1].strip()
                        if left.isdigit():
                            try:
                                f = Funcao.objects.filter(pk=int(left)).first()
                                return f.nome if f and hasattr(f, 'nome') else (right or s)
                            except Exception:
                                return right or s
                        return right or s
                    if s.isdigit():
                        try:
                            f = Funcao.objects.filter(pk=int(s)).first()
                            return f.nome if f and hasattr(f, 'nome') else s
                        except Exception:
                            return s
                    return s
                except Exception:
                    return None
            if membros_field is None:
                mlist = []
            elif isinstance(membros_field, (list, tuple)):
                mlist = list(membros_field)
            elif isinstance(membros_field, str):
                s = membros_field.strip()
                if s.startswith('['):
                    try:
                        mlist = json.loads(s)
                    except Exception:
                        mlist = [ln for ln in s.splitlines() if ln.strip()]
                else:
                    mlist = [ln for ln in s.splitlines() if ln.strip()]
            else:
                mlist = []

            if funcoes_field is None:
                flist = []
            elif isinstance(funcoes_field, (list, tuple)):
                flist = list(funcoes_field)
            elif isinstance(funcoes_field, str):
                s2 = funcoes_field.strip()
                if s2.startswith('['):
                    try:
                        flist = json.loads(s2)
                    except Exception:
                        flist = [ln for ln in s2.splitlines() if ln.strip()]
                else:
                    flist = [ln for ln in s2.splitlines() if ln.strip()]
            else:
                flist = []

            maxlen = max(len(mlist), len(flist))
            # Helper: tentar extrair pessoa_id quando o valor consolidado vier no formato "id|nome" ou for apenas id
            def _resolve_pessoa_id(val):
                try:
                    if val is None:
                        return None
                    if isinstance(val, dict):
                        # se o dicionário tiver id/ pk
                        for k in ('id', 'pk', 'pessoa_id'):
                            if k in val:
                                try:
                                    return int(val[k])
                                except Exception:
                                    pass
                        # tentar também pela chave 'nome' contendo 'id|nome'
                        candidate = val.get('nome') or val.get('name')
                        if candidate and isinstance(candidate, str) and '|' in candidate:
                            left = candidate.split('|', 1)[0].strip()
                            if left.isdigit():
                                return int(left)
                        return None
                    s = str(val).strip()
                    if not s:
                        return None
                    if '|' in s:
                        left = s.split('|', 1)[0].strip()
                        if left.isdigit():
                            return int(left)
                    if s.isdigit():
                        return int(s)
                    return None
                except Exception:
                    return None

            # Monta lista inicial com possíveis nomes já resolvidos
            for i in range(maxlen):
                raw_nome = (mlist[i] if i < len(mlist) else None)
                raw_func = (flist[i] if i < len(flist) else None)
                equipe_list.append({
                    'nome': _resolve_nome(raw_nome),
                    'funcao': _resolve_funcao(raw_func),
                    'pessoa_id': _resolve_pessoa_id(raw_nome),
                    'em_servico': None,
                })

            # Fallback: completar nomes ausentes com base em Pessoa.funcao
            try:
                # mapear função normalizada -> lista de Pessoas
                from collections import defaultdict
                import unicodedata as _unic

                def _norm_func_label(label):
                    try:
                        if not label:
                            return ''
                        s = str(label)
                        s = _unic.normalize('NFKD', s)
                        s = ''.join([c for c in s if not _unic.combining(c)])
                        s = s.lower().strip()
                        # normalizações simples
                        s = s.replace('  ', ' ')
                        return s
                    except Exception:
                        return str(label or '').lower().strip()
                pessoas_by_func = defaultdict(list)
                try:
                    pessoas_qs = Pessoa.objects.all().only('nome', 'funcao')
                except Exception:
                    pessoas_qs = []
                for p in pessoas_qs:
                    try:
                        fn = (getattr(p, 'funcao', '') or '').strip()
                        if fn:
                            pessoas_by_func[_norm_func_label(fn)].append(p)
                    except Exception:
                        continue

                # Conjunto de nomes já usados para não repetir
                usados = set()
                # Se houver Pessoa vinculada ao RDO (campo pessoas), priorizar quando função coincidir
                try:
                    vinc = getattr(rdo_obj, 'pessoas', None)
                    if vinc is not None:
                        nome_vinc = getattr(vinc, 'nome', None)
                        func_vinc = (getattr(vinc, 'funcao', '') or '').strip()
                        if nome_vinc:
                            usados.add(str(nome_vinc))
                            # se existir uma vaga sem nome para essa função, preenche
                            for item in equipe_list:
                                if (not item.get('nome')) and (_norm_func_label(item.get('funcao')) == _norm_func_label(func_vinc) if func_vinc else False):
                                    item['nome'] = nome_vinc
                                    break
                except Exception:
                    pass

                # Para os demais, quando existir exatamente um Pessoa para a função, usar
                for item in equipe_list:
                    if item.get('nome'):
                        usados.add(str(item['nome']))
                        continue
                    funcao_label = (str(item.get('funcao') or '').strip())
                    if not funcao_label:
                        continue
                    candidates = pessoas_by_func.get(_norm_func_label(funcao_label), [])
                    # Preencher com o primeiro candidato não utilizado; se todos usados, usar o primeiro mesmo
                    chosen = None
                    for cand in candidates:
                        try:
                            nm = getattr(cand, 'nome', None)
                        except Exception:
                            nm = None
                        if nm and nm not in usados:
                            chosen = nm
                            break
                    if not chosen and candidates:
                        try:
                            chosen = getattr(candidates[0], 'nome', None)
                        except Exception:
                            chosen = None
                    if chosen:
                        item['nome'] = chosen
                        usados.add(chosen)

                # Finalmente, se ainda houver vaga de 'Supervisor' sem nome e nenhuma Pessoa para a função,
                # usar o supervisor da OS como último recurso.
                try:
                    for item in equipe_list:
                        if item.get('nome'):
                            continue
                        if _norm_func_label(item.get('funcao')) != _norm_func_label('Supervisor'):
                            continue
                        if pessoas_by_func.get(_norm_func_label('Supervisor')):
                            # já haveria preenchido acima; se chegou aqui, não há Pessoa. Usar usuário.
                            continue
                        ordem_obj = getattr(rdo_obj, 'ordem_servico', None)
                        supervisor_user = getattr(ordem_obj, 'supervisor', None) if ordem_obj else None
                        if supervisor_user:
                            try:
                                sup_name = supervisor_user.get_full_name() or supervisor_user.username or str(supervisor_user)
                            except Exception:
                                sup_name = str(supervisor_user)
                            if sup_name:
                                item['nome'] = sup_name
                                usados.add(sup_name)
                                break
                except Exception:
                    pass
            except Exception:
                # fallback silencioso: manter como está
                pass
    except Exception:
        equipe_list = equipe_list
    # Desserializar entradas/saidas de confinamento (preferir novos campos explícitos; fallback consolidado/legado) e mapear para ec_times
    ec_times = {}
    try:
        entradas = []
        saidas = []
        # 1) Prefer new explicit fields
        try:
            tmp_e = []; tmp_s = []
            for i in range(6):
                tmp_e.append(_format_ec_time_value(getattr(rdo_obj, f'entrada_confinado_{i+1}', None)))
                tmp_s.append(_format_ec_time_value(getattr(rdo_obj, f'saida_confinado_{i+1}', None)))
            if any(tmp_e) or any(tmp_s):
                entradas = tmp_e
                saidas = tmp_s
        except Exception:
            entradas = []
            saidas = []
        # 2) Fallback: lista completa armazenada em ec_times_json
        if not entradas and not saidas:
            try:
                if getattr(rdo_obj, 'ec_times_json', None):
                    import json
                    parsed = json.loads(rdo_obj.ec_times_json)
                    if isinstance(parsed, dict):
                        entradas = parsed.get('entrada') if isinstance(parsed.get('entrada'), list) else []
                        saidas = parsed.get('saida') if isinstance(parsed.get('saida'), list) else []
            except Exception:
                entradas = []
                saidas = []
        # 3) Fallback: legacy single fields
        if not entradas and not saidas:
            entrada_field = getattr(rdo_obj, 'entrada_confinado', None)
            saida_field = getattr(rdo_obj, 'saida_confinado', None)
            entradas = _normalize_ec_field_to_list(entrada_field)
            saidas = _normalize_ec_field_to_list(saida_field)

        for i in range(6):
            ec_times[f'entrada_{i+1}'] = entradas[i] if i < len(entradas) else None
            ec_times[f'saida_{i+1}'] = saidas[i] if i < len(saidas) else None
    except Exception:
        ec_times = {}

    try:
        aggregates = compute_rdo_aggregates(rdo_obj, atividades_payload, ec_times)
    except Exception:
        logging.getLogger(__name__).exception('Falha ao calcular agregados para rdo_detail; retornando payload parcial')
        aggregates = {}
    payload = {
        'id': rdo_obj.id,
        'data': rdo_obj.data.isoformat() if rdo_obj.data else None,
        'data_inicio': rdo_obj.data_inicio.isoformat() if getattr(rdo_obj, 'data_inicio', None) else None,
        'previsao_termino': rdo_obj.previsao_termino.isoformat() if getattr(rdo_obj, 'previsao_termino', None) else None,
        # OrdemServico details (fallbacks)
        'numero_os': ordem.numero_os if ordem else None,
        'empresa': ordem.cliente if ordem else None,
        'unidade': ordem.unidade if ordem else None,
        'embarcacao': getattr(ordem, 'embarcacao', None),
        'rdo': rdo_obj.rdo,
        'turno': rdo_obj.turno,
        'nome_tanque': rdo_obj.nome_tanque,
        'tanque_codigo': rdo_obj.tanque_codigo,
        'tipo_tanque': rdo_obj.tipo_tanque,
        'numero_compartimentos': rdo_obj.numero_compartimentos,
        'volume_tanque_exec': str(rdo_obj.volume_tanque_exec) if rdo_obj.volume_tanque_exec is not None else None,
        'servico_exec': rdo_obj.servico_exec,
        'metodo_exec': rdo_obj.metodo_exec,
        'gavetas': rdo_obj.gavetas,
        'patamares': rdo_obj.patamares,
        'operadores_simultaneos': rdo_obj.operadores_simultaneos,
        'H2S_ppm': str(getattr(rdo_obj, 'h2s_ppm', None)) if getattr(rdo_obj, 'h2s_ppm', None) is not None else None,
        'LEL': str(getattr(rdo_obj, 'lel', None)) if getattr(rdo_obj, 'lel', None) is not None else None,
        'CO_ppm': str(getattr(rdo_obj, 'co_ppm', None)) if getattr(rdo_obj, 'co_ppm', None) is not None else None,
        'O2_percent': str(getattr(rdo_obj, 'o2_percent', None)) if getattr(rdo_obj, 'o2_percent', None) is not None else None,
        'bombeio': (lambda v: (str(v) if v is not None and not isinstance(v, (int, float)) else v))(getattr(rdo_obj, 'bombeio', getattr(rdo_obj, 'quantidade_bombeada', None))),
        'total_liquido': getattr(rdo_obj, 'total_liquido', None),
        # vazão de bombeio (m3/h) - expor campo para frontend/editor
        'vazao_bombeio': (None if getattr(rdo_obj, 'vazao_bombeio', None) is None else (str(rdo_obj.vazao_bombeio) if not isinstance(getattr(rdo_obj, 'vazao_bombeio', None), (int, float)) else getattr(rdo_obj, 'vazao_bombeio'))),
        # aliases e compatibilidade com nomes usados no editor (residuo_liquido, ensacamento_dia, tambores_dia, residuos_solidos, residuos_totais)
        'residuo_liquido': getattr(rdo_obj, 'residuo_liquido', getattr(rdo_obj, 'total_liquido', None)),
        'ensacamento': getattr(rdo_obj, 'ensacamento', None),
        'ensacamento_dia': getattr(rdo_obj, 'ensacamento', None),
        'tambores': getattr(rdo_obj, 'tambores', None),
        'tambores_dia': getattr(rdo_obj, 'tambores', None),
        # sólidos/resíduos (compatibilidade com vários nomes históricos)
        'total_solidos': getattr(rdo_obj, 'total_solidos', None),
        'residuos_solidos': getattr(rdo_obj, 'residuos_solidos', getattr(rdo_obj, 'total_solidos', None)),
        'total_residuos': getattr(rdo_obj, 'total_residuos', None),
        'residuos_totais': getattr(rdo_obj, 'residuos_totais', getattr(rdo_obj, 'total_residuos', None)),
        # Novos campos técnicos / acumulados
        'percentual_avanco': getattr(rdo_obj, 'percentual_avanco', None),
        'percentual_avanco_cumulativo': getattr(rdo_obj, 'percentual_avanco_cumulativo', None),
        'percentual_limpeza': getattr(rdo_obj, 'percentual_limpeza', None),
        'percentual_limpeza_cumulativo': getattr(rdo_obj, 'percentual_limpeza_cumulativo', None),
         # Campos canônicos calculados server-side (expor para o editor/modal)
        'percentual_limpeza_diario': getattr(rdo_obj, 'percentual_limpeza_diario', None),
        'limpeza_mecanizada_diaria': getattr(rdo_obj, 'limpeza_mecanizada_diaria', None),
        # Campos cumulativos canônicos (expor também)
        'percentual_limpeza_diario_cumulativo': getattr(rdo_obj, 'percentual_limpeza_diario_cumulativo', getattr(rdo_obj, 'percentual_limpeza_cumulativo', None)),
        'limpeza_mecanizada_cumulativa': getattr(rdo_obj, 'limpeza_mecanizada_cumulativa', getattr(rdo_obj, 'limpeza_mecanizada_cumulativa', None)),
        'percentual_limpeza_fina': getattr(rdo_obj, 'percentual_limpeza_fina', None),
        'percentual_limpeza_fina_cumulativo': getattr(rdo_obj, 'percentual_limpeza_fina_cumulativo', None),
        'ensacamento_cumulativo': getattr(rdo_obj, 'ensacamento_cumulativo', None),
        'ensacamento_previsao': getattr(rdo_obj, 'ensacamento_previsao', None),
        'percentual_ensacamento': getattr(rdo_obj, 'percentual_ensacamento', None),
        'icamento': getattr(rdo_obj, 'icamento', None),
        'icamento_cumulativo': getattr(rdo_obj, 'icamento_cumulativo', None),
        'icamento_previsao': getattr(rdo_obj, 'icamento_previsao', None),
        'percentual_icamento': getattr(rdo_obj, 'percentual_icamento', None),
        'cambagem': getattr(rdo_obj, 'cambagem', None),
        'cambagem_cumulativo': getattr(rdo_obj, 'cambagem_cumulativo', None),
        'cambagem_previsao': getattr(rdo_obj, 'cambagem_previsao', None),
        'percentual_cambagem': getattr(rdo_obj, 'percentual_cambagem', None),
        'pob': getattr(rdo_obj, 'pob', None),
        'total_hh_cumulativo_real': getattr(rdo_obj, 'total_hh_cumulativo_real', None),
        'hh_disponivel_cumulativo': getattr(rdo_obj, 'hh_disponivel_cumulativo', None),
        'total_hh_frente_real': getattr(rdo_obj, 'total_hh_frente_real', None),
        'ultimo_status': getattr(rdo_obj, 'ultimo_status', None),
    # Novos campos técnicos / acumulados
        'percentual_avanco': getattr(rdo_obj, 'percentual_avanco', None),
        'percentual_avanco_cumulativo': getattr(rdo_obj, 'percentual_avanco_cumulativo', None),
        'total_hh_cumulativo_real': getattr(rdo_obj, 'total_hh_cumulativo_real', None),
        'hh_disponivel_cumulativo': getattr(rdo_obj, 'hh_disponivel_cumulativo', None),
        'total_hh_frente_real': getattr(rdo_obj, 'total_hh_frente_real', None),
        'ultimo_status': getattr(rdo_obj, 'ultimo_status', None),
        'po': getattr(rdo_obj, 'po', None) or getattr(rdo_obj, 'contrato_po', None) or (rdo_obj.ordem_servico.po if getattr(rdo_obj, 'ordem_servico', None) else None),
        'exist_pt': rdo_obj.exist_pt,
        'select_turnos': rdo_obj.select_turnos,
        'pt_manha': rdo_obj.pt_manha,
        'pt_tarde': rdo_obj.pt_tarde,
        'pt_noite': rdo_obj.pt_noite,
        # Campo: ciência das observações contratado (persistido em PT e EN)
        'ciente_observacoes_pt': getattr(rdo_obj, 'ciente_observacoes_pt', None),
        'ciente_observacoes_en': getattr(rdo_obj, 'ciente_observacoes_en', None),
        'observacoes_pt': rdo_obj.observacoes_rdo_pt,
        'observacoes_en': getattr(rdo_obj, 'observacoes_rdo_en', None),
        'planejamento_pt': rdo_obj.planejamento_pt,
        'planejamento_en': getattr(rdo_obj, 'planejamento_en', None),
        'comentario_pt': getattr(rdo_obj, 'comentario_pt', None),
        'comentario_en': getattr(rdo_obj, 'comentario_en', None),
        'atividades': atividades_payload,
        
        'tempo_bomba': (None if not getattr(rdo_obj, 'tempo_uso_bomba', None) else round(rdo_obj.tempo_uso_bomba.total_seconds()/3600, 1)),
        # fotos: URLs normalizadas para uso no frontend
        'fotos': fotos_urls,
        # fotos_raw: conteúdo cru extraído do campo do modelo (útil para diagnóstico de permissões/formato)
        'fotos_raw': fotos_list,
        'equipe': equipe_list,
        # Espaço confinado: expor campo booleano e horários (ec_times) para o editor
        'espaco_confinado': getattr(rdo_obj, 'confinado', None),
        'ec_times': ec_times,
        # incluir cálculos agregados para uso imediato no frontend
        'total_atividade_min': aggregates.get('total_atividade_min'),
        'total_confinado_min': aggregates.get('total_confinado_min'),
        'total_abertura_pt_min': aggregates.get('total_abertura_pt_min'),
        'total_atividades_efetivas_min': aggregates.get('total_atividades_efetivas_min'),
        'total_atividades_nao_efetivas_fora_min': aggregates.get('total_atividades_nao_efetivas_fora_min'),
        'total_n_efetivo_confinado_min': aggregates.get('total_n_efetivo_confinado_min'),
    }

    # Incluir lista de tanques (RdoTanque) relacionados a este RDO para uso pelo editor e pela página
    try:
        tanques_payload = []
        for t in rdo_obj.tanques.all():
            try:
                # Coleta tolerante de campos por-tanque com aliases usados no frontend/template
                def _to_str_or_none(val):
                    try:
                        if val is None:
                            return None
                        return str(val)
                    except Exception:
                        return None

                # Campos base
                _id = getattr(t, 'id', None)
                _codigo = getattr(t, 'tanque_codigo', None)
                _nome = getattr(t, 'nome_tanque', None)
                _num_comp = getattr(t, 'numero_compartimentos', getattr(t, 'numero_compartimento', None))
                _tipo = getattr(t, 'tipo_tanque', getattr(t, 'tipo', None))
                _gavetas = getattr(t, 'gavetas', None)
                _pats = getattr(t, 'patamares', getattr(t, 'patamar', None))
                _vol = getattr(t, 'volume_tanque_exec', getattr(t, 'volume', None))

                # Operacionais / percentuais
                _pld = getattr(t, 'percentual_limpeza_diario', None)
                _plfd = getattr(t, 'percentual_limpeza_fina_diario', None)
                _plc = getattr(t, 'percentual_limpeza_cumulativo', None)
                _plfc = getattr(t, 'percentual_limpeza_fina_cumulativo', None)

                # Sentido (bool ou string) → gerar rótulo legível
                # tentar múltiplos aliases no modelo de tanque
                _sent_raw = None
                for cand in ('sentido_limpeza', 'sentido', 'direcao', 'direcao_limpeza', 'sentido_exec'):
                    try:
                        _val = getattr(t, cand, None)
                        if _val is not None:
                            _sent_raw = _val
                            break
                    except Exception:
                        continue
                if isinstance(_sent_raw, bool):
                    _sent_label = ('Vante para Ré' if _sent_raw else 'Ré para Vante')
                else:
                    _sent_label = _sent_raw

                # Bombeio / vazão acumulada por tanque: também tentar aliases comuns
                _bombeio_val = None
                for cand in ('bombeio', 'quantidade_bombeada', 'quantidade_bombeio', 'bombeio_dia', 'bombeado'):
                    try:
                        v = getattr(t, cand, None)
                        if v is not None:
                            _bombeio_val = v
                            break
                    except Exception:
                        continue

                # Total líquido por tanque (aliases)
                _total_liq = None
                for cand in ('total_liquido', 'total_liquidos', 'total_liquido_dia', 'residuo_liquido'):
                    try:
                        v = getattr(t, cand, None)
                        if v is not None:
                            _total_liq = v
                            break
                    except Exception:
                        continue

                # Valor combinado para coluna "percentuais" da tabela (usar diário mecanizada como default)
                # Se ambos (mecanizada e fina) existirem, exibir como "Mec: X% | Fina: Y%"; senão usar um só.
                if _pld is not None and _plfd is not None:
                    _percentuais_txt = f"Mec: {int(_pld)}% | Fina: {int(_plfd)}%" if isinstance(_pld, (int,float)) and isinstance(_plfd, (int,float)) else f"{_to_str_or_none(_pld)} | {_to_str_or_none(_plfd)}"
                elif _pld is not None:
                    _percentuais_txt = f"{int(_pld)}%" if isinstance(_pld, (int,float)) else _to_str_or_none(_pld)
                elif _plfd is not None:
                    _percentuais_txt = f"{int(_plfd)}%" if isinstance(_plfd, (int,float)) else _to_str_or_none(_plfd)
                else:
                    _percentuais_txt = None

                item = {
                    'id': _id,
                    # Identificação e aliases esperados pelo front
                    'tanque_codigo': _codigo,
                    'codigo': _codigo,
                    'nome_tanque': _nome,
                    'numero_compartimentos': _num_comp,
                    'numero_compartimento': _num_comp,
                    # Configuração do tanque
                    'tipo_tanque': _tipo,
                    'tipo': _tipo,
                    'gavetas': _gavetas,
                    'patamares': _pats,
                    'patamar': _pats,
                    'volume_tanque_exec': _to_str_or_none(_vol),
                    'volume': _to_str_or_none(_vol),
                    # Serviço/ método por tanque (quando existirem no modelo)
                    'servico_exec': getattr(t, 'servico_exec', None),
                    'metodo_exec': getattr(t, 'metodo_exec', None),
                    # Percentuais detalhados
                    'percentual_limpeza_diario': (_to_str_or_none(_pld) if _pld is not None else None),
                    'percentual_limpeza_fina_diario': (_to_str_or_none(_plfd) if _plfd is not None else None),
                    'percentual_limpeza_cumulativo': _plc,
                    'percentual_limpeza_fina_cumulativo': _plfc,
                    # Campo combinado para tabela
                    'percentuais': _percentuais_txt,
                    'percentual': _percentuais_txt,
                    # Sentido (expor token canônico quando possível + label compat)
                    'sentido_limpeza': (lambda v: _canonicalize_sentido(v))( _sent_raw ),
                    'sentido_label': (lambda v: ('Vante > Ré' if _canonicalize_sentido(v) == 'vante > ré' else ('Ré > Vante' if _canonicalize_sentido(v) == 'ré > vante' else ('Bombordo > Boreste' if _canonicalize_sentido(v) == 'bombordo > boreste' else ('Boreste < Bombordo' if _canonicalize_sentido(v) == 'boreste < bombordo' else v)) )))(_sent_raw),
                    'sentido': (lambda v: (_canonicalize_sentido(v) or v))(_sent_raw),
                    # Operacionais por-tanque (se existirem no modelo)
                    'tempo_bomba': getattr(t, 'tempo_bomba', None),
                    'ensacamento_dia': getattr(t, 'ensacamento_dia', None),
                    'icamento_dia': getattr(t, 'icamento_dia', None),
                    'cambagem_dia': getattr(t, 'cambagem_dia', None),
                    'icamento_prev': getattr(t, 'icamento_prev', None),
                    'cambagem_prev': getattr(t, 'cambagem_prev', None),
                    'tambores_dia': getattr(t, 'tambores_dia', None),
                    'residuos_solidos': getattr(t, 'residuos_solidos', None),
                    'residuos_totais': getattr(t, 'residuos_totais', None),
                    # incluir aliases detectados
                    'bombeio': (_bombeio_val if _bombeio_val is not None else None),
                    'total_liquido': (_total_liq if _total_liq is not None else None),
                    'avanco_limpeza': getattr(t, 'avanco_limpeza', None),
                    'avanco_limpeza_fina': getattr(t, 'avanco_limpeza_fina', None),
                    # Atmosfera por tanque (se existirem no modelo)
                    'h2s_ppm': _to_str_or_none(getattr(t, 'h2s_ppm', None)),
                    'lel': _to_str_or_none(getattr(t, 'lel', None)),
                    'co_ppm': _to_str_or_none(getattr(t, 'co_ppm', None)),
                    'o2_percent': _to_str_or_none(getattr(t, 'o2_percent', None)),
                    # Operacionais cumulativos por tanque (novos campos)
                    'ensacamento_cumulativo': getattr(t, 'ensacamento_cumulativo', None),
                    'icamento_cumulativo': getattr(t, 'icamento_cumulativo', None),
                    'cambagem_cumulativo': getattr(t, 'cambagem_cumulativo', None),
                    # Novos: cumulativos de resíduos por tanque (nomes esperados pelo frontend/template)
                    'total_liquido_acu': getattr(t, 'total_liquido_cumulativo', None),
                    'residuos_solidos_acu': getattr(t, 'residuos_solidos_cumulativo', None),
                    # Também expor nomes canônicos (útil para debug/compat)
                    'total_liquido_cumulativo': getattr(t, 'total_liquido_cumulativo', None),
                    'residuos_solidos_cumulativo': getattr(t, 'residuos_solidos_cumulativo', None),
                }

                tanques_payload.append(item)
            except Exception:
                continue
        payload['tanques'] = tanques_payload
    except Exception:
        payload['tanques'] = []

    # Se o cliente passou ?tank_id=NN, tentar promover esse tanque como 'ativo' no payload
    try:
        tank_q = request.GET.get('tank_id') or request.GET.get('tanque_id') or None
        # Caso não informado, assumir primeiro tanque da lista (se existir) para melhorar UX
        if not tank_q and payload.get('tanques'):
            try:
                tank_q = str(payload['tanques'][0].get('id'))
            except Exception:
                tank_q = None

        if tank_q:
            try:
                tid = int(tank_q)
            except Exception:
                tid = None

            active = None
            try:
                for x in payload.get('tanques', []):
                    if tid is not None and x.get('id') == tid:
                        active = x
                        break
            except Exception:
                active = None

            if active is None and payload.get('tanques'):
                # fallback para primeiro da lista se o id não foi encontrado
                try:
                    active = payload['tanques'][0]
                except Exception:
                    active = None

            if active:
                # Sobrescrever chaves de tanque no payload para que o fragmento
                # referenciando `r.*` mostre os valores do tanque ativo.
                payload['active_tanque_id'] = active.get('id')
                # Expor o dicionário do tanque ativo diretamente como `r.active_tanque`
                # para que o template `rdo_editor_fragment.html` possa usar
                # `r.active_tanque` (ou `rt`) e renderizar campos do RdoTanque.
                try:
                    payload['active_tanque'] = active
                except Exception:
                    payload['active_tanque'] = None
                # Identificação do tanque
                payload['tanque_codigo'] = active.get('tanque_codigo')
                payload['nome_tanque'] = active.get('nome_tanque')
                payload['numero_compartimentos'] = active.get('numero_compartimentos')
                # Campos de configuração do tanque
                # OBS: para estes campos que ainda não constam no tanques_payload,
                # tentamos buscar direto do banco (instância completa) para preencher o restante.
                try:
                    t_obj = rdo_obj.tanques.filter(pk=active.get('id')).first()
                except Exception:
                    t_obj = None
                if t_obj is not None:
                    try: payload['tipo_tanque'] = getattr(t_obj, 'tipo_tanque', None)
                    except Exception: pass
                    try: payload['gavetas'] = getattr(t_obj, 'gavetas', None)
                    except Exception: pass
                    try: payload['patamares'] = getattr(t_obj, 'patamares', None)
                    except Exception: pass
                    try:
                        vtx = getattr(t_obj, 'volume_tanque_exec', None)
                        payload['volume_tanque_exec'] = (str(vtx) if vtx is not None else None)
                    except Exception: pass
                    # Cumulativos de resíduos por tanque (nomes do frontend)
                    try:
                        payload['total_liquido_acu'] = getattr(t_obj, 'total_liquido_cumulativo', None)
                    except Exception:
                        pass
                    try:
                        payload['residuos_solidos_acu'] = getattr(t_obj, 'residuos_solidos_cumulativo', None)
                    except Exception:
                        pass
                    try: payload['servico_exec'] = getattr(t_obj, 'servico_exec', None)
                    except Exception: pass
                    try: payload['metodo_exec'] = getattr(t_obj, 'metodo_exec', None)
                    except Exception: pass
                    try: payload['espaco_confinado'] = getattr(t_obj, 'espaco_confinado', None)
                    except Exception: pass
                    try: payload['operadores_simultaneos'] = getattr(t_obj, 'operadores_simultaneos', None)
                    except Exception: pass
                    try:
                        h = getattr(t_obj, 'h2s_ppm', None)
                        payload['H2S_ppm'] = (str(h) if h is not None else None)
                    except Exception: pass
                    try:
                        l = getattr(t_obj, 'lel', None)
                        payload['LEL'] = (str(l) if l is not None else None)
                    except Exception: pass
                    try:
                        c = getattr(t_obj, 'co_ppm', None)
                        payload['CO_ppm'] = (str(c) if c is not None else None)
                    except Exception: pass
                    try:
                        o = getattr(t_obj, 'o2_percent', None)
                        payload['O2_percent'] = (str(o) if o is not None else None)
                    except Exception: pass
                    # Operacionais por tanque
                    try: payload['tempo_bomba'] = getattr(t_obj, 'tempo_bomba', None)
                    except Exception: pass
                    try: payload['ensacamento_dia'] = getattr(t_obj, 'ensacamento_dia', None)
                    except Exception: pass
                    try: payload['tambores_dia'] = getattr(t_obj, 'tambores_dia', None)
                    except Exception: pass
                    try: payload['residuos_solidos'] = getattr(t_obj, 'residuos_solidos', None)
                    except Exception: pass
                    try: payload['residuos_totais'] = getattr(t_obj, 'residuos_totais', None)
                    except Exception: pass
                    try: payload['avanco_limpeza'] = getattr(t_obj, 'avanco_limpeza', None)
                    except Exception: pass
                    try: payload['avanco_limpeza_fina'] = getattr(t_obj, 'avanco_limpeza_fina', None)
                    except Exception: pass
                    # Percentuais por tanque
                    try:
                        payload['percentual_limpeza_diario'] = (
                            active.get('percentual_limpeza_diario') if active.get('percentual_limpeza_diario') is not None else getattr(t_obj, 'percentual_limpeza_diario', None)
                        )
                    except Exception: pass
                    try:
                        payload['percentual_limpeza_fina'] = (
                            active.get('percentual_limpeza_fina_diario') if active.get('percentual_limpeza_fina_diario') is not None else getattr(t_obj, 'percentual_limpeza_fina_diario', None)
                        )
                    except Exception: pass
                    try: payload['percentual_limpeza_cumulativo'] = getattr(t_obj, 'percentual_limpeza_cumulativo', None)
                    except Exception: pass
                    try: payload['percentual_limpeza_fina_cumulativo'] = getattr(t_obj, 'percentual_limpeza_fina_cumulativo', None)
                    except Exception: pass
                    try: payload['percentual_ensacamento'] = getattr(t_obj, 'percentual_ensacamento', None)
                    except Exception: pass
                    try: payload['percentual_icamento'] = getattr(t_obj, 'percentual_icamento', None)
                    except Exception: pass
                    try: payload['percentual_cambagem'] = getattr(t_obj, 'percentual_cambagem', None)
                    except Exception: pass
                    try: payload['percentual_avanco'] = getattr(t_obj, 'percentual_avanco', None)
                    except Exception: pass
                    # Percentual de avanço cumulativo deve vir do TANQUE ativo (nunca do RDO)
                    try:
                        payload['percentual_avanco_cumulativo'] = getattr(t_obj, 'percentual_avanco_cumulativo', None)
                    except Exception:
                        payload['percentual_avanco_cumulativo'] = payload.get('percentual_avanco_cumulativo')

                    # Se ainda ausente, calcular via pesos 70/7/7/5/6 a partir dos percentuais componentes do tanque
                    try:
                        pac = payload.get('percentual_avanco_cumulativo')
                        def _p(x):
                            try:
                                if x is None or x == '':
                                    return None
                                return float(str(x).replace('.', '').replace(',', '.'))
                            except Exception:
                                return None
                        if pac in (None, ''):
                            p_limpeza = _p(getattr(t_obj, 'percentual_limpeza_cumulativo', None))
                            p_ens = _p(getattr(t_obj, 'percentual_ensacamento', None))
                            p_ica = _p(getattr(t_obj, 'percentual_icamento', None))
                            p_cam = _p(getattr(t_obj, 'percentual_cambagem', None))
                            p_fina = _p(getattr(t_obj, 'percentual_limpeza_fina_cumulativo', None))
                            nums = [p_limpeza, p_ens, p_ica, p_cam, p_fina]
                            weights = [70, 7, 7, 5, 6]
                            available = [(n, w) for n, w in zip(nums, weights) if n is not None]
                            if available:
                                total_w = sum(w for _, w in available)
                                if total_w > 0:
                                    calc = sum(n * w for n, w in available) / total_w
                                    payload['percentual_avanco_cumulativo'] = round(calc + 1e-8, 2)
                    except Exception:
                        pass
                    # Sentido limpeza (expor token canônico + rótulo legível e flag booleana compat)
                    try:
                        sl = getattr(t_obj, 'sentido_limpeza', None)
                        token = _canonicalize_sentido(sl)
                        if token:
                            payload['sentido_limpeza'] = token
                            # human label
                            if token == 'vante > ré':
                                payload['sentido_label'] = 'Vante > Ré'
                                payload['sentido_limpeza_bool'] = True
                            elif token == 'ré > vante':
                                payload['sentido_label'] = 'Ré > Vante'
                                payload['sentido_limpeza_bool'] = False
                            elif token == 'bombordo > boreste':
                                payload['sentido_label'] = 'Bombordo > Boreste'
                                payload['sentido_limpeza_bool'] = None
                            elif token == 'boreste < bombordo':
                                payload['sentido_label'] = 'Boreste < Bombordo'
                                payload['sentido_limpeza_bool'] = None
                        else:
                            # fallback: expose raw value for compatibility
                            payload['sentido_limpeza'] = sl
                            payload['sentido_limpeza_bool'] = None
                    except Exception:
                        pass
                else:
                    # fallback mínimo usando apenas o dicionário 'active'
                    payload['percentual_limpeza_diario'] = active.get('percentual_limpeza_diario')
                    payload['percentual_limpeza_fina'] = active.get('percentual_limpeza_fina_diario')
                    payload['percentual_limpeza_cumulativo'] = active.get('percentual_limpeza_cumulativo')
                    payload['percentual_limpeza_fina_cumulativo'] = active.get('percentual_limpeza_fina_cumulativo')
                    # Normalize active payload sentido to canonical token when possible
                    try:
                        ac = active.get('sentido_limpeza') if isinstance(active, dict) else None
                        token = _canonicalize_sentido(ac)
                        if token:
                            payload['sentido_limpeza'] = token
                            if token == 'vante > ré':
                                payload['sentido_label'] = 'Vante > Ré'
                                payload['sentido_limpeza_bool'] = True
                            elif token == 'ré > vante':
                                payload['sentido_label'] = 'Ré > Vante'
                                payload['sentido_limpeza_bool'] = False
                            elif token == 'bombordo > boreste':
                                payload['sentido_label'] = 'Bombordo > Boreste'
                                payload['sentido_limpeza_bool'] = None
                            elif token == 'boreste < bombordo':
                                payload['sentido_label'] = 'Boreste < Bombordo'
                                payload['sentido_limpeza_bool'] = None
                        else:
                            payload['sentido_limpeza'] = ac
                            payload['sentido_limpeza_bool'] = (True if ac in (True, 'Vante para Ré', 'Vante', 'vante') else (False if ac in (False, 'Ré para Vante', 're') else None))
                    except Exception:
                        payload['sentido_limpeza'] = active.get('sentido_limpeza')
                        payload['sentido_limpeza_bool'] = (True if active.get('sentido_limpeza') in (True, 'Vante para Ré', 'Vante', 'vante') else (False if active.get('sentido_limpeza') in (False, 'Ré para Vante', 're') else None))
                    # Expor cumulativos operacionais do tanque ativo para o editor
                    try:
                        payload['ensacamento_cumulativo'] = active.get('ensacamento_cumulativo')
                        payload['icamento_cumulativo'] = active.get('icamento_cumulativo')
                        payload['cambagem_cumulativo'] = active.get('cambagem_cumulativo')
                        payload['total_liquido_acu'] = active.get('total_liquido_acu') or active.get('total_liquido_cumulativo')
                        payload['residuos_solidos_acu'] = active.get('residuos_solidos_acu') or active.get('residuos_solidos_cumulativo')
                    except Exception:
                        pass
                    payload['sentido_limpeza_bool'] = (True if active.get('sentido_limpeza') in (True, 'Vante para Ré', 'Vante', 'vante') else (False if active.get('sentido_limpeza') in (False, 'Ré para Vante', 're') else None))

                # Disponibilizar o dicionário do tanque ativo completo para o template (quando útil)
                # Enriquecer o dicionário com keys esperadas pelo template para evitar
                # VariableDoesNotExist quando o template faz rt = r.active_tanque|default:r
                try:
                    enriched = dict(active) if isinstance(active, dict) else {}
                    # Campos conhecidos que o template pode acessar — prover fallbacks
                    fallback_keys = [
                        # ensacamento variants
                        'ensacamento_prev', 'ensacamento_previsao', 'ensacamento',
                        'ensacamento_cumulativo',
                        # icamento variants (icamento = 'icamento' in some templates)
                        'icamento', 'icamento_previsao', 'icamento_cumulativo',
                        # cambagem variants
                        'cambagem', 'cambagem_previsao', 'cambagem_cumulativo',
                        # percentuais componentizados
                        'percentual_ensacamento', 'percentual_icamento', 'percentual_cambagem',
                        # percentuais de avanço
                        'percentual_avanco', 'percentual_avanco_cumulativo',
                        # percentuais de limpeza (diários e cumulativos) e aliases para a UI
                        'percentual_limpeza_diario', 'percentual_limpeza_fina_diario',
                        'percentual_limpeza_cumulativo', 'percentual_limpeza_fina_cumulativo',
                        'percentuais', 'percentual',
                        # novos cumulativos de resíduos por tanque (nomes do frontend)
                        'total_liquido_acu', 'residuos_solidos_acu',
                        # nomes canônicos (backend)
                        'total_liquido_cumulativo', 'residuos_solidos_cumulativo',
                    ]
                    for k in fallback_keys:
                        if k not in enriched:
                            try:
                                enriched[k] = (active.get(k) if isinstance(active, dict) else None) or payload.get(k)
                            except Exception:
                                enriched[k] = payload.get(k)

                    # também expor nomes legíveis e aliases usados pelo template
                    if 'nome_tanque' not in enriched:
                        enriched['nome_tanque'] = active.get('nome_tanque') or payload.get('nome_tanque')
                    if 'tanque_codigo' not in enriched:
                        enriched['tanque_codigo'] = active.get('tanque_codigo') or payload.get('tanque_codigo')

                    # Aliases históricos/UX: o template espera 'limpeza_mecanizada_diaria'
                    # enquanto o modelo/tanques pode usar 'percentual_limpeza_diario'. Mapear ambos.
                    try:
                        if 'limpeza_mecanizada_diaria' not in enriched:
                            enriched['limpeza_mecanizada_diaria'] = (
                                (active.get('limpeza_mecanizada_diaria') if isinstance(active, dict) else None)
                                or (active.get('percentual_limpeza_diario') if isinstance(active, dict) else None)
                                or payload.get('percentual_limpeza_diario')
                                or payload.get('limpeza_mecanizada_diaria')
                            )
                    except Exception:
                        enriched['limpeza_mecanizada_diaria'] = payload.get('percentual_limpeza_diario')

                    # Possível alias para cumulativo limpeza mecanizada
                    try:
                        if 'limpeza_mecanizada_cumulativa' not in enriched:
                            enriched['limpeza_mecanizada_cumulativa'] = (
                                (active.get('limpeza_mecanizada_cumulativa') if isinstance(active, dict) else None)
                                or (active.get('percentual_limpeza_cumulativo') if isinstance(active, dict) else None)
                                or payload.get('percentual_limpeza_cumulativo')
                            )
                    except Exception:
                        enriched['limpeza_mecanizada_cumulativa'] = payload.get('percentual_limpeza_cumulativo')

                    payload['active_tanque'] = enriched
                except Exception:
                    # em caso de qualquer problema, ainda tentar expor o active original
                    try:
                        payload['active_tanque'] = active
                    except Exception:
                        pass
    except Exception:
        pass

    # Garantir chaves *_hhmm (strings 'HH:MM') para compatibilidade com inputs type=time
    try:
        from datetime import time as _dt_time
        def _time_to_hhmm(v):
            try:
                if v is None:
                    return None
                if isinstance(v, _dt_time):
                    return v.strftime('%H:%M')
                s = str(v)
                if not s:
                    return None
                if ':' in s:
                    parts = s.split(':')
                    try:
                        h = int(parts[0]); m = int(parts[1]) if len(parts) > 1 else 0
                        return f"{h:02d}:{m:02d}"
                    except Exception:
                        return s
                return s
            except Exception:
                return None

        payload['total_hh_cumulativo_real_hhmm'] = _time_to_hhmm(payload.get('total_hh_cumulativo_real'))
        payload['hh_disponivel_cumulativo_hhmm'] = _time_to_hhmm(payload.get('hh_disponivel_cumulativo'))
        payload['total_hh_frente_real_hhmm'] = _time_to_hhmm(payload.get('total_hh_frente_real'))
    except Exception:
        # não bloquear fluxo principal se formatação falhar
        pass

    # Incluir estado prévio por compartimento (agregado de RDOs anteriores da mesma Ordem de Serviço)
    try:
        prev_compartimentos = []
        n_comp = int(getattr(rdo_obj, 'numero_compartimentos') or 0)
        if n_comp and ordem is not None:
            # coletar RDOs anteriores da mesma OS (excluir o atual)
            prior_qs = RDO.objects.filter(ordem_servico=ordem).exclude(pk=rdo_obj.pk).filter(data__lte=rdo_obj.data).order_by('data', 'pk')
            # inicializar somatórios por índice
            sums = {str(i): {'mecanizada': 0, 'fina': 0} for i in range(1, n_comp + 1)}
            for prior in prior_qs:
                raw = getattr(prior, 'compartimentos_avanco_json', None)
                if not raw:
                    continue
                try:
                    parsed = json.loads(raw)
                except Exception:
                    continue
                for i in range(1, n_comp + 1):
                    key = str(i)
                    item = parsed.get(key) if isinstance(parsed, dict) else None
                    if not item:
                        continue
                    try:
                        mv = int(item.get('mecanizada') or 0)
                    except Exception:
                        mv = 0
                    try:
                        fv = int(item.get('fina') or 0)
                    except Exception:
                        fv = 0
                    # acumular e limitar a 100
                    sums[key]['mecanizada'] = max(0, min(100, sums[key]['mecanizada'] + (mv or 0)))
                    sums[key]['fina'] = max(0, min(100, sums[key]['fina'] + (fv or 0)))
            for i in range(1, n_comp + 1):
                key = str(i)
                prev_compartimentos.append({'index': i, 'mecanizada': sums[key]['mecanizada'], 'fina': sums[key]['fina']})
        payload['previous_compartimentos'] = prev_compartimentos
    except Exception:
        logging.getLogger(__name__).exception('Falha ao calcular previous_compartimentos para rdo_detail')
        payload['previous_compartimentos'] = []

        # Fallback: se hh_disponivel_cumulativo não estiver presente no RDO, tente calcular a partir da Ordem de Serviço
        try:
            if not payload.get('hh_disponivel_cumulativo') and ordem is not None:
                try:
                    # Preferir método que já retorna datetime.time
                    if hasattr(ordem, 'calc_hh_disponivel_cumulativo_time'):
                        try:
                            payload['hh_disponivel_cumulativo'] = ordem.calc_hh_disponivel_cumulativo_time()
                        except Exception:
                            # continue to try timedelta-based
                            pass
                    # Fallback: método que retorna timedelta
                    if not payload.get('hh_disponivel_cumulativo') and hasattr(ordem, 'calc_hh_disponivel_cumulativo'):
                        try:
                            td = ordem.calc_hh_disponivel_cumulativo()
                            if td:
                                total_seconds = int(td.total_seconds())
                                hours = total_seconds // 3600
                                minutes = (total_seconds % 3600) // 60
                                hours_mod = hours % 24
                                payload['hh_disponivel_cumulativo'] = dt_time(hour=hours_mod, minute=minutes)
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass

    # Se o cliente pediu renderização do fragmento do editor, gerar HTML parcial e retornar
    try:
        if request.GET.get('render') in ('editor', 'html'):
            from django.template.loader import render_to_string
            logger = logging.getLogger(__name__)
            # Debug: logar informações úteis para investigar porque o fragmento
            # às vezes exibe valores do RDO em vez dos valores do RdoTanque ativo.
            try:
                tank_q = request.GET.get('tank_id') or request.GET.get('tanque_id') or None
                logger.debug('rdo_detail(render=editor) rdo_id=%s tank_q=%s tanques_count=%s active_tanque_id=%s',
                             getattr(rdo_obj, 'id', None),
                             tank_q,
                             len(payload.get('tanques', [])),
                             payload.get('active_tanque_id', None))
            except Exception:
                logger.exception('Falha ao montar debug log para rdo_detail(render=editor)')
            try:
                # Preparar lista de funções para popular selects no fragmento do editor.
                # Usar constantes definidas em OrdemServico.FUNCOES + registros da tabela Funcao,
                # preservando ordem e evitando duplicatas.
                try:
                    from types import SimpleNamespace
                    db_funcoes_qs = Funcao.objects.order_by('nome').all() if hasattr(Funcao, 'objects') else []
                    db_funcoes_names = [getattr(f, 'nome', None) for f in db_funcoes_qs]
                    const_funcoes = [t[0] for t in getattr(OrdemServico, 'FUNCOES', [])]
                    const_only = [SimpleNamespace(nome=name) for name in const_funcoes if name not in db_funcoes_names]
                    db_funcoes_objs = [SimpleNamespace(nome=getattr(f, 'nome', None)) for f in db_funcoes_qs]
                    get_funcoes_ctx = const_only + db_funcoes_objs
                except Exception:
                    # Fallback simples: tentar retornar QuerySet ou lista vazia
                    try:
                        get_funcoes_ctx = Funcao.objects.order_by('nome').all() if hasattr(Funcao, 'objects') else []
                    except Exception:
                        get_funcoes_ctx = []

                # Garantir que a chave `active_tanque` exista no payload
                try:
                    payload.setdefault('active_tanque', None)
                except Exception:
                    payload['active_tanque'] = None

                html = render_to_string('rdo_editor_fragment.html', {
                    'r': payload,
                    'atividades_choices': getattr(RDO, 'ATIVIDADES_CHOICES', []),
                    'servico_choices': getattr(OrdemServico, 'SERVICO_CHOICES', []),
                    # Forçar apenas Manual/Mecanizada/Robotizada no editor fragment
                    'metodo_choices': [ ('Manual','Manual'), ('Mecanizada','Mecanizada'), ('Robotizada','Robotizada') ],
                    'get_pessoas': Pessoa.objects.order_by('nome').all() if hasattr(Pessoa, 'objects') else [],
                    'get_funcoes': get_funcoes_ctx,
                }, request=request)
                return JsonResponse({'success': True, 'html': html})
            except Exception:
                logger.exception('Falha renderizando fragmento do editor')
                # cair para retornar o payload JSON usual
                pass
    except Exception:
        pass

    return JsonResponse({
        'success': True,
        'rdo': payload
    })


@login_required(login_url='/login/')
@require_POST
def salvar_supervisor(request):
    """Persistência do modal do Supervisor.

    Regras principais:
    - Quando 'tanque_id' (ou 'tank_id') for enviado, atualizar somente o RdoTanque indicado
      com os campos por-tanque (previsões e limpeza), quantizando decimais em 2 casas.
    - Quando NÃO houver tanque_id, mas houver campos de limpeza no payload, replicar esses
      valores para todos os tanques do RDO informado.

    Campos aceitos (prioridade: canônicos -> aliases do modal legado):
      - limpeza_mecanizada_diaria        | alias: sup-limp            (Decimal 2dp, ROUND_HALF_UP)
      - limpeza_mecanizada_cumulativa    | alias: sup-limp-acu        (int)
      - percentual_limpeza_fina          | alias: sup-limp-fina       (int)
      - percentual_limpeza_fina_cumulativo | alias: sup-limp-fina-acu (int)
      - ensacamento_prev, icamento_prev, cambagem_prev (int, por tanque)

    Retorna JSON { success, updated: {rdo_id, tank_id?, count?}, tank? }
    """
    import json
    import logging
    from decimal import Decimal, ROUND_HALF_UP
    from django.db import transaction

    logger = logging.getLogger(__name__)

    # Helper: ler POST ou JSON body
    body_json = {}
    try:
        ctype = (request.META.get('CONTENT_TYPE') or request.META.get('HTTP_CONTENT_TYPE') or '')
        if (not request.POST) or ('application/json' in ctype.lower()):
            try:
                raw = request.body.decode('utf-8') if hasattr(request, 'body') else ''
                body_json = json.loads(raw) if raw else {}
            except Exception:
                body_json = {}
    except Exception:
        body_json = {}

    def get_in(name, default=None):
        if hasattr(request, 'POST') and name in request.POST:
            return request.POST.get(name)
        try:
            return body_json.get(name, default) if isinstance(body_json, dict) else default
        except Exception:
            return default

    def get_list(name):
        """Retorna lista do POST/JSON para campos com múltiplos valores (ex.: compartimentos_avanco)."""
        try:
            if hasattr(request, 'POST') and hasattr(request.POST, 'getlist'):
                vals = request.POST.getlist(name)
                if vals:
                    return vals
        except Exception:
            pass
        try:
            if isinstance(body_json, dict):
                v = body_json.get(name)
                if isinstance(v, list):
                    return v
        except Exception:
            pass
        return []

    def _clean(val):
        return val if val not in (None, '') else None

    def _to_int(v):
        try:
            if v is None or v == '':
                return None
            return int(float(v))
        except Exception:
            return None

    def _to_dec_2(v):
        try:
            if v is None or v == '':
                return None
            d = Decimal(str(v))
            return d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except Exception:
            return None

    def _norm_number_like(v):
        """Normalize numeric-like inputs (percent strings, comma decimals).

        - None or empty -> None
        - strips trailing '%', trims whitespace
        - replaces comma with dot
        - returns normalized string (suitable for Decimal/float parsing) or None
        """
        try:
            if v is None:
                return None
            s = str(v).strip()
            if s == '':
                return None
            # remove trailing percent sign if present
            if s.endswith('%'):
                s = s[:-1].strip()
            # replace comma decimal separator with dot
            s = s.replace(',', '.')
            if s == '':
                return None
            return s
        except Exception:
            return None

    # DEBUG: log incoming request payload summary to help diagnose missing keys in production
    safe_body_snip = ''
    try:
        if hasattr(request, 'body') and request.body:
            try:
                safe_body_snip = request.body.decode('utf-8')[:400]
            except Exception:
                safe_body_snip = ''
        logger.info('salvar_supervisor: CONTENT_TYPE=%s POST_keys=%s JSON_keys=%s body_snip=%s',
                    ctype,
                    (list(request.POST.keys()) if hasattr(request, 'POST') else None),
                    (list(body_json.keys()) if isinstance(body_json, dict) else None),
                    safe_body_snip)
    except Exception:
        # Não queremos que logging de debug quebre o fluxo em produção
        pass

    # Mapear nomes canônicos e aliases
    CANONICAL_MAP = {
        'limpeza_mecanizada_diaria': [
            'limpeza_mecanizada_diaria',
            'sup-limp',
            'percentual_limpeza_diario',
            'avanco_limpeza',
        ],
        'limpeza_mecanizada_cumulativa': [
            'limpeza_mecanizada_cumulativa',
            'sup-limp-acu',
            'limpeza_acu',
            'percentual_limpeza_cumulativo',
        ],
        'percentual_limpeza_fina': [
            'percentual_limpeza_fina',
            'sup-limp-fina',
            'avanco_limpeza_fina',
            'percentual_limpeza_fina_diario',
        ],
        'percentual_limpeza_fina_cumulativo': [
            'percentual_limpeza_fina_cumulativo',
            'sup-limp-fina-acu',
            'limpeza_fina_acu',
        ],
    }

    # Identificar RDO alvo (obrigatório para replicação e validação de tanque)
    rdo_id = _clean(get_in('rdo_id') or get_in('id') or get_in('rdo'))
    if not rdo_id:
        return JsonResponse({'success': False, 'error': 'rdo_id não informado.'}, status=400)
    try:
        rdo_obj = RDO.objects.select_related('ordem_servico').get(pk=int(rdo_id))
    except Exception:
        return JsonResponse({'success': False, 'error': 'RDO não encontrado.'}, status=404)

    # Se veio tanque_id -> atualização por-tanque
    tank_id_raw = _clean(get_in('tanque_id') or get_in('tank_id') or get_in('tanqueId'))
    try:
        tank_id = int(tank_id_raw) if tank_id_raw is not None else None
    except Exception:
        tank_id = None

    # Fallback robusto: se não veio tank_id, tentar resolver pelo código textual
    # enviado pelo formulário (tanque_codigo). Se houver exatamente 1 tanque no RDO,
    # usar esse como alvo para evitar perda de dados quando a UI não enviar o id.
    if tank_id is None:
        try:
            tank_code_fallback = _clean(get_in('tanque_id_text') or get_in('tanque_codigo') or get_in('tanque_code') or get_in('tanque'))
            if tank_code_fallback:
                try:
                    tmatch = rdo_obj.tanques.filter(tanque_codigo__iexact=str(tank_code_fallback).strip()).order_by('-id').first()
                    if tmatch:
                        tank_id = tmatch.id
                except Exception:
                    pass
            if tank_id is None:
                try:
                    if hasattr(rdo_obj, 'tanques') and rdo_obj.tanques.count() == 1:
                        tank_id = rdo_obj.tanques.first().id
                except Exception:
                    pass
        except Exception:
            pass

    # Coletar valores de limpeza do payload (canônicos com fallback pra aliases)
    def pick_cleaning_values():
        vals = {}
        for canon, names in CANONICAL_MAP.items():
            raw = None
            for nm in names:
                raw_candidate = _clean(get_in(nm))
                if raw_candidate is not None:
                    # normalize percent/decimal formatting so later conversions succeed
                    raw = _norm_number_like(raw_candidate)
                    # if normalization produced None (e.g. empty after stripping), still accept original raw_candidate
                    if raw is None:
                        raw = _clean(raw_candidate)
                    break
            vals[canon] = raw
        return vals

    cleaning_raw = pick_cleaning_values()

    # Helper interno: aplicar valores de limpeza ao RDO (fonte da verdade) quando enviados
    def _apply_cleaning_to_rdo(lm_d_val, lm_c_val, pf_d_val, pf_c_val):
        try:
            changed = False
            if lm_d_val is not None and hasattr(rdo_obj, 'limpeza_mecanizada_diaria'):
                rdo_obj.limpeza_mecanizada_diaria = lm_d_val
                changed = True
            if lm_c_val is not None and hasattr(rdo_obj, 'limpeza_mecanizada_cumulativa'):
                rdo_obj.limpeza_mecanizada_cumulativa = lm_c_val
                changed = True
            if pf_d_val is not None and hasattr(rdo_obj, 'percentual_limpeza_fina'):
                rdo_obj.percentual_limpeza_fina = pf_d_val
                changed = True
            if pf_c_val is not None and hasattr(rdo_obj, 'percentual_limpeza_fina_cumulativo'):
                rdo_obj.percentual_limpeza_fina_cumulativo = pf_c_val
                changed = True
            if changed:
                try:
                    _safe_save_global(rdo_obj)
                except Exception:
                    rdo_obj.save()
        except Exception:
            logging.getLogger(__name__).exception('Falha ao aplicar valores de limpeza no RDO %s', getattr(rdo_obj, 'id', None))

    # Atualizar somente um tanque
    if tank_id is not None:
        try:
            tank = RdoTanque.objects.get(pk=tank_id)
        except RdoTanque.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Tanque não encontrado.'}, status=404)
        # Validação branda: se o tanque não pertence ao RDO enviado, ainda assim
        # permita (há casos de UI navegando entre RDOs), mas logar para investigação.
        try:
            if getattr(tank, 'rdo_id', None) != getattr(rdo_obj, 'id', None):
                logger.warning('salvar_supervisor: tank_id=%s não pertence ao rdo_id=%s', tank_id, rdo_obj.id)
        except Exception:
            pass

        # Previsões por tanque
        ens_prev = _to_int(get_in('ensacamento_prev'))
        ica_prev = _to_int(get_in('icamento_prev'))
        cam_prev = _to_int(get_in('cambagem_prev'))
        if ens_prev is not None:
            tank.ensacamento_prev = ens_prev
        if ica_prev is not None:
            tank.icamento_prev = ica_prev
        if cam_prev is not None:
            tank.cambagem_prev = cam_prev

        # Atualizar número de compartimentos por tanque, se enviado
        try:
            n_comp_val = _to_int(get_in('numero_compartimentos') or get_in('numero_compartimento'))
            if n_comp_val is not None:
                tank.numero_compartimentos = n_comp_val
        except Exception:
            pass

        # Compartimentos por tanque (JSON em texto). Se não vier pronto, montar a partir dos inputs.
        comp_json = _clean(get_in('compartimentos_avanco_json'))
        if comp_json is None:
            # Tentar construir JSON com base nos hidden inputs individuais
            try:
                # Determinar quantidade de compartimentos
                n_raw = _clean(get_in('numero_compartimentos') or get_in('numero_compartimento'))
                try:
                    n_total = int(n_raw) if n_raw is not None else None
                except Exception:
                    n_total = None
                if not n_total:
                    try:
                        n_total = int(getattr(tank, 'numero_compartimentos', None) or 0)
                    except Exception:
                        n_total = None
                if not n_total:
                    try:
                        n_total = int(getattr(rdo_obj, 'numero_compartimentos', None) or 0)
                    except Exception:
                        n_total = None

                # Lista simples de compartimentos marcados (legado)
                try:
                    selected = [int(x) for x in get_list('compartimentos_avanco')]
                except Exception:
                    selected = []

                payload = {}
                if n_total and n_total > 0:
                    for i in range(1, n_total + 1):
                        m_raw = _clean(get_in(f'compartimento_avanco_mecanizada_{i}'))
                        f_raw = _clean(get_in(f'compartimento_avanco_fina_{i}'))
                        try:
                            m_val = int(float(m_raw)) if m_raw is not None else None
                        except Exception:
                            m_val = None
                        try:
                            f_val = int(float(f_raw)) if f_raw is not None else None
                        except Exception:
                            f_val = None
                        if m_val is None and (i in selected):
                            m_val = 100
                        if f_val is None:
                            f_val = 0
                        try:
                            m_val = 0 if m_val is None else max(0, min(100, int(m_val)))
                        except Exception:
                            m_val = 0
                        try:
                            f_val = 0 if f_val is None else max(0, min(100, int(f_val)))
                        except Exception:
                            f_val = 0
                        payload[str(i)] = {'mecanizada': m_val, 'fina': f_val}
                    comp_json = json.dumps(payload)
            except Exception:
                comp_json = None

        if comp_json is not None:
            try:
                # validar JSON superficialmente; se inválido, apenas ignora
                import json as _json
                _json.loads(comp_json)
                tank.compartimentos_avanco_json = comp_json
                # calcular limpeza diária a partir dos compartimentos
                try:
                    tank.compute_limpeza_from_compartimentos()
                except Exception:
                    logger.exception('Falha ao calcular limpeza mecanizada diária por tanque via compartimentos')
            except Exception:
                logger.warning('compartimentos_avanco_json inválido; ignorando para tank_id=%s', tank_id)

        # Campos canônicos por-tanque
        lm_d = _to_dec_2(cleaning_raw.get('limpeza_mecanizada_diaria'))
        lm_c = _to_int(cleaning_raw.get('limpeza_mecanizada_cumulativa'))
        pf_d = _to_int(cleaning_raw.get('percentual_limpeza_fina'))
        pf_c = _to_int(cleaning_raw.get('percentual_limpeza_fina_cumulativo'))

        # Cumulativos operacionais por-tanque (aceitar aliases simples via inputs)
        ensac_cum = _to_int(get_in('ensacamento_cumulativo') or get_in('ensacamento_acu') or cleaning_raw.get('ensacamento_cumulativo'))
        ic_cum = _to_int(get_in('icamento_cumulativo') or get_in('icamento_acu') or cleaning_raw.get('icamento_cumulativo'))
        camb_cum = _to_int(get_in('cambagem_cumulativo') or get_in('cambagem_acu') or cleaning_raw.get('cambagem_cumulativo'))
        tlq_cum = _to_int(get_in('total_liquido_cumulativo') or get_in('total_liquido_acu') or cleaning_raw.get('total_liquido_cumulativo') or cleaning_raw.get('total_liquido_acu'))
        rss_cum = _to_dec_2(get_in('residuos_solidos_cumulativo') or get_in('residuos_solidos_acu') or cleaning_raw.get('residuos_solidos_cumulativo') or cleaning_raw.get('residuos_solidos_acu'))

        # Refletir também no RDO (fonte da verdade)
        _apply_cleaning_to_rdo(lm_d, lm_c, pf_d, pf_c)

        if lm_d is not None:
            tank.limpeza_mecanizada_diaria = lm_d
        if lm_c is not None:
            tank.limpeza_mecanizada_cumulativa = lm_c
            # canonical per-tank field removed from server-side flow (kept only in model)
        if pf_d is not None:
            tank.percentual_limpeza_fina = pf_d
        if pf_c is not None:
            tank.percentual_limpeza_fina_cumulativo = pf_c
            # canonical per-tank field removed from server-side flow (kept only in model)

        # Persistir cumulativos operacionais por-tanque quando enviados explicitamente
        if ensac_cum is not None:
            tank.ensacamento_cumulativo = ensac_cum
        if ic_cum is not None:
            tank.icamento_cumulativo = ic_cum
        if camb_cum is not None:
            tank.cambagem_cumulativo = camb_cum
        if tlq_cum is not None and hasattr(tank, 'total_liquido_cumulativo'):
            tank.total_liquido_cumulativo = tlq_cum
        if rss_cum is not None and hasattr(tank, 'residuos_solidos_cumulativo'):
            tank.residuos_solidos_cumulativo = rss_cum

        # Permitir atualização do código textual do tanque caso enviado (preserva input textual)
        tank_code_in = _clean(get_in('tanque_codigo') or get_in('tanque_code'))
        if tank_code_in is not None:
            tank.tanque_codigo = tank_code_in

        # Permitir atualização do sentido da limpeza por-tanque (normalizar para token canônico)
        try:
            sentido_raw_tank = _clean(get_in('sentido') or get_in('sentido_limpeza'))
        except Exception:
            sentido_raw_tank = None
        if sentido_raw_tank is not None:
            try:
                try:
                    token_tank = _canonicalize_sentido(sentido_raw_tank)
                except Exception:
                    token_tank = None
                if token_tank is not None and hasattr(tank, 'sentido_limpeza'):
                    tank.sentido_limpeza = token_tank
                else:
                    # fallback: persistir string bruta quando não for possível canonicalizar
                    if hasattr(tank, 'sentido_limpeza'):
                        try:
                            tank.sentido_limpeza = str(sentido_raw_tank)
                        except Exception:
                            pass
            except Exception:
                pass

        # Salvar atomically
        try:
            with transaction.atomic():
                tank.save()
        except Exception:
            logger.exception('Falha ao salvar RdoTanque %s', tank_id)
            return JsonResponse({'success': False, 'error': 'Falha ao salvar tanque.'}, status=500)

        # Se cumulativos não foram enviados, tentar recomputar por-tanque
        try:
            sent_lm_c = cleaning_raw.get('limpeza_mecanizada_cumulativa') not in (None, '')
            sent_pf_c = cleaning_raw.get('percentual_limpeza_fina_cumulativo') not in (None, '')
            if not (sent_lm_c and sent_pf_c):
                try:
                    if hasattr(tank, 'recompute_metrics') and callable(tank.recompute_metrics):
                        res = tank.recompute_metrics(only_when_missing=True)
                        # só salvar se o recompute tiver produzido algum resultado
                        if res is not None:
                            with transaction.atomic():
                                tank.save()
                except Exception:
                    logger.exception('Falha ao recomputar cumulativos por tanque (id=%s)', getattr(tank, 'id', None))
        except Exception:
            logger.exception('Erro verificando campos enviados para cumulativos do tanque (id=%s)', getattr(tank, 'id', None))

        # Montar payload simples do tanque atualizado
        tank_payload = {
            'id': tank.id,
            'tanque_codigo': getattr(tank, 'tanque_codigo', None),
            'limpeza_mecanizada_diaria': getattr(tank, 'limpeza_mecanizada_diaria', None),
            'limpeza_mecanizada_cumulativa': getattr(tank, 'limpeza_mecanizada_cumulativa', None),
            'percentual_limpeza_fina': getattr(tank, 'percentual_limpeza_fina', None),
            'percentual_limpeza_fina_cumulativo': getattr(tank, 'percentual_limpeza_fina_cumulativo', None),
            # per-tank canonical limpeza fields intentionally omitted from response payload
            'ensacamento_prev': getattr(tank, 'ensacamento_prev', None),
            'icamento_prev': getattr(tank, 'icamento_prev', None),
            'cambagem_prev': getattr(tank, 'cambagem_prev', None),
            # Novos cumulativos de resíduos (nomes do frontend)
            'total_liquido_acu': getattr(tank, 'total_liquido_cumulativo', None),
            'residuos_solidos_acu': getattr(tank, 'residuos_solidos_cumulativo', None),
            'compartimentos_avanco_json': getattr(tank, 'compartimentos_avanco_json', None),
        }
        return JsonResponse({'success': True, 'updated': {'rdo_id': rdo_obj.id, 'tank_id': tank.id}, 'tank': tank_payload})

    # Sem tanque_id: replicar campos de limpeza para todos os tanques do RDO (quando vierem no payload)
    # Se nada de limpeza foi enviado, retornar erro leve para orientar o cliente
    if not any(v is not None and str(v) != '' for v in cleaning_raw.values()):
        return JsonResponse({'success': False, 'error': 'Nenhum campo de limpeza informado para replicação.'}, status=400)

    lm_d = _to_dec_2(cleaning_raw.get('limpeza_mecanizada_diaria'))
    lm_c = _to_int(cleaning_raw.get('limpeza_mecanizada_cumulativa'))
    pf_d = _to_int(cleaning_raw.get('percentual_limpeza_fina'))
    pf_c = _to_int(cleaning_raw.get('percentual_limpeza_fina_cumulativo'))

    # Cumulativos operacionais (replicação) — aceitar aliases
    ensac_cum = _to_int(cleaning_raw.get('ensacamento_cumulativo') or cleaning_raw.get('ensacamento_acu'))
    ic_cum = _to_int(cleaning_raw.get('icamento_cumulativo') or cleaning_raw.get('icamento_acu'))
    camb_cum = _to_int(cleaning_raw.get('cambagem_cumulativo') or cleaning_raw.get('cambagem_acu'))
    tlq_cum = _to_int(cleaning_raw.get('total_liquido_cumulativo') or cleaning_raw.get('total_liquido_acu'))
    rss_cum = _to_dec_2(cleaning_raw.get('residuos_solidos_cumulativo') or cleaning_raw.get('residuos_solidos_acu'))

    # Refletir no RDO (fonte da verdade) antes da replicação
    _apply_cleaning_to_rdo(lm_d, lm_c, pf_d, pf_c)

    updated = 0
    try:
        with transaction.atomic():
            for t in rdo_obj.tanques.all():
                if lm_d is not None:
                    t.limpeza_mecanizada_diaria = lm_d
                if lm_c is not None:
                    t.limpeza_mecanizada_cumulativa = lm_c
                if pf_d is not None:
                    t.percentual_limpeza_fina = pf_d
                if pf_c is not None:
                    t.percentual_limpeza_fina_cumulativo = pf_c
                # Replicar cumulativos operacionais quando enviados
                if ensac_cum is not None:
                    t.ensacamento_cumulativo = ensac_cum
                if ic_cum is not None:
                    t.icamento_cumulativo = ic_cum
                if camb_cum is not None:
                    t.cambagem_cumulativo = camb_cum
                if tlq_cum is not None and hasattr(t, 'total_liquido_cumulativo'):
                    t.total_liquido_cumulativo = tlq_cum
                if rss_cum is not None and hasattr(t, 'residuos_solidos_cumulativo'):
                    t.residuos_solidos_cumulativo = rss_cum
                t.save()
            # Após replicação, se cumulativos não foram enviados, completar via recompute
            if (lm_c is None) or (pf_c is None):
                for t in rdo_obj.tanques.all():
                    try:
                        t.recompute_metrics(only_when_missing=True)
                        t.save()
                    except Exception:
                        logger.exception('Falha ao recomputar cumulativos por tanque na replicação (id=%s)', getattr(t,'id',None))
                updated = rdo_obj.tanques.count()
                updated += 1
    except Exception:
        logger.exception('Falha ao replicar campos de limpeza para tanques do RDO %s', rdo_obj.id)
        return JsonResponse({'success': False, 'error': 'Falha ao replicar para tanques.'}, status=500)

    return JsonResponse({'success': True, 'updated': {'rdo_id': rdo_obj.id, 'count': updated}})


@require_POST
def debug_parse_supervisor(request):
    """Debug endpoint (DEBUG-only) that parses the Supervisor payload and
    returns the normalized & converted cleaning values without persisting.

    Use for testing payloads from the UI or curl when DB/schema is not safe
    to touch. This endpoint is intentionally lightweight and only available
    when Django DEBUG is True.
    """
    try:
        if not getattr(settings, 'DEBUG', False):
            return JsonResponse({'success': False, 'error': 'Not available'}, status=404)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Not available'}, status=404)

    # Read body as POST or JSON compatibly (same as salvar_supervisor)
    body_json = {}
    try:
        ctype = (request.META.get('CONTENT_TYPE') or request.META.get('HTTP_CONTENT_TYPE') or '')
        if (not request.POST) or ('application/json' in ctype.lower()):
            try:
                raw = request.body.decode('utf-8') if hasattr(request, 'body') else ''
                body_json = json.loads(raw) if raw else {}
            except Exception:
                body_json = {}
    except Exception:
        body_json = {}

    def get_in(name, default=None):
        if hasattr(request, 'POST') and name in request.POST:
            return request.POST.get(name)
        try:
            return body_json.get(name, default) if isinstance(body_json, dict) else default
        except Exception:
            return default

    def _clean(val):
        return val if val not in (None, '') else None

    def _norm_number_like(v):
        try:
            if v is None:
                return None
            s = str(v).strip()
            if s == '':
                return None
            if s.endswith('%'):
                s = s[:-1].strip()
            s = s.replace(',', '.')
            if s == '':
                return None
            return s
        except Exception:
            return None

    def _to_int(v):
        try:
            if v is None or v == '':
                return None
            return int(float(v))
        except Exception:
            return None

    def _to_dec_2(v):
        try:
            if v is None or v == '':
                return None
            d = Decimal(str(v))
            return d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except Exception:
            return None

    CANONICAL_MAP = {
        'limpeza_mecanizada_diaria': [
            'limpeza_mecanizada_diaria', 'sup-limp', 'percentual_limpeza_diario', 'avanco_limpeza',
        ],
        'limpeza_mecanizada_cumulativa': [
            'limpeza_mecanizada_cumulativa', 'sup-limp-acu', 'limpeza_acu', 'percentual_limpeza_cumulativo',
        ],
        'percentual_limpeza_fina': [
            'percentual_limpeza_fina', 'sup-limp-fina', 'avanco_limpeza_fina', 'percentual_limpeza_fina_diario',
        ],
        'percentual_limpeza_fina_cumulativo': [
            'percentual_limpeza_fina_cumulativo', 'sup-limp-fina-acu', 'limpeza_fina_acu',
        ],
    }

    # pick cleaning values using canonical map
    vals = {}
    for canon, names in CANONICAL_MAP.items():
        raw = None
        for nm in names:
            raw_candidate = _clean(get_in(nm))
            if raw_candidate is not None:
                raw = _norm_number_like(raw_candidate)
                if raw is None:
                    raw = _clean(raw_candidate)
                break
        vals[canon] = raw

    converted = {
        'limpeza_mecanizada_diaria': _to_dec_2(vals.get('limpeza_mecanizada_diaria')),
        'limpeza_mecanizada_cumulativa': _to_int(vals.get('limpeza_mecanizada_cumulativa')),
        'percentual_limpeza_fina': _to_int(vals.get('percentual_limpeza_fina')),
        'percentual_limpeza_fina_cumulativo': _to_int(vals.get('percentual_limpeza_fina_cumulativo')),
    }

    resp = {
        'success': True,
        'POST_keys': list(request.POST.keys()),
        'JSON_keys': (list(body_json.keys()) if isinstance(body_json, dict) else None),
        'cleaning_raw': vals,
        'converted': {k: (str(v) if isinstance(v, Decimal) else v) for k, v in converted.items()},
    }

    return JsonResponse(resp)


# Helper: aplica os campos POST ao objeto RDO e salva. Retorna (True, payload) ou (False, None)
def _apply_post_to_rdo(request, rdo_obj):
    logger = logging.getLogger(__name__)
    try:
        logger.info('_apply_post_to_rdo start user=%s rdo_id=%s POST_keys=%s', getattr(request, 'user', None), getattr(rdo_obj, 'id', None), list(request.POST.keys()))
        # DEBUG: dump full POST lists and FILES overview to help diagnose missing keys
        try:
            try:
                post_lists = {}
                if hasattr(request.POST, 'lists'):
                    for k, vals in request.POST.lists():
                        post_lists[k] = vals
                else:
                    for k in list(request.POST.keys()):
                        post_lists[k] = request.POST.getlist(k) if hasattr(request.POST, 'getlist') else [request.POST.get(k)]
                logger.info('_apply_post_to_rdo full POST lists: %s', post_lists)
            except Exception:
                logger.exception('Could not enumerate POST lists')
            try:
                files_info = []
                if hasattr(request, 'FILES') and request.FILES:
                    for k in list(request.FILES.keys()):
                        try:
                            objs = request.FILES.getlist(k) if hasattr(request.FILES, 'getlist') else [request.FILES.get(k)]
                            for f in objs:
                                try:
                                    files_info.append({'field': k, 'name': getattr(f, 'name', None), 'size': getattr(f, 'size', None)})
                                except Exception:
                                    files_info.append({'field': k, 'name': str(f), 'size': None})
                        except Exception:
                            files_info.append({'field': k, 'error': 'could not inspect'})
                logger.info('_apply_post_to_rdo FILES info: %s', files_info)
            except Exception:
                logger.exception('Could not enumerate FILES')
        except Exception:
            logger.exception('Debug dump of POST/FILES failed')
        # DEBUG: logar explicitamente os campos de limpeza que o frontend normalmente envia
        try:
            limp_keys = ['sup-limp', 'sup-limp-acu', 'sup-limp-fina', 'sup-limp-fina-acu', 'avanco_limpeza', 'percentual_limpeza', 'percentual_limpeza_cumulativo', 'limpeza_acu', 'limpeza_fina_acu']
            limp_vals = {k: request.POST.get(k) for k in limp_keys}
            logger.info('_apply_post_to_rdo limpeza POST values: %s', limp_vals)
        except Exception:
            logger.exception('Falha ao logar campos de limpeza do POST')
        # Mapeia helpers
        def _clean(val):
            return val if (val not in (None, '')) else None

        # Attempt to parse JSON body as a compatibility fallback when the client
        # sent JSON (application/json) or when request.POST appears empty.
        body_json = {}
        try:
            try:
                ctype = (request.META.get('CONTENT_TYPE') or request.META.get('HTTP_CONTENT_TYPE') or '')
            except Exception:
                ctype = ''
            if (not request.POST) or ('application/json' in ctype):
                try:
                    raw_body = (request.body.decode('utf-8') if getattr(request, 'body', None) else '') or ''
                    if raw_body:
                        parsed = json.loads(raw_body)
                        if isinstance(parsed, dict):
                            body_json = parsed
                except Exception:
                    # ignore JSON parse errors; keep body_json as empty dict
                    body_json = {}
        except Exception:
            body_json = {}

        def _get_post_or_json(name):
            """Return a value from request.POST when present, otherwise try parsed JSON body."""
            try:
                # Prefer explicit POST form data
                if hasattr(request, 'POST') and (name in request.POST):
                    return request.POST.get(name)
                # then fallback to JSON body
                if isinstance(body_json, dict) and body_json.get(name) is not None:
                    return body_json.get(name)
            except Exception:
                pass
            return None

        def _normalize_contrato(val):
            if val is None:
                return None
            s = str(val).strip()
            if s == '':
                return None
            return s[:30]
        
        # Usar helper global para salvamento resiliente

        # Parse common fields
        ordem_servico_id = request.POST.get('ordem_servico_id')
        data_str = request.POST.get('data')
        # novos campos de período
        data_inicio_str = request.POST.get('rdo_data_inicio') or request.POST.get('data_inicio')
        previsao_termino_str = request.POST.get('rdo_previsao_termino') or request.POST.get('previsao_termino')
        turno_str = request.POST.get('turno')
        contrato_po_str = request.POST.get('contrato_po')

        if rdo_obj is None:
            ordem_servico = OrdemServico.objects.get(id=ordem_servico_id)
            data = datetime.strptime(data_str, '%Y-%m-%d').date() if data_str else None
            # Se a data não foi enviada, usar a data de criação do RDO (hoje)
            if data is None:
                try:
                    data = datetime.today().date()
                except Exception:
                    data = None
            data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date() if data_inicio_str else None
            previsao_termino = datetime.strptime(previsao_termino_str, '%Y-%m-%d').date() if previsao_termino_str else None
            turno = turno_str
            contrato_po = contrato_po_str
            rdo_obj = RDO(ordem_servico=ordem_servico, data=data, data_inicio=data_inicio, previsao_termino=previsao_termino, turno=turno, contrato_po=contrato_po)
        else:
            # For update, set missing fields
            if not getattr(rdo_obj, 'data', None) and data_str:
                try:
                    rdo_obj.data = datetime.strptime(data_str, '%Y-%m-%d').date()
                except:
                    pass
            # atualizar novos campos se fornecidos
            if data_inicio_str:
                try:
                    rdo_obj.data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
                except Exception:
                    pass
            if previsao_termino_str:
                try:
                    rdo_obj.previsao_termino = datetime.strptime(previsao_termino_str, '%Y-%m-%d').date()
                except Exception:
                    pass
            if not getattr(rdo_obj, 'turno', None) and turno_str:
                rdo_obj.turno = turno_str
            if not getattr(rdo_obj, 'contrato_po', None) and contrato_po_str:
                rdo_obj.contrato_po = contrato_po_str

        # RDO / Turno
        # Se um número já foi atribuído (por exemplo, pelo servidor durante a criação
        # atômica), não sobrescrever com o valor enviado pelo cliente. Apenas use o
        # valor do POST quando o objeto ainda não possuir um número definido.
        rdo_num = _clean(request.POST.get('rdo_contagem'))
        if rdo_num and not getattr(rdo_obj, 'rdo', None):
            rdo_obj.rdo = rdo_num
        turno_in = _clean(request.POST.get('turno'))
        if turno_in:
            if turno_in.lower() == 'diurno':
                rdo_obj.turno = 'Diurno'
            elif turno_in.lower() == 'noturno':
                rdo_obj.turno = 'Noturno'

        contrato_in = _clean(request.POST.get('contrato_po'))
        contrato_in = _normalize_contrato(contrato_in)
        if contrato_in is not None:
            if hasattr(rdo_obj, 'contrato_po'):
                try:
                    rdo_obj.contrato_po = contrato_in
                except Exception:
                    pass
            elif hasattr(rdo_obj, 'po'):
                try:
                    rdo_obj.po = contrato_in
                except Exception:
                    pass
            else:
                try:
                    if getattr(rdo_obj, 'ordem_servico', None):
                        ordem = rdo_obj.ordem_servico
                        ordem.po = contrato_in
                        ordem.save()
                except Exception:
                    pass

        # Campos tanque / serviço
        # Campos tanque / serviço
        # IMPORTANTE: tanques são modelados como registros separados (RdoTanque).
        # Em operações de atualização (quando o RDO já existe no banco) devemos
        # evitar sobrescrever os campos de tanque do próprio RDO a partir do
        # modal, pois isso pode dar a impressão de que um tanque foi
        # "substituído" — na verdade os tanques são entradas separadas.
        is_update = getattr(rdo_obj, 'id', None) is not None
        if not is_update:
            rdo_obj.nome_tanque = _clean(request.POST.get('tanque_nome')) or rdo_obj.nome_tanque
            rdo_obj.tanque_codigo = _clean(request.POST.get('tanque_codigo')) or rdo_obj.tanque_codigo
            rdo_obj.tipo_tanque = _clean(request.POST.get('tipo_tanque')) or rdo_obj.tipo_tanque
            # Número de compartimentos: permitir definir apenas quando ainda não existe
        # (comportamento: o que for definido no primeiro RDO permanece e não pode ser alterado)
        # DEBUG: registrar quais chaves/valores estão sendo enviadas no POST/JSON
        try:
            try:
                post_keys = list(request.POST.keys()) if hasattr(request, 'POST') else []
            except Exception:
                post_keys = []
            logger.info('DEBUG _apply_post_to_rdo incoming POST keys: %s', post_keys)
            # se o corpo vier em JSON, tentar logar as chaves do JSON para ajudar no debug
            try:
                if request.content_type and 'json' in (request.content_type or '').lower():
                    import json as _json
                    try:
                        body = request.body.decode('utf-8') if hasattr(request, 'body') else None
                        jb = _json.loads(body) if body else None
                        if isinstance(jb, dict):
                            logger.info('DEBUG _apply_post_to_rdo incoming JSON keys: %s', list(jb.keys()))
                        else:
                            logger.info('DEBUG _apply_post_to_rdo incoming JSON payload (non-dict)')
                    except Exception:
                        logger.info('DEBUG _apply_post_to_rdo could not parse request.body as JSON')
            except Exception:
                pass
        except Exception:
            try:
                logger.exception('DEBUG failed to log incoming POST keys')
            except Exception:
                pass

        # Número de compartimentos: permitir definir apenas quando ainda não existe
        num_comp = _clean(request.POST.get('numero_compartimento'))
        parsed_num = None
        if num_comp is not None:
            try:
                parsed_num = int(num_comp)
            except Exception:
                parsed_num = None

        if parsed_num is not None:
            try:
                # Valor atual no objeto (None/0/'' => não definido)
                cur = getattr(rdo_obj, 'numero_compartimentos', None)
                # Só atribuir quando não houver valor pré-existente (preservar o primeiro valor)
                if not cur:
                    rdo_obj.numero_compartimentos = parsed_num
            except Exception:
                # em caso de falha, não interromper fluxo
                pass

        # Persistir valores por-compartimento recebidos no POST (hidden inputs do frontend)
        try:
            total_n = 0
            try:
                total_n = int(getattr(rdo_obj, 'numero_compartimentos') or parsed_num or 0)
            except Exception:
                total_n = 0
            comps = {}
            for i in range(1, (total_n or 0) + 1):
                keyM = f'compartimento_avanco_mecanizada_{i}'
                keyF = f'compartimento_avanco_fina_{i}'
                vM = request.POST.get(keyM)
                vF = request.POST.get(keyF)
                # DEBUG: log valores brutos recebidos por compartimento
                try:
                    logger.info('DEBUG compartment %s received: %s=%s ; %s=%s', i, keyM, repr(vM), keyF, repr(vF))
                except Exception:
                    pass
                try:
                    mval = int(float(vM)) if (vM not in (None, '')) else 0
                except Exception:
                    mval = 0
                try:
                    fval = int(float(vF)) if (vF not in (None, '')) else 0
                except Exception:
                    fval = 0
                try:
                    mval = max(0, min(100, int(mval)))
                except Exception:
                    mval = 0
                try:
                    fval = max(0, min(100, int(fval)))
                except Exception:
                    fval = 0
                comps[str(i)] = {'mecanizada': mval, 'fina': fval}
            if comps:
                try:
                    rdo_obj.compartimentos_avanco_json = json.dumps(comps, ensure_ascii=False)
                    logger.info('DEBUG serialized compartimentos_avanco_json: %s', rdo_obj.compartimentos_avanco_json)
                except Exception:
                    logger.exception('Falha serializando compartimentos_avanco_json')
                # --- Calcular avanco_limpeza server-side a partir dos compartimentos ---
                try:
                    # soma dos avanços mecanizados e contagem de compartimentos limpos (>0)
                    sum_mec = 0
                    cleaned_count = 0
                    for k, v in (comps or {}).items():
                        try:
                            mv = int(v.get('mecanizada', 0) if isinstance(v, dict) else 0)
                        except Exception:
                            try:
                                mv = int(float(v))
                            except Exception:
                                mv = 0
                        if mv > 0:
                            cleaned_count += 1
                            sum_mec += mv
                    mirror_val = (float(sum_mec) / float(cleaned_count)) if cleaned_count > 0 else 0.0
                    # arredondar para 2 casas
                    mirror_val = round(mirror_val, 2)
                    mirror_str = f"{mirror_val:.2f}"
                    logger.info('DEBUG computed mirror_val=%s cleaned_count=%s sum_mec=%s mirror_str=%s', mirror_val, cleaned_count, sum_mec, mirror_str)
                    # atribuir ao campo legado textual (avanco_limpeza) para compatibilidade
                    try:
                        if hasattr(rdo_obj, 'avanco_limpeza'):
                            rdo_obj.avanco_limpeza = mirror_str
                    except Exception:
                        pass
                    # atribuir ao campo canônico/decimal para cálculos posteriores
                    try:
                        if hasattr(rdo_obj, 'percentual_limpeza_diario'):
                            rdo_obj.percentual_limpeza_diario = Decimal(str(mirror_val))
                        elif hasattr(rdo_obj, 'limpeza_mecanizada_diaria'):
                            rdo_obj.limpeza_mecanizada_diaria = Decimal(str(mirror_val))
                    except Exception:
                        pass
                except Exception:
                    logger.exception('Erro calculando avanco_limpeza server-side')
        except Exception:
            logger.exception('Erro processando compartimentos_avanco do POST')

        # Campos seguintes: volume, servico, metodo, gavetas, patamar, operadores
        vol_exec = _clean(request.POST.get('volume_tanque_exec'))
        if vol_exec is not None:
            rdo_obj.volume_tanque_exec = vol_exec
        rdo_obj.servico_exec = _clean(request.POST.get('servico_exec')) or rdo_obj.servico_exec
        rdo_obj.metodo_exec = _clean(request.POST.get('metodo_exec')) or rdo_obj.metodo_exec

        gav = _clean(request.POST.get('gavetas'))
        if gav is not None:
            try:
                rdo_obj.gavetas = int(gav)
            except Exception:
                pass
        pat = _clean(request.POST.get('patamar'))
        if pat is not None:
            try:
                rdo_obj.patamares = int(pat)
            except Exception:
                pass

        op_sim = _clean(request.POST.get('operadores_simultaneos'))
        if op_sim is not None:
            try:
                rdo_obj.operadores_simultaneos = int(op_sim)
            except Exception:
                pass

        # Persistir previsões por-tanque quando um tanque existente for referenciado
        try:
            tanque_id_raw = _clean(request.POST.get('tanque_id') or request.POST.get('tank_id') or request.POST.get('tanqueId'))
            if tanque_id_raw is not None:
                try:
                    tanque_id_int = int(tanque_id_raw)
                except Exception:
                    tanque_id_int = None
                if tanque_id_int:
                    try:
                        tank_obj = RdoTanque.objects.get(pk=tanque_id_int)

                        def _to_int_or_none(val):
                            if val in (None, ''):
                                return None
                            try:
                                return int(val)
                            except Exception:
                                try:
                                    return int(float(val))
                                except Exception:
                                    return None

                        # Prefer POST, fallback to parsed JSON body
                        ens_val = _get_post_or_json('ensacamento_prev') or request.POST.get('ensacamento_prev')
                        ic_val = _get_post_or_json('icamento_prev') or request.POST.get('icamento_prev')
                        camb_val = _get_post_or_json('cambagem_prev') or request.POST.get('cambagem_prev')

                        ens_i = _to_int_or_none(ens_val)
                        ic_i = _to_int_or_none(ic_val)
                        camb_i = _to_int_or_none(camb_val)

                        updated = False
                        if ens_i is not None:
                            tank_obj.ensacamento_prev = ens_i
                            updated = True
                        if ic_i is not None:
                            tank_obj.icamento_prev = ic_i
                            updated = True
                        if camb_i is not None:
                            tank_obj.cambagem_prev = camb_i
                            updated = True

                        if updated:
                            try:
                                _safe_save_global(tank_obj)
                                logger.info('Updated RdoTanque(id=%s) predictions ens=%s ic=%s camb=%s', tank_obj.id, ens_i, ic_i, camb_i)
                            except Exception:
                                # fallback to simple save
                                try:
                                    tank_obj.save()
                                except Exception:
                                    logger.exception('Failed to save RdoTanque predictions for id=%s', tanque_id_int)

                        # Persistir também campos de limpeza por-tanque (quando fornecidos)
                        try:
                            def _to_decimal_or_none(val):
                                if val in (None, ''):
                                    return None
                                try:
                                    return Decimal(str(float(val)))
                                except Exception:
                                    try:
                                        return Decimal(str(val))
                                    except Exception:
                                        return None

                            # mecanizada diário (decimal) - aceitar vários nomes de POST/JSON
                            raw_mec_daily = _get_post_or_json('limpeza_mecanizada_diaria') or _get_post_or_json('percentual_limpeza_diario') or _get_post_or_json('sup-limp') or _get_post_or_json('percentual_limpeza')
                            parsed_mec_daily = _to_decimal_or_none(raw_mec_daily)

                            # mecanizada cumulativo (int)
                            raw_mec_acu = _get_post_or_json('limpeza_mecanizada_cumulativa') or _get_post_or_json('sup-limp-acu') or _get_post_or_json('percentual_limpeza_cumulativo')
                            try:
                                parsed_mec_acu = int(float(raw_mec_acu)) if raw_mec_acu not in (None, '') else None
                            except Exception:
                                parsed_mec_acu = None

                            # limpeza fina diário (decimal)
                            raw_fina_daily = _get_post_or_json('percentual_limpeza_fina') or _get_post_or_json('percentual_limpeza_fina_diario') or _get_post_or_json('sup-limp-fina') or _get_post_or_json('limpeza_fina_diaria')
                            parsed_fina_daily = _to_decimal_or_none(raw_fina_daily)

                            # limpeza fina cumulativo (int)
                            raw_fina_acu = _get_post_or_json('limpeza_fina_cumulativa') or _get_post_or_json('sup-limp-fina-acu') or _get_post_or_json('percentual_limpeza_fina_cumulativo')
                            try:
                                parsed_fina_acu = int(float(raw_fina_acu)) if raw_fina_acu not in (None, '') else None
                            except Exception:
                                parsed_fina_acu = None

                            cleaning_updated = False
                            # atribuir se o campo existir no modelo RdoTanque
                            # 1) gravar os quatro campos solicitados por tanque
                            if parsed_mec_daily is not None and hasattr(tank_obj, 'limpeza_mecanizada_diaria'):
                                try:
                                    # padronizar para Decimal com 2 casas (ROUND_HALF_UP)
                                    try:
                                        tank_obj.limpeza_mecanizada_diaria = parsed_mec_daily.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                    except Exception:
                                        # fallback: criar Decimal e quantize
                                        try:
                                            tank_obj.limpeza_mecanizada_diaria = Decimal(str(float(parsed_mec_daily))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                        except Exception:
                                            tank_obj.limpeza_mecanizada_diaria = parsed_mec_daily
                                    cleaning_updated = True
                                except Exception:
                                    logger.exception('Falha ao atribuir limpeza_mecanizada_diaria ao RdoTanque %s', tanque_id_int)
                            if parsed_mec_acu is not None and hasattr(tank_obj, 'limpeza_mecanizada_cumulativa'):
                                try:
                                    tank_obj.limpeza_mecanizada_cumulativa = max(0, min(100, int(parsed_mec_acu)))
                                    cleaning_updated = True
                                except Exception:
                                    logger.exception('Falha ao atribuir limpeza_mecanizada_cumulativa ao RdoTanque %s', tanque_id_int)
                            if parsed_fina_daily is not None and hasattr(tank_obj, 'percentual_limpeza_fina'):
                                try:
                                    # campo inteiro por especificação
                                    tank_obj.percentual_limpeza_fina = max(0, min(100, int(round(float(parsed_fina_daily)))))
                                    cleaning_updated = True
                                except Exception:
                                    logger.exception('Falha ao atribuir percentual_limpeza_fina ao RdoTanque %s', tanque_id_int)
                            # também aceitar e gravar o valor decimal fino no campo canônico, quando existir
                            if parsed_fina_daily is not None and hasattr(tank_obj, 'limpeza_fina_diaria'):
                                try:
                                    try:
                                        tank_obj.limpeza_fina_diaria = parsed_fina_daily.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                    except Exception:
                                        try:
                                            tank_obj.limpeza_fina_diaria = Decimal(str(float(parsed_fina_daily))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                        except Exception:
                                            tank_obj.limpeza_fina_diaria = parsed_fina_daily
                                    cleaning_updated = True
                                except Exception:
                                    logger.exception('Falha ao atribuir limpeza_fina_diaria ao RdoTanque %s', tanque_id_int)
                            if parsed_fina_acu is not None and hasattr(tank_obj, 'percentual_limpeza_fina_cumulativo'):
                                try:
                                    tank_obj.percentual_limpeza_fina_cumulativo = max(0, min(100, int(parsed_fina_acu)))
                                    cleaning_updated = True
                                except Exception:
                                    logger.exception('Falha ao atribuir percentual_limpeza_fina_cumulativo ao RdoTanque %s', tanque_id_int)

                            # 2) manter compat com campos percentuais derivados existentes (não são parte dos 4, mas úteis)
                            if parsed_mec_daily is not None and hasattr(tank_obj, 'percentual_limpeza_diario'):
                                try:
                                    try:
                                        tank_obj.percentual_limpeza_diario = parsed_mec_daily.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                    except Exception:
                                        try:
                                            tank_obj.percentual_limpeza_diario = Decimal(str(float(parsed_mec_daily))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                        except Exception:
                                            tank_obj.percentual_limpeza_diario = parsed_mec_daily
                                    cleaning_updated = True
                                except Exception:
                                    logger.exception('Falha ao atribuir percentual_limpeza_diario ao RdoTanque %s', tanque_id_int)
                            if parsed_mec_acu is not None and hasattr(tank_obj, 'percentual_limpeza_cumulativo'):
                                try:
                                    tank_obj.percentual_limpeza_cumulativo = max(0, min(100, int(parsed_mec_acu)))
                                    cleaning_updated = True
                                except Exception:
                                    logger.exception('Falha ao atribuir percentual_limpeza_cumulativo ao RdoTanque %s', tanque_id_int)
                            if parsed_fina_daily is not None and hasattr(tank_obj, 'percentual_limpeza_fina_diario'):
                                try:
                                    # padronizar decimal para 2 casas
                                    try:
                                        tank_obj.percentual_limpeza_fina_diario = parsed_fina_daily.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                    except Exception:
                                        try:
                                            tank_obj.percentual_limpeza_fina_diario = Decimal(str(float(parsed_fina_daily))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                        except Exception:
                                            tank_obj.percentual_limpeza_fina_diario = parsed_fina_daily
                                    cleaning_updated = True
                                except Exception:
                                    logger.exception('Falha ao atribuir percentual_limpeza_fina_diario ao RdoTanque %s', tanque_id_int)
                            if parsed_fina_acu is not None and hasattr(tank_obj, 'percentual_limpeza_fina_cumulativo'):
                                try:
                                    tank_obj.percentual_limpeza_fina_cumulativo = max(0, min(100, int(parsed_fina_acu)))
                                    cleaning_updated = True
                                except Exception:
                                    logger.exception('Falha ao atribuir percentual_limpeza_fina_cumulativo ao RdoTanque %s', tanque_id_int)

                            # Avanços textuais (compatibilidade), caso enviados
                            raw_avanco = _get_post_or_json('avanco_limpeza') or _get_post_or_json('sup-limp') or request.POST.get('avanco_limpeza')
                            if raw_avanco not in (None, '') and hasattr(tank_obj, 'avanco_limpeza'):
                                try:
                                    tank_obj.avanco_limpeza = str(raw_avanco)
                                    cleaning_updated = True
                                except Exception:
                                    pass
                            raw_avanco_fina = _get_post_or_json('avanco_limpeza_fina') or _get_post_or_json('sup-limp-fina') or request.POST.get('avanco_limpeza_fina')
                            if raw_avanco_fina not in (None, '') and hasattr(tank_obj, 'avanco_limpeza_fina'):
                                try:
                                    tank_obj.avanco_limpeza_fina = str(raw_avanco_fina)
                                    cleaning_updated = True
                                except Exception:
                                    pass

                            if cleaning_updated:
                                try:
                                    _safe_save_global(tank_obj)
                                    logger.info('Updated RdoTanque(id=%s) cleaning fields: mec_daily=%s mec_acu=%s fina=%s fina_acu=%s', tank_obj.id, parsed_mec_daily, parsed_mec_acu, parsed_fina_daily, parsed_fina_acu)
                                except Exception:
                                    try:
                                        tank_obj.save()
                                    except Exception:
                                        logger.exception('Failed to save RdoTanque cleaning fields for id=%s', tanque_id_int)
                            # Fallback/extra: garantir que campos decimais diários sejam preenchidos
                            # mesmo quando parsing anterior não os tenha gravado por algum motivo.
                            try:
                                # Fazer update direto no DB como fallback (contornar possíveis blocos do ORM na sessão)
                                update_values = {}
                                raw_mec = _get_post_or_json('limpeza_mecanizada_diaria') or _get_post_or_json('percentual_limpeza_diario') or _get_post_or_json('sup-limp')
                                if raw_mec not in (None, '') and hasattr(tank_obj, 'limpeza_mecanizada_diaria'):
                                    try:
                                        v = Decimal(str(float(raw_mec)))
                                        update_values['limpeza_mecanizada_diaria'] = v.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                    except Exception:
                                        pass
                                raw_fina = _get_post_or_json('limpeza_fina_diaria') or _get_post_or_json('percentual_limpeza_fina') or _get_post_or_json('sup-limp-fina')
                                if raw_fina not in (None, '') and hasattr(tank_obj, 'limpeza_fina_diaria'):
                                    try:
                                        v = Decimal(str(float(raw_fina)))
                                        update_values['limpeza_fina_diaria'] = v.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                    except Exception:
                                        pass
                                if update_values:
                                    try:
                                        RdoTanque.objects.filter(pk=tank_obj.pk).update(**update_values)
                                        # sincronizar objeto em memória
                                        try:
                                            tank_obj.refresh_from_db()
                                        except Exception:
                                            pass
                                    except Exception:
                                        logger.exception('DB-level update failed for limpeza daily fields on tank_id=%s', tanque_id_int)
                            except Exception:
                                logger.exception('Fallback DB update for daily cleaning fields failed for tank_id=%s', tanque_id_int)
                        except Exception:
                            logger.exception('Erro ao persistir campos de limpeza por-tanque para tanque_id=%s', tanque_id_raw)
                    except RdoTanque.DoesNotExist:
                        logger.info('tanque_id provided but RdoTanque not found: %s', tanque_id_int)
        except Exception:
            logger.exception('Erro ao persistir previsoes por-tanque a partir do POST')

        # Atmosfera – grava como decimal simples (strings aceitas pelo DecimalField)
        h2s_val = _clean(request.POST.get('h2s_ppm'))
        try:
            if hasattr(rdo_obj, 'h2s_ppm'):
                setattr(rdo_obj, 'h2s_ppm', h2s_val if h2s_val is not None else getattr(rdo_obj, 'h2s_ppm', None))
            elif hasattr(rdo_obj, 'H2S_ppm'):
                setattr(rdo_obj, 'H2S_ppm', h2s_val if h2s_val is not None else getattr(rdo_obj, 'H2S_ppm', None))
        except Exception:
            pass

        lel_val = _clean(request.POST.get('lel'))
        try:
            if hasattr(rdo_obj, 'lel'):
                setattr(rdo_obj, 'lel', lel_val if lel_val is not None else getattr(rdo_obj, 'lel', None))
            elif hasattr(rdo_obj, 'LEL'):
                setattr(rdo_obj, 'LEL', lel_val if lel_val is not None else getattr(rdo_obj, 'LEL', None))
        except Exception:
            pass

        co_val = _clean(request.POST.get('co_ppm'))
        try:
            if hasattr(rdo_obj, 'co_ppm'):
                setattr(rdo_obj, 'co_ppm', co_val if co_val is not None else getattr(rdo_obj, 'co_ppm', None))
            elif hasattr(rdo_obj, 'CO_ppm'):
                setattr(rdo_obj, 'CO_ppm', co_val if co_val is not None else getattr(rdo_obj, 'CO_ppm', None))
        except Exception:
            pass

        o2_val = _clean(request.POST.get('o2_percent'))
        try:
            if hasattr(rdo_obj, 'o2_percent'):
                setattr(rdo_obj, 'o2_percent', o2_val if o2_val is not None else getattr(rdo_obj, 'o2_percent', None))
            elif hasattr(rdo_obj, 'O2_percent'):
                setattr(rdo_obj, 'O2_percent', o2_val if o2_val is not None else getattr(rdo_obj, 'O2_percent', None))
        except Exception:
            pass

        # Bombeio / cálculo de vazão/quantidade bombeada será tratado mais abaixo

        total_liq = _clean(request.POST.get('residuo_liquido'))
        if total_liq is not None:
            try:
                rdo_obj.total_liquido = int(float(total_liq))
            except ValueError:
                pass
        ensac = _clean(request.POST.get('ensacamento_dia'))
        if ensac is not None:
            try:
                rdo_obj.ensacamento = int(ensac)
            except ValueError:
                pass
        tamb = _clean(request.POST.get('tambores_dia'))
        if tamb is not None:
            try:
                rdo_obj.tambores = int(tamb)
            except ValueError:
                pass
        # ---------------- Percentuais e campos de previsão/acumulados ----------------
        # Mapear vários campos do formulário para atributos do modelo de forma segura.
        def _parse_percent(val, as_int=False, clamp=True):
            """Remove '%' e espaços, aceita decimal com vírgula ou ponto.
               Retorna Decimal (quando as_int=False) ou int (quando as_int=True) ou None.
               Quando as_int=True, por padrão aplica clamp 0..100; passe clamp=False para
               permitir inteiros além desse intervalo (útil para campos de previsão como
               ensacamento_previsao/icamento_previsao/cambagem_previsao).
            """
            if val is None:
                return None
            s = str(val).strip()
            if not s:
                return None
            # remover sinal de porcentagem se existir
            if s.endswith('%'):
                s = s[:-1].strip()
            # substituir vírgula por ponto para casas decimais
            s = s.replace(',', '.')
            try:
                if as_int:
                    v = int(float(s))
                    if clamp:
                        # limitar entre 0 e 100 para percentuais inteiros
                        if v < 0:
                            v = 0
                        if v > 100:
                            v = 100
                    return v
                else:
                    # Decimal com até 2 casas
                    d = Decimal(str(float(s)))
                    return d
            except Exception:
                return None

        # Definir um mapeamento (nome_post, nome_modelo, tipo) onde tipo é 'int' ou 'decimal'
        percent_map = [
            ('avanco_limpeza', 'percentual_limpeza_diario', 'decimal'),
            # Aceitar também nomes enviados pelo frontend legacy / supervisor modal
            ('sup-limp', 'percentual_limpeza_diario', 'decimal'),
            ('sup-limp-acu', 'limpeza_mecanizada_cumulativa', 'int'),
            ('sup-limp-fina', 'limpeza_fina_diaria', 'decimal'),
            ('sup-limp-fina-acu', 'limpeza_fina_cumulativa', 'int'),
            ('avanco_limpeza_fina', 'percentual_limpeza_fina', 'int'),
            ('limpeza_acu', 'percentual_limpeza_cumulativo', 'int'),
            ('limpeza_fina_acu', 'percentual_limpeza_fina_cumulativo', 'int'),
            ('ensacamento_prev', 'ensacamento_previsao', 'int'),
            ('ensacamento_acu', 'ensacamento_cumulativo', 'int'),
            ('percentual_ensacamento', 'percentual_ensacamento', 'decimal'),
            ('icamento_dia', 'icamento', 'int'),
            ('icamento_prev', 'icamento_previsao', 'int'),
            ('icamento_acu', 'icamento_cumulativo', 'int'),
            ('percentual_icamento', 'percentual_icamento', 'decimal'),
            ('cambagem_dia', 'cambagem', 'int'),
            ('cambagem_prev', 'cambagem_previsao', 'int'),
            ('cambagem_acu', 'cambagem_cumulativo', 'int'),
            ('percentual_cambagem', 'percentual_cambagem', 'decimal'),
            ('pob', 'pob', 'int'),
            # Aceitar também nomes de POST que usem os nomes de campo do modelo
            ('percentual_avanco', 'percentual_avanco', 'int'),
            ('percentual_avanco_cumulativo', 'percentual_avanco_cumulativo', 'int'),
            # suportar envio direto por nome do modelo para percentuais já mapeados
            # aceitar envio direto para o novo campo canônico diário
            ('percentual_limpeza', 'percentual_limpeza_diario', 'decimal'),
            # Permitir que o cliente envie diretamente os campos canônicos (nome do campo == nome do POST)
            ('percentual_limpeza_diario', 'percentual_limpeza_diario', 'decimal'),
            ('percentual_limpeza_fina_diario', 'percentual_limpeza_fina_diario', 'decimal'),
            ('percentual_limpeza_cumulativo', 'limpeza_mecanizada_cumulativa', 'int'),
            ('percentual_limpeza_fina', 'percentual_limpeza_fina', 'int'),
            ('percentual_limpeza_fina_cumulativo', 'percentual_limpeza_fina_cumulativo', 'int'),
            ('ensacamento_cumulativo', 'ensacamento_cumulativo', 'int'),
            ('ensacamento_previsao', 'ensacamento_previsao', 'int'),
            ('icamento', 'icamento', 'int'),
            ('icamento_cumulativo', 'icamento_cumulativo', 'int'),
            ('icamento_previsao', 'icamento_previsao', 'int'),
            ('cambagem', 'cambagem', 'int'),
            ('cambagem_cumulativo', 'cambagem_cumulativo', 'int'),
            ('cambagem_previsao', 'cambagem_previsao', 'int'),
            ('percentual_ensacamento', 'percentual_ensacamento', 'decimal'),
            ('percentual_icamento', 'percentual_icamento', 'decimal'),
            ('percentual_cambagem', 'percentual_cambagem', 'decimal'),
        ]

        # Campos inteiros que representam "previsões" e não devem ser limitados a 0..100
        _UNCLAMPED_INT_POST_NAMES = set([
            'ensacamento_prev', 'ensacamento_previsao',
            'icamento_prev', 'icamento_previsao',
            'cambagem_prev', 'cambagem_previsao',
        ])

        for post_name, model_name, typ in percent_map:
            try:
                raw = _clean(_get_post_or_json(post_name))
                if raw is None:
                    continue
                # decidir se aplicamos clamp 0..100 a inteiros
                if typ == 'int':
                    clamp_flag = False if (post_name in _UNCLAMPED_INT_POST_NAMES or model_name in _UNCLAMPED_INT_POST_NAMES) else True
                    parsed = _parse_percent(raw, as_int=True, clamp=clamp_flag)
                else:
                    parsed = _parse_percent(raw, as_int=False)
                if parsed is None:
                    continue
                if hasattr(rdo_obj, model_name):
                    try:
                        setattr(rdo_obj, model_name, parsed)
                    except Exception:
                        # tentar conversão alternativa para DecimalField
                        try:
                            if typ == 'decimal':
                                setattr(rdo_obj, model_name, Decimal(str(parsed)))
                            else:
                                setattr(rdo_obj, model_name, int(parsed))
                        except Exception:
                            logging.getLogger(__name__).exception('Falha atribuindo %s=%s ao RDO', model_name, parsed)
            except Exception:
                logging.getLogger(__name__).exception('Erro ao processar campo %s', post_name)

            # DEBUG: log valores dos campos de limpeza após o mapeamento inicial
            try:
                logger.info('_apply_post_to_rdo after percent_map - current limpeza values: percentual_limpeza=%s, percentual_limpeza_diario=%s, percentual_limpeza_fina=%s, limpeza_fina_diaria=%s',
                            getattr(rdo_obj, 'percentual_limpeza', None), getattr(rdo_obj, 'percentual_limpeza_diario', None), getattr(rdo_obj, 'percentual_limpeza_fina', None), getattr(rdo_obj, 'limpeza_fina_diaria', None))
            except Exception:
                logger.exception('Falha ao logar valores de limpeza após percent_map')

        # Compatibilidade: garantir que valores enviados pelo Supervisor (sup-limp / sup-limp-fina)
        # também profiram os campos principais de percentual quando aplicável.
        try:
            # Limpeza mecanizada diário -> percentual_limpeza_diario (canônico)
            raw_sup_limp = _clean(_get_post_or_json('sup-limp') or _get_post_or_json('percentual_limpeza') or _get_post_or_json('avanco_limpeza'))
            if raw_sup_limp is not None:
                parsed_sup_limp = _parse_percent(raw_sup_limp, as_int=False)
                if parsed_sup_limp is not None:
                    try:
                        # atribuir ao campo canônico diário
                        if hasattr(rdo_obj, 'percentual_limpeza_diario'):
                            try:
                                rdo_obj.percentual_limpeza_diario = parsed_sup_limp
                                logger.info('_apply_post_to_rdo assigned percentual_limpeza_diario from sup-limp: %s', parsed_sup_limp)
                            except Exception:
                                logger.exception('Falha atribuindo percentual_limpeza_diario a partir de sup-limp')
                        # também preencher o campo legado do editor (limpeza_mecanizada_diaria) quando vazio
                        if hasattr(rdo_obj, 'limpeza_mecanizada_diaria') and getattr(rdo_obj, 'limpeza_mecanizada_diaria', None) in (None, ''):
                            try:
                                rdo_obj.limpeza_mecanizada_diaria = parsed_sup_limp
                            except Exception:
                                pass
                    except Exception:
                        logger.exception('Erro tratando sup-limp')

            # Limpeza fina diário -> percentual_limpeza_fina (Decimal)
            raw_sup_limp_f = _clean(_get_post_or_json('sup-limp-fina') or _get_post_or_json('percentual_limpeza_fina') or _get_post_or_json('avanco_limpeza_fina'))
            if raw_sup_limp_f is not None:
                parsed_sup_limp_f = _parse_percent(raw_sup_limp_f, as_int=False)
                if parsed_sup_limp_f is not None:
                    try:
                        # Atribuir ao campo canônico diário e ao campo de input do editor quando aplicável
                        if hasattr(rdo_obj, 'percentual_limpeza_fina_diario'):
                            try:
                                rdo_obj.percentual_limpeza_fina_diario = parsed_sup_limp_f
                                logger.info('_apply_post_to_rdo assigned percentual_limpeza_fina_diario from sup-limp-fina: %s', parsed_sup_limp_f)
                            except Exception:
                                logger.exception('Falha atribuindo percentual_limpeza_fina_diario a partir de sup-limp-fina')
                        if hasattr(rdo_obj, 'limpeza_fina_diaria') and getattr(rdo_obj, 'limpeza_fina_diaria', None) in (None, ''):
                            try:
                                rdo_obj.limpeza_fina_diaria = parsed_sup_limp_f
                            except Exception:
                                pass
                    except Exception:
                        logger.exception('Erro tratando sup-limp-fina')
        except Exception:
            logger.exception('Erro sincronizando campos sup-limp para percentuais principais')
        try:
            logger.info('_apply_post_to_rdo after sup-limp compatibility assignments: percentual_limpeza=%s (type=%s), percentual_limpeza_diario=%s, percentual_limpeza_fina=%s, limpeza_fina_diaria=%s',
                        getattr(rdo_obj, 'percentual_limpeza', None), type(getattr(rdo_obj, 'percentual_limpeza', None)).__name__ if getattr(rdo_obj, 'percentual_limpeza', None) is not None else 'None',
                        getattr(rdo_obj, 'percentual_limpeza_diario', None), getattr(rdo_obj, 'percentual_limpeza_fina', None), getattr(rdo_obj, 'limpeza_fina_diaria', None))
        except Exception:
            logger.exception('Falha ao logar valores de limpeza apos compatibilidade sup-limp')

        # Se o Supervisor forneceu campos de limpeza no formulário do RDO,
        # replicar esses valores para os RdoTanque associados a este RDO.
        # Regra: se o POST/JSON incluiu qualquer um dos campos de limpeza usados
        # pelo editor/modal, copiar os campos correspondentes do `rdo_obj` para
        # cada `RdoTanque` ligado a este RDO (substituindo valores existentes).
        try:
            copy_post_names = [
                'sup-limp', 'sup-limp-acu', 'sup-limp-fina', 'sup-limp-fina-acu',
                'avanco_limpeza', 'avanco_limpeza_fina',
                'percentual_limpeza_diario', 'limpeza_mecanizada_diaria', 'limpeza_mecanizada_cumulativa',
                'limpeza_fina_diaria', 'limpeza_fina_cumulativa'
            ]
            should_copy = False
            for pn in copy_post_names:
                try:
                    if _get_post_or_json(pn) is not None or (hasattr(request, 'POST') and pn in request.POST):
                        should_copy = True
                        break
                except Exception:
                    continue

            if should_copy and getattr(rdo_obj, 'tanques', None) is not None:
                logger.info('_apply_post_to_rdo: copying limpeza fields from RDO to RdoTanque for rdo_id=%s', getattr(rdo_obj, 'id', None))
                # garantir import local de Decimal/rounding para uso nas conversões
                from decimal import Decimal, ROUND_HALF_UP
                # Identificar tanque_id enviado para evitar sobrescrever o tanque atualizado explicitamente
                try:
                    explicit_tank_id = None
                    raw_tid = _clean(request.POST.get('tanque_id') or request.POST.get('tank_id') or request.POST.get('tanqueId'))
                    if raw_tid is not None:
                        try:
                            explicit_tank_id = int(str(raw_tid))
                        except Exception:
                            explicit_tank_id = None
                except Exception:
                    explicit_tank_id = None
                fields_to_copy = [
                    'limpeza_mecanizada_diaria', 'limpeza_mecanizada_cumulativa',
                    'limpeza_fina_diaria', 'limpeza_fina_cumulativa',
                    'percentual_limpeza_diario', 'percentual_limpeza_fina_diario',
                    'percentual_limpeza_cumulativo', 'percentual_limpeza_fina_cumulativo',
                    'percentual_limpeza_fina',
                    'avanco_limpeza', 'avanco_limpeza_fina'
                ]
                try:
                    tank_qs = rdo_obj.tanques.all()
                except Exception:
                    tank_qs = []

                for tank in (tank_qs or []):
                    try:
                        # Se este tanque foi atualizado explicitamente via tanque_id no mesmo POST, não sobrescrevê-lo aqui
                        if explicit_tank_id and getattr(tank, 'id', None) == explicit_tank_id:
                            continue
                        updated = False
                        # Helpers locais de parsing (priorizar POST/JSON quando disponível)
                        def _to_decimal_or_none_local(v):
                            """Converte para Decimal e quantiza para 2 casas, retornando None quando inválido."""
                            if v in (None, ''):
                                return None
                            try:
                                s = str(v).strip().replace(',', '.')
                                d = Decimal(str(float(s)))
                                return d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                            except Exception:
                                try:
                                    d = Decimal(str(v))
                                    return d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                except Exception:
                                    return None

                        def _to_int_or_none_local(v):
                            if v in (None, ''):
                                return None
                            try:
                                return int(float(v))
                            except Exception:
                                try:
                                    return int(v)
                                except Exception:
                                    return None

                        # mapear e preferir valores enviados no POST/JSON para cada campo
                        try:
                            # limpeza mecanizada diaria
                            raw_mec_daily = _get_post_or_json('limpeza_mecanizada_diaria') or _get_post_or_json('percentual_limpeza_diario') or _get_post_or_json('sup-limp')
                            val_mec_daily = _to_decimal_or_none_local(raw_mec_daily) if raw_mec_daily is not None else getattr(rdo_obj, 'limpeza_mecanizada_diaria', None)
                            if val_mec_daily is not None and hasattr(tank, 'limpeza_mecanizada_diaria'):
                                try:
                                    tank.limpeza_mecanizada_diaria = val_mec_daily
                                    updated = True
                                except Exception:
                                    logger.exception('Falha atribuindo limpeza_mecanizada_diaria ao RdoTanque id=%s', getattr(tank, 'id', None))

                            # limpeza mecanizada cumulativa
                            raw_mec_acu = _get_post_or_json('limpeza_mecanizada_cumulativa') or _get_post_or_json('sup-limp-acu') or _get_post_or_json('percentual_limpeza_cumulativo')
                            val_mec_acu = _to_int_or_none_local(raw_mec_acu) if raw_mec_acu is not None else getattr(rdo_obj, 'limpeza_mecanizada_cumulativa', None)
                            if val_mec_acu is not None and hasattr(tank, 'limpeza_mecanizada_cumulativa'):
                                try:
                                    tank.limpeza_mecanizada_cumulativa = max(0, min(100, int(val_mec_acu)))
                                    updated = True
                                except Exception:
                                    logger.exception('Falha atribuindo limpeza_mecanizada_cumulativa ao RdoTanque id=%s', getattr(tank, 'id', None))

                            # limpeza fina diaria -> aqui mapeamos para percentual_limpeza_fina (inteiro por tanque)
                            raw_fina_daily = _get_post_or_json('limpeza_fina_diaria') or _get_post_or_json('percentual_limpeza_fina') or _get_post_or_json('sup-limp-fina')
                            val_fina_daily = _to_decimal_or_none_local(raw_fina_daily) if raw_fina_daily is not None else getattr(rdo_obj, 'limpeza_fina_diaria', None)
                            if val_fina_daily is not None and hasattr(tank, 'percentual_limpeza_fina'):
                                try:
                                    tank.percentual_limpeza_fina = max(0, min(100, int(round(float(val_fina_daily)))))
                                    updated = True
                                except Exception:
                                    logger.exception('Falha atribuindo percentual_limpeza_fina ao RdoTanque id=%s', getattr(tank, 'id', None))
                            # também gravar o valor decimal fino no campo canônico do tanque quando disponível
                            if val_fina_daily is not None and hasattr(tank, 'limpeza_fina_diaria'):
                                try:
                                    tank.limpeza_fina_diaria = val_fina_daily
                                    updated = True
                                except Exception:
                                    logger.exception('Falha atribuindo limpeza_fina_diaria ao RdoTanque id=%s', getattr(tank, 'id', None))

                            # limpeza fina cumulativa
                            raw_fina_acu = _get_post_or_json('limpeza_fina_cumulativa') or _get_post_or_json('sup-limp-fina-acu') or _get_post_or_json('percentual_limpeza_fina_cumulativo')
                            val_fina_acu = _to_int_or_none_local(raw_fina_acu) if raw_fina_acu is not None else getattr(rdo_obj, 'limpeza_fina_cumulativa', None)
                            if val_fina_acu is not None and hasattr(tank, 'percentual_limpeza_fina_cumulativo'):
                                try:
                                    tank.percentual_limpeza_fina_cumulativo = max(0, min(100, int(val_fina_acu)))
                                    updated = True
                                except Exception:
                                    logger.exception('Falha atribuindo percentual_limpeza_fina_cumulativo ao RdoTanque id=%s', getattr(tank, 'id', None))
                        except Exception:
                            logger.exception('Erro mapeando valores POST->RdoTanque durante replicacao')
                        # Derivações/mapeamentos entre nomes diferentes RDO -> Tank
                        try:
                            # percentual_limpeza_diario (tank) a partir de percentual_limpeza_diario ou limpeza_mecanizada_diaria (RDO)
                            if hasattr(tank, 'percentual_limpeza_diario'):
                                src = getattr(rdo_obj, 'percentual_limpeza_diario', None)
                                if src is None:
                                    src = getattr(rdo_obj, 'limpeza_mecanizada_diaria', None)
                                if src is not None:
                                    try:
                                        # garantir decimal com 2 casas
                                        if not isinstance(src, Decimal):
                                            try:
                                                tank.percentual_limpeza_diario = Decimal(str(src)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                            except Exception:
                                                tank.percentual_limpeza_diario = Decimal(str(src))
                                        else:
                                            tank.percentual_limpeza_diario = src
                                        updated = True
                                    except Exception:
                                        pass
                            # percentual_limpeza_cumulativo (tank) a partir de limpeza_mecanizada_cumulativa (RDO) ou percentual_limpeza_diario_cumulativo
                            if hasattr(tank, 'percentual_limpeza_cumulativo'):
                                ac = getattr(rdo_obj, 'limpeza_mecanizada_cumulativa', None)
                                if ac is None:
                                    try:
                                        ac_dec = getattr(rdo_obj, 'percentual_limpeza_diario_cumulativo', None)
                                        ac = int(round(float(ac_dec))) if ac_dec is not None else None
                                    except Exception:
                                        ac = None
                                if ac is not None:
                                    try:
                                        tank.percentual_limpeza_cumulativo = int(ac)
                                        updated = True
                                    except Exception:
                                        pass
                            # percentual_limpeza_fina_diario (tank) a partir de percentual_limpeza_fina_diario/limpeza_fina_diaria/percentual_limpeza_fina (RDO)
                            if hasattr(tank, 'percentual_limpeza_fina_diario'):
                                srcf = getattr(rdo_obj, 'percentual_limpeza_fina_diario', None)
                                if srcf is None:
                                    srcf = getattr(rdo_obj, 'limpeza_fina_diaria', None)
                                if srcf is None:
                                    srcf = getattr(rdo_obj, 'percentual_limpeza_fina', None)
                                if srcf is not None:
                                    try:
                                        # converter int para Decimal quando necessário
                                        # garantir decimal com 2 casas
                                        if not isinstance(srcf, Decimal):
                                            try:
                                                tank.percentual_limpeza_fina_diario = Decimal(str(srcf)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                            except Exception:
                                                tank.percentual_limpeza_fina_diario = Decimal(str(srcf))
                                        else:
                                            tank.percentual_limpeza_fina_diario = srcf
                                        updated = True
                                    except Exception:
                                        pass
                            # percentual_limpeza_fina (inteiro) no tank a partir de percentual_limpeza_fina (RDO) ou de percentual_limpeza_fina_diario/limpeza_fina_diaria
                            if hasattr(tank, 'percentual_limpeza_fina'):
                                srci = getattr(rdo_obj, 'percentual_limpeza_fina', None)
                                if srci is None:
                                    srci = getattr(rdo_obj, 'percentual_limpeza_fina_diario', None)
                                if srci is None:
                                    srci = getattr(rdo_obj, 'limpeza_fina_diaria', None)
                                if srci is not None:
                                    try:
                                        tank.percentual_limpeza_fina = int(round(float(srci)))
                                        updated = True
                                    except Exception:
                                        pass
                            # percentual_limpeza_fina_cumulativo (tank) a partir de limpeza_fina_cumulativa ou percentual_limpeza_fina_cumulativo (RDO)
                            if hasattr(tank, 'percentual_limpeza_fina_cumulativo'):
                                acf = getattr(rdo_obj, 'limpeza_fina_cumulativa', None)
                                if acf is None:
                                    acf = getattr(rdo_obj, 'percentual_limpeza_fina_cumulativo', None)
                                if acf is not None:
                                    try:
                                        tank.percentual_limpeza_fina_cumulativo = int(acf)
                                        updated = True
                                    except Exception:
                                        pass
                        except Exception:
                            logger.exception('Falha nas derivações de campos RDO->RdoTanque')
                        if updated:
                            try:
                                _safe_save_global(tank)
                            except Exception:
                                try:
                                    tank.save()
                                except Exception:
                                    logger.exception('Falha ao salvar RdoTanque id=%s ao copiar campos de limpeza', getattr(tank, 'id', None))
                    except Exception:
                        logger.exception('Erro ao copiar campos de limpeza para RdoTanque do RDO id=%s', getattr(rdo_obj, 'id', None))
        except Exception:
            logger.exception('Erro ao replicar campos de limpeza do RDO para RdoTanque')

        # Nota: cálculo/armazenamento do valor visível de limpeza foi
        # centralizado no modelo `RDO.compute_limpeza_from_compartimentos()`.
        # Removemos o processamento direto do campo espelho aqui para evitar
        # duplicação de lógica entre view/JS e model.

        # Campos numéricos / técnicos adicionais enviados diretamente com o mesmo nome do modelo
        try:
            # Alguns campos técnicos podem ser enviados diretamente pelo frontend.
            # Atenção: alguns nomes parecem TimeField no modelo (ex: total_hh_cumulativo_real,
            # hh_disponivel_cumulativo, total_hh_frente_real) enquanto outros são inteiros
            # (ex: total_n_efetivo_confinado). Tratar separadamente para evitar atribuir
            # inteiros a TimeFields (o que vinha impedindo a persistência).
            candidate_fields = ['total_hh_cumulativo_real', 'hh_disponivel_cumulativo', 'total_hh_frente_real', 'total_n_efetivo_confinado']
            time_fields = set(['total_hh_cumulativo_real', 'hh_disponivel_cumulativo', 'total_hh_frente_real'])

            def _parse_to_time(val):
                """Tenta converter val para datetime.time.
                Suporta formatos 'HH:MM' ou número de minutos (int/str/float).
                Retorna None se não for possível.
                """
                if val is None:
                    return None
                try:
                    if isinstance(val, str):
                        s = val.strip()
                        if not s:
                            return None
                        # formato HH:MM
                        if ':' in s:
                            try:
                                return datetime.strptime(s, '%H:%M').time()
                            except Exception:
                                # tentar parse flexível (H:M)
                                parts = s.split(':')
                                if len(parts) >= 2:
                                    try:
                                        h = int(parts[0]); m = int(parts[1])
                                        h = h % 24
                                        m = max(0, min(59, m))
                                        return dt_time(hour=h, minute=m)
                                    except Exception:
                                        return None
                        # se for numérico em string, cair abaixo para tratar como minutos
                    # tratar números (minutos)
                    try:
                        mins = int(float(str(val)))
                        if mins < 0:
                            return None
                        h = (mins // 60) % 24
                        m = mins % 60
                        return dt_time(hour=int(h), minute=int(m))
                    except Exception:
                        return None
                except Exception:
                    return None

            for f in candidate_fields:
                try:
                    raw = _clean(request.POST.get(f))
                    if raw is None:
                        continue
                    if f in time_fields:
                        # converter para time antes de atribuir
                        tval = _parse_to_time(raw)
                        if tval is None:
                            # se não conseguimos converter, pular
                            continue
                        if hasattr(rdo_obj, f):
                            try:
                                setattr(rdo_obj, f, tval)
                            except Exception:
                                logging.getLogger(__name__).exception('Falha atribuindo campo time %s', f)
                    else:
                        # tratar como inteiro (fallback para compatibilidade)
                        try:
                            parsed = int(float(str(raw)))
                        except Exception:
                            parsed = None
                        if parsed is None:
                            continue
                        if hasattr(rdo_obj, f):
                            try:
                                setattr(rdo_obj, f, parsed)
                            except Exception:
                                logging.getLogger(__name__).exception('Falha atribuindo campo inteiro %s', f)
                except Exception:
                    continue
        except Exception:
            logging.getLogger(__name__).exception('Erro processando extra_int_fields')

        # Campo textual de status técnico
        try:
            us = _clean(request.POST.get('ultimo_status'))
            if us is not None and hasattr(rdo_obj, 'ultimo_status'):
                try:
                    # limitar comprimento razoável
                    setattr(rdo_obj, 'ultimo_status', str(us)[:255])
                except Exception:
                    logging.getLogger(__name__).exception('Falha atribuindo ultimo_status')
        except Exception:
            pass

        # Se o usuário forneceu 'ensacamento_prev', replicar para 'icamento_prev' quando
        # o campo 'icamento_previsao' ainda estiver vazio no objeto (comportamento: preenchido apenas uma vez)
        try:
            ep_raw = _clean(request.POST.get('ensacamento_prev'))
            if ep_raw is not None:
                ep_parsed = _parse_percent(ep_raw, as_int=True)
                if ep_parsed is not None and hasattr(rdo_obj, 'icamento_previsao'):
                    cur = getattr(rdo_obj, 'icamento_previsao', None)
                    # só replicar quando o campo destino estiver vazio / None
                    if cur in (None, ''):
                        try:
                            setattr(rdo_obj, 'icamento_previsao', ep_parsed)
                        except Exception:
                            logging.getLogger(__name__).exception('Falha ao replicar ensacamento_previsao para icamento_previsao')
        except Exception:
            logging.getLogger(__name__).exception('Erro ao replicar ensacamento_prev -> icamento_previsao')
        # Total sólidos: prefer value sent by client, else compute from ensacamento_dia * 0.008
        tot_sol = _clean(request.POST.get('residuos_solidos'))
        assigned_total_solidos = False
        if tot_sol is not None:
            try:
                valf = float(tot_sol)
                # prefer Decimal storage when available (preserve two decimals)
                try:
                    rdo_obj.total_solidos = Decimal(str(round(valf, 2)))
                except Exception:
                    try:
                        rdo_obj.total_solidos = int(valf)
                    except Exception:
                        rdo_obj.total_solidos = Decimal(str(round(valf, 2)))
                assigned_total_solidos = True
            except Exception:
                assigned_total_solidos = False

        if not assigned_total_solidos:
            # attempt to compute from ensacamento (prefer object's ensacamento if already parsed)
            try:
                ens_val = None
                if getattr(rdo_obj, 'ensacamento', None) is not None:
                    try:
                        ens_val = float(getattr(rdo_obj, 'ensacamento'))
                    except Exception:
                        ens_val = None
                elif ensac is not None:
                    try:
                        ens_val = float(ensac)
                    except Exception:
                        ens_val = None

                if ens_val is not None:
                    computed = round(ens_val * 0.008, 2)
                    try:
                        rdo_obj.total_solidos = Decimal(str(computed))
                    except Exception:
                        try:
                            rdo_obj.total_solidos = int(computed) if float(computed).is_integer() else Decimal(str(computed))
                        except Exception:
                            # last resort: set as float
                            try:
                                rdo_obj.total_solidos = float(computed)
                            except Exception:
                                pass
            except Exception:
                pass
        tot_res = _clean(request.POST.get('residuos_totais'))
        if tot_res is not None:
            try:
                rdo_obj.total_residuos = int(float(tot_res))
            except ValueError:
                pass

        # Normalize sentido_limpeza inputs (may come as 'sentido' or 'sentido_limpeza')
        try:
            sentido_raw = _clean(_get_post_or_json('sentido') or _get_post_or_json('sentido_limpeza'))
        except Exception:
            sentido_raw = _clean(request.POST.get('sentido') or request.POST.get('sentido_limpeza'))
        if sentido_raw is not None:
            try:
                token = _canonicalize_sentido(sentido_raw)
            except Exception:
                token = None
            # atribuir o token canônico ao campo do modelo quando suportado
            try:
                if token is not None:
                    if hasattr(rdo_obj, 'sentido_limpeza'):
                        setattr(rdo_obj, 'sentido_limpeza', token)
                    elif hasattr(rdo_obj, 'sent_limpeza'):
                        setattr(rdo_obj, 'sent_limpeza', token)
                else:
                    # fallback: se não conseguimos canonicalizar, ainda gravar o valor bruto
                    if hasattr(rdo_obj, 'sentido_limpeza'):
                        try:
                            setattr(rdo_obj, 'sentido_limpeza', str(sentido_raw))
                        except Exception:
                            pass
                    elif hasattr(rdo_obj, 'sent_limpeza'):
                        try:
                            setattr(rdo_obj, 'sent_limpeza', str(sentido_raw))
                        except Exception:
                            pass
            except Exception:
                pass

        obs_pt = _clean(request.POST.get('observacoes'))
        if obs_pt is not None:
            rdo_obj.observacoes_rdo_pt = obs_pt
            # Atualizar a versão em inglês sempre que uma observação PT for enviada
            try:
                from deep_translator import GoogleTranslator
                try:
                    translated = GoogleTranslator(source='pt', target='en').translate(obs_pt)
                    rdo_obj.observacoes_rdo_en = translated
                except Exception:
                    # se a tradução falhar, manter o valor anterior sem interromper o salvamento
                    pass
            except Exception:
                # deep_translator pode não estar disponível; simplesmente ignorar
                pass
        # aceitar tanto 'planejamento' (supervisor form) quanto 'planejamento_pt' (editor fragment)
        plan_pt = _clean(request.POST.get('planejamento') or request.POST.get('planejamento_pt'))
        if plan_pt is not None:
            rdo_obj.planejamento_pt = plan_pt
            # Atualizar a versão em inglês sempre que um planejamento PT for enviado
            try:
                from deep_translator import GoogleTranslator
                try:
                    translated_plan = GoogleTranslator(source='pt', target='en').translate(plan_pt)
                    # só sobrescrever se tradução não for vazia
                    if translated_plan:
                        rdo_obj.planejamento_en = translated_plan
                except Exception:
                    # se a tradução falhar, manter o valor anterior sem interromper o salvamento
                    pass
            except Exception:
                # deep_translator pode não estar disponível; simplesmente ignorar
                pass

        # Novo campo: ciente das observações contratadas (PT -> EN automático)
        try:
            ciente_pt = _clean(request.POST.get('ciente_observacoes') or request.POST.get('ciente_observacoes_pt') or request.POST.get('ciente') or request.POST.get('ciente_pt'))
            if ciente_pt is not None:
                rdo_obj.ciente_observacoes_pt = ciente_pt
                # tentar traduzir automaticamente para inglês quando possível
                try:
                    from deep_translator import GoogleTranslator
                    try:
                        translated = GoogleTranslator(source='pt', target='en').translate(ciente_pt)
                        if translated:
                            rdo_obj.ciente_observacoes_en = translated
                    except Exception:
                        # não interromper se a tradução falhar
                        pass
                except Exception:
                    pass
        except Exception:
            logging.getLogger(__name__).exception('Erro processando campo ciente_observacoes')

        # Garantir que o objeto tenha PK antes de manipular relacionamentos
        # (ao criar um novo RDO, acessar rdo_obj.atividades_rdo sem PK causa ValueError)
        if not getattr(rdo_obj, 'pk', None):
                try:
                    # garantir vínculo com OS se possível antes do save inicial
                    if not getattr(rdo_obj, 'ordem_servico_id', None):
                        try:
                            ordem_servico_id = request.POST.get('ordem_servico_id') or request.POST.get('ordem_id')
                            if ordem_servico_id:
                                rdo_obj.ordem_servico = OrdemServico.objects.get(id=ordem_servico_id)
                        except Exception:
                            pass
                    if not getattr(rdo_obj, 'data', None):
                        try:
                            d = request.POST.get('data')
                            if d:
                                rdo_obj.data = datetime.strptime(d, '%Y-%m-%d').date()
                        except Exception:
                            pass
                        # Se ainda não tem data definida, usar a data atual como data fixa do RDO
                        if not getattr(rdo_obj, 'data', None):
                            try:
                                rdo_obj.data = datetime.today().date()
                            except Exception:
                                pass
                    try:
                        _safe_save_global(rdo_obj)
                    except Exception as e:
                        try:
                            from django.db import IntegrityError as DjangoIntegrityError
                        except Exception:
                            DjangoIntegrityError = None
                        if DjangoIntegrityError is not None and isinstance(e, DjangoIntegrityError):
                            try:
                                logger = logging.getLogger(__name__)
                                logger.warning('IntegrityError when saving RDO initial save: %s. Attempting to load existing RDO.', e)
                                existing = None
                                try:
                                    if getattr(rdo_obj, 'ordem_servico', None) is not None and getattr(rdo_obj, 'rdo', None) is not None:
                                        existing = RDO.objects.filter(ordem_servico=getattr(rdo_obj, 'ordem_servico'), rdo=getattr(rdo_obj, 'rdo')).first()
                                except Exception:
                                    existing = None
                                if existing:
                                    logger.info('Found existing RDO (pk=%s) during initial save; reusing it.', getattr(existing, 'pk', None))
                                    rdo_obj = existing
                                else:
                                    logger.exception('IntegrityError saving initial RDO but no existing record found')
                                    raise
                            except Exception:
                                logger = logging.getLogger(__name__)
                                logger.exception('Error handling IntegrityError during initial RDO save')
                                raise
                        else:
                            logging.getLogger(__name__).exception('Falha ao salvar RDO antes de manipular atividades')
                            raise
                except Exception:
                    logging.getLogger(__name__).exception('Falha ao salvar RDO antes de manipular atividades')
                    raise

        # ---------------- Totais acumulados (ensacamento/icamento/cambagem) ----------------
        # Garantir que os totais acumulados sejam persistidos por RDO: somar todos os
        # valores anteriores da mesma OrdemServico e adicionar o valor deste RDO.
        try:
            ordem_obj = getattr(rdo_obj, 'ordem_servico', None)
            if ordem_obj is not None:
                prev_qs = RDO.objects.filter(ordem_servico=ordem_obj).exclude(pk=rdo_obj.pk)
                agg = prev_qs.aggregate(sum_ensac=Sum('ensacamento'), sum_ica=Sum('icamento'), sum_camba=Sum('cambagem'))
                prev_ens = int(agg.get('sum_ensac') or 0)
                prev_ica = int(agg.get('sum_ica') or 0)
                prev_camba = int(agg.get('sum_camba') or 0)

                cur_ens = 0
                try:
                    cur_ens = int(getattr(rdo_obj, 'ensacamento') or 0)
                except Exception:
                    cur_ens = 0
                cur_ica = 0
                try:
                    cur_ica = int(getattr(rdo_obj, 'icamento') or 0)
                except Exception:
                    cur_ica = 0
                cur_camba = 0
                try:
                    cur_camba = int(getattr(rdo_obj, 'cambagem') or 0)
                except Exception:
                    cur_camba = 0

                # Atribuir apenas se os campos existirem no modelo (compatibilidade)
                    try:
                        if hasattr(rdo_obj, 'ensacamento_cumulativo'):
                            rdo_obj.ensacamento_cumulativo = prev_ens + cur_ens
                        if hasattr(rdo_obj, 'icamento_cumulativo'):
                            rdo_obj.icamento_cumulativo = prev_ica + cur_ica
                        if hasattr(rdo_obj, 'cambagem_cumulativo'):
                            rdo_obj.cambagem_cumulativo = prev_camba + cur_camba
                        # Persistir imediatamente para garantir consistência entre RDOs
                        try:
                            _safe_save_global(rdo_obj)
                        except Exception as e:
                            try:
                                from django.db import IntegrityError as DjangoIntegrityError
                            except Exception:
                                DjangoIntegrityError = None
                            if DjangoIntegrityError is not None and isinstance(e, DjangoIntegrityError):
                                try:
                                    logger = logging.getLogger(__name__)
                                    logger.warning('IntegrityError when saving RDO totals: %s. Attempting to load existing RDO.', e)
                                    existing = None
                                    try:
                                        if getattr(rdo_obj, 'ordem_servico', None) is not None and getattr(rdo_obj, 'rdo', None) is not None:
                                            existing = RDO.objects.filter(ordem_servico=getattr(rdo_obj, 'ordem_servico'), rdo=getattr(rdo_obj, 'rdo')).first()
                                    except Exception:
                                        existing = None
                                    if existing:
                                        logger.info('Found existing RDO (pk=%s) when saving totals; reusing it.', getattr(existing, 'pk', None))
                                        rdo_obj = existing
                                    else:
                                        logger.exception('IntegrityError saving RDO totals but no existing record found')
                                        raise
                                except Exception:
                                    logger = logging.getLogger(__name__)
                                    logger.exception('Error handling IntegrityError during RDO totals save')
                                    raise
                            else:
                                logging.getLogger(__name__).exception('Falha ao atribuir/salvar totais acumulados do RDO')
                    except Exception:
                        logging.getLogger(__name__).exception('Falha ao atribuir/salvar totais acumulados do RDO')
        except Exception:
            logging.getLogger(__name__).exception('Erro ao calcular totais acumulados para RDO')

        # ---------------- Totais acumulados para Limpeza (Mecanizada) e Limpeza Fina ----------------
        # Calcular os acumulados de limpeza de forma *autoritativa* no servidor: somar os
        # percentuais DIÁRIOS (`percentual_limpeza`, `percentual_limpeza_fina`) dos RDOs
        # anteriores da mesma OrdemServico e adicionar o valor diário deste RDO.
        # Isso garante que o acumulado sempre conte com os RDOs anteriores e possa
        # chegar a 100% ao longo do tempo. Valores finais são armazenados como int
        # percentuais (0..100) em `percentual_limpeza_cumulativo` e
        # `percentual_limpeza_fina_cumulativo` quando estes campos existirem no modelo.
        try:
            ordem_obj = getattr(rdo_obj, 'ordem_servico', None)
            if ordem_obj is not None:
                # Permitir override explícito enviado pelo cliente para os acumulados
                raw_limpeza_acu = _clean(_get_post_or_json('limpeza_acu') or _get_post_or_json('percentual_limpeza_cumulativo'))
                raw_limpeza_fina_acu = _clean(_get_post_or_json('limpeza_fina_acu') or _get_post_or_json('percentual_limpeza_fina_cumulativo'))

                # Se o cliente forneceu um acumulado explícito, usá-lo (quando válido)
                def _try_parse_int(v):
                    try:
                        if v is None:
                            return None
                        return int(float(str(v)))
                    except Exception:
                        return None

                provided_limpeza_acu = _try_parse_int(raw_limpeza_acu)
                provided_limpeza_fina_acu = _try_parse_int(raw_limpeza_fina_acu)

                if provided_limpeza_acu is not None or provided_limpeza_fina_acu is not None:
                    # aplicar overrides quando enviados
                    try:
                        # armazenar override no campo de acumulado preferido
                        if provided_limpeza_acu is not None and hasattr(rdo_obj, 'limpeza_mecanizada_cumulativa'):
                            v = max(0, min(100, provided_limpeza_acu))
                            rdo_obj.limpeza_mecanizada_cumulativa = v
                        if provided_limpeza_fina_acu is not None and hasattr(rdo_obj, 'percentual_limpeza_fina_cumulativo'):
                            v2 = max(0, min(100, provided_limpeza_fina_acu))
                            rdo_obj.percentual_limpeza_fina_cumulativo = v2
                        _safe_save_global(rdo_obj)
                    except Exception:
                        logging.getLogger(__name__).exception('Falha ao aplicar override de acumulados de limpeza do RDO')
                else:
                    # Calcular acumulados de limpeza de forma *autoritativa* no servidor:
                    prev_qs = RDO.objects.filter(ordem_servico=ordem_obj).exclude(pk=rdo_obj.pk)
                    # Somar os percentuais DIÁRIOS canônicos
                    agg = prev_qs.aggregate(sum_prev_limpeza=Sum('percentual_limpeza_diario'), sum_prev_limpeza_fina=Sum('percentual_limpeza_fina'))
                    prev_sum_limpeza = float(agg.get('sum_prev_limpeza') or 0)
                    prev_sum_limpeza_fina = float(agg.get('sum_prev_limpeza_fina') or 0)

                    # obter os percentuais DIÁRIOS deste RDO (já parseados acima pelo percent_map)
                    try:
                        cur_daily_limpeza = float(getattr(rdo_obj, 'percentual_limpeza_diario') or getattr(rdo_obj, 'limpeza_mecanizada_diaria', 0) or 0)
                    except Exception:
                        cur_daily_limpeza = 0.0
                    try:
                        cur_daily_limpeza_fina = float(getattr(rdo_obj, 'percentual_limpeza_fina') or 0)
                    except Exception:
                        cur_daily_limpeza_fina = 0.0

                    # Somar percentuais diários anteriores + atual (unidade: percentuais 0..100)
                    total_limpeza_pct = prev_sum_limpeza + cur_daily_limpeza
                    total_limpeza_fina_pct = prev_sum_limpeza_fina + cur_daily_limpeza_fina

                    # Normalizar/limitar entre 0 e 100
                    try:
                        total_limpeza_pct_i = int(round(total_limpeza_pct))
                    except Exception:
                        total_limpeza_pct_i = 0
                    try:
                        total_limpeza_fina_pct_i = int(round(total_limpeza_fina_pct))
                    except Exception:
                        total_limpeza_fina_pct_i = 0
                    total_limpeza_pct_i = max(0, min(100, total_limpeza_pct_i))
                    total_limpeza_fina_pct_i = max(0, min(100, total_limpeza_fina_pct_i))

                    try:
                        # atribuir aos campos cumulativos preferidos
                        if hasattr(rdo_obj, 'limpeza_mecanizada_cumulativa'):
                            rdo_obj.limpeza_mecanizada_cumulativa = total_limpeza_pct_i
                        if hasattr(rdo_obj, 'percentual_limpeza_fina_cumulativo'):
                            rdo_obj.percentual_limpeza_fina_cumulativo = total_limpeza_fina_pct_i
                        # Persistir imediatamente
                        _safe_save_global(rdo_obj)
                    except Exception:
                        logging.getLogger(__name__).exception('Falha ao atribuir/salvar acumulados de limpeza do RDO')
        except Exception:
            logging.getLogger(__name__).exception('Erro ao calcular acumulados de limpeza para RDO')
        # ---------------- Percentuais calculados (ensacamento/icamento/cambagem e avanco) ----------------
        # Calcular no servidor os percentuais derivados para manter paridade com o frontend.
        try:
            from decimal import Decimal, ROUND_HALF_UP
            def _to_decimal_safe(v):
                try:
                    if v is None:
                        return Decimal('0')
                    return Decimal(str(v))
                except Exception:
                    try:
                        return Decimal(float(v))
                    except Exception:
                        return Decimal('0')

            # Valores acumulados e previsões (preferir campos cumulativos quando presentes)
            ensac_cum = _to_decimal_safe(getattr(rdo_obj, 'ensacamento_cumulativo', None) or getattr(rdo_obj, 'ensacamento', None) or 0)
            ensac_prev = _to_decimal_safe(getattr(rdo_obj, 'ensacamento_previsao', None) or 0)

            ic_cum = _to_decimal_safe(getattr(rdo_obj, 'icamento_cumulativo', None) or getattr(rdo_obj, 'icamento', None) or 0)
            ic_prev = _to_decimal_safe(getattr(rdo_obj, 'icamento_previsao', None) or 0)

            camb_cum = _to_decimal_safe(getattr(rdo_obj, 'cambagem_cumulativo', None) or getattr(rdo_obj, 'cambagem', None) or 0)
            camb_prev = _to_decimal_safe(getattr(rdo_obj, 'cambagem_previsao', None) or 0)

            def _clamp_pct(d):
                try:
                    if d is None:
                        return Decimal('0')
                    if d < 0:
                        return Decimal('0')
                    if d > 100:
                        return Decimal('100')
                    return d
                except Exception:
                    return Decimal('0')

            perc_ens = Decimal('0')
            if ensac_prev > 0:
                try:
                    perc_ens = (ensac_cum / ensac_prev) * Decimal('100')
                except Exception:
                    perc_ens = Decimal('0')
            perc_ens = _clamp_pct(perc_ens)

            perc_ic = Decimal('0')
            if ic_prev > 0:
                try:
                    perc_ic = (ic_cum / ic_prev) * Decimal('100')
                except Exception:
                    perc_ic = Decimal('0')
            perc_ic = _clamp_pct(perc_ic)

            perc_camb = Decimal('0')
            if camb_prev > 0:
                try:
                    perc_camb = (camb_cum / camb_prev) * Decimal('100')
                except Exception:
                    perc_camb = Decimal('0')
            perc_camb = _clamp_pct(perc_camb)

            # quantize para 2 casas decimais onde aplicável
            try:
                perc_ens_q = perc_ens.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            except Exception:
                perc_ens_q = perc_ens
            try:
                perc_ic_q = perc_ic.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            except Exception:
                perc_ic_q = perc_ic
            try:
                perc_camb_q = perc_camb.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            except Exception:
                perc_camb_q = perc_camb

            # Atribuir aos campos do modelo quando presentes
            try:
                if hasattr(rdo_obj, 'percentual_ensacamento'):
                    rdo_obj.percentual_ensacamento = perc_ens_q
            except Exception:
                logging.getLogger(__name__).exception('Falha atribuindo percentual_ensacamento')
            try:
                if hasattr(rdo_obj, 'percentual_icamento'):
                    rdo_obj.percentual_icamento = perc_ic_q
            except Exception:
                logging.getLogger(__name__).exception('Falha atribuindo percentual_icamento')
            try:
                if hasattr(rdo_obj, 'percentual_cambagem'):
                    rdo_obj.percentual_cambagem = perc_camb_q
            except Exception:
                logging.getLogger(__name__).exception('Falha atribuindo percentual_cambagem')

            # Calcular percentuais DIÁRIOS e CUMULATIVOS para ensacamento/icamento/cambagem
            # e derivar dois percentuais de avanço: diário (baseado nos valores do dia)
            # e cumulativo (baseado nos acumulados). Mantemos compatibilidade com
            # campos existentes: atribuímos percentuais diários a `percentual_...`
            # e cumulativos a `<campo>_cumulativo` quando suportado.
            try:
                # --- preparar valores ---
                # previsões (totais esperados)
                ensac_prev = _to_decimal_safe(getattr(rdo_obj, 'ensacamento_previsao', None) or 0)
                ic_prev = _to_decimal_safe(getattr(rdo_obj, 'icamento_previsao', None) or 0)
                camb_prev = _to_decimal_safe(getattr(rdo_obj, 'cambagem_previsao', None) or 0)

                # diários (valor deste RDO)
                try:
                    cur_ens = _to_decimal_safe(getattr(rdo_obj, 'ensacamento', None) or 0)
                except Exception:
                    cur_ens = Decimal('0')
                try:
                    cur_ic = _to_decimal_safe(getattr(rdo_obj, 'icamento', None) or 0)
                except Exception:
                    cur_ic = Decimal('0')
                try:
                    cur_camb = _to_decimal_safe(getattr(rdo_obj, 'cambagem', None) or 0)
                except Exception:
                    cur_camb = Decimal('0')

                # cumulativos (preferir campos cumulativos quando presentes)
                ensac_cum = _to_decimal_safe(getattr(rdo_obj, 'ensacamento_cumulativo', None) or cur_ens)
                ic_cum = _to_decimal_safe(getattr(rdo_obj, 'icamento_cumulativo', None) or cur_ic)
                camb_cum = _to_decimal_safe(getattr(rdo_obj, 'cambagem_cumulativo', None) or cur_camb)

                # função auxiliar para percentuais (0..100)
                def _pct_from(dividend, divisor):
                    try:
                        if divisor is None or divisor == 0:
                            return Decimal('0')
                        return _clamp_pct((dividend / divisor) * Decimal('100'))
                    except Exception:
                        return Decimal('0')

                # calcular percentuais DIÁRIOS (baseado no valor do dia / previsao)
                perc_ens_day = _pct_from(cur_ens, ensac_prev)
                perc_ic_day = _pct_from(cur_ic, ic_prev)
                perc_camb_day = _pct_from(cur_camb, camb_prev)

                # calcular percentuais CUMULATIVOS (baseado no cumulativo / previsao)
                perc_ens_cum = _pct_from(ensac_cum, ensac_prev)
                perc_ic_cum = _pct_from(ic_cum, ic_prev)
                perc_camb_cum = _pct_from(camb_cum, camb_prev)

                # quantize para 2 casas decimais quando for apresentável
                try:
                    perc_ens_day_q = perc_ens_day.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                except Exception:
                    perc_ens_day_q = perc_ens_day
                try:
                    perc_ic_day_q = perc_ic_day.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                except Exception:
                    perc_ic_day_q = perc_ic_day
                try:
                    perc_camb_day_q = perc_camb_day.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                except Exception:
                    perc_camb_day_q = perc_camb_day

                try:
                    perc_ens_cum_q = perc_ens_cum.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                except Exception:
                    perc_ens_cum_q = perc_ens_cum
                try:
                    perc_ic_cum_q = perc_ic_cum.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                except Exception:
                    perc_ic_cum_q = perc_ic_cum
                try:
                    perc_camb_cum_q = perc_camb_cum.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                except Exception:
                    perc_camb_cum_q = perc_camb_cum

                # Atribuir percentuais DIÁRIOS aos campos principais (compatibilidade com UI)
                try:
                    if hasattr(rdo_obj, 'percentual_ensacamento'):
                        rdo_obj.percentual_ensacamento = perc_ens_day_q
                except Exception:
                    logging.getLogger(__name__).exception('Falha atribuindo percentual_ensacamento (diário)')
                try:
                    if hasattr(rdo_obj, 'percentual_icamento'):
                        rdo_obj.percentual_icamento = perc_ic_day_q
                except Exception:
                    logging.getLogger(__name__).exception('Falha atribuindo percentual_icamento (diário)')
                try:
                    if hasattr(rdo_obj, 'percentual_cambagem'):
                        rdo_obj.percentual_cambagem = perc_camb_day_q
                except Exception:
                    logging.getLogger(__name__).exception('Falha atribuindo percentual_cambagem (diário)')

                # Se o modelo suportar campos cumulativos de percentual, atribuir também
                try:
                    if hasattr(rdo_obj, 'percentual_ensacamento_cumulativo'):
                        rdo_obj.percentual_ensacamento_cumulativo = perc_ens_cum_q
                except Exception:
                    pass
                try:
                    if hasattr(rdo_obj, 'percentual_icamento_cumulativo'):
                        rdo_obj.percentual_icamento_cumulativo = perc_ic_cum_q
                except Exception:
                    pass
                try:
                    if hasattr(rdo_obj, 'percentual_cambagem_cumulativo'):
                        rdo_obj.percentual_cambagem_cumulativo = perc_camb_cum_q
                except Exception:
                    pass

                # --- Agora calcular percentual de avanço DIÁRIO (pesos sobre valores do dia)
                pesos = {
                    'percentual_limpeza': Decimal('70'),
                    'percentual_ensacamento': Decimal('7'),
                    'percentual_icamento': Decimal('7'),
                    'percentual_cambagem': Decimal('5'),
                    'percentual_limpeza_fina': Decimal('6'),
                }

                # obter percentuais de limpeza (diário) e limpeza fina (diário)
                try:
                    lim_day = _to_decimal_safe(getattr(rdo_obj, 'percentual_limpeza', None) or 0)
                except Exception:
                    lim_day = Decimal('0')
                try:
                    lim_fina_day = _to_decimal_safe(getattr(rdo_obj, 'percentual_limpeza_fina', None) or 0)
                except Exception:
                    lim_fina_day = Decimal('0')

                vals_day = {
                    'percentual_limpeza': lim_day,
                    'percentual_ensacamento': perc_ens_day_q,
                    'percentual_icamento': perc_ic_day_q,
                    'percentual_cambagem': perc_camb_day_q,
                    'percentual_limpeza_fina': lim_fina_day,
                }

                weighted_day = Decimal('0')
                total_w = Decimal('0')
                for k,w in pesos.items():
                    try:
                        v = vals_day.get(k, Decimal('0')) or Decimal('0')
                        weighted_day += (v * w)
                        total_w += w
                    except Exception:
                        continue
                perc_avanco_day = Decimal('0')
                if total_w > 0:
                    try:
                        perc_avanco_day = (weighted_day / total_w)
                    except Exception:
                        perc_avanco_day = Decimal('0')
                perc_avanco_day = _clamp_pct(perc_avanco_day)

                # arredondar para inteiro quando necessário
                try:
                    perc_avanco_day_i = int(perc_avanco_day.to_integral_value(rounding=ROUND_HALF_UP))
                except Exception:
                    try:
                        perc_avanco_day_i = int(round(float(perc_avanco_day)))
                    except Exception:
                        perc_avanco_day_i = 0

                try:
                    if hasattr(rdo_obj, 'percentual_avanco'):
                        rdo_obj.percentual_avanco = perc_avanco_day_i
                except Exception:
                    logging.getLogger(__name__).exception('Falha atribuindo percentual_avanco (diário)')

                # --- Calcular percentual de avanço CUMULATIVO (pesos sobre percentuais cumulativos)
                try:
                    lim_cum = _to_decimal_safe(getattr(rdo_obj, 'percentual_limpeza_cumulativo', None) or 0)
                except Exception:
                    lim_cum = Decimal('0')
                try:
                    lim_fina_cum = _to_decimal_safe(getattr(rdo_obj, 'percentual_limpeza_fina_cumulativo', None) or 0)
                except Exception:
                    lim_fina_cum = Decimal('0')

                vals_cum = {
                    'percentual_limpeza': lim_cum,
                    'percentual_ensacamento': perc_ens_cum_q,
                    'percentual_icamento': perc_ic_cum_q,
                    'percentual_cambagem': perc_camb_cum_q,
                    'percentual_limpeza_fina': lim_fina_cum,
                }

                weighted_cum = Decimal('0')
                total_w2 = Decimal('0')
                for k,w in pesos.items():
                    try:
                        v = vals_cum.get(k, Decimal('0')) or Decimal('0')
                        weighted_cum += (v * w)
                        total_w2 += w
                    except Exception:
                        continue
                perc_avanco_cum = Decimal('0')
                if total_w2 > 0:
                    try:
                        perc_avanco_cum = (weighted_cum / total_w2)
                    except Exception:
                        perc_avanco_cum = Decimal('0')
                perc_avanco_cum = _clamp_pct(perc_avanco_cum)

                try:
                    perc_avanco_cum_i = int(perc_avanco_cum.to_integral_value(rounding=ROUND_HALF_UP))
                except Exception:
                    try:
                        perc_avanco_cum_i = int(round(float(perc_avanco_cum)))
                    except Exception:
                        perc_avanco_cum_i = 0

                try:
                    if hasattr(rdo_obj, 'percentual_avanco_cumulativo'):
                        rdo_obj.percentual_avanco_cumulativo = perc_avanco_cum_i
                except Exception:
                    logging.getLogger(__name__).exception('Falha atribuindo percentual_avanco_cumulativo')
            except Exception:
                logging.getLogger(__name__).exception('Erro calculando percentuais derivados server-side')

            # Persistir alterações de percentuais/campos derivados antes de continuar
            try:
                # DEBUG: log valores antes do save final de percentuais
                logger.info('_apply_post_to_rdo before saving derived percent fields: percentual_limpeza=%s, percentual_limpeza_cumulativo=%s, percentual_limpeza_fina=%s, percentual_limpeza_fina_cumulativo=%s, percentual_avanco=%s, percentual_avanco_cumulativo=%s',
                            getattr(rdo_obj, 'percentual_limpeza', None), getattr(rdo_obj, 'percentual_limpeza_cumulativo', None), getattr(rdo_obj, 'percentual_limpeza_fina', None), getattr(rdo_obj, 'percentual_limpeza_fina_cumulativo', None), getattr(rdo_obj, 'percentual_avanco', None), getattr(rdo_obj, 'percentual_avanco_cumulativo', None))
                _safe_save_global(rdo_obj)
            except Exception:
                logging.getLogger(__name__).exception('Falha ao salvar RDO após calcular percentuais')
        except Exception:
            logging.getLogger(__name__).exception('Erro ao calcular percentuais server-side')

        # ---------------- Atividades múltiplas ----------------
        try:
            atividades_nome = request.POST.getlist('atividade_nome[]') if hasattr(request.POST,'getlist') else []
            atividades_inicio = request.POST.getlist('atividade_inicio[]') if hasattr(request.POST,'getlist') else []
            atividades_fim = request.POST.getlist('atividade_fim[]') if hasattr(request.POST,'getlist') else []
            comentarios_pt = request.POST.getlist('atividade_comentario_pt[]') if hasattr(request.POST,'getlist') else []
        except Exception:
            atividades_nome, atividades_inicio, atividades_fim, comentarios_pt = [], [], [], []

        rdo_obj.atividades_rdo.all().delete()
        MAX_ATIV = 20
        for idx, nome in enumerate(atividades_nome[:MAX_ATIV]):
            nome_clean = _clean(nome)
            if not nome_clean:
                continue
            def parse_time(val):
                if not val:
                    return None
                try:
                    return datetime.strptime(val, '%H:%M').time()
                except Exception:
                    return None
            inicio_val = parse_time(atividades_inicio[idx] if idx < len(atividades_inicio) else None)
            fim_val = parse_time(atividades_fim[idx] if idx < len(atividades_fim) else None)
            comentario_val = _clean(comentarios_pt[idx]) if idx < len(comentarios_pt) else None
            RDOAtividade.objects.create(
                rdo=rdo_obj,
                ordem=idx,
                atividade=nome_clean,
                inicio=inicio_val,
                fim=fim_val,
                comentario_pt=comentario_val
            )

        if comentarios_pt:
            first_com_pt = _clean(comentarios_pt[0])
            if first_com_pt is not None:
                rdo_obj.comentario_pt = first_com_pt

        pt_abertura_raw = request.POST.get('pt_abertura')
        if pt_abertura_raw in ('sim', 'nao'):
            rdo_obj.exist_pt = True if pt_abertura_raw == 'sim' else False

        turnos_raw = request.POST.getlist('pt_turnos[]') if hasattr(request.POST, 'getlist') else []
        turno_map = {'manha': 'Manhã','tarde': 'Tarde','noite': 'Noite'}
        mapped_turnos = [turno_map[t] for t in turnos_raw if t in turno_map]
        if mapped_turnos:
            rdo_obj.select_turnos = mapped_turnos
        elif pt_abertura_raw in ('sim', 'nao') and not mapped_turnos:
            rdo_obj.select_turnos = []

        pt_manha = _clean(request.POST.get('pt_num_manha'))
        pt_tarde = _clean(request.POST.get('pt_num_tarde'))
        pt_noite = _clean(request.POST.get('pt_num_noite'))
        if pt_manha is not None:
            rdo_obj.pt_manha = pt_manha
        if pt_tarde is not None:
            rdo_obj.pt_tarde = pt_tarde
        if pt_noite is not None:
            rdo_obj.pt_noite = pt_noite
        if pt_abertura_raw == 'nao':
            rdo_obj.pt_manha = None
            rdo_obj.pt_tarde = None
            rdo_obj.pt_noite = None
            rdo_obj.select_turnos = []

        try:
            equipe_nomes = request.POST.getlist('equipe_nome[]') if hasattr(request.POST, 'getlist') else []
            equipe_funcoes = request.POST.getlist('equipe_funcao[]') if hasattr(request.POST, 'getlist') else []
            equipe_em_servico = request.POST.getlist('equipe_em_servico[]') if hasattr(request.POST, 'getlist') else []
            equipe_pessoa_ids = request.POST.getlist('equipe_pessoa_id[]') if hasattr(request.POST, 'getlist') else []
        except Exception:
            equipe_nomes, equipe_funcoes, equipe_em_servico, equipe_pessoa_ids = [], [], [], []

        def _norm_nome(n):
            if n is None: return None
            s = str(n).strip()
            return s if s != '' else None
        def _norm_func(f):
            if f is None: return None
            s = str(f).strip()
            if s == '': return None
            return s[:50]

        # ---------------- Equipe consolidada (membros / funcoes) ----------------
        # Armazenar como JSON string ou lista (dependendo do campo do modelo)
        membros_clean = []
        funcoes_clean = []
        for idx in range(len(equipe_nomes)):
            n = _norm_nome(equipe_nomes[idx])
            f = _norm_func(equipe_funcoes[idx]) if idx < len(equipe_funcoes) else None
            if n is None and f is None:
                continue
            membros_clean.append(n)
            funcoes_clean.append(f)

        try:
            # Se o modelo aceita listas, atribuir diretamente; senão, serializar em JSON
            if hasattr(rdo_obj, 'membros'):
                try:
                    # testar se campo é um list/JSONField
                    current = getattr(rdo_obj, 'membros')
                    setattr(rdo_obj, 'membros', membros_clean if isinstance(current, (list, tuple)) or membros_clean == [] else json.dumps(membros_clean))
                except Exception:
                    setattr(rdo_obj, 'membros', json.dumps(membros_clean))
        except Exception:
            pass

        # ---------------- Equipe relacional (persistência exata por RDO) ----------------
        try:
            # Limpa membros atuais e regrava conforme o payload recebido
            if hasattr(rdo_obj, 'membros_equipe'):
                rdo_obj.membros_equipe.all().delete()
                total = max(len(equipe_nomes), len(equipe_funcoes))
                def _parse_bool(v):
                    s = str(v).strip().lower()
                    return s in ('1','true','on','yes','sim','y','t')
                for i in range(total):
                    n = _norm_nome(equipe_nomes[i]) if i < len(equipe_nomes) else None
                    f = _norm_func(equipe_funcoes[i]) if i < len(equipe_funcoes) else None
                    es = _parse_bool(equipe_em_servico[i]) if i < len(equipe_em_servico) else True
                    pessoa = None
                    # Preferir pessoa_id explícito quando enviado
                    try:
                        pid = equipe_pessoa_ids[i] if i < len(equipe_pessoa_ids) else None
                        if pid and str(pid).isdigit():
                            pessoa = Pessoa.objects.filter(pk=int(pid)).first()
                    except Exception:
                        pessoa = None
                    # Se não houver id, tentar por nome exato (case-insensitive)
                    if pessoa is None and n:
                        try:
                            pessoa = Pessoa.objects.filter(nome__iexact=n).first()
                        except Exception:
                            pessoa = None
                    RDOMembroEquipe.objects.create(
                        rdo=rdo_obj,
                        pessoa=pessoa,
                        nome=None if pessoa else n,
                        funcao=f,
                        em_servico=bool(es),
                        ordem=i,
                    )
        except Exception:
            logging.getLogger(__name__).exception('Falha ao persistir equipe relacional do RDO')

        try:
            if hasattr(rdo_obj, 'funcoes'):
                try:
                    current2 = getattr(rdo_obj, 'funcoes')
                    setattr(rdo_obj, 'funcoes', funcoes_clean if isinstance(current2, (list, tuple)) or funcoes_clean == [] else json.dumps(funcoes_clean))
                except Exception:
                    setattr(rdo_obj, 'funcoes', json.dumps(funcoes_clean))
        except Exception:
            pass

        # Também persistir em funcoes_list (novo campo preferido)
        try:
            if hasattr(rdo_obj, 'funcoes_list'):
                try:
                    rdo_obj.funcoes_list = json.dumps(funcoes_clean)
                except Exception:
                    rdo_obj.funcoes_list = None
        except Exception:
            pass

        # ---------------- Fotos múltiplas / single (compatível com ImageField) ----------------
        fotos_saved = []
        files = []
        try:
            # coletar arquivos enviados nas possíveis chaves
            candidate_keys = ['fotos', 'fotos[]']
            for i in range(0, 10):
                candidate_keys.append(f'fotos[{i}]')
            if hasattr(request.FILES, 'getlist'):
                for k in candidate_keys:
                    try:
                        lst = request.FILES.getlist(k)
                    except Exception:
                        lst = []
                    if lst:
                        files.extend(list(lst))
            if not files:
                try:
                    single = request.FILES.get('fotos') if hasattr(request, 'FILES') else None
                    if single:
                        files.append(single)
                except Exception:
                    pass
            if not files:
                for i in range(1, 6):
                    try:
                        f = request.FILES.get(f'foto{i}') if hasattr(request, 'FILES') else None
                    except Exception:
                        f = None
                    if f:
                        files.append(f)
        except Exception:
            files = []

        # --- Remover possíveis duplicatas de arquivos (mesmo nome+tamanho) ---
        try:
            unique_files = []
            seen = set()
            for f in (files or []):
                try:
                    fname = getattr(f, 'name', None)
                    fsize = getattr(f, 'size', None)
                    key = (fname, fsize)
                except Exception:
                    key = None
                if key is None:
                    # se não for possível extrair chave, tentar incluir mas evitar crash
                    if f not in unique_files:
                        unique_files.append(f)
                else:
                    if key in seen:
                        continue
                    seen.add(key)
                    unique_files.append(f)
            files = unique_files
        except Exception:
            # Em caso de qualquer falha, manter o comportamento anterior
            pass

        # identificar tipo do campo fotos no modelo (ImageField/FileField vs texto/json)
        is_file_field = False
        try:
            fld = None
            try:
                fld = rdo_obj._meta.get_field('fotos')
            except Exception:
                fld = None
            from django.db.models import FileField, ImageField
            if fld is not None and isinstance(fld, (FileField, ImageField)):
                is_file_field = True
        except Exception:
            is_file_field = False

        # fotos_to_remove (do POST) - comum aos dois modos
        fotos_to_remove = []
        try:
            if hasattr(request.POST, 'getlist'):
                fotos_to_remove = request.POST.getlist('fotos_remove[]') or request.POST.getlist('fotos_remove') or []
            else:
                v = request.POST.get('fotos_remove') if hasattr(request, 'POST') else None
                if v:
                    fotos_to_remove = [x.strip() for x in v.split(',') if x.strip()]
        except Exception:
            fotos_to_remove = []

        # ---- Nova lógica: suportar slots explícitos fotos_1..fotos_5 ----
        try:
            # Normalizar requests para remoção que indiquem slots, ex: 'fotos_3', '3', 'foto3'
            slot_names = [f'fotos_{i}' for i in range(1, 6)]
            # detectar pedidos de remoção que mencionem um slot e limpar o campo correspondente
            normalized_remove = [str(x).strip() for x in fotos_to_remove if x is not None]
            for rem in normalized_remove:
                if not rem:
                    continue
                s = rem.lower()
                # aceitar formatos como '3', '03', 'fotos_3', 'foto3', 'fotos-3'
                import re
                m = re.search(r'(?:fotos?_?|-?)(\d{1,2})$', s)
                if m:
                    try:
                        idx = int(m.group(1))
                        if 1 <= idx <= 5:
                            fname = f'fotos_{idx}'
                            # tentar apagar o arquivo físico associado e zerar o campo
                            try:
                                cur_field = getattr(rdo_obj, fname, None)
                                if cur_field:
                                    try:
                                        # cur_field é um FieldFile
                                        cur_field.delete(save=False)
                                    except Exception:
                                        try:
                                            name = getattr(cur_field, 'name', None)
                                            if name:
                                                default_storage.delete(name)
                                        except Exception:
                                            pass
                                try:
                                    setattr(rdo_obj, fname, None)
                                except Exception:
                                    pass
                            except Exception:
                                pass
                    except Exception:
                        pass
        except Exception:
            # não bloquear o fluxo principal se a remoção por slot falhar
            pass

        # Se houver modelo relacional RDOFoto (múltiplas fotos), tentar remover instâncias
        # correspondentes aos valores enviados em fotos_to_remove. O cliente pode enviar
        # id, nome do arquivo, basename ou URL absoluta; tentamos casar de forma robusta
        # e remover tanto o arquivo no storage quanto o registro DB.
        try:
            use_rdofoto = hasattr(rdo_obj, 'fotos_rdo')
            if fotos_to_remove and use_rdofoto:
                _logger = logging.getLogger(__name__)
                # rdo_obj is already available in this scope; proceed to process related RDOFoto removals

                # Helper parsers
                def _parse_int(v):
                    try:
                        return int(v)
                    except Exception:
                        return None

                def _parse_decimal(v):
                    try:
                        return Decimal(str(v)) if v is not None and v != '' else None
                    except Exception:
                        return None

                post = request.POST
                attrs = {}

                # Mapping from POST names (form) to model fields
                # Observação: manter alinhado com RDO.add_tank (modelo) para evitar divergências
                mapping = {
                    'tanque_codigo': 'tanque_codigo',
                    'tanque_nome': 'nome_tanque',
                    'tipo_tanque': 'tipo_tanque',
                    'numero_compartimento': 'numero_compartimentos',
                    'gavetas': 'gavetas',
                    'patamar': 'patamares',
                    'volume_tanque_exec': 'volume_tanque_exec',
                    'servico_exec': 'servico_exec',
                    'metodo_exec': 'metodo_exec',
                    'espaco_confinado': 'espaco_confinado',
                    'operadores_simultaneos': 'operadores_simultaneos',
                    'h2s_ppm': 'h2s_ppm',
                    'lel': 'lel',
                    'co_ppm': 'co_ppm',
                    'o2_percent': 'o2_percent',
                    'total_n_efetivo_confinado': 'total_n_efetivo_confinado',
                    'tempo_bomba': 'tempo_bomba',
                    # previsões por tanque (persistidas como *_prev)
                    'ensacamento_prev': 'ensacamento_prev',
                    'icamento_prev': 'icamento_prev',
                    'cambagem_prev': 'cambagem_prev',
                    # valores diários explícitos por tanque
                    'ensacamento_dia': 'ensacamento_dia',
                    'icamento_dia': 'icamento_dia',
                    'cambagem_dia': 'cambagem_dia',
                    'tambores_dia': 'tambores_dia',
                    'residuos_solidos': 'residuos_solidos',
                    'residuos_totais': 'residuos_totais',
                    'bombeio': 'bombeio',
                    'total_liquido': 'total_liquido',
                    'avanco_limpeza': 'avanco_limpeza',
                    'avanco_limpeza_fina': 'avanco_limpeza_fina',
                    'sentido_limpeza': 'sentido_limpeza',
                    # Campos de limpeza por-tanque (removidos do mapeamento do request);
                    # os nomes canônicos permanecem apenas no modelo `RdoTanque`.
                    # percentuais por tanque
                    'percentual_limpeza_diario': 'percentual_limpeza_diario',
                    'percentual_limpeza_cumulativo': 'percentual_limpeza_cumulativo',
                    'percentual_limpeza_fina': 'percentual_limpeza_fina',
                    'percentual_limpeza_fina_diario': 'percentual_limpeza_fina_diario',
                    'percentual_limpeza_fina_cumulativo': 'percentual_limpeza_fina_cumulativo',
                    'percentual_ensacamento': 'percentual_ensacamento',
                    'percentual_icamento': 'percentual_icamento',
                    'percentual_cambagem': 'percentual_cambagem',
                    'percentual_avanco': 'percentual_avanco',
                    # estado por-compartimento (JSON texto)
                    'compartimentos_avanco_json': 'compartimentos_avanco_json',
                }

                # Numeric field sets for parsing
                int_fields = set([
                    'numero_compartimentos', 'gavetas', 'patamares',
                    'operadores_simultaneos', 'total_n_efetivo_confinado',
                    'ensacamento_dia', 'icamento_dia', 'cambagem_dia', 'tambores_dia',
                    'total_liquido',
                    'limpeza_mecanizada_cumulativa', 'limpeza_fina_cumulativa',
                    'percentual_limpeza_fina', 'percentual_limpeza_fina_cumulativo',
                    'percentual_limpeza_cumulativo',
                    'ensacamento_prev', 'icamento_prev', 'cambagem_prev',
                ])
                decimal_fields = set([
                    'volume_tanque_exec', 'h2s_ppm', 'lel', 'co_ppm', 'o2_percent', 'tempo_bomba',
                    'residuos_solidos', 'residuos_totais', 'bombeio',
                    'limpeza_mecanizada_diaria', 'limpeza_fina_diaria',
                    'percentual_limpeza_diario', 'percentual_limpeza_fina_diario',
                    'percentual_ensacamento', 'percentual_icamento', 'percentual_cambagem',
                    'percentual_avanco',
                ])

                for post_key, model_key in mapping.items():
                    if post_key in post:
                        val = post.get(post_key)
                        if val is None or val == '':
                            continue
                        # normalize numbers
                        if model_key in int_fields:
                            parsed = _parse_int(val)
                            if parsed is not None:
                                attrs[model_key] = parsed
                        elif model_key in decimal_fields:
                            parsed = _parse_decimal(val)
                            if parsed is not None:
                                attrs[model_key] = parsed
                        else:
                            # strings / choices
                            attrs[model_key] = val

                # Attach RDO and create
                try:
                    # Ensure sentido_limpeza is canonical before persisting
                    if 'sentido_limpeza' in attrs and attrs.get('sentido_limpeza') is not None:
                        try:
                            canon = _canonicalize_sentido(attrs.get('sentido_limpeza'))
                            if canon:
                                attrs['sentido_limpeza'] = canon
                        except Exception:
                            # fallback: leave original value
                            pass

                    tank = RdoTanque.objects.create(rdo=rdo_obj, **attrs)
                    logger.info('Created RdoTanque %s for RDO %s', tank.id, rdo_obj.id)
                    return JsonResponse({'success': True, 'id': tank.id, 'tanque': {
                        'id': tank.id,
                        'tanque_codigo': tank.tanque_codigo,
                        'nome_tanque': tank.nome_tanque,
                    }})
                except Exception as e:
                    # rdo_id may not be defined in this scope; use rdo_obj.id for context
                    logger.exception('Error creating RdoTanque for RDO %s: %s', getattr(rdo_obj, 'id', None), e)
                    return JsonResponse({'success': False, 'error': 'Could not create tank'}, status=500)
                except Exception:
                    _logger.exception('Error processing fotos_to_remove for RDOFoto')
        except Exception:
            # não bloquear fluxo principal se remoção relacional falhar
            pass

        # ---- Gravar arquivos recebidos em slots fotos_1..fotos_5 quando existir ----
        try:
            # verificar se o modelo tem campos de slot explicitamente
            has_slot = any(hasattr(rdo_obj, f'fotos_{i}') for i in range(1, 6))
            if has_slot and files:
                # construir lista de nomes de campos na ordem
                slot_fields = [f'fotos_{i}' for i in range(1, 6)]
                # identificar índices de slots vazios (após remoções já aplicadas)
                empty_slots = []
                for idx, fname in enumerate(slot_fields):
                    try:
                        cur = getattr(rdo_obj, fname, None)
                        # FieldFile: verificar 'name' vazio ou None
                        cur_name = getattr(cur, 'name', None) if cur is not None else None
                        if not cur_name:
                            empty_slots.append((idx, fname))
                    except Exception:
                        empty_slots.append((idx, fname))

                # preenche slots vazios com os arquivos na ordem recebida
                fi = 0
                for slot_idx, slot_name in empty_slots:
                    if fi >= len(files):
                        break
                    f = files[fi]
                    try:
                        # salvar usando FieldFile.save quando disponível
                        try:
                            field_obj = getattr(rdo_obj.__class__, slot_name)
                        except Exception:
                            field_obj = None
                        save_name = f'rdos/{datetime.now().strftime("%Y%m%d%H%M%S%f")}_{f.name}'
                        try:
                            dest_field = getattr(rdo_obj, slot_name)
                            try:
                                dest_field.save(save_name, ContentFile(f.read()), save=False)
                            except Exception:
                                # fallback para default_storage
                                try:
                                    saved_name = default_storage.save(save_name, ContentFile(f.read()))
                                    setattr(rdo_obj, slot_name, saved_name)
                                except Exception:
                                    pass
                        except Exception:
                            # último recurso: usar default_storage e atribuir string
                            try:
                                saved_name = default_storage.save(save_name, ContentFile(f.read()))
                                try:
                                    setattr(rdo_obj, slot_name, saved_name)
                                except Exception:
                                    pass
                            except Exception:
                                pass
                    except Exception:
                        pass
                    finally:
                        fi += 1
        except Exception:
            # não bloquear o fluxo principal por falhas na gravação de slots
            pass

        try:
            if is_file_field:
                # arquivo único: remover se solicitado
                try:
                    cur = getattr(rdo_obj, 'fotos')
                except Exception:
                    cur = None
                try:
                    cur_name = getattr(cur, 'name', None) if cur else None
                except Exception:
                    cur_name = None
                # remover atual se solicitado (por nome ou por índice '0'/'1')
                if fotos_to_remove and cur_name:
                    # Normalizar valores atuais
                    try:
                        cur_name_str = str(cur_name)
                    except Exception:
                        cur_name_str = ''
                    try:
                        cur_basename = cur_name_str.split('/')[-1] if cur_name_str else ''
                    except Exception:
                        cur_basename = ''
                    for rem in fotos_to_remove:
                        try:
                            srem = str(rem or '').strip()
                            if not srem:
                                continue
                            matched = False
                            # Match by exact stored name
                            if srem == cur_name_str:
                                matched = True
                            # Match by basename (filename)
                            if not matched and cur_basename and (srem == cur_basename or srem.endswith('/' + cur_basename) or srem.endswith(cur_basename)):
                                matched = True
                            # If frontend sent an absolute URL, try to strip domain and /media/ prefix
                            if not matched and srem.startswith('http'):
                                try:
                                    # buscar segmento após /media/ se existir
                                    if '/media/' in srem:
                                        after = srem.split('/media/', 1)[1]
                                        if after == cur_name_str or after == cur_basename or after.endswith('/' + cur_basename):
                                            matched = True
                                    # também aceitar quando a URL termina com o basename
                                    if not matched and cur_basename and srem.split('?')[0].endswith('/' + cur_basename):
                                        matched = True
                                except Exception:
                                    pass
                            # aceitar índices simples '0'/'1' vindos do cliente
                            if not matched and srem in (str(0), str(1)):
                                matched = True
                            if matched:
                                try:
                                    rdo_obj.fotos.delete(save=False)
                                except Exception:
                                    pass
                                try:
                                    rdo_obj.fotos = None
                                except Exception:
                                    pass
                                break
                        except Exception:
                            continue
                # se houver arquivos enviados, salvar o primeiro no campo
                if files:
                    try:
                        f = files[0]
                        name = f'rdos/{datetime.now().strftime("%Y%m%d%H%M%S%f")}_{f.name}'
                        # garantir que o FieldFile salve corretamente
                        try:
                            rdo_obj.fotos.save(name, ContentFile(f.read()), save=False)
                        except Exception:
                            # fallback: salvar na storage e atribuir nome (quando possível)
                            try:
                                saved_name = default_storage.save(name, ContentFile(f.read()))
                                # atribuir caminho relativo (FieldFile descriptor cuidará ao salvar)
                                rdo_obj.fotos = saved_name
                            except Exception:
                                pass
                    except Exception:
                        pass
            else:
                # legado: campo texto/json que guarda lista de URLs
                fotos_saved = []
                try:
                    for f in files:
                        try:
                            name = default_storage.save(f'rdos/{datetime.now().strftime("%Y%m%d%H%M%S%f")}_{f.name}', ContentFile(f.read()))
                            fotos_saved.append(default_storage.url(name) if hasattr(default_storage, 'url') else name)
                        except Exception:
                            logging.getLogger(__name__).exception('Falha salvando foto do RDO')
                except Exception:
                    fotos_saved = []

                # construir lista existing a partir do campo atual (texto/json)
                cur = getattr(rdo_obj, 'fotos', None)
                existing = []
                try:
                    if isinstance(cur, (list, tuple)):
                        existing = list(cur)
                    elif isinstance(cur, str) and cur.strip().startswith('['):
                        existing = json.loads(cur)
                    elif isinstance(cur, str) and cur.strip():
                        existing = [ln for ln in cur.splitlines() if ln.strip()]
                except Exception:
                    existing = []

                # aplicar remoções por valor ou índice
                if fotos_to_remove:
                    normalized_remove = [str(x).strip() for x in fotos_to_remove if x is not None]
                    filtered = []
                    for idx, item in enumerate(existing):
                        try:
                            if str(item) in normalized_remove:
                                continue
                            if any((str(i) == str(idx) or str(i) == str(idx+1)) for i in normalized_remove):
                                continue
                        except Exception:
                            pass
                        filtered.append(item)
                    existing = filtered

                # anexar novas fotos salvas e deduplicar por URL
                combined = list(existing) + list(fotos_saved)
                deduped = []
                seen_urls = set()
                for it in combined:
                    try:
                        s = str(it)
                    except Exception:
                        s = None
                    if not s:
                        continue
                    if s in seen_urls:
                        continue
                    seen_urls.add(s)
                    deduped.append(s)
                existing = deduped

                # reatribuir (preservar JSON quando campo texto)
                try:
                    if isinstance(cur, str) and cur.strip().startswith('['):
                        setattr(rdo_obj, 'fotos', json.dumps(existing))
                    else:
                        setattr(rdo_obj, 'fotos', existing)
                except Exception:
                    setattr(rdo_obj, 'fotos', existing)
        except Exception:
            pass

        # ---- Recomputar campo consolidado fotos_json (sincronizar slots/legado) ----
        try:
            fotos_new = []
            try:
                # Preferir slots explícitos fotos_1..fotos_5 quando existirem
                for i in range(1, 6):
                    try:
                        f = getattr(rdo_obj, f'fotos_{i}', None)
                    except Exception:
                        f = None
                    if not f:
                        continue
                    url = None
                    try:
                        url = getattr(f, 'url', None)
                    except Exception:
                        url = None
                    if not url:
                        try:
                            name = getattr(f, 'name', None)
                            if name and hasattr(default_storage, 'url'):
                                try:
                                    url = default_storage.url(name)
                                except Exception:
                                    url = name
                            else:
                                url = name or str(f)
                        except Exception:
                            url = str(f)
                    if url:
                        fotos_new.append(url)
            except Exception:
                fotos_new = []

            # Se não encontramos imagens nos slots, usar o campo legado `fotos` (lista/str)
            if not fotos_new:
                try:
                    fotos_field = getattr(rdo_obj, 'fotos', None)
                    if fotos_field is None:
                        fotos_new = []
                    elif isinstance(fotos_field, (list, tuple)):
                        fotos_new = list(fotos_field)
                    elif isinstance(fotos_field, str):
                        s = fotos_field.strip()
                        if s.startswith('['):
                            try:
                                fotos_new = json.loads(s)
                            except Exception:
                                fotos_new = [ln for ln in s.splitlines() if ln.strip()]
                        else:
                            fotos_new = [ln for ln in s.splitlines() if ln.strip()]
                    else:
                        try:
                            url = getattr(fotos_field, 'url', None)
                        except Exception:
                            url = None
                        if url:
                            fotos_new = [url]
                        else:
                            fotos_new = []
                except Exception:
                    fotos_new = []

            # Deduplicar e persistir no campo fotos_json quando disponível
            try:
                deduped = []
                seen_urls = set()
                for it in (fotos_new or []):
                    try:
                        s = str(it)
                    except Exception:
                        s = None
                    if not s:
                        continue
                    if s in seen_urls:
                        continue
                    seen_urls.add(s)
                    deduped.append(s)
                fotos_new = deduped
                if hasattr(rdo_obj, 'fotos_json'):
                    try:
                        rdo_obj.fotos_json = json.dumps(fotos_new)
                    except Exception:
                        try:
                            setattr(rdo_obj, 'fotos_json', json.dumps(fotos_new))
                        except Exception:
                            pass
            except Exception:
                pass
        except Exception:
            # não bloquear fluxo principal por falhas na sincronização de fotos
            pass

        # ---------------- Entradas/Saidas de confinamento ----------------
        # O modelo usa TimeField único para entrada/saída. Normalizar listas do formulário e gravar apenas o primeiro horário válido.
        entrada_list = []
        saida_list = []
        try:
            # DEBUG: registrar chaves/valores relevantes do POST para diagnosticar problemas de persistência de horários
            try:
                _logger = logging.getLogger(__name__)
                if hasattr(request, 'POST'):
                    try:
                        post_keys = list(request.POST.keys())
                        _logger.info('DEBUG _apply_post_to_rdo POST keys: %s', post_keys)
                    except Exception:
                        _logger.info('DEBUG _apply_post_to_rdo could not list POST keys')
                    try:
                        _logger.info('DEBUG entrada_confinado[] getlist: %s', request.POST.getlist('entrada_confinado[]') if hasattr(request.POST, 'getlist') else 'no-getlist')
                        _logger.info('DEBUG entrada_confinado getlist: %s', request.POST.getlist('entrada_confinado') if hasattr(request.POST, 'getlist') else 'no-getlist')
                        _logger.info('DEBUG saida_confinado[] getlist: %s', request.POST.getlist('saida_confinado[]') if hasattr(request.POST, 'getlist') else 'no-getlist')
                        _logger.info('DEBUG saida_confinado getlist: %s', request.POST.getlist('saida_confinado') if hasattr(request.POST, 'getlist') else 'no-getlist')
                    except Exception:
                        _logger.exception('DEBUG failed reading entrada/saida lists from POST')
            except Exception:
                try:
                    logging.getLogger(__name__).exception('DEBUG logger setup failed inside _apply_post_to_rdo')
                except Exception:
                    pass
            if hasattr(request.POST, 'getlist'):
                entrada_list = request.POST.getlist('entrada_confinado[]') or request.POST.getlist('entrada_confinado') or []
                saida_list = request.POST.getlist('saida_confinado[]') or request.POST.getlist('saida_confinado') or []
            else:
                v1 = request.POST.get('entrada_confinado')
                v2 = request.POST.get('saida_confinado')
                if v1: entrada_list = [v1]
                if v2: saida_list = [v2]
        except Exception:
            entrada_list, saida_list = [], []

        def _first_valid_time(lst):
            for val in lst:
                if not val:
                    continue
                s = str(val).strip()
                if not s:
                    continue
                # aceitar HH:MM ou HH:MM:SS
                try:
                    return datetime.strptime(s, '%H:%M').time()
                except Exception:
                    try:
                        return datetime.strptime(s, '%H:%M:%S').time()
                    except Exception:
                        continue
            return None

        ent_time = _first_valid_time(entrada_list)
        sai_time = _first_valid_time(saida_list)
        # Legacy single fields
        try:
            if hasattr(rdo_obj, 'entrada_confinado'):
                rdo_obj.entrada_confinado = ent_time
        except Exception:
            pass
        try:
            if hasattr(rdo_obj, 'saida_confinado'):
                rdo_obj.saida_confinado = sai_time
        except Exception:
            pass
        # New explicit 6 pairs fields
        try:
            for i in range(6):
                e = None; s = None
                try:
                    e = _first_valid_time([entrada_list[i]]) if i < len(entrada_list) else None
                except Exception:
                    e = None
                try:
                    s = _first_valid_time([saida_list[i]]) if i < len(saida_list) else None
                except Exception:
                    s = None
                try:
                    setattr(rdo_obj, f'entrada_confinado_{i+1}', e)
                except Exception:
                    pass
                try:
                    setattr(rdo_obj, f'saida_confinado_{i+1}', s)
                except Exception:
                    pass
        except Exception:
            pass

        _safe_save_global(rdo_obj)

        # Sincronizar campo contrato/PO no objeto OrdemServico vinculado quando o RDO
        # recebeu um valor para 'contrato_po' (ou 'po'). Isso garante que alterações
        # feitas pelo Supervisor no modal RDO reflitam na OS exibida no home.html.
        try:
            ordem = getattr(rdo_obj, 'ordem_servico', None)
            # Priorizar contrato_po do RDO, senão o campo po (compatibilidade)
            contrato_val = getattr(rdo_obj, 'contrato_po', None) or getattr(rdo_obj, 'po', None)
            if ordem and contrato_val is not None:
                try:
                    ordem.po = contrato_val if contrato_val != '' else None
                    ordem.save(update_fields=['po'])
                except Exception:
                    # Não bloquear o fluxo principal por falha nesse sync
                    pass
        except Exception:
            pass

        atividades_payload = []
        for atv in rdo_obj.atividades_rdo.all():
            atividades_payload.append({
                'ordem': atv.ordem,
                'atividade': atv.atividade,
                'atividade_label': atv.get_atividade_display(),
                'inicio': atv.inicio.strftime('%H:%M') if atv.inicio else None,
                'fim': atv.fim.strftime('%H:%M') if atv.fim else None,
                'comentario_pt': atv.comentario_pt,
                'comentario_en': atv.comentario_en,
            })

        # Construir fotos_list para retornar no payload (compatível com rdo_detail)
        fotos_list = []
        try:
            # Preferir slots explícitos fotos_1..fotos_5 quando existirem
            try:
                for i in range(1, 6):
                    try:
                        f = getattr(rdo_obj, f'fotos_{i}', None)
                    except Exception:
                        f = None
                    if not f:
                        continue
                    url = None
                    try:
                        # FieldFile expõe .url quando storage configurado
                        url = getattr(f, 'url', None)
                    except Exception:
                        url = None
                    if not url:
                        try:
                            name = getattr(f, 'name', None)
                            if name and hasattr(default_storage, 'url'):
                                try:
                                    url = default_storage.url(name)
                                except Exception:
                                    url = name
                            else:
                                url = name or str(f)
                        except Exception:
                            url = str(f)
                    if url:
                        fotos_list.append(url)
            except Exception:
                fotos_list = []

            # Se não encontramos imagens nos slots, usar o campo legado `fotos` (lista/str)
            if not fotos_list:
                fotos_field = getattr(rdo_obj, 'fotos', None)
                if fotos_field is None:
                    fotos_list = []
                elif isinstance(fotos_field, (list, tuple)):
                    fotos_list = list(fotos_field)
                elif isinstance(fotos_field, str):
                    s = fotos_field.strip()
                    if s.startswith('['):
                        try:
                            fotos_list = json.loads(s)
                        except Exception:
                            fotos_list = [ln for ln in s.splitlines() if ln.strip()]
                    else:
                        fotos_list = [ln for ln in s.splitlines() if ln.strip()]
                else:
                    # se for um FieldFile single, expor sua URL
                    try:
                        url = getattr(fotos_field, 'url', None)
                    except Exception:
                        url = None
                    if url:
                        fotos_list = [url]
                    else:
                        fotos_list = []
        except Exception:
            fotos_list = []

        # Construir equipe_list preferindo os membros relacionais recém salvos
        equipe_list = []
        try:
            rel_members = list(rdo_obj.membros_equipe.all().order_by('ordem', 'id'))
        except Exception:
            rel_members = []
        if rel_members:
            for em in rel_members:
                try:
                    nome = getattr(em.pessoa, 'nome', None) if getattr(em, 'pessoa', None) else getattr(em, 'nome', None)
                except Exception:
                    nome = getattr(em, 'nome', None)
                equipe_list.append({
                    'nome': nome,
                    'funcao': getattr(em, 'funcao', None),
                    'em_servico': bool(getattr(em, 'em_servico', True)),
                })
        else:
            try:
                membros_field = getattr(rdo_obj, 'membros', None)
                funcoes_field = getattr(rdo_obj, 'funcoes_list', None) or getattr(rdo_obj, 'funcoes', None)
                if membros_field is None:
                    mlist = []
                elif isinstance(membros_field, (list, tuple)):
                    mlist = list(membros_field)
                elif isinstance(membros_field, str):
                    s = membros_field.strip()
                    if s.startswith('['):
                        try:
                            mlist = json.loads(s)
                        except Exception:
                            mlist = [ln for ln in s.splitlines() if ln.strip()]
                    else:
                        mlist = [ln for ln in s.splitlines() if ln.strip()]
                else:
                    mlist = []

                if funcoes_field is None:
                    flist = []
                elif isinstance(funcoes_field, (list, tuple)):
                    flist = list(funcoes_field)
                elif isinstance(funcoes_field, str):
                    s2 = funcoes_field.strip()
                    if s2.startswith('['):
                        try:
                            flist = json.loads(s2)
                        except Exception:
                            flist = [ln for ln in s2.splitlines() if ln.strip()]
                    else:
                        flist = [ln for ln in s2.splitlines() if ln.strip()]
                else:
                    flist = []

                maxlen = max(len(mlist), len(flist))
                for i in range(maxlen):
                    equipe_list.append({'nome': (mlist[i] if i < len(mlist) else None), 'funcao': (flist[i] if i < len(flist) else None)})
            except Exception:
                equipe_list = []

        # helper para serializar percentuais/decimais de forma consistente no payload
        def _fmt(v):
            return str(v) if v is not None else None

        payload = {
            'id': rdo_obj.id,
            'rdo': rdo_obj.rdo,
            'data': rdo_obj.data.isoformat() if rdo_obj.data else None,
            'data_inicio': rdo_obj.data_inicio.isoformat() if getattr(rdo_obj, 'data_inicio', None) else None,
            'previsao_termino': rdo_obj.previsao_termino.isoformat() if getattr(rdo_obj, 'previsao_termino', None) else None,
            'numero_os': getattr(rdo_obj.ordem_servico, 'numero_os', None) if getattr(rdo_obj, 'ordem_servico', None) else None,
            'empresa': getattr(rdo_obj.ordem_servico, 'cliente', None) if getattr(rdo_obj, 'ordem_servico', None) else None,
            'unidade': getattr(rdo_obj.ordem_servico, 'unidade', None) if getattr(rdo_obj, 'ordem_servico', None) else None,
            'turno': rdo_obj.turno,
            'nome_tanque': rdo_obj.nome_tanque,
            'tanque_codigo': rdo_obj.tanque_codigo,
            'tipo_tanque': rdo_obj.tipo_tanque,
            'numero_compartimentos': rdo_obj.numero_compartimentos,
            'volume_tanque_exec': str(rdo_obj.volume_tanque_exec) if rdo_obj.volume_tanque_exec is not None else None,
            'servico_exec': rdo_obj.servico_exec,
            'metodo_exec': rdo_obj.metodo_exec,
            'gavetas': rdo_obj.gavetas,
            'patamares': rdo_obj.patamares,
            'operadores_simultaneos': rdo_obj.operadores_simultaneos,
            'H2S_ppm': str(getattr(rdo_obj, 'h2s_ppm', None)) if getattr(rdo_obj, 'h2s_ppm', None) is not None else None,
            'LEL': str(getattr(rdo_obj, 'lel', None)) if getattr(rdo_obj, 'lel', None) is not None else None,
            'CO_ppm': str(getattr(rdo_obj, 'co_ppm', None)) if getattr(rdo_obj, 'co_ppm', None) is not None else None,
            'O2_percent': str(getattr(rdo_obj, 'o2_percent', None)) if getattr(rdo_obj, 'o2_percent', None) is not None else None,
            'bombeio': (lambda v: (str(v) if v is not None and not isinstance(v, (int, float)) else v))(getattr(rdo_obj, 'bombeio', getattr(rdo_obj, 'quantidade_bombeada', None))),
            'total_liquido': rdo_obj.total_liquido,
            'ensacamento': rdo_obj.ensacamento,
            'tambores': rdo_obj.tambores,
            'total_solidos': rdo_obj.total_solidos,
            'total_residuos': rdo_obj.total_residuos,
            'po': getattr(rdo_obj, 'po', None) or getattr(rdo_obj, 'contrato_po', None) or (rdo_obj.ordem_servico.po if getattr(rdo_obj, 'ordem_servico', None) else None),
            'exist_pt': rdo_obj.exist_pt,
            'select_turnos': rdo_obj.select_turnos,
            'pt_manha': rdo_obj.pt_manha,
            'pt_tarde': rdo_obj.pt_tarde,
            'pt_noite': rdo_obj.pt_noite,
            'observacoes_pt': rdo_obj.observacoes_rdo_pt,
            'observacoes_en': getattr(rdo_obj, 'observacoes_rdo_en', None),
            'planejamento_pt': rdo_obj.planejamento_pt,
            'planejamento_en': getattr(rdo_obj, 'planejamento_en', None),
            'comentario_pt': getattr(rdo_obj, 'comentario_pt', None),
            'comentario_en': getattr(rdo_obj, 'comentario_en', None),
            'atividades': atividades_payload,
            # Expor token canônico e rótulo legível para frontend; manter flag booleana compat quando aplicável
            'sentido_limpeza': (lambda v: (_canonicalize_sentido(v)))(getattr(rdo_obj, 'sentido_limpeza', getattr(rdo_obj, 'sent_limpeza', None))),
            'sentido_label': (lambda v: ('Vante > Ré' if _canonicalize_sentido(v) == 'vante > ré' else ('Ré > Vante' if _canonicalize_sentido(v) == 'ré > vante' else ( 'Bombordo > Boreste' if _canonicalize_sentido(v) == 'bombordo > boreste' else ( 'Boreste < Bombordo' if _canonicalize_sentido(v) == 'boreste < bombordo' else None)) )))(getattr(rdo_obj, 'sentido_limpeza', getattr(rdo_obj, 'sent_limpeza', None))),
            'sentido_limpeza_bool': (lambda v: (True if _canonicalize_sentido(v) == 'vante > ré' else (False if _canonicalize_sentido(v) == 'ré > vante' else None)))(getattr(rdo_obj, 'sentido_limpeza', getattr(rdo_obj, 'sent_limpeza', None))),
            'tempo_bomba': (None if not getattr(rdo_obj, 'tempo_uso_bomba', None) else round(rdo_obj.tempo_uso_bomba.total_seconds()/3600, 1)),
            'fotos': fotos_list,
            'equipe': equipe_list,
            # incluir percentuais e acumulados calculados server-side para uso imediato no frontend
            'percentual_limpeza_fina': _fmt(getattr(rdo_obj, 'percentual_limpeza_fina', None)),
            'percentual_limpeza_cumulativo': _fmt(getattr(rdo_obj, 'percentual_limpeza_cumulativo', None)),
            'percentual_limpeza_fina_cumulativo': _fmt(getattr(rdo_obj, 'percentual_limpeza_fina_cumulativo', None)),
            # Novos campos canônicos (diário) e campos de fonte de verdade do Supervisor
            'percentual_limpeza_diario': _fmt(getattr(rdo_obj, 'percentual_limpeza_diario', None)),
            'percentual_limpeza_fina_diario': _fmt(getattr(rdo_obj, 'percentual_limpeza_fina_diario', None)),
            # Campos que representam diretamente o input do Supervisor (nomes alternativos existentes no modelo)
            'limpeza_mecanizada_diaria': _fmt(getattr(rdo_obj, 'limpeza_mecanizada_diaria', None)),
            'limpeza_fina_diaria': _fmt(getattr(rdo_obj, 'limpeza_fina_diaria', None)),
            'limpeza_mecanizada_cumulativa': _fmt(getattr(rdo_obj, 'limpeza_mecanizada_cumulativa', None)),
            'limpeza_fina_cumulativa': _fmt(getattr(rdo_obj, 'limpeza_fina_cumulativa', None)),
            # Compatibilidade: expor também chaves usadas pelo Supervisor modal
            'limpeza_acu': _fmt(getattr(rdo_obj, 'percentual_limpeza_cumulativo', None)),
            'limpeza_fina_acu': _fmt(getattr(rdo_obj, 'percentual_limpeza_fina_cumulativo', None)),
            'avanco_limpeza': _fmt(getattr(rdo_obj, 'percentual_limpeza', None)),
            'ensacamento_cumulativo': (getattr(rdo_obj, 'ensacamento_cumulativo', None) if getattr(rdo_obj, 'ensacamento_cumulativo', None) is not None else getattr(rdo_obj, 'ensacamento', None)),
            'ensacamento_previsao': (getattr(rdo_obj, 'ensacamento_previsao', None) if getattr(rdo_obj, 'ensacamento_previsao', None) is not None else None),
            'icamento_cumulativo': (getattr(rdo_obj, 'icamento_cumulativo', None) if getattr(rdo_obj, 'icamento_cumulativo', None) is not None else getattr(rdo_obj, 'icamento', None)),
            'icamento_previsao': (getattr(rdo_obj, 'icamento_previsao', None) if getattr(rdo_obj, 'icamento_previsao', None) is not None else None),
            'cambagem_cumulativo': (getattr(rdo_obj, 'cambagem_cumulativo', None) if getattr(rdo_obj, 'cambagem_cumulativo', None) is not None else getattr(rdo_obj, 'cambagem', None)),
            'cambagem_previsao': (getattr(rdo_obj, 'cambagem_previsao', None) if getattr(rdo_obj, 'cambagem_previsao', None) is not None else None),
            'percentual_ensacamento': _fmt(getattr(rdo_obj, 'percentual_ensacamento', None)),
            'percentual_icamento': _fmt(getattr(rdo_obj, 'percentual_icamento', None)),
            'percentual_cambagem': _fmt(getattr(rdo_obj, 'percentual_cambagem', None)),
            'percentual_avanco': _fmt(getattr(rdo_obj, 'percentual_avanco', None)),
            # incluir cálculos agregados para uso imediato no frontend
            'total_atividade_min': None,
            'total_confinado_min': None,
            'total_abertura_pt_min': None,
            'total_atividades_efetivas_min': None,
            'total_atividades_nao_efetivas_fora_min': None,
            'total_n_efetivo_confinado_min': None,
        }
        try:
            # reconstuir ec_times_local para passar ao cálculo de agregados
            # Preferir os valores recebidos no POST (entrada_list/saida_list) quando disponíveis,
            # para que o payload retornado ao cliente reflita exatamente o que foi enviado.
            ec_times_local = {}
            try:
                # Prefer lists from request; fallback to new explicit fields; then legacy
                if isinstance(entrada_list, (list, tuple)) and any(str(x).strip() for x in entrada_list or []):
                    entradas = [_format_ec_time_value(v) for v in entrada_list]
                else:
                    # Try new explicit fields
                    entradas = []
                    try:
                        for i in range(6):
                            entradas.append(_format_ec_time_value(getattr(rdo_obj, f'entrada_confinado_{i+1}', None)))
                    except Exception:
                        entradas = []
                    if not any(entradas):
                        entrada_field = getattr(rdo_obj, 'entrada_confinado', None)
                        entradas = _normalize_ec_field_to_list(entrada_field)

                if isinstance(saida_list, (list, tuple)) and any(str(x).strip() for x in saida_list or []):
                    saidas = [_format_ec_time_value(v) for v in saida_list]
                else:
                    saidas = []
                    try:
                        for i in range(6):
                            saidas.append(_format_ec_time_value(getattr(rdo_obj, f'saida_confinado_{i+1}', None)))
                    except Exception:
                        saidas = []
                    if not any(saidas):
                        saida_field = getattr(rdo_obj, 'saida_confinado', None)
                        saidas = _normalize_ec_field_to_list(saida_field)

                for i in range(6):
                    ec_times_local[f'entrada_{i+1}'] = entradas[i] if i < len(entradas) else None
                    ec_times_local[f'saida_{i+1}'] = saidas[i] if i < len(saidas) else None
            except Exception:
                ec_times_local = {}
            ag = compute_rdo_aggregates(rdo_obj, atividades_payload, ec_times_local)
            payload['total_atividade_min'] = ag.get('total_atividade_min')
            payload['total_confinado_min'] = ag.get('total_confinado_min')
            payload['total_abertura_pt_min'] = ag.get('total_abertura_pt_min')
            payload['total_atividades_efetivas_min'] = ag.get('total_atividades_efetivas_min')
            payload['total_atividades_nao_efetivas_fora_min'] = ag.get('total_atividades_nao_efetivas_fora_min')
            payload['total_n_efetivo_confinado_min'] = ag.get('total_n_efetivo_confinado_min')
            # Incluir ec_times no payload de retorno para que o fragmento do editor seja
            # repovoado com os horários enviados no POST (mesmo que o modelo armazene
            # apenas o primeiro horário nos TimeFields legacy).
            try:
                payload['ec_times'] = ec_times_local
            except Exception:
                payload['ec_times'] = {}
            # Incluir debug raw das listas recebidas (ajuda a diagnosticar falta de múltiplos horários)
            try:
                payload['ec_raw'] = {
                    'entrada_list': entrada_list,
                    'saida_list': saida_list,
                }
            except Exception:
                payload['ec_raw'] = {'entrada_list': [], 'saida_list': []}
        except Exception:
            # não bloquear fluxo principal se a reconstrução de ec_times falhar
            pass

        logger.info('_apply_post_to_rdo about to return payload for rdo_id=%s', getattr(rdo_obj, 'id', None))
        return True, payload
    except Exception:
        logging.getLogger(__name__).exception('Erro aplicando POST ao RDO')
        return False, None


@login_required(login_url='/login/')
@require_POST
def create_rdo_ajax(request):
    """Cria um novo RDO a partir dos dados do modal. Aceita opcionalmente 'ordem_servico_id' para vincular a OS."""
    logger = logging.getLogger(__name__)
    try:
        logger.info('create_rdo_ajax called by user=%s, POST_keys=%s', getattr(request, 'user', None), list(request.POST.keys()))
        # DEBUG: registrar content-type e tamanho do body para diagnosticar envios via FormData vs JSON
        try:
            content_type = request.META.get('CONTENT_TYPE') or request.content_type if hasattr(request, 'content_type') else None
        except Exception:
            content_type = None
        try:
            body_len = len(getattr(request, 'body', b''))
        except Exception:
            body_len = None
        logger.debug('create_rdo_ajax debug content_type=%s body_len=%s', content_type, body_len)
        # Se request.POST estiver vazio, logar o início do request.body (truncado) para inspeção
        try:
            if not list(request.POST.keys()):
                try:
                    raw = request.body
                    # truncar para evitar logs gigantes
                    logger.debug('create_rdo_ajax raw body (truncated 2000 chars): %s', raw[:2000])
                except Exception:
                    logger.exception('create_rdo_ajax failed reading raw body')
        except Exception:
            pass
        # Logar valores específicos de limpeza que esperamos receber
        try:
            if hasattr(request, 'POST') and hasattr(request.POST, 'getlist'):
                logger.debug('create_rdo_ajax cleaned keys: sup-limp=%s sup-limp-fina=%s percentual_limpeza_diario=%s percentual_limpeza_fina_diario=%s',
                             request.POST.getlist('sup-limp') or request.POST.get('sup-limp'),
                             request.POST.getlist('sup-limp-fina') or request.POST.get('sup-limp-fina'),
                             request.POST.getlist('percentual_limpeza_diario') or request.POST.get('percentual_limpeza_diario'),
                             request.POST.getlist('percentual_limpeza_fina_diario') or request.POST.get('percentual_limpeza_fina_diario'))
            else:
                logger.debug('create_rdo_ajax quick keys: sup-limp=%s sup-limp-fina=%s percentual_limpeza_diario=%s percentual_limpeza_fina_diario=%s',
                             request.POST.get('sup-limp'), request.POST.get('sup-limp-fina'), request.POST.get('percentual_limpeza_diario'), request.POST.get('percentual_limpeza_fina_diario'))
        except Exception:
            logger.exception('create_rdo_ajax failed logging specific limpeza keys')
        ordem_id = request.POST.get('ordem_servico_id') or request.POST.get('ordem_id') or request.POST.get('rdo_id')
        rdo_obj = RDO()
        if ordem_id:
            try:
                # Usar transação para reservar/atribuir o próximo número de RDO de forma atômica
                with transaction.atomic():
                    # Bloquear a OS para evitar condições de corrida ao calcular o próximo número
                    # Tentar buscar por PK primeiro; se não existir, aceitar numero_os (int ou text)
                    os_obj = None
                    try:
                        os_obj = OrdemServico.objects.select_for_update().get(pk=ordem_id)
                    except OrdemServico.DoesNotExist:
                        try:
                            # tentar interpretar como numero_os (inteiro quando possível)
                            numero_val = int(str(ordem_id).strip())
                        except Exception:
                            numero_val = None
                        try:
                            if numero_val is not None:
                                os_obj = OrdemServico.objects.select_for_update().filter(numero_os=numero_val).first()
                            else:
                                os_obj = OrdemServico.objects.select_for_update().filter(numero_os__iexact=str(ordem_id).strip()).first()
                        except Exception:
                            os_obj = None
                    if not os_obj:
                        return JsonResponse({'success': False, 'error': 'Ordem de Serviço não encontrada.'}, status=404)
                    # Restrição de acesso para Supervisores: só podem criar RDO para sua própria OS
                    try:
                        is_supervisor_user = (hasattr(request, 'user') and request.user.is_authenticated and request.user.groups.filter(name='Supervisor').exists())
                    except Exception:
                        is_supervisor_user = False
                    if is_supervisor_user and getattr(os_obj, 'supervisor', None) != request.user:
                        return JsonResponse({'success': False, 'error': 'Sem permissão para criar RDO para esta OS.'}, status=403)

                    # Calcular próximo RDO disponível (tentar interpretar valores numéricos)
                    max_val = None
                    # Se o cliente forneceu explicitamente um rdo (rdo_contagem / rdo / rdo_override),
                    # tentar respeitar esse valor desde que não exista um RDO com o mesmo número
                    # para a mesma OS (evitar duplicação). Mantemos isso dentro da transação.
                    rdo_override_raw = None
                    try:
                        rdo_override_raw = (request.POST.get('rdo_contagem') or request.POST.get('rdo') or request.POST.get('rdo_override'))
                        if rdo_override_raw is not None:
                            rdo_override_raw = str(rdo_override_raw).strip()
                            if rdo_override_raw == '':
                                rdo_override_raw = None
                    except Exception:
                        rdo_override_raw = None
                    try:
                        # se a OS foi localizada por numero_os, preferimos agregar
                        # todos os RDOs que tenham ordem_servico__numero_os igual
                        # ao valor, assim cobrimos casos onde RDOs foram gravados
                        # em diferentes PKs mas compartilham o mesmo numero_os.
                        numero_lookup = getattr(os_obj, 'numero_os', None)
                        if numero_lookup is not None:
                            qs_for_max = RDO.objects.filter(ordem_servico__numero_os=numero_lookup)
                        else:
                            qs_for_max = RDO.objects.filter(ordem_servico=os_obj)

                        # Tentar obter máximo diretamente via agregação (se campo for numérico)
                        try:
                            agg = qs_for_max.aggregate(max_rdo=Max('rdo'))
                            max_rdo_raw = agg.get('max_rdo')
                            if max_rdo_raw is not None:
                                try:
                                    max_val = int(str(max_rdo_raw))
                                except Exception:
                                    max_val = None
                        except Exception:
                            max_val = None
                    except Exception:
                        max_val = None

                    if max_val is None:
                        # Fallback: iterar e parsear manualmente sobre a mesma queryset
                        try:
                            for r in qs_for_max.only('rdo'):
                                try:
                                    v = int(str(r.rdo))
                                    if max_val is None or v > max_val:
                                        max_val = v
                                except Exception:
                                    continue
                        except Exception:
                            max_val = None

                    # Se cliente enviou rdo_override e ele não existe ainda para esta OS, use-o.
                    used_rdo = None
                    try:
                        if rdo_override_raw is not None:
                            try:
                                cand = int(rdo_override_raw)
                            except Exception:
                                cand = None
                            if cand is not None:
                                # verificar existência de RDO com o mesmo rdo para essa OS
                                try:
                                    exists_same = qs_for_max.filter(rdo=str(cand)).exists()
                                except Exception:
                                    exists_same = False
                                if not exists_same:
                                    used_rdo = cand
                    except Exception:
                        used_rdo = None

                    if used_rdo is None:
                        next_num = (max_val or 0) + 1
                        used_rdo = next_num

                    # Garantir unicidade do número de RDO calculado: se por algum motivo
                    # já existir um RDO com o mesmo número (p.ex. parsing estranho,
                    # dados legados ou corrida não prevista), iterar até encontrar um
                    # número livre. Fazemos isso dentro da transação onde temos
                    # `qs_for_max` definido para a mesma OS.
                    try:
                        # converter para int quando possível
                        cur_try = int(used_rdo) if used_rdo is not None else None
                    except Exception:
                        cur_try = None
                    try:
                        # se cur_try for None (não numérico), tentar checar existência
                        # usando a representação em string uma vez; caso exista, não
                        # haverá forma segura de incrementar — então apenas prosseguir.
                        if cur_try is None:
                            exists_once = False
                            try:
                                exists_once = qs_for_max.filter(rdo=str(used_rdo)).exists()
                            except Exception:
                                exists_once = False
                            if exists_once:
                                # como fallback, tentar usar max_val+1
                                try:
                                    cur_try = (max_val or 0) + 1
                                except Exception:
                                    cur_try = None
                        # se temos um inteiro, incrementar até achar um disponível
                        if cur_try is not None:
                            attempts = 0
                            while True:
                                try:
                                    if not qs_for_max.filter(rdo=str(cur_try)).exists():
                                        used_rdo = cur_try
                                        break
                                except Exception:
                                    # em caso de erro no DB, abortar o loop e manter used_rdo
                                    break
                                cur_try = cur_try + 1
                                attempts += 1
                                if attempts > 10000:
                                    # proteção contra loop infinito em cenários inesperados
                                    break
                    except Exception:
                        # se alguma verificação falhar, cair no comportamento original
                        pass

                    # Proteção extra: garantir que nunca será criado um RDO com número já existente para a mesma OS
                    final_rdo = str(used_rdo)
                    attempts_final = 0
                    while qs_for_max.filter(rdo=final_rdo).exists():
                        try:
                            final_rdo = str(int(final_rdo) + 1)
                        except Exception:
                            # Se não for numérico, adiciona sufixo _n
                            final_rdo = f"{final_rdo}_{attempts_final+1}"
                        attempts_final += 1
                        if attempts_final > 10000:
                            logger.error("Loop de proteção final_rdo excedeu 10000 tentativas!")
                            break
                    rdo_obj.rdo = final_rdo
                    rdo_obj.ordem_servico = os_obj

                    # Persistir um placeholder mínimo do RDO dentro da transação
                    # para reservar o número calculado (final_rdo). Em seguida
                    # sair do bloco atomic e aplicar o restante do POST fora da
                    # transação crítica, evitando longas retenções de lock.
                    # Em ambientes SQLite podemos encontrar 'database is locked'
                    # — neste caso, evitar abortar a view: registrar a falha e
                    # tentar salvar o placeholder novamente fora do atomic.
                    save_placeholder_failed = False
                    try:
                        from django.db.utils import OperationalError as DjangoOperationalError
                    except Exception:
                        DjangoOperationalError = None
                    try:
                        _safe_save_global(rdo_obj)
                    except Exception as e:
                        # Se for OperationalError de 'locked' e DjangoOperationalError disponível,
                        # registrar e adiar nova tentativa fora do bloco atomic.
                        msg = str(e).lower()
                        handled = False
                        # IntegrityError: outro processo criou o mesmo RDO entre o cálculo e o save.
                        try:
                            from django.db import IntegrityError as DjangoIntegrityError
                        except Exception:
                            DjangoIntegrityError = None

                        if DjangoOperationalError is not None and isinstance(e, DjangoOperationalError) and 'locked' in msg:
                            logger.warning('SQLite locked while saving placeholder RDO inside atomic; will retry outside atomic: %s', e)
                            save_placeholder_failed = True
                            handled = True

                        # Tratamento para Unique constraint: o RDO já foi criado por outro request.
                        if not handled and DjangoIntegrityError is not None and isinstance(e, DjangoIntegrityError):
                            try:
                                logger.warning('IntegrityError when saving placeholder RDO: %s. Attempting to load existing RDO.', e)
                                existing = None
                                try:
                                    if getattr(rdo_obj, 'ordem_servico', None) is not None and getattr(rdo_obj, 'rdo', None) is not None:
                                        existing = RDO.objects.filter(ordem_servico=getattr(rdo_obj, 'ordem_servico'), rdo=getattr(rdo_obj, 'rdo')).first()
                                except Exception:
                                    existing = None
                                if existing:
                                    logger.info('Found existing RDO (pk=%s) with same ordem_servico and rdo; reusing it.', getattr(existing, 'pk', None))
                                    rdo_obj = existing
                                    save_placeholder_failed = False
                                    handled = True
                                else:
                                    # se não encontramos, logar e re-raise original
                                    logger.exception('IntegrityError saving placeholder but no existing RDO found.')
                            except Exception:
                                logger.exception('Error handling IntegrityError for placeholder save')

                        if not handled:
                            logger.exception('Falha ao salvar RDO de reserva dentro da transação')
                            raise

                # Fora do bloco transaction.atomic(): se falhamos em salvar o placeholder
                # dentro do atomic devido a lock no SQLite, tentar salvar agora fora
                # do atomic (melhora resiliência em ambientes concorrentes).
                try:
                    if save_placeholder_failed:
                        try:
                            logger.info('Retrying placeholder save for RDO outside atomic (possible prior SQLite lock)')
                            _safe_save_global(rdo_obj)
                            save_placeholder_failed = False
                        except Exception as e:
                            try:
                                from django.db import IntegrityError as DjangoIntegrityError
                            except Exception:
                                DjangoIntegrityError = None
                            # Se for IntegrityError, outro request criou o mesmo RDO entre o cálculo e o save;
                            # então carregar o registro existente e continuar.
                            if DjangoIntegrityError is not None and isinstance(e, DjangoIntegrityError):
                                try:
                                    logger.warning('IntegrityError on retrying placeholder save outside atomic: %s. Attempting to load existing RDO.', e)
                                    existing = None
                                    try:
                                        if getattr(rdo_obj, 'ordem_servico', None) is not None and getattr(rdo_obj, 'rdo', None) is not None:
                                            existing = RDO.objects.filter(ordem_servico=getattr(rdo_obj, 'ordem_servico'), rdo=getattr(rdo_obj, 'rdo')).first()
                                    except Exception:
                                        existing = None
                                    if existing:
                                        logger.info('Found existing RDO (pk=%s) after retry; reusing it.', getattr(existing, 'pk', None))
                                        rdo_obj = existing
                                        save_placeholder_failed = False
                                    else:
                                        logger.exception('Retry to save placeholder RDO outside atomic failed and no existing RDO found')
                                except Exception:
                                    logger.exception('Error handling IntegrityError on retry placeholder save')
                            else:
                                logger.exception('Retry to save placeholder RDO outside atomic failed')
                            # não raise aqui: vamos deixar _apply_post_to_rdo decidir como proceder
                            pass
                except NameError:
                    # variável pode não existir em caminhos alternativos; ignorar
                    pass

                # Aplicar o POST completo
                logger.debug('About to call _apply_post_to_rdo (outside atomic) for RDO rdo=%s ordem=%s', getattr(rdo_obj, 'rdo', None), getattr(rdo_obj, 'ordem_servico', None))
                import time as _time
                _t0 = _time.time()
                created, payload = _apply_post_to_rdo(request, rdo_obj)
                _t1 = _time.time()
                logger.info('Finished _apply_post_to_rdo (created=%s) elapsed=%.3fs', bool(created), (_t1 - _t0))
                if not created:
                    # tentar remover o RDO reservado para não poluir números
                    try:
                        if getattr(rdo_obj, 'pk', None):
                            rdo_obj.delete()
                    except Exception:
                        logger.exception('Falha ao remover RDO reservado após falha em _apply_post_to_rdo')
                    return JsonResponse({'success': False, 'error': 'Falha ao criar RDO.'}, status=400)

                # Se chegamos aqui, a criação foi bem-sucedida (created == True).
                try:
                    # Garantir que o ID retornado seja um inteiro (PK). Não confiar em used_rdo
                    rdo_pk = payload.get('id') if payload is not None else getattr(rdo_obj, 'id', None)
                    try:
                        rdo_pk = int(rdo_pk) if rdo_pk is not None else None
                    except Exception:
                        rdo_pk = None
                    resp_debug = {
                        'success': True,
                        'message': 'RDO criado',
                        'id': rdo_pk,
                        'pk': rdo_pk,
                        'rdo': payload,
                        'used_rdo': str(final_rdo),
                        'computed_max': (max_val if max_val is not None else None)
                    }
                except Exception:
                    resp_debug = {'success': True, 'message': 'RDO criado', 'id': None, 'rdo': payload}
                return JsonResponse(resp_debug)
            except OrdemServico.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Ordem de Serviço não encontrada.'}, status=404)
        else:
            # Sem ordem_id, ainda tentar criar sem vínculo à OS (comportamento legado)
            created, payload = _apply_post_to_rdo(request, rdo_obj)
            if not created:
                return JsonResponse({'success': False, 'error': 'Falha ao criar RDO.'}, status=400)
            return JsonResponse({'success': True, 'message': 'RDO criado', 'id': payload.get('id'), 'rdo': payload})
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.exception('Erro create_rdo_ajax')
        # Quando em DEBUG, retornar detalhes do erro no JSON para facilitar debug local.
        try:
            if getattr(settings, 'DEBUG', False):
                return JsonResponse({
                    'success': False,
                    'error': 'Erro interno',
                    'exception': str(e),
                    'traceback': traceback.format_exc(),
                }, status=500)
        except Exception:
            # se por alguma razão settings/traceback falharem, cair para retorno genérico
            pass
        return JsonResponse({'success': False, 'error': 'Erro interno'}, status=500)

    # Segurança: garantir que sempre retornamos um HttpResponse mesmo que um
    # caminho imprevisto atravesse a função sem hits de return (evita ValueError
    # "didn't return an HttpResponse object"). Logamos para diagnóstico.
    try:
        logging.getLogger(__name__).error('create_rdo_ajax reached end of function without explicit return - returning generic error')
    except Exception:
        pass
    return JsonResponse({'success': False, 'error': 'Erro interno (no response path)'}, status=500)


@login_required(login_url='/login/')
@require_POST
def update_rdo_ajax(request):
    """Atualiza RDO existente via AJAX. Espera 'rdo_id' no POST."""
    logger = logging.getLogger(__name__)
    try:
        logger.info('update_rdo_ajax called by user=%s POST_keys=%s', getattr(request, 'user', None), list(request.POST.keys()))
        rdo_id = request.POST.get('rdo_id')
        if not rdo_id:
            return JsonResponse({'success': False, 'error': 'ID do RDO não informado.'}, status=400)
        try:
            rdo_obj = RDO.objects.get(pk=rdo_id)
        except RDO.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'RDO não encontrado.'}, status=404)
        # Restrição de acesso para Supervisores: só podem atualizar RDOs das suas OS
        try:
            is_supervisor_user = (hasattr(request, 'user') and request.user.is_authenticated and request.user.groups.filter(name='Supervisor').exists())
        except Exception:
            is_supervisor_user = False
        if is_supervisor_user:
            ordem = getattr(rdo_obj, 'ordem_servico', None)
            if getattr(ordem, 'supervisor', None) != request.user:
                return JsonResponse({'success': False, 'error': 'Sem permissão para atualizar este RDO.'}, status=403)
        updated, payload = _apply_post_to_rdo(request, rdo_obj)
        if not updated:
            return JsonResponse({'success': False, 'error': 'Falha ao atualizar RDO.'}, status=400)
        return JsonResponse({'success': True, 'message': 'RDO atualizado', 'rdo': payload})
    except Exception:
        logging.getLogger(__name__).exception('Erro update_rdo_ajax')
        return JsonResponse({'success': False, 'error': 'Erro interno'}, status=500)


@login_required(login_url='/login/')
@require_POST
def add_tank_ajax(request, rdo_id):
    """Cria um novo tanque associado a um RDO existente.

    Espera rdo_id na URL e campos do tanque no POST (compatível com os names do modal).
    Retorna JSON com o objeto criado.
    """
    logger = logging.getLogger(__name__)
    try:
        logger.info('add_tank_ajax called by user=%s for rdo_id=%s POST_keys=%s', getattr(request, 'user', None), rdo_id, list(request.POST.keys()))
        try:
            rdo_obj = RDO.objects.get(pk=rdo_id)
        except RDO.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'RDO não encontrado.'}, status=404)

        # Restrição: supervisores só podem operar sobre suas OS
        try:
            is_supervisor_user = (hasattr(request, 'user') and request.user.is_authenticated and request.user.groups.filter(name='Supervisor').exists())
        except Exception:
            is_supervisor_user = False
        if is_supervisor_user:
            ordem = getattr(rdo_obj, 'ordem_servico', None)
            if getattr(ordem, 'supervisor', None) != request.user:
                return JsonResponse({'success': False, 'error': 'Sem permissão para adicionar tanque neste RDO.'}, status=403)

        # Coletar campos do POST (parsing defensivo com normalização de números)
        from decimal import Decimal

        def _norm_num(val):
            try:
                if val is None:
                    return None
                s = str(val).strip()
                if s == '':
                    return None
                # remover sufixo de porcentagem e trocar vírgula por ponto
                if s.endswith('%'):
                    s = s[:-1].strip()
                s = s.replace(',', '.')
                return s if s != '' else None
            except Exception:
                return None

        def _get_int(name):
            raw = request.POST.get(name)
            s = _norm_num(raw)
            if s is None:
                return None
            try:
                return int(float(s))
            except Exception:
                return None

        def _get_decimal(name):
            raw = request.POST.get(name)
            s = _norm_num(raw)
            if s is None:
                return None
            try:
                return Decimal(str(s))
            except Exception:
                return None

        def _get_bool(name):
            v = request.POST.get(name)
            if v is None or v == '':
                return None
            s = str(v).strip().lower()
            if s in ('1', 'true', 't', 'yes', 'y', 'on', 'sim'):
                return True
            if s in ('0', 'false', 'f', 'no', 'n', 'off', 'nao', 'não'):
                return False
            return None

        def _parse_sentido():
            """Parseia valores variados enviados pelo frontend para o campo 'sentido'.
            Aceita formas booleanas ('sim'/'nao', 'true'/'false', '1'/'0') e textos
            como 'vante', 'ré', 'vante-re', 're-vante'. Retorna o token canônico
            (ex.: 'vante > ré', 'ré > vante', ...) quando possível ou None.
            """
            # priorizar chaves comuns
            raw = None
            for k in ('sentido_limpeza', 'sentido', 'sent', 'sent_limpeza'):
                if k in request.POST and request.POST.get(k) not in (None, ''):
                    raw = request.POST.get(k)
                    break
            if raw is None:
                return None
            # Use server-side canonicalizer for robust mapping of legacy values
            try:
                canon = _canonicalize_sentido(raw)
                return canon
            except Exception:
                return None

        # Aceitar variantes de nomes que o frontend possa enviar (ex.: *_prev)
        tanque_data = {
            'tanque_codigo': request.POST.get('tanque_codigo') or None,
            'nome_tanque': request.POST.get('tanque_nome') or request.POST.get('nome_tanque') or None,
            'tipo_tanque': request.POST.get('tipo_tanque') or None,
            'numero_compartimentos': _get_int('numero_compartimento') or _get_int('numero_compartimentos'),
            'gavetas': _get_int('gavetas'),
            'patamares': _get_int('patamar') or _get_int('patamares'),
            'volume_tanque_exec': _get_decimal('volume_tanque_exec'),
            'servico_exec': request.POST.get('servico_exec') or None,
            'metodo_exec': request.POST.get('metodo_exec') or None,
            'espaco_confinado': request.POST.get('espaco_confinado') or None,
            'operadores_simultaneos': _get_int('operadores_simultaneos'),
            'h2s_ppm': _get_decimal('h2s_ppm'),
            'lel': _get_decimal('lel'),
            'co_ppm': _get_decimal('co_ppm'),
            'o2_percent': _get_decimal('o2_percent'),
            'total_n_efetivo_confinado': _get_int('total_n_efetivo_confinado'),
            'tempo_bomba': _get_decimal('tempo_bomba'),
            # campos enviados pelo frontend podem ter sufixo _prev (preservados no cliente)
            'ensacamento_dia': _get_int('ensacamento_dia') or _get_int('ensacamento_prev'),
            'icamento_dia': _get_int('icamento_dia') or _get_int('icamento_prev'),
            'cambagem_dia': _get_int('cambagem_dia') or _get_int('cambagem_prev'),
            # cumulativos operacionais por tanque (aceitar aliases do frontend)
            'ensacamento_cumulativo': _get_int('ensacamento_cumulativo') or _get_int('ensacamento_acu'),
            'icamento_cumulativo': _get_int('icamento_cumulativo') or _get_int('icamento_acu'),
            'cambagem_cumulativo': _get_int('cambagem_cumulativo') or _get_int('cambagem_acu'),
            # novos cumulativos por tanque (resíduos) — frontend usa *_acu
            'total_liquido_cumulativo': _get_int('total_liquido_cumulativo') or _get_int('total_liquido_acu'),
            'residuos_solidos_cumulativo': _get_decimal('residuos_solidos_cumulativo') or _get_decimal('residuos_solidos_acu'),
            # Previsões por-tanque: aceitar valores enviados no POST (_prev/_previsao)
            # ou herdar do RDO quando o supervisor preencheu no nível do RDO.
            'ensacamento_prev': _get_int('ensacamento_prev') or _get_int('ensacamento_previsao') or getattr(rdo_obj, 'ensacamento_previsao', None) or getattr(rdo_obj, 'ensacamento', None),
            'icamento_prev': _get_int('icamento_prev') or _get_int('icamento_previsao') or getattr(rdo_obj, 'icamento_previsao', None) or getattr(rdo_obj, 'icamento', None),
            'cambagem_prev': _get_int('cambagem_prev') or _get_int('cambagem_previsao') or getattr(rdo_obj, 'cambagem_previsao', None) or getattr(rdo_obj, 'cambagem', None),
            'tambores_dia': _get_int('tambores_dia') or _get_int('tambores_prev'),
            'residuos_solidos': _get_decimal('residuos_solidos'),
            'residuos_totais': _get_decimal('residuos_totais'),
            # Bombeio (m3) e total líquido (aceitar aliases do frontend como 'residuo_liquido')
            'bombeio': _get_decimal('bombeio'),
            'total_liquido': _get_int('total_liquido') or _get_int('residuo_liquido') or _get_int('residuo'),
            'avanco_limpeza': request.POST.get('avanco_limpeza') or None,
            'avanco_limpeza_fina': request.POST.get('avanco_limpeza_fina') or None,
            # Percentuais (aceitar nomes usados no formulário ou variantes)
            'percentual_limpeza_diario': _get_decimal('percentual_limpeza_diario') or _get_decimal('percentual_limpeza') or _get_decimal('percentual_limpeza') or None,
            'percentual_limpeza_fina_diario': _get_decimal('percentual_limpeza_fina_diario') or _get_decimal('percentual_limpeza_fina') or None,
            'percentual_limpeza_cumulativo': _get_int('percentual_limpeza_cumulativo') or _get_int('limpeza_acu') or None,
            'percentual_limpeza_fina_cumulativo': _get_int('percentual_limpeza_fina_cumulativo') or _get_int('limpeza_fina_acu') or None,
            'percentual_ensacamento': _get_decimal('percentual_ensacamento') or None,
            'percentual_icamento': _get_decimal('percentual_icamento') or None,
            'percentual_cambagem': _get_decimal('percentual_cambagem') or None,
            'percentual_avanco': _get_decimal('percentual_avanco') or None,
            # novo: sentido da limpeza por tanque (aceitar várias formas enviadas pelo frontend)
            'sentido_limpeza': _parse_sentido(),
        }

        # If the frontend didn't send a specific sentido for this tank, inherit
        # the RDO-level boolean when available. This makes the per-tank boolean
        # persist even when the supervisor set the value only at the RDO level.
        try:
            if tanque_data.get('sentido_limpeza') is None and getattr(rdo_obj, 'sentido_limpeza', None) is not None:
                # Prefer canonical token when inheriting from RDO-level value
                inherited = getattr(rdo_obj, 'sentido_limpeza', None)
                try:
                    tanque_data['sentido_limpeza'] = _canonicalize_sentido(inherited) or inherited
                except Exception:
                    tanque_data['sentido_limpeza'] = inherited
        except Exception:
            pass

        # Criar o registro do tanque dentro de transação curta
        with transaction.atomic():
            tank = RdoTanque.objects.create(rdo=rdo_obj, **{k: v for k, v in tanque_data.items() if v is not None})

        # Se os cumulativos operacionais não foram enviados explicitamente, tentar recomputar
        try:
            sent_ens = request.POST.get('ensacamento_cumulativo') not in (None, '')
            sent_ic = request.POST.get('icamento_cumulativo') not in (None, '')
            sent_camb = request.POST.get('cambagem_cumulativo') not in (None, '')
            sent_tlq = (request.POST.get('total_liquido_cumulativo') not in (None, '') or request.POST.get('total_liquido_acu') not in (None, ''))
            sent_rss = (request.POST.get('residuos_solidos_cumulativo') not in (None, '') or request.POST.get('residuos_solidos_acu') not in (None, ''))
            if not (sent_ens and sent_ic and sent_camb and sent_tlq and sent_rss):
                try:
                    if hasattr(tank, 'recompute_metrics') and callable(tank.recompute_metrics):
                        res = tank.recompute_metrics(only_when_missing=True)
                        if res is not None:
                            with transaction.atomic():
                                tank.save()
                except Exception:
                    logger.exception('Falha ao recomputar cumulativos por tanque (id=%s)', getattr(tank, 'id', None))
        except Exception:
            pass

        # Preparar payload de retorno
        tank_payload = {
            'id': tank.id,
            'tanque_codigo': tank.tanque_codigo,
            'nome_tanque': tank.nome_tanque,
            'tipo_tanque': tank.tipo_tanque,
            'numero_compartimentos': tank.numero_compartimentos,
            'gavetas': tank.gavetas,
            'patamares': tank.patamares,
            'volume_tanque_exec': str(tank.volume_tanque_exec) if tank.volume_tanque_exec is not None else None,
            'servico_exec': tank.servico_exec,
            'metodo_exec': tank.metodo_exec,
            # incluir campos operacionais que o frontend usa para atualizar a lista
            'ensacamento_dia': getattr(tank, 'ensacamento_dia', None),
            'icamento_dia': getattr(tank, 'icamento_dia', None),
            'cambagem_dia': getattr(tank, 'cambagem_dia', None),
            'tambores_dia': getattr(tank, 'tambores_dia', None),
            'sentido_limpeza': getattr(tank, 'sentido_limpeza', None),
            'bombeio': getattr(tank, 'bombeio', None),
            'total_liquido': getattr(tank, 'total_liquido', None),
            # incluir acumulados operacionais para atualizar UI
            'ensacamento_cumulativo': getattr(tank, 'ensacamento_cumulativo', None),
            'icamento_cumulativo': getattr(tank, 'icamento_cumulativo', None),
            'cambagem_cumulativo': getattr(tank, 'cambagem_cumulativo', None),
            # novos acumulados (nomes do frontend)
            'total_liquido_acu': getattr(tank, 'total_liquido_cumulativo', None),
            'residuos_solidos_acu': getattr(tank, 'residuos_solidos_cumulativo', None),
        }

        return JsonResponse({'success': True, 'message': 'Tanque criado', 'tank': tank_payload})
    except Exception:
        logger.exception('Erro em add_tank_ajax')
        return JsonResponse({'success': False, 'error': 'Erro interno'}, status=500)


@login_required(login_url='/login/')
@require_POST
def update_rdo_tank_ajax(request, tank_id):
    """Atualiza um RdoTanque existente com campos enviados pelo frontend.

    Endpoint: POST /api/rdo/tank/<tank_id>/update/
    Reusa a lógica de parsing de `add_tank_ajax` (aceita aliases) e retorna
    payload similar a add_tank_ajax.
    """
    logger = logging.getLogger(__name__)
    try:
        try:
            tank = RdoTanque.objects.select_related('rdo').get(pk=tank_id)
        except RdoTanque.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Tanque não encontrado.'}, status=404)

        # Restrição: supervisores só podem operar sobre suas OS
        try:
            is_supervisor_user = (hasattr(request, 'user') and request.user.is_authenticated and request.user.groups.filter(name='Supervisor').exists())
        except Exception:
            is_supervisor_user = False
        if is_supervisor_user:
            ordem = getattr(tank.rdo, 'ordem_servico', None)
            if getattr(ordem, 'supervisor', None) != request.user:
                return JsonResponse({'success': False, 'error': 'Sem permissão para atualizar este tanque.'}, status=403)

        # Parsing helpers (reutilizar a mesma estratégia de add_tank_ajax)
        from decimal import Decimal

        def _norm_num(val):
            try:
                if val is None:
                    return None
                s = str(val).strip()
                if s == '':
                    return None
                if s.endswith('%'):
                    s = s[:-1].strip()
                s = s.replace(',', '.')
                return s if s != '' else None
            except Exception:
                return None

        def _get_int(name):
            raw = request.POST.get(name)
            s = _norm_num(raw)
            if s is None:
                return None
            try:
                return int(float(s))
            except Exception:
                return None

        def _get_decimal(name):
            raw = request.POST.get(name)
            s = _norm_num(raw)
            if s is None:
                return None
            try:
                return Decimal(str(s))
            except Exception:
                return None

        def _get_bool(name):
            v = request.POST.get(name)
            if v is None or v == '':
                return None
            s = str(v).strip().lower()
            if s in ('1', 'true', 't', 'yes', 'y', 'on', 'sim'):
                return True
            if s in ('0', 'false', 'f', 'no', 'n', 'off', 'nao', 'não'):
                return False
            return None

        def _parse_sentido():
            raw = None
            for k in ('sentido_limpeza', 'sentido', 'sent', 'sent_limpeza'):
                if k in request.POST and request.POST.get(k) not in (None, ''):
                    raw = request.POST.get(k)
                    break
            if raw is None:
                return None
            try:
                canon = _canonicalize_sentido(raw)
                return canon
            except Exception:
                return None

        # Build attrs dict similar to add_tank_ajax mapping
        attrs = {}
        mapping = {
            'tanque_codigo': 'tanque_codigo',
            'tanque_nome': 'nome_tanque',
            'nome_tanque': 'nome_tanque',
            'tipo_tanque': 'tipo_tanque',
            'numero_compartimento': 'numero_compartimentos',
            'numero_compartimentos': 'numero_compartimentos',
            'gavetas': 'gavetas',
            'patamar': 'patamares',
            'patamares': 'patamares',
            'volume_tanque_exec': 'volume_tanque_exec',
            'servico_exec': 'servico_exec',
            'metodo_exec': 'metodo_exec',
            'espaco_confinado': 'espaco_confinado',
            'operadores_simultaneos': 'operadores_simultaneos',
            'h2s_ppm': 'h2s_ppm',
            'lel': 'lel',
            'co_ppm': 'co_ppm',
            'o2_percent': 'o2_percent',
            'total_n_efetivo_confinado': 'total_n_efetivo_confinado',
            'tempo_bomba': 'tempo_bomba',
            'ensacamento_dia': 'ensacamento_dia',
            'icamento_dia': 'icamento_dia',
            'cambagem_dia': 'cambagem_dia',
            'ensacamento_prev': 'ensacamento_prev',
            'icamento_prev': 'icamento_prev',
            'cambagem_prev': 'cambagem_prev',
            'tambores_dia': 'tambores_dia',
            'residuos_solidos': 'residuos_solidos',
            'residuos_totais': 'residuos_totais',
            'bombeio': 'bombeio',
            'total_liquido': 'total_liquido',
            # cumulativos (aceitar *_acu e *_cumulativo)
            'ensacamento_acu': 'ensacamento_cumulativo',
            'icamento_acu': 'icamento_cumulativo',
            'cambagem_acu': 'cambagem_cumulativo',
            'ensacamento_cumulativo': 'ensacamento_cumulativo',
            'icamento_cumulativo': 'icamento_cumulativo',
            'cambagem_cumulativo': 'cambagem_cumulativo',
            'total_liquido_acu': 'total_liquido_cumulativo',
            'total_liquido_cumulativo': 'total_liquido_cumulativo',
            'residuos_solidos_acu': 'residuos_solidos_cumulativo',
            'residuos_solidos_cumulativo': 'residuos_solidos_cumulativo',
            'avanco_limpeza': 'avanco_limpeza',
            'avanco_limpeza_fina': 'avanco_limpeza_fina',
            'percentual_limpeza_diario': 'percentual_limpeza_diario',
            'percentual_limpeza_cumulativo': 'percentual_limpeza_cumulativo',
            'percentual_limpeza_fina': 'percentual_limpeza_fina',
            'percentual_limpeza_fina_diario': 'percentual_limpeza_fina_diario',
            'percentual_limpeza_fina_cumulativo': 'percentual_limpeza_fina_cumulativo',
            'percentual_ensacamento': 'percentual_ensacamento',
            'percentual_icamento': 'percentual_icamento',
            'percentual_cambagem': 'percentual_cambagem',
            'percentual_avanco': 'percentual_avanco',
            'compartimentos_avanco_json': 'compartimentos_avanco_json',
            'sentido_limpeza': 'sentido_limpeza',
        }

        int_fields = set([
            'numero_compartimentos', 'gavetas', 'patamares', 'operadores_simultaneos', 'total_n_efetivo_confinado',
            'ensacamento_dia', 'icamento_dia', 'cambagem_dia', 'tambores_dia', 'total_liquido', 'ensacamento_prev', 'icamento_prev', 'cambagem_prev',
            'ensacamento_cumulativo', 'icamento_cumulativo', 'cambagem_cumulativo',
            'total_liquido_cumulativo',
        ])
        decimal_fields = set([
            'volume_tanque_exec', 'h2s_ppm', 'lel', 'co_ppm', 'o2_percent', 'tempo_bomba', 'residuos_solidos', 'residuos_totais', 'bombeio',
            'percentual_limpeza_diario', 'percentual_limpeza_fina_diario', 'percentual_ensacamento', 'percentual_icamento', 'percentual_cambagem', 'percentual_avanco',
            'residuos_solidos_cumulativo',
        ])

        post = request.POST
        for post_key, model_key in mapping.items():
            if post_key in post:
                val = post.get(post_key)
                if val is None or val == '':
                    continue
                if model_key in int_fields:
                    parsed = _get_int(post_key)
                    if parsed is not None:
                        attrs[model_key] = parsed
                elif model_key in decimal_fields:
                    parsed = _get_decimal(post_key)
                    if parsed is not None:
                        attrs[model_key] = parsed
                else:
                    # special handling for sentido
                    if model_key == 'sentido_limpeza':
                        canon = _parse_sentido()
                        if canon:
                            attrs['sentido_limpeza'] = canon
                        else:
                            attrs['sentido_limpeza'] = val
                    else:
                        attrs[model_key] = val

        # Apply attrs to tank and save within transaction
        try:
            for k, v in attrs.items():
                try:
                    setattr(tank, k, v)
                except Exception:
                    logger.exception('Falha ao atribuir %s=%s ao tanque %s', k, v, tank_id)
            with transaction.atomic():
                tank.save()
        except Exception:
            logger.exception('Falha ao salvar tanque %s', tank_id)
            return JsonResponse({'success': False, 'error': 'Erro ao salvar tanque'}, status=500)

        # recompute metrics conservatively
        try:
            if hasattr(tank, 'recompute_metrics') and callable(tank.recompute_metrics):
                try:
                    tank.recompute_metrics(only_when_missing=False)
                    with transaction.atomic():
                        tank.save()
                except Exception:
                    logger.exception('Falha ao recomputar métricas para tanque %s', tank_id)
        except Exception:
            pass

        payload = {
            'id': tank.id,
            'tanque_codigo': tank.tanque_codigo,
            'nome_tanque': tank.nome_tanque,
            'tipo_tanque': tank.tipo_tanque,
            'numero_compartimentos': tank.numero_compartimentos,
            'gavetas': tank.gavetas,
            'patamares': tank.patamares,
            'volume_tanque_exec': str(tank.volume_tanque_exec) if tank.volume_tanque_exec is not None else None,
            'servico_exec': tank.servico_exec,
            'metodo_exec': tank.metodo_exec,
            # incluir campos operacionais que o frontend usa para atualizar a lista
            'ensacamento_dia': getattr(tank, 'ensacamento_dia', None),
            'icamento_dia': getattr(tank, 'icamento_dia', None),
            'cambagem_dia': getattr(tank, 'cambagem_dia', None),
            'tambores_dia': getattr(tank, 'tambores_dia', None),
            'sentido_limpeza': getattr(tank, 'sentido_limpeza', None),
            'bombeio': getattr(tank, 'bombeio', None),
            'total_liquido': getattr(tank, 'total_liquido', None),
            # incluir acumulados para atualizar UI
            'ensacamento_cumulativo': getattr(tank, 'ensacamento_cumulativo', None),
            'icamento_cumulativo': getattr(tank, 'icamento_cumulativo', None),
            'cambagem_cumulativo': getattr(tank, 'cambagem_cumulativo', None),
            'total_liquido_acu': getattr(tank, 'total_liquido_cumulativo', None),
            'residuos_solidos_acu': getattr(tank, 'residuos_solidos_cumulativo', None),
        }
        return JsonResponse({'success': True, 'message': 'Tanque atualizado', 'tank': payload})
    except Exception:
        logger.exception('Erro em update_rdo_tank_ajax')
        return JsonResponse({'success': False, 'error': 'Erro interno'}, status=500)


@login_required(login_url='/login/')
@require_POST
def delete_photo_basename_ajax(request):
    """
    Remove uma foto de um RDO com base na basename (nome do arquivo).
    Aceita rdo_id e um dos aliases: foto_basename|foto_name|basename|foto.
    Remove nos slots (fotos_1..fotos_5), relação fotos_rdo, campo único 'fotos'
    e também atualiza a lista consolidada 'fotos' (texto/JSON) removendo entradas que batam por basename.
    """
    logger = logging.getLogger(__name__)
    try:
        rdo_id = request.POST.get('rdo_id') or request.POST.get('id')
        name = next((request.POST.get(k) for k in ('foto_basename','foto_name','basename','foto') if request.POST.get(k)), None)
        if not rdo_id or not name:
            return JsonResponse({'success': False, 'error': 'rdo_id ou foto_basename não informados.'}, status=400)

        try:
            rdo_obj = RDO.objects.get(pk=rdo_id)
        except RDO.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'RDO não encontrado.'}, status=404)

        basename = str(name).strip().split('/')[-1].split('?')[0]
        if not basename:
            return JsonResponse({'success': False, 'error': 'Nome da foto inválido.'}, status=400)

        removed = []

        def safe_delete(file_field, path_name):
            try:
                if file_field:
                    file_field.delete(save=False)
                elif path_name:
                    default_storage.delete(path_name)
            except Exception:
                logger.warning('Falha ao deletar arquivo: %s', path_name, exc_info=True)

        # 1) Slots fotos_1..fotos_5
        for i in range(1, 6):
            slot = f'fotos_{i}'
            field = getattr(rdo_obj, slot, None)
            fname = getattr(field, 'name', None)
            if fname and fname.endswith('/' + basename):
                safe_delete(field, fname)
                try: setattr(rdo_obj, slot, None)
                except Exception: pass
                removed.append({'slot': slot, 'name': fname})

        # 2) Relação fotos_rdo
        try:
            for rel in list(getattr(rdo_obj, 'fotos_rdo').all()):
                foto_field = getattr(rel, 'foto', None)
                foto_name = getattr(foto_field, 'name', None)
                if foto_name and foto_name.endswith('/' + basename):
                    safe_delete(foto_field, foto_name)
                    rel_id = getattr(rel, 'id', None)
                    try: rel.delete()
                    except Exception: logger.exception('Falha ao deletar RDOFoto id=%s', rel_id)
                    removed.append({'rdofoto_id': rel_id, 'name': foto_name})
        except Exception:
            pass

        # 3) Campo único FileField 'fotos'
        try:
            single_field = getattr(rdo_obj, 'fotos', None)
            single_name = getattr(single_field, 'name', None)
            if single_name and single_name.endswith('/' + basename):
                safe_delete(single_field, single_name)
                try: rdo_obj.fotos = None
                except Exception: pass
                removed.append({'single': True, 'name': single_name})
        except Exception:
            pass

        # 4) Lista consolidada 'fotos' (texto/JSON com URLs/paths)
        try:
            cur = getattr(rdo_obj, 'fotos', None)
            # evitar sobrepor quando for FieldFile
            if not hasattr(cur, 'url'):
                def _basename_from_entry(entry):
                    try:
                        if not entry: return ''
                        val = str(entry).strip()
                        if '?' in val: val = val.split('?',1)[0]
                        from urllib.parse import urlparse as _u
                        try:
                            p = _u(val)
                            path = p.path if (p.scheme and p.netloc) else val
                        except Exception:
                            path = val
                        return path.rsplit('/',1)[-1] if '/' in path else path
                    except Exception:
                        return ''
                # obter lista atual
                lst = []
                if isinstance(cur, (list, tuple)):
                    lst = list(cur)
                elif isinstance(cur, str):
                    s = cur.strip()
                    if s.startswith('['):
                        try:
                            lst = json.loads(s)
                        except Exception:
                            lst = [ln for ln in s.splitlines() if ln.strip()]
                    elif s:
                        lst = [ln for ln in s.splitlines() if ln.strip()]
                # filtrar
                if lst:
                    new_list = [it for it in lst if _basename_from_entry(it) != basename]
                    if len(new_list) != len(lst):
                        try:
                            if isinstance(cur, (list, tuple)):
                                setattr(rdo_obj, 'fotos', new_list)
                            else:
                                setattr(rdo_obj, 'fotos', json.dumps(new_list))
                        except Exception:
                            try:
                                setattr(rdo_obj, 'fotos', json.dumps(new_list))
                            except Exception:
                                pass
                        removed.append({'consolidated': True, 'removed_count': (len(lst)-len(new_list))})
        except Exception:
            pass

        if removed:
            try:
                _safe_save_global(rdo_obj)
            except Exception:
                logger.exception('Falha ao salvar RDO após remoção de foto')
            return JsonResponse({'success': True, 'removed': removed})
        return JsonResponse({'success': False, 'error': 'Foto não encontrada no RDO.'}, status=404)
    except Exception:
        logger.exception('Erro em delete_photo_basename_ajax')
        return JsonResponse({'success': False, 'error': 'Erro interno'}, status=500)


    

@login_required(login_url='/login/')
def rdo(request):
    """Página principal do RDO: lista OS para o supervisor preencher/editar RDOs.
    MVP: lista todas as OS ordenadas por data desc.
    """
    # Identificar se o usuário é Supervisor
    is_supervisor_user = (hasattr(request, 'user') and request.user.is_authenticated and request.user.groups.filter(name='Supervisor').exists())

    # Ambiente separado: lista RDOs; filtrar para supervisores
    # Nota: se o usuário fornecer explicitamente o parâmetro `supervisor` na querystring
    # queremos respeitar esse filtro e não limitar automaticamente ao usuário logado.
    base_qs = RDO.objects.select_related('ordem_servico').all()
    try:
        supplied_supervisor = request.GET.get('supervisor')
    except Exception:
        supplied_supervisor = None
    if is_supervisor_user and not supplied_supervisor:
        base_qs = base_qs.filter(ordem_servico__supervisor=request.user)

    # ---- Filtragem server-side via querystring ----
    # Aceitamos parâmetros GET: contrato, os, empresa, unidade, turno,
    # servico, metodo, date_start, tanque, supervisor, status_geral
    try:
        from django.db.models import Q

        def _g(name):
            v = request.GET.get(name)
            if v is None:
                return None
            s = str(v).strip()
            return s if s != '' else None

        contrato = _g('contrato')
        os_q = _g('os')
        empresa = _g('empresa')
        unidade = _g('unidade')
        turno = _g('turno')
        servico = _g('servico')
        metodo = _g('metodo')
        date_start = _g('date_start')
        tanque = _g('tanque')
        supervisor = _g('supervisor')
        rdo = _g('rdo')
        status_geral = _g('status_geral')

        q_filters = Q()
        active_filters = 0

        if contrato:
            active_filters += 1
            q_filters &= (Q(contrato_po__icontains=contrato) | Q(po__icontains=contrato))
        if os_q:
            active_filters += 1
            q_filters &= Q(ordem_servico__numero_os__icontains=os_q)
        if empresa:
            active_filters += 1
            # OrdemServico armazena Cliente como FK em `Cliente` (com property `cliente` para compat).
            # Filtrar por property (ordem_servico__cliente) não funciona no ORM.
            q_filters &= Q(ordem_servico__Cliente__nome__icontains=empresa)
        if unidade:
            active_filters += 1
            # OrdemServico armazena Unidade como FK em `Unidade` (com property `unidade` para compat).
            # Filtrar por property (ordem_servico__unidade) não funciona no ORM.
            q_filters &= Q(ordem_servico__Unidade__nome__icontains=unidade)
        if turno:
            active_filters += 1
            q_filters &= Q(turno__icontains=turno)
        if servico:
            active_filters += 1
            q_filters &= (Q(servico_exec__icontains=servico) | Q(tanques__servico_exec__icontains=servico) | Q(ordem_servico__servico__icontains=servico))
        if metodo:
            active_filters += 1
            q_filters &= (Q(metodo_exec__icontains=metodo) | Q(tanques__metodo_exec__icontains=metodo) | Q(ordem_servico__metodo__icontains=metodo))
        if tanque:
            active_filters += 1
            q_filters &= (Q(nome_tanque__icontains=tanque) | Q(tanques__nome_tanque__icontains=tanque) | Q(tanque_codigo__icontains=tanque) | Q(tanques__tanque_codigo__icontains=tanque))
        if supervisor:
            active_filters += 1
            # Normalize supervisor search to match different stored forms:
            # - username like 'carolina.machado'
            # - first_name / last_name fields
            # - 'First Last' typed by user should match username with dot or space
            def _supervisor_search_q(val):
                import unicodedata
                def _strip_accents(s):
                    if not s:
                        return s
                    try:
                        nkfd = unicodedata.normalize('NFKD', s)
                        return ''.join([c for c in nkfd if not unicodedata.combining(c)])
                    except Exception:
                        return s

                raw = (val or '').strip()
                if not raw:
                    return Q()

                raw_noaccent = _strip_accents(raw).lower()
                parts = [p for p in raw_noaccent.split() if p]

                # base Q: try raw against username/first/last
                q = Q(ordem_servico__supervisor__username__icontains=raw) | Q(ordem_servico__supervisor__first_name__icontains=raw) | Q(ordem_servico__supervisor__last_name__icontains=raw)
                # also try accent-folded matches
                q |= Q(ordem_servico__supervisor__username__icontains=raw_noaccent) | Q(ordem_servico__supervisor__first_name__icontains=raw_noaccent) | Q(ordem_servico__supervisor__last_name__icontains=raw_noaccent)

                # tokenized match: try first/last combinations
                if len(parts) >= 2:
                    first = parts[0]
                    last = parts[-1]
                    q |= (Q(ordem_servico__supervisor__first_name__icontains=first) & Q(ordem_servico__supervisor__last_name__icontains=last))
                    q |= (Q(ordem_servico__supervisor__first_name__icontains=last) & Q(ordem_servico__supervisor__last_name__icontains=first))

                    # username-like variant: join tokens with dot and also without separator
                    try:
                        uname_dot = '.'.join(parts)
                        uname_nospace = ''.join(parts)
                        q |= Q(ordem_servico__supervisor__username__icontains=uname_dot) | Q(ordem_servico__supervisor__username__icontains=uname_nospace)
                    except Exception:
                        pass
                else:
                    # single token: also try matching username variants
                    try:
                        p = parts[0] if parts else ''
                        if p:
                            q |= Q(ordem_servico__supervisor__username__icontains=p)
                    except Exception:
                        pass

                return q

            try:
                q_filters &= _supervisor_search_q(supervisor)
            except Exception:
                # fallback minimal matching
                q_filters &= (Q(ordem_servico__supervisor__username__icontains=supervisor) | Q(ordem_servico__supervisor__first_name__icontains=supervisor) | Q(ordem_servico__supervisor__last_name__icontains=supervisor))
        if rdo:
            # filtro por número/identificador do RDO (campo do próprio modelo RDO)
            try:
                active_filters += 1
                q_filters &= (Q(rdo__icontains=rdo) | Q(rdo__iexact=rdo))
            except Exception:
                pass
        if status_geral:
            active_filters += 1
            q_filters &= Q(ordem_servico__status_geral__icontains=status_geral)
        if date_start:
            active_filters += 1
            try:
                from datetime import datetime
                d = datetime.fromisoformat(date_start).date()
                q_filters &= (Q(data__gte=d) | Q(data_inicio__gte=d))
            except Exception:
                # aceitar outras formas de data se necessário; ignorar se inválida
                pass

        # Aplicar filtros ao queryset base (distinct para evitar duplicados por joins)
        if q_filters:
            try:
                base_qs = base_qs.filter(q_filters).distinct()
            except Exception:
                # falha na filtragem não deve quebrar a página; cair para queryset sem filtros
                pass
    except Exception:
        # segurança: qualquer erro de parsing não deve interromper a view
        active_filters = 0

    # Expor contador de filtros aplicados ao contexto abaixo
    try:
        request._rdo_active_filters = int(active_filters)
    except Exception:
        request._rdo_active_filters = 0

    # Nota: removida filtragem automática que excluía RDOs ligados a OS com
    # status finalizado/retornado. A tabela deve exibir essas linhas — o
    # controle de visibilidade específico (por exemplo: esconder cartões no
    # view do supervisor) é feito no template/JS. Mantemos o queryset intacto.
    rdos = base_qs.order_by('-data', '-id')
    # Nota: removido filtro runtime que excluía RDOs cujo OS estivesse marcado
    # como finalizado. Queremos que a tabela mostre entradas finalizadas também.
    # Paginação: 6 itens por página
    page = request.GET.get('page', 1)
    try:
        is_force_mobile = bool(request.GET.get('mobile') == '1') or bool(request.GET.get('force_mobile')) or bool(request.GET.get('force_mobile') == '1')
    except Exception:
        is_force_mobile = False

    if is_supervisor_user and is_force_mobile:
        # Build a small ordered list of most-recent RDO per OrdemServico and keep only the latest
        unique = []
        seen = set()
        for r in rdos:
            # defesa adicional: pular RDOs ligados a OS com status_geral finalizada
            try:
                os_obj = getattr(r, 'ordem_servico', None)
                st = getattr(os_obj, 'status_geral', '') or ''
                if isinstance(st, str) and st.strip():
                    low = st.lower()
                    if any(k in low for k in ('retorn', 'finaliz', 'encerrad', 'fechad', 'conclu')):
                        continue
            except Exception:
                pass
            try:
                osid = getattr(r, 'ordem_servico_id', None) or (r.ordem_servico.id if getattr(r, 'ordem_servico', None) else None)
            except Exception:
                osid = None
            if osid is None:
                # if no OS linked, still allow the entry but avoid duplicates
                key = ('no-os', getattr(r, 'id', None))
            else:
                key = osid
            if key in seen:
                continue
            seen.add(key)
            unique.append(r)
            # we only want one OS shown at a time for supervisors in mobile mode
            if len(unique) >= 1:
                break
        # create a small paginator from the list so template rendering stays compatible
        try:
            per_page = int(request.GET.get('per_page') or request.GET.get('perpage') or 6)
        except Exception:
            per_page = 6
        try:
            if per_page <= 0 or per_page > 500:
                per_page = 6
        except Exception:
            per_page = 6

        paginator = Paginator(unique, per_page)
        try:
            servicos = paginator.page(1)
        except Exception:
            servicos = paginator.page(1)
    else:
        # Para a listagem padrão (não-supervisor), apresentar uma linha por TANQUE.
        # Se o RDO tiver tanques relacionados (RdoTanque), expandir em múltiplas linhas
        # repetindo os dados do RDO e substituindo os campos específicos do tanque.
        try:
            from types import SimpleNamespace
        except Exception:
            SimpleNamespace = None

        flat_rows = []
        for r in rdos:
            try:
                # Obter tanques relacionais quando existirem
                tanks = []
                try:
                    # Preferir o related_name canônico 'tanques'; manter fallback para
                    # instalações antigas que usem o nome padrão 'rdotanque_set'.
                    manager = getattr(r, 'tanques', None) or getattr(r, 'rdotanque_set', None)
                    if manager is not None:
                        tanks = list(manager.all())
                    else:
                        tanks = []
                except Exception:
                    tanks = []

                if tanks:
                    for t in tanks:
                        try:
                            row = SimpleNamespace() if SimpleNamespace else type('Row', (), {})()
                            # Copiar campos base do RDO
                            row.id = r.id
                            row.rdo = getattr(r, 'rdo', None)
                            row.data = getattr(r, 'data', None)
                            row.data_inicio = getattr(r, 'data_inicio', None)
                            row.previsao_termino = getattr(r, 'previsao_termino', None)
                            row.ordem_servico = getattr(r, 'ordem_servico', None)
                            row.contrato_po = getattr(r, 'contrato_po', None)
                            row.turno = getattr(r, 'turno', None)
                            # Substituir campos específicos do tanque com dados do relacional
                            row.tanque_codigo = getattr(t, 'tanque_codigo', None)
                            row.nome_tanque = getattr(t, 'nome_tanque', None)
                            row.tipo_tanque = getattr(t, 'tipo_tanque', None)
                            row.numero_compartimentos = getattr(t, 'numero_compartimentos', getattr(t, 'numero_compartimento', None))
                            row.gavetas = getattr(t, 'gavetas', None)
                            row.patamares = getattr(t, 'patamares', getattr(t, 'patamar', None))
                            row.volume_tanque_exec = getattr(t, 'volume_tanque_exec', None)
                            row.servico_exec = getattr(t, 'servico_exec', None)
                            row.metodo_exec = getattr(t, 'metodo_exec', None)
                            row.operadores_simultaneos = getattr(t, 'operadores_simultaneos', None)
                            row.h2s_ppm = getattr(t, 'h2s_ppm', None)
                            row.lel = getattr(t, 'lel', None)
                            row.co_ppm = getattr(t, 'co_ppm', None)
                            row.o2_percent = getattr(t, 'o2_percent', None)
                            # Totais diários vinculados ao tanque quando existirem
                            row.tambores = getattr(t, 'tambores_dia', None)
                            row.total_solidos = getattr(t, 'residuos_solidos', None)
                            row.total_residuos = getattr(t, 'residuos_totais', None)
                            flat_rows.append(row)
                        except Exception:
                            # Em caso de erro em um tanque, cair para a linha do próprio RDO
                            pass
                else:
                    # Sem tanques relacionais: manter linha única baseada no próprio RDO (legado)
                    row = SimpleNamespace() if SimpleNamespace else type('Row', (), {})()
                    row.id = r.id
                    row.rdo = getattr(r, 'rdo', None)
                    row.data = getattr(r, 'data', None)
                    row.data_inicio = getattr(r, 'data_inicio', None)
                    row.previsao_termino = getattr(r, 'previsao_termino', None)
                    row.ordem_servico = getattr(r, 'ordem_servico', None)
                    row.contrato_po = getattr(r, 'contrato_po', None)
                    row.turno = getattr(r, 'turno', None)
                    row.tanque_codigo = getattr(r, 'tanque_codigo', None)
                    row.nome_tanque = getattr(r, 'nome_tanque', None)
                    row.tipo_tanque = getattr(r, 'tipo_tanque', None)
                    row.numero_compartimentos = getattr(r, 'numero_compartimentos', None)
                    row.gavetas = getattr(r, 'gavetas', None)
                    row.patamares = getattr(r, 'patamares', None)
                    row.volume_tanque_exec = getattr(r, 'volume_tanque_exec', None)
                    row.servico_exec = getattr(r, 'servico_exec', None)
                    row.metodo_exec = getattr(r, 'metodo_exec', None)
                    row.operadores_simultaneos = getattr(r, 'operadores_simultaneos', None)
                    row.h2s_ppm = getattr(r, 'h2s_ppm', None)
                    row.lel = getattr(r, 'lel', None)
                    row.co_ppm = getattr(r, 'co_ppm', None)
                    row.o2_percent = getattr(r, 'o2_percent', None)
                    row.tambores = getattr(r, 'tambores', None)
                    row.total_solidos = getattr(r, 'total_solidos', None)
                    row.total_residuos = getattr(r, 'total_residuos', None)
                    flat_rows.append(row)
            except Exception:
                # Fallback: se ocorrer qualquer erro ao montar as linhas para este RDO,
                # ainda assim emitir uma linha única baseada no próprio RDO (legado)
                row = SimpleNamespace() if SimpleNamespace else type('Row', (), {})()
                row.id = getattr(r, 'id', None)
                row.rdo = getattr(r, 'rdo', None)
                row.data = getattr(r, 'data', None)
                row.data_inicio = getattr(r, 'data_inicio', None)
                row.previsao_termino = getattr(r, 'previsao_termino', None)
                row.ordem_servico = getattr(r, 'ordem_servico', None)
                row.contrato_po = getattr(r, 'contrato_po', None)
                row.turno = getattr(r, 'turno', None)
                row.tanque_codigo = getattr(r, 'tanque_codigo', None)
                row.nome_tanque = getattr(r, 'nome_tanque', None)
                row.tipo_tanque = getattr(r, 'tipo_tanque', None)
                row.numero_compartimentos = getattr(r, 'numero_compartimentos', None)
                row.gavetas = getattr(r, 'gavetas', None)
                row.patamares = getattr(r, 'patamares', None)
                row.volume_tanque_exec = getattr(r, 'volume_tanque_exec', None)
                row.servico_exec = getattr(r, 'servico_exec', None)
                row.metodo_exec = getattr(r, 'metodo_exec', None)
                row.operadores_simultaneos = getattr(r, 'operadores_simultaneos', None)
                row.h2s_ppm = getattr(r, 'h2s_ppm', None)
                row.lel = getattr(r, 'lel', None)
                row.co_ppm = getattr(r, 'co_ppm', None)
                row.o2_percent = getattr(r, 'o2_percent', None)
                row.tambores = getattr(r, 'tambores', None)
                row.total_solidos = getattr(r, 'total_solidos', None)
                row.total_residuos = getattr(r, 'total_residuos', None)
                flat_rows.append(row)
        # Paginar a lista achatada
        try:
            per_page = int(request.GET.get('per_page') or request.GET.get('perpage') or 6)
        except Exception:
            per_page = 6
        # sanitize: enforce sensible bounds
        try:
            if per_page <= 0 or per_page > 500:
                per_page = 6
        except Exception:
            per_page = 6

        paginator = Paginator(flat_rows, per_page)
        try:
            servicos = paginator.page(page)
        except PageNotAnInteger:
            servicos = paginator.page(1)
        except EmptyPage:
            servicos = paginator.page(paginator.num_pages)
    # Choices de serviço e método do modelo OrdemServico para uso no modal supervisor
    from .models import OrdemServico
    servico_choices = OrdemServico.SERVICO_CHOICES
    # Limitar as opções de método conforme solicitado: apenas Manual, Mecanizada e Robotizada
    metodo_choices = [
        ('Manual', 'Manual'),
        ('Mecanizada', 'Mecanizada'),
        ('Robotizada', 'Robotizada'),
    ]
    # disponibilizar listas de pessoas e funções para popular selects no template.
    try:
        get_pessoas = Pessoa.objects.order_by('nome').all()
    except Exception:
        get_pessoas = []
    try:
        # Construir lista combinada: constantes FUNCOES (OrdemServico.FUNCOES) + entradas em tabela Funcao
        from types import SimpleNamespace
        db_funcoes_qs = Funcao.objects.order_by('nome').all()
        db_funcoes_names = [f.nome for f in db_funcoes_qs]
        const_funcoes = [t[0] for t in getattr(OrdemServico, 'FUNCOES', [])]
        # evitar duplicatas: incluir apenas constantes que não existem no DB
        const_only = [SimpleNamespace(nome=name) for name in const_funcoes if name not in db_funcoes_names]
        db_funcoes_objs = [SimpleNamespace(nome=f.nome) for f in db_funcoes_qs]
        # mostrar constantes primeiro, depois funções cadastradas pelo admin
        get_funcoes = const_only + db_funcoes_objs
    except Exception:
        get_funcoes = []
    # Construir um mapa canonical_login -> nome para uso imediato no frontend.
    # Ex.: 'carolina.machado' -> 'Carolina Machado'
    try:
        def _canonical_login_from_name(name):
            if not name:
                return ''
            # Normalizar acentos, degradar para ASCII
            s = unicodedata.normalize('NFKD', str(name))
            s = ''.join([c for c in s if not unicodedata.combining(c)])
            s = s.lower()
            # substituir qualquer sequência de caracteres não alfanuméricos por '.'
            import re
            s = re.sub(r'[^a-z0-9]+', '.', s)
            s = re.sub(r'\.+', '.', s)
            s = s.strip('.')
            return s

        pessoas_map = {}
        try:
            for p in (get_pessoas or []):
                nome = getattr(p, 'nome', None) or ''
                key = _canonical_login_from_name(nome)
                if key:
                    pessoas_map[key] = nome
        except Exception:
            pessoas_map = {}
        # incluir também mapeamento para possíveis supervisors vindos na lista de RDOs (username -> full name)
        try:
            for r in rdos:
                ordem_obj = getattr(r, 'ordem_servico', None)
                sup = getattr(ordem_obj, 'supervisor', None) if ordem_obj else None
                if sup is None:
                    continue
                # se for objeto user-like, tente extrair username e full name
                try:
                    uname = getattr(sup, 'username', None)
                    full = sup.get_full_name() if hasattr(sup, 'get_full_name') else str(sup)
                except Exception:
                    uname = None
                    full = str(sup)
                if uname:
                    pessoas_map.setdefault(str(uname).lower(), full or uname)
        except Exception:
            pass

        import json as _json
        pessoas_map_json = _json.dumps(pessoas_map)
    except Exception:
        pessoas_map_json = '{}'

    # Ajustar índices mostrados: usar contagem real de objetos na página
    try:
        obj_list = list(getattr(servicos, 'object_list', [])) if servicos is not None else []
        count_on_page = len(obj_list)
    except Exception:
        count_on_page = 0
    try:
        if servicos is not None and hasattr(servicos, 'start_index') and callable(servicos.start_index):
            start_idx = servicos.start_index()
        else:
            # fallback: assume 1 quando houver pelo menos um item
            start_idx = 1 if count_on_page > 0 else 0
    except Exception:
        start_idx = 1 if count_on_page > 0 else 0

    if count_on_page <= 0:
        page_start = 0
        page_end = 0
    else:
        page_start = start_idx
        page_end = start_idx + count_on_page - 1

    return render(request, 'rdo.html', {
        'rdos': rdos,
        'servicos': servicos,
        # número de filtros ativos aplicados (usado no template/JS para badge)
        'active_filters_count': getattr(request, '_rdo_active_filters', 0),
        # indicador para template mostrar badge 'Nenhum resultado'
        'no_results': (getattr(paginator, 'count', 0) == 0),
        'show_pagination': (hasattr(paginator, 'num_pages') and getattr(paginator, 'num_pages', 0) > 1),
        'servico_choices': servico_choices,
        'metodo_choices': metodo_choices,
        # escolhas de atividades do modelo RDO (para popular selects no modal)
        'atividades_choices': getattr(RDO, 'ATIVIDADES_CHOICES', []),
        # number of activity slots shown in the report modal (0..8)
        'activity_slots': list(range(9)),
        # Forçar versão mobile somente quando o query param mobile=1 estiver presente.
        # Removemos a dependência de session['force_mobile'] para evitar forçar mobile em desktops.
        'force_mobile': True if request.GET.get('mobile') == '1' else False,
        # Indica ao template se o usuário atual pertence ao grupo Supervisor
        'is_supervisor': is_supervisor_user,
        # current per-page value (int) used by template to select dropdown default
        'per_page_current': int(request.GET.get('per_page') or request.GET.get('perpage') or 6),
        'get_pessoas': get_pessoas,
        # total de linhas resultantes (usado pelo template para decidir exibir o seletor)
        'total_count': getattr(paginator, 'count', 0),
        # índices da página mostrados ao usuário (ajustados para refletir
        # o número real de itens renderizados na página)
        'page_start': page_start,
        'page_end': page_end,
        'get_funcoes': get_funcoes,
        'pessoas_map_json': pessoas_map_json,
    })


@login_required(login_url='/login/')
@require_GET
def pending_os_json(request):
    """API que retorna as OS pendentes de RDO.

    Critério: todas as Ordens de Serviço (OrdemServico) que não possuem um RDO
    associado na tabela RDO (i.e., OrdemServico.rdos.exists() == False).

    Retorna JSON no formato:
    { 'count': int, 'os_list': [ { 'id': int, 'numero_os': int, 'empresa': str, 'unidade': str, 'supervisor': str }, ... ] }
    """
    try:
        # Seleciona ordens de serviço que não têm RDOs relacionadas
        qs = OrdemServico.objects.filter(rdos__isnull=True)
        # Excluir ordens que já estão finalizadas/encerradas/fechadas/concluídas
        # (podem ser armazenadas em vários campos dependendo da versão do modelo)
        try:
            final_pattern = r'finaliz|encerrad|fechad|conclu'
            qs = qs.exclude(
                Q(status_geral__iregex=final_pattern) |
                Q(status_operacao__iregex=final_pattern) |
                Q(status_frente__iregex=final_pattern) |
                Q(status__iregex=final_pattern)
            )
        except Exception:
            # Não interromper o fluxo se os campos não existirem no modelo
            pass
        # Se usuário for Supervisor, restringir apenas às OS sob sua responsabilidade
        try:
            is_supervisor_user = (hasattr(request, 'user') and request.user.is_authenticated and request.user.groups.filter(name='Supervisor').exists())
        except Exception:
            is_supervisor_user = False
        if is_supervisor_user:
            qs = qs.filter(supervisor=request.user)
        # ordenar por data de criação/ID para previsibilidade
        qs = qs.order_by('-id')[:200]
        os_list = []
        # palavras-chave que indicam que uma OS está finalizada/retornada/encerrada
        runtime_final_keywords = ('retorn', 'finaliz', 'encerrad', 'fechad', 'conclu')
        for o in qs:
            # Verificação defensiva: se o.status_geral contém uma palavra indicando finalizado,
            # pule a OS mesmo que o queryset anterior não tenha excluído corretamente.
            try:
                st = getattr(o, 'status_geral', '') or ''
                if isinstance(st, str) and st.strip():
                    low = st.lower()
                    if any(k in low for k in runtime_final_keywords):
                        # pular entradas finalizadas/retornadas
                        continue
            except Exception:
                # não falhar por conta deste check; prossiga normalmente
                pass

            # garantir que o.supervisor seja serializado como string (nome ou username) para o frontend
            try:
                if getattr(o, 'supervisor', None):
                    try:
                        sup_val = o.supervisor.get_full_name() or o.supervisor.username
                    except Exception:
                        sup_val = str(o.supervisor)
                else:
                    sup_val = ''
            except Exception:
                sup_val = ''

            os_list.append({
                'id': o.id,
                'numero_os': o.numero_os,
                'empresa': o.cliente,
                'unidade': o.unidade,
                'supervisor': sup_val,
                'status_geral': getattr(o, 'status_geral', '') or '',
                # fornecer data_fim da OS no formato ISO (YYYY-MM-DD) quando disponível
                'data_fim': (o.data_fim.isoformat() if getattr(o, 'data_fim', None) else ''),
            })
        return JsonResponse({'success': True, 'count': len(os_list), 'data': os_list, 'os_list': os_list})
    except Exception:
        logger = logging.getLogger(__name__)
        logger.exception('Erro ao gerar lista de OS pendentes')
        return JsonResponse({'success': False, 'count': 0, 'data': [], 'os_list': []}, status=500)


@login_required(login_url='/login/')
@require_GET
def next_rdo(request):
    """Retorna o próximo número de RDO esperado para uma Ordem de Serviço.

    Parâmetros: ?os_id=<id>
    Retorna JSON: {'success': True, 'next_rdo': <int>} ou {'success': False, 'error': ...}
    Nota: este endpoint é apenas informativo e não reserva o número; a reserva
    atômica é feita em create_rdo_ajax.
    """
    try:
        os_id = request.GET.get('os_id') or request.GET.get('ordem_servico_id')
        os_obj = None
        if os_id:
            try:
                os_obj = OrdemServico.objects.get(pk=os_id)
            except OrdemServico.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Ordem de Serviço não encontrada (os_id).'}, status=404)
        else:
            # Fallback: aceitar número da OS quando id não for fornecido
            numero = request.GET.get('numero_os') or request.GET.get('numero') or request.GET.get('os_numero')
            if not numero:
                return JsonResponse({'success': False, 'error': 'os_id ou numero_os não informado.'}, status=400)
            # tentar converter para int e buscar
            try:
                # permitir string que contenha apenas dígitos
                numero_val = int(str(numero).strip())
            except Exception:
                numero_val = None
            try:
                if numero_val is not None:
                    os_obj = OrdemServico.objects.filter(numero_os=numero_val).first()
                else:
                    # tentativa por igualdade textual (caso numero_os seja string com prefixos)
                    os_obj = OrdemServico.objects.filter(numero_os__iexact=str(numero).strip()).first()
                if not os_obj:
                    return JsonResponse({'success': False, 'error': 'Ordem de Serviço não encontrada (numero_os).'}, status=404)
            except Exception:
                return JsonResponse({'success': False, 'error': 'Erro ao buscar Ordem de Serviço.'}, status=500)

    # Calcular próximo RDO sem reservar (read-only).
        # Observação: o campo `rdo` no modelo historicamente já foi armazenado
        # como string em algumas instalações (ex.: 'RDO-1', '1', '01'). Logo,
        # confiar em aggregate(Max('rdo')) pode ser incorreto (ordenação
        # lexicográfica). Para robustez, iteramos as entradas e extraímos
        # sequências numéricas presentes no valor, escolhendo o maior número
        # encontrado e somando 1.
        import re
        max_val = None
        # Construir queryset base de RDOs: preferir buscar por numero_os quando
        # disponível, pois algumas instalações gravam RDOs ligados a ordens
        # que compartilham o mesmo numero_os mas podem ter PKs diferentes.
        try:
            if os_obj is not None:
                numero_for_lookup = getattr(os_obj, 'numero_os', None)
                if numero_for_lookup is not None:
                    rdo_qs = RDO.objects.filter(ordem_servico__numero_os=numero_for_lookup)
                else:
                    rdo_qs = RDO.objects.filter(ordem_servico=os_obj)
            else:
                # os_obj pode ser None when we looked up by numero earlier and set os_obj accordingly,
                # but keep safe fallback: empty queryset
                rdo_qs = RDO.objects.none()
        except Exception:
            # Fallback conservador
            try:
                rdo_qs = RDO.objects.filter(ordem_servico=os_obj) if os_obj is not None else RDO.objects.none()
            except Exception:
                rdo_qs = RDO.objects.none()
        try:
            # Tentar aggregate primeiro (rápido quando o campo for numérico)
            try:
                agg = rdo_qs.aggregate(max_rdo=Max('rdo'))
                max_rdo_raw = agg.get('max_rdo')
                if max_rdo_raw is not None:
                    try:
                        max_val = int(str(max_rdo_raw))
                    except Exception:
                        # ignora e cairá para a varredura completa
                        max_val = None
            except Exception:
                max_val = None

            # Varredura completa: extrair todas as sequências numéricas dos
            # valores de `rdo` e escolher a maior encontrada.
            try:
                for r in rdo_qs.only('rdo'):
                    raw = getattr(r, 'rdo', None)
                    if raw is None:
                        continue
                    s = str(raw).strip()
                    if not s:
                        continue
                    # buscar todas as sequências de dígitos no valor (ex.: 'RDO-12' -> ['12'])
                    nums = re.findall(r"\d+", s)
                    if nums:
                        for n in nums:
                            try:
                                v = int(n)
                                if max_val is None or v > max_val:
                                    max_val = v
                            except Exception:
                                continue
                    else:
                        # caso não haja dígitos, tentar conversão direta (ex.: '3')
                        try:
                            v = int(s)
                            if max_val is None or v > max_val:
                                max_val = v
                        except Exception:
                            continue
            except Exception:
                # em caso de erro na iteração, deixamos max_val como está
                pass
        except Exception:
            max_val = None

        next_num = (max_val or 0) + 1
        # se o cliente pedir debug, incluir lista de RDOs encontrados para
        # diagnóstico (não inclui dados sensíveis, apenas os valores do campo rdo)
        try:
            debug_flag = str(request.GET.get('debug') or '').strip() in ('1', 'true', 'yes')
        except Exception:
            debug_flag = False

        if debug_flag:
            try:
                existing = [ (getattr(r,'rdo', None) if getattr(r,'rdo', None) is not None else None) for r in rdo_qs.only('rdo') ]
            except Exception:
                existing = []
            return JsonResponse({'success': True, 'next_rdo': next_num, 'max_rdo': max_val, 'existing_rdos': existing})

        return JsonResponse({'success': True, 'next_rdo': next_num})
    except Exception:
        logger = logging.getLogger(__name__)
        logger.exception('Erro em next_rdo')
        return JsonResponse({'success': False, 'error': 'Erro interno'}, status=500)
