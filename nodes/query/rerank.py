"""Rerank merged documents with a local or remote reranker."""

from __future__ import annotations

from typing import Any
from typing import Dict

from core.reranker_factory import rerank_scores
from core.tourism_metadata import OVERVIEW_DOC_TYPES
from graphs.states import RAGChatState
from tool.logger import logger


def rerank(state: RAGChatState) -> Dict[str, Any]:
    logger.info("Start rerank")
    try:
        if not state.rrf_chunks:
            return {"reranked_docs": []}
        query = state.rewritten_query or state.query
        documents = [doc.get("content", "") for doc in state.rrf_chunks]
        scores = rerank_scores(query, documents)
        reranked = []
        for index, doc in enumerate(state.rrf_chunks):
            item = doc.copy()
            item["rerank_score"] = scores[index] if index < len(scores) else 0.0
            reranked.append(item)
        reranked.sort(key=lambda row: row.get("rerank_score", row.get("rrf_score", 0.0)), reverse=True)
        if set(state.requested_doc_types or []) == set(OVERVIEW_DOC_TYPES):
            selected = []
            covered = set()
            for doc_type in OVERVIEW_DOC_TYPES:
                for row in reranked:
                    if row.get("doc_type") == doc_type and row.get("chunk_id") not in covered:
                        selected.append(row)
                        covered.add(row.get("chunk_id"))
                        break
            for row in reranked:
                if row.get("chunk_id") in covered:
                    continue
                selected.append(row)
                covered.add(row.get("chunk_id"))
                if len(selected) >= 8:
                    break
            reranked = selected
        logger.info(f"Rerank complete: {len(reranked[:8])} docs")
        return {"reranked_docs": reranked[:8]}
    except Exception as exc:
        logger.warning(f"Rerank fallback to RRF: {exc}")
        return {"errors": state.errors + [f"[rerank] {exc}"], "reranked_docs": state.rrf_chunks[:8]}
