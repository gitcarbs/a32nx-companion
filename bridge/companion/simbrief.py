import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import aiohttp

from companion.config import SimbriefConfig

Stage = Literal["CLB", "CRZ", "DES"]
_STAGES: dict[str, Stage] = {"CLB": "CLB", "CRZ": "CRZ", "DSC": "DES"}
_UNITS: dict[str, Literal["kg", "lb"]] = {"kgs": "kg", "lbs": "lb"}
_STEP = re.compile(r"^([A-Z0-9]+)/(\d{3,4})$")


class OfpError(Exception):
    pass


@dataclass(frozen=True)
class Fix:
    ident: str
    lat: float
    lon: float
    alt_ft: int
    stage: Stage
    planned_fob: float
    is_sid_star: bool


@dataclass(frozen=True)
class Ofp:
    origin: str
    origin_rwy: str | None
    dest: str
    dest_rwy: str | None
    dest_lat: float
    dest_lon: float
    altn: str | None
    route: str
    sid: str | None
    star: str | None
    cost_index: int
    initial_fl: int
    step_climbs: tuple[tuple[str, int], ...]
    units: Literal["kg", "lb"]
    block_fuel: float
    trip_fuel: float
    final_reserve: float
    altn_fuel: float
    zfw: float
    tow: float
    ldw: float
    fixes: tuple[Fix, ...]
    airac: str | None
    generated_at: datetime


def normalize(raw: dict[str, Any]) -> Ofp:
    """The only place that knows SimBrief's json=v2 field names."""
    try:
        return _normalize(raw)
    except _Missing as exc:
        raise OfpError(f"OFP is missing {exc.path}") from exc
    except (TypeError, ValueError) as exc:
        raise OfpError(f"OFP has an unreadable value: {exc}") from exc


def to_wire(ofp: Ofp) -> dict[str, Any]:
    wire = asdict(ofp)
    wire["generated_at"] = ofp.generated_at.isoformat()
    wire["step_climbs"] = [list(step) for step in ofp.step_climbs]
    wire["fixes"] = list(wire["fixes"])
    return wire


class _Missing(Exception):
    def __init__(self, path: str) -> None:
        super().__init__(path)
        self.path = path


def _get(raw: dict[str, Any], path: str) -> Any:
    node: Any = raw
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise _Missing(path)
        node = node[part]
    return node


def _opt(raw: dict[str, Any], path: str) -> str | None:
    try:
        value = _get(raw, path)
    except _Missing:
        return None
    return str(value) if value else None


def _normalize(raw: dict[str, Any]) -> Ofp:
    origin = _get(raw, "origin.icao_code")
    units = _UNITS.get(_get(raw, "params.units"))
    if units is None:
        raise OfpError(f"unknown OFP units {_get(raw, 'params.units')!r}")
    return Ofp(
        origin=origin,
        origin_rwy=_opt(raw, "origin.plan_rwy"),
        dest=_get(raw, "destination.icao_code"),
        dest_rwy=_opt(raw, "destination.plan_rwy"),
        dest_lat=float(_get(raw, "destination.pos_lat")),
        dest_lon=float(_get(raw, "destination.pos_long")),
        altn=_alternate(raw.get("alternate")),
        route=_get(raw, "general.route"),
        sid=_opt(raw, "general.sid_ident"),
        star=_opt(raw, "general.star_ident"),
        cost_index=int(_get(raw, "general.costindex")),
        initial_fl=int(_get(raw, "general.initial_altitude")) // 100,
        step_climbs=_step_climbs(_opt(raw, "general.stepclimb_string") or "", origin),
        units=units,
        block_fuel=float(_get(raw, "fuel.plan_ramp")),
        trip_fuel=float(_get(raw, "fuel.enroute_burn")),
        final_reserve=float(_get(raw, "fuel.reserve")),
        altn_fuel=float(_get(raw, "fuel.alternate_burn")),
        zfw=float(_get(raw, "weights.est_zfw")),
        tow=float(_get(raw, "weights.est_tow")),
        ldw=float(_get(raw, "weights.est_ldw")),
        fixes=tuple(_fix(f) for f in _navlog(_get(raw, "navlog"))),
        airac=_opt(raw, "params.airac"),
        generated_at=_timestamp(_get(raw, "params.time_generated")),
    )


def _alternate(value: Any) -> str | None:
    # v2 sends a list when there are alternates; older payloads send one object.
    if isinstance(value, list):
        value = value[0] if value else None
    if not isinstance(value, dict):
        return None
    return str(value.get("icao_code") or "") or None


def _navlog(value: Any) -> list[dict[str, Any]]:
    fixes = value.get("fix", []) if isinstance(value, dict) else value
    if not isinstance(fixes, list):
        raise OfpError("OFP navlog is not a list of fixes")
    return fixes


def _fix(raw: dict[str, Any]) -> Fix:
    stage = _STAGES.get(_get(raw, "stage"))
    if stage is None:
        raise OfpError(f"unknown navlog stage {raw.get('stage')!r}")
    return Fix(
        ident=_get(raw, "ident"),
        lat=float(_get(raw, "pos_lat")),
        lon=float(_get(raw, "pos_long")),
        alt_ft=int(_get(raw, "altitude_feet")),
        stage=stage,
        planned_fob=float(_get(raw, "fuel_plan_onboard")),
        is_sid_star=_get(raw, "is_sid_star") == "1",
    )


def _step_climbs(text: str, origin: str) -> tuple[tuple[str, int], ...]:
    # The first token repeats the origin with the initial level; only later tokens are steps.
    steps = (_STEP.match(token) for token in text.split())
    return tuple((m[1], int(m[2])) for m in steps if m and m[1] != origin)


def _timestamp(value: Any) -> datetime:
    value = str(value)
    if value.isdigit():
        return datetime.fromtimestamp(int(value), UTC)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


SIMBRIEF_URL = "https://www.simbrief.com/api/xml.fetcher.php"
_TIMEOUT = aiohttp.ClientTimeout(total=15)
log = logging.getLogger(__name__)


class SimbriefError(Exception):
    pass


async def fetch_raw(
    session: aiohttp.ClientSession, config: SimbriefConfig, url: str = SIMBRIEF_URL
) -> dict[str, Any]:
    identity = {"username": config.username} if config.username else {"userid": config.userid or ""}
    async with session.get(url, params={**identity, "json": "v2"}) as response:
        try:
            body = await response.json(content_type=None)
        except json.JSONDecodeError as exc:
            raise SimbriefError(f"SimBrief returned non-JSON (HTTP {response.status})") from exc
    status = body.get("fetch", {}).get("status", "") if isinstance(body, dict) else ""
    if response.status != 200 or status != "Success":
        raise SimbriefError(
            f"SimBrief fetch failed (HTTP {response.status}): {status or 'no status'}"
        )
    if not isinstance(body, dict):
        raise SimbriefError("SimBrief returned a JSON value that is not an object")
    return cast(dict[str, Any], body)


def default_cache_path() -> Path:
    return Path.home() / ".a32nx-companion" / "ofp.json"


class SimbriefLoader:
    def __init__(self, config: SimbriefConfig, cache_path: Path, url: str = SIMBRIEF_URL) -> None:
        self._config = config
        self._cache_path = cache_path
        self._url = url

    def cached(self) -> Ofp | None:
        try:
            return normalize(json.loads(self._cache_path.read_text()))
        except FileNotFoundError:
            return None
        except (OSError, ValueError, OfpError) as exc:
            log.warning("ignoring unreadable OFP cache %s: %s", self._cache_path, exc)
            return None

    async def refresh(self) -> Ofp:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            raw = await fetch_raw(session, self._config, self._url)
        ofp = normalize(raw)
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(json.dumps(raw))
        return ofp
