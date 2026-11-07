"""Pydantic models aligned with shared/contracts.schema.json AlertPrediction."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


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


class FleetSummary(BaseModel):
    vessel: str
    watch: str
    critical: int
    actionable: int
    sensor_faults: int
    availability_pct: float
    healthy: int
    total: int
    nuisance_suppressed_pct: float


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
