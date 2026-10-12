"""Streaming PDF boundary validation; content extraction belongs to M4."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePosixPath
from typing import BinaryIO

from fastapi import HTTPException, UploadFile
from pypdf import PdfReader
from pypdf.errors import EmptyFileError, FileNotDecryptedError, PdfReadError

from app.core.config import Settings

READ_CHUNK_BYTES = 64 * 1024
MAX_MULTIPART_OVERHEAD_BYTES = 64 * 1024


@dataclass(frozen=True)
class ValidatedPDF:
    filename: str
    byte_size: int
    sha256: str
    page_count: int


def validate_declared_request_size(content_length: str | None, settings: Settings) -> None:
    if content_length is None:
        return
    try:
        declared_size = int(content_length)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_content_length", "message": "Invalid upload size header"},
        ) from None
    if declared_size < 0 or declared_size > (
        settings.max_upload_bytes + MAX_MULTIPART_OVERHEAD_BYTES
    ):
        raise upload_too_large()


def validate_pdf_upload(upload: UploadFile, settings: Settings) -> ValidatedPDF:
    filename = _safe_pdf_filename(upload.filename)
    if upload.content_type not in {None, "", "application/pdf", "application/octet-stream"}:
        raise unsupported_pdf()

    stream: BinaryIO = upload.file
    stream.seek(0)
    digest = sha256()
    size = 0
    signature_window = bytearray()
    while chunk := stream.read(READ_CHUNK_BYTES):
        size += len(chunk)
        if size > settings.max_upload_bytes:
            raise upload_too_large()
        digest.update(chunk)
        if len(signature_window) < 1024:
            signature_window.extend(chunk[: 1024 - len(signature_window)])

    if size == 0 or b"%PDF-" not in signature_window:
        raise unsupported_pdf()

    stream.seek(0)
    try:
        reader = PdfReader(stream, strict=False)
        if reader.is_encrypted:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "encrypted_pdf_unsupported",
                    "message": "Password-protected PDFs are not supported",
                },
            )
        page_count = len(reader.pages)
    except HTTPException:
        raise
    except (EmptyFileError, FileNotDecryptedError, PdfReadError, ValueError, IndexError) as error:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_pdf",
                "message": "The uploaded PDF is malformed or unreadable",
            },
        ) from error

    if page_count < 1:
        raise HTTPException(
            status_code=422,
            detail={"code": "empty_pdf", "message": "The PDF must contain at least one page"},
        )
    if page_count > settings.max_pdf_pages:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "pdf_page_limit_exceeded",
                "message": f"PDFs may contain no more than {settings.max_pdf_pages} pages",
            },
        )
    stream.seek(0)
    return ValidatedPDF(filename, size, digest.hexdigest(), page_count)


def _safe_pdf_filename(filename: str | None) -> str:
    if not filename:
        raise unsupported_pdf()
    leaf_name = PurePosixPath(filename.replace("\\", "/")).name
    safe_name = "".join(character for character in leaf_name if character.isprintable()).strip()
    if not safe_name or len(safe_name) > 255 or not safe_name.lower().endswith(".pdf"):
        raise unsupported_pdf()
    return safe_name


def upload_too_large() -> HTTPException:
    return HTTPException(
        status_code=413,
        detail={
            "code": "upload_too_large",
            "message": "The PDF exceeds the configured upload limit",
        },
    )


def unsupported_pdf() -> HTTPException:
    return HTTPException(
        status_code=415,
        detail={"code": "pdf_required", "message": "Upload a valid PDF file"},
    )
