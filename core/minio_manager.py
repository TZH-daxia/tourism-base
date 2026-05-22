"""MinIO helpers for the tourism knowledge base."""

from io import BytesIO
from urllib.parse import quote

from core.config import get_settings
from tool.logger import logger

_client = None


def get_client():
    global _client
    if _client is not None:
        return _client
    from minio import Minio

    settings = get_settings()
    _client = Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    logger.info(f"MinIO connected: {settings.minio_endpoint}")
    return _client


def ensure_bucket():
    settings = get_settings()
    client = get_client()
    if not client.bucket_exists(settings.minio_bucket_name):
        client.make_bucket(settings.minio_bucket_name)
        logger.info(f"Created bucket: {settings.minio_bucket_name}")
    else:
        logger.info(f"Bucket exists: {settings.minio_bucket_name}")


def build_object_name(city: str, doc_type: str, task_id: str, file_name: str) -> str:
    safe_city = (city or "unknown").replace("/", "_")
    safe_type = (doc_type or "misc").replace("/", "_")
    safe_name = file_name.replace("\\", "/").split("/")[-1]
    return f"tourism/{safe_city}/{safe_type}/{task_id}/{safe_name}"


def build_proxy_url(object_name: str) -> str:
    settings = get_settings()
    return f"/api/knowledge/assets/{quote(settings.minio_bucket_name)}/{quote(object_name, safe='/')}"


def get_object_bytes(bucket_name: str, object_name: str) -> tuple[bytes, str]:
    resp = get_client().get_object(bucket_name, object_name)
    try:
        data = resp.read()
        content_type = resp.headers.get("Content-Type", "application/octet-stream")
        return data, content_type
    finally:
        resp.close()
        resp.release_conn()


def put_bytes(object_name: str, data: bytes, content_type: str = "application/octet-stream"):
    settings = get_settings()
    get_client().put_object(
        settings.minio_bucket_name,
        object_name,
        BytesIO(data),
        length=len(data),
        content_type=content_type,
    )


def reset():
    global _client
    _client = None
