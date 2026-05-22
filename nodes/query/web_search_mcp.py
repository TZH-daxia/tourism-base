"""节点: MCP 实时搜索 — 天气/门票/交通"""
import httpx, time
from typing import Dict, Any
from core.config import get_settings
from graphs.states import RAGChatState
from tool.logger import logger


def web_search_mcp(state: RAGChatState) -> Dict[str, Any]:
    logger.info("MCP 搜索开始")
    try:
        settings = get_settings()
        if not settings.bailian_mcp_api_key:
            return {"web_search_docs": []}

        query = state.rewritten_query or state.query
        payload = {"api_key": settings.bailian_mcp_api_key, "query": query, "count": 3, "type": "web"}
        try:
            resp = httpx.post(settings.mcp_dashscope_base_url,
                              headers={"Content-Type": "application/json", "Authorization": f"Bearer {settings.bailian_mcp_api_key}"},
                              json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("result", {}).get("items", []) if data.get("status") == "success" else []
        except Exception as e:
            logger.warning(f"MCP 调用失败: {e}")
            return {"web_search_docs": []}

        docs = [{"chunk_id": f"web_{i}", "content": r.get("content", ""),
                  "source_file": r.get("url", ""), "score": 0.0, "source_type": "web"}
                for i, r in enumerate(items)]
        logger.info(f"MCP 搜索完成: {len(docs)} 条")
        return {"web_search_docs": docs}
    except Exception as e:
        logger.error(f"MCP 搜索失败: {e}")
        return {"errors": state.errors + [f"[web_search_mcp] {e}"], "web_search_docs": []}
