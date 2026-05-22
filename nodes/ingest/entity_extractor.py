"""Extract product-level metadata from tourism documents."""

from __future__ import annotations

from typing import Any
from typing import Dict

from core.tourism_metadata import build_suggested_queries
from graphs.states import IngestState
from nodes.ingest.progress import report_progress
from tool.logger import logger


def entity_extractor(state: IngestState) -> Dict[str, Any]:
    logger.info(f"Extract metadata for {state.file_name}")
    report_progress(state.task_id, "产品索引生成中", 0.68)
    try:
        if not state.chunks:
            raise ValueError("chunks is empty")

        doc_types = sorted({chunk.doc_type for chunk in state.chunks if chunk.doc_type})
        suggested_queries = state.suggested_queries or build_suggested_queries(state.city, doc_types)
        entities = [
            {
                "name": state.product_name or state.city,
                "type": "city",
                "city": state.city,
                "product_id": state.product_id,
                "doc_type": state.doc_type,
                "available_doc_types": doc_types,
                "aliases": [state.city, f"{state.city}旅游", f"{state.city}攻略"],
                "suggested_queries": suggested_queries,
            }
        ]
        logger.info(f"Metadata extracted: city={state.city}, doc_type={state.doc_type}")
        return {"entities": entities, "suggested_queries": suggested_queries, "status": "entities_extracted"}
    except Exception as exc:
        logger.error(f"Metadata extraction failed: {exc}")
        return {"status": "error", "errors": state.errors + [f"[entity_extractor] {exc}"]}
