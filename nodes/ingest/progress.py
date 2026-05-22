"""Progress reporting helpers for ingestion tasks."""

import asyncio

from core.mongo_manager import MongoManager
from tool.logger import logger


def report_progress(task_id: str, step: str, progress: float, detail: str = ""):
    if not task_id:
        return
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            loop.create_task(MongoManager.get().update_task_progress(task_id, step=step, progress=progress, detail=detail))
        else:
            asyncio.run(MongoManager.get().update_task_progress(task_id, step=step, progress=progress, detail=detail))
    except Exception as exc:
        logger.warning(f"Progress update skipped for {task_id} {step}: {exc}")
