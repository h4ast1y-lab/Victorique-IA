import asyncio
import json
import logging
import re
import unicodedata
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional

import numpy as np

from app.config import DOCS_DIR, settings
from app.memory.database import get_connection
from app.rag.document_loader import document_loader
from app.rag.text_splitter import text_splitter
from app.models.ollama_client import ollama_client

logger = logging.getLogger("vector_store")


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    a = np.array(v1, dtype=np.float32)
    b = np.array(v2, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _lexical_score(query: str, text: str) -> float:
    """Calcula correspondência léxica/BM25 simplificada entre a busca e o texto."""
    q_lower = query.lower().strip()
    t_lower = text.lower()
    if not q_lower or not t_lower:
        return 0.0

    # Bônus forte se a frase inteira da busca aparece exatamente no texto
    exact_bonus = 0.5 if q_lower in t_lower else 0.0

    # Quebra em termos significativos (palavras com 3 ou mais caracteres)
    terms = [w for w in re.findall(r"\w+", q_lower) if len(w) >= 3]
    if not terms:
        return exact_bonus

    matches = sum(1 for term in terms if term in t_lower)
    term_ratio = matches / len(terms)
    return min(1.0, 0.5 * term_ratio + exact_bonus)


# --- Keyword mode (no embeddings) -------------------------------------------
# Used when Ollama is not installed or not running: on a machine where the AI
# runs only through Claude Code there is nothing to compute embeddings, so
# documents are indexed and searched by their words alone.

_STOPWORDS = frozenset(
    """
    que para com uma uns umas dos das nos nas pelo pela pelos pelas por sem sob
    sobre entre como mais menos muito muita muitos muitas isso isto esse essa
    esses essas este esta estes estas aquele aquela aquilo qual quais quem onde
    quando porque pois mas tambem ainda ser sao foi era sera tem ter tinha
    voce voces ele ela eles elas meu minha seu sua nosso nossa lhe aos ate
    the and for with that this from are was were you your what which who
    """.split()
)
_MIN_KEYWORD_COVERAGE = 0.5


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _keyword_terms(query: str) -> List[str]:
    terms: List[str] = []
    for word in re.findall(r"\w+", _normalize(query)):
        if len(word) < 3 or word in _STOPWORDS:
            continue
        # Light stemming so "gato"/"gatos" or "relatorio"/"relatorios" match.
        stem = word[: max(4, len(word) - 2)]
        if stem not in terms:
            terms.append(stem)
    return terms


def _keyword_score(query: str, text: str) -> float:
    """Accent-insensitive keyword score in [0, 1]; 0 means "not relevant".

    At least half of the meaningful query words must appear in the text.
    Among matches, more occurrences and the exact phrase rank higher.
    """
    terms = _keyword_terms(query)
    if not terms or not text:
        return 0.0
    words = re.findall(r"\w+", _normalize(text))
    counts = [sum(1 for w in words if w.startswith(term)) for term in terms]
    coverage = sum(1 for c in counts if c) / len(terms)
    if coverage < _MIN_KEYWORD_COVERAGE:
        return 0.0
    frequency = min(1.0, sum(counts) / (3 * len(terms)))
    phrase = 0.1 if _normalize(query).strip() in _normalize(text) else 0.0
    return round(min(1.0, 0.7 * coverage + 0.2 * frequency + phrase), 4)


async def _try_embedding(text: str) -> Optional[List[float]]:
    """Embedding from Ollama, or None when it is missing/offline/failing."""
    try:
        vector = await ollama_client.generate_embeddings(text)
    except Exception as exc:
        logger.info("Embeddings indisponíveis (%s); usando busca por palavras-chave.", exc)
        return None
    return vector or None


class VectorStore:
    async def index_document(
        self,
        file_path: str,
        collection: str = "Geral",
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Parses, splits, embeds and indexes a document into SQLite.
        Embeddings are computed before opening the write transaction to avoid
        holding a database lock during slow model calls.
        """
        path = Path(file_path).resolve()
        # Parsing (PDF, Office, OCR) is slow and blocking: keep it off the event loop.
        pages = await asyncio.to_thread(document_loader.load, str(path))
        chunks = await asyncio.to_thread(text_splitter.split_pages, pages)

        if not chunks:
            raise ValueError(
                "Nenhum texto extraível encontrado no documento. "
                "Se for um PDF digitalizado (imagem), verifique se o Tesseract-OCR está instalado."
            )

        doc_id = str(uuid.uuid4())
        title = path.name
        ext = path.suffix.lower().replace(".", "")

        logger.info(f"Indexing '{title}': {len(pages)} pages, {len(chunks)} chunks.")

        # Without Ollama the chunks are stored with an empty vector ("[]") and
        # found later by keyword search. Stop asking after the first failure.
        embedded_chunks = []
        embeddings_ok = True
        for ch in chunks:
            vector = await _try_embedding(ch["text"]) if embeddings_ok else None
            if vector is None:
                embeddings_ok = False
            embedded_chunks.append((ch, vector or []))
        search_mode = "semantic" if any(v for _, v in embedded_chunks) else "keyword"

        await asyncio.to_thread(self._insert_document, doc_id, title, path, ext, pages,
                                chunks, collection, project_id, embedded_chunks)

        return {
            "id": doc_id,
            "title": title,
            "total_pages": len(pages),
            "total_chunks": len(chunks),
            "collection": collection,
            "search_mode": search_mode,
        }

    @staticmethod
    def _insert_document(doc_id, title, path, ext, pages, chunks, collection, project_id,
                         embedded_chunks) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO documents (id, title, file_path, file_type, total_pages, total_chunks, collection, project_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (doc_id, title, str(path), ext, len(pages), len(chunks), collection, project_id)
            )

            for ch, vector in embedded_chunks:
                chunk_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO document_chunks (id, document_id, chunk_index, page_number, content, embedding_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (chunk_id, doc_id, ch["chunk_index"], ch["page"], ch["text"], json.dumps(vector))
                )

    async def search(
        self,
        query: str,
        project_id: Optional[str] = None,
        collection: Optional[str] = None,
        top_k: int = 4,
        min_score: float = 0.35
    ) -> List[Dict[str, Any]]:
        """
        Semantic search across indexed document chunks using cosine similarity.
        Falls back to keyword search for chunks without an embedding, or for
        every chunk when Ollama cannot embed the query.
        """
        rows = await asyncio.to_thread(self._candidate_rows, project_id, collection)
        if not rows:
            # Nothing indexed for this scope: no reason to wake Ollama (on a
            # Claude-only machine that call alone cost seconds per message).
            return []
        # Only documents indexed with embeddings need the query embedded.
        needs_vector = any((r["embedding_json"] or "[]").strip() not in ("", "[]") for r in rows)
        query_vec = await _try_embedding(query) if needs_vector else None
        return await asyncio.to_thread(self._score_rows, rows, query, query_vec, top_k, min_score)

    @staticmethod
    def _candidate_rows(project_id: Optional[str], collection: Optional[str]) -> List[Any]:
        sql = """
            SELECT c.id, c.document_id, c.page_number, c.content, c.embedding_json,
                   d.title as doc_title, d.file_path, d.collection
            FROM document_chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE 1=1
        """
        params = []
        if project_id:
            sql += " AND d.project_id = ?"
            params.append(project_id)
        else:
            # No project selected: only global documents. Never leak another
            # project's documents into a global conversation.
            sql += " AND d.project_id IS NULL"
        if collection:
            sql += " AND d.collection = ?"
            params.append(collection)
        with get_connection() as conn:
            return conn.execute(sql, params).fetchall()

    @staticmethod
    def _score_rows(rows, query: str, query_vec: Optional[List[float]], top_k: int,
                    min_score: float) -> List[Dict[str, Any]]:
        hybrid = getattr(settings, "rag_hybrid_search", True)
        scored_results = []
        for r in rows:
            try:
                chunk_vec = json.loads(r["embedding_json"] or "[]")
                if not query_vec or not chunk_vec or len(chunk_vec) != len(query_vec):
                    score = _keyword_score(query, r["content"])
                    if score > 0:
                        scored_results.append({
                            "chunk_id": r["id"],
                            "document_id": r["document_id"],
                            "document_title": r["doc_title"],
                            "file_path": r["file_path"],
                            "page": r["page_number"],
                            "content": r["content"],
                            "score": score,
                            "similarity": None,
                        })
                    continue

                sim = cosine_similarity(query_vec, chunk_vec)
                if hybrid:
                    # 70% semântica vetorial, 30% correspondência léxica exata
                    final_score = 0.7 * sim + 0.3 * _lexical_score(query, r["content"])
                else:
                    final_score = sim

                if final_score >= min_score or (hybrid and sim >= min_score):
                    scored_results.append({
                        "chunk_id": r["id"],
                        "document_id": r["document_id"],
                        "document_title": r["doc_title"],
                        "file_path": r["file_path"],
                        "page": r["page_number"],
                        "content": r["content"],
                        "score": round(final_score, 4),
                        "similarity": round(sim, 4),
                    })
            except Exception as e:
                logger.debug(f"Error calculating similarity: {e}")

        scored_results.sort(key=lambda x: x["score"], reverse=True)
        return scored_results[:top_k]

    def list_documents(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM documents"
        params = []
        if project_id:
            sql += " WHERE project_id = ?"
            params.append(project_id)
        sql += " ORDER BY created_at DESC"

        with get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def delete_document(self, document_id: str) -> bool:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT file_path FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
            if not row:
                return False
            file_path = row["file_path"]
            cur = conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            if cur.rowcount <= 0:
                return False
            remaining = conn.execute(
                "SELECT COUNT(*) FROM documents WHERE file_path = ?", (file_path,)
            ).fetchone()[0]

        # Remove the stored copy only when no other document row uses it and it
        # lives inside the managed documents directory.
        if remaining == 0 and file_path:
            try:
                p = Path(file_path).resolve()
                docs_root = DOCS_DIR.resolve()
                if p.is_relative_to(docs_root) and p.is_file():
                    p.unlink()
            except Exception as e:
                logger.warning(f"Could not remove document file '{file_path}': {e}")
        return True


vector_store = VectorStore()
