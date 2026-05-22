"""Generate tourism answers with grouped categories and image extraction."""

from __future__ import annotations

from typing import Any
from typing import AsyncGenerator
from typing import Dict

from core.llm_factory import get_llm
from graphs.states import RAGChatState
from tool.logger import logger

PROMPT = """你是一个旅游规划顾问，请基于知识库资料回答用户问题。

要求：
1. 如果用户是在问某个城市“有什么好玩的”，请优先按 景点、线路、酒店、美食、交通 五个部分组织。
2. 只使用参考资料中的信息，不要编造。
3. 用适合游客阅读的中文表达，适度美化措辞，但不要脱离资料。
4. 如果参考资料带有图片链接，不要把链接原样堆在正文里。

参考资料：
{context}

用户问题：
{query}
"""


def citation_answer(state: RAGChatState) -> Dict[str, Any]:
    logger.info("Generate final answer")
    try:
        query = state.rewritten_query or state.query
        context = _build_context(state.reranked_docs)
        answer, images = _generate_answer(query, context, state.reranked_docs)
        return {
            "answer": answer,
            "sources": _extract_sources(state.reranked_docs),
            "citations": _extract_citations(state.reranked_docs),
            "answer_images": images,
        }
    except Exception as exc:
        logger.error(f"Answer generation failed: {exc}")
        return {
            "errors": state.errors + [f"[citation_answer] {exc}"],
            "answer": "抱歉，当前暂时无法生成结果，请稍后再试。",
            "sources": [],
            "citations": [],
            "answer_images": [],
        }


async def citation_answer_stream(state: RAGChatState) -> AsyncGenerator[str, None]:
    try:
        query = state.rewritten_query or state.query
        context = _build_context(state.reranked_docs)
        llm = get_llm()
        if not llm:
            yield _fallback_answer(query, state.reranked_docs)
            return
        from langchain_core.messages import HumanMessage
        from langchain_core.messages import SystemMessage

        async for chunk in llm.astream(
            [SystemMessage(content=PROMPT.format(context=context, query=query)), HumanMessage(content=query)]
        ):
            if chunk.content:
                yield chunk.content
    except Exception as exc:
        logger.error(f"Streaming answer failed: {exc}")
        yield f"[错误] {exc}"


def _generate_answer(query: str, context: str, docs: list[dict]) -> tuple[str, list[dict]]:
    llm = get_llm()
    images = _extract_images(docs)
    if not llm:
        return _fallback_answer(query, docs), images
    from langchain_core.messages import HumanMessage
    from langchain_core.messages import SystemMessage

    resp = llm.invoke([SystemMessage(content=PROMPT.format(context=context, query=query)), HumanMessage(content=query)])
    return resp.content, images


def _build_context(docs: list[dict]) -> str:
    if not docs:
        return "暂无相关资料。"
    grouped: dict[str, list[str]] = {}
    for doc in docs:
        doc_type = doc.get("doc_type") or "旅游资料"
        grouped.setdefault(doc_type, []).append(
            f"标题：{doc.get('title', '')}\n来源：{doc.get('source_file', '')}\n内容：{doc.get('content', '')}"
        )
    parts = []
    for doc_type, items in grouped.items():
        parts.append(f"## {doc_type}\n" + "\n\n".join(items[:3]))
    return "\n\n".join(parts)


def _extract_images(docs: list[dict]) -> list[dict]:
    image_map: dict[str, dict] = {}
    for doc in docs:
        urls = doc.get("image_urls") or []
        alts = doc.get("image_alts") or []
        for index, url in enumerate(urls):
            if not url or url in image_map:
                continue
            image_map[url] = {
                "url": url,
                "alt": alts[index] if index < len(alts) else "旅游图片",
                "title": doc.get("title", ""),
                "city": doc.get("city", ""),
                "doc_type": doc.get("doc_type", ""),
                "source_file": doc.get("source_file", ""),
            }
    return list(image_map.values())[:6]


def _extract_sources(docs: list[dict]) -> list[dict]:
    seen = set()
    sources = []
    for doc in docs:
        key = (doc.get("source_file", ""), doc.get("doc_type", ""))
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            {
                "file_name": doc.get("source_file", ""),
                "url": doc.get("source_url", ""),
                "doc_type": doc.get("doc_type", ""),
                "city": doc.get("city", ""),
            }
        )
    return sources


def _extract_citations(docs: list[dict]) -> list[dict]:
    citations = []
    for index, doc in enumerate(docs[:8], start=1):
        citations.append(
            {
                "id": index,
                "title": doc.get("source_file", ""),
                "doc_type": doc.get("doc_type", ""),
                "city": doc.get("city", ""),
                "url": doc.get("source_url", ""),
            }
        )
    return citations


def _fallback_answer(query: str, docs: list[dict]) -> str:
    if not docs:
        return "暂时没有检索到相关旅游资料。"
    city = docs[0].get("city", "")
    lines = [f"已为您整理 {city} 的旅游资料："] if city else ["已为您整理相关旅游资料："]
    for doc in docs[:5]:
        lines.append(f"- {doc.get('doc_type', '资料')}：{doc.get('content', '')[:140]}")
    return "\n".join(lines)
