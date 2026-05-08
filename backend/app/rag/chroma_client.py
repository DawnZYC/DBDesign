"""ChromaDB 持久化向量库封装。

策略：
  - PersistentClient：本地嵌入式，目录由 settings.chroma_persist_dir 控制
  - 单例 vectorstore，按当前 embedding provider 自动注入
  - 切换 embedding provider 时，旧 collection 维度会不匹配 — 提供 reset_collection() 一键清空
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from langchain_chroma import Chroma

from app.config import get_settings
from app.rag.embeddings import get_embedder

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_vectorstore() -> Chroma:
    """获取（或新建）持久化 vectorstore 单例。

    第一次调用会触发 embedding 模型加载（HuggingFace 本地模型 ~80MB，会下载）。
    """
    settings = get_settings()
    persist_dir = Path(settings.chroma_persist_dir).expanduser().resolve()
    persist_dir.mkdir(parents=True, exist_ok=True)

    embedder = get_embedder()

    logger.info(
        "Init Chroma vectorstore: dir=%s collection=%s embedder=%s",
        persist_dir,
        settings.chroma_collection_name,
        type(embedder).__name__,
    )

    return Chroma(
        collection_name=settings.chroma_collection_name,
        embedding_function=embedder,
        persist_directory=str(persist_dir),
    )


def reset_collection() -> None:
    """删除并重建 collection（切换 embedding provider 后用）。"""
    settings = get_settings()
    persist_dir = Path(settings.chroma_persist_dir).expanduser().resolve()

    # 清掉单例缓存
    get_vectorstore.cache_clear()

    if persist_dir.exists():
        # 通过 chromadb 客户端 API 删 collection 更安全
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(persist_dir))
            try:
                client.delete_collection(name=settings.chroma_collection_name)
                logger.info("Deleted existing Chroma collection: %s",
                            settings.chroma_collection_name)
            except Exception:  # noqa: BLE001
                logger.info("No existing collection to delete (ok)")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to delete via API (%s); falling back", exc)


def get_collection_size() -> int:
    """返回当前 collection 中的文档数量。"""
    vs = get_vectorstore()
    try:
        return vs._collection.count()
    except Exception:  # noqa: BLE001
        return 0
