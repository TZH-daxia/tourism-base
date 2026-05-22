"""Finalize task status in MongoDB."""

import asyncio
from typing import Any
from typing import Dict

from core.mongo_manager import MongoManager
from graphs.states import IngestState
from tool.logger import logger


def task_tracker(state: IngestState) -> Dict[str, Any]:
    logger.info(f"Update task tracker: {state.task_id}")
    if not state.task_id:
        return {"status": "stored"}
    try:
        mongo = MongoManager.get()
        if state.status == "error":
            asyncio.run(
                mongo.update_task(
                    state.task_id,
                    status="failed",
                    current_step=f"失败: {state.errors[-1][:80] if state.errors else '未知错误'}",
                    error_log=state.errors,
                )
            )
            asyncio.run(
                mongo.update_task_progress(
                    state.task_id,
                    step="入库失败",
                    progress=1.0,
                    status="failed",
                    detail=state.errors[-1] if state.errors else "",
                )
            )
        else:
            stats = {
                "chunks": len(state.chunks),
                "images": len(state.images),
                "entities": len(state.entities),
                "city": state.city,
                "doc_type": state.doc_type,
            }
            asyncio.run(
                mongo.update_task(
                    state.task_id,
                    status="completed",
                    progress=1.0,
                    current_step="入库完成",
                    city=state.city,
                    doc_type=state.doc_type,
                    product_id=state.product_id,
                    suggested_queries=state.suggested_queries,
                    stats=stats,
                )
            )
            asyncio.run(
                mongo.update_task_progress(
                    state.task_id,
                    step="入库完成",
                    progress=1.0,
                    status="completed",
                    stats=stats,
                )
            )
        return {"status": "stored"}
    except Exception as exc:
        logger.warning(f"Task tracker update skipped: {exc}")
        return {"status": "stored"}
