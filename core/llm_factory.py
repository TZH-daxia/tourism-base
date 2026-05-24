"""LLM factory with graceful fallback when dependencies are unavailable."""

from __future__ import annotations

from typing import Any

from core.config import get_runtime_llm_settings
from core.config import get_settings
from tool.logger import logger

_cache: dict[tuple[str, bool], Any] = {}


def get_llm(model: str | None = None, json_mode: bool = False):
    settings = get_settings()
    runtime = get_runtime_llm_settings()
    model_name = model or runtime["model"] or settings.llm_default_model
    key = (runtime["base_url"], model_name, json_mode)
    if key in _cache:
        return _cache[key]
    try:
        from langchain_openai import ChatOpenAI
    except Exception as exc:
        logger.warning(f"langchain_openai unavailable: {exc}")
        _cache[key] = None
        return None

    model_kwargs: dict = {}
    if json_mode:
        model_kwargs["response_format"] = {"type": "json_object"}
    client = ChatOpenAI(
        model=model_name,
        temperature=settings.llm_default_temperature,
        api_key=runtime["api_key"],
        base_url=runtime["base_url"],
        timeout=30,
        max_retries=1,
        extra_body={"enable_thinking": False},
        model_kwargs=model_kwargs,
    )
    _cache[key] = client
    return client


def reset():
    _cache.clear()
