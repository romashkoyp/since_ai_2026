from __future__ import annotations

import pytest

from src.deps import settings_dep
from src.main import app
from src.models import AlertPrediction
from src.settings import Settings

from .conftest import minute_summaries, to_csv

CONTRACT_FIELDS = set(AlertPrediction.model_fields) | set(AlertPrediction.model_computed_fields)


# ------------------------------------------------------------------ dashboard reads (bundled seed run)
def test_health_reports_model(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["database"] == "disabled"
    assert body["model"] not in (None, "unavailable")


def test_fleet_assets_and_cockpits_are_consistent(client):
    summary = client.get("/api/fleet/summary").json()
    assets = client.get("/api/assets").json()
    assert summary["total"] == len(assets) > 0
    assert summary["run_id"] == client.get("/api/analyses/latest").json()["run_id"]
    for a in assets:
        cockpit = client.get(f"/api/cockpit/{a['asset_id']}")
        assert cockpit.status_code == 200
        body = cockpit.json()
        if a["severity"] == "ok":
            assert body["diagnosis"] == "No active fault"
        else:
            assert body["fault_type"] and a["open_alerts"] > 0


def test_pump_status_agrees_with_its_alerts(client):
    """A pump tile says 'ok' only when the pump has no alerts at all in the run (same data as Detected issues)."""
    alerts = client.get("/api/alerts").json()
    for a in client.get("/api/assets").json():
        n = sum(1 for x in alerts if x["asset_id"] == a["asset_id"])
        assert (a["severity"] == "ok") == (n == 0), (a["asset_id"], a["severity"], n)
        assert a["open_alerts"] == n


def test_alerts_follow_the_shared_contract(client):
    alerts = client.get("/api/alerts").json()
    assert alerts
    for a in alerts:
        assert set(a) <= CONTRACT_FIELDS
        assert 0 <= a["confidence"] <= 1


def test_alert_filters(client):
    sensor = client.get("/api/alerts", params={"event_class": "SENSOR"}).json()
    assert sensor and all(a["event_class"] == "SENSOR" for a in sensor)
    assert client.get("/api/alerts", params={"event_class": "nope"}).status_code == 422
    assert client.get("/api/alerts/NO-SUCH-PUMP").status_code == 404
    assert client.get("/api/cockpit/NO-SUCH-PUMP").status_code == 404


def test_alert_severity_bands_and_filter(client):
    alerts = client.get("/api/alerts").json()
    assert all(a["severity"] in {"SEVERE", "MODERATE", "MINIMAL", "LOW_CONFIDENCE"} for a in alerts)
    severe = client.get("/api/alerts", params={"severity": "SEVERE"}).json()
    assert severe and all(a["severity"] == "SEVERE" for a in severe)
    both = client.get("/api/alerts", params=[("severity", "SEVERE"), ("severity", "MODERATE")]).json()
    assert len(both) == sum(a["severity"] in {"SEVERE", "MODERATE"} for a in alerts)
    assert client.get("/api/alerts", params={"severity": "HUGE"}).status_code == 422
    pump = alerts[0]["asset_id"]
    assert client.get(f"/api/alerts/{pump}", params={"severity": "LOW_CONFIDENCE"}).status_code in (200, 404)


def test_alerts_csv_uses_template_columns(client):
    run_id = client.get("/api/analyses/latest").json()["run_id"]
    r = client.get(f"/api/analyses/{run_id}/alerts.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.text.splitlines()[0] == "asset_id,alert_time_utc,event_class,fault_type,confidence,evidence,recommended_action"
    assert client.get("/api/analyses/unknown/alerts.csv").status_code == 404


def test_fault_guide_covers_every_fault_type(client):
    from src.models import FaultType

    guide = {g["fault_type"]: g for g in client.get("/api/fault-guide").json()}
    assert set(guide) == {f.value for f in FaultType}
    for g in guide.values():
        assert g["plain_name"] and g["what_to_do"], g["fault_type"]
        assert g["urgency_level"] in {"act_now", "within_a_day", "next_planned_stop", "check_sensor"}
    assert guide["CAVITATION"]["urgency_level"] == "act_now"
    assert guide["SENSOR_STUCK"]["event_class"] == "SENSOR"


def test_model_info(client):
    info = client.get("/api/model").json()
    assert info["available"] is True
    assert "asset_id" in info["required_datasheet_columns"]


# ------------------------------------------------------------------ uploads
def _files(datasheet_csv, telemetry, baseline=None):
    files = {"datasheet": ("datasheet.csv", datasheet_csv, "text/csv"),
             "telemetry": ("telemetry.csv", to_csv(telemetry), "text/csv")}
    if baseline is not None:
        files["baseline"] = ("baseline.csv", to_csv(baseline), "text/csv")
    return files


def _wait(client, job_id: str, timeout_s: float = 60) -> dict:
    """poll an upload job until it finishes, like the dashboard does"""
    import time

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        job = client.get(f"/api/analyses/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish in {timeout_s}s")


def test_upload_runs_model_and_becomes_latest(client, datasheet_csv):
    baseline = minute_summaries(30, "2026-01-01T00:00:00Z", seed=1)
    telemetry = minute_summaries(24, "2026-01-02T06:00:00Z", suction_drop_last_h=6, seed=2)
    r = client.post("/api/analyses", files=_files(datasheet_csv, telemetry, baseline), data={"use_ml": "true"})
    assert r.status_code == 202, r.text
    assert r.headers["location"] == f"/api/analyses/jobs/{r.json()['job_id']}"
    job = _wait(client, r.json()["job_id"])
    assert job["status"] == "completed", job
    run = job["run"]
    assert run["source"] == "upload" and run["pumps"] == 1 and run["alerts"] >= 1

    assert client.get("/api/analyses/latest").json()["run_id"] == run["run_id"]
    assets = client.get("/api/assets").json()
    assert [a["asset_id"] for a in assets] == ["TEST-01"]
    assert assets[0]["severity"] != "ok"  # the suction collapse is flagged
    machine = client.get("/api/alerts", params={"event_class": "MACHINE"}).json()
    assert machine and all(a["asset_id"] == "TEST-01" for a in machine)
    assert [r["run_id"] for r in client.get("/api/analyses").json()][0] == run["run_id"]


def test_upload_rejects_bad_datasheet(client):
    telemetry = minute_summaries(2, "2026-01-01T00:00:00Z")
    bad_sheet = b"asset_id,control\nTEST-01,FIXED_SPEED\n"
    r = client.post("/api/analyses", files=_files(bad_sheet, telemetry))
    assert r.status_code == 422
    assert "missing columns" in r.json()["detail"]


def test_upload_rejects_unknown_file_type(client, datasheet_csv):
    files = {"datasheet": ("datasheet.csv", datasheet_csv, "text/csv"),
             "telemetry": ("telemetry.xlsx", b"PK\x03\x04", "application/octet-stream")}
    assert client.post("/api/analyses", files=files).status_code == 415


@pytest.mark.parametrize("max_mb", [0.001])
def test_upload_size_limit(client, datasheet_csv, max_mb):
    app.dependency_overrides[settings_dep] = lambda: Settings(max_upload_mb=max_mb)
    telemetry = minute_summaries(4, "2026-01-01T00:00:00Z")
    r = client.post("/api/analyses", files=_files(datasheet_csv, telemetry))
    assert r.status_code == 413


def test_failure_inside_the_run_is_reported_on_the_job(client, datasheet_csv):
    """columns are fine but the data cannot be analysed -> the job fails with a readable message (no 500 page)"""
    telemetry = minute_summaries(2, "2026-01-01T00:00:00Z").drop(columns=["operating_mode", "running_fraction"])
    r = client.post("/api/analyses", files=_files(datasheet_csv, telemetry))
    assert r.status_code == 202, r.text
    job = _wait(client, r.json()["job_id"])
    assert job["status"] == "failed" and job["error"] and job["error_status"] in (422, 500), job
    assert client.get("/api/analyses/latest").json()["source"] == "seed"   # nothing saved


def test_unknown_job_is_404(client):
    assert client.get("/api/analyses/jobs/nope").status_code == 404
