"""节点: RRF 多路融合排序"""
from typing import Dict, Any, List
from graphs.states import RAGChatState
from tool.logger import logger


def rrf_merge(state: RAGChatState) -> Dict[str, Any]:
    logger.info("RRF 融合开始")
    try:
        k = 60
        scores: Dict[str, float] = {}
        mapping: Dict[str, Dict] = {}

        for chunks, w in [(state.embedding_chunks, 1.0), (state.hyde_chunks, 0.8), (state.web_search_docs, 0.5)]:
            for rank, c in enumerate(chunks):
                cid = c.get("chunk_id", f"unknown_{rank}")
                scores[cid] = scores.get(cid, 0.0) + w / (k + rank + 1)
                if cid not in mapping:
                    mapping[cid] = c

        sorted_ids = sorted(scores, key=scores.get, reverse=True)
        rrf_chunks = []
        for cid in sorted_ids[:20]:
            c = mapping[cid].copy()
            c["rrf_score"] = scores[cid]
            rrf_chunks.append(c)

        logger.info(f"RRF 融合完成: {len(rrf_chunks)} 条 (从 {len(mapping)} 条去重)")
        return {"rrf_chunks": rrf_chunks}
    except Exception as e:
        logger.error(f"RRF 融合失败: {e}")
        return {"errors": state.errors + [f"[rrf] {e}"], "rrf_chunks": []}
