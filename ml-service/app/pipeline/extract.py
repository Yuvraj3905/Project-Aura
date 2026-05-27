"""Text extraction from uploaded documents (pdf / docx / txt / md)."""
from pathlib import Path


def extract_text(path: str, mime_type: str = "") -> str:
    """Extract plain text from a file, dispatching on extension then mime type."""
    suffix = Path(path).suffix.lower()
    mime = (mime_type or "").lower()

    if suffix == ".pdf" or "pdf" in mime:
        return _extract_pdf(path)
    if suffix == ".docx" or "officedocument.wordprocessing" in mime:
        return _extract_docx(path)
    # txt, md, and anything else readable as text
    return Path(path).read_text(encoding="utf-8", errors="replace")


def _extract_pdf(path: str) -> str:
    from pypdf import PdfReader

    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


def _extract_docx(path: str) -> str:
    import docx

    document = docx.Document(path)
    return "\n".join(p.text for p in document.paragraphs)
