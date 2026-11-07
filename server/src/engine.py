"""Bridge to the trained model package `retrofit_engine/` (owned by the AI domain, used read-only here).

The package lives at the repo root. In Docker it is copied next to `src/` (/app/retrofit_engine), so it is
importable from the working directory. For local runs from `server/` we add the repo root to sys.path once.
If the package or its dependencies are missing, the API still starts; analysis endpoints answer 503.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from types import ModuleType

log = logging.getLogger("uvicorn.error")
_REPO_ROOT = Path(__file__).resolve().parents[2]

_engine: ModuleType | None = None
_error: str | None = None


def _import_engine() -> ModuleType:
    try:
        import retrofit_engine
    except ModuleNotFoundError as exc:
        if exc.name != "retrofit_engine" or not (_REPO_ROOT / "retrofit_engine").is_dir():
            raise
        sys.path.insert(0, str(_REPO_ROOT))
        import retrofit_engine
    return retrofit_engine


def load() -> ModuleType | None:
    """Import retrofit_engine once; None (with a logged reason) when unavailable."""
    global _engine, _error
    if _engine is not None or _error is not None:
        return _engine
    try:
        _engine = _import_engine()
        info = _engine.model_info()
        log.info("Model engine: loaded (model=%s)", info.get("model_version"))
    except Exception as exc:  # noqa: BLE001 - any import/model-load failure must not stop the API
        _error = f"{type(exc).__name__}: {exc}"
        log.warning("Model engine: unavailable — %s", _error)
    return _engine


def require() -> ModuleType:
    engine = load()
    if engine is None:
        raise EngineUnavailableError(_error or "model engine not loaded")
    return engine


def unavailable_reason() -> str | None:
    load()
    return _error


class EngineUnavailableError(RuntimeError):
    pass
