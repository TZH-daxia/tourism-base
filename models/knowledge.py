"""Request and response models."""

from datetime import datetime
from typing import List
from typing import Optional

from pydantic import BaseModel
from pydantic import Field


class KnowledgeUploadResponse(BaseModel):
    task_id: str
    file_name: str
    status: str = "processing"
    message: str = "文件已上传"


class TaskStatusResponse(BaseModel):
    task_id: str
    file_name: str
    status: str
    progress: float = 0.0
    current_step: str = ""
    error: str = ""
    city: str = ""
    doc_type: str = ""
    product_id: str = ""
    suggested_queries: List[str] = Field(default_factory=list)
    timeline: List[dict] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)

    model_config = {"extra": "ignore"}


class RecommendationCard(BaseModel):
    city: str
    product_id: str = ""
    doc_types: List[str] = Field(default_factory=list)
    queries: List[str] = Field(default_factory=list)


class RuntimeModelSettings(BaseModel):
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    vision_required: bool = True
    warning: str = "请优先使用支持视觉的模型，否则文档里的图片信息可能无法被正确理解。"


class RuntimeModelSettingsUpdate(BaseModel):
    api_key: str
    base_url: str
    model: str


class RAGChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    rag_enabled: bool = True


class RAGChatResponse(BaseModel):
    session_id: str
    message: str
    sources: List[dict] = Field(default_factory=list)
    citations: List[dict] = Field(default_factory=list)
    images: List[dict] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)
