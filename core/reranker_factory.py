"""Local or remote reranker access."""

from __future__ import annotations

from typing import List

import httpx

from core.config import get_settings

_local_reranker = None


def get_local_reranker():
    global _local_reranker
    if _local_reranker is not None:
        return _local_reranker
    settings = get_settings()
    from FlagEmbedding import FlagReranker

    _local_reranker = FlagReranker(
        settings.reranker_model_path,
        use_fp16=settings.reranker_use_fp16,
        devices=settings.reranker_device,
    )
    return _local_reranker


def rerank_scores(query: str, documents: List[str]) -> List[float]:
    settings = get_settings()
    mode = settings.reranker_mode.lower()
    if not documents:
        return []
    if mode == "disabled":
        return [0.0 for _ in documents]
    if mode == "remote":
        api_key = settings.text_rerank_api_key or settings.openai_api_key
        resp = httpx.post(
            f"{settings.openai_api_base}/rerank",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": settings.text_rerank_model, "query": query, "documents": documents, "top_n": len(documents)},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        scores = [0.0 for _ in documents]
        for item in data.get("results", []):
            idx = item.get("index", -1)
            if 0 <= idx < len(scores):
                scores[idx] = item.get("relevance_score", 0.0)
        return scores
    try:
        reranker = get_local_reranker()
        return reranker.compute_score([[query, doc] for doc in documents], normalize=True)
    except Exception:
        return [0.0 for _ in documents]
