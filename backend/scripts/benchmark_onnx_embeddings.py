"""Measure E5 ONNX RSS/latency in the current Linux container process."""

from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
from pathlib import Path


def process_rss_mib() -> float:
    status = Path("/proc/self/status").read_text()
    for line in status.splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024
    raise RuntimeError("/proc/self/status does not contain VmRSS")


def process_hwm_mib() -> float:
    status = Path("/proc/self/status").read_text()
    for line in status.splitlines():
        if line.startswith("VmHWM:"):
            return int(line.split()[1]) / 1024
    return process_rss_mib()


def cgroup_value(paths: tuple[str, ...]) -> int | None:
    for candidate in paths:
        path = Path(candidate)
        if path.is_file():
            value = path.read_text().strip()
            if value != "max":
                return int(value)
    return None


def pdf_chunks(pdf_path: Path, chunk_size: int, overlap: int) -> list[str]:
    from pypdf import PdfReader

    from app.processing.chunking import chunk_pages
    from app.processing.extraction import ExtractedPage, normalize_page_text

    pages = [
        ExtractedPage(
            page_number=index,
            text=normalize_page_text(page.extract_text() or ""),
            content_hash="benchmark",
        )
        for index, page in enumerate(PdfReader(str(pdf_path)).pages, start=1)
    ]
    chunks = chunk_pages(pages, chunk_size_chars=chunk_size, overlap_chars=overlap)
    return [chunk.text for chunk in chunks]


class PeakSampler:
    def __init__(self) -> None:
        self.peak = process_rss_mib()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._sample, daemon=True)

    def _sample(self) -> None:
        while not self.stop_event.wait(0.02):
            self.peak = max(self.peak, process_rss_mib())

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_exc):
        self.stop_event.set()
        self.thread.join()
        self.peak = max(self.peak, process_rss_mib(), process_hwm_mib())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--chunks", type=int, default=80)
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()

    def checkpoint(label: str) -> None:
        print(f"[benchmark] {label}; process_rss_mib={process_rss_mib():.2f}", flush=True)

    # Importing the FastAPI application captures the real backend process baseline,
    # while the ONNX runtime/model remain lazy-loaded just as they are in the API.
    print("[benchmark] importing FastAPI application", flush=True)
    from app.main import app  # noqa: F401

    baseline = process_rss_mib()
    checkpoint("FastAPI application imported")
    import onnxruntime as ort
    import tokenizers

    runtime_imported = process_rss_mib()
    checkpoint("ONNX Runtime and tokenizers imported")
    from app.core.config import Settings
    from app.embeddings.factory import _load_onnx_runtime
    from app.embeddings.onnx_runtime import ONNXEmbeddingProvider

    settings = Settings(
        _env_file=None,
        app_env="test",
        embedding_backend="onnx",
        embedding_batch_size=args.batch_size,
    )
    started = time.perf_counter()
    checkpoint("starting ONNX model/session initialization")
    with PeakSampler() as model_sampler:
        provider = ONNXEmbeddingProvider(
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
        init_seconds = time.perf_counter() - started
        after_model_load = process_rss_mib()
    model_load_peak = model_sampler.peak
    checkpoint(f"model/session initialized in {init_seconds:.3f}s")

    query = "How much vacation time do staff get?"
    query_latencies = []
    query_result = None
    checkpoint("starting query embedding")
    with PeakSampler() as query_sampler:
        for _ in range(6):
            query_started = time.perf_counter()
            query_result = provider.embed([query], purpose="query")
            query_latencies.append((time.perf_counter() - query_started) * 1000)
    query_peak = query_sampler.peak
    after_query = process_rss_mib()
    checkpoint("query embedding complete")

    checkpoint("extracting sample PDF and constructing chunks")
    chunks = pdf_chunks(args.pdf, settings.chunk_size_chars, settings.chunk_overlap_chars)
    if not chunks:
        raise RuntimeError("The sample PDF produced no chunks")
    actual_chunk_count = len(chunks)
    # Repeat real sample passages for a bounded, representative document batch.
    workload = [chunks[index % len(chunks)] for index in range(args.chunks)]
    checkpoint(f"starting document embedding: {len(workload)} chunks, batch_size={args.batch_size}")
    document_progress = 0

    def report_document_batch() -> None:
        nonlocal document_progress
        document_progress = min(document_progress + args.batch_size, len(workload))
        checkpoint(f"document embedding batch complete: {document_progress}/{len(workload)}")

    with PeakSampler() as document_sampler:
        document_started = time.perf_counter()
        document_result = provider.embed(
            workload, purpose="document", progress=report_document_batch
        )
        document_seconds = time.perf_counter() - document_started
    document_peak = document_sampler.peak
    after_document = process_rss_mib()
    checkpoint("document embedding complete")

    artifact_path = Path(settings.embedding_onnx_model_path)
    tokenizer_path = Path(settings.embedding_tokenizer_path)
    artifact_size = artifact_path.stat().st_size
    limit_bytes = cgroup_value(
        ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes")
    )
    cgroup_peak = cgroup_value(
        ("/sys/fs/cgroup/memory.peak", "/sys/fs/cgroup/memory/memory.max_usage_in_bytes")
    )
    peak_rss = max(model_load_peak, query_peak, document_peak, process_hwm_mib())
    peak_container_mib = cgroup_peak / (1024 * 1024) if cgroup_peak else None
    limit_mib = limit_bytes / (1024 * 1024) if limit_bytes else None
    measured_peak = max(peak_rss, peak_container_mib or 0.0)
    headroom = limit_mib - measured_peak if limit_mib else None
    output = {
        "measurement_units": "MiB, milliseconds, seconds",
        "embedding_backend": "onnxruntime CPUExecutionProvider",
        "onnxruntime_version": ort.__version__,
        "tokenizers_version": tokenizers.__version__,
        "cpu_providers": provider.session.get_providers(),
        "model": settings.embedding_model_identifier,
        "dimensions": settings.embedding_dimensions,
        "query_prefix": "query: ",
        "passage_prefix": "passage: ",
        "normalized": all(
            abs(sum(value * value for value in row) ** 0.5 - 1.0) < 1e-4
            for row in (query_result.vectors[0], document_result.vectors[0])
        ),
        "rss_mib": {
            "backend_baseline_after_fastapi_import": round(baseline, 2),
            "after_onnxruntime_and_tokenizers_import": round(runtime_imported, 2),
            "after_model_session_load": round(after_model_load, 2),
            "after_query_embedding": round(after_query, 2),
            "after_document_chunk_embedding": round(after_document, 2),
            "peak_during_model_session_initialization": round(model_load_peak, 2),
            "peak_during_query_embedding": round(query_peak, 2),
            "peak_during_document_embedding": round(document_peak, 2),
            "sampled_peak_process_rss": round(peak_rss, 2),
            "container_cgroup_peak": round(peak_container_mib, 2) if peak_container_mib else None,
            "container_memory_limit": round(limit_mib, 2) if limit_mib else None,
            "headroom_to_container_limit": round(headroom, 2) if headroom is not None else None,
            "recommended_pass_peak_mib": 384,
            "recommended_minimum_headroom_mib": 128,
        },
        "latency": {
            "model_session_initialization_seconds": round(init_seconds, 3),
            "query_embedding_median_ms": round(statistics.median(query_latencies[1:]), 2),
            "query_embedding_samples_ms": [round(value, 2) for value in query_latencies[1:]],
            "document_chunks": len(workload),
            "unique_sample_pdf_chunks": actual_chunk_count,
            "document_embedding_seconds": round(document_seconds, 3),
            "document_chunks_per_second": round(len(workload) / document_seconds, 2),
        },
        "artifacts": {
            "onnx_model_path": str(artifact_path),
            "onnx_model_bytes": artifact_size,
            "onnx_model_mib": round(artifact_size / (1024 * 1024), 2),
            "tokenizer_bytes": tokenizer_path.stat().st_size,
            "total_model_bytes": artifact_size + tokenizer_path.stat().st_size,
        },
        "memory_candidate_pass": bool(
            limit_mib and headroom is not None and measured_peak <= 384 and headroom >= 128
        ),
        "note": (
            "A process killed by the 512 MiB cgroup may not print this report; "
            "check Docker exit/OOM status."
        ),
    }
    print(json.dumps(output, indent=2), flush=True)


if __name__ == "__main__":
    main()
