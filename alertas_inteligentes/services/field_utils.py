def get_field_safe(obj, *names, default=None):
    if obj is None:
        return default

    for name in names:
        if not name or not isinstance(name, str):
            continue
        try:
            if hasattr(obj, name):
                return getattr(obj, name)
        except Exception:
            continue

    return default


def has_field_safe(obj, *names):
    if obj is None:
        return False

    for name in names:
        if not name or not isinstance(name, str):
            continue
        try:
            if hasattr(obj, name):
                return True
        except Exception:
            continue

    return False
