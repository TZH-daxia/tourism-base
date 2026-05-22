"""Embedding factory with graceful fallback."""

from __future__ import annotations

from typing import Any

from core.config import get_settings
from tool.logger import logger

_ef: Any = None


class _FallbackEmbedding:
    def encode_documents(self, texts: list[str]):
        dense = [[0.0] * 1024 for _ in texts]

        class Sparse:
            indices = []
            indptr = [0] * (len(texts) + 1)
            data = []

        return {"dense": dense, "sparse": Sparse()}


def get_embedding():
    global _ef
    if _ef is not None:
        return _ef
    settings = get_settings()
    try:
        from pymilvus.model.hybrid import BGEM3EmbeddingFunction

        _ef = BGEM3EmbeddingFunction(
            model_name=settings.bge_model_path,
            device=settings.bge_device,
            use_fp16=settings.bge_fp16,
        )
    except Exception as exc:
        logger.warning(f"Embedding model unavailable, using fallback vectors: {exc}")
        _ef = _FallbackEmbedding()
    return _ef


def encode(texts: list[str]) -> tuple[list[list[float]], list[dict]]:
    ef = get_embedding()
    out = ef.encode_documents(texts)
    dense = []
    for item in out["dense"]:
        dense.append(item.tolist() if hasattr(item, "tolist") else list(item))
    sparse = []
    sparse_matrix = out["sparse"]
    for idx in range(len(texts)):
        if not hasattr(sparse_matrix, "indices") or not hasattr(sparse_matrix, "indptr") or not hasattr(sparse_matrix, "data"):
            sparse.append({})
            continue
        indices = sparse_matrix.indices[sparse_matrix.indptr[idx]:sparse_matrix.indptr[idx + 1]].tolist()
        values = sparse_matrix.data[sparse_matrix.indptr[idx]:sparse_matrix.indptr[idx + 1]].tolist()
        sparse.append({key: value for key, value in zip(indices, values)})
    return dense, sparse


def encode_single(text: str) -> tuple[list[float], dict]:
    dense, sparse = encode([text])
    return dense[0], sparse[0]


def reset():
    global _ef
    _ef = None
