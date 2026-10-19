# A32NX Companion — Instructor Mode Spec

Status: draft · Owner: Ismael · Repo: `gitcarbs/a32nx-companion`

## 1. Context

`index.html` today is a static, single-file flight companion for the FlyByWire A32NX in MSFS 2024: 13 phases (PLAN → PARK & SECURE), each with flows (checkbox steps tagged by panel), an ECAM-style checklist tab, a BeyondATC card and a hard-coded worked-example rail (KRDU → KATL). Progress lives in `localStorage`.

This spec turns it into a **simulator flight instructor**: a local Python bridge reads aircraft state, the SimBrief OFP and (optionally) the MCDU screen, and pushes **nudges** (something is due and not done) and **corrections** (something is wrong) to the page.

### Decisions already made

| Decision | Rationale |
|---|---|
| Instructor, **not auto-check**. The pilot ticks steps; the bridge never ticks them. | The page is a learning tool. Auto-ticking removes the check. |
| **No audio.** Visual cues only. | User preference. |
| **No radio/ATC coaching from the bridge.** The page keeps its BeyondATC cards as static reference. | User is a licensed pilot; the cards stay as a reminder of BATC's workflow. |
| **SimBrief-aware.** OFP drives the rail and the cross-checks. | Replaces hard-coded example numbers with the actual flight. |
| **FMC help is a primary goal.** | The gap is FMGS/automation, not airmanship. |
| **External Python bridge** over SimConnect, not an in-sim toolbar panel. | Python, normal tooling, offline replay testing; page runs on any screen. |

### Non-goals

Audio/TTS · bridge-generated ATC/radio cues · auto-ticking steps · writing to the aircraft or MCDU (no H:events, no key injection) · aircraft other than the A32NX · duplicating ECAM warnings the jet already gives (T.O CONFIG, gear not down, etc.).

## 2. Architecture

```
MSFS 2024 + FBW A32NX                (Windows PC)
  │ SimConnect: A: simvars, L:A32NX_* vars @ 4 Hz
  │ SimBridge WS :8380 (MCDU screen) — optional, gated by M2
  ▼
bridge (Python 3.12, asyncio)        (same Windows PC)
  ├─ sources/   simconnect · simbridge · replay
  ├─ state.py   normalized State + derived signals
  ├─ phase.py   page-phase detector
  ├─ simbrief.py OFP fetch + normalize
  ├─ rules/     nudges + corrections (Python)
  ├─ engine.py  timing, grace, cooldown, inhibition
  ├─ recorder   State → JSONL
  └─ server.py  aiohttp: serves index.html + WebSocket /ws
  │ WebSocket JSON (LAN)
  ▼
index.html                           (any browser: Mac, tablet, 2nd monitor)
```

**Platform constraint:** SimConnect is Windows-only. Development happens on a Mac. Therefore the `replay` source is a first-class source, not a test afterthought: everything above `sources/` must run on macOS against recorded JSONL. Only `sources/simconnect.py` needs Windows.

### Repo layout

```
index.html
config.example.toml
bridge/
  pyproject.toml
  companion/
    __main__.py        # CLI: run | record | replay
    server.py
    config.py
    state.py
    phase.py
    simbrief.py
    engine.py
    debrief.py
    sources/{base,simconnect,simbridge,replay}.py
    vars/a32nx.toml    # normalized name → simvar/L:var mapping
    rules/{__init__,ofp_checks,preflight,takeoff,climb_cruise,descent_approach,automation,park}.py
  tests/
    fixtures/*.jsonl   # recorded flights
    test_phase.py
    test_engine.py
    test_rules_*.py
```

### Config (`config.toml`)

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

## 3. Page changes (`index.html`)

1. **Stable step IDs.** Every flow step and checklist item gets an explicit `id` (e.g. `appr.config.flaps1`). Progress keys and rules use IDs, never array indices. Bump storage key to `a32nx-companion.v2`; drop v1 data.
2. **Profile height into phase data.** Remove the `PROFY` array; add `y` to each phase object.
3. **Keep the BeyondATC cards** (`batc` field and its rendering) unchanged.
4. **Content fixes:**
   - Taxi flow: add `GND SPLRS — ARM` (currently never armed; takeoff phase disarms them). The push after-start step that said "GND SPLRS — leave for taxi flow · FLAPS — set" becomes a flaps-only step (`push.after.flaps`).
   - Push & start: the "stabilized ~68% N2" figure matches the FBW beginner guide (ISA sea level) and stays; cite FBW in the step note. The Airbus FCOM figure for the real LEAP-1A is ~58.5%.
5. **Rail from OFP.** Rail rows become a function of the normalized OFP (§5). Keep the static KRDU → KATL data as the fallback when no OFP is loaded, labeled "EXAMPLE".
6. **Instructor UI** (only rendered when the bridge is connected):
   - Connection pill in header: `BRIDGE ● SIM ● OFP ● MCDU` (each green/grey).
   - **Cue feed** above the phase card: active cues, newest first, colour by severity (nudge = cyan, caution = amber, warning = red). Each cue shows text + optional "why" line + "→ step" link that scrolls to and highlights the step.
   - **Step markers:** a step referenced by an active cue gets a left-border highlight. Checkbox state is untouched.
   - **Auto-follow phase:** when the bridge reports a phase change, the page moves to it unless the user navigated manually in the last 60 s. A "FOLLOW SIM" toggle in the header controls this.
   - **Coach panel** (M5): replaces the rail while an MCDU page is recognised (§7).
   - **Debrief view** (M6): after PARK & SECURE, a table of cues from this flight.
7. Page must remain fully usable with no bridge (current behaviour).

## 4. Bridge ↔ page protocol

WebSocket at `/ws`, JSON messages, one object per frame.

Bridge → page:

```jsonc
{"type":"hello","version":1,"sources":{"sim":true,"mcdu":false,"ofp":true}}
{"type":"ofp","data":{ /* normalized OFP, §5 */ }}
{"type":"phase","phase":"taxi","fwc_phase":2,"reason":"gs>5kt, engines running"}
{"type":"state","t":1729.5,"s":{"ias":142,"alt":2350,"agl":1910,"gs":140,"fob":5210, "fma":{"lat":"NAV","vert":"SRS","thr":"MAN FLX"}}}  // 1 Hz, display subset only
{"type":"cue","id":"flaps1_green_dot","kind":"nudge","severity":"nudge","text":"Green dot. Flaps 1.","why":"Config schedule: F1 at green dot.","step":"appr.config.flaps1","phase":"appr","t":3021.0}
{"type":"cue_clear","id":"flaps1_green_dot","resolved_after_s":4.2}
{"type":"mcdu","side":"L","page":"INIT B","lines":[...],"scratchpad":""}   // M5
{"type":"sources","sim":false,"mcdu":false,"ofp":true}                       // on change
```

Page → bridge:

```jsonc
{"type":"follow","enabled":false}
{"type":"phase_override","phase":"clr"}     // pilot forces a phase
{"type":"dismiss","id":"flaps1_green_dot"}  // hide cue; engine treats as acknowledged
{"type":"ofp_refresh"}
```

Phase IDs are the existing page IDs: `plan dark prep clr push taxi tkof clb crz des appr land park`.

## 5. SimBrief

- Endpoint: `https://www.simbrief.com/api/xml.fetcher.php?username={alias}&json=v2` (or `userid=`). HTTP 400 on bad user.
- Fetched by the bridge at startup and on `ofp_refresh`. Cached to `~/.a32nx-companion/ofp.json`.
- **CORS (verified 2026-10-18):** the endpoint sends `access-control-allow-origin: *`, so the page may fetch directly in no-bridge mode later. M1 keeps OFP bridge-only so the normalization lives in one place (Python).
- **v2 shape (checked against a published v2 response):** `navlog` and `alternate` are arrays; numbers arrive as strings; `params.units` is `kgs`/`lbs`; navlog `stage` is `CLB`/`CRZ`/`DSC`; `params.time_generated` may be ISO-8601 or a unix timestamp string.
- Normalize to a stable internal shape so rules never touch raw SimBrief keys. Field paths below are expected but **must be checked against a real `json=v2` response** and the mapping kept in one function:

```python
@dataclass
class Ofp:
    origin: str; origin_rwy: str | None
    dest: str; dest_rwy: str | None; dest_lat: float; dest_lon: float
    altn: str | None
    route: str; sid: str | None; star: str | None
    cost_index: int; initial_fl: int; step_climbs: list[tuple[str,int]]
    units: Literal["kg","lb"]
    block_fuel: float; trip_fuel: float; final_reserve: float; altn_fuel: float
    zfw: float; tow: float; ldw: float
    fixes: list[Fix]          # ident, lat, lon, alt_ft, stage (CLB/CRZ/DES), planned_fob, is_sid_star
    airac: str | None
    generated_at: datetime
```

- ZFWCG generally isn't in the OFP; take it from flyPad/sim, not SimBrief.
- Stale-OFP guard: if `origin` ≠ nearest airport to aircraft position at power-up, emit a caution "Loaded OFP is for {origin}, you're at {icao}."

## 6. Aircraft state

### 6.1 Variable mapping (`vars/a32nx.toml`)

Rules read normalized names only. The mapping file is the single place that knows SimConnect names, and is versioned against FBW Stable/Dev.

```toml
[meta]
fbw_version = "stable-x.y.z"     # fill in when verified

[vars.on_ground]   sim = "SIM ON GROUND"            unit = "bool"
[vars.ias]         sim = "AIRSPEED INDICATED"       unit = "knots"
[vars.gs]          sim = "GROUND VELOCITY"          unit = "knots"
[vars.alt]         sim = "INDICATED ALTITUDE"       unit = "feet"
[vars.agl]         sim = "PLANE ALT ABOVE GROUND"   unit = "feet"
[vars.vs]          sim = "VERTICAL SPEED"           unit = "feet per minute"
[vars.hdg_true]    sim = "PLANE HEADING DEGREES TRUE" unit = "degrees"
[vars.lat]         sim = "PLANE LATITUDE"           unit = "degrees"
[vars.lon]         sim = "PLANE LONGITUDE"          unit = "degrees"
[vars.fob]         sim = "FUEL TOTAL QUANTITY WEIGHT" unit = "kilograms"
[vars.gross_wt]    sim = "TOTAL WEIGHT"             unit = "kilograms"
[vars.beacon]      sim = "LIGHT BEACON"             unit = "bool"
[vars.gear_handle] sim = "GEAR HANDLE POSITION"     unit = "bool"
[vars.flaps_idx]   sim = "FLAPS HANDLE INDEX"       unit = "number"
[vars.eng1_n2]     sim = "TURB ENG N2:1"            unit = "percent"
[vars.eng2_n2]     sim = "TURB ENG N2:2"            unit = "percent"
[vars.xpdr_code]   sim = "TRANSPONDER CODE:1"       unit = "bco16"
# --- L:vars: names below are CANDIDATES, verify each against FBW docs/source ---
[vars.fwc_phase]   sim = "L:A32NX_FWC_FLIGHT_PHASE" unit = "enum"   # confirmed in FBW docs
[vars.fmgc_phase]  sim = "L:A32NX_FMGC_FLIGHT_PHASE" unit = "enum"  # verify
[vars.fma_lat]     sim = "L:A32NX_FMA_LATERAL_MODE" unit = "enum"   # verify, + enum table
[vars.fma_vert]    sim = "L:A32NX_FMA_VERTICAL_MODE" unit = "enum"  # verify, + enum table
[vars.v1]          sim = "L:AIRLINER_V1_SPEED"      unit = "knots"  # verify
[vars.vr]          sim = "L:AIRLINER_VR_SPEED"      unit = "knots"  # verify
[vars.v2]          sim = "L:AIRLINER_V2_SPEED"      unit = "knots"  # verify
[vars.flex]        sim = "L:AIRLINER_TO_FLEX_TEMP"  unit = "celsius"# verify
[vars.green_dot]   sim = "L:A32NX_SPEEDS_GD"        unit = "knots"  # verify
[vars.vapp]        sim = "L:A32NX_SPEEDS_VAPP"      unit = "knots"  # verify
[vars.vdev]        sim = "?"                        unit = "feet"   # find
[vars.spoilers_armed] sim = "?"                     unit = "bool"   # find
[vars.baro_std]    sim = "?"                        unit = "bool"   # find (FBW FCU)
[vars.adirs_knob_1] sim = "?"                       unit = "enum"   # find
[vars.ci]          sim = "?"                        unit = "number" # find, else MCDU screen
[vars.crz_fl]      sim = "?"                        unit = "number" # find, else MCDU screen
[vars.zfw_fmgc]    sim = "?"                        unit = "kg"     # find, else MCDU screen
```

Unresolved (`?`) vars make their dependent rules inactive, logged once at startup. They do not crash the bridge.

**Verify early (M3 day 1):** that plain `L:` names work in `AddToDataDefinition` on MSFS 2024 with the Python SimConnect library. Fallback: MobiFlight WASM module.

### 6.2 State

`State` is a frozen dataclass of normalized values plus derived signals computed in `state.py`, never inside rules:

- `any_engine_running` (N2 > 50 on either)
- `both_engines_stable`
- `decelerating` (IAS trend over 5 s < −0.5 kt/s)
- `dist_to_dest_nm` (from OFP dest coords)
- `on_runway_heading_of` (origin runway whose heading is within 10° and threshold within 0.5 nm, using a small runway table or OFP data)
- `time_in_phase_s`, `time_since(event)` helpers via a small history buffer (last ~120 s)

### 6.3 Recorder / replay

- `python -m companion record out.jsonl` writes one State per tick (4 Hz) with monotonic `t`.
- `python -m companion replay in.jsonl --speed 10` feeds the same pipeline. The page can't tell the difference.
- Every bug found in flight gets a fixture trimmed from a recording and a test.

## 7. MCDU via SimBridge (gated)

SimBridge serves the remote MCDU on `:8380` and streams screen content over a WebSocket on the same port. The message format is **not documented**; it lives in the SimBridge/A32NX source.

**M2 is a time-boxed spike (½ day)** with a written go/no-go:

1. Connect a Python client to SimBridge's WS as an additional MCDU display client.
2. Dump messages while visiting INIT A, INIT B, F-PLN, PERF TO, PERF APPR.
3. Determine: page title extractable? Line text + colour/size markup parseable? Updates on every change? Does an extra client disturb the real remote MCDU?
4. Write `docs/simbridge-mcdu.md` with the observed schema and a recommendation.

If **go**: `sources/simbridge.py` emits `McduScreen(side, page, lines, scratchpad)`; `state` gains `mcdu_page` and parsed fields (`init_a.ci`, `init_b.zfw`, `fpln.legs[...]`, `perf_appr.qnh`, …) that back-fill the `?` vars in §6.1.

If **no-go**: FMC help is phase-based only (§8.4 without page awareness), and the screen-only checks in §8.2 are dropped.

Known limitation even on go: only the **displayed** page is visible. F-PLN checks only run while F-PLN is on screen; cache the last seen F-PLN with a timestamp.

## 8. Rules

### 8.1 Rule model

Rules are Python, not a YAML DSL. No expression language to build or debug.

```python
@dataclass(frozen=True)
class Rule:
    id: str
    kind: Literal["nudge", "correction"]
    severity: Literal["nudge", "caution", "warning"]
    phases: frozenset[str]                 # page phases where the rule is evaluated
    when: Callable[[State, Ofp | None], bool]    # rule is due
    expect: Callable[[State, Ofp | None], bool]  # condition that satisfies it
    text: Callable[[State, Ofp | None], str] | str
    why: str = ""
    step: str | None = None                # page step ID
    grace_s: float = 5.0
    cooldown_s: float = 120.0
    once: bool = True                      # at most one emission per flight
    needs: frozenset[str] = frozenset()    # normalized vars required; rule disabled if any unresolved
```

### 8.2 Engine semantics (`engine.py`)

Per tick, for each enabled rule whose `phases` contains the current phase:

1. If `not when` or `expect` → clear any pending timer; if the cue is active, emit `cue_clear` with `resolved_after_s`.
2. Else start/continue the due timer. When `now − due_since ≥ grace_s` and the rule may speak (not `once`-spent, outside cooldown, not dismissed) → emit `cue`.
3. **Inhibition**, modelled on the Airbus FWC: during `fwc_phase` 3–5 (takeoff roll to liftoff) and 7–9 (final below ~800 ft to 80 kt rollout) only `severity == "warning"` cues are emitted. Others are queued and re-evaluated when inhibition ends; drop any whose `when` is no longer true.
4. Max 3 active cues visible; overflow is queued by severity then age.

All timing uses State `t`, never wall clock, so replay at 10× behaves identically.

### 8.3 Phase detector (`phase.py`)

Inputs: `fwc_phase`, `fmgc_phase` (if resolved), ground state, engines, GS, altitude/VS, OFP. Hysteresis: a candidate phase must hold for 3 s. Pilot `phase_override` wins until the detector's candidate moves past it.

| Page phase | Enter when |
|---|---|
| plan | no electrical power, or OFP loaded and on ground cold & dark |
| dark | batteries on (`fwc_phase` ≥ 1) |
| prep | ADIRS in NAV |
| clr | squawk ≠ 2000/1200/7000 *or* pilot override (weak signal — prep/clr may stay manual) |
| push | pushback active or first engine start (`fwc_phase` = 2) |
| taxi | engines running, GS > 5 kt, not on runway |
| tkof | `fwc_phase` 3 |
| clb | airborne and `fmgc_phase` = climb (fallback: AGL > 1 500, VS > +500) |
| crz | `fmgc_phase` = cruise (fallback: within 500 ft of OFP initial FL, \|VS\| < 300 for 60 s) |
| des | `fmgc_phase` = descent (fallback: past TOD/VS < −500 for 30 s) |
| appr | `fmgc_phase` = approach, or LOC/G/S armed |
| land | `fwc_phase` 8 |
| park | `fwc_phase` 10, or GS 0 + park brake + engines off |

### 8.4 Initial rule set

IDs are suggestions. `[OFP]` needs SimBrief; `[MCDU]` needs the M2 go.

**OFP ↔ aircraft/FMC cross-checks (`ofp_checks.py`)**

| id | phase | when → expect | sev |
|---|---|---|---|
| ofp_stale | dark | power up → OFP origin == nearest airport | caution |
| block_fuel_loaded | push | first engine start → \|fob − ofp.block_fuel\| ≤ 100 kg | caution |
| ci_matches | prep..taxi | CI available → == ofp.cost_index `[MCDU or var]` | nudge |
| crz_fl_matches | prep..taxi | CRZ FL available → == ofp.initial_fl | nudge |
| zfw_matches | prep..taxi | FMGC ZFW available → within 300 kg of sim ZFW (gross − fob) | caution |
| vspeeds_entered | taxi | moving → v1, vr, v2 > 0 | caution |
| wrong_runway | taxi→tkof | aligned with a runway → runway == FMC/OFP departure runway (speak before thrust) | warning |
| fuel_vs_plan | clb..des | passing each OFP fix → show Δ vs planned FOB; caution if trend projects FOB at dest < final_reserve + altn | nudge/caution |
| arrival_loaded | crz | dist_to_dest ≤ 150 nm → arrival/approach in F-PLN `[MCDU]` / PERF APPR filled | nudge |
| fpln_discont | any airborne | F-PLN shown with discontinuity within next 3 legs `[MCDU]` | caution |

**Procedural nudges**

| id | phase | when → expect | step |
|---|---|---|---|
| adirs_after_power | dark | batteries on 120 s → ADIRS NAV | dark.power.adirs |
| apu_bleed_off_after_start | push | both engines stable 60 s → APU bleed off | push.after.apu_bleed |
| eng_mode_norm | push | both stable 30 s → ENG MODE NORM | push.start.mode_norm |
| spoilers_armed_taxi | taxi | taxiing 60 s → spoilers armed | taxi.during.spoilers |
| to_flaps_set | taxi | taxiing 60 s → flaps idx == PERF TO conf | push.after.flaps |
| thr_red_clb | tkof/clb | AGL > THR RED + 200 and FMA thr shows LVR CLB → levers in CL | tkof.climb.thr_red |
| baro_std_climb | clb | alt > transition alt + 500, 30 s → baro STD | clb.trans.baro |
| baro_qnh_desc | des | alt < transition level − 500, 30 s → baro QNH | des.trans.baro |
| ldg_lts_10k | clb/des | crossing `sop.landing_lights_off_ft` → lights per SOP | clb.10k.lights / des.10k.lights |
| flaps1_green_dot | appr | IAS ≤ green_dot + 3 and decelerating → flaps ≥ 1 | appr.config.flaps1 |
| flaps2_s_speed | appr | IAS ≤ S + 3 and flaps 1 → flaps ≥ 2 | appr.config.flaps2 |
| gear_gs_alive | appr | G/S within 1 dot (or AGL < 2 500 on ILS) → gear down | appr.config.gear |
| flaps_full_2000 | appr | AGL < 2 000 → flaps FULL (per SOP) | appr.config.full |
| beacon_off_parked | park | engines off 30 s → beacon off | park.shutdown.beacon |

**Corrections (`automation.py` and others)**

| id | phase | condition | sev |
|---|---|---|---|
| beacon_engines | any | engine running, beacon off, 10 s | caution |
| taxi_speed | taxi | GS > 30 kt (or > 10 kt in a turn > 30°) | caution |
| speed_250_below_10k | clb/des | IAS > 255 below 10 000 ft, 10 s | caution |
| open_clb_with_constraints | clb | FMA vert = OP CLB with altitude constraints ahead `[MCDU]` | nudge |
| appr_phase_not_active | appr | past decel point and FMGC phase ≠ approach | caution |
| high_on_profile | des | managed DES, VDEV > +500 ft for 30 s | nudge |
| loc_no_gs | appr | LOC captured, G/S not armed, ILS approach | caution |
| thr_not_in_cl | clb..appr | A/THR active, levers not in CL detent, 10 s | caution |
| **stable_gate_1000** | appr | at 1 000 ft AGL: not (gear down ∧ flaps FULL ∧ VAPP −5/+10 ∧ VS ≤ 1 000 fpm ∧ G/S ≤ 1 dot) | **warning**: "Unstable at 1 000 ft — go around" |
| rev_below_70 | land | reversers deployed below 60 kt | nudge |
| cooldown | park | engine master off < 120 s after landing touchdown + taxi | nudge |

Each rule ships with a test that uses a synthetic State sequence: due → grace → emit → resolve → clear; and an inhibition test for at least one rule.

### 8.5 FMC coach (M5, requires MCDU go)

When `mcdu_page` is recognised, the coach panel shows, for that page:

- What the page is for and what must already be done (e.g. PERF TO needs INIT B weights).
- **Expected values from the OFP**, with the LSK and the input format (`55.3/27.1 → 1R`).
- Live diffs: field on screen vs expected, coloured.
- The next page in the sequence `INIT A → F-PLN → INIT B → PERF TO` (preflight) and `F-PLN arrival → PERF APPR → RAD NAV` (pre-descent).

Content per page lives in `bridge/companion/coach/{init_a,init_b,fpln,perf_to,perf_appr,rad_nav}.py` and is the main effort of M5. Only pages that are needed for a normal flight; no SEC F-PLN, HOLD, etc. in the first version.

## 9. Debrief (M6)

- Every cue and its resolution is written to `~/.a32nx-companion/flights/{date}_{origin}-{dest}.jsonl`.
- Page debrief view: per-phase list of cues with `resolved_after_s` (or "never"), fuel vs plan chart (planned FOB vs actual per fix), and the stable-gate result.
- Cross-flight summary (later): counts per rule over the last N flights.

## 10. Milestones

| # | Scope | Done when |
|---|---|---|
| **M0** | Page cleanup (§3 items 1–4) | Step IDs everywhere; v2 storage; no `PROFY`; BATC cards unchanged; spoilers-arm step present. Page works with no bridge. |
| **M1** | Bridge skeleton + SimBrief | `python -m companion run` serves the page, `/ws` sends `hello` + `ofp`; rail shows the current OFP. Runs on macOS. |
| **M2** | SimBridge MCDU spike | `docs/simbridge-mcdu.md` with schema + go/no-go. |
| **M3** | SimConnect source, State, vars map, phase detector, recorder | Recorded JSONL of one full flight; phase detector produces the right sequence on replay; all `?` vars resolved or documented. |
| **M4** | Rule engine + §8.4 rules + cue UI | Replaying the M3 recording at 10× produces the expected cues; unit tests for engine and each rule; one real flight flown with it. |
| **M5** | FMC coach | INIT A/B, F-PLN, PERF TO, PERF APPR coached with OFP values (only if M2 = go). |
| **M6** | Debrief | Debrief view after park; flight log file written. |

Order is M0 → M1 → M2 → M3 → M4, then M5/M6. M0, M1, M2 can be done on the Mac; M2 needs the sim running on the PC.

## 11. Open questions

1. **FMC help emphasis**: data entry ("what goes where") or automation management ("what mode am I in, why isn't it doing what I expected")? Decides whether M5 coach or the `automation.py` corrections get more depth.
2. **SimBridge in the daily setup**: is running SimBridge every flight acceptable? If not, M5 is out regardless of M2.
3. **Units**: kg throughout, or follow OFP units?
4. **Network**: bridge on the Windows PC with the page on the Mac/tablet over LAN — confirm firewall/port 8765 is fine.
5. **SOP baseline**: which operator's SOP do the defaults follow (landing lights at 10 000 vs FL180, packs, single-engine taxi)?

## 12. Things to verify before relying on them

- Plain `L:` var reads via SimConnect `AddToDataDefinition` in MSFS 2024 from Python.
- Every `L:` name marked "verify" in §6.1 and the FMA enum tables.
- Whether `A32NX_FMGC_FLIGHT_PHASE` (or equivalent) exists.
- SimBrief `json=v2` field paths against the user's own OFP (capture a fixture).
- SimBridge MCDU WebSocket schema (M2).

## References

- FBW A32NX API: https://docs.flybywiresim.com/aircraft/a32nx/a32nx-api/
- FBW Systems API (FWC flight phase): https://docs.flybywiresim.com/aircraft/a32nx/a32nx-api/a32nx-systems-api/
- flyPad checklists (prior art, autofill): https://docs.flybywiresim.com/aircraft/common/flypados3/checklists/
- SimBridge remote displays architecture: https://docs.flybywiresim.com/tools/simbridge/simbridge-feature-guides/remote-displays/architecture/
- SimBrief API: https://developers.navigraph.com/docs/simbrief/fetching-ofp-data
- SimConnect AddToDataDefinition (MSFS 2024): https://docs.flightsimulator.com/msfs2024/flighting/programming-apis/simconnect/api-reference/events-and-data/simconnect_addtodatadefinition/index.md
