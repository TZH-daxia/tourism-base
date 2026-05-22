"""Split tourism markdown into retrieval-ready chunks."""

from __future__ import annotations

import re
from typing import Any
from typing import Dict
from typing import List

from core.config import get_settings
from core.tourism_metadata import build_chunk_id
from core.tourism_metadata import extract_image_markdown
from graphs.states import IngestState
from graphs.states import TourismChunk
from nodes.ingest.progress import report_progress
from tool.logger import logger


def tourism_splitter(state: IngestState) -> Dict[str, Any]:
    logger.info(f"Split markdown for {state.file_name}")
    report_progress(state.task_id, "文档切分中", 0.45)
    try:
        if not state.markdown_content:
            raise ValueError("markdown_content is empty")
        settings = get_settings()
        sections = _split_by_headings(state.markdown_content)
        chunks: list[TourismChunk] = []
        chunk_index = 0
        for title, content in sections:
            if not content.strip():
                continue
            for part in _split_long(content, settings.chunk_size, settings.chunk_overlap):
                part = part.strip()
                if not part:
                    continue
                images = extract_image_markdown(part)
                chunks.append(
                    TourismChunk(
                        chunk_id=build_chunk_id(state.product_id, state.file_name, chunk_index),
                        product_id=state.product_id,
                        product_name=state.product_name or state.city,
                        title=title or f"{state.city}{state.doc_type}",
                        content=part if not title else f"## {title}\n{part}",
                        content_type=state.doc_type,
                        city=state.city,
                        doc_type=state.doc_type,
                        source_file=state.file_name,
                        source_url="",
                        chunk_index=chunk_index,
                        image_urls=[item["url"] for item in images],
                        image_alts=[item["alt"] for item in images],
                    )
                )
                chunk_index += 1
        report_progress(state.task_id, "文档切分完成", 0.62, detail=f"生成 {len(chunks)} 个 chunks")
        logger.info(f"Split complete: {len(chunks)} chunks")
        return {"chunks": chunks, "status": "split"}
    except Exception as exc:
        logger.error(f"Split failed: {exc}")
        return {"status": "error", "errors": state.errors + [f"[tourism_splitter] {exc}"]}


def _split_by_headings(markdown: str) -> List[tuple[str, str]]:
    lines = markdown.replace("\r\n", "\n").split("\n")
    sections: list[tuple[str, str]] = []
    current_title = ""
    current_lines: list[str] = []
    for line in lines:
        match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if match:
            if current_lines:
                sections.append((current_title, "\n".join(current_lines).strip()))
            current_title = match.group(2).strip()
            current_lines = []
            continue
        current_lines.append(line)
    if current_lines:
        sections.append((current_title, "\n".join(current_lines).strip()))
    return sections or [("", markdown)]


def _split_long(text: str, size: int, overlap: int) -> List[str]:
    if len(text) <= size:
        return [text]
    separators = ["\n\n", "\n", "。", "！", "？", "；", "，", " "]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        window = text[start:end]
        if end < len(text):
            split_at = -1
            for sep in separators:
                idx = window.rfind(sep)
                if idx > size // 2:
                    split_at = idx + len(sep)
                    break
            if split_at > 0:
                end = start + split_at
                window = text[start:end]
        chunks.append(window)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks
