import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from companion.simbrief import OfpError, normalize, to_wire

FIXTURE = Path(__file__).parent / "fixtures" / "ofp_krdu_katl.json"


@pytest.fixture
def raw() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(FIXTURE.read_text())
    return loaded


def test_normalizes_route_and_airports(raw: dict[str, Any]) -> None:
    ofp = normalize(raw)
    assert (ofp.origin, ofp.origin_rwy, ofp.dest, ofp.dest_rwy) == ("KRDU", "23L", "KATL", "27R")
    assert ofp.altn == "KBHM"
    assert (ofp.sid, ofp.star) == ("LILLS4", "OZZZI1")
    assert ofp.dest_lat == pytest.approx(33.636719)
    assert ofp.dest_lon == pytest.approx(-84.428067)


def test_normalizes_numbers(raw: dict[str, Any]) -> None:
    ofp = normalize(raw)
    assert ofp.cost_index == 15
    assert ofp.initial_fl == 320
    assert ofp.units == "kg"
    assert (ofp.block_fuel, ofp.trip_fuel, ofp.final_reserve, ofp.altn_fuel) == (
        5400,
        2650,
        1050,
        1100,
    )
    assert (ofp.zfw, ofp.tow, ofp.ldw) == (55300, 60500, 57850)
    assert ofp.airac == "2610"
    assert ofp.generated_at == datetime.fromtimestamp(1760820000, UTC)


def test_step_climbs_skip_the_origin_entry(raw: dict[str, Any]) -> None:
    assert normalize(raw).step_climbs == (("SPA", 360),)


def test_fixes_map_dsc_to_des(raw: dict[str, Any]) -> None:
    fixes = normalize(raw).fixes
    assert [f.stage for f in fixes] == ["CLB", "CLB", "CRZ", "CRZ", "DES", "DES"]
    assert fixes[0].is_sid_star is True
    assert fixes[-1].planned_fob == 2550
    assert fixes[1].alt_ft == 32000


def test_blank_optional_fields_become_none(raw: dict[str, Any]) -> None:
    raw["general"]["sid_ident"] = ""
    raw["origin"]["plan_rwy"] = ""
    raw["alternate"] = []
    ofp = normalize(raw)
    assert (ofp.sid, ofp.origin_rwy, ofp.altn) == (None, None, None)


def test_accepts_lbs_and_iso_time(raw: dict[str, Any]) -> None:
    raw["params"]["units"] = "lbs"
    raw["params"]["time_generated"] = "2026-10-03T21:18:38Z"
    ofp = normalize(raw)
    assert ofp.units == "lb"
    assert ofp.generated_at == datetime(2026, 10, 3, 21, 18, 38, tzinfo=UTC)


def test_accepts_integer_epoch_time(raw: dict[str, Any]) -> None:
    raw["params"]["time_generated"] = 1760820000
    assert normalize(raw).generated_at == datetime.fromtimestamp(1760820000, UTC)


def test_accepts_navlog_wrapped_in_fix_key(raw: dict[str, Any]) -> None:
    raw["navlog"] = {"fix": raw["navlog"]}
    assert len(normalize(raw).fixes) == 6


def test_missing_field_names_the_path(raw: dict[str, Any]) -> None:
    broken = copy.deepcopy(raw)
    del broken["destination"]["icao_code"]
    with pytest.raises(OfpError, match="destination.icao_code"):
        normalize(broken)


def test_unknown_units_rejected(raw: dict[str, Any]) -> None:
    raw["params"]["units"] = "stone"
    with pytest.raises(OfpError, match="units"):
        normalize(raw)


def test_to_wire_is_json_safe(raw: dict[str, Any]) -> None:
    wire = to_wire(normalize(raw))
    assert json.loads(json.dumps(wire)) == wire
    assert wire["generated_at"] == "2025-10-18T20:40:00+00:00"
    assert wire["step_climbs"] == [["SPA", 360]]
    assert wire["fixes"][0]["ident"] == "LILLS"
