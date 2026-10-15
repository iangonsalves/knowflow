"""Configured local embedding factory shared by API and worker processes."""

from functools import lru_cache
from threading import Lock

from app.core.config import Settings
from app.embeddings.onnx_runtime import ONNXEmbeddingProvider, _load_runtime
from app.embeddings.provider import EmbeddingProvider
from app.embeddings.sentence_transformers import SentenceTransformerEmbeddingProvider

_shared_provider: EmbeddingProvider | None = None
_shared_provider_lock = Lock()


def get_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.run_worker_in_api:
        return initialize_shared_embedding_provider(settings)
    return _create_embedding_provider(settings)


def initialize_shared_embedding_provider(settings: Settings) -> EmbeddingProvider:
    """Initialize one provider object shared by API requests and in-process worker."""
    global _shared_provider
    if not settings.run_worker_in_api:
        raise ValueError("shared embedding provider is only used by in-process worker mode")
    with _shared_provider_lock:
        if _shared_provider is None:
            _shared_provider = _create_embedding_provider(settings)
        return _shared_provider


def clear_shared_embedding_provider() -> None:
    """Release the deployment provider reference after the app worker stops."""
    global _shared_provider
    with _shared_provider_lock:
        _shared_provider = None
        _load_onnx_runtime.cache_clear()


def _create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_backend == "onnx":
        return ONNXEmbeddingProvider(
            model_name=settings.embedding_model,
            revision=settings.embedding_revision,
            dimensions=settings.embedding_dimensions,
            version=settings.embedding_storage_version,
            model_path=settings.embedding_onnx_model_path,
            tokenizer_path=settings.embedding_tokenizer_path,
            cache_dir=settings.embedding_cache_dir,
            batch_size=settings.embedding_batch_size,
            runtime_loader=lambda model_path, tokenizer_path, cache_dir: _load_onnx_runtime(
                model_path, tokenizer_path, cache_dir
            ),
        )
    return SentenceTransformerEmbeddingProvider(
        model_name=settings.embedding_model,
        revision=settings.embedding_revision,
        dimensions=settings.embedding_dimensions,
        version=settings.embedding_storage_version,
        cache_dir=settings.embedding_cache_dir,
        device=settings.embedding_device,
        batch_size=settings.embedding_batch_size,
        model_loader=lambda model_name, revision, cache_dir, device: _load_model(
            model_name, revision, cache_dir, device
        ),
    )


@lru_cache(maxsize=2)
def _load_onnx_runtime(model_path: str, tokenizer_path: str, cache_dir: str):
    """Reuse one tokenizer/session per Python process, as the PyTorch path does."""
    return _load_runtime(model_path, tokenizer_path, cache_dir)


@lru_cache(maxsize=2)
def _load_model(model_name: str, revision: str, cache_dir: str, device: str):
    """Load once per process so requests/jobs reuse model weights and runtime memory."""
    from pathlib import Path

    from sentence_transformers import SentenceTransformer

    try:
        cache_path = Path(cache_dir)
        cache_path.mkdir(parents=True, exist_ok=True)
        ready_marker = cache_path / f"knowflow-{revision}.ready"
        model = SentenceTransformer(
            model_name,
            revision=revision,
            cache_folder=cache_dir,
            device=device,
            local_files_only=ready_marker.exists(),
        )
        # A marker is written only after Sentence Transformers loaded the full model.
        # Interrupted downloads are retried online; complete caches work offline.
        ready_marker.touch(exist_ok=True)
        return model
    except OSError as error:
        # Hub/model file errors can be transient during the first cache download.
        from app.embeddings.provider import EmbeddingTransientError

        raise EmbeddingTransientError from error
