"""全局配置单例 — Pydantic BaseSettings，从 .env 加载"""
from pydantic_settings import BaseSettings
from functools import lru_cache

_runtime_llm_overrides: dict[str, str] = {}


class Settings(BaseSettings):
    # ========== LLM ==========
    openai_api_key: str = ""
    openai_api_base: str = "https://api.siliconflow.cn/v1"
    llm_default_model: str = "Pro/moonshotai/Kimi-K2.5"
    vl_model: str = "Pro/moonshotai/Kimi-K2.5"
    item_model: str = "Pro/moonshotai/Kimi-K2.5"
    llm_default_temperature: float = 0.1

    # ========== MongoDB ==========
    mongo_url: str = "mongodb://192.168.10.129:27017"
    mongo_db_name: str = "ly001"

    # ========== Milvus ==========
    milvus_url: str = "http://192.168.10.129:19530"
    chunks_collection: str = "ly_chunks"
    entities_collection: str = "ly_tourism_entities"
    milvus_metric_type: str = "COSINE"
    milvus_min_cosine_score: float = 0.75

    # ========== BGE-M3 ==========
    bge_model_path: str = r"D:\AI_models\models\bge-m3"
    bge_device: str = "cuda:0"
    bge_fp16: bool = True

    # ========== MinIO ==========
    minio_endpoint: str = "192.168.10.129:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket_name: str = "knowledge-base"
    minio_secure: bool = False

    # ========== MinerU ==========
    mineru_api_token: str = ""
    mineru_base_url: str = "https://mineru.net/api/v4"

    # ========== Reranker (硅基流动 BAAI/bge-reranker-v2-m3) ==========
    text_rerank_api_key: str = ""
    text_rerank_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_mode: str = "local"
    reranker_model_path: str = r"D:\AI_models\models\bge-reranker-large"
    reranker_device: str = "cuda:0"
    reranker_use_fp16: bool = True

    # ========== MCP ==========
    bailian_mcp_api_key: str = ""
    mcp_dashscope_base_url: str = "https://dashscope.aliyuncs.com/api/v1/mcps/WebSearch/mcp"

    # ========== 检索配置 ==========
    rag_top_k: int = 5
    rag_item_top_k: int = 3
    item_confirm_high_score: float = 0.85
    item_confirm_mid_score: float = 0.65
    city_recommendation_limit: int = 3
    enable_web_search: bool = False

    # ========== Chunk ==========
    chunk_size: int = 1024
    chunk_overlap: int = 128

    # ========== 环境 ==========
    app_env: str = "development"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()


def get_runtime_llm_settings() -> dict[str, str]:
    settings = get_settings()
    return {
        "api_key": _runtime_llm_overrides.get("api_key", settings.openai_api_key),
        "base_url": _runtime_llm_overrides.get("base_url", settings.openai_api_base),
        "model": _runtime_llm_overrides.get("model", settings.llm_default_model),
    }


def has_runtime_llm_overrides() -> bool:
    return any(_runtime_llm_overrides.get(key, "").strip() for key in ("api_key", "base_url", "model"))


def set_runtime_llm_settings(api_key: str, base_url: str, model: str):
    _runtime_llm_overrides["api_key"] = api_key.strip()
    _runtime_llm_overrides["base_url"] = base_url.strip().rstrip("/")
    _runtime_llm_overrides["model"] = model.strip()


def clear_runtime_llm_settings():
    _runtime_llm_overrides.clear()
