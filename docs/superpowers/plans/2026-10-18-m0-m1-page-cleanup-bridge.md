# M0 + M1: Page Cleanup and Bridge Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every page step a stable ID (M0), then add a Python bridge that serves the page, fetches the SimBrief OFP and pushes it over a WebSocket so the rail shows the real flight (M1).

**Architecture:** `index.html` stays a single static file and keeps working from `file://`. A new `bridge/` package (aiohttp) serves that file at `/`, holds the current normalized OFP, and speaks the §4 protocol on `/ws`. SimBrief JSON is normalized in exactly one Python function; the page only ever sees the normalized shape.

**Tech Stack:** Python 3.12, uv, aiohttp, pytest + pytest-aiohttp, ruff, mypy. Vanilla JS in `index.html`.

**Spec:** `spec.md` (§3 items 1–5 and the connection pill from item 6, §4 `hello`/`ofp`/`sources`/`ofp_refresh`, §5).

## Global Constraints

- Python 3.12; dependencies managed with `uv` (`uv sync`, `uv run`). Runtime dependency: `aiohttp` only. Dev: `pytest`, `pytest-aiohttp`, `ruff`, `mypy`.
- Everything in this plan runs on macOS. No SimConnect code.
- Page must remain fully usable with no bridge, including when opened from `file://`.
- BeyondATC cards (`batc`) stay exactly as they are.
- Storage key `a32nx-companion.v2`; v1 data is dropped.
- Phase IDs: `plan dark prep clr push taxi tkof clb crz des appr land park`.
- Step IDs are `{phase}.{section}.{step}`; checklist item IDs are `{phase}.cl.{item}`.
- Rules (later milestones) and the page never read raw SimBrief keys; only `simbrief.normalize` does.
- Everything the bridge sends that ends up in `innerHTML` is escaped with `esc()`.
- Comments explain why, never what. No negation-style prose in comments.
- Config file `config.toml` lives at the repo root and is gitignored; `config.example.toml` is committed.

## File Structure

| Path | Responsibility |
|---|---|
| `index.html` | Page: data model with IDs (Task 1), bridge client + OFP rail + pill (Task 6) |
| `config.example.toml` | Example config from spec §2 |
| `.gitignore` | Ignore `config.toml`, `.venv`, caches |
| `bridge/pyproject.toml` | Package + deps + pytest/ruff/mypy config |
| `bridge/companion/__init__.py` | Empty |
| `bridge/companion/config.py` | Load and validate `config.toml` into dataclasses |
| `bridge/companion/simbrief.py` | `Ofp`/`Fix` dataclasses, `normalize`, `to_wire`, `fetch_raw`, cache read/write, `SimbriefLoader` |
| `bridge/companion/server.py` | aiohttp app: `/` serves `index.html`, `/ws` protocol, `Hub` |
| `bridge/companion/__main__.py` | CLI: `run` |
| `bridge/tests/fixtures/ofp_krdu_katl.json` | Hand-built v2-shaped OFP (only the fields we read) |
| `bridge/tests/test_config.py`, `test_simbrief_normalize.py`, `test_simbrief_fetch.py`, `test_server.py` | Tests |

All commands below run from the repo root unless they `cd bridge`.

---

### Task 1: M0 — stable step IDs, v2 storage, profile height in data, content fixes

**Files:**
- Modify: `index.html` (data array `D` lines 145–450, state/storage/progress/render code lines 451–564)

**Interfaces:**
- Produces (used by Task 6 and by M4 cue links):
  - Every flow section object has `k` (section key); every flow step has `id`; every checklist item (except `{line:1}`) has `id`.
  - After the data array, a walk sets `st.key` on every step and checklist item to its full ID and fills `const STEP_IDS=new Set()`.
  - Each rendered step `<label class="step">` and `<div class="cl-item">` carries `data-k="<full id>"` (checkbox input keeps `data-k` too).
  - Each phase object has `y` (profile height); `PROFY` is gone.
  - `state.checks` is a `Set` of full IDs.

- [ ] **Step 1: Add section keys and step IDs to `D`**

Add `k:"<key>"` to each flow section object and `id:"<slug>"` to each step, in this exact order (one line per section: phase · section heading → `k` → step ids in order):

```
plan · DISPATCH SETUP → setup → airframe, airports, route, ci, units, generate
plan · READ THE OFP → ofp → block, zfw, crz, rwy, fuel, flypad_link
dark · ELECTRICAL POWER-UP → elec → bat, ext_pwr, apu
dark · IMMEDIATELY AFTER POWER → power → adirs, lights
dark · SAFETY TESTS & OVERHEAD SCAN → tests → eng1_fire, eng2_fire, apu_fire, emer_exit, seat_belts, no_smoking, probe_heat, ovhd_scan
prep · MCDU — DATA & INIT A → init → status, init_request, ci, crz_fl, flt_nbr
prep · MCDU — F-PLN & RAD NAV → fpln → legs, discont, sid, radnav
prep · FLYPAD — LOAD THE AIRCRAFT → load → fuel, payload, doors
prep · MCDU — INIT B & PERF TO → perf → zfw, block, perf_calc, flaps_ths, flex, vspeeds, thr_red
prep · FCU & LOWER PANEL → fcu → baro, nd, fd
clr · MAKE THE JET MATCH THE CLEARANCE → match → sid, discont, fcu_alt, xpdr_code, perf_to, brief
push · BEFORE PUSHBACK → before → apu, apu_bleed_on, ext_pwr, doors, fuel_pumps, beacon, windows, thr_park
push · ENGINE START → start → xpdr, mode_ign, eng2, eng1, mode_norm
push · AFTER START FLOW → after → apu_bleed, apu_master, anti_ice, flaps, pitch_trim, rudder_trim, ecam_status
taxi · ROLLING → rolling → lights, park_brk, brake_check, steering
taxi · DURING TAXI → during → flt_ctl, spoilers, auto_brk, to_config, cabin, to_memo
taxi · APPROACHING HOLD SHORT → hold → tcas, packs, eng_mode
tkof · LINING UP → lineup → lights, rwy_check, chrono
tkof · TAKEOFF ROLL → roll → thrust, fma, kt100, v1_vr
tkof · INITIAL CLIMB → climb → gear, ap, thr_red, flaps, packs
clb · PASSING 10 000 FT → 10k → lights, seat_belts, nd
clb · TRANSITION ALTITUDE → trans → baro, alt_xcheck
clb · CONTINUOUS → cont → fma, speed, ecam
crz · HOUSEKEEPING → house → fuel, sd_pages, step_climb
crz · ARRIVAL SETUP → arrival → atis, star, discont, perf_appr, perf_des, ldg_perf, brief, radnav
des · AT / NEAR TOD → tod → fcu_alt, managed, vdev
des · TRANSITION LEVEL → trans → baro, alt_xcheck
des · PASSING 10 000 FT → 10k → lights, seat_belts, speed, ldg_elev
appr · SETUP & DECELERATION → decel → appr_phase, ls, speed
appr · INTERCEPT → intercept → appr_pb, ap2, capture
appr · CONFIGURATION SCHEDULE → config → flaps1, flaps2, gear, spoilers, full, lights, ldg_memo, stable
land · FINAL & TOUCHDOWN → final → minimums, retard, touchdown, rev, decel, kt70
land · VACATING → vacate → clear, lights
park · AFTER LANDING FLOW → after → spoilers, flaps, apu, wx, tcas, eng_mode
park · AT THE GATE — SHUTDOWN → shutdown → park_brk, apu_bleed, masters, beacon, signs_pumps, flypad
park · SECURING → secure → adirs, oxygen, apu, emer_exit, ext_lts, bat
```

Example of the resulting shape:

```js
{h:"IMMEDIATELY AFTER POWER",k:"power",s:[
  {id:"adirs",t:"<b>ADIRS 1, 2, 3</b> — NAV",c:"OVHD ADIRS",n:"Start the ~10 min alignment now and do everything else while it runs. IR lights extinguish when aligned."},
  {id:"lights",t:"<b>Cockpit / integ / dome lights</b> — as required",c:"OVHD"}]},
```

`taxi.during.spoilers` and `push.after.flaps` come from Step 3 content edits; the `taxi · DURING TAXI` list above already includes the new `spoilers` step in its final position.

- [ ] **Step 2: Add checklist item IDs**

Add `id:"<slug>"` to each checklist item (skip `{line:1}`), in order:

```
clr  → cockpit_prep, gear_pins, signs, adirs, fuel_qty, to_data, baro
push → windows_doors, beacon, thr_levers, park_brk, | anti_ice, ecam_status, pitch_trim, rudder_trim
taxi → flt_ctl, flt_inst, briefing, flaps, vspeeds, ecam_memo, | to_rwy, cabin_crew, tcas, eng_mode, packs
clb  → gear, flaps, packs, | baro
des  → briefing, ecam_status, seat_belts, baro, minimum, auto_brake
appr → cabin_crew, athr, ecam_memo
park → apu_bleed, engines, seat_belts, ext_lt, fuel_pumps, park_brk, | adirs, oxygen, apu_bleed_off, emer_exit, signs, apu_bat
```

(`|` marks where the existing `{line:1}` sits.) Example: `{id:"cockpit_prep",ch:"COCKPIT PREP",rsp:"COMPLETED (BOTH)"}`.

- [ ] **Step 3: Content fixes**

In push `after`, replace the step text
`<b>GND SPLRS</b> — leave for taxi flow · <b>FLAPS</b> — set takeoff CONF (1+F)`
with
`<b>FLAPS</b> — set takeoff CONF (1+F)` (id `flaps`, chip `PED`).

In taxi `during`, insert after `flt_ctl`:

```js
{id:"spoilers",t:"<b>GND SPLRS</b> — ARM",c:"PED",n:"Armed before T.O CONFIG so the takeoff memo shows SPLRS ARM; the initial-climb flow disarms them."},
```

In push `start`, step `eng2`, change `stabilized ~68% N2` to `stabilized ~68% N2 (FBW, ISA sea level)`.

- [ ] **Step 4: Move profile heights into the data**

Move `const GY=118;` above `const D=[`. Add `y` to each phase object right after `nav`: `y:GY` for plan, dark, prep, clr, push, taxi, land, park; `y:106` tkof; `y:62` clb; `y:30` crz; `y:62` des; `y:92` appr. Delete `PROFY`. In `drawProfile` change `PROFY[i]` to `D[i].y`:

```js
const pts=D.map((p,i)=>[x0+(x1-x0)*i/(n-1),p.y]);
```

- [ ] **Step 5: Assign full IDs once, detect duplicates**

Directly after the `D` array (and after `GY`), add:

```js
/* Progress, cue links and rules all address steps by these IDs, so a
   duplicate would silently merge two steps. */
const STEP_IDS=new Set();
function claim(st,key){
  if(STEP_IDS.has(key))console.error("Duplicate step id",key);
  STEP_IDS.add(key);st.key=key;
}
D.forEach(p=>{
  (p.flows||[]).forEach(sec=>sec.s.forEach(st=>claim(st,`${p.id}.${sec.k}.${st.id}`)));
  if(p.cl&&p.cl.items)p.cl.items.forEach(it=>{if(!it.line)claim(it,`${p.id}.cl.${it.id}`)});
});
```

- [ ] **Step 6: Switch progress and storage to IDs**

Replace `SKEY`, `load`, `key`, `phaseTotals`, and the two render sites:

```js
const SKEY="a32nx-companion.v2";
try{localStorage.removeItem("a32nx-companion.v1")}catch(e){}
```

In `load`, keep only known IDs:

```js
if(Array.isArray(s.checks))state.checks=new Set(s.checks.filter(k=>STEP_IDS.has(k)));
```

Delete `function key(...)`. New `phaseTotals`:

```js
function phaseItems(p){
  const flow=(p.flows||[]).flatMap(sec=>sec.s);
  const cl=p.cl&&p.cl.items?p.cl.items.filter(it=>!it.line):[];
  return flow.concat(cl);
}
function phaseTotals(pi){
  const items=phaseItems(D[pi]);
  return[items.filter(it=>state.checks.has(it.key)).length,items.length];
}
```

In `renderPhase`, flow steps use `st.key` and put `data-k` on the label too:

```js
sec.s.map(st=>{const k=st.key,ck=state.checks.has(k);
  return `<label class="step${ck?" ck":""}" data-k="${k}"><input type="checkbox" data-k="${k}" ${ck?"checked":""}>
    <span class="txt">${st.t}${st.c?`<span class="chip">${st.c}</span>`:""}${st.n?`<span class="note">${st.n}</span>`:""}</span></label>`;
}).join("")
```

Checklist items use `const k=it.key,ck=state.checks.has(k);` (drop the index argument from the `map` callback).

The event binding `$("#phaseArt").querySelectorAll("input[data-k]")` and `.cl-item[data-k]` keep working unchanged.

- [ ] **Step 7: Verify in the browser pane**

Open `file:///Users/ismael/onna/a32nx-companion/index.html` in the built-in browser (`mcp__Claude_Browser__navigate`), then run with `javascript_tool`:

```js
({ids:STEP_IDS.size,
  hasAdirs:STEP_IDS.has("dark.power.adirs"),
  hasSpoilers:STEP_IDS.has("taxi.during.spoilers"),
  hasFlaps:STEP_IDS.has("push.after.flaps"),
  hasBeacon:STEP_IDS.has("park.shutdown.beacon"),
  hasGear:STEP_IDS.has("appr.config.gear"),
  profy:typeof PROFY,
  batc:D.filter(p=>p.batc).length})
```

Expected: `ids` = 217 (159 flow steps + 58 checklist items, matching the lists in Steps 1–2), all `has*` true, `profy` = `"undefined"`, `batc` = 13. `read_console_messages` with `onlyErrors:true` returns nothing. Tick a step on the TAXI phase, reload, and confirm it stays ticked and `localStorage.getItem("a32nx-companion.v2")` contains `"taxi.during.spoilers"` when that step is ticked.

- [ ] **Step 8: Commit**

```bash
git add index.html
git commit -m "Give every page step a stable ID and move to v2 storage"
```

---

### Task 2: Bridge package scaffold and config

**Files:**
- Create: `bridge/pyproject.toml`, `bridge/companion/__init__.py`, `bridge/companion/config.py`, `bridge/tests/__init__.py`, `bridge/tests/test_config.py`, `config.example.toml`, `.gitignore`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class SimbriefConfig: username: str | None; userid: str | None`
  - `@dataclass(frozen=True) class ServerConfig: host: str = "0.0.0.0"; port: int = 8765`
  - `@dataclass(frozen=True) class SopConfig: landing_lights_off_ft: int = 10000; single_engine_taxi: bool = False; apu_start_before_push_min: int = 5; units: Literal["kg","lb"] = "kg"`
  - `@dataclass(frozen=True) class Config: simbrief: SimbriefConfig; server: ServerConfig; sop: SopConfig`
  - `class ConfigError(Exception)`
  - `def load_config(path: Path) -> Config`

- [ ] **Step 1: Create `bridge/pyproject.toml`**

```toml
[project]
name = "a32nx-companion"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["aiohttp>=3.9"]

[dependency-groups]
dev = ["pytest>=8", "pytest-aiohttp>=1.0", "ruff>=0.6", "mypy>=1.11"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["companion"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
strict = true
python_version = "3.12"
```

Create empty `bridge/companion/__init__.py` and `bridge/tests/__init__.py`. Run `cd bridge && uv sync` and confirm it creates `bridge/uv.lock` and `.venv`.

- [ ] **Step 2: Create `config.example.toml` and `.gitignore`**

`config.example.toml` (repo root):

```toml
[simbrief]
username = "navigraph-alias"     # or userid = "123456"

[server]
host = "0.0.0.0"
port = 8765

[sop]                            # operator-variable items, consumed by rules
landing_lights_off_ft = 10000
single_engine_taxi = false
apu_start_before_push_min = 5
units = "kg"                     # must match OFP units
```

`.gitignore`:

```
config.toml
.venv/
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
```

- [ ] **Step 3: Write the failing tests**

`bridge/tests/test_config.py`:

```python
from pathlib import Path

import pytest

from companion.config import ConfigError, load_config

EXAMPLE = Path(__file__).resolve().parents[2] / "config.example.toml"


def write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(body)
    return path


def test_example_config_loads() -> None:
    config = load_config(EXAMPLE)
    assert config.simbrief.username == "navigraph-alias"
    assert config.simbrief.userid is None
    assert config.server.port == 8765
    assert config.sop.units == "kg"


def test_defaults_fill_missing_sections(tmp_path: Path) -> None:
    config = load_config(write(tmp_path, '[simbrief]\nuserid = "42"\n'))
    assert config.simbrief.userid == "42"
    assert config.server.host == "0.0.0.0"
    assert config.sop.landing_lights_off_ft == 10000


def test_simbrief_needs_exactly_one_identity(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="username or userid"):
        load_config(write(tmp_path, "[simbrief]\n"))
    with pytest.raises(ConfigError, match="username or userid"):
        load_config(write(tmp_path, '[simbrief]\nusername = "a"\nuserid = "1"\n'))


def test_rejects_unknown_units(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="units"):
        load_config(write(tmp_path, '[simbrief]\nuserid = "1"\n[sop]\nunits = "st"\n'))


def test_missing_file_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.toml")


def test_unknown_key_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"\[server\]"):
        load_config(write(tmp_path, '[simbrief]\nuserid = "1"\n[server]\nprot = 1\n'))
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd bridge && uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'companion.config'`

- [ ] **Step 5: Implement `bridge/companion/config.py`**

```python
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class SimbriefConfig:
    username: str | None = None
    userid: str | None = None


@dataclass(frozen=True)
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8765


@dataclass(frozen=True)
class SopConfig:
    landing_lights_off_ft: int = 10000
    single_engine_taxi: bool = False
    apu_start_before_push_min: int = 5
    units: Literal["kg", "lb"] = "kg"


@dataclass(frozen=True)
class Config:
    simbrief: SimbriefConfig
    server: ServerConfig = field(default_factory=ServerConfig)
    sop: SopConfig = field(default_factory=SopConfig)


def load_config(path: Path) -> Config:
    try:
        raw = tomllib.loads(path.read_text())
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc

    simbrief = _build(SimbriefConfig, raw, "simbrief")
    if (simbrief.username is None) == (simbrief.userid is None):
        raise ConfigError("[simbrief] needs exactly one of username or userid")

    sop = _build(SopConfig, raw, "sop")
    if sop.units not in ("kg", "lb"):
        raise ConfigError(f"[sop] units must be 'kg' or 'lb', got {sop.units!r}")

    return Config(simbrief=simbrief, server=_build(ServerConfig, raw, "server"), sop=sop)


def _build[T](cls: type[T], raw: dict[str, Any], name: str) -> T:
    # A typo'd key reaches the dataclass constructor as a TypeError.
    try:
        return cls(**_section(raw, name))
    except TypeError as exc:
        raise ConfigError(f"[{name}] {exc}") from exc


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    section = raw.get(name, {})
    if not isinstance(section, dict):
        raise ConfigError(f"[{name}] must be a table")
    return cast(dict[str, Any], section)
```

- [ ] **Step 6: Run tests, ruff, mypy**

Run: `cd bridge && uv run pytest tests/test_config.py -v && uv run ruff check . && uv run ruff format --check . && uv run mypy companion`
Expected: 6 passed, ruff and mypy clean.

- [ ] **Step 7: Commit**

```bash
git add .gitignore config.example.toml bridge/pyproject.toml bridge/uv.lock bridge/companion/__init__.py bridge/companion/config.py bridge/tests/__init__.py bridge/tests/test_config.py
git commit -m "Add bridge package scaffold and config loader"
```

---

### Task 3: SimBrief OFP normalization

**Files:**
- Create: `bridge/companion/simbrief.py`, `bridge/tests/fixtures/ofp_krdu_katl.json`, `bridge/tests/test_simbrief_normalize.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Fix: ident: str; lat: float; lon: float; alt_ft: int; stage: Literal["CLB","CRZ","DES"]; planned_fob: float; is_sid_star: bool`
  - `@dataclass(frozen=True) class Ofp:` fields exactly as spec §5 (`origin, origin_rwy, dest, dest_rwy, dest_lat, dest_lon, altn, route, sid, star, cost_index, initial_fl, step_climbs, units, block_fuel, trip_fuel, final_reserve, altn_fuel, zfw, tow, ldw, fixes, airac, generated_at`); `step_climbs: tuple[tuple[str, int], ...]`, `fixes: tuple[Fix, ...]` (tuples keep the dataclass hashable and frozen).
  - `class OfpError(Exception)`
  - `def normalize(raw: dict[str, Any]) -> Ofp`
  - `def to_wire(ofp: Ofp) -> dict[str, Any]` (JSON-safe: lists, ISO datetime)

- [ ] **Step 1: Create the fixture**

`bridge/tests/fixtures/ofp_krdu_katl.json` — the v2 shape (strings for numbers, arrays for `alternate` and `navlog`), limited to the fields `normalize` reads:

```json
{
  "fetch": {"userid": "1", "static_id": "", "status": "Success", "time": "0.01"},
  "params": {"units": "kgs", "airac": "2610", "time_generated": "1760820000"},
  "general": {
    "route": "LILLS4 LILLS Q64 SPA OZZZI1",
    "costindex": "15",
    "initial_altitude": "32000",
    "stepclimb_string": "KRDU/0320 SPA/0360",
    "sid_ident": "LILLS4",
    "star_ident": "OZZZI1"
  },
  "origin": {"icao_code": "KRDU", "plan_rwy": "23L", "pos_lat": "35.877639", "pos_long": "-78.787472"},
  "destination": {"icao_code": "KATL", "plan_rwy": "27R", "pos_lat": "33.636719", "pos_long": "-84.428067"},
  "alternate": [{"icao_code": "KBHM", "plan_rwy": "06"}],
  "fuel": {"plan_ramp": "5400", "enroute_burn": "2650", "reserve": "1050", "alternate_burn": "1100"},
  "weights": {"est_zfw": "55300", "est_tow": "60500", "est_ldw": "57850"},
  "navlog": [
    {"ident": "LILLS", "pos_lat": "35.700000", "pos_long": "-79.100000", "altitude_feet": "9000", "stage": "CLB", "fuel_plan_onboard": "4950", "is_sid_star": "1"},
    {"ident": "TOC", "pos_lat": "35.500000", "pos_long": "-79.700000", "altitude_feet": "32000", "stage": "CLB", "fuel_plan_onboard": "4500", "is_sid_star": "0"},
    {"ident": "SPA", "pos_lat": "35.033333", "pos_long": "-81.926667", "altitude_feet": "36000", "stage": "CRZ", "fuel_plan_onboard": "3700", "is_sid_star": "0"},
    {"ident": "TOD", "pos_lat": "34.300000", "pos_long": "-83.200000", "altitude_feet": "36000", "stage": "CRZ", "fuel_plan_onboard": "3050", "is_sid_star": "0"},
    {"ident": "OZZZI", "pos_lat": "33.900000", "pos_long": "-83.900000", "altitude_feet": "12000", "stage": "DSC", "fuel_plan_onboard": "2700", "is_sid_star": "1"},
    {"ident": "KATL", "pos_lat": "33.636719", "pos_long": "-84.428067", "altitude_feet": "1026", "stage": "DSC", "fuel_plan_onboard": "2550", "is_sid_star": "0"}
  ]
}
```

- [ ] **Step 2: Write the failing tests**

`bridge/tests/test_simbrief_normalize.py`:

```python
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
    return json.loads(FIXTURE.read_text())


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
    assert (ofp.block_fuel, ofp.trip_fuel, ofp.final_reserve, ofp.altn_fuel) == (5400, 2650, 1050, 1100)
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd bridge && uv run pytest tests/test_simbrief_normalize.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'companion.simbrief'`

- [ ] **Step 4: Implement normalization in `bridge/companion/simbrief.py`**

```python
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Literal

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


def _timestamp(value: str) -> datetime:
    if value.isdigit():
        return datetime.fromtimestamp(int(value), UTC)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
```


- [ ] **Step 5: Run tests, ruff, mypy**

Run: `cd bridge && uv run pytest tests/test_simbrief_normalize.py -v && uv run ruff check . && uv run ruff format --check . && uv run mypy companion`
Expected: 10 passed, ruff and mypy clean. (`1760820000` is `2025-10-18T20:40:00+00:00`; if the assertion in `test_to_wire_is_json_safe` disagrees, recompute with `python -c "import datetime;print(datetime.datetime.fromtimestamp(1760820000, datetime.UTC).isoformat())"` and fix the test constant.)

- [ ] **Step 6: Commit**

```bash
git add bridge/companion/simbrief.py bridge/tests/fixtures/ofp_krdu_katl.json bridge/tests/test_simbrief_normalize.py
git commit -m "Normalize SimBrief v2 OFPs into a stable Ofp shape"
```

---

### Task 4: SimBrief fetch and on-disk cache

**Files:**
- Modify: `bridge/companion/simbrief.py` (append)
- Create: `bridge/tests/test_simbrief_fetch.py`

**Interfaces:**
- Consumes: `SimbriefConfig` (Task 2), `normalize`, `Ofp`, `OfpError` (Task 3).
- Produces:
  - `SIMBRIEF_URL = "https://www.simbrief.com/api/xml.fetcher.php"`
  - `class SimbriefError(Exception)`
  - `async def fetch_raw(session: aiohttp.ClientSession, config: SimbriefConfig, url: str = SIMBRIEF_URL) -> dict[str, Any]`
  - `def default_cache_path() -> Path` → `Path.home() / ".a32nx-companion" / "ofp.json"`
  - `class SimbriefLoader:` `__init__(self, config: SimbriefConfig, cache_path: Path, url: str = SIMBRIEF_URL)`; `def cached(self) -> Ofp | None`; `async def refresh(self) -> Ofp` (fetch → normalize → write cache → return; raises `SimbriefError` or `OfpError`). The loader opens its own `aiohttp.ClientSession` per refresh with a 15 s total timeout.

The cache stores the raw SimBrief JSON so a fixed `normalize` re-reads old caches correctly.

- [ ] **Step 1: Write the failing tests**

`bridge/tests/test_simbrief_fetch.py` uses a real local aiohttp server standing in for SimBrief:

```python
import json
from pathlib import Path
from typing import Any

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from companion.config import SimbriefConfig
from companion.simbrief import SimbriefError, SimbriefLoader

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "ofp_krdu_katl.json").read_text())


async def fake_simbrief(aiohttp_server: Any, seen: list[dict[str, str]]) -> TestServer:
    async def handler(request: web.Request) -> web.Response:
        seen.append(dict(request.query))
        if request.query.get("username") == "bad":
            return web.json_response({"fetch": {"status": "Error: Unknown UserID"}}, status=400)
        if request.query.get("username") == "garbage":
            return web.Response(text="<html>oops</html>", content_type="text/html")
        return web.json_response(FIXTURE)

    app = web.Application()
    app.router.add_get("/api/xml.fetcher.php", handler)
    server: TestServer = await aiohttp_server(app)
    return server


async def test_refresh_fetches_normalizes_and_caches(aiohttp_server: Any, tmp_path: Path) -> None:
    seen: list[dict[str, str]] = []
    server = await fake_simbrief(aiohttp_server, seen)
    cache = tmp_path / "ofp.json"
    loader = SimbriefLoader(SimbriefConfig(username="pilot"), cache, str(server.make_url("/api/xml.fetcher.php")))

    ofp = await loader.refresh()

    assert ofp.origin == "KRDU"
    assert seen == [{"username": "pilot", "json": "v2"}]
    assert json.loads(cache.read_text()) == FIXTURE
    assert loader.cached() == ofp


async def test_userid_is_sent_when_configured(aiohttp_server: Any, tmp_path: Path) -> None:
    seen: list[dict[str, str]] = []
    server = await fake_simbrief(aiohttp_server, seen)
    loader = SimbriefLoader(SimbriefConfig(userid="123"), tmp_path / "o.json", str(server.make_url("/api/xml.fetcher.php")))
    await loader.refresh()
    assert seen == [{"userid": "123", "json": "v2"}]


async def test_bad_user_raises_and_keeps_cache(aiohttp_server: Any, tmp_path: Path) -> None:
    server = await fake_simbrief(aiohttp_server, [])
    cache = tmp_path / "ofp.json"
    cache.write_text(json.dumps(FIXTURE))
    loader = SimbriefLoader(SimbriefConfig(username="bad"), cache, str(server.make_url("/api/xml.fetcher.php")))

    with pytest.raises(SimbriefError, match="Unknown UserID"):
        await loader.refresh()

    assert json.loads(cache.read_text()) == FIXTURE


async def test_non_json_response_raises(aiohttp_server: Any, tmp_path: Path) -> None:
    server = await fake_simbrief(aiohttp_server, [])
    loader = SimbriefLoader(SimbriefConfig(username="garbage"), tmp_path / "o.json", str(server.make_url("/api/xml.fetcher.php")))
    with pytest.raises(SimbriefError, match="JSON"):
        await loader.refresh()


def test_cached_is_none_without_a_file(tmp_path: Path) -> None:
    assert SimbriefLoader(SimbriefConfig(username="x"), tmp_path / "missing.json").cached() is None


def test_cached_is_none_for_a_corrupt_file(tmp_path: Path) -> None:
    cache = tmp_path / "ofp.json"
    cache.write_text("{not json")
    assert SimbriefLoader(SimbriefConfig(username="x"), cache).cached() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd bridge && uv run pytest tests/test_simbrief_fetch.py -v`
Expected: FAIL with `ImportError: cannot import name 'SimbriefError'`

- [ ] **Step 3: Implement fetch, cache and loader**

Append to `bridge/companion/simbrief.py` (add `import json`, `import logging`, `from pathlib import Path`, `import aiohttp`, and `from companion.config import SimbriefConfig` to the imports at the top):

```python
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
        raise SimbriefError(f"SimBrief fetch failed (HTTP {response.status}): {status or 'no status'}")
    return body


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
        except (json.JSONDecodeError, OfpError) as exc:
            log.warning("ignoring unreadable OFP cache %s: %s", self._cache_path, exc)
            return None

    async def refresh(self) -> Ofp:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            raw = await fetch_raw(session, self._config, self._url)
        ofp = normalize(raw)
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(json.dumps(raw))
        return ofp
```

`aiohttp.ClientError` and `TimeoutError` from the network propagate to the caller (the server logs them; Task 5).

- [ ] **Step 4: Run tests, ruff, mypy**

Run: `cd bridge && uv run pytest tests/test_simbrief_fetch.py tests/test_simbrief_normalize.py -v && uv run ruff check . && uv run ruff format --check . && uv run mypy companion`
Expected: 16 passed, ruff and mypy clean.

- [ ] **Step 5: Commit**

```bash
git add bridge/companion/simbrief.py bridge/tests/test_simbrief_fetch.py
git commit -m "Fetch the SimBrief OFP and cache the raw response"
```

---

### Task 5: aiohttp server, WebSocket protocol and CLI

**Files:**
- Create: `bridge/companion/server.py`, `bridge/companion/__main__.py`, `bridge/tests/test_server.py`

**Interfaces:**
- Consumes: `Ofp`, `OfpError`, `SimbriefError`, `SimbriefLoader`, `default_cache_path`, `to_wire` (Tasks 3–4); `load_config`, `ConfigError` (Task 2).
- Produces:
  - `class OfpSource(Protocol): def cached(self) -> Ofp | None: ...; async def refresh(self) -> Ofp: ...` (`SimbriefLoader` satisfies it; tests pass a fake they own)
  - `INDEX_PATH = Path(__file__).resolve().parents[2] / "index.html"`
  - `def make_app(ofp_source: OfpSource, index_path: Path = INDEX_PATH) -> web.Application`
  - `class Hub` stored at `app[HUB]` (`HUB = web.AppKey("hub", Hub)`) with `ofp: Ofp | None`, `clients: set[web.WebSocketResponse]`
  - Messages sent, exactly:
    - on connect: `{"type":"hello","version":1,"sources":{"sim":false,"mcdu":false,"ofp":<bool>}}`, then `{"type":"ofp","data":to_wire(ofp)}` when an OFP is held
    - after a successful refresh, to every client: `{"type":"ofp","data":...}`, and `{"type":"sources","sim":false,"mcdu":false,"ofp":true}` when `ofp` flipped from false to true
  - Messages handled: `{"type":"ofp_refresh"}`. Every other `type` and every malformed frame is logged at debug and ignored.
  - CLI: `python -m companion run [--config PATH]` (default `config.toml` in the current directory).

- [ ] **Step 1: Write the failing tests**

`bridge/tests/test_server.py`:

```python
import asyncio
import json
from pathlib import Path
from typing import Any

from aiohttp.test_utils import TestClient

from companion.server import make_app
from companion.simbrief import Ofp, SimbriefError, normalize, to_wire

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "ofp_krdu_katl.json").read_text())


class FakeOfpSource:
    def __init__(self, cached: Ofp | None, fresh: Ofp | Exception | None) -> None:
        self._cached = cached
        self._fresh = fresh
        self.refreshes = 0

    def cached(self) -> Ofp | None:
        return self._cached

    async def refresh(self) -> Ofp:
        self.refreshes += 1
        if isinstance(self._fresh, Exception):
            raise self._fresh
        assert self._fresh is not None
        return self._fresh


async def client_for(aiohttp_client: Any, source: FakeOfpSource, tmp_path: Path) -> TestClient:
    index = tmp_path / "index.html"
    index.write_text("<!doctype html><title>t</title>")
    client: TestClient = await aiohttp_client(make_app(source, index))
    return client


async def recv(ws: Any) -> dict[str, Any]:
    msg: dict[str, Any] = await asyncio.wait_for(ws.receive_json(), timeout=2)
    return msg


async def test_serves_index(aiohttp_client: Any, tmp_path: Path) -> None:
    client = await client_for(aiohttp_client, FakeOfpSource(None, SimbriefError("x")), tmp_path)
    response = await client.get("/")
    assert response.status == 200
    assert "<title>t</title>" in await response.text()


async def test_hello_then_cached_ofp(aiohttp_client: Any, tmp_path: Path) -> None:
    ofp = normalize(FIXTURE)
    client = await client_for(aiohttp_client, FakeOfpSource(ofp, SimbriefError("offline")), tmp_path)
    ws = await client.ws_connect("/ws")
    assert await recv(ws) == {"type": "hello", "version": 1, "sources": {"sim": False, "mcdu": False, "ofp": True}}
    assert await recv(ws) == {"type": "ofp", "data": to_wire(ofp)}


async def test_hello_without_ofp(aiohttp_client: Any, tmp_path: Path) -> None:
    client = await client_for(aiohttp_client, FakeOfpSource(None, SimbriefError("offline")), tmp_path)
    ws = await client.ws_connect("/ws")
    assert (await recv(ws))["sources"]["ofp"] is False


async def test_refresh_broadcasts_ofp_and_sources(aiohttp_client: Any, tmp_path: Path) -> None:
    ofp = normalize(FIXTURE)
    source = FakeOfpSource(None, SimbriefError("offline at startup"))
    client = await client_for(aiohttp_client, source, tmp_path)
    first = await client.ws_connect("/ws")
    second = await client.ws_connect("/ws")
    await recv(first)
    await recv(second)

    source._fresh = ofp
    await first.send_json({"type": "ofp_refresh"})

    for ws in (first, second):
        assert await recv(ws) == {"type": "ofp", "data": to_wire(ofp)}
        assert await recv(ws) == {"type": "sources", "sim": False, "mcdu": False, "ofp": True}


async def test_failed_refresh_keeps_connection_open(aiohttp_client: Any, tmp_path: Path) -> None:
    source = FakeOfpSource(None, SimbriefError("bad user"))
    client = await client_for(aiohttp_client, source, tmp_path)
    ws = await client.ws_connect("/ws")
    await recv(ws)
    await ws.send_json({"type": "ofp_refresh"})
    await ws.send_str("not json")
    await ws.send_json({"type": "dismiss", "id": "x"})
    source._fresh = normalize(FIXTURE)
    await ws.send_json({"type": "ofp_refresh"})
    assert (await recv(ws))["type"] == "ofp"
    assert not ws.closed


async def test_startup_refresh_runs_once(aiohttp_client: Any, tmp_path: Path) -> None:
    source = FakeOfpSource(None, normalize(FIXTURE))
    client = await client_for(aiohttp_client, source, tmp_path)
    ws = await client.ws_connect("/ws")
    first = await recv(ws)
    if first["sources"]["ofp"] is False:
        assert (await recv(ws))["type"] == "ofp"
    assert source.refreshes == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd bridge && uv run pytest tests/test_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'companion.server'`

- [ ] **Step 3: Implement `bridge/companion/server.py`**

```python
import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import aiohttp
from aiohttp import web

from companion.simbrief import Ofp, OfpError, SimbriefError, to_wire

PROTOCOL_VERSION = 1
INDEX_PATH = Path(__file__).resolve().parents[2] / "index.html"
log = logging.getLogger(__name__)


class OfpSource(Protocol):
    def cached(self) -> Ofp | None: ...
    async def refresh(self) -> Ofp: ...


@dataclass
class Hub:
    source: OfpSource
    ofp: Ofp | None = None
    clients: set[web.WebSocketResponse] = field(default_factory=set)
    _refreshing: asyncio.Lock = field(default_factory=asyncio.Lock)

    def sources(self) -> dict[str, bool]:
        return {"sim": False, "mcdu": False, "ofp": self.ofp is not None}

    async def broadcast(self, message: dict[str, Any]) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_json(message)
            except ConnectionResetError:
                self.clients.discard(ws)

    async def refresh_ofp(self) -> None:
        # Serialized so a burst of refresh clicks costs one SimBrief request at a time.
        async with self._refreshing:
            try:
                ofp = await self.source.refresh()
            except (SimbriefError, OfpError, aiohttp.ClientError, TimeoutError) as exc:
                log.warning("OFP refresh failed: %s", exc)
                return
            had_ofp = self.ofp is not None
            self.ofp = ofp
            await self.broadcast({"type": "ofp", "data": to_wire(ofp)})
            if not had_ofp:
                await self.broadcast({"type": "sources", **self.sources()})


HUB = web.AppKey("hub", Hub)
STARTUP_TASK = web.AppKey("startup_task", asyncio.Task[None])


def make_app(ofp_source: OfpSource, index_path: Path = INDEX_PATH) -> web.Application:
    app = web.Application()
    app[HUB] = Hub(source=ofp_source, ofp=ofp_source.cached())

    async def index(_: web.Request) -> web.FileResponse:
        return web.FileResponse(index_path)

    async def start_refresh(app: web.Application) -> None:
        app[STARTUP_TASK] = asyncio.create_task(app[HUB].refresh_ofp())

    async def stop_refresh(app: web.Application) -> None:
        app[STARTUP_TASK].cancel()

    app.router.add_get("/", index)
    app.router.add_get("/ws", websocket)
    app.on_startup.append(start_refresh)
    app.on_cleanup.append(stop_refresh)
    return app



async def websocket(request: web.Request) -> web.WebSocketResponse:
    hub = request.app[HUB]
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    hub.clients.add(ws)
    try:
        await ws.send_json({"type": "hello", "version": PROTOCOL_VERSION, "sources": hub.sources()})
        if hub.ofp is not None:
            await ws.send_json({"type": "ofp", "data": to_wire(hub.ofp)})
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                await handle(hub, msg.data)
    finally:
        hub.clients.discard(ws)
    return ws


async def handle(hub: Hub, text: str) -> None:
    try:
        message = json.loads(text)
    except json.JSONDecodeError:
        log.debug("ignoring non-JSON frame")
        return
    if not isinstance(message, dict):
        return
    if message.get("type") == "ofp_refresh":
        await hub.refresh_ofp()
    else:
        log.debug("ignoring message type %r", message.get("type"))
```

Note on `test_startup_refresh_runs_once`: the startup refresh may finish before or after the client connects, so the test accepts both orders.

- [ ] **Step 4: Implement `bridge/companion/__main__.py`**

```python
import argparse
import logging
import sys
from pathlib import Path

from aiohttp import web

from companion.config import ConfigError, load_config
from companion.server import make_app
from companion.simbrief import SimbriefLoader, default_cache_path


def main() -> int:
    parser = argparse.ArgumentParser(prog="companion")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="serve the page and the /ws bridge")
    run.add_argument("--config", type=Path, default=Path("config.toml"))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"companion: {exc}", file=sys.stderr)
        return 2

    loader = SimbriefLoader(config.simbrief, default_cache_path())
    web.run_app(make_app(loader), host=config.server.host, port=config.server.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the whole bridge suite, ruff, mypy**

Run: `cd bridge && uv run pytest -v && uv run ruff check . && uv run ruff format --check . && uv run mypy companion`
Expected: all tests pass (6 config + 10 normalize + 6 fetch + 6 server), ruff and mypy clean.

- [ ] **Step 6: Smoke-test the CLI**

Run: `cd bridge && uv run python -m companion run --config /nonexistent.toml; echo "exit=$?"`
Expected: `companion: config file not found: /nonexistent.toml` and `exit=2`.

- [ ] **Step 7: Commit**

```bash
git add bridge/companion/server.py bridge/companion/__main__.py bridge/tests/test_server.py
git commit -m "Serve the page and push hello/ofp over /ws"
```

---

### Task 6: Page — bridge client, connection pill, OFP rail

**Files:**
- Modify: `index.html`

**Interfaces:**
- Consumes: wire messages from Task 5 (`hello`, `ofp`, `sources`); `ofp.data` fields from `to_wire` (Task 3): `origin, origin_rwy, dest, dest_rwy, altn, route, sid, star, cost_index, initial_fl, step_climbs [[fix, fl]], units "kg"|"lb", block_fuel, trip_fuel, final_reserve, altn_fuel, zfw, tow, ldw, fixes [{ident, planned_fob, ...}], airac, generated_at`.
- Produces: `state.bridge` (`{connected:bool, sources:{sim,mcdu,ofp}}`), `state.ofp` (normalized OFP or `null`), `send(msg)` helper for later milestones.

- [ ] **Step 1: Add an escape helper and bridge state**

After `const $=...`:

```js
const esc=s=>String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
```

Extend state: `const state={checks:new Set(),cur:0,tab:"flow",ofp:null,bridge:{connected:false,sources:{sim:false,mcdu:false,ofp:false}}};`

`save()` keeps persisting only `checks`, `cur`, `tab`; the OFP always comes fresh from the bridge.

- [ ] **Step 2: Connection pill markup and CSS**

In the header `.hdr-right`, before the progress pill:

```html
<div class="conn" id="connPill" hidden></div>
```

CSS (next to `.prog-pill`):

```css
.conn{border:1px solid var(--line);border-radius:4px;padding:7px 12px;font-size:11.5px;letter-spacing:.08em;color:var(--dimmer);background:var(--panel2);display:flex;gap:12px}
.conn span::after{content:" ●"}
.conn .on{color:var(--grn)}
```

Render function:

```js
function renderConn(){
  const el=$("#connPill"),b=state.bridge;
  el.hidden=!b.connected;
  if(!b.connected)return;
  const dot=(label,on)=>`<span class="${on?"on":""}">${label}</span>`;
  el.innerHTML=dot("BRIDGE",true)+dot("SIM",b.sources.sim)+dot("OFP",b.sources.ofp)+dot("MCDU",b.sources.mcdu);
}
```

Call `renderConn()` from `render()`.

- [ ] **Step 3: OFP rail rows**

Add after `phaseTotals`:

```js
const wt=(v,o)=>Math.round(v).toLocaleString("en-US").replace(/,/g," ")+" "+o.units;
const fl=n=>"FL"+String(n).padStart(3,"0");
function ofpRows(pid,o){
  const destFob=o.fixes.length?wt(o.fixes[o.fixes.length-1].planned_fob,o):"—";
  const steps=o.step_climbs.length?o.step_climbs.map(([f,l])=>`${f} ${fl(l)}`).join(" · "):"none";
  const r={
    route:["Route",`${o.origin} → ${o.dest}`],altn:["ALTN",o.altn||"—"],ci:["CI",o.cost_index],
    crz:["CRZ",fl(o.initial_fl)],steps:["Step climbs",steps],block:["Block fuel",wt(o.block_fuel,o)],
    trip:["Trip fuel",wt(o.trip_fuel,o)],fres:["Final reserve",wt(o.final_reserve,o)],
    zfw:["ZFW",wt(o.zfw,o)],tow:["TOW",wt(o.tow,o)],ldw:["LDW",wt(o.ldw,o)],
    deprwy:["Dep RWY",o.origin_rwy||"—"],sid:["SID",o.sid||"—"],
    arrrwy:["Arr RWY",o.dest_rwy||"—"],star:["STAR",o.star||"—"],destfob:["Plan FOB at dest",destFob]};
  const by={
    plan:["route","altn","ci","crz","block","trip","zfw","tow"],dark:["route","altn","deprwy"],
    prep:["ci","crz","zfw","block","tow","deprwy"],clr:["deprwy","sid","crz"],
    push:["block","deprwy"],taxi:["deprwy","sid","tow"],tkof:["deprwy","tow"],
    clb:["crz","steps"],crz:["crz","steps","star","arrrwy","trip"],des:["star","arrrwy","ldw"],
    appr:["arrrwy","ldw"],land:["arrrwy","destfob"],park:["destfob","fres","trip"]};
  return by[pid].map(k=>r[k]);
}
```

- [ ] **Step 4: Render the rail from the OFP, with the example as fallback**

Change the rail tag CSS label to come from data. Replace the rail block in `renderPhase` with:

```js
$("#railBox").innerHTML=renderRail(p);
```

and add:

```js
function renderRail(p){
  const o=state.ofp;
  if(o){
    const when=new Date(o.generated_at).toISOString().slice(0,16).replace("T"," ")+"Z";
    const rows=ofpRows(p.id,o);
    const refresh=state.bridge.connected?`<button class="rail-refresh" id="ofpRefresh">↻ REFRESH OFP</button>`:"";
    return `<div class="rail"><div class="rail-tag">YOUR OFP</div><div class="rail-route">${esc(o.origin)} → ${esc(o.dest)}</div>
      <table>${rows.map(r=>`<tr><td>${esc(r[0])}</td><td>${esc(r[1])}</td></tr>`).join("")}</table>
      <div class="rl-note">SimBrief OFP · generated ${esc(when)}${o.airac?` · AIRAC ${esc(o.airac)}`:""}</div>${refresh}</div>`;
  }
  const rail=p.rail;
  return rail?`<div class="rail"><div class="rail-tag">EXAMPLE</div><div class="rail-route">KRDU → KATL</div>
    <table>${rail.rows.map(r=>`<tr><td>${r[0]}</td><td>${r[1]}</td></tr>`).join("")}</table>
    <div class="rl-note">${rail.note}</div></div>`:"";
}
```

CSS:

```css
.rail-refresh{margin-top:10px;width:100%;background:none;border:1px solid #3a3423;color:var(--amb);border-radius:4px;padding:6px 0;font-size:11.5px;letter-spacing:.08em}
.rail-refresh:hover{border-color:var(--amb)}
```

After setting `#railBox`, bind the button:

```js
const rb=$("#ofpRefresh");if(rb)rb.addEventListener("click",()=>send({type:"ofp_refresh"}));
```

- [ ] **Step 5: WebSocket client with reconnect**

Before `load();render();` add:

```js
/* Opened from file:// there is no bridge to talk to; the page runs standalone. */
let ws=null,retryMs=2000;
function send(msg){if(ws&&ws.readyState===WebSocket.OPEN)ws.send(JSON.stringify(msg))}
function onBridgeMessage(m){
  if(m.type==="hello"){state.bridge.sources=m.sources}
  else if(m.type==="sources"){state.bridge.sources={sim:m.sim,mcdu:m.mcdu,ofp:m.ofp}}
  else if(m.type==="ofp"){state.ofp=m.data;state.bridge.sources.ofp=true}
  else return;
  render();
}
function connectBridge(){
  if(!location.protocol.startsWith("http"))return;
  ws=new WebSocket((location.protocol==="https:"?"wss://":"ws://")+location.host+"/ws");
  ws.addEventListener("open",()=>{retryMs=2000;state.bridge.connected=true;render()});
  ws.addEventListener("message",e=>{try{onBridgeMessage(JSON.parse(e.data))}catch(err){console.error("bad bridge message",err)}});
  ws.addEventListener("close",()=>{
    state.bridge.connected=false;render();
    setTimeout(connectBridge,retryMs);retryMs=Math.min(retryMs*2,30000);
  });
}
```

and after `render();` add `connectBridge();`.

On disconnect the OFP stays in `state.ofp` so the rail keeps showing it; only the pill and refresh button go away.

- [ ] **Step 6: Verify standalone mode still works**

Open `file:///Users/ismael/onna/a32nx-companion/index.html` in the browser pane. Check with `javascript_tool`:

```js
({pillHidden:document.getElementById("connPill").hidden,railTag:document.querySelector(".rail-tag").textContent,batc:!!document.querySelector(".batc")})
```

Expected: `{pillHidden:true, railTag:"EXAMPLE", batc:true}`; `read_console_messages` with `onlyErrors:true` is empty.

- [ ] **Step 7: Verify bridge mode against the fixture**

Set up a throwaway home so the bridge reads the fixture as its cache and the startup refresh fails harmlessly (fake user):

```bash
mkdir -p "$TMPDIR/companion-home/.a32nx-companion"
cp bridge/tests/fixtures/ofp_krdu_katl.json "$TMPDIR/companion-home/.a32nx-companion/ofp.json"
printf '[simbrief]\nusername = "zzz_nonexistent_user_q"\n[server]\nhost = "127.0.0.1"\nport = 8765\n' > "$TMPDIR/companion-home/config.toml"
```

Start it in the background:

```bash
cd bridge && HOME="$TMPDIR/companion-home" uv run python -m companion run --config "$TMPDIR/companion-home/config.toml"
```

The log shows `OFP refresh failed: SimBrief fetch failed (HTTP 400): Error: Unknown UserID`, and the server keeps running on the cached OFP. Open `http://127.0.0.1:8765/` in the browser pane and check:

```js
({pill:document.getElementById("connPill").textContent,railTag:document.querySelector(".rail-tag").textContent,route:document.querySelector(".rail-route").textContent,rows:[...document.querySelectorAll(".rail td:first-child")].map(td=>td.textContent)})
```

Expected: pill text contains `BRIDGE`, `SIM`, `OFP`, `MCDU`; `railTag` = `"YOUR OFP"`; `route` = `"KRDU → KATL"`; on PLAN `rows` = `["Route","ALTN","CI","CRZ","Block fuel","Trip fuel","ZFW","TOW"]`. Click NEXT PHASE through to PARK and confirm each rail renders rows with no console errors. Stop the server, confirm the pill disappears within a few seconds and the rail still shows the OFP. Take one screenshot of the PREP phase for the user.

- [ ] **Step 8: Commit**

```bash
git add index.html
git commit -m "Show the SimBrief OFP in the rail when the bridge is connected"
```

---

### Task 7: Capture the user's real OFP and check the mapping

This needs the user's SimBrief alias or user ID; the controller asks the user for it before dispatching. Skip the task (and say so in the final report) if the user does not provide one.

**Files:**
- Create: `bridge/tests/fixtures/ofp_real.json`
- Modify: `bridge/tests/test_simbrief_normalize.py`

- [ ] **Step 1: Capture**

```bash
curl -s 'https://www.simbrief.com/api/xml.fetcher.php?username=<ALIAS>&json=v2' -o bridge/tests/fixtures/ofp_real.json
```

Strip personal data before committing: run a short `python -I` script that keeps only the top-level keys `fetch, params, general, origin, destination, alternate, fuel, weights, navlog`, deletes `fetch.userid`, `general.dx_rmk`, `general.sys_rmk`, and inside `params` keeps only `units, airac, time_generated`.

- [ ] **Step 2: Add a test**

```python
REAL = Path(__file__).parent / "fixtures" / "ofp_real.json"


def test_real_ofp_normalizes() -> None:
    ofp = normalize(json.loads(REAL.read_text()))
    assert len(ofp.origin) == 4 and len(ofp.dest) == 4
    assert ofp.fixes and ofp.fixes[-1].stage == "DES"
    assert ofp.block_fuel > ofp.trip_fuel > 0
```

- [ ] **Step 3: Run, fix mapping if it fails, commit**

Run: `cd bridge && uv run pytest tests/test_simbrief_normalize.py -v`. Any failure means a field path in `_normalize` differs from the live API: fix it there (and only there), rerun the whole suite.

```bash
git add bridge/tests/fixtures/ofp_real.json bridge/tests/test_simbrief_normalize.py bridge/companion/simbrief.py
git commit -m "Check OFP normalization against a real SimBrief response"
```
