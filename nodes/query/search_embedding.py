"""Search the chunk collection after product ids are confirmed."""

from __future__ import annotations

import json
from typing import Any
from typing import Dict
from typing import List

from core.config import get_settings
from core.milvus_manager import MilvusManager
from core.tourism_metadata import OVERVIEW_DOC_TYPES
from graphs.states import RAGChatState
from tool.logger import logger


def search_embedding(state: RAGChatState) -> Dict[str, Any]:
    logger.info(f"Search embedding for city={state.city} products={state.product_ids}")
    try:
        if not state.query_dense:
            return {"errors": state.errors + ["[search_embedding] query_dense is empty"], "embedding_chunks": []}
        if not state.product_ids:
            return {"embedding_chunks": []}

        settings = get_settings()
        doc_types = state.requested_doc_types or OVERVIEW_DOC_TYPES
        chunks: list[dict] = []

        if set(doc_types) == set(OVERVIEW_DOC_TYPES):
            for doc_type in OVERVIEW_DOC_TYPES:
                results = MilvusManager.search_chunks(
                    query_dense=state.query_dense,
                    query_sparse=state.query_sparse or None,
                    top_k=2,
                    filter_expr=_build_filter(state.product_ids, [doc_type]),
                )
                chunks.extend(_format_hits(results))
        else:
            results = MilvusManager.search_chunks(
                query_dense=state.query_dense,
                query_sparse=state.query_sparse or None,
                top_k=max(settings.rag_top_k, 8),
                filter_expr=_build_filter(state.product_ids, doc_types),
            )
            chunks.extend(_format_hits(results))

        chunks = _dedupe_chunks(chunks)[:15]
        logger.info(f"Embedding search complete: {len(chunks)} docs")
        return {"embedding_chunks": chunks}
    except Exception as exc:
        logger.error(f"Embedding search failed: {exc}")
        return {"errors": state.errors + [f"[search_embedding] {exc}"], "embedding_chunks": []}


def _build_filter(product_ids: List[str], doc_types: List[str]) -> str:
    pid_expr = ", ".join(f'"{pid}"' for pid in product_ids if pid)
    if doc_types:
        type_expr = ", ".join(f'"{doc_type}"' for doc_type in doc_types if doc_type)
        return f"product_id in [{pid_expr}] and doc_type in [{type_expr}]"
    return f"product_id in [{pid_expr}]"


def _format_hits(results: List[Dict]) -> List[Dict]:
    rows = []
    for hit in results:
        entity = hit.get("entity", {})
        rows.append(
            {
                "task_id": entity.get("task_id", ""),
                "product_id": entity.get("product_id", ""),
                "product_name": entity.get("product_name", ""),
                "city": entity.get("city", ""),
                "doc_type": entity.get("doc_type", ""),
                "chunk_id": entity.get("chunk_id", hit.get("id", "")),
                "title": entity.get("title", ""),
                "content": entity.get("content", ""),
                "source_file": entity.get("source_file", ""),
                "source_url": entity.get("source_url", ""),
                "chunk_index": entity.get("chunk_index", 0),
                "image_urls": _loads(entity.get("image_urls", "[]")),
                "image_alts": _loads(entity.get("image_alts", "[]")),
                "score": hit.get("distance", 0.0),
            }
        )
    return rows


def _loads(value: str) -> list:
    try:
        return json.loads(value) if value else []
    except json.JSONDecodeError:
        return []


def _dedupe_chunks(chunks: List[Dict]) -> List[Dict]:
    mapping: Dict[str, Dict] = {}
    for chunk in chunks:
        chunk_id = chunk.get("chunk_id", "")
        if not chunk_id:
            continue
        existing = mapping.get(chunk_id)
        if not existing or chunk.get("score", 0) > existing.get("score", 0):
            mapping[chunk_id] = chunk
    return sorted(mapping.values(), key=lambda item: item.get("score", 0.0), reverse=True)
