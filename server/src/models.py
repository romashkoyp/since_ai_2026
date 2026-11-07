"""Pydantic models aligned with shared/contracts.schema.json AlertPrediction."""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, computed_field

from .severity import Severity, categorize_alert


class PumpSeverity(str, Enum):
    """Per-pump triage level (Fleet screen colour), from the urgency of its open alerts.

    Not the same as `Severity` (per-alert confidence band from severity.py, part of the shared contract).
    """

    ACT_NOW = "act_now"
    ATTENTION = "attention"
    SENSOR = "sensor"
    OK = "ok"


class EventClass(str, Enum):
    MACHINE = "MACHINE"
    SENSOR = "SENSOR"


class FaultType(str, Enum):
    BEARING_WEAR = "BEARING_WEAR"
    SUCTION_STRAINER_CLOGGING = "SUCTION_STRAINER_CLOGGING"
    CAVITATION = "CAVITATION"
    DISCHARGE_RESTRICTION = "DISCHARGE_RESTRICTION"
    MISALIGNMENT = "MISALIGNMENT"
    IMBALANCE = "IMBALANCE"
    IMPELLER_WEAR = "IMPELLER_WEAR"
    AIR_ENTRAINMENT = "AIR_ENTRAINMENT"
    SENSOR_DRIFT = "SENSOR_DRIFT"
    SENSOR_STUCK = "SENSOR_STUCK"
    SENSOR_CALIBRATION_SHIFT = "SENSOR_CALIBRATION_SHIFT"
    SENSOR_NOISE_SPIKES = "SENSOR_NOISE_SPIKES"
    COMMUNICATION_LOSS = "COMMUNICATION_LOSS"
    UNKNOWN = "UNKNOWN"


class AlertPrediction(BaseModel):
    asset_id: str
    alert_time_utc: str
    event_class: EventClass
    fault_type: FaultType
    confidence: float = Field(ge=0, le=1)
    evidence: Optional[str] = None
    recommended_action: Optional[str] = None
    true_fault_type: Optional[str] = None
    correct: Optional[bool] = None

    @computed_field
    @property
    def severity(self) -> Severity:
        """Derived API/UI band; never changes the detector's raw alert fields."""
        return categorize_alert(self.event_class, self.fault_type, self.confidence)


class StoredAlert(AlertPrediction):
    """An alert as stored with its analysis run. API alert lists still serialise as AlertPrediction."""

    alert_id: str
    decided_by: Optional[str] = None
    rule_fault_type: Optional[str] = None
    ml_fault_type: Optional[str] = None
    ml_confidence: Optional[float] = None


class AssetStatus(BaseModel):
    asset_id: str
    site: str
    system: str
    tier: str
    status: str
    mode: str
    load_pct: float
    open_alerts: int
    fault_summary: Optional[str] = None
    rul_hours: Optional[float] = None
    severity: Optional[PumpSeverity] = None
    last_data_utc: Optional[str] = None


class FleetSummary(BaseModel):
    vessel: str
    watch: str
    critical: int
    actionable: int
    sensor_faults: int
    availability_pct: float
    healthy: int
    total: int
    nuisance_suppressed_pct: Optional[float] = None
    run_id: Optional[str] = None
    model_version: Optional[str] = None
    data_end_utc: Optional[str] = None


class TrendPoint(BaseModel):
    t: str
    value: float


class TrendSeries(BaseModel):
    name: str
    unit: str
    points: list[TrendPoint]
    threshold: Optional[float] = None


class EvidenceRow(BaseModel):
    channel: str
    sigma: float
    note: str


class CockpitResponse(BaseModel):
    asset_id: str
    title: str
    diagnosis: str
    event_class: EventClass
    confidence: float
    severity: Optional[Severity] = None
    safe_window: str
    evidence: list[EvidenceRow]
    sop: list[str]
    trends: list[TrendSeries]
    sandbox_default_speed_pct: float
    npsh_at_100: float
    npsh_at_88: float
    risk_at_100: float
    risk_at_88: float
    energy_delta_eur_day: float
    cooling_margin_pct: float
    fault_type: Optional[FaultType] = None
    rated_rpm: Optional[float] = None
    cooling_safe_flow_m3h: Optional[float] = None
    sandbox_note: Optional[str] = None


class ScorecardResponse(BaseModel):
    composite_score: float
    event_f1: float
    precision: float
    fault_type_recall: float
    timeliness: float
    false_alarms: int
    t0_vs_t1: list[dict]
    hardware_bom: list[dict]
    economics: list[dict]


class HealthResponse(BaseModel):
    status: str
    service: str
    database: Optional[str] = None
    model: Optional[str] = None


class ModelInfo(BaseModel):
    available: bool
    model_version: Optional[str] = None
    physics_version: Optional[str] = None
    classes: list[str] = []
    calibrated: Optional[bool] = None
    reason: Optional[str] = None
    required_datasheet_columns: list[str] = []
    min_history_hours: Optional[float] = None
    max_upload_mb: float


class FaultGuideEntry(BaseModel):
    """What a fault means and what to do about it (from fault_actions.json)."""

    fault_type: str
    event_class: EventClass
    plain_name: str
    what_it_means: str
    what_to_do: list[str]
    urgency_level: Literal["act_now", "within_a_day", "next_planned_stop", "check_sensor"]
    urgency_text: str
    not_to_confuse_with: Optional[str] = None


class AnalysisRunSummary(BaseModel):
    run_id: str
    created_utc: str
    source: Literal["upload", "seed"]
    label: Optional[str] = None
    model_version: str
    physics_version: Optional[str] = None
    use_ml: bool
    pumps: int
    alerts: int
    ml_overrides: int
    by_fault_type: dict[str, int]
    data_start_utc: Optional[str] = None
    data_end_utc: Optional[str] = None
    processing_seconds: float
    scored: bool = Field(default=False, description="True when ground-truth events were supplied")
    notes: list[str] = []


class AnalysisJob(BaseModel):
    """A queued / running / finished model run started by an upload (poll until completed or failed)."""

    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    created_utc: str
    started_utc: Optional[str] = None
    finished_utc: Optional[str] = None
    label: Optional[str] = None
    run: Optional[AnalysisRunSummary] = Field(default=None, description="Set when completed")
    error: Optional[str] = Field(default=None, description="Set when failed: message for the user")
    error_status: Optional[int] = Field(default=None, description="HTTP-style code of the failure (422, 500, 503)")


class AnalysisRecord(BaseModel):
    """Everything one model run produced; immutable once stored."""

    summary: AnalysisRunSummary
    alerts: list[StoredAlert]
    assets: list[AssetStatus]
    cockpits: list[CockpitResponse]
