from __future__ import annotations

import io
import os

import numpy as np
import pandas as pd
import pytest

os.environ["MONGODB_URI"] = ""  # tests always use the in-memory store

from fastapi.testclient import TestClient  # noqa: E402

from src.main import app  # noqa: E402

CHANNELS = {  # channel: (healthy mean, noise std)
    "motor_speed_rpm": (1480.0, 2.0),
    "motor_current_a": (60.0, 0.5),
    "motor_power_kw": (30.0, 0.3),
    "suction_pressure_kpa": (60.0, 0.5),
    "discharge_pressure_kpa": (380.0, 1.5),
    "flow_m3_h": (300.0, 2.0),
    "fluid_temp_c": (30.0, 0.1),
    "bearing_temp_c": (45.0, 0.2),
    "vibration_rms_mm_s": (1.5, 0.03),
}


@pytest.fixture()
def client():
    with TestClient(app) as c:  # lifespan runs: fresh memory store + bundled seed run
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def datasheet_csv() -> bytes:
    sheet = pd.DataFrame([{
        "asset_id": "TEST-01", "control": "VFD_PRESSURE", "motor_rated_rpm": 1480, "pump_rated_flow_m3_h": 320,
        "pump_rated_head_m": 33, "pump_shutoff_head_m": 42, "npsh3_at_bep_m": 4.0, "fluid": "Cooling-tower water",
        "motor_rated_kw": 45, "motor_rated_current_a": 80, "site": "Test plant", "system": "Test loop",
    }])
    return sheet.to_csv(index=False).encode()


def minute_summaries(hours: float, start: str, suction_drop_last_h: float = 0.0, seed: int = 0) -> pd.DataFrame:
    """1-minute summary table for one steady pump; optionally a suction-pressure collapse at the end."""
    rng = np.random.default_rng(seed)
    n = int(hours * 60)
    t = pd.date_range(start, periods=n, freq="1min", tz="UTC")
    df = pd.DataFrame({"asset_id": "TEST-01", "window_start_utc": t.strftime("%Y-%m-%dT%H:%M:%SZ")})
    for ch, (mu, sd) in CHANNELS.items():
        x = mu + rng.normal(0, sd, n)
        if ch == "suction_pressure_kpa" and suction_drop_last_h:
            k = int(suction_drop_last_h * 60)
            x[-k:] -= np.linspace(0, 30, k)
        df[f"{ch}__mean"] = x
        df[f"{ch}__std"] = sd
        df[f"{ch}__min"] = x - 2 * sd
        df[f"{ch}__max"] = x + 2 * sd
        df[f"{ch}__count"] = 60
    df["operating_mode"] = "RUNNING"
    df["running_fraction"] = 1.0
    df["quality_any"] = 0
    df["rows"] = 60
    return df


def to_csv(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()
