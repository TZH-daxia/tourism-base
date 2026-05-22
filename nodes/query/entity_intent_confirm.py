"""Extract city intent and resolve product ids before retrieval."""

from __future__ import annotations

import json
import re
from typing import Any
from typing import Dict
from typing import List

from core.embedding_factory import encode_single
from core.llm_factory import get_llm
from core.milvus_manager import MilvusManager
from core.tourism_metadata import build_suggested_queries
from core.tourism_metadata import detect_need_images
from core.tourism_metadata import infer_city_from_filename
from core.tourism_metadata import OVERVIEW_DOC_TYPES
from graphs.states import RAGChatState
from tool.logger import logger

PROMPT = """你是旅游知识库查询意图分析助手。
请根据历史对话和当前问题，提取：
1. city: 用户想咨询的城市
2. intent: city_overview / traffic / scenic / hotel / food / route / image_search
3. requested_doc_types: 从 [交通指南, 景点攻略, 酒店信息, 美食推荐, 线路推荐] 中选择 1 到多个
4. rewritten_query: 补全后的独立问题

历史对话：
{history}

当前问题：
{query}

只输出 JSON。"""

DOC_TYPE_MAP = {
    "traffic": ["交通指南"],
    "scenic": ["景点攻略"],
    "hotel": ["酒店信息"],
    "food": ["美食推荐"],
    "route": ["线路推荐"],
    "image_search": ["景点攻略", "线路推荐"],
    "city_overview": OVERVIEW_DOC_TYPES,
}


def entity_intent_confirm(state: RAGChatState) -> Dict[str, Any]:
    logger.info(f"Confirm entity and intent: {state.query[:50]}")
    try:
        extracted = _extract_city_and_intent(state)
        city = extracted.get("city", "")
        intent = extracted.get("intent", "city_overview")
        requested_doc_types = extracted.get("requested_doc_types") or DOC_TYPE_MAP.get(intent, OVERVIEW_DOC_TYPES)
        if _is_city_overview_query(state.query):
            intent = "city_overview"
            requested_doc_types = OVERVIEW_DOC_TYPES
        rewritten_query = extracted.get("rewritten_query") or state.query
        need_images = detect_need_images(state.query) or intent == "image_search"

        query_dense, query_sparse = encode_single(rewritten_query)
        search_text = city or rewritten_query
        product_dense, product_sparse = encode_single(search_text)
        product_hits = MilvusManager.search_products(product_dense, product_sparse, top_k=5)
        products = _normalize_product_hits(product_hits)

        if city:
            filtered = [item for item in products if city == item.get("city")]
            if filtered:
                products = filtered

        unique_products = []
        seen_ids = set()
        for product in products:
            pid = product.get("product_id", "")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                unique_products.append(product)

        if not unique_products:
            return {
                "confirm_answer": "暂时没有检索到这个城市的旅游知识，您可以换个城市试试，或者先上传对应资料。",
                "query_dense": query_dense,
                "query_sparse": query_sparse,
            }

        primary_city = city or unique_products[0].get("city", "")
        product_ids = [item["product_id"] for item in unique_products[:3]]
        product_names = [item.get("product_name") or item.get("city") for item in unique_products[:3]]
        recommended_queries = unique_products[0].get("suggested_queries") or build_suggested_queries(primary_city, requested_doc_types)

        return {
            "city": primary_city,
            "intent": intent,
            "rewritten_query": rewritten_query,
            "requested_doc_types": requested_doc_types,
            "product_ids": product_ids,
            "product_names": product_names,
            "recommended_queries": recommended_queries,
            "need_images": need_images,
            "query_dense": query_dense,
            "query_sparse": query_sparse,
            "entities": {"city": primary_city, "doc_types": requested_doc_types},
        }
    except Exception as exc:
        logger.error(f"Entity confirm failed: {exc}")
        return {
            "errors": state.errors + [f"[entity_intent_confirm] {exc}"],
            "confirm_answer": "抱歉，当前无法解析您的问题，请稍后重试。",
        }


def _extract_city_and_intent(state: RAGChatState) -> Dict[str, Any]:
    history_text = "\n".join(f"{item.get('role', '')}: {item.get('content', '')}" for item in (state.history or [])[-6:])
    fallback = _fallback_extract(state.query, history_text)
    llm = get_llm(json_mode=True)
    if not llm:
        return fallback
    try:
        from langchain_core.messages import HumanMessage

        resp = llm.invoke([HumanMessage(content=PROMPT.format(history=history_text or "无", query=state.query))])
        parsed = _parse_json(resp.content)
        if parsed.get("city"):
            return {
                "city": parsed.get("city", ""),
                "intent": parsed.get("intent", fallback["intent"]),
                "requested_doc_types": parsed.get("requested_doc_types", fallback["requested_doc_types"]),
                "rewritten_query": parsed.get("rewritten_query", state.query),
            }
    except Exception as exc:
        logger.warning(f"LLM city extraction skipped: {exc}")
    return fallback


def _fallback_extract(query: str, history_text: str) -> Dict[str, Any]:
    merged = f"{history_text}\n{query}"
    city = ""
    for candidate in re.findall(r"[\u4e00-\u9fff]{2,4}", merged):
        if candidate.endswith(("攻略", "酒店", "美食", "线路", "交通")):
            continue
        city = infer_city_from_filename(candidate)
        if city:
            break
    intent = "city_overview"
    if any(token in query for token in ("交通", "怎么去", "机场", "高铁")):
        intent = "traffic"
    elif any(token in query for token in ("酒店", "住宿", "住哪")):
        intent = "hotel"
    elif any(token in query for token in ("美食", "好吃", "吃什么")):
        intent = "food"
    elif any(token in query for token in ("路线", "线路", "行程")):
        intent = "route"
    elif any(token in query for token in ("图片", "照片", "看看", "长什么样")):
        intent = "image_search"
    elif any(token in query for token in ("景点", "好玩", "玩什么", "推荐")):
        intent = "city_overview"
    return {
        "city": city,
        "intent": intent,
        "requested_doc_types": DOC_TYPE_MAP.get(intent, OVERVIEW_DOC_TYPES),
        "rewritten_query": query,
    }


def _normalize_product_hits(hits: List[Dict]) -> List[Dict]:
    rows = []
    for hit in hits:
        entity = hit.get("entity", {})
        suggested = entity.get("suggested_queries", "[]")
        try:
            suggested_queries = json.loads(suggested) if suggested else []
        except json.JSONDecodeError:
            suggested_queries = []
        rows.append(
            {
                "product_id": entity.get("product_id", ""),
                "product_name": entity.get("product_name", ""),
                "city": entity.get("city", ""),
                "doc_type": entity.get("doc_type", ""),
                "score": hit.get("distance", 0.0),
                "suggested_queries": suggested_queries,
            }
        )
    rows.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    return rows


def _is_city_overview_query(query: str) -> bool:
    tokens = ("有什么好玩的", "好玩的", "怎么玩", "推荐", "攻略", "第一次去", "旅游建议")
    return any(token in (query or "") for token in tokens)


def _parse_json(content: str) -> Dict[str, Any]:
    try:
        return json.loads(content.strip())
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            return json.loads(match.group())
    return {}
