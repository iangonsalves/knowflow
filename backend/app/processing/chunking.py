"""Deterministic, page-preserving character chunking for later retrieval stages."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256

from app.processing.extraction import ExtractedPage


@dataclass(frozen=True)
class PreparedChunk:
    chunk_index: int
    text: str
    page_start: int
    page_end: int
    content_hash: str


def chunk_pages(
    pages: list[ExtractedPage],
    *,
    chunk_size_chars: int,
    overlap_chars: int,
    progress: Callable[[], None] | None = None,
) -> list[PreparedChunk]:
    """Split each normalized page in order, preferring paragraph and sentence breaks."""
    if chunk_size_chars < 1:
        raise ValueError("chunk_size_chars must be positive")
    if overlap_chars < 0 or overlap_chars >= chunk_size_chars:
        raise ValueError("overlap_chars must be nonnegative and smaller than chunk size")

    prepared: list[PreparedChunk] = []
    for page in pages:
        if progress is not None:
            progress()
        text = page.text.strip()
        if not text:
            continue
        for part in _split_text(text, chunk_size_chars, overlap_chars):
            prepared.append(
                PreparedChunk(
                    chunk_index=len(prepared),
                    text=part,
                    page_start=page.page_number,
                    page_end=page.page_number,
                    content_hash=sha256(part.encode("utf-8")).hexdigest(),
                )
            )
    return prepared


def _split_text(text: str, chunk_size_chars: int, overlap_chars: int) -> list[str]:
    if len(text) <= chunk_size_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        hard_end = min(start + chunk_size_chars, len(text))
        end = hard_end
        if hard_end < len(text):
            end = _preferred_boundary(text, start, hard_end, chunk_size_chars)
        value = text[start:end].strip()
        if value:
            chunks.append(value)
        if end >= len(text):
            break

        next_start = max(start + 1, end - overlap_chars)
        while next_start < end and text[next_start].isspace():
            next_start += 1
        start = next_start
    return chunks


def _preferred_boundary(text: str, start: int, end: int, chunk_size_chars: int) -> int:
    floor = start + max(1, int(chunk_size_chars * 0.65))
    paragraph = text.rfind("\n\n", floor, end)
    if paragraph >= floor:
        return paragraph

    sentence_matches = list(re.finditer(r"[.!?](?:[\"')\]]*)\s+", text[floor:end]))
    if sentence_matches:
        return floor + sentence_matches[-1].end()

    whitespace = max(text.rfind(" ", floor, end), text.rfind("\n", floor, end))
    if whitespace >= floor:
        return whitespace
    return end
