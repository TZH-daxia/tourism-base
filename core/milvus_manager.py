"""Milvus manager for city-first tourism retrieval."""

from typing import Dict
from typing import List
from typing import Set

from core.config import get_settings
from tool.logger import logger

DENSE_DIM = 1024


class MilvusManager:
    _client = None

    @classmethod
    def get_client(cls):
        if cls._client is not None:
            return cls._client
        from pymilvus import MilvusClient

        settings = get_settings()
        cls._client = MilvusClient(uri=settings.milvus_url)
        logger.info(f"Milvus connected: {settings.milvus_url}")
        return cls._client

    @classmethod
    def ensure_collections(cls):
        settings = get_settings()
        client = cls.get_client()
        cls._ensure_chunks_collection(client, settings.chunks_collection)
        cls._ensure_products_collection(client, settings.entities_collection)

    @classmethod
    def _ensure_chunks_collection(cls, client, name: str):
        required_fields = {
            "id", "task_id", "product_id", "product_name", "city", "doc_type",
            "chunk_id", "title", "content", "source_file", "source_url",
            "chunk_index", "image_urls", "image_alts", "dense_vector", "sparse_vector",
        }
        cls._ensure_collection(name, required_fields, cls._create_chunks_collection)

    @classmethod
    def _ensure_products_collection(cls, client, name: str):
        required_fields = {
            "id", "task_id", "product_id", "product_name", "city", "doc_type",
            "aliases", "available_doc_types", "suggested_queries", "source_file",
            "dense_vector", "sparse_vector",
        }
        cls._ensure_collection(name, required_fields, cls._create_products_collection)

    @classmethod
    def _ensure_collection(cls, name: str, required_fields: Set[str], create_fn):
        client = cls.get_client()
        if client.has_collection(name):
            existing = cls._collection_fields(client, name)
            missing = sorted(required_fields - existing)
            if not missing:
                logger.info(f"Milvus collection ready: {name}")
                return
            logger.warning(f"Collection {name} missing fields {missing}, recreating to sync schema")
            client.drop_collection(name)
        create_fn(client, name)

    @staticmethod
    def _create_chunks_collection(client, name: str):
        from pymilvus import CollectionSchema
        from pymilvus import DataType
        from pymilvus import FieldSchema

        schema = CollectionSchema(
            fields=[
                FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
                FieldSchema(name="task_id", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="product_id", dtype=DataType.VARCHAR, max_length=128),
                FieldSchema(name="product_name", dtype=DataType.VARCHAR, max_length=128),
                FieldSchema(name="city", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="doc_type", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=160),
                FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=256),
                FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=12000),
                FieldSchema(name="source_file", dtype=DataType.VARCHAR, max_length=256),
                FieldSchema(name="source_url", dtype=DataType.VARCHAR, max_length=1024),
                FieldSchema(name="chunk_index", dtype=DataType.INT64),
                FieldSchema(name="image_urls", dtype=DataType.VARCHAR, max_length=4096),
                FieldSchema(name="image_alts", dtype=DataType.VARCHAR, max_length=4096),
                FieldSchema(name="dense_vector", dtype=DataType.FLOAT_VECTOR, dim=DENSE_DIM),
                FieldSchema(name="sparse_vector", dtype=DataType.SPARSE_FLOAT_VECTOR),
            ],
            description="Tourism knowledge chunks",
        )
        idx = client.prepare_index_params()
        idx.add_index("dense_vector", index_type="IVF_FLAT", metric_type="COSINE", params={"nlist": 128})
        idx.add_index("sparse_vector", index_type="SPARSE_INVERTED_INDEX", metric_type="IP")
        client.create_collection(collection_name=name, schema=schema, index_params=idx)
        logger.info(f"Created collection: {name}")

    @staticmethod
    def _create_products_collection(client, name: str):
        from pymilvus import CollectionSchema
        from pymilvus import DataType
        from pymilvus import FieldSchema

        schema = CollectionSchema(
            fields=[
                FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
                FieldSchema(name="task_id", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="product_id", dtype=DataType.VARCHAR, max_length=128),
                FieldSchema(name="product_name", dtype=DataType.VARCHAR, max_length=128),
                FieldSchema(name="city", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="doc_type", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="aliases", dtype=DataType.VARCHAR, max_length=1024),
                FieldSchema(name="available_doc_types", dtype=DataType.VARCHAR, max_length=1024),
                FieldSchema(name="suggested_queries", dtype=DataType.VARCHAR, max_length=2048),
                FieldSchema(name="source_file", dtype=DataType.VARCHAR, max_length=256),
                FieldSchema(name="dense_vector", dtype=DataType.FLOAT_VECTOR, dim=DENSE_DIM),
                FieldSchema(name="sparse_vector", dtype=DataType.SPARSE_FLOAT_VECTOR),
            ],
            description="City/product index for tourism retrieval",
        )
        idx = client.prepare_index_params()
        idx.add_index("dense_vector", index_type="IVF_FLAT", metric_type="COSINE", params={"nlist": 128})
        idx.add_index("sparse_vector", index_type="SPARSE_INVERTED_INDEX", metric_type="IP")
        client.create_collection(collection_name=name, schema=schema, index_params=idx)
        logger.info(f"Created collection: {name}")

    @classmethod
    def insert_chunks(cls, data: List[Dict]):
        settings = get_settings()
        client = cls.get_client()
        data = cls._filter_supported_fields(client, settings.chunks_collection, data)
        for i in range(0, len(data), 100):
            client.insert(collection_name=settings.chunks_collection, data=data[i:i + 100])
        logger.info(f"Inserted {len(data)} chunk rows")

    @classmethod
    def insert_products(cls, data: List[Dict]):
        settings = get_settings()
        client = cls.get_client()
        data = cls._filter_supported_fields(client, settings.entities_collection, data)
        for i in range(0, len(data), 100):
            client.insert(collection_name=settings.entities_collection, data=data[i:i + 100])
        logger.info(f"Inserted {len(data)} product rows")

    @classmethod
    def search_chunks(
        cls,
        query_dense: List[float],
        query_sparse: Dict | None = None,
        top_k: int = 5,
        filter_expr: str | None = None,
    ) -> List:
        from pymilvus import AnnSearchRequest
        from pymilvus import RRFRanker

        settings = get_settings()
        client = cls.get_client()
        output = cls._supported_output_fields(
            client,
            settings.chunks_collection,
            [
                "id", "task_id", "product_id", "product_name", "city", "doc_type",
                "chunk_id", "title", "content", "source_file", "source_url",
                "chunk_index", "image_urls", "image_alts",
            ],
        )
        dense_req = AnnSearchRequest(
            data=[query_dense],
            anns_field="dense_vector",
            param={"metric_type": "COSINE", "params": {"nprobe": 16}},
            limit=max(top_k * 2, 8),
            expr=filter_expr,
        )
        try:
            if query_sparse:
                sparse_req = AnnSearchRequest(
                    data=[query_sparse],
                    anns_field="sparse_vector",
                    param={"metric_type": "IP"},
                    limit=max(top_k * 2, 8),
                    expr=filter_expr,
                )
                results = client.hybrid_search(
                    collection_name=settings.chunks_collection,
                    reqs=[dense_req, sparse_req],
                    ranker=RRFRanker(k=60),
                    limit=top_k,
                    output_fields=output,
                )
            else:
                results = client.search(
                    collection_name=settings.chunks_collection,
                    data=[query_dense],
                    anns_field="dense_vector",
                    search_params={"metric_type": "COSINE", "params": {"nprobe": 16}},
                    limit=top_k,
                    output_fields=output,
                    filter=filter_expr,
                )
            return list(results[0]) if results else []
        except Exception as exc:
            logger.error(f"Chunk search failed: {exc}")
            return []

    @classmethod
    def search_products(cls, query_dense: List[float], query_sparse: Dict | None = None, top_k: int = 3) -> List:
        from pymilvus import AnnSearchRequest
        from pymilvus import RRFRanker

        settings = get_settings()
        client = cls.get_client()
        output = cls._supported_output_fields(
            client,
            settings.entities_collection,
            ["task_id", "product_id", "product_name", "city", "doc_type", "available_doc_types", "suggested_queries", "source_file"],
        )
        dense_req = AnnSearchRequest(
            data=[query_dense],
            anns_field="dense_vector",
            param={"metric_type": "COSINE", "params": {"nprobe": 16}},
            limit=max(top_k * 2, 6),
        )
        try:
            if query_sparse:
                sparse_req = AnnSearchRequest(
                    data=[query_sparse],
                    anns_field="sparse_vector",
                    param={"metric_type": "IP"},
                    limit=max(top_k * 2, 6),
                )
                results = client.hybrid_search(
                    collection_name=settings.entities_collection,
                    reqs=[dense_req, sparse_req],
                    ranker=RRFRanker(k=60),
                    limit=top_k,
                    output_fields=output,
                )
            else:
                results = client.search(
                    collection_name=settings.entities_collection,
                    data=[query_dense],
                    anns_field="dense_vector",
                    search_params={"metric_type": "COSINE", "params": {"nprobe": 16}},
                    limit=top_k,
                    output_fields=output,
                )
            return list(results[0]) if results else []
        except Exception as exc:
            logger.error(f"Product search failed: {exc}")
            return []

    @classmethod
    def delete_by_source_file(cls, source_file: str) -> Dict[str, int]:
        settings = get_settings()
        client = cls.get_client()
        escaped = source_file.replace("\\", "\\\\").replace('"', '\\"')
        results = {
            "chunks": cls._delete_if_supported(client, settings.chunks_collection, "source_file", f'source_file == "{escaped}"'),
            "products": cls._delete_if_supported(client, settings.entities_collection, "source_file", f'source_file == "{escaped}"'),
        }
        logger.info(f"Deleted Milvus rows for {source_file}: {results}")
        return results

    @classmethod
    def _collection_fields(cls, client, collection_name: str) -> Set[str]:
        try:
            desc = client.describe_collection(collection_name=collection_name)
            fields = desc.get("fields", []) if isinstance(desc, dict) else []
            return {field.get("name") for field in fields if isinstance(field, dict) and field.get("name")}
        except Exception as exc:
            logger.warning(f"Describe collection failed for {collection_name}: {exc}")
            return set()

    @classmethod
    def _filter_supported_fields(cls, client, collection_name: str, rows: List[Dict]) -> List[Dict]:
        fields = cls._collection_fields(client, collection_name)
        if not fields:
            return rows
        return [{k: v for k, v in row.items() if k in fields} for row in rows]

    @classmethod
    def _supported_output_fields(cls, client, collection_name: str, fields: List[str]) -> List[str]:
        existing = cls._collection_fields(client, collection_name)
        if not existing:
            return fields
        return [field for field in fields if field in existing]

    @classmethod
    def _delete_if_supported(cls, client, collection_name: str, field_name: str, filter_expr: str) -> Dict:
        fields = cls._collection_fields(client, collection_name)
        if fields and field_name not in fields:
            return {"deleted_count": 0, "skipped": True}
        result = client.delete(collection_name=collection_name, filter=filter_expr)
        client.flush(collection_name=collection_name)
        return result or {"deleted_count": 0}

    @classmethod
    def reset(cls):
        if cls._client:
            cls._client.close()
        cls._client = None
