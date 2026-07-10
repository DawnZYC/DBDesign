"""Golden-question evaluation runner for the EcoTEA multi-agent platform.

Streams each question in eval/golden_questions.yaml through
POST /api/chat/stream, collects the final answer / tool calls / chart spec,
and scores them against the expectations:

  * keywords    — every expected keyword appears in the answer (case-insensitive)
  * tools       — every expected tool shows up in tool_call events
  * chart       — the chart event's first series type matches expected_chart_type
                  ("none" means a chart is simply not required)

Usage:
    python eval/runner.py                                  # localhost:8000
    python eval/runner.py --base-url http://localhost:8000 --ids q01,q07
    python eval/runner.py --json report.json               # machine-readable report

Exit code is 0 when the pass rate meets --min-pass-rate (default 0.8),
1 otherwise — suitable for a non-blocking CI job.

Prerequisites: backend running, template imported, seed scripts executed.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import yaml

QUESTIONS_FILE = Path(__file__).parent / "golden_questions.yaml"


@dataclass
class StreamResult:
    answer: str = ""
    tools_called: list[str] = field(default_factory=list)
    chart_spec: dict | None = None
    error: str | None = None
    duration_s: float = 0.0


def stream_chat(base_url: str, question: str, timeout: float) -> StreamResult:
    """POST /api/chat/stream and fold the SSE events into a StreamResult."""
    result = StreamResult()
    started = time.perf_counter()
    payload = {"message": question, "history": []}

    event_type = ""
    with (
        httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0)) as client,
        client.stream("POST", f"{base_url}/api/chat/stream", json=payload) as response,
    ):
        response.raise_for_status()
        for raw_line in response.iter_lines():
            line = raw_line.strip()
            if line.startswith("event:"):
                event_type = line[len("event:") :].strip()
                continue
            if not line.startswith("data:"):
                continue
            try:
                data = json.loads(line[len("data:") :].strip())
            except json.JSONDecodeError:
                continue
            if event_type == "token":
                result.answer += data.get("delta", "")
            elif event_type == "tool_call":
                tool = data.get("tool")
                if tool:
                    result.tools_called.append(tool)
            elif event_type == "chart":
                result.chart_spec = data.get("spec")
            elif event_type == "error":
                result.error = data.get("message")
            elif event_type == "done":
                break

    result.duration_s = time.perf_counter() - started
    return result


def chart_series_type(spec: dict | None) -> str:
    """Pull the first series type out of an ECharts option, or 'none'."""
    if not spec:
        return "none"
    series = spec.get("series") or []
    if isinstance(series, dict):
        series = [series]
    for s in series:
        if isinstance(s, dict) and s.get("type"):
            return str(s["type"])
    return "none"


def score(case: dict, result: StreamResult) -> tuple[bool, list[str]]:
    """Return (passed, list of failure reasons) for one golden question."""
    reasons: list[str] = []
    answer_lower = result.answer.lower()

    if result.error:
        reasons.append(f"stream error: {result.error}")

    for kw in case.get("expected_keywords") or []:
        if str(kw).lower() not in answer_lower:
            reasons.append(f"keyword missing: {kw!r}")

    called = set(result.tools_called)
    for tool in case.get("expected_tools") or []:
        if tool not in called:
            reasons.append(f"tool not called: {tool}")

    expected_chart = case.get("expected_chart_type", "none")
    if expected_chart and expected_chart != "none":
        actual = chart_series_type(result.chart_spec)
        if actual != expected_chart:
            reasons.append(f"chart type: expected {expected_chart}, got {actual}")

    return (not reasons, reasons)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--ids", default="", help="comma-separated case ids to run")
    parser.add_argument("--timeout", type=float, default=120.0, help="per-question seconds")
    parser.add_argument("--min-pass-rate", type=float, default=0.8)
    parser.add_argument("--json", dest="json_out", default="", help="write JSON report here")
    args = parser.parse_args()

    cases: list[dict] = yaml.safe_load(QUESTIONS_FILE.read_text(encoding="utf-8"))
    if args.ids:
        wanted = {i.strip() for i in args.ids.split(",") if i.strip()}
        cases = [c for c in cases if c["id"] in wanted]
    if not cases:
        print("No cases selected.")
        return 1

    report: list[dict] = []
    passed_count = 0
    for case in cases:
        try:
            result = stream_chat(args.base_url, case["question"], args.timeout)
        except httpx.HTTPError as exc:
            result = StreamResult(error=f"HTTP error: {exc}")
        ok, reasons = score(case, result)
        passed_count += ok
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {case['id']:<28} {result.duration_s:6.1f}s  tools={result.tools_called}")
        for r in reasons:
            print(f"         - {r}")
        report.append(
            {
                "id": case["id"],
                "category": case.get("category"),
                "passed": ok,
                "reasons": reasons,
                "duration_s": round(result.duration_s, 1),
                "tools_called": result.tools_called,
                "answer_preview": result.answer[:200],
            }
        )

    rate = passed_count / len(cases)
    print("=" * 60)
    print(
        f"Pass rate: {passed_count}/{len(cases)} = {rate:.0%} (threshold {args.min_pass_rate:.0%})"
    )

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"pass_rate": rate, "results": report}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"JSON report written to {args.json_out}")

    return 0 if rate >= args.min_pass_rate else 1


if __name__ == "__main__":
    raise SystemExit(main())
