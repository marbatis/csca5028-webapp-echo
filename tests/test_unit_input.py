from src.app import build_external_detail_url, normalize_user_input, parse_int, summarize_inventory


def test_normalize_user_input_trims_whitespace() -> None:
    raw_input = "   Boulder weather alert   "
    expected_output = "Boulder weather alert"

    assert normalize_user_input(raw_input) == expected_output


def test_parse_int_handles_empty_and_valid_values() -> None:
    assert parse_int(None) is None
    assert parse_int("") is None
    assert parse_int("  ") is None
    assert parse_int("1987") == 1987
    assert parse_int("  1990  ") == 1990


def test_parse_int_returns_none_for_non_numeric_value() -> None:
    assert parse_int("year1987") is None


def test_summarize_inventory_returns_correct_rollup() -> None:
    summary = summarize_inventory(
        [
            {"model_year": 1987},
            {"model_year": 1987},
            {"model_year": 1988},
        ]
    )
    assert summary == {
        "total_records": 3,
        "distinct_years": 2,
        "year_start": 1987,
        "year_end": 1988,
    }


def test_build_external_detail_url_prefers_marketplace_payload_url() -> None:
    row = {
        "source": "CLASSICCARS_LISTINGS",
        "external_id": "CC-123",
        "model_year": 1987,
        "model_name": "1987 Toyota Land Cruiser",
        "payload_json": (
            '{"marketplace":"ClassicCars.com","url":"https://www.classiccars.com/listings/view/123/"}'
        ),
    }
    assert build_external_detail_url(row) == "https://www.classiccars.com/listings/view/123/"
