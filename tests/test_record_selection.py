#!/usr/bin/env python3
"""Tests for the pure record-selection helpers (no Home Assistant needed)::

    python3 tests/test_record_selection.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "whoop"
    / "record_selection.py"
)
_spec = importlib.util.spec_from_file_location("record_selection", PATH)
rs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rs)

CYCLE_TODAY = {"id": 2, "start": "2026-11-08T06:30:00.000Z", "step_count": 4120}
CYCLE_YDAY = {
    "id": 1,
    "start": "2026-11-07T06:40:00.000Z",
    "end": "2026-11-08T06:30:00.000Z",
    "step_count": 9876,
    "score": {"strain": 9.1},
}


def _sleep(id_, start, nap, light=0, sws=0, rem=0):
    return {
        "id": id_,
        "start": start,
        "nap": nap,
        "score": {
            "stage_summary": {
                "total_light_sleep_time_milli": light,
                "total_slow_wave_sleep_time_milli": sws,
                "total_rem_sleep_time_milli": rem,
            },
            "sleep_needed": {
                "baseline_milli": 27_000_000,
                "need_from_sleep_debt_milli": 3_000_000,
                "need_from_recent_strain_milli": 600_000,
                "need_from_recent_nap_milli": -900_000,
            },
        },
    }


def test_split_cycles() -> None:
    out = rs.split_cycles({"records": [CYCLE_TODAY, CYCLE_YDAY]})
    assert out["latest_cycle"]["step_count"] == 4120
    assert out["previous_cycle"]["step_count"] == 9876
    one = rs.split_cycles({"records": [CYCLE_TODAY]})
    assert one["previous_cycle"] is None
    assert rs.split_cycles(None) == {"latest_cycle": None, "previous_cycle": None}


def test_nap_does_not_replace_night_sleep() -> None:
    nap = _sleep("n1", "2026-11-08T13:00:00.000Z", True, light=1_200_000)
    night = _sleep("s1", "2026-11-07T22:30:00.000Z", False, 10, 20, 30)
    old_nap = _sleep("n0", "2026-11-07T13:00:00.000Z", True, light=600_000)
    out = rs.split_sleeps({"records": [nap, night, old_nap]}, CYCLE_TODAY)
    assert out["latest_sleep"]["id"] == "s1"
    assert out["latest_nap"]["id"] == "n1"
    assert [n["id"] for n in out["naps_today"]] == ["n1"]


def test_only_naps_falls_back_to_newest() -> None:
    nap = _sleep("n1", "2026-11-08T13:00:00.000Z", True)
    out = rs.split_sleeps({"records": [nap]}, CYCLE_TODAY)
    assert out["latest_sleep"]["id"] == "n1"


def test_workouts_today() -> None:
    w_today = {"id": "w2", "start": "2026-11-08T07:00:00+00:00", "score": {}}
    w_today2 = {"id": "w3", "start": "2026-11-08T07:25:00.000Z", "score": {}}
    w_yday = {"id": "w1", "start": "2026-11-07T07:00:00.000Z", "score": {}}
    out = rs.split_workouts({"records": [w_today2, w_today, w_yday]}, CYCLE_TODAY)
    assert out["latest_workout"]["id"] == "w3"
    assert [w["id"] for w in out["workouts_today"]] == ["w3", "w2"]
    assert rs.split_workouts({"records": [w_yday]}, None)["workouts_today"] == []


def test_sleep_maths() -> None:
    night = _sleep("s1", "2026-11-07T22:30:00.000Z", False, 100, 200, 300)
    assert rs.sleep_asleep_milli(night) == 600
    assert rs.sleep_need_total_milli(night) == 29_700_000
    assert rs.sleep_asleep_milli({"score": None}) is None
    assert rs.sleep_need_total_milli(None) is None


def test_workout_summary_and_zone_sum() -> None:
    w = {
        "sport_name": "running",
        "start": "s",
        "end": "e",
        "score": {
            "strain": 8.2,
            "average_heart_rate": 140,
            "max_heart_rate": 160,
            "kilojoule": 1000,
            "zone_durations": {"zone_two_milli": 600_000, "zone_three_milli": 90_000},
        },
    }
    s = rs.workout_summary(w)
    assert s["kcal"] == 239 and s["zone_2_min"] == 10.0 and s["zone_3_min"] == 1.5
    assert "zone_5_min" not in s
    path = ("score", "zone_durations", "zone_two_milli")
    assert rs.sum_milli([w, w, {"score": None}], path) == 1_200_000


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
    print(f"{len(tests)} record-selection tests passed")
