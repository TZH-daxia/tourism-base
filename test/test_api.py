import os
import sys
import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def mock_services():
    importlib.import_module("api.knowledge")
    mongo_patch = patch("api.knowledge.MongoManager")
    milvus_patch = patch("api.knowledge.MilvusManager")
    llm_patch = patch("api.knowledge.get_llm")
    reset_llm_patch = patch("api.knowledge.reset_llm_cache")

    mock_mongo_cls = mongo_patch.start()
    mock_milvus_cls = milvus_patch.start()
    mock_llm = llm_patch.start()
    mock_reset_llm = reset_llm_patch.start()

    mgr = MagicMock()
    mgr.get_recent = AsyncMock(return_value=[])
    mgr.save_message = AsyncMock(return_value="msg_001")
    mgr.create_task = AsyncMock(return_value="task_001")
    mgr.get_task = AsyncMock(return_value=None)
    mgr.get_all_tasks = AsyncMock(return_value=[])
    mgr.delete_task = AsyncMock(return_value=None)
    mgr.delete_session = AsyncMock(return_value=2)
    mgr.rename_session = AsyncMock(return_value=True)
    mgr.get_chat_sessions = AsyncMock(return_value=[])
    mgr.has_completed_tasks = AsyncMock(return_value=False)
    mgr.update_task = AsyncMock()
    mgr.ensure_indexes = AsyncMock()
    mgr.next_session_id = AsyncMock(return_value="1")
    mock_mongo_cls.get.return_value = mgr

    yield {
        "mongo_cls": mock_mongo_cls,
        "mongo_mgr": mgr,
        "milvus_cls": mock_milvus_cls,
        "llm": mock_llm,
        "reset_llm": mock_reset_llm,
    }

    mongo_patch.stop()
    milvus_patch.stop()
    llm_patch.stop()
    reset_llm_patch.stop()


@pytest.fixture
def client():
    from main import app

    return TestClient(app)


class TestUpload:
    def test_reject_invalid_extension(self, client):
        resp = client.post("/api/knowledge/upload", files={"file": ("test.txt", b"hello", "text/plain")})
        assert resp.status_code == 400

    def test_accept_pdf(self, client):
        resp = client.post("/api/knowledge/upload", files={"file": ("doc.pdf", b"%PDF-1.4 test", "application/pdf")})
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"]
        assert data["status"] == "processing"

    def test_accept_md(self, client):
        resp = client.post("/api/knowledge/upload", files={"file": ("readme.md", b"# Hello", "text/markdown")})
        assert resp.status_code == 200
        assert resp.json()["status"] == "processing"


class TestChatStream:
    def _read_sse(self, resp):
        events = []
        for line in resp.iter_lines():
            if line.startswith("data: "):
                import json

                events.append(json.loads(line[6:]))
        return events

    def test_chat_without_rag_returns_sse_tokens(self, client, mock_services):
        class FakeChunk:
            def __init__(self, c):
                self.content = c

        async def mock_astream(messages):
            yield FakeChunk("你好")
            yield FakeChunk("，有什么可以帮您？")

        mock_services["llm"].return_value.astream = mock_astream

        resp = client.post("/api/knowledge/chat/stream", json={"message": "你好", "rag_enabled": False})
        assert resp.status_code == 200
        events = self._read_sse(resp)
        assert "你好" in "".join(e["token"] for e in events if "token" in e)
        assert any(e.get("done") for e in events)

    def test_chat_without_rag_handles_llm_error(self, client, mock_services):
        async def mock_astream_error(messages):
            raise RuntimeError("API rate limit exceeded")
            yield

        mock_services["llm"].return_value.astream = mock_astream_error

        resp = client.post("/api/knowledge/chat/stream", json={"message": "测试错误", "rag_enabled": False})
        assert resp.status_code == 200
        events = self._read_sse(resp)
        assert any(e.get("error") or ("错误" in str(e.get("token", ""))) for e in events)

    def test_chat_without_rag_handles_null_llm(self, client, mock_services):
        mock_services["llm"].return_value = None

        resp = client.post("/api/knowledge/chat/stream", json={"message": "你好", "rag_enabled": False})
        assert resp.status_code == 200
        events = self._read_sse(resp)
        combined = "".join(e["token"] for e in events if "token" in e)
        assert "抱歉" in combined or "不可用" in combined

    def test_chat_with_rag_when_no_tasks_falls_back(self, client, mock_services):
        class FakeChunk:
            def __init__(self, c):
                self.content = c

        async def mock_astream(messages):
            yield FakeChunk("fallback response")

        mock_services["llm"].return_value.astream = mock_astream

        resp = client.post("/api/knowledge/chat/stream", json={"message": "三亚有什么景点？", "rag_enabled": True})
        assert resp.status_code == 200
        events = self._read_sse(resp)
        assert "fallback" in "".join(e["token"] for e in events if "token" in e)

    def test_chat_stream_saves_session_id(self, client, mock_services):
        class FakeChunk:
            def __init__(self, c):
                self.content = c

        async def mock_astream(messages):
            yield FakeChunk("ok")

        mock_services["llm"].return_value.astream = mock_astream

        resp = client.post("/api/knowledge/chat/stream", json={"message": "hi", "rag_enabled": False})
        events = self._read_sse(resp)
        done_events = [e for e in events if e.get("done")]
        assert len(done_events) == 1
        assert done_events[0].get("session_id")

    def test_plain_chat_saves_user_and_assistant_once_each(self, client, mock_services):
        class FakeChunk:
            def __init__(self, c):
                self.content = c

        async def mock_astream(messages):
            yield FakeChunk("ok")

        mock_services["llm"].return_value.astream = mock_astream

        resp = client.post("/api/knowledge/chat/stream", json={"message": "hello", "rag_enabled": False})
        assert resp.status_code == 200
        mgr = mock_services["mongo_mgr"]
        assert mgr.save_message.await_count == 2


class TestChatPlainApi:
    def test_chat_endpoint_respects_rag_toggle(self, client, mock_services):
        class FakeChunk:
            def __init__(self, c):
                self.content = c

        async def mock_astream(messages):
            yield FakeChunk("plain ")
            yield FakeChunk("answer")

        mock_services["llm"].return_value.astream = mock_astream

        resp = client.post("/api/knowledge/chat", json={"message": "hello", "rag_enabled": False})
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "plain answer"
        assert data["sources"] == []
        mock_services["mongo_mgr"].get_recent.assert_not_awaited()


class TestTasks:
    def test_list_tasks(self, client):
        resp = client.get("/api/knowledge/tasks")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_tasks_supports_filters(self, client, mock_services):
        mock_services["mongo_mgr"].get_all_tasks.return_value = [
            {"task_id": "t1", "file_name": "sanya.pdf", "status": "completed", "progress": 1.0, "current_step": "done"}
        ]

        resp = client.get("/api/knowledge/tasks?search=sanya&status=completed")
        assert resp.status_code == 200
        mock_services["mongo_mgr"].get_all_tasks.assert_awaited_with(search="sanya", status="completed")
        assert resp.json()[0]["file_name"] == "sanya.pdf"

    def test_delete_task_removes_db_record_and_vectors(self, client, mock_services):
        mock_services["mongo_mgr"].get_task.return_value = {
            "task_id": "t1",
            "file_name": "sanya.pdf",
            "status": "completed",
        }

        resp = client.delete("/api/knowledge/task/t1")
        assert resp.status_code == 200
        mock_services["mongo_mgr"].get_task.assert_awaited_with("t1")
        mock_services["milvus_cls"].delete_by_source_file.assert_called_once_with("sanya.pdf")
        mock_services["mongo_mgr"].delete_task.assert_awaited_with("t1")

    def test_delete_task_keeps_record_when_vector_delete_fails(self, client, mock_services):
        mock_services["mongo_mgr"].get_task.return_value = {
            "task_id": "t1",
            "file_name": "sanya.pdf",
            "status": "completed",
        }
        mock_services["milvus_cls"].delete_by_source_file.side_effect = RuntimeError("boom")

        resp = client.delete("/api/knowledge/task/t1")
        assert resp.status_code == 500
        mock_services["mongo_mgr"].delete_task.assert_not_awaited()

    def test_get_nonexistent_status(self, client):
        resp = client.get("/api/knowledge/status/nonexistent")
        assert resp.status_code == 404


class TestRuntimeModelSettings:
    def test_get_runtime_model_settings(self, client):
        resp = client.get("/api/knowledge/runtime-model-settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["vision_required"] is True
        assert data["is_default"] is True
        assert "warning" in data

    def test_update_runtime_model_settings(self, client, mock_services):
        resp = client.post(
            "/api/knowledge/runtime-model-settings",
            json={
                "api_key": "sk-demo",
                "base_url": "https://example.com/v1/",
                "model": "gpt-4.1-mini",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["api_key"] == "sk-demo"
        assert data["base_url"] == "https://example.com/v1"
        assert data["model"] == "gpt-4.1-mini"
        assert data["is_default"] is False
        mock_services["reset_llm"].assert_called_once()

    def test_reset_runtime_model_settings(self, client, mock_services):
        resp = client.delete("/api/knowledge/runtime-model-settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_default"] is True
        mock_services["reset_llm"].assert_called()


class TestHistory:
    def test_get_history(self, client):
        resp = client.get("/api/knowledge/chat/test_session/history")
        assert resp.status_code == 200
        data = resp.json()
        assert "messages" in data
        assert "total" in data

    def test_list_chat_sessions_sorted_from_backend(self, client, mock_services):
        mock_services["mongo_mgr"].get_chat_sessions.return_value = [
            {
                "session_id": "2",
                "title": "第二个会话",
                "updated_at": "2026-05-22T10:00:00",
                "created_at": "2026-05-22T09:00:00",
                "message_count": 4,
            },
            {
                "session_id": "1",
                "title": "第一个会话",
                "updated_at": "2026-05-22T09:00:00",
                "created_at": "2026-05-22T08:00:00",
                "message_count": 2,
            },
        ]

        resp = client.get("/api/knowledge/chat/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert [item["session_id"] for item in data] == ["2", "1"]
        assert data[0]["message_count"] == 4

    def test_delete_chat_session_removes_mongo_messages(self, client, mock_services):
        resp = client.delete("/api/knowledge/chat/session_1")
        assert resp.status_code == 200
        mock_services["mongo_mgr"].delete_session.assert_awaited_with("session_1")
        assert resp.json()["deleted"] == 2

    def test_rename_chat_session(self, client, mock_services):
        resp = client.patch("/api/knowledge/chat/2", json={"title": "新的标题"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "新的标题"
        mock_services["mongo_mgr"].rename_session.assert_awaited_with("2", "新的标题")
