from contextlib import contextmanager

import requests
from django.conf import settings


@contextmanager
def _requests_get_default_timeout(timeout_seconds):
    original_get = requests.get

    def get_with_timeout(*args, **kwargs):
        kwargs.setdefault("timeout", timeout_seconds)
        return original_get(*args, **kwargs)

    requests.get = get_with_timeout
    try:
        yield
    finally:
        requests.get = original_get


def translate_pt_to_en(text, timeout_seconds=None):
    from deep_translator import GoogleTranslator

    effective_timeout = timeout_seconds
    if effective_timeout is None:
        effective_timeout = getattr(
            settings,
            "TRANSLATE_PREVIEW_TIMEOUT_SECONDS",
            5,
        )

    with _requests_get_default_timeout(effective_timeout):
        return GoogleTranslator(source="pt", target="en").translate(text)
