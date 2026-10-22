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
    for raw in [
        "event:left:INIT",
        'print:{"lines":[]}',
        "requestUpdate",
        "update:not json",
        "update:[1]",
        "",
    ]:
        assert parse_frame(raw) is None


def test_page_number_and_scratchpad() -> None:
    raw = update_frame(
        side("{white}X{end}", [], page="{small}1/3{end}", scratchpad="{amber}NOT ALLOWED{end}")
    )
    frame = parse_frame(raw)
    assert isinstance(frame, Update)
    assert frame.left.page == "1/3"
    assert frame.left.scratchpad == "NOT ALLOWED"


def test_short_and_missing_rows_are_empty() -> None:
    frame = parse_frame(
        'update:{"left":{"title":"{white}X{end}","lines":[["{white}L{end}"]]},"right":{}}'
    )
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
