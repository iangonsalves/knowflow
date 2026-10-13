"""Local CPU embeddings using a pretrained Sentence Transformers model."""

from collections.abc import Callable
from math import isfinite
from typing import Any

from app.embeddings.provider import (
    EmbeddingConfigurationError,
    EmbeddingPermanentError,
    EmbeddingResponseError,
    EmbeddingSet,
    EmbeddingTransientError,
)

MODEL_REVISION = "ffb93f3bd4047442299a41ebb6fa998a38507c52"
ModelLoader = Callable[[str, str, str, str], Any]


class SentenceTransformerEmbeddingProvider:
    """Embed E5 queries/passages locally; no inference API or credential is used."""

    def __init__(
        self,
        *,
        model_name: str,
        revision: str,
        dimensions: int,
        version: str,
        cache_dir: str,
        device: str,
        batch_size: int,
        model_loader: ModelLoader,
    ) -> None:
        if (
            model_name != "intfloat/e5-small-v2"
            or revision != MODEL_REVISION
            or dimensions != 384
        ):
            raise EmbeddingConfigurationError
        self.model_name = model_name
        self.dimensions = dimensions
        self.version = version
        self.batch_size = batch_size
        try:
            self.model = model_loader(model_name, revision, cache_dir, device)
        except EmbeddingConfigurationError:
            raise
        except EmbeddingTransientError:
            raise
        except (OSError, TimeoutError, ConnectionError) as error:
            raise EmbeddingTransientError from error
        except Exception as error:
            # Model import/runtime setup failures are configuration issues. Download and
            # transport errors should be exposed by the loader as transient failures.
            if isinstance(error, ModuleNotFoundError) and error.name == "sentence_transformers":
                raise EmbeddingConfigurationError from error
            if "huggingface" in type(error).__module__.lower() or "download" in str(error).lower():
                raise EmbeddingTransientError from error
            raise EmbeddingConfigurationError from error

    def embed(self, texts, *, purpose, progress=None) -> EmbeddingSet:
        if purpose not in {"document", "query"}:
            raise EmbeddingPermanentError
        if not texts:
            return EmbeddingSet(self._model_identifier, self.version, self.dimensions, [])

        prefix = "query: " if purpose == "query" else "passage: "
        vectors: list[list[float]] = []
        try:
            for start in range(0, len(texts), self.batch_size):
                batch = [prefix + text for text in texts[start : start + self.batch_size]]
                encoded = self.model.encode(
                    batch,
                    batch_size=self.batch_size,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
                rows = encoded.tolist() if hasattr(encoded, "tolist") else encoded
                for row in rows:
                    vector = [float(value) for value in row]
                    if len(vector) != self.dimensions or not all(isfinite(v) for v in vector):
                        raise EmbeddingResponseError
                    vectors.append(vector)
                if progress is not None:
                    progress()
        except EmbeddingResponseError:
            raise
        except (MemoryError, OSError, RuntimeError, TimeoutError) as error:
            raise EmbeddingTransientError from error
        except Exception as error:
            raise EmbeddingPermanentError from error

        if len(vectors) != len(texts):
            raise EmbeddingResponseError
        return EmbeddingSet(self._model_identifier, self.version, self.dimensions, vectors)

    @property
    def _model_identifier(self) -> str:
        return f"{self.model_name}@{MODEL_REVISION}"
