"""FastAPI dependencies (overridable in tests via app.dependency_overrides)."""

from __future__ import annotations

from fastapi import Request

from .db import RunStore
from .jobs import JobRunner
from .settings import Settings, get_settings


def get_store(request: Request) -> RunStore:
    return request.app.state.store


def get_jobs(request: Request) -> JobRunner:
    return request.app.state.jobs


def settings_dep() -> Settings:
    return get_settings()
