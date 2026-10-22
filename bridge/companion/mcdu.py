import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

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
