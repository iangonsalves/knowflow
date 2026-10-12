"""Provider-neutral PDF extraction with one normalized record per source page."""

import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from tempfile import SpooledTemporaryFile

from pypdf import PdfReader
from pypdf.errors import EmptyFileError, FileNotDecryptedError, PdfReadError

from app.db.models import Document
from app.documents.storage import ObjectStorage, ObjectStorageError, StoredObjectNotFound

DOWNLOAD_BLOCK_SIZE = 64 * 1024
SPOOL_MEMORY_LIMIT = 8 * 1024 * 1024


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    text: str
    content_hash: str


class ProcessingError(Exception):
    """A safe, classifiable document processing failure."""

    code = "document_processing_failed"
    safe_message = "The document could not be processed."
    retryable = False


class MissingSourceObject(ProcessingError):
    code = "source_object_missing"
    safe_message = "The stored PDF is missing. Re-upload the document."


class InvalidSourcePDF(ProcessingError):
    code = "invalid_source_pdf"
    safe_message = "The stored PDF is malformed or cannot be read."


class EncryptedSourcePDF(ProcessingError):
    code = "encrypted_pdf_unsupported"
    safe_message = "Password-protected PDFs cannot be processed."


class NoExtractableText(ProcessingError):
    code = "no_extractable_text"
    safe_message = "No selectable text was found. Scanned PDFs require OCR, which is not supported."


class SourceIntegrityError(ProcessingError):
    code = "source_integrity_error"
    safe_message = "The stored PDF did not match its upload metadata. Re-upload the document."


class TransientProcessingError(ProcessingError):
    code = "processing_temporarily_unavailable"
    safe_message = "Processing could not finish because of a temporary service error."
    retryable = True


class ProcessingTimedOut(TransientProcessingError):
    code = "processing_timeout"
    safe_message = "Processing exceeded its time limit and will be retried."


class LeaseLost(Exception):
    """Another worker owns or completed this job lease."""


def extract_pdf_pages(
    document: Document,
    storage: ObjectStorage,
    heartbeat: Callable[[], None] | None = None,
) -> list[ExtractedPage]:
    try:
        source, _content_length = storage.get_file(document.storage_key)
    except StoredObjectNotFound as error:
        raise MissingSourceObject from error
    except ObjectStorageError as error:
        raise TransientProcessingError from error

    with source, SpooledTemporaryFile(max_size=SPOOL_MEMORY_LIMIT, mode="w+b") as pdf_file:
        digest = sha256()
        total_bytes = 0
        while block := source.read(DOWNLOAD_BLOCK_SIZE):
            total_bytes += len(block)
            if total_bytes > document.byte_size:
                raise SourceIntegrityError
            pdf_file.write(block)
            digest.update(block)
            if heartbeat is not None:
                heartbeat()
        if total_bytes != document.byte_size or digest.hexdigest() != document.sha256:
            raise SourceIntegrityError
        pdf_file.seek(0)
        try:
            reader = PdfReader(pdf_file, strict=False)
            if reader.is_encrypted:
                raise EncryptedSourcePDF
            pages: list[ExtractedPage] = []
            has_text = False
            for index, page in enumerate(reader.pages, start=1):
                if heartbeat is not None:
                    heartbeat()
                try:
                    text = normalize_page_text(page.extract_text() or "")
                except (
                    EmptyFileError,
                    FileNotDecryptedError,
                    PdfReadError,
                    ValueError,
                    IndexError,
                ) as error:
                    raise InvalidSourcePDF from error
                except Exception as error:
                    raise TransientProcessingError from error
                if any(character.isalnum() for character in text):
                    has_text = True
                pages.append(
                    ExtractedPage(
                        page_number=index,
                        text=text,
                        content_hash=sha256(text.encode("utf-8")).hexdigest(),
                    )
                )
        except EncryptedSourcePDF:
            raise
        except (
            EmptyFileError,
            FileNotDecryptedError,
            PdfReadError,
            ValueError,
            IndexError,
        ) as error:
            raise InvalidSourcePDF from error
        except ProcessingError:
            raise
        except Exception as error:
            raise TransientProcessingError from error

    if not pages or not has_text:
        raise NoExtractableText
    if len(pages) != document.page_count:
        raise InvalidSourcePDF
    return pages


def normalize_page_text(value: str) -> str:
    """Normalize whitespace and Unicode while preserving meaningful line structure."""
    normalized = unicodedata.normalize("NFKC", value).replace("\x00", "")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n").replace("\u00ad", "")
    lines = [" ".join(line.split()) for line in normalized.split("\n")]
    compacted: list[str] = []
    blank_seen = False
    for line in lines:
        if line:
            compacted.append(line)
            blank_seen = False
        elif compacted and not blank_seen:
            compacted.append("")
            blank_seen = True
    return "\n".join(compacted).strip()
