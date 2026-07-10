"""Conversation-context helpers — let each Agent node carry the last few turns.

Bug this fixes: user says "help me look at power data" -> assistant asks which metric
-> user replies just "capex". Previously the Planner / SQL Agent / direct-answer mode
only took the last user message, so the key context "power" was dropped and the
assistant kept re-asking.

Design:
  * render_context()  — render the last N Human/AI messages into a plain-text
    transcript, injected into the Planner / SQL Agent prompt (most robust for the
    structured-output case).
  * recent_messages() — return the last N Human/AI message objects; direct-answer
    mode passes them as-is as chat messages to the LLM (the most natural multi-turn form).
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

# Per-message truncation length when rendering into the transcript (interpretation
# answers can be long; truncate to avoid token blow-up).
_MAX_CHARS_PER_MESSAGE = 200


def recent_messages(messages: list[BaseMessage], *, limit: int = 8) -> list[BaseMessage]:
    """Return the last `limit` conversation messages (Human/AI only; filter system/tool)."""
    convo = [m for m in messages if isinstance(m, HumanMessage | AIMessage)]
    return convo[-limit:]


def render_context(messages: list[BaseMessage], *, limit: int = 6) -> str:
    """Render the recent conversation "before the current message" into transcript text.

    The last Human message is treated as the current question and excluded (the caller
    injects it into the prompt separately). Returns an empty string when there is no
    history, so the caller can skip the context block.
    """
    convo = [m for m in messages if isinstance(m, HumanMessage | AIMessage)]
    prior = convo[:-1][-limit:]  # drop the current message, then take the last `limit`
    lines: list[str] = []
    for m in prior:
        role = "User" if isinstance(m, HumanMessage) else "Assistant"
        content = str(m.content).strip()
        if len(content) > _MAX_CHARS_PER_MESSAGE:
            content = content[:_MAX_CHARS_PER_MESSAGE] + "…"
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def with_context(question: str, messages: list[BaseMessage], *, limit: int = 6) -> str:
    """Wrap the current question as "[Conversation context] + [Current message]"."""
    context = render_context(messages, limit=limit)
    if not context:
        return question
    return f"[Conversation context]\n{context}\n\n[Current message]\n{question}"
