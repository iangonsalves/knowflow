import threading

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.embeddings import factory
from app.main import app


def deployment_settings(**overrides) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        embedding_backend="onnx",
        embedding_batch_size=1,
        run_worker_in_api=True,
        worker_poll_interval_seconds=600,
        **overrides,
    )


def test_default_app_lifecycle_does_not_start_worker(monkeypatch) -> None:
    import app.main as main

    monkeypatch.setattr(main, "settings", Settings(_env_file=None, app_env="test"))
    monkeypatch.setattr(
        main,
        "initialize_shared_embedding_provider",
        lambda *_args: (_ for _ in ()).throw(AssertionError("provider should stay lazy")),
    )

    with TestClient(app):
        assert app.state.embedding_provider_ready is True
        assert app.state.worker_thread is None


def test_enabled_lifecycle_shares_provider_and_shuts_worker_down(monkeypatch) -> None:
    import app.main as main

    settings = deployment_settings()
    provider = object()
    worker_started = threading.Event()
    worker_stopped = threading.Event()
    observed = {}

    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(factory, "_create_embedding_provider", lambda _settings: provider)
    monkeypatch.setattr(main, "get_object_storage", lambda: object())

    def fake_worker(**kwargs):
        observed.update(kwargs)
        worker_started.set()
        kwargs["stop_event"].wait(timeout=3)
        worker_stopped.set()

    monkeypatch.setattr(main, "run_worker", fake_worker)
    try:
        with TestClient(app):
            assert worker_started.wait(timeout=2)
            assert app.state.embedding_provider_ready is True
            assert app.state.worker_thread.is_alive()
            assert factory.get_embedding_provider(settings) is provider
            assert observed["embedding_provider"] is provider
            assert observed["settings"].embedding_batch_size == 1
            assert observed["settings"].worker_poll_interval_seconds == 600
            from app.jobs.worker import wake_in_process_worker

            observed["wakeup_event"].clear()
            wake_in_process_worker()
            assert observed["wakeup_event"].is_set()
        assert worker_stopped.is_set()
        assert not app.state.worker_thread.is_alive()
    finally:
        factory.clear_shared_embedding_provider()


def test_deployment_readiness_requires_initialized_provider_and_live_worker(monkeypatch) -> None:
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.api import health

    class Result:
        def __init__(self, value=None):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, statement):
            return Result("vector" if "pg_extension" in str(statement) else None)

    class Engine:
        def connect(self):
            return Connection()

    class Worker:
        def is_alive(self):
            return True

    settings = deployment_settings()
    monkeypatch.setattr(health, "engine", Engine())
    monkeypatch.setattr(health, "get_settings", lambda: settings)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(embedding_provider_ready=True, worker_thread=Worker())
        )
    )

    assert health.readiness(request) == {
        "status": "ready",
        "database": "ready",
        "vector_extension": "ready",
        "embedding_provider": "ready",
        "worker": "ready",
    }
    request.app.state.embedding_provider_ready = False
    try:
        health.readiness(request)
    except HTTPException as error:
        assert error.status_code == 503
    else:
        raise AssertionError("readiness accepted an uninitialized embedding provider")
