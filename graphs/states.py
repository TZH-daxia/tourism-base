"""LangGraph state models for ingestion and query flows."""

from typing import Annotated
from typing import Dict
from typing import List

import operator
from pydantic import BaseModel
from pydantic import Field


class ImageRef(BaseModel):
    original_ref: str = ""
    minio_url: str = ""
    summary: str = ""
    file_name: str = ""
    local_path: str = ""
    object_name: str = ""
    category: str = ""
    city: str = ""


class TourismChunk(BaseModel):
    chunk_id: str = ""
    product_id: str = ""
    product_name: str = ""
    title: str = ""
    content: str = ""
    content_type: str = ""
    city: str = ""
    doc_type: str = ""
    source_file: str = ""
    source_url: str = ""
    chunk_index: int = 0
    image_urls: List[str] = Field(default_factory=list)
    image_alts: List[str] = Field(default_factory=list)
    dense_vector: List[float] = Field(default_factory=list)
    sparse_vector: Dict = Field(default_factory=dict)


class IngestState(BaseModel):
    task_id: str = ""
    file_path: str = ""
    file_name: str = ""
    file_dir: str = ""
    city: str = ""
    product_id: str = ""
    product_name: str = ""
    doc_type: str = ""
    suggested_queries: List[str] = Field(default_factory=list)
    markdown_content: str = ""
    images: List[ImageRef] = Field(default_factory=list)
    chunks: List[TourismChunk] = Field(default_factory=list)
    entities: List[Dict] = Field(default_factory=list)
    dense_vectors: List[List[float]] = Field(default_factory=list)
    sparse_vectors: List[Dict] = Field(default_factory=list)
    entity_dense: List[List[float]] = Field(default_factory=list)
    entity_sparse: List[Dict] = Field(default_factory=list)
    status: str = "initialized"
    errors: List[str] = Field(default_factory=list)


class RAGChatState(BaseModel):
    query: str = ""
    session_id: str = ""
    guest_mode: bool = False
    history: List[Dict] = Field(default_factory=list)
    entities: Dict = Field(default_factory=dict)
    city: str = ""
    product_ids: List[str] = Field(default_factory=list)
    product_names: List[str] = Field(default_factory=list)
    requested_doc_types: List[str] = Field(default_factory=list)
    intent: str = ""
    rewritten_query: str = ""
    confirm_answer: str = ""
    need_images: bool = False
    query_dense: List[float] = Field(default_factory=list)
    query_sparse: Dict = Field(default_factory=dict)
    embedding_chunks: List[Dict] = Field(default_factory=list)
    hyde_chunks: List[Dict] = Field(default_factory=list)
    web_search_docs: List[Dict] = Field(default_factory=list)
    rrf_chunks: List[Dict] = Field(default_factory=list)
    reranked_docs: List[Dict] = Field(default_factory=list)
    answer: str = ""
    context: str = ""
    sources: List[Dict] = Field(default_factory=list)
    citations: List[Dict] = Field(default_factory=list)
    answer_images: List[Dict] = Field(default_factory=list)
    recommended_queries: List[str] = Field(default_factory=list)
    errors: Annotated[List[str], operator.add] = Field(default_factory=list)
