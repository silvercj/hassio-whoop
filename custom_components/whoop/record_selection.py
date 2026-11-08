"""Pure helpers that pick and summarise WHOOP records.

No Home Assistant imports, so they can be tested without HA installed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

Record = Dict[str, Any]


def _records(response: Optional[Dict[str, Any]]) -> List[Record]:
    if isinstance(response, dict) and isinstance(response.get("records"), list):
        return [r for r in response["records"] if isinstance(r, dict)]
    return []


def _parse_time(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _starts_at_or_after(record: Record, boundary: Optional[datetime]) -> bool:
    start = _parse_time(record.get("start"))
    return boundary is not None and start is not None and start >= boundary


def split_cycles(response: Optional[Dict[str, Any]]) -> Dict[str, Optional[Record]]:
    """Latest (current) cycle and the one before it (yesterday, finished)."""
    records = _records(response)
    return {
        "latest_cycle": records[0] if records else None,
        "previous_cycle": records[1] if len(records) > 1 else None,
    }


def split_sleeps(
    response: Optional[Dict[str, Any]], current_cycle: Optional[Record]
) -> Dict[str, Any]:
    """Separate the main sleep from naps.

    Before this, a nap became "latest_sleep" and replaced the night's sleep
    figures until the next night. The main sleep is now the newest record that
    is not a nap; if none of the fetched records is a main sleep, fall back to
    the newest record (the old behaviour).
    """
    records = _records(response)
    main = next((r for r in records if not r.get("nap")), None)
    if main is None and records:
        main = records[0]
    naps = [r for r in records if r.get("nap")]
    boundary = _parse_time((current_cycle or {}).get("start"))
    return {
        "latest_sleep": main,
        "latest_nap": naps[0] if naps else None,
        "naps_today": [n for n in naps if _starts_at_or_after(n, boundary)],
    }


def split_workouts(
    response: Optional[Dict[str, Any]], current_cycle: Optional[Record]
) -> Dict[str, Any]:
    """Latest workout plus every workout in the current cycle (today)."""
    records = _records(response)
    boundary = _parse_time((current_cycle or {}).get("start"))
    return {
        "latest_workout": records[0] if records else None,
        "workouts_today": [w for w in records if _starts_at_or_after(w, boundary)],
    }


def sleep_asleep_milli(sleep: Optional[Record]) -> Optional[int]:
    """Time actually asleep: light + slow wave + REM."""
    stages = ((sleep or {}).get("score") or {}).get("stage_summary")
    if not isinstance(stages, dict):
        return None
    keys = (
        "total_light_sleep_time_milli",
        "total_slow_wave_sleep_time_milli",
        "total_rem_sleep_time_milli",
    )
    values = [stages.get(k) for k in keys]
    if any(v is None for v in values):
        return None
    return int(sum(values))


def sleep_need_total_milli(sleep: Optional[Record]) -> Optional[int]:
    """Total sleep need as the WHOOP app shows it.

    baseline + debt + recent strain + recent nap (WHOOP reports the nap part
    as a negative number, as it reduces the need).
    """
    need = ((sleep or {}).get("score") or {}).get("sleep_needed")
    if not isinstance(need, dict) or need.get("baseline_milli") is None:
        return None
    keys = (
        "baseline_milli",
        "need_from_sleep_debt_milli",
        "need_from_recent_strain_milli",
        "need_from_recent_nap_milli",
    )
    return int(sum(need.get(k) or 0 for k in keys))


_ZONES = ("zero", "one", "two", "three", "four", "five")


def workout_summary(workout: Record) -> Dict[str, Any]:
    """Compact, attribute-friendly view of one workout."""
    score = workout.get("score") or {}
    zones = score.get("zone_durations") or {}
    kj = score.get("kilojoule")
    summary: Dict[str, Any] = {
        "sport_name": workout.get("sport_name"),
        "start": workout.get("start"),
        "end": workout.get("end"),
        "strain": score.get("strain"),
        "average_heart_rate": score.get("average_heart_rate"),
        "max_heart_rate": score.get("max_heart_rate"),
        "kilojoule": kj,
        "kcal": round(kj * 0.239006) if isinstance(kj, (int, float)) else None,
        "distance_meter": score.get("distance_meter"),
    }
    for i, name in enumerate(_ZONES):
        milli = zones.get(f"zone_{name}_milli")
        summary[f"zone_{i}_min"] = (
            round(milli / 60000, 1) if isinstance(milli, (int, float)) else None
        )
    return {k: v for k, v in summary.items() if v is not None}


def sum_milli(records: List[Record], path: tuple) -> int:
    """Sum a nested milli value across records, skipping gaps."""
    total = 0
    for record in records:
        value: Any = record
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        if isinstance(value, (int, float)):
            total += value
    return int(total)
