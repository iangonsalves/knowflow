"""Compare pinned PyTorch and quantized ONNX outputs on the real sample PDFs."""

from __future__ import annotations

import json
import math
from pathlib import Path

from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

from app.core.config import Settings
from app.embeddings.factory import _load_onnx_runtime
from app.embeddings.onnx_runtime import ONNXEmbeddingProvider
from app.embeddings.sentence_transformers import SentenceTransformerEmbeddingProvider
from app.processing.chunking import chunk_pages
from app.processing.extraction import ExtractedPage, normalize_page_text


def cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True)) / (
        math.sqrt(sum(value * value for value in left))
        * math.sqrt(sum(value * value for value in right))
    )


def sample_chunks(sample_dir: Path, settings: Settings) -> list[tuple[str, str, int]]:
    output = []
    for path in sorted(sample_dir.glob("*.pdf")):
        pages = [
            ExtractedPage(
                page_number=index,
                text=normalize_page_text(page.extract_text() or ""),
                content_hash="comparison",
            )
            for index, page in enumerate(PdfReader(str(path)).pages, start=1)
        ]
        chunks = chunk_pages(
            pages,
            chunk_size_chars=settings.chunk_size_chars,
            overlap_chars=settings.chunk_overlap_chars,
        )
        output.extend((path.name, chunk.text, chunk.page_start) for chunk in chunks)
    if not output:
        raise RuntimeError(f"No PDF chunks found in {sample_dir}")
    return output


def normalized(vectors: list[list[float]]) -> bool:
    return all(abs(math.sqrt(sum(value * value for value in row)) - 1.0) < 1e-4 for row in vectors)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=Path, default=Path("/samples"))
    parser.add_argument("--reference-model", type=Path, default=Path("/opt/reference-e5"))
    args = parser.parse_args()
    settings = Settings(_env_file=None, app_env="test", embedding_backend="onnx")
    corpus = sample_chunks(args.samples, settings)
    texts = [entry[1] for entry in corpus]
    queries = [
        "How much vacation time do staff get?",
        "How much annual leave do employees receive?",
        "How many days can employees work remotely?",
        "What is the maternity leave entitlement?",
    ]

    started_model = SentenceTransformer(
        str(args.reference_model), device="cpu", local_files_only=True
    )
    torch_provider = SentenceTransformerEmbeddingProvider(
        model_name=settings.embedding_model,
        revision=settings.embedding_revision,
        dimensions=settings.embedding_dimensions,
        version=settings.embedding_version,
        cache_dir=settings.embedding_cache_dir,
        device="cpu",
        batch_size=settings.embedding_batch_size,
        model_loader=lambda *_args: started_model,
    )
    onnx_provider = ONNXEmbeddingProvider(
        model_name=settings.embedding_model,
        revision=settings.embedding_revision,
        dimensions=settings.embedding_dimensions,
        version=settings.embedding_version,
        model_path=settings.embedding_onnx_model_path,
        tokenizer_path=settings.embedding_tokenizer_path,
        cache_dir=settings.embedding_cache_dir,
        batch_size=settings.embedding_batch_size,
        runtime_loader=lambda model_path, tokenizer_path, cache_dir: _load_onnx_runtime(
            model_path, tokenizer_path, cache_dir
        ),
    )

    torch_passages = torch_provider.embed(texts, purpose="document").vectors
    onnx_passages = onnx_provider.embed(texts, purpose="document").vectors
    torch_queries = torch_provider.embed(queries, purpose="query").vectors
    onnx_queries = onnx_provider.embed(queries, purpose="query").vectors

    vector_cosines = [
        cosine(torch_vector, onnx_vector)
        for torch_vector, onnx_vector in zip(
            torch_passages + torch_queries,
            onnx_passages + onnx_queries,
            strict=True,
        )
    ]
    rankings = []
    for index, query in enumerate(queries):
        ranks = {
            "pytorch_query_pytorch_passages": sorted(
                range(len(texts)),
                key=lambda i: cosine(torch_queries[index], torch_passages[i]),
                reverse=True,
            ),
            "onnx_query_onnx_passages": sorted(
                range(len(texts)),
                key=lambda i: cosine(onnx_queries[index], onnx_passages[i]),
                reverse=True,
            ),
            "onnx_query_existing_pytorch_passages": sorted(
                range(len(texts)),
                key=lambda i: cosine(onnx_queries[index], torch_passages[i]),
                reverse=True,
            ),
        }
        target_indexes = [
            i
            for i, (filename, text, _page) in enumerate(corpus)
            if "KnowFlow_Sample_HR_Policies" in filename and "25 working days" in text
        ]
        rankings.append(
            {
                "query": query,
                "pytorch_top": corpus[ranks["pytorch_query_pytorch_passages"][0]],
                "onnx_top": corpus[ranks["onnx_query_onnx_passages"][0]],
                "onnx_query_existing_pytorch_passages_top": corpus[
                    ranks["onnx_query_existing_pytorch_passages"][0]
                ],
                "pytorch_vs_onnx_top1_same": ranks["pytorch_query_pytorch_passages"][0]
                == ranks["onnx_query_onnx_passages"][0],
                "annual_leave_in_top_5_torch": any(
                    candidate in ranks["pytorch_query_pytorch_passages"][:5]
                    for candidate in target_indexes
                ),
                "annual_leave_in_top_5_onnx": any(
                    candidate in ranks["onnx_query_onnx_passages"][:5]
                    for candidate in target_indexes
                ),
                "annual_leave_in_top_5_onnx_query_torch_passages": any(
                    candidate in ranks["onnx_query_existing_pytorch_passages"][:5]
                    for candidate in target_indexes
                ),
            }
        )

    report = {
        "pytorch_model": settings.embedding_model_identifier,
        "onnx_model": settings.embedding_model_identifier,
        "vector_dimension": settings.embedding_dimensions,
        "query_prefix": "query: ",
        "passage_prefix": "passage: ",
        "pytorch_normalized": normalized(torch_passages + torch_queries),
        "onnx_normalized": normalized(onnx_passages + onnx_queries),
        "paired_vector_cosine": {
            "count": len(vector_cosines),
            "minimum": min(vector_cosines),
            "median": sorted(vector_cosines)[len(vector_cosines) // 2],
            "mean": sum(vector_cosines) / len(vector_cosines),
        },
        "same_space_compatibility_policy": (
            "Do not infer compatibility from dimensions alone. Inspect paired-vector cosine and "
            "cross-provider retrieval ranks; if meaningful ranking drift appears, re-embed "
            "all active documents."
        ),
        "retrieval_comparison": rankings,
    }
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
