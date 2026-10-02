"""Page-aware, structure-aware chunking of OCR text for retrieval.

The OCR reader joins pages as ``--- PAGINA n ---`` blocks. Chunks keep the
pages they come from (so an answer can cite "pag. 3"), start a new chunk at
clause/heading boundaries instead of cutting mid-clause at a fixed character
count, merge tiny sections so no chunk is just a heading, and only use
overlap when a single block is too long to keep whole. Pure and deterministic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PAGE_MARKER = re.compile(r"^[ \t]*---[ \t]*PAGINA[ \t]+(\d+)[ \t]*---[ \t]*$", re.MULTILINE)

TARGET_SIZE = 900      # a chunk is closed once adding the next block would pass this
MAX_SIZE = 1500        # a single block longer than this is split on sentences
OVERLAP = 150          # sentence overlap, used only when splitting a long block
MIN_SIZE = 200         # smaller sections are merged with the following one

_CLAUSE_START = re.compile(
    r"^(?:Art(?:icolo)?\.?\s*\d+[a-z]?\b|\d{1,2}(?:\.\d{1,2})*[.)]\s+\S|\d{1,2}\.\d{1,2}\s+\S)",
    re.IGNORECASE,
)
_SENTENCE_END = re.compile(r"(?<=[.;:!?])\s+")


@dataclass(frozen=True)
class TextChunk:
    index: int
    text: str
    page_start: int
    page_end: int
    heading: str | None


def split_pages(full_text: str) -> list[tuple[int, str]]:
    """(page number, text) pairs. Text without page markers is one page."""
    text = full_text or ""
    marks = list(PAGE_MARKER.finditer(text))
    if not marks:
        return [(1, text)] if text.strip() else []
    pages: list[tuple[int, str]] = []
    leading = text[: marks[0].start()]
    if leading.strip():
        pages.append((max(int(marks[0].group(1)) - 1, 1), leading))
    for position, mark in enumerate(marks):
        end = marks[position + 1].start() if position + 1 < len(marks) else len(text)
        body = text[mark.end():end]
        if body.strip():
            pages.append((int(mark.group(1)), body))
    return pages


def _is_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 90:
        return False
    if _CLAUSE_START.match(stripped):
        # "Art. 5 - Destinazione d'uso" is a heading; "1) Il venditore dichiara che ..." is a clause body.
        return len(stripped) <= 70 and not stripped.endswith((".", ";", ","))
    letters = [c for c in stripped if c.isalpha()]
    return len(letters) >= 4 and stripped == stripped.upper() and not stripped.endswith((".", ","))


def _blocks(page_text: str) -> list[tuple[str, str | None]]:
    """Blocks of one page as (text, heading if the block starts with one)."""
    blocks: list[tuple[str, str | None]] = []
    current: list[str] = []
    current_heading: str | None = None

    def close() -> None:
        nonlocal current, current_heading
        text = "\n".join(current).strip()
        if text:
            blocks.append((text, current_heading))
        current, current_heading = [], None

    for raw in page_text.splitlines():
        line = re.sub(r"[ \t]+", " ", raw).strip()
        if not line:
            close()
            continue
        starts_clause = bool(_CLAUSE_START.match(line)) or _is_heading(line)
        if starts_clause and current:
            close()
        if starts_clause and _is_heading(line):
            current_heading = line
        current.append(line)
    close()
    return blocks


def _split_long(block: str) -> list[str]:
    """A block longer than MAX_SIZE, split on lines then sentences, with a
    sentence-sized overlap so a fact cut at the boundary appears in both."""
    units: list[str] = []
    for line in block.split("\n"):
        if len(line) <= MAX_SIZE:
            units.append(line)
            continue
        for sentence in _SENTENCE_END.split(line):
            while len(sentence) > MAX_SIZE:            # unpunctuated OCR noise: hard cut
                units.append(sentence[:MAX_SIZE])
                sentence = sentence[MAX_SIZE:]
            if sentence:
                units.append(sentence)
    pieces: list[str] = []
    current: list[str] = []
    size = 0
    for unit in units:
        if size + len(unit) > TARGET_SIZE and current:
            pieces.append("\n".join(current))
            tail: list[str] = []
            carried = 0
            for previous in reversed(current):
                if carried + len(previous) > OVERLAP:
                    break
                tail.insert(0, previous)
                carried += len(previous)
            current, size = tail, carried
        current.append(unit)
        size += len(unit) + 1
    if current:
        pieces.append("\n".join(current))
    return pieces


def chunk_document(full_text: str) -> list[TextChunk]:
    """Chunks with page range and the heading in effect where each starts."""
    chunks: list[TextChunk] = []
    buffer: list[tuple[int, str]] = []
    size = 0
    heading_in_effect: str | None = None
    chunk_heading: str | None = None

    def flush() -> None:
        nonlocal buffer, size, chunk_heading
        if not buffer:
            return
        pages = [page for page, _ in buffer]
        chunks.append(TextChunk(
            index=len(chunks), text="\n".join(text for _, text in buffer).strip(),
            page_start=min(pages), page_end=max(pages), heading=chunk_heading,
        ))
        buffer, size, chunk_heading = [], 0, None

    for page, page_text in split_pages(full_text):
        for block, heading in _blocks(page_text):
            if heading:
                heading_in_effect = heading
                if size >= MIN_SIZE:
                    flush()          # a new section starts a new chunk, unless the previous one is still tiny
            pieces = [block] if len(block) <= MAX_SIZE else _split_long(block)
            for piece in pieces:
                if size + len(piece) > TARGET_SIZE and size >= MIN_SIZE:
                    flush()
                if not buffer:
                    chunk_heading = heading_in_effect
                buffer.append((page, piece))
                size += len(piece) + 1
    flush()
    return chunks
