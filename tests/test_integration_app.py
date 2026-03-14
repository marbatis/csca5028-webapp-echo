from unittest.mock import patch

from src.app import app


def test_home_page_renders_reporting_sections() -> None:
    with app.test_client() as client:
        response = client.get("/")

    assert response.status_code == 200
    assert b"Inventory Report" in response.data
    assert b"Total Records" in response.data
    assert b"API endpoints" in response.data
    assert b"Year scope is locked to" in response.data


def test_echo_endpoint_returns_submitted_text() -> None:
    with app.test_client() as client:
        response = client.post("/echo", data={"user_input": "Boulder"}, follow_redirects=True)

    assert response.status_code == 200
    assert b"You entered:" in response.data
    assert b"Boulder" in response.data


def test_health_endpoint_returns_ok_and_database_status() -> None:
    with app.test_client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["database"] == "ok"
    assert "timestamp_utc" in payload


def test_inventory_api_supports_filters() -> None:
    with app.test_client() as client:
        response = client.get("/api/v1/inventory?min_year=1987&max_year=1987&model_contains=lx")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] >= 1
    assert any("LX" in row["model_name"].upper() for row in payload["items"])
    assert all(int(row["model_year"]) == 1987 for row in payload["items"])


def test_inventory_api_enforces_project_year_scope() -> None:
    with app.test_client() as client:
        response = client.get("/api/v1/inventory?min_year=1980&max_year=1990")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] > 0
    assert all(int(row["model_year"]) == 1987 for row in payload["items"])


def test_summary_api_returns_rollup() -> None:
    with app.test_client() as client:
        _ = client.get("/")
        response = client.get("/api/v1/summary")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total_records"] > 0
    assert payload["distinct_years"] == 1
    assert payload["year_start"] == 1987
    assert payload["year_end"] == 1987
    assert payload["request_count"] >= 2


def test_metrics_endpoint_returns_prometheus_text() -> None:
    with app.test_client() as client:
        response = client.get("/metrics")

    assert response.status_code == 200
    assert b"app_requests_total" in response.data
    assert b"inventory_records_total" in response.data


def test_summary_endpoint_with_mocked_rows() -> None:
    mocked_rows = [
        {"model_year": 1987},
        {"model_year": 1987},
        {"model_year": 1988},
    ]
    with patch("src.app.fetch_inventory_rows", return_value=mocked_rows):
        with app.test_client() as client:
            response = client.get("/api/v1/summary")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total_records"] == 3
    assert payload["distinct_years"] == 2
    assert payload["year_start"] == 1987
    assert payload["year_end"] == 1988
