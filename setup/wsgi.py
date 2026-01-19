import os
import hashlib

_openssl_md5 = getattr(hashlib, 'openssl_md5', None)
if _openssl_md5 is not None:
	def _openssl_md5_compat(data=b'', *args, **kwargs):
		try:
			return _openssl_md5(data)
		except TypeError:
			return _openssl_md5()
	hashlib.openssl_md5 = _openssl_md5_compat
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