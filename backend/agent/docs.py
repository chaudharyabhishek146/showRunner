"""The uploaded product document.

The document is a per-demo input, not configuration: the presenter uploads the
flow they want walked through, and everything downstream — the plan, the
narration, the answers — is grounded in that upload rather than in anything
baked into this repo.

Storage is deliberately dumb. Documents are written under the upload directory
keyed by a content hash, so re-uploading the same file is free and a restart
doesn't lose the doc a demo was planned from.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from . import config

log = logging.getLogger(__name__)

# Product docs are long; the planner and the cached system block are both
# happier with a bound. 400k characters is far more than any real one-flow doc.
MAX_CHARS = 400_000

_TAGS = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.S | re.I)
_BLANKS = re.compile(r"\n{3,}")


@dataclass(frozen=True)
class Document:
    id: str
    name: str
    text: str
    uploaded_at: str

    def summary(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "chars": len(self.text),
            "uploaded_at": self.uploaded_at,
            "preview": self.text[:400],
        }


_cache: dict[str, Document] = {}


def extract_text(name: str, raw: bytes) -> str:
    """Get readable text out of an upload, by extension.

    Anything unrecognised is treated as text — a mislabelled markdown file
    should not stop a demo, and binary garbage is obvious the moment the
    preview renders.
    """
    lower = name.lower()

    if lower.endswith(".pdf"):
        return _from_pdf(raw)
    if lower.endswith((".html", ".htm")):
        return _clean(_TAGS.sub(" ", raw.decode("utf-8", errors="replace")))
    if lower.endswith(".docx"):
        return _from_docx(raw)
    return _clean(raw.decode("utf-8", errors="replace"))


def _clean(text: str) -> str:
    return _BLANKS.sub("\n\n", text.replace("\r\n", "\n")).strip()[:MAX_CHARS]


def _from_pdf(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        log.warning("pypdf is not installed — cannot read PDF uploads")
        return ""
    try:
        reader = PdfReader(io.BytesIO(raw))
        return _clean("\n\n".join(page.extract_text() or "" for page in reader.pages))
    except Exception as exc:  # a malformed PDF is a user error, not a crash
        log.warning("Could not read PDF: %s", exc)
        return ""


def _from_docx(raw: bytes) -> str:
    """.docx is a zip of XML; the text lives in word/document.xml."""
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", errors="replace")
    except Exception as exc:
        log.warning("Could not read .docx: %s", exc)
        return ""
    # Paragraph breaks first, then strip the rest of the markup.
    xml = re.sub(r"</w:p>", "\n", xml)
    return _clean(re.sub(r"<[^>]+>", "", xml))


def store(name: str, text: str) -> Document:
    """Persist a document and return its handle."""
    text = _clean(text)
    doc_id = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    document = Document(
        id=doc_id,
        name=name or "document",
        text=text,
        uploaded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    _cache[doc_id] = document

    try:
        config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        (config.UPLOAD_DIR / f"{doc_id}.txt").write_text(text, encoding="utf-8")
    except OSError as exc:  # read-only container: memory is enough for one run
        log.warning("Could not persist upload %s: %s", doc_id, exc)

    log.info("Stored document %r (%s, %d chars)", document.name, doc_id, len(text))
    return document


def get(doc_id: str) -> Document | None:
    """Fetch a stored document, rehydrating from disk after a restart."""
    if doc_id in _cache:
        return _cache[doc_id]
    path = config.UPLOAD_DIR / f"{doc_id}.txt"
    if not path.exists():
        return None
    document = Document(
        id=doc_id,
        name=doc_id,
        text=path.read_text(encoding="utf-8"),
        uploaded_at=datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc
        ).isoformat(timespec="seconds"),
    )
    _cache[doc_id] = document
    return document


def resolve(doc_id: str = "", inline: str = "") -> str:
    """The document text for a run: by id, inline, or the bundled sample."""
    if doc_id:
        found = get(doc_id)
        if found is not None:
            return found.text
        log.warning("Unknown document id %r", doc_id)
    if inline.strip():
        return _clean(inline)
    return config.read_sample_doc()
