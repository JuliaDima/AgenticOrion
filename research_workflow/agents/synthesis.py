"""
Synthesis agent: combines literature findings and code results into a
structured Markdown research report.
"""

import time
from datetime import datetime, timezone

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from logging_db import get_logger
from state import ResearchState


_SYSTEM = """\
You are a scientific research synthesiser.
Produce a concise, structured Markdown report with these sections:
  ## Summary
  ## Key Findings (bullet points, one per paper or major insight)
  ## Quantitative Analysis (only if code results are provided)
  ## Conclusion
  ## References (title + URL for each paper)

Be precise and factual. Do not speculate beyond what the evidence supports.
"""


def synthesis_node(state: ResearchState) -> dict:
    logger = get_logger()
    run_id = state["run_id"]
    start_time = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()

    papers_block = "\n\n".join(
        f"[{i+1}] {p['title']} ({p['published']})\n"
        f"Authors: {', '.join(p['authors'])}\n"
        f"URL: {p['url']}\n"
        f"Abstract: {p['abstract']}"
        for i, p in enumerate(state.get("literature_results", []))
    )

    code_block = ""
    cr = state.get("code_results") or {}
    if not cr.get("skipped") and not cr.get("error"):
        code_block = (
            f"\n\nPython analysis output:\n```\n{cr.get('stdout', '')}\n```"
        )
    elif cr.get("error"):
        code_block = f"\n\nCode execution error: {cr['error']}"

    user_content = (
        f"Research query: {state['query']}\n\n"
        f"Papers found:\n{papers_block}"
        f"{code_block}"
    )

    llm = ChatAnthropic(model="claude-sonnet-4-20250514", temperature=0)
    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=user_content),
    ]

    error: str | None = None
    report = "Report generation failed."
    try:
        response = llm.invoke(messages)
        report = response.content
    except Exception as exc:
        error = str(exc)

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    logger.log_agent_call(
        run_id=run_id,
        agent_name="synthesis",
        input_summary=f"{len(state.get('literature_results', []))} papers + code_results",
        output_summary=report[:300],
        start_time=start_time,
        duration_ms=duration_ms,
        error=error,
    )
    logger.log_state_transition(run_id, "code_executor", "synthesis", state)

    return {
        "synthesis_report": report,
        "current_step": "synthesis",
        "step_count": state.get("step_count", 0) + 1,
        "errors": state.get("errors", []) + ([error] if error else []),
    }
