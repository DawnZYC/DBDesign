"""Chat 路由（M3）— POST /api/chat/stream。

端点语义：
  接收用户消息 + 对话历史，驱动 LangGraph 4-Agent 图执行，
  用 Server-Sent Events（SSE）实时推送每个阶段的事件给前端。

SSE 事件协议（前端 M4 按此解析）：
  event: agent_start   data: {"node": "planner"|"sql_gen"|"interpreter"|"visualizer"}
  event: plan          data: {"steps": ["step1", "step2", ...]}
  event: token         data: {"delta": "..."}             ← Interpreter 流式 token
  event: tool_call     data: {"tool": "run_sql", "args": {...}}
  event: tool_result   data: {"tool": "run_sql", "row_count": 12, "truncated": false}
  event: chart         data: {"spec": {...echarts option...}}
  event: agent_end     data: {"node": "..."}
  event: error         data: {"message": "..."}
  event: done          data: {"trace_id": "..."}

实现方案：
  * graph.astream_events(state, version="v2") 订阅所有事件
  * 用事件 name / metadata.langgraph_node 过滤出感兴趣的事件类型
  * sse_starlette.sse.EventSourceResponse 包装异步生成器推给客户端
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.agents.graph import NODE_INTERPRETER, NODE_PLANNER, NODE_SQL, NODE_VISUALIZER, get_graph

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


# -----------------------------------------------------------------------------
# 请求 / 响应 schema
# -----------------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' 或 'assistant'")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="用户当前消息")
    history: list[ChatMessage] = Field(
        default_factory=list,
        description="对话历史（不含当前消息），最多保留最近 10 条",
    )

    @property
    def lc_messages(self) -> list:
        """把 history + 当前消息转为 LangChain BaseMessage 列表。"""
        msgs = []
        # 只保留最近 10 条历史（避免 context 过长）
        for cm in self.history[-10:]:
            if cm.role == "user":
                msgs.append(HumanMessage(content=cm.content))
            else:
                msgs.append(AIMessage(content=cm.content))
        msgs.append(HumanMessage(content=self.message))
        return msgs


# -----------------------------------------------------------------------------
# SSE 事件序列化助手
# -----------------------------------------------------------------------------
def _sse_event(event_type: str, data: Any) -> dict:
    """格式化为 sse_starlette 期望的 dict 格式。"""
    return {
        "event": event_type,
        "data": json.dumps(data, ensure_ascii=False, default=str),
    }


# -----------------------------------------------------------------------------
# 核心异步生成器：驱动 graph，把 LangGraph 事件转为 SSE 事件
# -----------------------------------------------------------------------------
async def _stream_graph_events(
    req: ChatRequest,
    trace_id: str,
) -> AsyncIterator[dict]:
    """监听 LangGraph astream_events，把感兴趣的事件转成 SSE dict 推出去。"""

    graph = get_graph()

    # 初始状态
    initial_state = {
        "messages": req.lc_messages,
        "plan": [],
        "sql_params": None,
        "sql_result": None,
        "interpretation": None,
        "chart_spec": None,
        "retry_count": 0,
        "error": None,
    }

    # 记录上一个节点，用于推送 agent_end
    current_node: str | None = None
    # 是否已经通过 on_chat_model_stream 推送过 token（避免 on_chain_end 兜底重复）
    tokens_sent: bool = False

    try:
        async for event in graph.astream_events(initial_state, version="v2"):
            ev_type: str = event.get("event", "")
            metadata: dict = event.get("metadata", {})
            node: str = metadata.get("langgraph_node", "")

            logger.debug("LG event: type=%s node=%s name=%s", ev_type, node, event.get("name", ""))

            # ---- 节点开始 ----
            if ev_type == "on_chain_start" and node and node != current_node:
                if node in (NODE_PLANNER, NODE_SQL, NODE_INTERPRETER, NODE_VISUALIZER):
                    if current_node:
                        yield _sse_event("agent_end", {"node": current_node})
                    current_node = node
                    if node == NODE_INTERPRETER:
                        tokens_sent = False  # 进入新 interpreter 节点时重置
                    yield _sse_event("agent_start", {"node": node})
                    logger.debug("SSE agent_start: node=%s", node)

            # ---- Planner 完成：推送 plan ----
            # 注意：on_chain_end 会为节点内的每条内部链（LLM call / prompt chain 等）
            # 都各触发一次，那些 output 是 AIMessage 等对象而不是 dict。只对真正
            # 节点出口（output 是 dict 且含 'plan' key）的事件做处理。
            elif ev_type == "on_chain_end" and node == NODE_PLANNER:
                output = event.get("data", {}).get("output")
                if isinstance(output, dict):
                    plan = output.get("plan", [])
                    if plan:
                        yield _sse_event("plan", {"steps": plan})
                        logger.debug("SSE plan: steps=%d", len(plan))

            # ---- SQL Agent 工具调用 ----
            elif ev_type == "on_tool_start" and node == NODE_SQL:
                tool_input = event.get("data", {}).get("input", {})
                yield _sse_event("tool_call", {"tool": "run_sql", "args": tool_input})
                logger.debug("SSE tool_call: run_sql")

            elif ev_type == "on_tool_end" and node == NODE_SQL:
                tool_output = event.get("data", {}).get("output", {})
                if isinstance(tool_output, dict):
                    yield _sse_event(
                        "tool_result",
                        {
                            "tool": "run_sql",
                            "row_count": tool_output.get("row_count", 0),
                            "truncated": tool_output.get("truncated", False),
                            "metric": tool_output.get("metric"),
                            "sql_summary": tool_output.get("sql_summary", ""),
                        },
                    )
                    logger.debug("SSE tool_result: row_count=%s", tool_output.get("row_count"))

            # ---- Interpreter：流式 token（打字机效果） ----
            elif ev_type == "on_chat_model_stream" and node == NODE_INTERPRETER:
                chunk = event.get("data", {}).get("chunk")
                if chunk is not None:
                    delta = chunk.content if hasattr(chunk, "content") else str(chunk)
                    if delta:
                        tokens_sent = True
                        yield _sse_event("token", {"delta": delta})

            # ---- Interpreter 完成：若流式 token 未触发，用兜底全量发送 ----
            # 同样要先排除内部 chain（LLM）的 on_chain_end，那些 output 是 AIMessage 不是 dict
            elif ev_type == "on_chain_end" and node == NODE_INTERPRETER:
                output = event.get("data", {}).get("output")
                if isinstance(output, dict) and not tokens_sent:
                    interpretation = output.get("interpretation") or ""
                    if interpretation:
                        logger.info("SSE token fallback: sending interpretation as single token")
                        yield _sse_event("token", {"delta": interpretation})
                        tokens_sent = True

            # ---- Visualizer 完成：推送图表 ----
            elif ev_type == "on_chain_end" and node == NODE_VISUALIZER:
                output = event.get("data", {}).get("output")
                if isinstance(output, dict):
                    chart_spec = output.get("chart_spec")
                    if chart_spec:
                        yield _sse_event("chart", {"spec": chart_spec})
                        logger.debug(
                            "SSE chart: chart_type=%s",
                            chart_spec.get("_meta", {}).get("chart_type"),
                        )
                    # 检查有无错误
                    error = output.get("error")
                    if error:
                        yield _sse_event("error", {"message": error})

        # ---- 结束：最后一个节点的 agent_end ----
        if current_node:
            yield _sse_event("agent_end", {"node": current_node})

        yield _sse_event("done", {"trace_id": trace_id})
        logger.info("SSE stream done: trace_id=%s", trace_id)

    except Exception as exc:  # noqa: BLE001
        logger.exception("SSE stream error: trace_id=%s", trace_id)
        yield _sse_event("error", {"message": f"服务端错误: {exc!s}"})
        yield _sse_event("done", {"trace_id": trace_id})


# -----------------------------------------------------------------------------
# FastAPI 端点
# -----------------------------------------------------------------------------
@router.post("/stream", summary="AI 助手流式对话（SSE）")
async def chat_stream(req: ChatRequest) -> EventSourceResponse:
    """POST /api/chat/stream

    接收用户消息，驱动 LangGraph 4-Agent 图，通过 SSE 实时推送执行事件。

    SSE 事件类型：
    - agent_start / agent_end：节点生命周期
    - plan：Planner 执行步骤
    - tool_call / tool_result：工具调用追踪
    - token：Interpreter 流式 token（打字机效果）
    - chart：ECharts 完整 option
    - error：局部错误（流仍继续）
    - done：流结束信号
    """
    trace_id = str(uuid.uuid4())
    logger.info("chat_stream: start trace_id=%s message_len=%d", trace_id, len(req.message))

    return EventSourceResponse(
        _stream_graph_events(req, trace_id),
        media_type="text/event-stream",
    )
