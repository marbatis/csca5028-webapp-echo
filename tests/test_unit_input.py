from src.app import normalize_user_input


def test_normalize_user_input_trims_whitespace() -> None:
    raw_input = "   Boulder weather alert   "
    expected_output = "Boulder weather alert"

    assert normalize_user_input(raw_input) == expected_output
