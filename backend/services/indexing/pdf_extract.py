import base64
import io

from pypdf import PdfReader


def extract_text_from_pdf_base64(pdf_base64: str) -> str:
    """Decode a base64 PDF and return its extracted text (pages joined)."""
    raw = base64.b64decode(pdf_base64)
    reader = PdfReader(io.BytesIO(raw))
    parts = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            parts.append(text.strip())
    return "\n\n".join(parts)
