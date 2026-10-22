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
