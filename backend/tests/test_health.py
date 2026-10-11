from fastapi.testclient import TestClient

from app.api import health
from app.main import app


def test_liveness_reports_running_api() -> None:
    response = TestClient(app).get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness_reports_database_and_vector_extension(monkeypatch) -> None:
    class Result:
        def __init__(self, value: str | None = None) -> None:
            self.value = value

        def scalar_one_or_none(self) -> str | None:
            return self.value

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def execute(self, statement):
            if "pg_extension" in str(statement):
                return Result("vector")
            return Result()

    class Engine:
        def connect(self) -> Connection:
            return Connection()

    monkeypatch.setattr(health, "engine", Engine())
    response = TestClient(app).get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "ready",
        "vector_extension": "ready",
    }
