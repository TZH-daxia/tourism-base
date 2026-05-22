"""Persist query/answer history."""

import asyncio
from typing import Any
from typing import Dict

from core.mongo_manager import MongoManager
from graphs.states import RAGChatState
from tool.logger import logger


def save_history(state: RAGChatState) -> Dict[str, Any]:
    logger.info(f"Save history: {state.session_id}")
    try:
        if not state.session_id:
            return {}
        mongo = MongoManager.get()
        asyncio.run(
            mongo.save_message(
                session_id=state.session_id,
                role="user",
                text=state.query,
                intent=state.intent or "",
                entities=state.entities or {},
                rewritten_query=state.rewritten_query or "",
            )
        )
        asyncio.run(
            mongo.save_message(
                session_id=state.session_id,
                role="assistant",
                text=state.answer or state.confirm_answer,
                intent=state.intent or "",
                citations=state.citations or [],
                sources=state.sources or [],
                images=state.answer_images or [],
            )
        )
        return {}
    except Exception as exc:
        logger.warning(f"Save history skipped: {exc}")
        return {}
