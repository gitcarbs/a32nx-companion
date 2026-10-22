# M2: SimBridge MCDU Spike — Design

Status: approved 2026-10-21 · Spec: `spec.md` §7, §10 (M2)

## Goal

Decide go/no-go on reading the A32NX MCDU screen through SimBridge, proven against a capture from the user's own sim, and leave behind the parser that M5 will build on.

The user runs SimBridge on every flight, so the verdict rests on the protocol alone (spec open question 2 is answered "yes").

## What the source already tells us

Read from `flybywiresim/simbridge` (`apps/server/src/interfaces/mcdu.gateway.ts`, `apps/mcdu/src/`) and `flybywiresim/aircraft` (`fbw-a32nx/src/systems/instruments/src/MCDU/legacy/A320_Neo_CDU_MainDisplay.ts`):

- Endpoint `ws://<host>:8380/interfaces/v1/mcdu`. Text frames only.
- SimBridge is a broadcast relay: every frame from any client goes to every client, including the sender.
- Aircraft → all: `mcduConnected` when the sim joins; SimBridge sends `mcduDisconnected` when it leaves.
- Aircraft → all: `update:{"left":S,"right":S}`, where `S` has `title`, `titleLeft` (unused), `page` (`{small}1/3{end}` or `""`), `lines` (12 rows, alternating label/data, each `[left, right, center]`), `scratchpad`, `arrows` (`[up, down, left, right]`), plus brightness/annunciator fields. Both sides carry the same screen; an unpowered side is a blank screen.
- Any client → aircraft: `requestUpdate` makes the aircraft resend the screen. `event:<side>:<BUTTON>` **presses that MCDU key in the sim**.
- `print:{...}` frames are printer output; ignore.
- Cell text uses inline markup: `{big} {small} {amber} {red} {green} {cyan} {white} {magenta} {yellow} {inop} {sp} {left} {right} {end}`.
- `sendUpdate()` runs on every `setLine`/`setLabel`, so one page draw produces a burst of ~25 full frames.
- No page identifier is sent. Titles are generic: INIT A is `INIT`, INIT B is `INIT FUEL PRED`, F-PLN's title row is `FROM … <flight number>`.
- Requires flyPad EFB → Settings → SimBridge set to Auto or On.
- Risk: this is the "legacy" MCDU; a source comment mentions an upcoming "MCDU split" that could change the format.

## Scope

In: a passive capture tool, a pure parser/classifier, tests, `docs/simbridge-mcdu.md` with the verdict.

Out: wiring MCDU into `run`, the page, State or the `sources/` layer (M3/M5); field extraction beyond the three proof fields.

## Components

### `companion/mcdu_capture.py`

- CLI: `python -m companion mcdu-capture OUT.jsonl [--url ws://localhost:8380/interfaces/v1/mcdu]`.
- aiohttp WebSocket client; no new dependencies.
- Passive: the only frame it can send is the constant `requestUpdate`, through a single parameterless function. Sent once on connect and again on each `mcduConnected`.
- Writes one JSON object per received frame: `{"t": <float seconds since capture start, monotonic>, "raw": "<frame verbatim>"}`. Flushes each line so a crash loses nothing.
- Feeds frames through `Settler` + `classify` and prints one line per settled screen, e.g. `12.4s  INIT_A  ci=25 crz_fl=350`.
- If the connection fails or drops, logs it and retries every 2 s. Ctrl+C exits cleanly with the file closed.

### `companion/mcdu.py`

Pure functions and dataclasses, no I/O.

- `parse_frame(raw: str) -> Frame | None` — `Update(left: McduScreen, right: McduScreen)`, `Connected`, `Disconnected`; `None` for anything else (`event:`, `print:`, `requestUpdate` echoes, malformed JSON).
- `parse_markup(cell: str) -> tuple[Span, ...]` — `Span(text, color, size)`. Tags push onto a stack, `{end}` pops, `{sp}` is a space, unknown tags are dropped. Default color `white`; default size `big` for data rows, `small` for label rows (passed in by the caller).
- `McduScreen` — `title: tuple[Span, ...]`, `page: str` (e.g. `1/3`), `labels: tuple[Row, ...]` (6), `lines: tuple[Row, ...]` (6), `scratchpad: str`, plus `text` helpers. `Row` holds `left`, `right`, `center` span tuples. A screen whose rows and title are all empty is `blank`.
- `screen_of(update) -> McduScreen | None` — left side, else right if left is blank, else `None`.
- `Settler(quiet_s=0.15)` — `push(t, screen)` and `poll(t)`; returns a screen once `quiet_s` has passed (by frame `t`) with no newer frame, and only if it differs from the last emitted screen. Never reads the wall clock.
- `classify(screen) -> PageId | None` — `INIT_A`, `INIT_B`, `FPLN`, `PERF_TO`, `PERF_APPR`. Matches title text plus label signatures (e.g. INIT A: title `INIT` and a `FROM/TO` label; INIT B: title contains `FUEL PRED` and a `ZFW/ZFWCG` label). Signatures are first written from FBW source and then confirmed or corrected against the capture.
- Proof fields: `init_a_fields(screen) -> {"ci": int | None, "crz_fl": int | None}`, `init_b_fields(screen) -> {"zfw": float | None}`. Placeholder boxes/dashes give `None`.

### `docs/simbridge-mcdu.md`

Endpoint and frame schema, markup table, page signatures, observed burst sizes and frame rates from the capture, flyPad setting, the `event:` safety rule, risks, go/no-go and what M5 should build on.

## Error handling

- Malformed or unknown frames are skipped, never raised; the capture still records them raw.
- Capture never exits on connection errors; it retries until Ctrl+C.
- Parser tolerates short `lines` arrays and missing keys (treated as empty).

## Testing

Before the capture:

- `test_mcdu_markup.py`: plain text, colors, nested tags, `{sp}`, unknown tags, unterminated tags.
- `test_mcdu_frames.py`: `update:` parsing, side fallback, connected/disconnected, ignored frames.
- `test_mcdu_settler.py`: a burst collapses to one screen; identical repeat is suppressed; timing uses `t` only.
- `test_mcdu_classify.py`: hand-built screens from the FBW templates for each page, plus an unknown page.
- `test_mcdu_capture.py`: a fake SimBridge (aiohttp WS server) relays scripted frames; asserts the client sent only `requestUpdate` (on connect and after `mcduConnected`) and wrote every frame to JSONL.

After the capture:

- Trim the user's capture to `tests/fixtures/mcdu_preflight.jsonl`.
- `test_mcdu_fixture.py`: replaying it through `Settler` + `classify` yields the visited page sequence, and the proof fields match the values entered. **Go = this test passes.**

## Workflow

1. Build capture tool, parser and pre-capture tests (WSL/macOS).
2. User pulls on Windows, starts MSFS + SimBridge, runs `mcdu-capture`, and visits INIT A → F-PLN → INIT B → PERF TO → PERF APPR, noting the CI, CRZ FL and ZFW entered.
3. User commits the `.jsonl` (or puts it where it can be read).
4. Build the fixture test, tune signatures, write `docs/simbridge-mcdu.md` with the verdict.
