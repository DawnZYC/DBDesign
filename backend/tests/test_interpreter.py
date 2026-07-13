"""Interpreter node unit tests — all three answer modes, offline.

The LLM is replaced by a fake whose astream yields scripted chunks, so the tests
cover: data-interpretation mode (with/without SQL results), tool-query mode,
direct-answer mode, the language directive, result summarization, and error paths.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from langchain_core.messages import AIMessageChunk, HumanMessage

from app.agents.interpreter import (
    MAX_ROWS_FOR_LLM,
    _language_directive,
    _summarize_result,
    interpreter_node,
)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
class FakeStreamingLLM:
    """Fake chat model: astream yields the scripted chunks (or raises)."""

    def __init__(self, chunks: list[str], error: Exception | None = None):
        self._chunks = chunks
        self._error = error
        self.calls: list[list] = []

    async def astream(self, messages):  # noqa: ANN001
        self.calls.append(messages)
        if self._error is not None:
            raise self._error
        for c in self._chunks:
            yield AIMessageChunk(content=c)


def _state(**overrides) -> dict:
    base = {
        "messages": [HumanMessage(content="Power sector capex 2030")],
        "plan": [],
        "sql_params": None,
        "sql_result": None,
        "tool_context": None,
        "interpretation": None,
        "chart_spec": None,
        "language": None,
        "retry_count": 0,
        "error": None,
    }
    base.update(overrides)
    return base


def _run(state: dict, llm: FakeStreamingLLM | None = None) -> dict:
    llm = llm or FakeStreamingLLM(["ok"])
    with patch("app.agents.interpreter.get_chat_model", return_value=llm):
        return asyncio.run(interpreter_node(state))


# -----------------------------------------------------------------------------
# _language_directive
# -----------------------------------------------------------------------------
def test_language_directive_empty_for_auto():
    assert _language_directive(_state(language=None)) == ""
    assert _language_directive(_state(language="   ")) == ""


def test_language_directive_names_the_language():
    directive = _language_directive(_state(language="Chinese"))
    assert "Chinese" in directive
    assert "IMPORTANT" in directive


# -----------------------------------------------------------------------------
# _summarize_result
# -----------------------------------------------------------------------------
def test_summarize_result_includes_metric_and_rows():
    summary = _summarize_result(
        {
            "rows": [{"year": 2030, "value": 1.5}],
            "row_count": 1,
            "metric": "capex",
            "metric_unit": "M$/GW",
            "aggregation": "avg",
            "sql_summary": "capex by year",
            "truncated": False,
        }
    )
    assert "capex" in summary
    assert "M$/GW" in summary
    assert "2030" in summary


def test_summarize_result_trims_to_max_rows():
    rows = [{"i": i} for i in range(MAX_ROWS_FOR_LLM + 20)]
    summary = _summarize_result({"rows": rows, "row_count": len(rows), "metric": "capex"})
    assert f"only the first {MAX_ROWS_FOR_LLM} shown" in summary


# -----------------------------------------------------------------------------
# Data-interpretation mode
# -----------------------------------------------------------------------------
def test_data_mode_streams_and_joins_chunks():
    llm = FakeStreamingLLM(["Capex ", "is ", "**rising**."])
    result = _run(
        _state(sql_result={"rows": [{"y": 2030, "v": 1}], "row_count": 1, "metric": "capex"}),
        llm,
    )
    assert result["interpretation"] == "Capex is **rising**."
    assert result["error"] is None


def test_data_mode_language_directive_reaches_prompt():
    llm = FakeStreamingLLM(["ok"])
    _run(
        _state(
            sql_result={"rows": [], "row_count": 0, "metric": "capex"},
            language="French",
        ),
        llm,
    )
    system_text = str(llm.calls[0][0].content)
    assert "French" in system_text


def test_no_result_with_error_reports_failure():
    result = _run(_state(sql_result=None, error="SQL failed: bad column"))
    assert "SQL failed: bad column" in result["interpretation"]
    assert result["error"] == "SQL failed: bad column"


def test_no_result_without_error_reports_zero_rows():
    result = _run(_state(sql_result=None, error=None))
    assert "matched no rows" in result["interpretation"]
    assert result["error"] is None


def test_data_mode_llm_failure_sets_error():
    llm = FakeStreamingLLM([], error=RuntimeError("rate limited"))
    result = _run(
        _state(sql_result={"rows": [{"y": 1}], "row_count": 1, "metric": "capex"}),
        llm,
    )
    assert "rate limited" in result["interpretation"]
    assert "Interpreter failed" in result["error"]


# -----------------------------------------------------------------------------
# Tool-query mode
# -----------------------------------------------------------------------------
def test_tool_mode_composes_from_tool_context():
    llm = FakeStreamingLLM(["1 PJ = **23.88 ktoe**"])
    result = _run(
        _state(intent="tool_query", tool_context="convert_unit -> {'value': 23.88}"),
        llm,
    )
    assert "23.88" in result["interpretation"]
    assert result["error"] is None
    # The tool context must be inside the prompt
    human_text = str(llm.calls[0][1].content)
    assert "convert_unit" in human_text


def test_tool_mode_without_context_reports_error():
    result = _run(_state(intent="tool_query", tool_context=None, error="tool crashed"))
    assert "tool crashed" in result["interpretation"]


def test_tool_mode_llm_failure_sets_error():
    llm = FakeStreamingLLM([], error=RuntimeError("timeout"))
    result = _run(_state(intent="tool_query", tool_context="some result"), llm)
    assert "Interpreter failed" in result["error"]


# -----------------------------------------------------------------------------
# Direct-answer mode
# -----------------------------------------------------------------------------
def test_direct_mode_answers_small_talk():
    llm = FakeStreamingLLM(["Hello! Ask me about capex."])
    result = _run(
        _state(intent="direct_answer", messages=[HumanMessage(content="hi")]),
        llm,
    )
    assert "Hello" in result["interpretation"]
    assert result["error"] is None


def test_direct_mode_empty_history_still_answers():
    llm = FakeStreamingLLM(["Hi!"])
    result = _run(_state(intent="direct_answer", messages=[]), llm)
    assert result["interpretation"] == "Hi!"


def test_direct_mode_llm_failure_sets_error():
    llm = FakeStreamingLLM([], error=RuntimeError("no key"))
    result = _run(
        _state(intent="direct_answer", messages=[HumanMessage(content="hi")]),
        llm,
    )
    assert "Interpreter failed" in result["error"]
