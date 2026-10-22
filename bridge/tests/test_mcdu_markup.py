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
