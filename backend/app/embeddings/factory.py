"""Configured local embedding factory shared by API and worker processes."""

from functools import lru_cache

from app.core.config import Settings
from app.embeddings.provider import EmbeddingProvider
from app.embeddings.sentence_transformers import SentenceTransformerEmbeddingProvider


def get_embedding_provider(settings: Settings) -> EmbeddingProvider:
    return SentenceTransformerEmbeddingProvider(
        model_name=settings.embedding_model,
        revision=settings.embedding_revision,
        dimensions=settings.embedding_dimensions,
        version=settings.embedding_version,
        cache_dir=settings.embedding_cache_dir,
        device=settings.embedding_device,
        batch_size=settings.embedding_batch_size,
        model_loader=lambda model_name, revision, cache_dir, device: _load_model(
            model_name, revision, cache_dir, device
        ),
    )


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
