"""Upload images to MinIO and replace Markdown image references."""

from __future__ import annotations

import mimetypes
import os
from typing import Any
from typing import Dict

from core.minio_manager import build_object_name
from core.minio_manager import build_proxy_url
from core.minio_manager import ensure_bucket
from core.minio_manager import get_client
from core.tourism_metadata import extract_image_markdown
from graphs.states import IngestState
from nodes.ingest.progress import report_progress
from tool.logger import logger


def image_processor(state: IngestState) -> Dict[str, Any]:
    logger.info(f"Process images for {state.file_name}")
    report_progress(state.task_id, "图片处理中", 0.32)
    try:
        if not state.markdown_content:
            raise ValueError("markdown_content is empty")
        if not state.images:
            return {"status": "images_processed"}

        ensure_bucket()
        client = get_client()
        md = state.markdown_content
        for image in state.images:
            try:
                if not image.local_path or not os.path.exists(image.local_path):
                    continue
                object_name = build_object_name(state.city, state.doc_type, state.task_id, image.file_name)
                content_type = mimetypes.guess_type(image.file_name)[0] or "application/octet-stream"
                client.fput_object(
                    bucket_name=get_bucket_name(),
                    object_name=object_name,
                    file_path=image.local_path,
                    content_type=content_type,
                )
                image.object_name = object_name
                image.minio_url = build_proxy_url(object_name)
                image.summary = image.summary or "旅游图片"
                md = md.replace(f"![{image.summary}]({image.original_ref})", f"![{image.summary}]({image.minio_url})")
                if f"]({image.original_ref})" in md:
                    md = md.replace(f"]({image.original_ref})", f"]({image.minio_url})")
            except Exception as exc:
                logger.warning(f"Skip image {image.file_name}: {exc}")

        report_progress(state.task_id, "图片处理完成", 0.4, detail=f"上传图片 {len(state.images)} 张")
        logger.info(f"Image processing complete: {len(extract_image_markdown(md))} linked images")
        return {"markdown_content": md, "images": state.images, "status": "images_processed"}
    except Exception as exc:
        logger.error(f"Image processing failed: {exc}")
        return {"status": "error", "errors": state.errors + [f"[image_processor] {exc}"]}


def get_bucket_name() -> str:
    from core.config import get_settings

    return get_settings().minio_bucket_name
