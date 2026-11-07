"""Runtime settings, read once from environment variables (see repo .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CORS = "http://localhost:5173,http://localhost:3000,http://localhost,http://79.76.32.240"


def _float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    return float(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    cors_origins: list[str] = field(default_factory=list)
    mongodb_uri: str = ""
    mongodb_db: str = "since_ai"
    # Largest accepted upload per file. Raw 1 Hz telemetry is big; 1-minute summaries are ~1 MB per pump-week.
    max_upload_mb: float = 200.0
    # Optional: only alerts raised within this many hours before the pump's last reading set its status.
    # None (default) = the whole analysed period, so the status always agrees with the "Detected issues" card.
    active_alert_hours: float | None = None
    # Mitigation sandbox assumptions (documented in the cockpit's sandbox_note).
    energy_price_eur_kwh: float = 0.15
    # Share of today's flow the cooled system needs (1 - thermal slack); sets the sandbox cooling margin.
    cooling_min_flow_fraction: float = 0.8
    seed_run_path: Path = SERVER_DIR / "seed" / "demo_run.json"

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1_000_000)  # decimal MB, the same unit the dashboard shows


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    cors = os.getenv("CORS_ORIGINS", DEFAULT_CORS)
    seed = os.getenv("SEED_RUN_PATH", "").strip()
    return Settings(
        cors_origins=[o.strip() for o in cors.split(",") if o.strip()],
        mongodb_uri=os.getenv("MONGODB_URI", "").strip(),
        mongodb_db=os.getenv("MONGODB_DB", "since_ai").strip() or "since_ai",
        max_upload_mb=_float("MAX_UPLOAD_MB", 200.0),
        active_alert_hours=_float("ACTIVE_ALERT_HOURS", 0.0) or None,
        energy_price_eur_kwh=_float("ENERGY_PRICE_EUR_KWH", 0.15),
        cooling_min_flow_fraction=_float("COOLING_MIN_FLOW_FRACTION", 0.8),
        seed_run_path=Path(seed) if seed else SERVER_DIR / "seed" / "demo_run.json",
    )
