"""Agent router – SSE streaming chat endpoint.

POST /api/agent/chat
  Body: { "message": "...", "history": [{"role": "user"|"assistant", "content": "..."}] }
  Response: text/event-stream

GET /api/agent/index
  Triggers re-indexing of technology descriptions into ChromaDB.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.agent_service import run_agent_stream
from app.services.chroma_service import index_technologies

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


@router.post("/chat")
async def chat(request: ChatRequest):
    """Stream the agent's response via Server-Sent Events."""

    history = [m.model_dump() for m in request.history]

    async def event_generator():
        try:
            async for chunk in run_agent_stream(request.message, history=history):
                yield {"data": json.dumps(chunk, ensure_ascii=False)}
        except Exception as exc:
            logger.error("SSE generator error: %s", exc)
            yield {"data": json.dumps({"type": "error", "content": str(exc)})}

    return EventSourceResponse(event_generator())


@router.post("/index")
def trigger_index(db: Session = Depends(get_db)):
    """Re-index all technology descriptions into ChromaDB."""
    count = index_technologies(db)
    return {"indexed": count, "status": "ok"}
