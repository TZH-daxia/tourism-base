"""Persist product index rows and chunks into Milvus."""

from __future__ import annotations

import json
import uuid
from typing import Any
from typing import Dict

from core.milvus_manager import MilvusManager
from graphs.states import IngestState
from nodes.ingest.progress import report_progress
from tool.logger import logger


def vector_store(state: IngestState) -> Dict[str, Any]:
    logger.info(f"Store vectors for {state.file_name}")
    report_progress(state.task_id, "向量入库中", 0.92)
    try:
        if not state.chunks or not state.dense_vectors:
            raise ValueError("chunks or dense_vectors is empty")

        chunk_rows = []
        for chunk in state.chunks:
            chunk_rows.append(
                {
                    "id": str(uuid.uuid4()),
                    "task_id": state.task_id,
                    "product_id": chunk.product_id,
                    "product_name": chunk.product_name,
                    "city": chunk.city,
                    "doc_type": chunk.doc_type,
                    "chunk_id": chunk.chunk_id,
                    "title": chunk.title[:256],
                    "content": chunk.content[:12000],
                    "source_file": chunk.source_file,
                    "source_url": chunk.source_url or "",
                    "chunk_index": chunk.chunk_index,
                    "image_urls": json.dumps(chunk.image_urls, ensure_ascii=False),
                    "image_alts": json.dumps(chunk.image_alts, ensure_ascii=False),
                    "dense_vector": chunk.dense_vector,
                    "sparse_vector": chunk.sparse_vector,
                }
            )
        MilvusManager.insert_chunks(chunk_rows)

        if state.entities and state.entity_dense:
            entity = state.entities[0]
            product_rows = [
                {
                    "id": state.task_id,
                    "task_id": state.task_id,
                    "product_id": state.product_id,
                    "product_name": state.product_name or state.city,
                    "city": state.city,
                    "doc_type": state.doc_type,
                    "aliases": ",".join(entity.get("aliases", [])),
                    "available_doc_types": ",".join(entity.get("available_doc_types", [])),
                    "suggested_queries": json.dumps(entity.get("suggested_queries", []), ensure_ascii=False),
                    "source_file": state.file_name,
                    "dense_vector": state.entity_dense[0],
                    "sparse_vector": state.entity_sparse[0] if state.entity_sparse else {},
                }
            ]
            MilvusManager.insert_products(product_rows)

        logger.info(f"Stored chunks={len(chunk_rows)} city={state.city} doc_type={state.doc_type}")
        return {"status": "stored"}
    except Exception as exc:
        logger.error(f"Vector store failed: {exc}")
        return {"status": "error", "errors": state.errors + [f"[vector_store] {exc}"]}
