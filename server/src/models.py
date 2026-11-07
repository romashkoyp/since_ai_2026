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


class AssetStatus(BaseModel):
    asset_id: str
    site: str
    tier: str
    status: str
    open_alerts: int


class HealthResponse(BaseModel):
    status: str
    service: str
