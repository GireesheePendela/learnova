"""Loading lesson text from the sample, a .txt/.md file, or a PDF."""

import io
from pathlib import Path

SAMPLE_LESSON = Path(__file__).resolve().parent.parent / "data" / "sample_fractions.md"
MAX_CHARS = 20_000

LANGUAGES = [
    "Hindi", "Spanish", "Bengali", "Arabic", "Portuguese",
    "Swahili", "Vietnamese", "Chinese (Simplified)", "Tagalog", "English",
]


def sample_lesson() -> str:
    return SAMPLE_LESSON.read_text(encoding="utf-8")


def text_from_upload(filename: str, data: bytes) -> str:
    if filename.lower().endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    else:
        text = data.decode("utf-8", errors="replace")
    text = text.strip()
    if not text:
        raise ValueError("No readable text found. Scanned PDFs are not supported yet; try a text-based PDF or .txt file.")
    # Keep the prompt a reasonable size; one chapter section is plenty for a session.
    return text[:MAX_CHARS]


def text_from_path(path: str) -> str:
    p = Path(path)
    return text_from_upload(p.name, p.read_bytes())
