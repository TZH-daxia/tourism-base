"""Batch upload and verify the tourism markdown dataset end to end."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.milvus_manager import MilvusManager
from core.mongo_manager import MongoManager
from core.tourism_metadata import is_valid_city_name
from main import app

DATASET_ROOT = Path(
    r"D:\AI_models\09_尚硅谷大模型项目之掌柜智库\4.视频\尚硅谷大模型项目实战之掌柜智库实战\资料\旅游\数据"
)
REPORT_PATH = Path("test_output/tourism_full_flow_report.json")
MAX_WAIT_SECONDS = 240


def collect_dataset_files() -> list[Path]:
    files = sorted(DATASET_ROOT.rglob("*.md"))
    if not files:
        raise RuntimeError(f"No markdown files found under {DATASET_ROOT}")
    return files


def cleanup_existing_dataset_records(dataset_files: list[Path]) -> dict:
    mongo = MongoManager.get()
    file_names = {path.name for path in dataset_files}
    import_tasks = mongo.import_tasks

    cleanup_docs = list(
        import_tasks.find(
            {
                "$or": [
                    {"file_name": {"$in": list(file_names)}},
                    {"file_name": {"$regex": r"^sanya_.*\.md$", "$options": "i"}},
                    {"file_name": "??????.md"},
                    {"status": "processing"},
                ]
            }
        )
    )
    invalid_city_docs = [doc for doc in import_tasks.find({"status": "completed"}) if not is_valid_city_name(doc.get("city", ""))]
    merged = {doc["task_id"]: doc for doc in cleanup_docs + invalid_city_docs if doc.get("task_id")}

    milvus_deleted = 0
    for doc in merged.values():
        file_name = doc.get("file_name")
        if file_name:
            try:
                MilvusManager.delete_by_source_file(file_name)
                milvus_deleted += 1
            except Exception:
                pass

    deleted = import_tasks.delete_many({"task_id": {"$in": list(merged)}}).deleted_count if merged else 0
    return {"mongo_deleted": deleted, "milvus_cleanup_attempts": milvus_deleted}


def upload_all_files(client: TestClient, files: list[Path]) -> list[dict]:
    uploads = []
    for path in files:
        with path.open("rb") as handle:
            response = client.post(
                "/api/knowledge/upload",
                files={"file": (path.name, handle, "text/markdown")},
            )
        if response.status_code != 200:
            raise RuntimeError(f"Upload failed for {path.name}: {response.status_code} {response.text}")
        uploads.append(response.json())
    return uploads


def wait_for_tasks(client: TestClient, task_ids: list[str]) -> list[dict]:
    deadline = time.time() + MAX_WAIT_SECONDS
    task_map: dict[str, dict] = {}
    while time.time() < deadline:
        pending = []
        for task_id in task_ids:
            response = client.get(f"/api/knowledge/status/{task_id}")
            if response.status_code != 200:
                raise RuntimeError(f"Status check failed for {task_id}: {response.status_code} {response.text}")
            payload = response.json()
            task_map[task_id] = payload
            if payload["status"] not in {"completed", "failed"}:
                pending.append(task_id)
        if not pending:
            return [task_map[task_id] for task_id in task_ids]
        time.sleep(1.0)
    raise TimeoutError(f"Timed out waiting for tasks: {task_ids}")


def verify_query(client: TestClient, query: str) -> dict:
    response = client.post(
        "/api/knowledge/chat",
        json={"message": query, "session_id": f"manual-{int(time.time())}", "rag_enabled": True},
    )
    if response.status_code != 200:
        raise RuntimeError(f"Query failed for {query}: {response.status_code} {response.text}")
    payload = response.json()
    payload["source_doc_types"] = sorted({item.get("doc_type", "") for item in payload.get("sources", []) if item.get("doc_type")})
    return payload


def main():
    client = TestClient(app)

    dataset_files = collect_dataset_files()
    cleanup_summary = cleanup_existing_dataset_records(dataset_files)
    uploads = upload_all_files(client, dataset_files)
    task_ids = [item["task_id"] for item in uploads]
    statuses = wait_for_tasks(client, task_ids)
    completed = [item for item in statuses if item["status"] == "completed"]
    failed = [item for item in statuses if item["status"] == "failed"]
    recommendations = client.get("/api/knowledge/recommendations").json()

    queries = {
        "overview_sanya": "三亚有什么好玩的？",
        "food_hangzhou": "杭州住哪里方便，吃什么值得推荐？",
        "route_yunnan": "云南有哪些值得参考的旅游线路？",
    }
    query_results = {name: verify_query(client, text) for name, text in queries.items()}

    report = {
        "dataset_root": str(DATASET_ROOT),
        "dataset_file_count": len(dataset_files),
        "cleanup_summary": cleanup_summary,
        "completed_count": len(completed),
        "failed_count": len(failed),
        "failed_tasks": failed,
        "recommendations": recommendations,
        "query_results": {
            key: {
                "message_preview": value.get("message", "")[:400],
                "source_count": len(value.get("sources", [])),
                "source_doc_types": value.get("source_doc_types", []),
                "image_count": len(value.get("images", [])),
            }
            for key, value in query_results.items()
        },
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
