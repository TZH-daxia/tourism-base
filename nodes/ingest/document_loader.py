"""Load documents from PDF via MinerU or from Markdown files."""

from __future__ import annotations

import io
import os
import re
import tempfile
import time
import zipfile
from typing import Any
from typing import Dict
from typing import Iterable

import httpx

from core.config import get_settings
from core.tourism_metadata import build_product_id
from core.tourism_metadata import build_suggested_queries
from core.tourism_metadata import infer_city
from core.tourism_metadata import infer_doc_type
from graphs.states import ImageRef
from graphs.states import IngestState
from nodes.ingest.progress import report_progress
from tool.logger import logger


def document_loader(state: IngestState) -> Dict[str, Any]:
    logger.info(f"Load document: {state.file_name}")
    report_progress(state.task_id, "文档解析中", 0.18)
    try:
        if not state.file_path or not os.path.exists(state.file_path):
            raise FileNotFoundError(f"File not found: {state.file_path}")

        settings = get_settings()
        batch_id, file_urls = _request_upload(state.file_path, settings)
        task_data = _poll_result(batch_id, file_urls, settings)
        md_content, images = _parse_zip(task_data)
        city, doc_type, product_id, suggested_queries = _build_metadata(state.file_name, md_content)
        logger.info(f"Loaded markdown length={len(md_content)}, images={len(images)}, city={city}, type={doc_type}")
        return {
            "markdown_content": md_content,
            "images": images,
            "city": city,
            "doc_type": doc_type,
            "product_id": product_id,
            "product_name": city,
            "suggested_queries": suggested_queries,
            "status": "loaded",
        }
    except Exception as exc:
        logger.error(f"Document load failed: {exc}")
        return {"status": "error", "errors": state.errors + [f"[document_loader] {exc}"]}


def enrich_markdown_state(file_name: str, file_path: str, content: str, task_id: str) -> Dict[str, Any]:
    images = _extract_local_markdown_images(file_path, content)
    city, doc_type, product_id, suggested_queries = _build_metadata(file_name, content)
    report_progress(task_id, "文档已加载", 0.12)
    return {
        "markdown_content": content,
        "images": images,
        "city": city,
        "doc_type": doc_type,
        "product_id": product_id,
        "product_name": city,
        "suggested_queries": suggested_queries,
        "status": "loaded",
    }


def _build_metadata(file_name: str, content: str) -> tuple[str, str, str, list[str]]:
    city = infer_city(file_name, content)
    doc_type = infer_doc_type(file_name, content)
    product_id = build_product_id(city)
    suggested_queries = build_suggested_queries(city, [doc_type])
    return city, doc_type, product_id, suggested_queries


def _extract_local_markdown_images(file_path: str, content: str) -> list[ImageRef]:
    base_dir = os.path.dirname(file_path)
    images: list[ImageRef] = []
    for alt, ref in re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", content or ""):
        if ref.startswith(("http://", "https://", "minio://", "/api/knowledge/assets/")):
            continue
        local_path = os.path.normpath(os.path.join(base_dir, ref))
        if os.path.exists(local_path):
            images.append(
                ImageRef(
                    original_ref=ref,
                    file_name=os.path.basename(local_path),
                    local_path=local_path,
                    summary=alt or "旅游图片",
                )
            )
    return images


def _request_upload(file_path: str, settings) -> tuple[str, Iterable[str]]:
    with httpx.Client(timeout=60) as client:
        file_size = os.path.getsize(file_path)
        with open(file_path, "rb") as handle:
            resp = client.post(
                f"{settings.mineru_base_url}/file-upload/get-batch-info",
                data={"files": f'{{"file_name":"{os.path.basename(file_path)}","file_size":{file_size}}}'},
                headers={"Authorization": f"Bearer {settings.mineru_api_token}"},
            )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise ValueError(f"MinerU upload init failed: {data}")
        batch_id = data["data"]["batch_id"]
        file_urls = data["data"]["file_urls"]
        with open(file_path, "rb") as handle:
            payload = handle.read()
            for url in file_urls:
                client.put(url, content=payload, headers={"Content-Type": "application/octet-stream"})
        return batch_id, file_urls


def _poll_result(batch_id: str, file_urls: Iterable[str], settings, timeout: int = 300) -> dict:
    with httpx.Client(timeout=60) as client:
        start = time.time()
        while time.time() - start < timeout:
            resp = client.get(
                f"{settings.mineru_base_url}/file-upload/get-batch-info",
                params={"batch_id": batch_id},
                headers={"Authorization": f"Bearer {settings.mineru_api_token}"},
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise ValueError(f"MinerU poll failed: {data}")
            tasks = data.get("data", {}).get("tasks", [])
            if tasks and all(task.get("state") == "done" for task in tasks):
                return data["data"]
            if tasks and any(task.get("state") == "failed" for task in tasks):
                raise RuntimeError(f"MinerU task failed: {tasks}")
            time.sleep(6)
    raise TimeoutError(f"MinerU timeout: {batch_id}")


def _parse_zip(task_data: dict) -> tuple[str, list[ImageRef]]:
    tasks = task_data.get("tasks", [])
    if not tasks:
        raise ValueError("MinerU returned no tasks")
    zip_url = tasks[0].get("full_zip_url")
    if not zip_url:
        raise ValueError("MinerU returned no downloadable zip")
    settings = get_settings()
    with httpx.Client(timeout=120) as client:
        resp = client.get(zip_url, headers={"Authorization": f"Bearer {settings.mineru_api_token}"})
        resp.raise_for_status()

    md_content = ""
    images: list[ImageRef] = []
    with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
        tmp_dir = tempfile.mkdtemp()
        archive.extractall(tmp_dir)
        for root, _, files in os.walk(tmp_dir):
            for file_name in files:
                file_path = os.path.join(root, file_name)
                rel = os.path.relpath(file_path, tmp_dir).replace("\\", "/")
                if file_name.endswith(".md"):
                    with open(file_path, "r", encoding="utf-8") as handle:
                        md_content = handle.read()
                elif file_name.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                    images.append(ImageRef(original_ref=rel, file_name=file_name, local_path=file_path))
    return md_content or "PDF 解析结果为空", images
