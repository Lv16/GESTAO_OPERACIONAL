"""
WSGI config for setup project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os
import hashlib

# Compat shim global: algumas builds de OpenSSL expõem hashlib.openssl_md5 que não aceita
# o kwarg `usedforsecurity`. Em ambientes onde reportlab chama md5(usedforsecurity=False)
# isto causa TypeError. Substituímos por um wrapper que ignora kwargs extras.
_openssl_md5 = getattr(hashlib, 'openssl_md5', None)
if _openssl_md5 is not None:
	def _openssl_md5_compat(data=b'', *args, **kwargs):
		try:
			return _openssl_md5(data)
		except TypeError:
			return _openssl_md5()
	hashlib.openssl_md5 = _openssl_md5_compat
# Garantir compatibilidade também para hashlib.md5 caso a implementação subjacente não aceite kwargs
_orig_md5 = getattr(hashlib, 'md5', None)
if _orig_md5 is not None:
	def _md5_compat(data=b'', *args, **kwargs):
		try:
			return _orig_md5(data, **kwargs)
		except TypeError:
			return _orig_md5(data)
	hashlib.md5 = _md5_compat

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')

application = get_wsgi_application()
