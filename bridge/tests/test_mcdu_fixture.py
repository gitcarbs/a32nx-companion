import gzip
import json
from pathlib import Path

from companion.mcdu import (
    McduScreen,
    PageId,
    Settler,
    Update,
    classify,
    init_a_fields,
    init_b_fields,
    parse_frame,
    screen_of,
)

# Unedited mcdu-capture output from FBW stable in MSFS 2024: a SimBrief INIT uplink, page
# browsing, scratchpad typing and a rejected ZFW entry.
FIXTURE = Path(__file__).parent / "fixtures" / "mcdu_preflight.jsonl.gz"


def settled() -> list[McduScreen]:
    settler, out, t = Settler(), [], 0.0
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as lines:
        for line in lines:
            record = json.loads(line)
            t = record["t"]
            frame = parse_frame(record["raw"])
            screen = screen_of(frame) if isinstance(frame, Update) else None
            if screen is not None and (done := settler.push(t, screen)) is not None:
                out.append(done)
    if (done := settler.poll(t + 1)) is not None:
        out.append(done)
    return out


def test_page_sequence() -> None:
    pages = [page for page in map(classify, settled()) if page is not None]
    visited = [page for i, page in enumerate(pages) if i == 0 or pages[i - 1] != page]
    a, b, f, to = PageId.INIT_A, PageId.INIT_B, PageId.FPLN, PageId.PERF_TO
    assert visited == [a, b, to, a, f, a, to, b, to, a, to, a, f, b, to, a, b]


def test_other_pages_stay_unclassified() -> None:
    titles = {screen.title_text for screen in settled() if classify(screen) is None}
    assert titles == {
        "AOC INIT/REVIEW",
        "AOC MENU",
        "ATC MENU",
        "ATSU DATALINK",
        "DATA INDEX",
        "MCDU MENU",
        "SEC INDEX",
        "TO",
        "TO 15",
    }


def test_uplinked_init_a_values() -> None:
    screens = [s for s in settled() if classify(s) is PageId.INIT_A]
    assert init_a_fields(screens[0]) == {"ci": None, "crz_fl": None}
    assert init_a_fields(screens[-1]) == {"ci": 10, "crz_fl": 160}


def test_rejected_zfw_stays_empty() -> None:
    screens = [s for s in settled() if classify(s) is PageId.INIT_B]
    assert screens
    assert all(init_b_fields(s) == {"zfw": None} for s in screens)


def test_scratchpad_typing_is_visible() -> None:
    pads = [s.scratchpad for s in settled() if classify(s) is PageId.INIT_B]
    assert [p for p in pads if p[:1].isdigit()] == ["6", "65", "65/", "65/6", "65/65"]
