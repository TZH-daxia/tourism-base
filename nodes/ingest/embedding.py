"""Generate dense and sparse embeddings for chunks and product index rows."""

from __future__ import annotations

from typing import Any
from typing import Dict

from core.embedding_factory import encode
from core.embedding_factory import encode_single
from graphs.states import IngestState
from nodes.ingest.progress import report_progress
from tool.logger import logger


def embedding_node(state: IngestState) -> Dict[str, Any]:
    logger.info(f"Embedding {len(state.chunks)} chunks")
    report_progress(state.task_id, "向量生成中", 0.76)
    try:
        if not state.chunks:
            raise ValueError("chunks is empty")

        chunk_texts = []
        for chunk in state.chunks:
            prefix = f"[{chunk.city}][{chunk.doc_type}][{chunk.product_name}]"
            chunk_texts.append(f"{prefix}\n{chunk.title}\n{chunk.content}")
        dense, sparse = encode(chunk_texts)
        for idx, chunk in enumerate(state.chunks):
            chunk.dense_vector = dense[idx]
            chunk.sparse_vector = sparse[idx]

        product_text = f"{state.city} 旅游 {state.doc_type} {' '.join(state.suggested_queries or [])}".strip()
        entity_dense, entity_sparse = [], []
        if state.entities:
            d, s = encode_single(product_text)
            entity_dense.append(d)
            entity_sparse.append(s)

        report_progress(state.task_id, "向量生成完成", 0.88, detail=f"chunks={len(state.chunks)}")
        logger.info(f"Embedding complete: chunks={len(dense)}, products={len(entity_dense)}")
        return {
            "dense_vectors": dense,
            "sparse_vectors": sparse,
            "entity_dense": entity_dense,
            "entity_sparse": entity_sparse,
            "status": "embedded",
        }
    except Exception as exc:
        logger.error(f"Embedding failed: {exc}")
        return {"status": "error", "errors": state.errors + [f"[embedding] {exc}"]}
