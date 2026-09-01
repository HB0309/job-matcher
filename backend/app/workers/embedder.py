"""Stage 2 of agentic matching: cheap semantic re-rank via embeddings.

No vector-DB/pgvector — embeddings are stored as plain JSON float arrays
(see migration 008) and compared in-process with numpy cosine similarity.
This is the free/near-free layer between the zero-cost heuristic pre-filter
(matcher.py) and the bounded LLM agent pass (agent.py): it narrows a top-N
heuristic shortlist down further before any chat-completion tokens are spent.

Posting embeddings are computed ONCE at ingestion and cached on
JobPosting.embedding — never recomputed per match run. Profile embeddings are
computed once per resume upload and cached on Profile.embedding.
"""
from __future__ import annotations

import logging
import time

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

_EMBED_MODEL = "text-embedding-004"


def embed_text(text: str) -> list[float] | None:
    """Embed a single text via Gemini's free embedding endpoint. Returns None
    on any failure (missing key, rate limit exhausted) — callers must treat
    embeddings as an optional re-rank signal, never a hard dependency."""
    if not settings.gemini_api_key:
        logger.info("embedder: no gemini_api_key configured, skipping embedding")
        return None
    if not text or not text.strip():
        return None

    from google import genai

    client = genai.Client(api_key=settings.gemini_api_key)
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            response = client.models.embed_content(model=_EMBED_MODEL, contents=text[:8000])
            return list(response.embeddings[0].values)
        except Exception as exc:
            last_exc = exc
            s = str(exc)
            if "429" in s or "RESOURCE_EXHAUSTED" in s:
                if attempt == 2:
                    break
                wait = 5 * (2 ** attempt)
                logger.warning(
                    "embedder: rate limit, retry in %ds (attempt %d/2)", wait, attempt + 1
                )
                time.sleep(wait)
                continue
            break

    logger.warning(
        "embedder: embedding failed (%s), skipping semantic re-rank for this text", last_exc
    )
    return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


def rerank_by_similarity(
    profile_embedding: list[float],
    candidates: list[tuple[str, list[float] | None]],
    top_k: int,
) -> list[str]:
    """candidates: list of (job_id, embedding). Postings with no embedding sort
    last (never dropped — they just don't benefit from the semantic re-rank).
    Returns job_ids in re-ranked order, truncated to top_k."""
    scored = [
        (job_id, cosine_similarity(profile_embedding, emb) if emb else -1.0)
        for job_id, emb in candidates
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [job_id for job_id, _ in scored[:top_k]]
