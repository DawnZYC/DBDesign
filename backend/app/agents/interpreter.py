"""Interpreter 节点 — 把 SQL 查询结果翻译为自然语言分析。

职责：
  1. 读取 AgentState.sql_result（QueryResult 序列化后的 dict）
  2. 用 llm.astream 流式生成分析文本，token 级别推给 SSE
  3. 完整文本写入 AgentState.interpretation

流式策略：
  * Interpreter 是整个流水线中唯一做 token 级流式的节点
  * 其他节点（Planner / SQL / Visualizer）都是 invoke（等待完整输出）
  * router（chat.py）监听 graph stream_mode="values" + stream_events，
    把 on_chat_model_stream 事件转为 SSE token 事件推给前端

数据裁剪：
  * SQL 结果可能有几百行，全部传给 LLM 会超 context window
  * 只取前 MAX_ROWS_FOR_LLM 行 + 统计摘要，避免超额消耗 token
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.state import AgentState
from app.llm.provider import get_chat_model

logger = logging.getLogger(__name__)

MAX_ROWS_FOR_LLM = 30  # 最多把这么多行发给 LLM，其余用统计摘要替代

# -----------------------------------------------------------------------------
# Prompt
# -----------------------------------------------------------------------------
_SYSTEM = """你是 SG-TIMES 数据分析平台的数据解读专家。
你的任务：用清晰、专业的中文解读 SQL 查询结果，给出有价值的洞察。

解读要求：
1. 先用一句话概括查询主题和结论
2. 指出数据中的关键趋势（最高/最低值、增减幅度、拐点等）
3. 如果数据被截断（truncated=True），明确告知用户数据不完整
4. 用 Markdown 格式输出，可以包含加粗重点
5. 控制在 200-400 字，不要过度铺开
6. 不要重复列出原始数据行，只分析规律
"""


def _summarize_result(sql_result: dict[str, Any]) -> str:
    """把 SQL 结果压缩成 LLM 可消化的文本摘要。"""
    rows: list[dict] = sql_result.get("rows", [])
    row_count = sql_result.get("row_count", len(rows))
    metric = sql_result.get("metric", "unknown")
    aggregation = sql_result.get("aggregation", "raw")
    metric_unit = sql_result.get("metric_unit", "")
    sql_summary = sql_result.get("sql_summary", "")
    truncated = sql_result.get("truncated", False)

    # 只取前 MAX_ROWS_FOR_LLM 行传给 LLM
    sample = rows[:MAX_ROWS_FOR_LLM]
    sample_json = json.dumps(sample, ensure_ascii=False, indent=2, default=str)

    lines = [
        f"查询摘要：{sql_summary}",
        f"指标：{metric}（单位：{metric_unit or '未知'}）| 聚合：{aggregation}",
        f"总行数：{row_count}{'（已截断至 limit）' if truncated else ''}",
        "",
        f"数据样本（前 {len(sample)} 行）：",
        sample_json,
    ]
    if row_count > MAX_ROWS_FOR_LLM:
        lines.append(f"\n[注：共 {row_count} 行，仅展示前 {MAX_ROWS_FOR_LLM} 行供分析]")

    return "\n".join(lines)


# -----------------------------------------------------------------------------
# 节点函数（async，支持流式 token）
# -----------------------------------------------------------------------------
async def interpreter_node(state: AgentState) -> dict:
    """LangGraph 节点：Interpreter（async 版本）。

    使用 llm.astream 流式生成，LangGraph astream_events(version="v2") 会捕获
    on_chat_model_stream 事件，router 层将其转为 SSE token 推给前端（打字机效果）。

    同步调用（测试/graph.invoke）时 LangGraph 会自动在事件循环中 await。
    """
    logger.info("interpreter_node: start (intent=%s)", state.get("intent"))

    # 直接回答模式（Planner 判定为闲聊 / 概念问题）：不依赖 SQL 结果，
    # 用对话 prompt 流式回答。流式 token 透出方式与数据解读模式完全一致。
    if state.get("intent") == "direct_answer":
        return await _direct_answer(state)

    sql_result = state.get("sql_result")
    if not sql_result:
        return {
            "interpretation": "没有可分析的数据（SQL 查询未返回结果）。",
            "error": None,
        }

    result_summary = _summarize_result(sql_result)
    llm = get_chat_model()

    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=f"请解读以下查询结果：\n\n{result_summary}"),
    ]

    try:
        chunks: list[str] = []
        async for chunk in llm.astream(messages):
            content = chunk.content
            if isinstance(content, str):
                chunks.append(content)
        text = "".join(chunks)
        logger.info("interpreter_node: generated %d chars", len(text))
        return {"interpretation": text, "error": None}
    except Exception as exc:  # noqa: BLE001
        logger.exception("interpreter_node: LLM call failed")
        return {
            "interpretation": f"解读生成失败：{exc!s}",
            "error": f"Interpreter 失败: {exc!s}",
        }


_DIRECT_SYSTEM = """你是 SG-TIMES 能源数据分析平台的 AI 助手，友好、简洁。

你的能力（用户问起时可介绍）：
- 用自然语言查询新加坡能源系统模型数据：capex / 运维成本 / 排放因子 / 容量等指标，
  支持跨部门（Power、Industry、Transport 等 10 个）、跨年份的查询、对比与趋势图
- 术语解释（如 PWRNGA 等商品编码）、单位换算（PJ/ktoe/GWh）、趋势预测

回答要求：用中文、保持简短（闲聊 1-3 句即可）；如果用户的问题其实需要查数据，
引导他直接提出具体的数据问题（举一个示例问法）。不要编造数据库里的数值。"""


async def _direct_answer(state: AgentState) -> dict:
    """对话式直接回答（不查库）。复用 astream 以便前端拿到流式 token。"""
    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    question = str(user_messages[-1].content) if user_messages else "你好"

    llm = get_chat_model()
    messages = [SystemMessage(content=_DIRECT_SYSTEM), HumanMessage(content=question)]
    try:
        chunks: list[str] = []
        async for chunk in llm.astream(messages):
            content = chunk.content
            if isinstance(content, str):
                chunks.append(content)
        text = "".join(chunks)
        logger.info("interpreter_node(direct): generated %d chars", len(text))
        return {"interpretation": text, "error": None}
    except Exception as exc:  # noqa: BLE001
        logger.exception("interpreter_node(direct): LLM call failed")
        return {
            "interpretation": f"回答生成失败：{exc!s}",
            "error": f"Interpreter 失败: {exc!s}",
        }
