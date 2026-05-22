"""FastAPI 主应用 — 旅游知识库问答系统"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import os

load_dotenv()

from api.knowledge import router as knowledge_router
from core.mongo_manager import MongoManager
from core.milvus_manager import MilvusManager
from core.minio_manager import ensure_bucket
from tool.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        mongo = MongoManager.get()
        await mongo.ensure_indexes()
        logger.info("MongoDB 已连接")
    except Exception as e:
        logger.warning(f"MongoDB 初始化跳过: {e}")
    try:
        MilvusManager.ensure_collections()
        logger.info("Milvus 集合已就绪")
    except Exception as e:
        logger.warning(f"Milvus 初始化跳过: {e}")
    try:
        ensure_bucket()
        logger.info("MinIO bucket 已就绪")
    except Exception as e:
        logger.warning(f"MinIO 初始化跳过: {e}")
    yield
    try:
        MongoManager.reset()
    except Exception:
        pass
    try:
        MilvusManager.reset()
    except Exception:
        pass
    logger.info("服务关闭")


app = FastAPI(
    title="旅游知识库智能问答系统",
    description="基于 LangGraph + Milvus + BGE-M3 的旅游垂直领域 RAG 系统",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(knowledge_router, prefix="/api")

# 静态文件 (Vue3 前端)
dist_dir = os.path.join(os.path.dirname(__file__), "web", "dist")
if os.path.exists(dist_dir):
    app.mount("/", StaticFiles(directory=dist_dir, html=True), name="static")
