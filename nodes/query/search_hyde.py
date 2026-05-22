"""HyDE search for recall enrichment."""

from __future__ import annotations

import json
from typing import Any
from typing import Dict
from typing import List

from core.config import get_settings
from core.embedding_factory import encode_single
from core.llm_factory import get_llm
from core.milvus_manager import MilvusManager
from graphs.states import RAGChatState
from tool.logger import logger

HYDE_PROMPT = """请围绕下面这个旅游问题，写一段 180 字以内、信息密度高的参考答案，用来辅助检索：

问题：{query}
"""


def search_hyde(state: RAGChatState) -> Dict[str, Any]:
    logger.info("Run HyDE search")
    try:
        if not state.product_ids:
            return {"hyde_chunks": []}
        llm = get_llm()
        if not llm:
            return {"hyde_chunks": []}
        from langchain_core.messages import HumanMessage

        query = state.rewritten_query or state.query
        hypo = llm.invoke([HumanMessage(content=HYDE_PROMPT.format(query=query))]).content
        dense, sparse = encode_single(hypo)
        results = MilvusManager.search_chunks(
            query_dense=dense,
            query_sparse=sparse,
            top_k=max(get_settings().rag_top_k, 8),
            filter_expr=_build_filter(state.product_ids, state.requested_doc_types),
        )
        chunks = _format_hits(results)
        logger.info(f"HyDE search complete: {len(chunks)} docs")
        return {"hyde_chunks": chunks}
    except Exception as exc:
        logger.warning(f"HyDE search skipped: {exc}")
        return {"errors": state.errors + [f"[search_hyde] {exc}"], "hyde_chunks": []}


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
