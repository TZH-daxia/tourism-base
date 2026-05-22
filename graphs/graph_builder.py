"""LangGraph 编排 — 导入图 + 查询图"""
from langgraph.graph import StateGraph, END
from langgraph.types import Send
from core.config import get_settings
from graphs.states import IngestState, RAGChatState
from tool.logger import logger


def _route_after(next_node: str):
    def router(state: IngestState) -> str:
        return "end" if state.status == "error" else next_node
    return router


def build_ingest_graph():
    from nodes.ingest.document_loader import document_loader
    from nodes.ingest.image_processor import image_processor
    from nodes.ingest.tourism_splitter import tourism_splitter
    from nodes.ingest.entity_extractor import entity_extractor
    from nodes.ingest.embedding import embedding_node
    from nodes.ingest.vector_store import vector_store
    from nodes.ingest.task_tracker import task_tracker

    w = StateGraph(IngestState)
    for name, fn in [("document_loader", document_loader), ("image_processor", image_processor),
                      ("tourism_splitter", tourism_splitter), ("entity_extractor", entity_extractor),
                      ("embedding", embedding_node), ("vector_store", vector_store),
                      ("task_tracker", task_tracker)]:
        w.add_node(name, fn)

    def entry(state: IngestState) -> str:
        return "image_processor" if state.status == "loaded" else "document_loader"

    w.set_conditional_entry_point(entry, {"document_loader": "document_loader", "image_processor": "image_processor"})
    for cur, nxt in [("document_loader", "image_processor"), ("image_processor", "tourism_splitter"),
                      ("tourism_splitter", "entity_extractor"), ("entity_extractor", "embedding"),
                      ("embedding", "vector_store"), ("vector_store", "task_tracker")]:
        w.add_conditional_edges(cur, _route_after(nxt), {nxt: nxt, "end": END})
    w.add_edge("task_tracker", END)
    logger.info("导入图构建完成")
    return w.compile()


def build_query_graph():
    from nodes.query.entity_intent_confirm import entity_intent_confirm
    from nodes.query.search_embedding import search_embedding
    from nodes.query.search_hyde import search_hyde
    from nodes.query.web_search_mcp import web_search_mcp
    from nodes.query.rrf import rrf_merge
    from nodes.query.rerank import rerank
    from nodes.query.citation_answer import citation_answer
    from nodes.query.save_history import save_history

    w = StateGraph(RAGChatState)
    for name, fn in [("entity_intent_confirm", entity_intent_confirm),
                      ("search_embedding", search_embedding), ("search_hyde", search_hyde),
                      ("web_search_mcp", web_search_mcp), ("rrf_merge", rrf_merge),
                      ("rerank", rerank), ("citation_answer", citation_answer),
                      ("save_history", save_history)]:
        w.add_node(name, fn)

    w.set_entry_point("entity_intent_confirm")

    def route_after_confirm(state: RAGChatState):
        if state.confirm_answer:
            return "direct_answer"
        routes = [Send("search_embedding", state), Send("search_hyde", state)]
        if get_settings().enable_web_search:
            routes.append(Send("web_search_mcp", state))
        return routes

    w.add_conditional_edges("entity_intent_confirm", route_after_confirm, {"direct_answer": "save_history"})
    w.add_edge("search_embedding", "rrf_merge")
    w.add_edge("search_hyde", "rrf_merge")
    w.add_edge("web_search_mcp", "rrf_merge")
    w.add_edge("rrf_merge", "rerank")
    w.add_edge("rerank", "citation_answer")
    w.add_edge("citation_answer", "save_history")
    w.add_edge("save_history", END)
    logger.info("查询图构建完成（7节点+并发三路检索）")
    return w.compile()


ingest_graph = build_ingest_graph()
query_graph = build_query_graph()
