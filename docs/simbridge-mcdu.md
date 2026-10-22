# SimBridge MCDU: findings and verdict (M2)

Date: 2026-10-21 · Spike for `spec.md` §7 · Code: `bridge/companion/mcdu.py`, `bridge/companion/mcdu_capture.py`

**Verdict: GO.** SimBridge relays the full MCDU screen as JSON text that the bridge can read passively. Titles, line text, colour and size come through intact, and a real five-minute capture from the user's sim parses, settles and classifies correctly (`tests/test_mcdu_fixture.py`). Details and caveats below.

## 1. Setup

- flyPad EFB → Settings → SimBridge: **Auto** or **On**. SimBridge running on the sim PC.
- Endpoint: `ws://<sim-pc>:8380/interfaces/v1/mcdu`. No auth; CORS `*`.
- Capture: `uv run python -m companion mcdu-capture OUT.jsonl [--url …]` (from `bridge/`).
- **WSL2 (NAT) to Windows:** use the Windows host IP (`ip route show default | awk '{print $3}'`) in `--url`. Windows Firewall needs an inbound allow on TCP 8380 for `172.16.0.0/12`, and any **Block** rules for `fbw-simbridge.exe` (created when the first-run firewall prompt is dismissed) must be disabled; block beats allow. Mirrored networking was not available on this machine.

## 2. Frame schema

SimBridge (`apps/server/src/interfaces/mcdu.gateway.ts`) is a broadcast relay: every text frame from any client goes to every client, **including the sender**.

| Frame | From | Meaning |
|---|---|---|
| `mcduConnected` | aircraft | Sim joined; clients should `requestUpdate`. |
| `mcduDisconnected` | SimBridge | Sim socket closed. |
| `update:{"left":S,"right":S}` | aircraft | Full screen for both MCDUs. |
| `requestUpdate` | any client | Aircraft resends `update:`. Echoed back to the sender. |
| `event:<left\|right>:<BUTTON>` | any client | **Presses that MCDU key in the sim.** |
| `print:{"lines":[…]}` | aircraft | Printer output. |

`S` keys seen: `title`, `titleLeft` (always `""`), `page` (`{small}1/2{end}` or `""`), `lines`, `scratchpad`, `arrows` (`[up, down, left, right]`), `integralBrightness`, `displayBrightness`, `annunciators` (`fmgc fail mcdu_menu fm1 ind rdy blank fm2`). `lines` is 12 rows alternating label/data, each `[left, right, center]` (FBW stable sends 3 cells; the source allows 4). Unpowered side: empty strings.

Real frame, trimmed to two rows:

```json
{"left": {
  "title": "{white}{sp}{sp}{sp}{sp}{sp}{sp}{sp}{sp}{sp}{sp}{white}INIT{end}{sp}{sp}{sp}{sp}{sp}{sp}{sp}{sp}{sp}{sp}{small}{end}{big}{end}{end}",
  "titleLeft": "", "page": "",
  "lines": [
    ["{white}{sp}{white}CO{sp}RTE{end}{sp}{sp}{sp}{sp}{sp}{sp}{sp}{sp}{white}FROM/TO{end}{sp}{sp}{small}{end}{big}{end}{end}", "", ""],
    ["{white}{amber}__________{end}{sp}{sp}{sp}{sp}{sp}{amber}____{end}{amber}/____{end}{small}{end}{big}{end}{end}", "", ""]
  ],
  "scratchpad": "{white}GPS PRIMARY{end}",
  "arrows": [false, false, false, false],
  "integralBrightness": 0.22, "displayBrightness": 0.15,
  "annunciators": {"fmgc": false, "fail": false, "mcdu_menu": false, "fm1": false, "ind": false, "rdy": false, "blank": false, "fm2": false}},
 "right": "…same shape…"}
```

## 3. Markup

Tags push a style, `{end}` pops it: `{white} {amber} {red} {green} {cyan} {magenta} {yellow} {inop}` (colour), `{big} {small}` (size), `{left} {right}` (alignment, ignored), `{sp}` (one space). `\xa0` is also a space. Rows end with a `{small}{end}{big}{end}` no-op.

Two cell styles:
- **`FormatTemplate` pages** (INIT, FUEL PRED, F-PLN): the whole 24-char row in cell 0, columns positioned with `{sp}`.
- **Legacy pages** (PERF, DATA, menus): short strings per cell, `\xa0` for spacing, `[color]x` suffixes already converted to tags by the aircraft.

`parse_markup` handles both; `Row.text` gives the row as plain text with spacing preserved.

## 4. Page identification

No page id is sent, and titles are generic, so `classify` uses the title plus label rows:

| PageId | Rule | Real title seen |
|---|---|---|
| `INIT_A` | title has word `INIT` and a label has `FROM/TO` | `INIT` |
| `INIT_B` | title has `INIT` or `FUEL PRED`, and a label has `ZFW/ZFWCG` | `FUEL PRED` (FBW stable; source on master says `INIT FUEL PRED`) |
| `FPLN` | title starts with `FROM` | `FROM … AAL580` |
| `PERF_TO` | title contains `TAKE OFF` | `TAKE OFF RWY` |
| `PERF_APPR` | title has word `APPR` and a label has `QNH` | not captured; rule from source |

Unclassified in the capture, as intended: `DATA INDEX`, `SEC INDEX`, `MCDU MENU`, `ATSU DATALINK`, `AOC MENU`, `AOC INIT/REVIEW`, `ATC MENU`, and PROG (title is the flight phase: `TO`, `TO 15`).

Proof fields read from the real capture: INIT A `ci=10`, `crz_fl=160` after a SimBrief INIT uplink; INIT B `zfw=None` while the field showed `___._/__._` (a `65/65` entry was rejected with `ENTRY OUT OF RANGE`).

## 5. Measured (capture: 173 frames, 301 s, FBW stable, MSFS 2024)

- Frame size: ~4 KB (median 3 975 B, max 4 223 B).
- **Periodic resend:** 91 of 173 frames were byte-identical to the previous one, mostly ~3 s apart, with nothing changing on screen.
- Bursts: median 1 frame per change; max 9 frames within 150 ms (page change during an uplink). `setTemplate` sends once per page draw.
- Scratchpad typing sends one frame per keystroke (`6`, `65`, `65/`, …).
- `left` and `right` were identical in all 172 `update:` frames.
- Latency was not measured; frames arrived within the same second as the keypress by eye.

`Settler(quiet_s=0.15)` collapses bursts and drops identical resends: 172 updates → 61 settled screens.

## 6. Safety

- The capture client sends only the constant `requestUpdate` (on connect and on `mcduConnected`), enforced by a single parameterless send function and `test_mcdu_capture.py`. It never sends `event:`.
- `requestUpdate` is broadcast to every client. The remote MCDU web client ignores it; the aircraft answers with an `update:` that every client receives anyway. No effect on the sim beyond one redraw broadcast.
- Effect on an open remote MCDU tab was not specifically observed during the capture.

## 7. Risks and limits

- **Legacy MCDU dependency.** All of this lives in FBW's legacy MCDU (`A320_Neo_CDU_MainDisplay.ts`), and a source comment refers to an upcoming "MCDU split". A rewrite could change the frame format or titles. Mitigation: keep all SimBridge knowledge in `mcdu.py`, keep the capture fixture as the regression test, re-capture after FBW updates.
- **Titles differ between FBW builds** (`FUEL PRED` vs `INIT FUEL PRED`). Classify by labels as well as titles; add a fixture per FBW version when it changes.
- **Displayed page only** (spec §7). Values are known only while their page is on screen; cache with a timestamp.
- **Network setup** on WSL2/LAN needs the firewall steps in §1.

## 8. What M5 builds on

- `parse_frame` → `Update`; `screen_of` → `McduScreen` (`title_text`, `page`, `labels`, `lines`, `scratchpad`, `line_under(label)`).
- `Settler` for debounced screens; `classify` → `PageId`.
- Field extraction per page follows `init_a_fields` / `init_b_fields`: find the label row, read the data row text, treat boxes/dashes as `None`.
- Next: a `sources/simbridge.py` that runs the capture loop without the file and feeds settled screens into State (M3 sources layer), then the coach pages (M5).
