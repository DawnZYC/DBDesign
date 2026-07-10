"""Planner node — intent routing + decomposing a data question into ordered steps.

Responsibilities:
  1. Read the latest user message from the conversation history.
  2. Use the LLM to classify intent (data_query / chat) and, for data questions,
     generate 3-5 execution steps.
  3. Write the intent into AgentState.intent and the steps into AgentState.plan;
     clear the error field.

Intent routing (fixes "small talk also runs SQL + charts"):
  * data_query     -> full pipeline: SQL Agent -> Interpreter -> Visualizer
  * tool_query     -> Tool Agent (function-calling: terminology / unit / emission / forecast)
                      -> Interpreter, no SQL, no chart
  * direct_answer  -> straight to the Interpreter for a conversational answer, no
                      tools, no DB query, no chart

Notes:
  * Plain llm.invoke; intent and steps are produced in a single call (saves one LLM round-trip).
  * First output line is `INTENT: ...`, the rest is a Markdown bullet list.
  * On parse failure, conservatively treat it as data_query (preserves old behavior).
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.context import with_context
from app.agents.state import AgentState
from app.llm.provider import get_chat_model

logger = logging.getLogger(__name__)

INTENT_DATA_QUERY = "data_query"
INTENT_TOOL_QUERY = "tool_query"
INTENT_DIRECT_ANSWER = "direct_answer"

# -----------------------------------------------------------------------------
# Prompt
# -----------------------------------------------------------------------------
_SYSTEM = """You are the Planner of the EcoTEA data analysis platform.

Step 1 — classify the user's intent and write it on the FIRST line:
  INTENT: data_query   -- asking about data in the database: metric VALUES, trends,
                          comparisons, rankings, totals, technology parameters by year/sector
  INTENT: tool_query   -- can be answered by a helper tool rather than a DB query:
                          * what a commodity/technology code MEANS (e.g. "what is BIOMASS01?")
                          * unit conversion (e.g. "1 PJ natural gas in ktoe")
                          * a single technology's emission factor for a year
                          * forecasting / extrapolating a trend the user provides
  INTENT: chat         -- greetings, small talk, thanks, "who are you / what can you do",
                          pure concept explanations -- needs neither a DB query nor a tool

Note: the message may include a [Conversation context] block. Use it when
classifying and planning -- e.g. if the assistant previously asked "which
metric?" and the user replies just "capex", that continues the earlier data
question (intent data_query), and the plan must merge the sector / years /
metric mentioned earlier in the context.

Step 2 — ONLY when INTENT is data_query, break the question into 3-5 concise steps:
- Markdown bullet list, one step per line
- start each step with a verb, keep it specific
- at most 5 steps, each under 15 words
When INTENT is tool_query or chat, output the INTENT line only — no steps.

Metrics available in the database: capex, fixed_opex, variable_opex,
emission_factor, tax_cost, subsidy_cost, efficiency_value,
technology_efficiency, heat_rate, capacity_to_activity_factor, capacity,
commodity_demand_value

Example 1 (data question):
INTENT: data_query
- Query raw capex data for the Power sector, 2018-2050
- Aggregate capex by year (sum)
- Show the trend as a line chart

Example 2 (terminology / unit / forecast):
INTENT: tool_query

Example 3 (small talk / greeting):
INTENT: chat
"""


def _parse_intent(raw: str) -> str:
    """Extract INTENT from the start of the LLM output; default to data_query when
    missing or unrecognized (conservative)."""
    for line in raw.splitlines()[:3]:
        normalized = line.strip().lower()
        if normalized.startswith("intent"):
            if "tool" in normalized:
                return INTENT_TOOL_QUERY
            if "chat" in normalized:
                return INTENT_DIRECT_ANSWER
            return INTENT_DATA_QUERY
    return INTENT_DATA_QUERY


def _parse_plan(raw: str) -> list[str]:
    """Convert the LLM's Markdown bullet list into list[str] (the INTENT line is skipped)."""
    steps: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith(("- ", "* ", "• ")):
            step = line[2:].strip()
        elif line and line[0].isdigit() and ". " in line:
            # Fallback: handle the "1. xxx" format
            step = line.split(". ", 1)[-1].strip()
        else:
            continue
        if step:
            steps.append(step)
    return steps


# -----------------------------------------------------------------------------
# Node function
# -----------------------------------------------------------------------------
def planner_node(state: AgentState) -> dict:
    """LangGraph node: Planner.

    In:  AgentState (reads messages)
    Out: { plan, intent, error } (partial state update)
    """
    logger.info("planner_node: start (retry_count=%d)", state.get("retry_count", 0))

    # Take the latest user message as the core question
    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    if not user_messages:
        logger.warning("planner_node: no HumanMessage found in state")
        return {
            "plan": ["Could not understand the question, please rephrase"],
            "intent": INTENT_DIRECT_ANSWER,
            "error": "missing user message",
        }

    latest_question = user_messages[-1].content

    # On a retry (retry_count > 0), attach the previous error to the prompt to inform the LLM
    retry_note = ""
    if state.get("retry_count", 0) > 0 and state.get("error"):
        retry_note = (
            f"\n\n[Retry hint] The previous attempt failed with: {state['error']}\n"
            "Adjust the query strategy: try broader filters or a different aggregation."
        )

    llm = get_chat_model()
    # Carry the last few turns: the user may have replied with only a metric name
    # (e.g. "capex"), so the full intent must be reconstructed from context
    # (e.g. "help me look at power data").
    prompt = with_context(str(latest_question), state["messages"]) + retry_note
    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=prompt),
    ]

    try:
        response = llm.invoke(messages)
        raw_text = response.content if isinstance(response.content, str) else str(response.content)
        intent = _parse_intent(raw_text)
        plan = _parse_plan(raw_text)
        if intent == INTENT_DATA_QUERY and not plan:
            # Data question but no steps parsed: fall back to treating the whole text as one step (old behavior)
            plan = [raw_text.strip()]
        logger.info("planner_node: intent=%s, %d steps", intent, len(plan))
        return {"plan": plan, "intent": intent, "error": None}
    except Exception as exc:  # noqa: BLE001
        logger.exception("planner_node: LLM call failed")
        return {"plan": [], "intent": INTENT_DATA_QUERY, "error": f"Planner failed: {exc!s}"}
