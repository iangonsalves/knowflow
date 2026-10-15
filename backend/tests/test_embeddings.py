from dataclasses import dataclass
from types import ModuleType

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.embeddings.factory import get_embedding_provider
from app.embeddings.provider import (
    EmbeddingConfigurationError,
    EmbeddingResponseError,
    EmbeddingSet,
    EmbeddingTransientError,
)
from app.embeddings.sentence_transformers import SentenceTransformerEmbeddingProvider


@dataclass
class FakeModel:
    dimension: int = 384
    inputs: list[str] | None = None

    def encode(self, texts, **kwargs):
        self.inputs = texts
        assert kwargs["convert_to_numpy"] is True
        assert kwargs["normalize_embeddings"] is True
        return [[1.0] + [0.0] * (self.dimension - 1) for _ in texts]


def make_provider(model=None, model_loader=None, **overrides):
    settings = Settings(_env_file=None, app_env="test", **overrides)
    fake = model or FakeModel()
    return SentenceTransformerEmbeddingProvider(
        model_name=settings.embedding_model,
        revision=settings.embedding_revision,
        dimensions=settings.embedding_dimensions,
        version=settings.embedding_version,
        cache_dir=settings.embedding_cache_dir,
        device=settings.embedding_device,
        batch_size=settings.embedding_batch_size,
        model_loader=model_loader or (lambda *_args: fake),
    ), fake


def test_local_model_generates_normalized_dimensioned_vectors_and_e5_prefixes() -> None:
    provider, model = make_provider()
    progress_calls = []

    result = provider.embed(
        ["The leave policy grants annual vacation."],
        purpose="document",
        progress=lambda: progress_calls.append(True),
    )

    assert result.model == settings_model_identifier()
    assert result.version == "v1"
    assert result.dimensions == 384
    assert len(result.vectors[0]) == 384
    assert model.inputs == ["passage: The leave policy grants annual vacation."]
    assert len(progress_calls) == 1

    provider.embed(["How much vacation?"], purpose="query")
    assert model.inputs == ["query: How much vacation?"]


def test_embedding_batches_are_bounded_and_order_is_preserved() -> None:
    provider, model = make_provider(embedding_batch_size=2)
    result = provider.embed(["one", "two", "three"], purpose="document")

    assert len(result.vectors) == 3
    assert model.inputs == ["passage: three"]


def test_empty_input_does_not_invoke_model() -> None:
    provider, _ = make_provider()
    assert provider.embed([], purpose="document") == EmbeddingSet(
        settings_model_identifier(), "v1", 384, []
    )


def test_vector_dimension_and_finite_values_are_validated() -> None:
    with pytest.raises(EmbeddingResponseError):
        provider, _ = make_provider(model=FakeModel(dimension=383))
        provider.embed(["text"], purpose="query")

    class NonFiniteModel:
        def encode(self, *_args, **_kwargs):
            return [[float("nan")] + [0.0] * 383]

    provider, _ = make_provider(model=NonFiniteModel())
    with pytest.raises(EmbeddingResponseError):
        provider.embed(["text"], purpose="query")


def test_only_selected_local_model_and_schema_dimensions_are_allowed() -> None:
    with pytest.raises(ValueError, match="changing them requires a migration"):
        Settings(_env_file=None, app_env="test", embedding_dimensions=768)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="test", embedding_version="v2")
    with pytest.raises(ValueError, match="changing them requires a migration"):
        Settings(_env_file=None, app_env="test", embedding_revision="main")
    with pytest.raises(EmbeddingConfigurationError):
        SentenceTransformerEmbeddingProvider(
            model_name="another/model",
            revision="ffb93f3bd4047442299a41ebb6fa998a38507c52",
            dimensions=384,
            version="v1",
            cache_dir="/models",
            device="cpu",
            batch_size=16,
            model_loader=lambda *_args: FakeModel(),
        )


def test_model_download_failure_is_retryable_and_startup_needs_no_api_key() -> None:
    settings = Settings(
        _env_file=None, app_env="test", embedding_backend="sentence_transformers"
    )
    assert settings.embedding_model == "intfloat/e5-small-v2"
    assert not hasattr(settings, "embedding_api_key")
    with pytest.raises(EmbeddingTransientError):
        make_provider(model_loader=lambda *_args: (_ for _ in ()).throw(OSError("offline")))


def test_factory_loads_local_model_and_reuses_process_cache(monkeypatch) -> None:
    from app.embeddings import factory

    model = FakeModel()
    calls = []
    monkeypatch.setattr(factory, "_load_model", lambda *args: calls.append(args) or model)
    settings = Settings(
        _env_file=None, app_env="test", embedding_backend="sentence_transformers"
    )
    first = get_embedding_provider(settings)
    second = get_embedding_provider(settings)
    assert isinstance(first, SentenceTransformerEmbeddingProvider)
    assert isinstance(second, SentenceTransformerEmbeddingProvider)
    assert first.model is second.model is model
    assert (
        calls
        == [
            (
                "intfloat/e5-small-v2",
                "ffb93f3bd4047442299a41ebb6fa998a38507c52",
                "/models",
                "cpu",
            )
        ]
        * 2
    )


def test_onnx_provider_uses_same_e5_prefix_dimensions_and_normalizes() -> None:
    from types import SimpleNamespace

    pytest.importorskip("numpy", reason="NumPy is installed by the opt-in ONNX runtime extra")

    from app.embeddings.onnx_runtime import ONNXEmbeddingProvider

    class Tokenizer:
        seen = []

        def encode_batch(self, texts):
            self.seen = texts
            return [
                SimpleNamespace(ids=[1, 2, 0], attention_mask=[1, 1, 0], type_ids=[0, 0, 0])
                for _ in texts
            ]

    class Session:
        def get_inputs(self):
            return [SimpleNamespace(name="input_ids"), SimpleNamespace(name="attention_mask")]

        def get_outputs(self):
            return [SimpleNamespace(name="last_hidden_state")]

        def get_providers(self):
            return ["CPUExecutionProvider"]

        def run(self, _outputs, inputs):
            self.inputs = inputs
            row = [[1.0] + [0.0] * 383, [0.0, 1.0] + [0.0] * 382, [0.0] * 384]
            return [[[list(token) for token in row] for _ in inputs["input_ids"]]]

    tokenizer, session = Tokenizer(), Session()
    settings = Settings(_env_file=None, app_env="test", embedding_backend="onnx")
    provider = ONNXEmbeddingProvider(
        model_name=settings.embedding_model,
        revision=settings.embedding_revision,
        dimensions=settings.embedding_dimensions,
        version=settings.embedding_version,
        model_path="model.onnx",
        tokenizer_path="tokenizer.json",
        cache_dir="/models",
        batch_size=4,
        runtime_loader=lambda *_args: (tokenizer, session),
    )

    result = provider.embed(["How much vacation?"], purpose="query")
    assert tokenizer.seen == ["query: How much vacation?"]
    assert set(session.inputs) == {"input_ids", "attention_mask"}
    assert result.model == settings_model_identifier()
    assert result.dimensions == 384
    assert len(result.vectors[0]) == 384
    assert abs(sum(value * value for value in result.vectors[0]) - 1.0) < 1e-9
    assert result.vectors[0][0] == pytest.approx(result.vectors[0][1])
    assert result.vectors[0][2:] == [0.0] * 382

    provider.embed(["Annual leave policy"], purpose="document")
    assert tokenizer.seen == ["passage: Annual leave policy"]


def test_factory_selects_onnx_provider_without_changing_model_identity(monkeypatch) -> None:
    from types import SimpleNamespace

    from app.embeddings import factory
    from app.embeddings.onnx_runtime import ONNXEmbeddingProvider

    class Session:
        def get_inputs(self):
            return [
                SimpleNamespace(name="input_ids"),
                SimpleNamespace(name="attention_mask"),
            ]

        def get_outputs(self):
            return [SimpleNamespace(name="embeddings")]

    sentinel = (object(), Session())
    calls = []
    monkeypatch.setattr(
        factory,
        "_load_onnx_runtime",
        lambda *args: calls.append(args) or sentinel,
    )
    settings = Settings(_env_file=None, app_env="test", embedding_backend="onnx")

    provider = get_embedding_provider(settings)
    assert isinstance(provider, ONNXEmbeddingProvider)
    assert provider.model_name == "intfloat/e5-small-v2"
    assert provider.revision == settings.embedding_revision
    assert provider.dimensions == 384
    assert provider.version == "v1-onnx-int8-matmul"
    assert calls == [
        (
            settings.embedding_onnx_model_path,
            settings.embedding_tokenizer_path,
            settings.embedding_cache_dir,
        )
    ]


def test_completed_model_cache_loads_offline_and_failed_load_is_not_marked(
    monkeypatch, tmp_path
) -> None:
    from app.embeddings import factory

    revision = "ffb93f3bd4047442299a41ebb6fa998a38507c52"
    options = []

    class Loader:
        def __init__(self, _name, **kwargs):
            options.append(kwargs)
            if kwargs["local_files_only"] is False and len(options) == 1:
                raise OSError("interrupted initial download")

    fake_library = ModuleType("sentence_transformers")
    fake_library.SentenceTransformer = Loader
    monkeypatch.setitem(__import__("sys").modules, "sentence_transformers", fake_library)

    with pytest.raises(EmbeddingTransientError):
        factory._load_model("intfloat/e5-small-v2", revision, str(tmp_path), "cpu")
    marker = tmp_path / f"knowflow-{revision}.ready"
    assert not marker.exists()

    factory._load_model("intfloat/e5-small-v2", revision, str(tmp_path), "cpu")
    assert marker.exists()
    factory._load_model.cache_clear()
    factory._load_model("intfloat/e5-small-v2", revision, str(tmp_path), "cpu")
    assert [option["local_files_only"] for option in options] == [False, False, True]


def settings_model_identifier() -> str:
    return "intfloat/e5-small-v2@ffb93f3bd4047442299a41ebb6fa998a38507c52"
