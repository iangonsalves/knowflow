"""Tiny standards-readable text PDF fixtures for document pipeline tests."""


def make_text_pdf(page_count: int = 1, page_texts: list[str] | None = None) -> bytes:
    texts = page_texts or [f"KnowFlow page {index + 1}" for index in range(page_count)]
    page_count = len(texts)
    page_object_ids = [3 + index * 2 for index in range(page_count)]
    font_object_id = 3 + page_count * 2
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        (
            f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_object_ids)}] "
            f"/Count {page_count} >>"
        ).encode(),
    ]
    for page_id, page_text in zip(page_object_ids, texts, strict=True):
        content_id = page_id + 1
        escaped_text = page_text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream_data = f"BT /F1 12 Tf 20 80 Td ({escaped_text}) Tj ET\n".encode()
        objects.extend(
            [
                (
                    f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] "
                    f"/Resources << /Font << /F1 {font_object_id} 0 R >> >> "
                    f"/Contents {content_id} 0 R >>"
                ).encode(),
                f"<< /Length {len(stream_data)} >>\nstream\n".encode() + stream_data + b"endstream",
            ]
        )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{object_number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return bytes(pdf)
