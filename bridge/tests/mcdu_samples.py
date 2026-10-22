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


BLANK: Side = side("", [])


def update_frame(left: Side, right: Side | None = None) -> str:
    return "update:" + json.dumps({"left": left, "right": left if right is None else right})


def init_a(ci: str = "25", crz: str = "FL350/-54°", sec: bool = False) -> Side:
    title = (
        fbw_line((1, "SEC", "white"), (10, "INIT", "white"))
        if sec
        else fbw_line((10, "INIT", "white"))
    )
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
            row(
                fbw_line((0, "KRDU05L", "green"), (8, "0000", "green"), (14, "---/   430", "green"))
            ),
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
    )


def perf_appr() -> Side:
    return side(
        legacy("\xa0\xa0\xa0\xa0\xa0{white}APPR{end}\xa0{green}ILS27R{end}" + "\xa0" * 8),
        [
            row(legacy("QNH")),
            row(legacy("1013", "cyan")),
            row(legacy("TEMP")),
            row(legacy("15°", "cyan")),
        ],
    )


def data_index() -> Side:
    return side(
        legacy("DATA INDEX"),
        [row(legacy("\xa0POSITION")), row(legacy("<MONITOR"))],
        page="{small}1/2{end}",
    )
