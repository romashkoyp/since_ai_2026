"""Plain-language guidance per fault type (copied from joice_physics_rules/dashboard_data/fault_actions.json)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .models import PumpSeverity

_GUIDE_FILE = Path(__file__).resolve().parent / "data" / "fault_actions.json"

# urgency.level in the guide -> dashboard severity
_URGENCY_TO_SEVERITY = {
    "act_now": PumpSeverity.ACT_NOW,
    "within_a_day": PumpSeverity.ATTENTION,
    "next_planned_stop": PumpSeverity.ATTENTION,
    "check_sensor": PumpSeverity.SENSOR,
}
SEVERITY_RANK = {PumpSeverity.ACT_NOW: 0, PumpSeverity.ATTENTION: 1, PumpSeverity.SENSOR: 2, PumpSeverity.OK: 3}
# within the same severity, a more urgent guide level wins
_URGENCY_RANK = {"act_now": 0, "within_a_day": 1, "next_planned_stop": 2, "check_sensor": 3}


@dataclass(frozen=True)
class FaultGuide:
    fault_type: str
    event_class: str
    plain_name: str
    what_it_means: str
    what_to_do: tuple[str, ...]
    urgency_level: str
    urgency_text: str
    not_to_confuse_with: str | None = None

    @property
    def severity(self) -> PumpSeverity:
        return _URGENCY_TO_SEVERITY.get(self.urgency_level, PumpSeverity.ATTENTION)

    @property
    def rank(self) -> tuple[int, int]:
        return SEVERITY_RANK[self.severity], _URGENCY_RANK.get(self.urgency_level, 9)


@lru_cache(maxsize=1)
def _load() -> dict[str, FaultGuide]:
    raw = json.loads(_GUIDE_FILE.read_text(encoding="utf-8"))
    out: dict[str, FaultGuide] = {}
    for fault_type, g in raw.items():
        if fault_type.startswith("_"):
            continue
        urgency = g.get("urgency", {})
        out[fault_type] = FaultGuide(
            fault_type=fault_type,
            event_class=g.get("class", "MACHINE"),
            plain_name=g["plain_name"],
            what_it_means=g.get("what_it_means", ""),
            what_to_do=tuple(g.get("what_to_do", [])),
            urgency_level=urgency.get("level", "within_a_day"),
            urgency_text=urgency.get("text", ""),
            not_to_confuse_with=g.get("not_to_confuse_with") or None,
        )
    return out


def all_guides() -> list[FaultGuide]:
    return list(_load().values())


def guide_for(fault_type: str) -> FaultGuide:
    guides = _load()
    return guides.get(fault_type, guides["UNKNOWN"])
