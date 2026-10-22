import pytest

from companion.mcdu import (
    McduScreen,
    PageId,
    Update,
    classify,
    describe,
    init_a_fields,
    init_b_fields,
    parse_frame,
)
from tests.mcdu_samples import (
    Side,
    data_index,
    fpln,
    init_a,
    init_b,
    perf_appr,
    perf_to,
    update_frame,
)


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
