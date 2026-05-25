"""MongoDB manager for chat history and knowledge ingestion tasks."""

from collections import defaultdict
from datetime import datetime
from typing import Dict
from typing import List
from typing import Optional
import uuid

from pymongo import MongoClient
from pymongo import ReturnDocument

from core.config import get_settings
from core.tourism_metadata import build_suggested_queries
from core.tourism_metadata import is_valid_city_name
from tool.logger import logger


class MongoManager:
    _instance: Optional["MongoManager"] = None

    def __init__(self):
        settings = get_settings()
        self.client = MongoClient(settings.mongo_url)
        self.db = self.client[settings.mongo_db_name]
        self.chat_messages = self.db["chat_messages"]
        self.import_tasks = self.db["import_tasks"]
        self.counters = self.db["counters"]

    @classmethod
    def get(cls) -> "MongoManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def ensure_indexes(self):
        await self.migrate_legacy_chat_messages()
        self.chat_messages.create_index(
            "session_id",
            unique=True,
            partialFilterExpression={"messages": {"$exists": True}},
        )
        self.chat_messages.create_index(
            [("session_id", 1), ("updated_at", -1)],
            partialFilterExpression={"messages": {"$exists": True}},
        )
        self.chat_messages.create_index(
            [("updated_at", -1), ("session_id", 1)],
            partialFilterExpression={"messages": {"$exists": True}},
        )
        self.import_tasks.create_index("task_id", unique=True)
        self.import_tasks.create_index([("city", 1), ("updated_at", -1)])
        self.import_tasks.create_index([("status", 1), ("updated_at", -1)])
        await self._ensure_session_counter_seeded()
        logger.info("MongoDB indexes ready")

    async def next_session_id(self) -> str:
        doc = self.counters.find_one_and_update(
            {"_id": "chat_session_id"},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return str(doc.get("seq", 1))

    async def save_message(
        self,
        session_id: str,
        role: str,
        text: str,
        intent: str = "",
        entities: dict = None,
        rewritten_query: str = "",
        citations: list = None,
        sources: list = None,
        images: list = None,
        feedback: str = "",
    ) -> str:
        await self._migrate_legacy_session(session_id)
        message_id = uuid.uuid4().hex
        now = datetime.now()
        message = {
            "message_id": message_id,
            "role": role,
            "content": text,
            "feedback": feedback,
            "sources": sources if sources is not None else self._sources_from_citations(citations or []),
            "images": images or [],
            "intent": intent,
            "entities": entities or {},
            "rewritten_query": rewritten_query,
            "timestamp": now,
        }
        self.chat_messages.update_one(
            {"session_id": session_id, "messages": {"$exists": True}},
            {
                "$setOnInsert": {"session_id": session_id, "title": "", "created_at": now},
                "$push": {"messages": message},
                "$set": {"updated_at": now},
            },
            upsert=True,
        )
        return message_id

    async def get_recent(self, session_id: str, limit: int = 10) -> List[Dict]:
        await self._migrate_legacy_session(session_id)
        session = self.chat_messages.find_one(
            {"session_id": session_id, "messages": {"$exists": True}},
            {"messages": 1, "_id": 0},
        )
        if session:
            messages = [self._normalize_message(m) for m in session.get("messages", [])]
            return messages[-limit:] if limit else messages
        cursor = self.chat_messages.find({"session_id": session_id, "messages": {"$exists": False}}).sort("timestamp", 1).limit(limit)
        return list(cursor)

    async def delete_session(self, session_id: str) -> int:
        result = self.chat_messages.delete_many({"session_id": session_id})
        return result.deleted_count

    async def rename_session(self, session_id: str, title: str) -> bool:
        result = self.chat_messages.update_one(
            {"session_id": session_id, "messages": {"$exists": True}},
            {"$set": {"title": title.strip(), "updated_at": datetime.now()}},
        )
        return result.matched_count > 0

    async def get_chat_sessions(self, limit: int = 100) -> List[Dict]:
        cursor = self.chat_messages.find(
            {"messages": {"$exists": True}, "session_id": {"$not": {"$regex": "^guest_"}}},
            {"session_id": 1, "title": 1, "messages": 1, "updated_at": 1, "created_at": 1, "_id": 0},
        ).sort("updated_at", -1)
        docs = list(cursor.limit(limit))
        sessions = []
        for doc in docs:
            messages = [self._normalize_message(item) for item in doc.get("messages", [])]
            title = (doc.get("title") or "").strip()
            if not title:
                first_user_message = next((item.get("content", "").strip() for item in messages if item.get("role") == "user" and item.get("content")), "")
                title = first_user_message[:18]
            sessions.append(
                {
                    "session_id": str(doc.get("session_id", "")),
                    "title": title,
                    "updated_at": doc.get("updated_at") or datetime.now(),
                    "created_at": doc.get("created_at") or doc.get("updated_at") or datetime.now(),
                    "message_count": len(messages),
                }
            )
        return sessions

    async def create_task(
        self,
        task_id: str,
        file_name: str,
        city: str = "",
        doc_type: str = "",
        product_id: str = "",
        suggested_queries: list | None = None,
    ) -> str:
        now = datetime.now()
        doc = {
            "task_id": task_id,
            "file_name": file_name,
            "city": city,
            "doc_type": doc_type,
            "product_id": product_id,
            "status": "processing",
            "progress": 0.05,
            "current_step": "文件入队",
            "stats": {},
            "error_log": [],
            "suggested_queries": suggested_queries or build_suggested_queries(city, [doc_type] if doc_type else []),
            "timeline": [
                {
                    "step": "文件入队",
                    "progress": 0.05,
                    "status": "processing",
                    "timestamp": now,
                }
            ],
            "created_at": now,
            "updated_at": now,
        }
        self.import_tasks.insert_one(doc)
        return task_id

    async def update_task(self, task_id: str, **kwargs):
        kwargs["updated_at"] = datetime.now()
        self.import_tasks.update_one({"task_id": task_id}, {"$set": kwargs})

    async def update_task_progress(
        self,
        task_id: str,
        step: str,
        progress: float,
        status: str = "processing",
        detail: str = "",
        stats: dict | None = None,
    ):
        now = datetime.now()
        payload = {
            "status": status,
            "progress": progress,
            "current_step": step,
            "updated_at": now,
        }
        if stats:
            payload["stats"] = stats
        if detail:
            payload["detail"] = detail
        self.import_tasks.update_one(
            {"task_id": task_id},
            {
                "$set": payload,
                "$push": {
                    "timeline": {
                        "step": step,
                        "progress": progress,
                        "status": status,
                        "detail": detail,
                        "timestamp": now,
                    }
                },
            },
        )

    async def get_task(self, task_id: str) -> Optional[Dict]:
        return self.import_tasks.find_one({"task_id": task_id})

    async def get_all_tasks(self, search: str = "", status: str = "") -> List[Dict]:
        query: Dict = {}
        if search:
            query["file_name"] = {"$regex": search, "$options": "i"}
        if status:
            query["status"] = status
        cursor = self.import_tasks.find(query).sort("updated_at", -1)
        return list(cursor.limit(100))

    async def delete_task(self, task_id: str) -> Optional[Dict]:
        doc = self.import_tasks.find_one({"task_id": task_id})
        if not doc:
            return None
        self.import_tasks.delete_one({"task_id": task_id})
        return doc

    async def has_completed_tasks(self) -> bool:
        count = self.import_tasks.count_documents({"status": "completed"})
        return count > 0

    async def get_city_recommendations(self, limit: int) -> List[Dict]:
        docs = list(self.import_tasks.find({"status": "completed", "city": {"$ne": ""}}).sort("updated_at", -1).limit(200))
        grouped: Dict[str, Dict] = {}
        doc_types_map: Dict[str, set] = defaultdict(set)
        for doc in docs:
            city = doc.get("city", "")
            if not is_valid_city_name(city):
                continue
            doc_types_map[city].add(doc.get("doc_type", ""))
            if city not in grouped:
                grouped[city] = {
                    "city": city,
                    "product_id": doc.get("product_id", ""),
                    "queries": list(doc.get("suggested_queries", [])),
                    "updated_at": doc.get("updated_at"),
                }
        results = []
        for city, item in grouped.items():
            item["doc_types"] = sorted(d for d in doc_types_map[city] if d)
            item["queries"] = build_suggested_queries(city, item["doc_types"])
            results.append(item)
        results.sort(key=lambda x: x.get("updated_at") or datetime.min, reverse=True)
        return results[:limit]

    async def _migrate_legacy_session(self, session_id: str):
        existing = self.chat_messages.find_one({"session_id": session_id, "messages": {"$exists": True}})
        cursor = self.chat_messages.find({"session_id": session_id, "messages": {"$exists": False}}).sort("timestamp", 1)
        legacy_docs = list(cursor.limit(1000))
        normalized_existing = [self._normalize_message(m) for m in existing.get("messages", [])] if existing else []
        legacy_messages = [self._message_from_legacy_doc(doc) for doc in legacy_docs]
        messages = normalized_existing + legacy_messages

        if existing and messages != existing.get("messages", []):
            self.chat_messages.update_one(
                {"_id": existing["_id"]},
                {
                    "$set": {
                        "messages": messages,
                        "updated_at": messages[-1]["timestamp"] if messages else datetime.now(),
                        "migrated_to_session_document": True,
                    }
                },
            )
        elif not existing and messages:
            self.chat_messages.insert_one(
                {
                    "session_id": session_id,
                    "title": "",
                    "messages": messages,
                    "created_at": messages[0]["timestamp"],
                    "updated_at": messages[-1]["timestamp"],
                    "migrated_to_session_document": True,
                }
            )

        if legacy_docs:
            self.chat_messages.delete_many({"_id": {"$in": [doc["_id"] for doc in legacy_docs if doc.get("_id")]}})

    async def migrate_legacy_chat_messages(self):
        session_ids = self.chat_messages.distinct("session_id")
        for session_id in session_ids:
            if session_id:
                await self._migrate_legacy_session(session_id)

    async def _ensure_session_counter_seeded(self):
        existing = self.counters.find_one({"_id": "chat_session_id"})
        if existing and isinstance(existing.get("seq"), int):
            return

        max_numeric_session_id = 0
        for session_id in self.chat_messages.distinct("session_id"):
            if isinstance(session_id, int):
                max_numeric_session_id = max(max_numeric_session_id, session_id)
                continue
            if isinstance(session_id, str) and session_id.isdigit():
                max_numeric_session_id = max(max_numeric_session_id, int(session_id))

        self.counters.update_one(
            {"_id": "chat_session_id"},
            {"$set": {"seq": max_numeric_session_id}},
            upsert=True,
        )

    def _message_from_legacy_doc(self, doc: Dict) -> Dict:
        return self._normalize_message(
            {
                "message_id": str(doc.get("_id") or uuid.uuid4().hex),
                "role": doc.get("role", ""),
                "content": doc.get("content") or doc.get("text", ""),
                "feedback": doc.get("feedback", ""),
                "sources": doc.get("sources") or self._sources_from_citations(doc.get("citations", [])),
                "images": doc.get("images", []),
                "intent": doc.get("intent", ""),
                "entities": doc.get("entities", {}),
                "rewritten_query": doc.get("rewritten_query", ""),
                "timestamp": doc.get("timestamp") or datetime.now(),
            }
        )

    def _normalize_message(self, message: Dict) -> Dict:
        normalized = {
            "message_id": message.get("message_id") or str(message.get("_id") or uuid.uuid4().hex),
            "role": message.get("role", ""),
            "content": message.get("content") or message.get("text", ""),
            "feedback": message.get("feedback", ""),
            "sources": message.get("sources") or self._sources_from_citations(message.get("citations", [])),
            "images": message.get("images", []),
            "timestamp": message.get("timestamp") or datetime.now(),
        }
        if message.get("intent"):
            normalized["intent"] = message.get("intent", "")
        if message.get("entities"):
            normalized["entities"] = message.get("entities", {})
        if message.get("rewritten_query"):
            normalized["rewritten_query"] = message.get("rewritten_query", "")
        return normalized

    @staticmethod
    def _sources_from_citations(citations: list) -> list:
        sources = []
        for item in citations or []:
            if isinstance(item, dict):
                sources.append(
                    {
                        "file_name": item.get("file_name") or item.get("title") or item.get("source_file") or "",
                        "page": item.get("page"),
                        "url": item.get("url", ""),
                        "doc_type": item.get("doc_type", ""),
                        "city": item.get("city", ""),
                    }
                )
            elif item:
                sources.append({"file_name": str(item), "page": None, "url": ""})
        return sources

    @classmethod
    def reset(cls):
        if cls._instance and cls._instance.client:
            cls._instance.client.close()
        cls._instance = None
