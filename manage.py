#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
import hashlib

# Aplicar shim para hashlib.openssl_md5 para evitar TypeError quando reportlab é importado
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


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
