"""RAG retrieval + knowledge-document upload routes (M1 / knowledge base management)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.rag import list_embedding_providers, search
from app.rag.chroma_client import get_collection_size
from app.rag.ingest import (
    delete_uploaded_document,
    ingest_uploaded_text,
    list_uploaded_documents,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rag", tags=["rag"])


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural-language query")
    k: int = Field(default=5, ge=1, le=50)


class SearchResultItem(BaseModel):
    text: str
    score: float
    metadata: dict


class SearchResponse(BaseModel):
    query: str
    k: int
    hits: list[SearchResultItem]


@router.post("/search", response_model=SearchResponse, summary="Semantic search over the domain knowledge base")
def rag_search(req: SearchRequest) -> SearchResponse:
    try:
        hits = search(req.query, k=req.k)
    except Exception as exc:  # noqa: BLE001
        logger.exception("RAG search failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {exc!s}",
        ) from exc
    return SearchResponse(
        query=req.query,
        k=req.k,
        hits=[SearchResultItem(text=h.text, score=h.score, metadata=h.metadata) for h in hits],
    )


@router.get("/info", summary="RAG subsystem status (vector store size + embedding provider)")
def rag_info() -> dict:
    """For the frontend settings page: know how many entries exist and which embedding is active."""
    try:
        size = get_collection_size()
    except Exception as exc:  # noqa: BLE001
        size = -1
        logger.warning("get_collection_size failed: %s", exc)

    return {
        "collection_size": size,
        "providers": list_embedding_providers(),
    }


# -----------------------------------------------------------------------------
# Knowledge-document upload management (source='upload', independent of domain_knowledge.md / dictionaries)
# -----------------------------------------------------------------------------
_ALLOWED_DOC_SUFFIXES = (".md", ".markdown", ".txt")
_MAX_DOC_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB, plenty for a knowledge document


class UploadDocResponse(BaseModel):
    file: str
    chunks: int = Field(..., description="Number of chunks (vectors); split by H2 headings, or aggregated by paragraph when no headings")


class UploadedDocInfo(BaseModel):
    file: str
    chunks: int
    titles: list[str] = Field(default_factory=list, description="List of H2 titles in the document")


@router.post(
    "/documents",
    response_model=UploadDocResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a knowledge document (.md / .txt) into the vector store; same name overwrites",
)
async def upload_document(
    file: UploadFile = File(..., description="Markdown or plain-text knowledge document"),
) -> UploadDocResponse:
    name = file.filename or "upload.md"
    if not name.lower().endswith(_ALLOWED_DOC_SUFFIXES):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {_ALLOWED_DOC_SUFFIXES} documents are supported",
        )
    raw = await file.read()
    if not raw.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty")
    if len(raw) > _MAX_DOC_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {_MAX_DOC_SIZE_BYTES // 1024 // 1024} MB limit",
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is not valid UTF-8 text",
        ) from exc

    try:
        chunks = ingest_uploaded_text(text, file_name=name)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Knowledge document ingestion failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {exc!s}",
        ) from exc
    return UploadDocResponse(file=name, chunks=chunks)


@router.get(
    "/documents",
    response_model=list[UploadedDocInfo],
    summary="List uploaded knowledge documents",
)
def list_documents() -> list[UploadedDocInfo]:
    try:
        return [UploadedDocInfo(**d) for d in list_uploaded_documents()]
    except Exception as exc:  # noqa: BLE001
        logger.exception("Listing knowledge documents failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query failed: {exc!s}",
        ) from exc


@router.delete(
    "/documents/{file_name}",
    summary="Delete all knowledge chunks of an uploaded document",
)
def delete_document(file_name: str) -> dict:
    try:
        deleted = delete_uploaded_document(file_name)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Deleting knowledge document failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Deletion failed: {exc!s}",
        ) from exc
    if deleted == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {file_name!r} not found",
        )
    return {"file": file_name, "deleted": deleted}
