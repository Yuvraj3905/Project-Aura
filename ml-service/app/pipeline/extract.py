"""Text extraction from uploaded documents (pdf / docx / txt / md).

First stage of the ingestion pipeline: turn an arbitrary uploaded file into one plain
string for summarization + chunking. Format-specific parsers (pypdf, python-docx) are
imported lazily so that ingesting a plain .txt never pays the import cost of libraries
it doesn't need.
"""
from pathlib import Path


def extract_text(path: str, mime_type: str = "") -> str:
    """Extract plain text from a file.

    Dispatches on file extension first, then mime type as a fallback (uploads may arrive
    with a generic or missing mime). Anything not recognized as PDF/DOCX is read as UTF-8
    text — covering .txt and .md, with `errors="replace"` so a stray byte never crashes
    ingestion.
    """
    suffix = Path(path).suffix.lower()
    mime = (mime_type or "").lower()

    if suffix == ".pdf" or "pdf" in mime:
        return _extract_pdf(path)
    if suffix == ".docx" or "officedocument.wordprocessing" in mime:
        return _extract_docx(path)
    # txt, md, and anything else readable as text
    return Path(path).read_text(encoding="utf-8", errors="replace")


def _extract_pdf(path: str) -> str:
    # Concatenate per-page text with blank lines so page boundaries survive as paragraph
    # breaks. `or ""` guards pages that pypdf can't extract (e.g. scanned images).
    from pypdf import PdfReader

    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


def _extract_docx(path: str) -> str:
    # python-docx exposes the document as paragraph objects; join their text with newlines.
    import docx

    document = docx.Document(path)
    return "\n".join(p.text for p in document.paragraphs)
