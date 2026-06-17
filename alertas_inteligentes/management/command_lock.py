from contextlib import contextmanager
from threading import local
from uuid import uuid4

from django.core.cache import caches
from django.utils import timezone


COMMAND_EXECUTION_LOCK_CACHE_ALIAS = "synchro_ai_lock"
COMMAND_EXECUTION_LOCK_KEY = "alertas_inteligentes:command_lock:synchro_ai"
COMMAND_EXECUTION_LOCK_TIMEOUT = 60 * 60

_state = local()


def _owned_locks():
    owned = getattr(_state, "owned_locks", None)
    if owned is None:
        owned = {}
        _state.owned_locks = owned
    return owned


@contextmanager
def command_execution_lock(command_name, timeout=COMMAND_EXECUTION_LOCK_TIMEOUT):
    lock_cache = caches[COMMAND_EXECUTION_LOCK_CACHE_ALIAS]
    owned = _owned_locks()

    if COMMAND_EXECUTION_LOCK_KEY in owned:
        yield {
            "acquired": True,
            "reentrant": True,
            "owner": owned[COMMAND_EXECUTION_LOCK_KEY],
        }
        return

    token = uuid4().hex
    owner = {
        "token": token,
        "command": command_name,
        "started_at": timezone.now().isoformat(),
    }

    acquired = lock_cache.add(COMMAND_EXECUTION_LOCK_KEY, owner, timeout=timeout)
    if not acquired:
        yield {
            "acquired": False,
            "reentrant": False,
            "owner": lock_cache.get(COMMAND_EXECUTION_LOCK_KEY) or {},
        }
        return

    owned[COMMAND_EXECUTION_LOCK_KEY] = owner

    try:
        yield {
            "acquired": True,
            "reentrant": False,
            "owner": owner,
        }
    finally:
        current_owner = lock_cache.get(COMMAND_EXECUTION_LOCK_KEY) or {}
        if current_owner.get("token") == token:
            lock_cache.delete(COMMAND_EXECUTION_LOCK_KEY)
        owned.pop(COMMAND_EXECUTION_LOCK_KEY, None)


def build_lock_message(lock_info):
    owner = lock_info.get("owner") or {}
    command_name = owner.get("command")
    started_at = owner.get("started_at")

    if command_name and started_at:
        return (
            "Rotina Synchro AI ja esta em execucao "
            f"({command_name} iniciado em {started_at}). Encerrando esta execucao."
        )

    if command_name:
        return (
            "Rotina Synchro AI ja esta em execucao "
            f"({command_name}). Encerrando esta execucao."
        )

    return "Rotina Synchro AI ja esta em execucao. Encerrando esta execucao."
