"""Knowledge base API: upload, progress, recommendations, chat, assets."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import List

from fastapi import APIRouter
from fastapi import File
from fastapi import HTTPException
from fastapi import Query
from fastapi import UploadFile
from fastapi.responses import Response
from fastapi.responses import StreamingResponse

from core.llm_factory import get_llm
from core.llm_factory import reset as reset_llm_cache
from core.milvus_manager import MilvusManager
from core.minio_manager import get_object_bytes
from core.config import get_runtime_llm_settings
from core.config import clear_runtime_llm_settings
from core.config import has_runtime_llm_overrides
from core.config import set_runtime_llm_settings
from core.config import get_settings
from core.mongo_manager import MongoManager
from core.tourism_metadata import build_product_id
from core.tourism_metadata import build_suggested_queries
from core.tourism_metadata import infer_city_from_filename
from core.tourism_metadata import infer_doc_type
from graphs.states import IngestState
from graphs.states import RAGChatState
from models.knowledge import ChatHistoryTurn
from models.knowledge import KnowledgeUploadResponse
from models.knowledge import ChatSessionSummary
from models.knowledge import ChatSessionRenameRequest
from models.knowledge import RAGChatRequest
from models.knowledge import RAGChatResponse
from models.knowledge import RecommendationCard
from models.knowledge import RuntimeModelSettings
from models.knowledge import RuntimeModelSettingsTestResponse
from models.knowledge import RuntimeModelSettingsUpdate
from models.knowledge import TaskStatusResponse
from nodes.ingest.document_loader import enrich_markdown_state
from tool.logger import logger

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
_task_status: dict = {}

PLAIN_SYSTEM_PROMPT = "你是一个专业的旅游顾问，请用中文给出清晰、友好、实用的回答。"


def _normalize_history(history: List[ChatHistoryTurn] | List[dict] | None) -> List[dict]:
    items: List[dict] = []
    for turn in history or []:
        role = (turn.role if isinstance(turn, ChatHistoryTurn) else turn.get("role", "")).strip()
        content = (turn.content if isinstance(turn, ChatHistoryTurn) else turn.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            items.append({"role": role, "content": content})
    return items


def _build_plain_llm_messages(system_prompt: str, history: List[dict]):
    try:
        from langchain_core.messages import AIMessage
        from langchain_core.messages import HumanMessage
        from langchain_core.messages import SystemMessage

        llm_messages = [SystemMessage(content=system_prompt)]
        for item in history:
            if item.get("role") == "assistant":
                llm_messages.append(AIMessage(content=item.get("content", "")))
            else:
                llm_messages.append(HumanMessage(content=item.get("content", "")))
        return llm_messages
    except Exception:
        conversation = [system_prompt]
        for item in history:
            prefix = "Assistant" if item.get("role") == "assistant" else "User"
            conversation.append(f"{prefix}: {item.get('content', '')}")
        return conversation


def _strip_current_user(history: List[dict], message: str) -> List[dict]:
    if history and history[-1].get("role") == "user" and history[-1].get("content", "").strip() == message.strip():
        return history[:-1]
    return history


def _ensure_current_user(history: List[dict], message: str) -> List[dict]:
    if history and history[-1].get("role") == "user" and history[-1].get("content", "").strip() == message.strip():
        return history
    return [*history, {"role": "user", "content": message}]


@router.post("/upload", response_model=KnowledgeUploadResponse)
async def upload_file(file: UploadFile = File(...)):
    safe_name = file.filename or "unknown"
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in (".pdf", ".md"):
        raise HTTPException(400, "仅支持 PDF 和 Markdown(.md) 文件")

    upload_dir = os.path.join(os.path.dirname(__file__), "..", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    task_id = uuid.uuid4().hex[:16]
    clean_name = "".join(ch for ch in safe_name if ch.isalnum() or ch in "._- ()（）")
    file_path = os.path.join(upload_dir, f"{task_id}_{clean_name}")

    try:
        with open(file_path, "wb") as handle:
            handle.write(await file.read())
    except Exception as exc:
        logger.error(f"Save upload failed: {exc}")
        raise HTTPException(500, f"文件保存失败: {exc}")

    city = infer_city_from_filename(safe_name)
    doc_type = infer_doc_type(safe_name)
    product_id = build_product_id(city)
    suggested_queries = build_suggested_queries(city, [doc_type])

    try:
        mongo = MongoManager.get()
        await mongo.create_task(task_id, safe_name, city=city, doc_type=doc_type, product_id=product_id, suggested_queries=suggested_queries)
    except Exception as exc:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(500, f"任务创建失败: {exc}")

    _task_status[task_id] = {
        "task_id": task_id,
        "file_name": safe_name,
        "city": city,
        "doc_type": doc_type,
        "product_id": product_id,
        "status": "processing",
        "progress": 0.05,
        "current_step": "文件入队",
        "error": "",
        "suggested_queries": suggested_queries,
        "timeline": [],
    }
    asyncio.create_task(_process(task_id, file_path, safe_name))
    return KnowledgeUploadResponse(task_id=task_id, file_name=safe_name, status="processing")


async def _process(task_id: str, file_path: str, file_name: str):
    from graphs.graph_builder import ingest_graph

    try:
        MilvusManager.ensure_collections()
        is_md = file_name.lower().endswith(".md")
        if is_md:
            with open(file_path, "r", encoding="utf-8") as handle:
                markdown = handle.read()
            init_data = enrich_markdown_state(file_name=file_name, file_path=file_path, content=markdown, task_id=task_id)
            init = IngestState(file_path=file_path, file_name=file_name, task_id=task_id, **init_data)
        else:
            init = IngestState(file_path=file_path, file_name=file_name, task_id=task_id, status="initialized")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: ingest_graph.invoke(init.model_dump()))
        final_state = IngestState(**result)
        if final_state.status == "error":
            await MongoManager.get().update_task(
                task_id,
                status="failed",
                current_step="处理失败",
                error_log=final_state.errors,
            )
        else:
            await MongoManager.get().update_task(
                task_id,
                status="completed",
                progress=1.0,
                current_step="入库完成",
                city=final_state.city,
                doc_type=final_state.doc_type,
                product_id=final_state.product_id,
                suggested_queries=final_state.suggested_queries,
                stats={
                    "chunks": len(final_state.chunks),
                    "images": len(final_state.images),
                    "city": final_state.city,
                    "doc_type": final_state.doc_type,
                },
            )
    except Exception as exc:
        logger.error(f"Ingest failed for {task_id}: {exc}")
        await MongoManager.get().update_task(task_id, status="failed", current_step="处理失败", error_log=[str(exc)])
    finally:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_status(task_id: str):
    data = await MongoManager.get().get_task(task_id)
    if not data and task_id not in _task_status:
        raise HTTPException(404, "任务不存在")
    if data:
        _task_status[task_id] = {**_task_status.get(task_id, {}), **data}
    return TaskStatusResponse(**_task_status[task_id])


@router.get("/tasks", response_model=List[TaskStatusResponse])
async def list_tasks(search: str = Query(default=""), status: str = Query(default="")):
    db_tasks = await MongoManager.get().get_all_tasks(search=search, status=status)
    for task in db_tasks:
        task_id = task.get("task_id")
        if task_id:
            _task_status[task_id] = {**_task_status.get(task_id, {}), **task}
    return [TaskStatusResponse(**_task_status[task["task_id"]]) for task in db_tasks if task.get("task_id")]


@router.get("/recommendations", response_model=List[RecommendationCard])
async def get_recommendations():
    cards = await MongoManager.get().get_city_recommendations(limit=3)
    return [RecommendationCard(**card) for card in cards]


@router.get("/runtime-model-settings", response_model=RuntimeModelSettings)
async def get_runtime_model_settings():
    data = get_runtime_llm_settings()
    return RuntimeModelSettings(
        api_key=data["api_key"],
        base_url=data["base_url"],
        model=data["model"],
        is_default=not has_runtime_llm_overrides(),
    )


@router.post("/runtime-model-settings", response_model=RuntimeModelSettings)
async def update_runtime_model_settings(payload: RuntimeModelSettingsUpdate):
    if not payload.api_key.strip():
        raise HTTPException(400, "API Key 不能为空")
    if not payload.base_url.strip():
        raise HTTPException(400, "Base URL 不能为空")
    if not payload.model.strip():
        raise HTTPException(400, "模型名不能为空")

    set_runtime_llm_settings(payload.api_key, payload.base_url, payload.model)
    reset_llm_cache()
    data = get_runtime_llm_settings()
    return RuntimeModelSettings(
        api_key=data["api_key"],
        base_url=data["base_url"],
        model=data["model"],
        is_default=False,
    )


@router.delete("/runtime-model-settings", response_model=RuntimeModelSettings)
async def reset_runtime_model_settings():
    clear_runtime_llm_settings()
    reset_llm_cache()
    data = get_runtime_llm_settings()
    return RuntimeModelSettings(
        api_key=data["api_key"],
        base_url=data["base_url"],
        model=data["model"],
        is_default=True,
    )


@router.post("/runtime-model-settings/test", response_model=RuntimeModelSettingsTestResponse)
async def test_runtime_model_settings(payload: RuntimeModelSettingsUpdate):
    if not payload.api_key.strip():
        raise HTTPException(400, "API Key 不能为空")
    if not payload.base_url.strip():
        raise HTTPException(400, "Base URL 不能为空")
    if not payload.model.strip():
        raise HTTPException(400, "模型名不能为空")

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage
        from langchain_core.messages import SystemMessage
    except Exception as exc:
        raise HTTPException(500, f"模型测试依赖不可用: {exc}")

    try:
        settings = get_settings()
        client = ChatOpenAI(
            model=payload.model.strip(),
            temperature=settings.llm_default_temperature,
            api_key=payload.api_key.strip(),
            base_url=payload.base_url.strip().rstrip("/"),
            extra_body={"enable_thinking": False},
        )
        await client.ainvoke(
            [
                SystemMessage(content="你是一个连通性测试助手，请只回复ok。"),
                HumanMessage(content="请回复ok"),
            ]
        )
        return RuntimeModelSettingsTestResponse(ok=True, message="连接测试通过，可以保存并生效。")
    except Exception as exc:
        detail = str(exc).strip() or "模型未返回有效响应"
        short_detail = detail.splitlines()[0][:140]
        if "<" in short_detail or "doctype html" in short_detail.lower():
            short_detail = "接口返回异常，请确认 Base URL 指向可用的 OpenAI 兼容服务。"
        return RuntimeModelSettingsTestResponse(
            ok=False,
            message=f"当前自定义模型暂不可用，请切回默认模型，或检查 API Key、Base URL 和模型名后重新测试。{short_detail}",
        )


@router.get("/assets/{bucket_name}/{object_path:path}")
async def get_asset(bucket_name: str, object_path: str):
    try:
        data, content_type = get_object_bytes(bucket_name, object_path)
        return Response(content=data, media_type=content_type)
    except Exception as exc:
        raise HTTPException(404, f"图片读取失败: {exc}")


@router.delete("/task/{task_id}")
async def delete_task(task_id: str):
    mongo = MongoManager.get()
    task = await mongo.get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    file_name = task.get("file_name")
    if file_name:
        try:
            MilvusManager.delete_by_source_file(file_name)
        except Exception as exc:
            raise HTTPException(500, f"向量删除失败: {exc}")
    await mongo.delete_task(task_id)
    _task_status.pop(task_id, None)
    return {"ok": True}


@router.post("/chat/stream")
async def rag_chat_stream(request: RAGChatRequest):
    mongo = MongoManager.get()
    session_id = request.session_id or (f"guest_{uuid.uuid4().hex[:12]}" if request.guest_mode else await mongo.next_session_id())
    should_rag = False
    rag_state: RAGChatState | None = None
    request_history = _normalize_history(request.history)

    if request.rag_enabled:
        try:
            if await mongo.has_completed_tasks():
                should_rag = True
                if request_history:
                    history_dicts = _strip_current_user(request_history, request.message)
                elif request.guest_mode:
                    history_dicts = []
                else:
                    history = await mongo.get_recent(session_id, limit=10)
                    history_dicts = [{"role": msg.get("role", ""), "content": msg.get("content", "")} for msg in history]
                init = RAGChatState(
                    query=request.message,
                    session_id=session_id,
                    guest_mode=request.guest_mode,
                    history=history_dicts,
                )
                from graphs.graph_builder import query_graph

                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, lambda: query_graph.invoke(init.model_dump()))
                rag_state = RAGChatState(**result)
        except Exception as exc:
            logger.error(f"RAG flow failed, fallback to plain chat: {exc}")

    async def generate():
        full = ""
        try:
            if should_rag and rag_state:
                if rag_state.confirm_answer:
                    full = rag_state.confirm_answer
                    yield _sse(
                        {
                            "token": full,
                            "session_id": session_id,
                            "sources": [],
                            "images": rag_state.answer_images,
                            "rag_referenced": False,
                            "confirm_answer": True,
                        }
                    )
                else:
                    from nodes.query.citation_answer import citation_answer_stream

                    async for token in citation_answer_stream(rag_state):
                        full += token
                        yield _sse(
                            {
                                "token": token,
                                "session_id": session_id,
                                "sources": rag_state.sources,
                                "rag_referenced": True,
                            }
                        )
                yield _sse(
                    {
                        "done": True,
                        "session_id": session_id,
                        "sources": rag_state.sources if rag_state else [],
                        "images": rag_state.answer_images if rag_state else [],
                        "recommendations": rag_state.recommended_queries if rag_state else [],
                        "rag_referenced": bool(rag_state and not rag_state.confirm_answer),
                    }
                )
                return

            if not request.guest_mode:
                await mongo.save_message(session_id, "user", request.message)
            llm = get_llm()
            if not llm:
                fallback = "抱歉，AI 服务暂时不可用，请稍后再试。"
                if not request.guest_mode:
                    await mongo.save_message(session_id, "assistant", fallback)
                yield _sse({"token": fallback, "session_id": session_id, "rag_referenced": False})
                yield _sse({"done": True, "session_id": session_id, "sources": [], "images": []})
                return

            if request_history:
                llm_history = _ensure_current_user(request_history, request.message)
            elif request.guest_mode:
                llm_history = [{"role": "user", "content": request.message}]
            else:
                history = await mongo.get_recent(session_id, limit=10)
                llm_history = [{"role": msg.get("role", ""), "content": msg.get("content", "")} for msg in history]
                llm_history.append({"role": "user", "content": request.message})

            llm_messages = _build_plain_llm_messages(PLAIN_SYSTEM_PROMPT, llm_history)

            async for chunk in llm.astream(llm_messages):
                if chunk.content:
                    full += chunk.content
                    yield _sse({"token": chunk.content, "session_id": session_id, "rag_referenced": False})
            if not request.guest_mode:
                await mongo.save_message(session_id, "assistant", full)
            yield _sse({"done": True, "session_id": session_id, "sources": [], "images": []})
        except Exception as exc:
            logger.error(f"Stream error: {exc}")
            yield _sse({"error": str(exc), "session_id": session_id})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/chat", response_model=RAGChatResponse)
async def rag_chat(request: RAGChatRequest):
    mongo = MongoManager.get()
    session_id = request.session_id or (f"guest_{uuid.uuid4().hex[:12]}" if request.guest_mode else await mongo.next_session_id())
    request_history = _normalize_history(request.history)

    if not request.rag_enabled:
        llm = get_llm()
        if not llm:
            return RAGChatResponse(session_id=session_id, message="抱歉，AI 服务暂时不可用，请稍后再试。")

        if request_history:
            llm_history = _ensure_current_user(request_history, request.message)
        elif request.guest_mode or not request.session_id:
            llm_history = [{"role": "user", "content": request.message}]
        else:
            history = await mongo.get_recent(session_id, limit=10)
            llm_history = [{"role": msg.get("role", ""), "content": msg.get("content", "")} for msg in history]
            llm_history.append({"role": "user", "content": request.message})

        llm_messages = _build_plain_llm_messages(PLAIN_SYSTEM_PROMPT, llm_history)

        chunks: list[str] = []
        async for chunk in llm.astream(llm_messages):
            if chunk.content:
                chunks.append(chunk.content)
        return RAGChatResponse(session_id=session_id, message="".join(chunks))

    if request_history:
        history_payload = _strip_current_user(request_history, request.message)
    elif request.session_id and not request.guest_mode:
        history = await mongo.get_recent(session_id, limit=10)
        history_payload = [{"role": msg.get("role", ""), "content": msg.get("content", "")} for msg in history]
    else:
        history_payload = []
    init = RAGChatState(
        query=request.message,
        session_id=session_id,
        guest_mode=request.guest_mode,
        history=history_payload,
    )
    from graphs.graph_builder import query_graph

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: query_graph.invoke(init.model_dump()))
    state = RAGChatState(**result)
    answer = state.confirm_answer or state.answer or "抱歉，未能生成回答。"
    return RAGChatResponse(
        session_id=init.session_id,
        message=answer,
        sources=state.sources,
        citations=state.citations,
        images=state.answer_images,
    )


@router.get("/chat/{session_id}/history")
async def get_history(session_id: str):
    messages = await MongoManager.get().get_recent(session_id, limit=50)
    return {"session_id": session_id, "messages": messages, "total": len(messages)}


@router.get("/chat/sessions", response_model=List[ChatSessionSummary])
async def list_chat_sessions():
    sessions = await MongoManager.get().get_chat_sessions(limit=100)
    return [ChatSessionSummary(**session) for session in sessions]


@router.delete("/chat/{session_id}")
async def delete_chat_session(session_id: str):
    deleted = await MongoManager.get().delete_session(session_id)
    return {"ok": True, "session_id": session_id, "deleted": deleted}


@router.patch("/chat/{session_id}")
async def rename_chat_session(session_id: str, payload: ChatSessionRenameRequest):
    renamed = await MongoManager.get().rename_session(session_id, payload.title)
    if not renamed:
        raise HTTPException(404, "会话不存在")
    return {"ok": True, "session_id": session_id, "title": payload.title.strip()}


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
