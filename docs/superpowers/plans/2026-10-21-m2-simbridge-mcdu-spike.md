# M2: SimBridge MCDU Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A passive SimBridge MCDU capture tool plus a pure parser/page classifier, proven against a capture from the user's sim, ending in `docs/simbridge-mcdu.md` with a go/no-go.

**Architecture:** `companion/mcdu.py` is pure (markup → spans, frames → screens, debounce by recorded `t`, page classification, three proof fields). `companion/mcdu_capture.py` is the only I/O: an aiohttp WebSocket client that records every frame verbatim to JSONL and prints each settled screen. Nothing is wired into `run`, the page or State.

**Tech Stack:** Python 3.12, uv, aiohttp (client + test server), pytest + pytest-aiohttp, ruff, mypy strict.

**Design:** `docs/superpowers/specs/2026-10-21-m2-simbridge-mcdu-spike-design.md`

## Global Constraints

- All commands run from `bridge/`: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy companion tests`.
- No new dependencies.
- The capture client sends exactly one kind of frame: `requestUpdate`. Any `event:` frame presses an MCDU key in the sim.
- Timing in `mcdu.py` uses frame `t` only, never the wall clock.
- Comments explain why, never what.
- NBSP (`\xa0`) is a space everywhere text is compared.

## File Structure

| Path | Responsibility |
|---|---|
| `bridge/companion/mcdu.py` | Markup parser, `McduScreen`, `parse_frame`, `screen_of`, `Settler`, `PageId`, `classify`, proof fields, `describe` |
| `bridge/companion/mcdu_capture.py` | `capture()` WebSocket client, JSONL writer, settled-screen reporting |
| `bridge/companion/__main__.py` | Add `mcdu-capture` subcommand |
| `bridge/tests/mcdu_samples.py` | FBW-shaped frame builders shared by tests |
| `bridge/tests/test_mcdu_markup.py` | `parse_markup` |
| `bridge/tests/test_mcdu_frames.py` | `parse_frame`, `screen_of`, `McduScreen` helpers |
| `bridge/tests/test_mcdu_settler.py` | `Settler` |
| `bridge/tests/test_mcdu_classify.py` | `classify`, proof fields, `describe` |
| `bridge/tests/test_mcdu_capture.py` | `capture()` against a fake SimBridge |
| `bridge/tests/fixtures/mcdu_preflight.jsonl` | Trimmed real capture (Task 8) |
| `bridge/tests/test_mcdu_fixture.py` | Replay of the real capture (Task 8) |
| `docs/simbridge-mcdu.md` | Findings and verdict (Task 9) |

---

### Task 1: Markup parser

**Files:**
- Create: `bridge/companion/mcdu.py`
- Test: `bridge/tests/test_mcdu_markup.py`

- [ ] **Step 1: Write the failing tests**

```python
from companion.mcdu import Span, parse_markup, plain


def test_plain_text_is_white_big() -> None:
    assert parse_markup("ABC") == (Span("ABC", "white", "big"),)


def test_default_size_comes_from_caller() -> None:
    assert parse_markup("L", "small") == (Span("L", "white", "small"),)


def test_color_tag() -> None:
    assert parse_markup("{cyan}25{end}") == (Span("25", "cyan", "big"),)


def test_end_restores_the_enclosing_style() -> None:
    assert parse_markup("{small}{green}A{end}B{end}C") == (
        Span("A", "green", "small"),
        Span("B", "white", "small"),
        Span("C", "white", "big"),
    )


def test_sp_and_nbsp_are_spaces_and_merge() -> None:
    assert parse_markup("{white}A{sp}\xa0B{end}") == (Span("A  B", "white", "big"),)


def test_unknown_tag_keeps_end_balanced() -> None:
    assert parse_markup("{cyan}{left}X{end}Y{end}Z") == (
        Span("XY", "cyan", "big"),
        Span("Z", "white", "big"),
    )


def test_unterminated_tag() -> None:
    assert parse_markup("{amber}X") == (Span("X", "amber", "big"),)


def test_stray_end_and_brace() -> None:
    assert plain(parse_markup("A{end}{end}B }")) == "AB }"


def test_empty() -> None:
    assert parse_markup("") == ()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_mcdu_markup.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'companion.mcdu'`

- [ ] **Step 3: Implement**

```python
import re
from dataclasses import dataclass
from typing import Literal

Size = Literal["big", "small"]
_COLORS = frozenset({"amber", "red", "green", "cyan", "white", "magenta", "yellow", "inop"})
_SIZES: dict[str, Size] = {"big": "big", "small": "small"}
_TAG = re.compile(r"\{([a-z]+)\}")


@dataclass(frozen=True)
class Span:
    text: str
    color: str
    size: Size


def parse_markup(cell: str, size: Size = "big") -> tuple[Span, ...]:
    spans: list[Span] = []
    # FBW closes every tag with {end}, so unknown tags push a copy to keep pops aligned.
    stack: list[tuple[str, Size]] = [("white", size)]
    pos = 0
    for match in _TAG.finditer(cell):
        _append(spans, cell[pos : match.start()], *stack[-1])
        pos = match.end()
        tag = match.group(1)
        color, current = stack[-1]
        if tag == "sp":
            _append(spans, " ", color, current)
        elif tag == "end":
            if len(stack) > 1:
                stack.pop()
        elif tag in _COLORS:
            stack.append((tag, current))
        elif tag in _SIZES:
            stack.append((color, _SIZES[tag]))
        else:
            stack.append((color, current))
    _append(spans, cell[pos:], *stack[-1])
    return tuple(spans)


def plain(spans: tuple[Span, ...]) -> str:
    return "".join(span.text for span in spans)


def _append(spans: list[Span], text: str, color: str, size: Size) -> None:
    text = text.replace("\xa0", " ")
    if not text:
        return
    if spans and spans[-1].color == color and spans[-1].size == size:
        spans[-1] = Span(spans[-1].text + text, color, size)
    else:
        spans.append(Span(text, color, size))
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_mcdu_markup.py -q`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add companion/mcdu.py tests/test_mcdu_markup.py
git commit -m "Parse SimBridge MCDU cell markup into styled spans"
```

---

### Task 2: Test samples, frames and screens

**Files:**
- Create: `bridge/tests/mcdu_samples.py`
- Modify: `bridge/companion/mcdu.py`
- Test: `bridge/tests/test_mcdu_frames.py`

- [ ] **Step 1: Write the shared samples**

Shapes follow `A320_Neo_CDU_MainDisplay.sendUpdate`, `FormatLine` and the INIT/PERF/F-PLN page templates in `flybywiresim/aircraft`.

```python
import json
from typing import Any

Side = dict[str, Any]


def fbw_line(*columns: tuple[int, str, str]) -> str:
    """Mimic FormatLine + setLine: positioned columns on a 24-char row, whitespace as {sp}."""
    out = ""
    pos = 0
    for index, text, color in sorted(columns):
        out += " " * (index - pos) + f"{{{color}}}{text}{{end}}"
        pos = index + len(text)
    out += " " * max(0, 24 - pos)
    return "{white}" + out.replace(" ", "{sp}") + "{small}{end}{big}{end}{end}"


def legacy(text: str, color: str = "white") -> str:
    """Mimic setLine/setLabel on a page that builds rows from plain strings."""
    return f"{{{color}}}{text}{{end}}"


def row(cell: str) -> list[str]:
    return [cell, "", "", ""]


def side(title: str, rows: list[list[str]], page: str = "", scratchpad: str = "") -> Side:
    padded = rows + [["", "", "", ""]] * (12 - len(rows))
    return {
        "title": title,
        "titleLeft": "",
        "page": page,
        "lines": padded,
        "scratchpad": scratchpad,
        "arrows": [False, False, False, False],
    }


BLANK: Side = {"lines": [["", "", ""]] * 12, "scratchpad": "", "title": "", "titleLeft": "", "page": "", "arrows": [False] * 4}


def update_frame(left: Side, right: Side | None = None) -> str:
    return "update:" + json.dumps({"left": left, "right": left if right is None else right})


def init_a(ci: str = "25", crz: str = "FL350/-54°", sec: bool = False) -> Side:
    title = fbw_line((1, "SEC", "white"), (10, "INIT", "white")) if sec else fbw_line((10, "INIT", "white"))
    return side(
        title,
        [
            row(fbw_line((1, "CO RTE", "white"), (15, "FROM/TO", "white"))),
            row(fbw_line((0, "NONE", "cyan"), (15, "KRDU/KATL", "cyan"))),
            row(fbw_line((0, "ALTN/CO RTE", "white"))),
            row(fbw_line((0, "KCHA", "cyan"))),
            row(fbw_line((0, "FLT NBR", "white"))),
            row(fbw_line((0, "DAL1234", "cyan"))),
            row(""),
            row(""),
            row(fbw_line((0, "COST INDEX", "white"), (19, "TROPO", "white"))),
            row(fbw_line((0, ci, "cyan"), (19, "36090", "cyan"))),
            row(fbw_line((0, "CRZ FL/TEMP", "white"), (16, "GND TEMP", "white"))),
            row(fbw_line((0, crz, "cyan"), (21, "15°", "cyan"))),
        ],
    )


def init_b(zfw: str = "55.3/27.1") -> Side:
    return side(
        fbw_line((5, "INIT FUEL PRED", "white")),
        [
            row(fbw_line((0, "TAXI", "white"), (15, "ZFW/ZFWCG", "white"))),
            row(fbw_line((0, "0.2", "cyan"), (13, zfw, "cyan"))),
            row(fbw_line((0, "TRIP", "white"), (5, "/TIME", "white"), (19, "BLOCK", "white"))),
            row(fbw_line((0, "---.-/----", "white"), (19, "8.4", "cyan"))),
        ],
    )


def fpln() -> Side:
    return side(
        fbw_line((1, "FROM", "white"), (17, "DAL1234", "white")),
        [
            row(""),
            row(fbw_line((0, "KRDU05L", "green"), (8, "0000", "green"), (14, "---/   430", "green"))),
            row(fbw_line((1, "C062°", "green"), (13, "SPD/ALT", "white"))),
            row(fbw_line((0, "D062M", "green"), (8, "0002", "green"), (16, "*/  1000", "magenta"))),
        ],
    )


def perf_to() -> Side:
    return side(
        legacy("\xa0\xa0\xa0\xa0TAKE\xa0OFF\xa0RWY\xa0{green}\xa005L{end}\xa0\xa0\xa0\xa0"),
        [
            row(legacy("\xa0V1\xa0\xa0FLP RETR")),
            row(legacy("142", "cyan")),
            row(legacy("\xa0VR\xa0\xa0SLT RETR")),
            row(legacy("145", "cyan")),
        ],
        page="",
    )


def perf_appr() -> Side:
    return side(
        legacy("\xa0\xa0\xa0\xa0\xa0{white}APPR{end}\xa0{green}ILS27R{end}\xa0\xa0\xa0\xa0\xa0\xa0\xa0\xa0"),
        [row(legacy("QNH")), row(legacy("1013", "cyan")), row(legacy("TEMP")), row(legacy("15°", "cyan"))],
    )


def data_index() -> Side:
    return side(legacy("DATA INDEX"), [row(legacy("\xa0POSITION")), row(legacy("<MONITOR"))], page="{small}1/2{end}")
```

- [ ] **Step 2: Write the failing tests**

```python
from companion.mcdu import Connected, Disconnected, Update, parse_frame, screen_of
from tests.mcdu_samples import BLANK, init_a, side, update_frame


def test_update_frame() -> None:
    frame = parse_frame(update_frame(init_a()))
    assert isinstance(frame, Update)
    screen = frame.left
    assert screen.title_text == "INIT"
    assert len(screen.labels) == 6 and len(screen.lines) == 6
    assert "FROM/TO" in screen.labels[0].text
    assert screen.lines[0].text.split() == ["NONE", "KRDU/KATL"]


def test_connection_frames() -> None:
    assert parse_frame("mcduConnected") == Connected()
    assert parse_frame("mcduDisconnected") == Disconnected()


def test_ignored_frames() -> None:
    for raw in ["event:left:INIT", 'print:{"lines":[]}', "requestUpdate", "update:not json", "update:[1]", ""]:
        assert parse_frame(raw) is None


def test_page_number_and_scratchpad() -> None:
    frame = parse_frame(update_frame(side("{white}X{end}", [], page="{small}1/3{end}", scratchpad="{amber}NOT ALLOWED{end}")))
    assert isinstance(frame, Update)
    assert frame.left.page == "1/3"
    assert frame.left.scratchpad == "NOT ALLOWED"


def test_short_and_missing_rows_are_empty() -> None:
    frame = parse_frame('update:{"left":{"title":"{white}X{end}","lines":[["{white}L{end}"]]},"right":{}}')
    assert isinstance(frame, Update)
    assert frame.left.labels[0].text == "L"
    assert all(not row.text for row in frame.left.lines)
    assert frame.right.blank


def test_screen_of_prefers_left_then_right() -> None:
    a = parse_frame(update_frame(init_a(), BLANK))
    b = parse_frame(update_frame(BLANK, init_a()))
    c = parse_frame(update_frame(BLANK, BLANK))
    assert isinstance(a, Update) and isinstance(b, Update) and isinstance(c, Update)
    assert screen_of(a) == a.left
    assert screen_of(b) == b.right
    assert screen_of(c) is None


def test_line_under() -> None:
    frame = parse_frame(update_frame(init_a()))
    assert isinstance(frame, Update)
    line = frame.left.line_under("COST INDEX")
    assert line is not None and line.text.split()[0] == "25"
    assert frame.left.line_under("NOPE") is None
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/test_mcdu_frames.py -q`
Expected: FAIL, `ImportError: cannot import name 'Connected'`

- [ ] **Step 4: Implement** — append to `companion/mcdu.py` (add `import json` and `from typing import Any` to the imports)

```python
@dataclass(frozen=True)
class Row:
    cells: tuple[tuple[Span, ...], ...]

    @property
    def text(self) -> str:
        return " ".join(text for text in (plain(cell) for cell in self.cells) if text.strip())


@dataclass(frozen=True)
class McduScreen:
    title: tuple[Span, ...]
    page: str
    labels: tuple[Row, ...]
    lines: tuple[Row, ...]
    scratchpad: str

    @property
    def title_text(self) -> str:
        return " ".join(plain(self.title).split())

    @property
    def blank(self) -> bool:
        return not self.title_text and not any(row.text.strip() for row in self.labels + self.lines)

    def line_under(self, label: str) -> Row | None:
        for label_row, line in zip(self.labels, self.lines, strict=True):
            if label in label_row.text:
                return line
        return None


@dataclass(frozen=True)
class Update:
    left: McduScreen
    right: McduScreen


@dataclass(frozen=True)
class Connected:
    pass


@dataclass(frozen=True)
class Disconnected:
    pass


Frame = Update | Connected | Disconnected


def parse_frame(raw: str) -> Frame | None:
    if raw == "mcduConnected":
        return Connected()
    if raw == "mcduDisconnected":
        return Disconnected()
    if not raw.startswith("update:"):
        return None
    try:
        content = json.loads(raw.removeprefix("update:"))
    except json.JSONDecodeError:
        return None
    if not isinstance(content, dict):
        return None
    return Update(_screen(content.get("left")), _screen(content.get("right")))


def screen_of(update: Update) -> McduScreen | None:
    # Both sides carry the same screen; an unpowered MCDU arrives blank.
    for screen in (update.left, update.right):
        if not screen.blank:
            return screen
    return None


def _screen(raw: Any) -> McduScreen:
    side = raw if isinstance(raw, dict) else {}
    lines = side.get("lines")
    rows = lines if isinstance(lines, list) else []
    parsed = [
        _row(rows[i] if i < len(rows) else [], "small" if i % 2 == 0 else "big") for i in range(12)
    ]
    return McduScreen(
        title=parse_markup(_str(side.get("title"))),
        page=plain(parse_markup(_str(side.get("page")))).strip(),
        labels=tuple(parsed[0::2]),
        lines=tuple(parsed[1::2]),
        scratchpad=plain(parse_markup(_str(side.get("scratchpad")))).strip(),
    )


def _row(raw: Any, size: Size) -> Row:
    cells = raw if isinstance(raw, list) else []
    return Row(tuple(parse_markup(_str(cell), size) for cell in cells))


def _str(value: Any) -> str:
    return value if isinstance(value, str) else ""
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_mcdu_frames.py tests/test_mcdu_markup.py -q`
Expected: 16 passed

- [ ] **Step 6: Commit**

```bash
git add companion/mcdu.py tests/mcdu_samples.py tests/test_mcdu_frames.py
git commit -m "Parse SimBridge MCDU update frames into screens"
```

---

### Task 3: Settler

**Files:**
- Modify: `bridge/companion/mcdu.py`
- Test: `bridge/tests/test_mcdu_settler.py`

- [ ] **Step 1: Write the failing tests**

```python
from companion.mcdu import McduScreen, Settler, Update, parse_frame
from tests.mcdu_samples import fpln, init_a, init_b, update_frame


def screen(side: dict[str, object]) -> McduScreen:
    frame = parse_frame(update_frame(side))
    assert isinstance(frame, Update)
    return frame.left


A, B, C = screen(init_a()), screen(init_b()), screen(fpln())


def test_burst_settles_to_last_screen() -> None:
    settler = Settler(quiet_s=0.15)
    assert settler.push(0.0, A) is None
    assert settler.push(0.05, B) is None
    assert settler.push(0.10, C) is None
    assert settler.poll(0.20) is None
    assert settler.poll(0.25) == C
    assert settler.poll(0.30) is None


def test_next_frame_after_quiet_releases_previous() -> None:
    settler = Settler(quiet_s=0.15)
    settler.push(0.0, A)
    assert settler.push(1.0, B) == A
    assert settler.poll(2.0) == B


def test_identical_screen_is_not_repeated() -> None:
    settler = Settler(quiet_s=0.15)
    settler.push(0.0, A)
    assert settler.poll(1.0) == A
    settler.push(2.0, screen(init_a()))
    assert settler.poll(3.0) is None


def test_poll_without_frames() -> None:
    assert Settler().poll(10.0) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_mcdu_settler.py -q`
Expected: FAIL, `ImportError: cannot import name 'Settler'`

- [ ] **Step 3: Implement** — append to `companion/mcdu.py`

```python
class Settler:
    """Collapses bursts of frames into one screen once the MCDU stops redrawing."""

    def __init__(self, quiet_s: float = 0.15) -> None:
        self._quiet_s = quiet_s
        self._pending: tuple[float, McduScreen] | None = None
        self._last: McduScreen | None = None

    def push(self, t: float, screen: McduScreen) -> McduScreen | None:
        settled = self.poll(t)
        self._pending = (t, screen)
        return settled

    def poll(self, t: float) -> McduScreen | None:
        if self._pending is None:
            return None
        since, screen = self._pending
        if t - since < self._quiet_s:
            return None
        self._pending = None
        if screen == self._last:
            return None
        self._last = screen
        return screen
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_mcdu_settler.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add companion/mcdu.py tests/test_mcdu_settler.py
git commit -m "Debounce MCDU frame bursts by recorded time"
```

---

### Task 4: Page classifier, proof fields, describe

**Files:**
- Modify: `bridge/companion/mcdu.py`
- Test: `bridge/tests/test_mcdu_classify.py`

Signatures come from FBW source and are confirmed against the real capture in Task 8.

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from companion.mcdu import McduScreen, PageId, Update, classify, describe, init_a_fields, init_b_fields, parse_frame
from tests.mcdu_samples import Side, data_index, fpln, init_a, init_b, perf_appr, perf_to, update_frame


def screen(side: Side) -> McduScreen:
    frame = parse_frame(update_frame(side))
    assert isinstance(frame, Update)
    return frame.left


@pytest.mark.parametrize(
    ("side", "page"),
    [
        (init_a(), PageId.INIT_A),
        (init_a(sec=True), PageId.INIT_A),
        (init_b(), PageId.INIT_B),
        (fpln(), PageId.FPLN),
        (perf_to(), PageId.PERF_TO),
        (perf_appr(), PageId.PERF_APPR),
        (data_index(), None),
    ],
)
def test_classify(side: Side, page: PageId | None) -> None:
    assert classify(screen(side)) is page


def test_init_a_fields() -> None:
    assert init_a_fields(screen(init_a())) == {"ci": 25, "crz_fl": 350}


def test_init_a_fields_missing() -> None:
    assert init_a_fields(screen(init_a(ci="___", crz="_____"))) == {"ci": None, "crz_fl": None}


def test_init_b_fields() -> None:
    assert init_b_fields(screen(init_b())) == {"zfw": 55.3}
    assert init_b_fields(screen(init_b(zfw="___._/__._"))) == {"zfw": None}


def test_describe() -> None:
    assert describe(screen(init_a())) == "INIT_A  ci=25 crz_fl=350"
    assert describe(screen(init_b())) == "INIT_B  zfw=55.3"
    assert describe(screen(fpln())) == "FPLN"
    assert describe(screen(data_index())) == "?  title='DATA INDEX'"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_mcdu_classify.py -q`
Expected: FAIL, `ImportError: cannot import name 'PageId'`

- [ ] **Step 3: Implement** — append to `companion/mcdu.py` (add `from collections.abc import Mapping` and `from enum import StrEnum` to the imports)

```python
class PageId(StrEnum):
    INIT_A = "INIT_A"
    INIT_B = "INIT_B"
    FPLN = "FPLN"
    PERF_TO = "PERF_TO"
    PERF_APPR = "PERF_APPR"


_FL = re.compile(r"FL(\d{3})")
_ZFW = re.compile(r"(\S+)/\S+$")


def classify(screen: McduScreen) -> PageId | None:
    # FBW sends no page id and the titles are generic, so the label rows disambiguate.
    title = screen.title_text
    words = title.split()
    labels = " | ".join(row.text for row in screen.labels)
    if "TAKE OFF" in title:
        return PageId.PERF_TO
    if "APPR" in words and "QNH" in labels:
        return PageId.PERF_APPR
    if words[:1] == ["FROM"]:
        return PageId.FPLN
    if "INIT" in words:
        if "FROM/TO" in labels:
            return PageId.INIT_A
        if "ZFW/ZFWCG" in labels:
            return PageId.INIT_B
    return None


def init_a_fields(screen: McduScreen) -> dict[str, int | None]:
    ci_row = screen.line_under("COST INDEX")
    crz_row = screen.line_under("CRZ FL/TEMP")
    ci = ci_row.text.split()[0] if ci_row and ci_row.text.split() else ""
    fl = _FL.search(crz_row.text) if crz_row else None
    return {"ci": int(ci) if ci.isdigit() else None, "crz_fl": int(fl.group(1)) if fl else None}


def init_b_fields(screen: McduScreen) -> dict[str, float | None]:
    zfw_row = screen.line_under("ZFW/ZFWCG")
    match = _ZFW.search(zfw_row.text.rstrip()) if zfw_row else None
    try:
        zfw = float(match.group(1)) if match else None
    except ValueError:
        zfw = None
    return {"zfw": zfw}


def describe(screen: McduScreen) -> str:
    page = classify(screen)
    fields: Mapping[str, object] = {}
    if page is PageId.INIT_A:
        fields = init_a_fields(screen)
    elif page is PageId.INIT_B:
        fields = init_b_fields(screen)
    name = page.value if page else f"?  title={screen.title_text!r}"
    detail = " ".join(f"{key}={value}" for key, value in fields.items())
    return f"{name}  {detail}".rstrip()
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_mcdu_classify.py -q`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add companion/mcdu.py tests/test_mcdu_classify.py
git commit -m "Classify MCDU pages and read CI, CRZ FL and ZFW"
```

---

### Task 5: Capture client

**Files:**
- Create: `bridge/companion/mcdu_capture.py`
- Test: `bridge/tests/test_mcdu_capture.py`

- [ ] **Step 1: Write the failing tests**

```python
import asyncio
import io
import json
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from aiohttp import web

from companion.mcdu_capture import capture
from tests.mcdu_samples import init_a, update_frame

PATH = "/interfaces/v1/mcdu"


async def until(condition: Callable[[], bool]) -> None:
    async def poll() -> None:
        while not condition():
            await asyncio.sleep(0.005)

    await asyncio.wait_for(poll(), timeout=3)


async def test_records_every_frame_and_only_requests_updates(aiohttp_server: Any) -> None:
    frames = [update_frame(init_a()), "event:left:INIT", "mcduConnected", 'print:{"lines":[]}']
    received: list[str] = []

    async def mcdu(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        for frame in frames:
            await ws.send_str(frame)
        async for msg in ws:
            received.append(msg.data)
        return ws

    app = web.Application()
    app.router.add_get(PATH, mcdu)
    server = await aiohttp_server(app)
    out = io.StringIO()
    reports: list[str] = []
    task = asyncio.create_task(capture(str(server.make_url(PATH)), out, reports.append))
    try:
        await until(
            lambda: len(received) >= 2
            and out.getvalue().count("\n") == len(frames)
            and any("INIT_A  ci=25 crz_fl=350" in r for r in reports)
        )
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    assert received == ["requestUpdate", "requestUpdate"]
    recorded = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [r["raw"] for r in recorded] == frames
    times = [r["t"] for r in recorded]
    assert times == sorted(times)


async def test_keeps_retrying_when_simbridge_is_down(unused_tcp_port: int) -> None:
    reports: list[str] = []
    task = asyncio.create_task(
        capture(f"ws://127.0.0.1:{unused_tcp_port}{PATH}", io.StringIO(), reports.append, retry_s=0.01)
    )
    try:
        await until(lambda: sum("cannot reach" in r for r in reports) >= 2)
        assert not task.done()
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_mcdu_capture.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'companion.mcdu_capture'`

- [ ] **Step 3: Implement**

```python
import asyncio
import json
from collections.abc import Callable
from typing import TextIO

import aiohttp

from companion.mcdu import Connected, Disconnected, McduScreen, Settler, Update, describe, parse_frame, screen_of

DEFAULT_URL = "ws://localhost:8380/interfaces/v1/mcdu"
Report = Callable[[str], None]


async def capture(url: str, out: TextIO, report: Report, retry_s: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    start = loop.time()

    def clock() -> float:
        return loop.time() - start

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.ws_connect(url, heartbeat=20) as ws:
                    report(f"connected to {url}")
                    await _request_update(ws)
                    await _record(ws, out, report, clock)
                report("SimBridge closed the connection")
            except (aiohttp.ClientError, OSError, TimeoutError) as exc:
                report(f"cannot reach {url}: {exc}")
            await asyncio.sleep(retry_s)


async def _request_update(ws: aiohttp.ClientWebSocketResponse) -> None:
    # The only frame this client ever sends: SimBridge relays everything, and an "event:" frame
    # would press an MCDU key in the sim.
    await ws.send_str("requestUpdate")


async def _record(
    ws: aiohttp.ClientWebSocketResponse, out: TextIO, report: Report, clock: Callable[[], float]
) -> None:
    settler = Settler()
    ticker = asyncio.create_task(_tick(settler, report, clock))
    try:
        async for msg in ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            t = clock()
            out.write(json.dumps({"t": round(t, 3), "raw": msg.data}) + "\n")
            out.flush()
            frame = parse_frame(msg.data)
            if isinstance(frame, Connected):
                report(f"{t:7.1f}s  sim connected")
                await _request_update(ws)
            elif isinstance(frame, Disconnected):
                report(f"{t:7.1f}s  sim disconnected")
            elif isinstance(frame, Update):
                screen = screen_of(frame)
                if screen is not None:
                    _report_settled(settler.push(t, screen), t, report)
    finally:
        ticker.cancel()


async def _tick(settler: Settler, report: Report, clock: Callable[[], float]) -> None:
    # Separate task so a quiet socket still releases the last screen.
    while True:
        await asyncio.sleep(0.05)
        t = clock()
        _report_settled(settler.poll(t), t, report)


def _report_settled(screen: McduScreen | None, t: float, report: Report) -> None:
    if screen is not None:
        report(f"{t:7.1f}s  {describe(screen)}")
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_mcdu_capture.py -q`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add companion/mcdu_capture.py tests/test_mcdu_capture.py
git commit -m "Add a passive SimBridge MCDU capture client"
```

---

### Task 6: `mcdu-capture` CLI

**Files:**
- Modify: `bridge/companion/__main__.py`

- [ ] **Step 1: Implement** — replace `main()`:

```python
def main() -> int:
    parser = argparse.ArgumentParser(prog="companion")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="serve the page and the /ws bridge")
    run.add_argument("--config", type=Path, default=Path("config.toml"))
    mcdu = commands.add_parser("mcdu-capture", help="record SimBridge MCDU frames to JSONL")
    mcdu.add_argument("out", type=Path)
    mcdu.add_argument("--url", default=DEFAULT_URL)
    args = parser.parse_args()

    if args.command == "mcdu-capture":
        with args.out.open("w", encoding="utf-8") as out:
            with suppress(KeyboardInterrupt):
                asyncio.run(capture(args.url, out, lambda line: print(line, flush=True)))
        return 0

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"companion: {exc}", file=sys.stderr)
        return 2

    loader = SimbriefLoader(config.simbrief, default_cache_path())
    web.run_app(make_app(loader), host=config.server.host, port=config.server.port)
    return 0
```

Add imports: `import asyncio`, `from contextlib import suppress`, `from companion.mcdu_capture import DEFAULT_URL, capture`.

- [ ] **Step 2: Smoke-test with SimBridge down**

Run: `timeout -s INT 3 uv run python -m companion mcdu-capture /tmp/x.jsonl; echo exit=$?`
Expected: `cannot reach ws://localhost:8380/interfaces/v1/mcdu: …` lines every 2 s, then `exit=0`.

- [ ] **Step 3: Full check**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy companion tests`
Expected: all pass, no lint/type errors.

- [ ] **Step 4: Commit**

```bash
git add companion/__main__.py
git commit -m "Add mcdu-capture command"
```

---

### Task 7: Capture session (user, Windows)

- [ ] flyPad EFB → Settings → SimBridge: Auto or On. SimBridge running.
- [ ] From `bridge\`: `uv run python -m companion mcdu-capture ..\captures\preflight.jsonl`
- [ ] Wait for `sim connected` / a settled line, then visit INIT A → F-PLN → INIT B → PERF TO → PERF APPR, pausing ~2 s on each. Enter CI, CRZ FL and ZFW and note the values.
- [ ] Also open one or two unrelated pages (DATA, RAD NAV) and type in the scratchpad once.
- [ ] Ctrl+C. Report the values entered and whether the real remote MCDU (if open) behaved normally.

---

### Task 8: Real-capture fixture

**Files:**
- Create: `bridge/tests/fixtures/mcdu_preflight.jsonl`
- Create: `bridge/tests/test_mcdu_fixture.py`
- Modify (only if the capture disagrees): `classify`/field signatures in `bridge/companion/mcdu.py` and the matching samples in `bridge/tests/mcdu_samples.py`

- [ ] **Step 1:** Replay the capture and look at every settled screen:

```bash
uv run python -c "
import json,sys
from companion.mcdu import Settler, Update, parse_frame, screen_of, describe
s=Settler(); last=0.0
for line in open(sys.argv[1]):
    r=json.loads(line); f=parse_frame(r['raw']); last=r['t']
    if isinstance(f, Update) and (sc:=screen_of(f)):
        if (d:=s.push(r['t'], sc)): print(f\"{r['t']:7.1f}\", describe(d))
if (d:=s.poll(last+1)): print('  end', describe(d))
" ../captures/preflight.jsonl
```

- [ ] **Step 2:** Fix any misclassification by adjusting `classify` against the real titles/labels, update `mcdu_samples.py` to match the real shapes, rerun `uv run pytest -q`.
- [ ] **Step 3:** Trim the capture to the frames from first INIT A to last PERF APPR (keep `t` as is) into `tests/fixtures/mcdu_preflight.jsonl`.
- [ ] **Step 4:** Write `tests/test_mcdu_fixture.py`, filling `EXPECTED` from Step 1 output and the user's entered values:

```python
import json
from pathlib import Path

from companion.mcdu import PageId, Settler, Update, classify, init_a_fields, init_b_fields, parse_frame, screen_of

FIXTURE = Path(__file__).parent / "fixtures" / "mcdu_preflight.jsonl"


def settled() -> list:
    settler, out, t = Settler(), [], 0.0
    for line in FIXTURE.read_text().splitlines():
        record = json.loads(line)
        t = record["t"]
        frame = parse_frame(record["raw"])
        if isinstance(frame, Update) and (screen := screen_of(frame)) is not None:
            if (done := settler.push(t, screen)) is not None:
                out.append(done)
    if (done := settler.poll(t + 1)) is not None:
        out.append(done)
    return out


def test_page_sequence() -> None:
    pages = [classify(s) for s in settled()]
    visited = [p for i, p in enumerate(pages) if p is not None and (i == 0 or pages[i - 1] != p)]
    assert visited == [PageId.INIT_A, PageId.FPLN, PageId.INIT_B, PageId.PERF_TO, PageId.PERF_APPR]


def test_entered_values() -> None:
    screens = settled()
    init_a = [init_a_fields(s) for s in screens if classify(s) is PageId.INIT_A][-1]
    init_b = [init_b_fields(s) for s in screens if classify(s) is PageId.INIT_B][-1]
    assert init_a == {"ci": CI_ENTERED, "crz_fl": CRZ_FL_ENTERED}
    assert init_b == {"zfw": ZFW_ENTERED}
```

Replace `CI_ENTERED`, `CRZ_FL_ENTERED`, `ZFW_ENTERED` with the literal values the user entered, and the `visited` list with the order actually flown. Add type parameters (`list[McduScreen]`) so mypy passes.

- [ ] **Step 5:** `uv run pytest -q && uv run ruff check . && uv run mypy companion tests` → pass. Commit fixture, test and any signature fixes.

---

### Task 9: Findings doc and verdict

**Files:**
- Create: `docs/simbridge-mcdu.md`

- [ ] **Step 1:** Write the doc with these sections, filled from the design's source findings plus the capture:
  1. Setup (flyPad setting, SimBridge, endpoint).
  2. Frame schema (`update:`, `mcduConnected`, `mcduDisconnected`, `requestUpdate`, `event:`, `print:`), with one real `update:` example trimmed to 2 rows.
  3. Markup table and the two cell styles.
  4. Page signatures as implemented in `classify`, and the title strings seen.
  5. Measured from capture: total frames, frames per settled screen (median/max), frames per second while idle and while typing.
  6. Safety: passive client rule; observed effect on the real remote MCDU.
  7. Risks: legacy MCDU / "MCDU split", displayed-page-only limitation.
  8. **Verdict: GO / NO-GO** with one paragraph of reasoning, and what M5 builds on (`mcdu.py` API).
- [ ] **Step 2:** Update `spec.md` §10 M2 row status and §6.1 notes for `ci`, `crz_fl`, `zfw_fmgc` ("from MCDU INIT A/B when displayed").
- [ ] **Step 3:** Commit.
