from src.app import app


def test_echo_endpoint_returns_submitted_text() -> None:
    with app.test_client() as client:
        response = client.post("/echo", data={"user_input": "Boulder"}, follow_redirects=True)

    assert response.status_code == 200
    assert b"You entered:" in response.data
    assert b"Boulder" in response.data


def test_health_endpoint_returns_ok() -> None:
    with app.test_client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
