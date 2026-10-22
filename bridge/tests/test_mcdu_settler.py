from companion.mcdu import McduScreen, Settler, Update, parse_frame
from tests.mcdu_samples import Side, fpln, init_a, init_b, update_frame


def screen(side: Side) -> McduScreen:
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
