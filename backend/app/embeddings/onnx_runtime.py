"""CPU ONNX inference for the same pinned E5-small-v2 embedding model.

The ONNX graph must be exported/quantized from the exact configured model revision.
This module deliberately uses the light `tokenizers` runtime rather than importing
Sentence Transformers or PyTorch in the deployment process.
"""

from collections.abc import Callable
from pathlib import Path
from threading import Lock
from typing import Any

from app.embeddings.provider import (
    EmbeddingConfigurationError,
    EmbeddingPermanentError,
    EmbeddingResponseError,
    EmbeddingSet,
    EmbeddingTransientError,
)
from app.embeddings.sentence_transformers import MODEL_REVISION

RuntimeLoader = Callable[[str, str, str], tuple[Any, Any]]


def _load_runtime(model_path: str, tokenizer_path: str, cache_dir: str) -> tuple[Any, Any]:
    try:
        import onnxruntime as ort
        from tokenizers import Tokenizer
    except ImportError as error:
        raise EmbeddingConfigurationError from error

    if not Path(model_path).is_file() or not Path(tokenizer_path).is_file():
        raise EmbeddingConfigurationError

    try:
        tokenizer = Tokenizer.from_file(tokenizer_path)
        pad_id = tokenizer.token_to_id("[PAD]")
        if pad_id is None:
            raise EmbeddingConfigurationError
        tokenizer.enable_truncation(max_length=512)
        tokenizer.enable_padding(pad_id=pad_id, pad_type_id=0)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        session = ort.InferenceSession(
            model_path,
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        if session.get_providers() != ["CPUExecutionProvider"]:
            raise EmbeddingConfigurationError
        return tokenizer, session
    except EmbeddingConfigurationError:
        raise
    except (OSError, RuntimeError, ValueError) as error:
        raise EmbeddingTransientError from error


class ONNXEmbeddingProvider:
    """CPU-only E5 embeddings with the same query/passage and vector semantics."""

    def __init__(
        self,
        *,
        model_name: str,
        revision: str,
        dimensions: int,
        version: str,
        model_path: str,
        tokenizer_path: str,
        cache_dir: str,
        batch_size: int,
        runtime_loader: RuntimeLoader = _load_runtime,
    ) -> None:
        if model_name != "intfloat/e5-small-v2" or revision != MODEL_REVISION or dimensions != 384:
            raise EmbeddingConfigurationError
        self.model_name = model_name
        self.revision = revision
        self.dimensions = dimensions
        self.version = version
        self.batch_size = batch_size
        # FastAPI query requests and the in-process worker share this instance.
        # Serialize inference so a query cannot overlap a document batch and spike
        # memory beyond the measured single-inference footprint.
        self._inference_lock = Lock()
        try:
            self.tokenizer, self.session = runtime_loader(model_path, tokenizer_path, cache_dir)
            self.input_names = {item.name for item in self.session.get_inputs()}
            outputs = self.session.get_outputs()
            if not outputs or not {"input_ids", "attention_mask"}.issubset(self.input_names):
                raise EmbeddingConfigurationError
            self.output_name = outputs[0].name
        except EmbeddingConfigurationError:
            raise
        except (OSError, RuntimeError, ValueError) as error:
            raise EmbeddingTransientError from error

    def embed(self, texts, *, purpose, progress=None) -> EmbeddingSet:
        with self._inference_lock:
            return self._embed_locked(texts, purpose=purpose, progress=progress)

    def _embed_locked(self, texts, *, purpose, progress=None) -> EmbeddingSet:
        if purpose not in {"document", "query"}:
            raise EmbeddingPermanentError
        if not texts:
            return EmbeddingSet(self._model_identifier, self.version, self.dimensions, [])

        try:
            import numpy as np
        except ImportError as error:
            raise EmbeddingConfigurationError from error

        prefix = "query: " if purpose == "query" else "passage: "
        vectors: list[list[float]] = []
        try:
            for start in range(0, len(texts), self.batch_size):
                batch = [prefix + text for text in texts[start : start + self.batch_size]]
                encoded = self.tokenizer.encode_batch(batch)
                inputs: dict[str, Any] = {
                    "input_ids": np.asarray([item.ids for item in encoded], dtype=np.int64),
                    "attention_mask": np.asarray(
                        [item.attention_mask for item in encoded], dtype=np.int64
                    ),
                }
                if "token_type_ids" in self.input_names:
                    inputs["token_type_ids"] = np.asarray(
                        [item.type_ids for item in encoded], dtype=np.int64
                    )
                inputs = {key: value for key, value in inputs.items() if key in self.input_names}
                raw_embeddings = np.asarray(self.session.run([self.output_name], inputs)[0])
                attention_mask = np.asarray(
                    [item.attention_mask for item in encoded], dtype=np.float32
                )
                if (
                    raw_embeddings.ndim != 3
                    or raw_embeddings.shape[0] != len(encoded)
                    or raw_embeddings.shape[1] != attention_mask.shape[1]
                    or raw_embeddings.shape[2] != self.dimensions
                ):
                    raise EmbeddingResponseError

                # Pool in NumPy while the runtime output is still a compact
                # float32 array. Converting the full [batch, tokens, dims]
                # tensor to nested Python floats can use hundreds of MiB on
                # its own and is unnecessary; only the final [batch, dims]
                # vectors are converted for the API response.
                token_counts = attention_mask.sum(axis=1, keepdims=True)
                if bool((token_counts == 0).any()):
                    raise EmbeddingResponseError
                raw_embeddings *= attention_mask[:, :, None]
                pooled = raw_embeddings.sum(axis=1) / token_counts
                norms = np.linalg.norm(pooled, axis=1, keepdims=True)
                if bool((norms <= 1e-12).any()):
                    raise EmbeddingResponseError
                normalized = pooled / norms
                if not bool(np.isfinite(normalized).all()):
                    raise EmbeddingResponseError
                vectors.extend(normalized.tolist())
                if progress is not None:
                    progress()
        except EmbeddingResponseError:
            raise
        except EmbeddingConfigurationError:
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
        return f"{self.model_name}@{self.revision}"
