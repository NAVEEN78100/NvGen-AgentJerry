"""Knowledge base (RAG layer).

Ingestion: extract text (PDF/TXT/MD) -> section-aware chunks with overlap.
Retrieval: Okapi BM25 over the org's chunks, filtered by the agent's attached
sources. The `Retriever` interface is deliberately small so a vector store
(ChromaDB / pgvector + sentence-transformer embeddings) can replace BM25
without touching the engine."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import KnowledgeChunk, KnowledgeSource

CHUNK_WORDS = 140
OVERLAP_WORDS = 30

_STOP = set("""a an the and or but if then of to in on at for from by with without is are was were be been being
this that these those it its as into over under about our your their we you they i me my us them he she his her
will would can could should may might must do does did done have has had not no yes so than too very just also
any all each every per via""".split())

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    toks = [t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 1]
    # light stemming: strip common plural/verb suffixes
    out = []
    for t in toks:
        for suf in ("ing", "ers", "ies", "es", "s", "ed"):
            if len(t) > 4 and t.endswith(suf):
                t = t[: -len(suf)] + ("y" if suf == "ies" else "")
                break
        out.append(t)
    return out


def extract_text(path: Path, source_type: str) -> str:
    if source_type == "pdf":
        reader = PdfReader(str(path))
        pages = []
        for i, page in enumerate(reader.pages):
            t = page.extract_text() or ""
            if t.strip():
                pages.append(t)
        return "\n\n".join(pages)
    return path.read_text(encoding="utf-8", errors="replace")


def chunk_text(text: str) -> list[tuple[str, str]]:
    """Return (section, chunk_text) pairs. Markdown-style headings and short
    title lines start new sections so chunks keep their context."""
    text = text.replace("\r\n", "\n")
    sections: list[tuple[str, list[str]]] = []
    current = ("", [])
    for line in text.split("\n"):
        stripped = line.strip()
        is_heading = stripped.startswith("#") or (
            0 < len(stripped) < 70 and stripped == stripped.title() and not stripped.endswith(".") and len(stripped.split()) <= 8
        )
        if is_heading and stripped:
            if current[1]:
                sections.append(current)
            current = (stripped.lstrip("# ").strip(), [])
        elif stripped:
            current[1].append(stripped)
    if current[1]:
        sections.append(current)

    chunks: list[tuple[str, str]] = []
    for section, lines in sections:
        words = " ".join(lines).split()
        if not words:
            continue
        start = 0
        while start < len(words):
            end = min(len(words), start + CHUNK_WORDS)
            chunks.append((section, " ".join(words[start:end])))
            if end == len(words):
                break
            start = end - OVERLAP_WORDS
    return chunks


def ingest(db: Session, source: KnowledgeSource, path: Path) -> KnowledgeSource:
    text = extract_text(path, source.source_type)
    if not text.strip():
        source.status = "empty"
        source.chunk_count = 0
        return source
    pieces = chunk_text(text)
    source.chunks.clear()
    for i, (section, body) in enumerate(pieces):
        source.chunks.append(KnowledgeChunk(org_id=source.org_id, idx=i, section=section[:250], text=body))
    source.chunk_count = len(pieces)
    source.char_count = len(text)
    source.status = "ready"
    return source


@dataclass
class Passage:
    chunk_id: int
    source_id: str
    source_title: str
    section: str
    text: str
    score: float

    def as_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id, "source_id": self.source_id, "source_title": self.source_title,
            "section": self.section, "text": self.text, "score": round(self.score, 3),
        }


class BM25Retriever:
    k1 = 1.4
    b = 0.75

    def __init__(self, db: Session, org_id: str, source_ids: list[str] | None = None):
        q = select(KnowledgeChunk, KnowledgeSource.title).join(KnowledgeSource).where(KnowledgeChunk.org_id == org_id)
        if source_ids is not None:
            if not source_ids:
                self.docs = []
                return
            q = q.where(KnowledgeChunk.source_id.in_(source_ids))
        self.docs = []
        for chunk, title in db.execute(q).all():
            toks = tokenize(f"{chunk.section} {chunk.section} {chunk.text}")
            self.docs.append((chunk, title, Counter(toks), len(toks)))
        n = len(self.docs)
        self.avgdl = (sum(d[3] for d in self.docs) / n) if n else 0
        df: Counter = Counter()
        for _, _, tf, _ in self.docs:
            df.update(tf.keys())
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, k: int = 3, min_score: float = 0.5) -> list[Passage]:
        qt = tokenize(query)
        if not qt or not self.docs:
            return []
        results = []
        for chunk, title, tf, dl in self.docs:
            score = 0.0
            for t in qt:
                f = tf.get(t)
                if not f:
                    continue
                score += self.idf.get(t, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1)))
            if score >= min_score:
                results.append(Passage(chunk.id, chunk.source_id, title, chunk.section, chunk.text, score))
        results.sort(key=lambda p: -p.score)
        return results[:k]


def best_sentence(passage_text: str, query: str) -> str:
    """Pick the sentence in a passage that best matches the query (used by the
    offline writer to ground a draft in the knowledge base)."""
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", passage_text) if len(s.strip()) > 25]
    if not sents:
        return passage_text.strip()[:240]
    qt = set(tokenize(query))
    scored = sorted(sents, key=lambda s: -len(qt & set(tokenize(s))))
    return scored[0]
