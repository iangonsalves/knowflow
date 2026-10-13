"""Embedding provider contract and safe failure classifications."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


class EmbeddingError(Exception):
    """A provider error safe to classify for the durable worker."""

    code = "embedding_failed"
    safe_message = "The document could not be embedded."
    retryable = False


class EmbeddingConfigurationError(EmbeddingError):
    code = "embedding_not_configured"
    safe_message = "The local embedding model is not available or configured correctly."


class EmbeddingTransientError(EmbeddingError):
    code = "embedding_temporarily_unavailable"
    safe_message = "The local embedding model could not load temporarily. Processing will retry."
    retryable = True


class EmbeddingPermanentError(EmbeddingError):
    code = "embedding_request_rejected"
    safe_message = "The local embedding model rejected the input."


class EmbeddingResponseError(EmbeddingError):
    code = "invalid_embedding_response"
    safe_message = "The local embedding model returned an invalid vector."


@dataclass(frozen=True)
class EmbeddingSet:
    model: str
    version: str
    dimensions: int
    vectors: list[list[float]]


class EmbeddingProvider(Protocol):
    def embed(
        self,
        texts: list[str],
        *,
        purpose: str,
        progress: Callable[[], None] | None = None,
    ) -> EmbeddingSet:
        """Embed ordered passages for `document` or `query` retrieval use."""
