"""
Code executor agent: asks the LLM to write analysis code, then runs it
in a sandboxed subprocess and returns the results.
Skips execution if the supervisor determined no code is needed.
"""

import time
from datetime import datetime, timezone

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from logging_db import get_logger
from state import ResearchState
from tools import execute_python


_SYSTEM = """\
You are a scientific data-analysis assistant.
You will be given:
  - A research topic and analysis goal
  - Abstracts of relevant papers

Write a self-contained Python script (no external data files, no matplotlib show calls)
that performs the requested analysis using only the Python standard library and numpy/scipy
if needed. The script must print its results clearly. Do not include markdown fences or
explanations — output only valid Python code.
"""


def code_executor_node(state: ResearchState) -> dict:
    logger = get_logger()
    run_id = state["run_id"]
    start_time = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()

    # Skip if supervisor said no code needed
    if not state.get("needs_code", False):
        logger.log_agent_call(
            run_id=run_id,
            agent_name="code_executor",
            input_summary="skipped (needs_code=False)",
            output_summary="no-op",
            start_time=start_time,
            duration_ms=0.0,
        )
        logger.log_state_transition(run_id, "literature", "code_executor", state)
        return {
            "code_to_execute": None,
            "code_results": {"skipped": True, "reason": "Supervisor determined no code needed."},
            "current_step": "code_executor",
            "step_count": state.get("step_count", 0) + 1,
        }

    # Build context from literature results
    papers_ctx = "\n\n".join(
        f"Title: {p['title']}\nAbstract: {p['abstract']}"
        for p in state.get("literature_results", [])[:3]
    )

    llm = ChatAnthropic(model="claude-sonnet-4-20250514", temperature=0)
    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(
            content=(
                f"Research topic: {state['query']}\n\n"
                f"Analysis goal: {state.get('analysis_description', 'Quantitative summary of findings.')}\n\n"
                f"Relevant papers:\n{papers_ctx}"
            )
        ),
    ]

    error: str | None = None
    code = ""
    code_results: dict = {}

    try:
        llm_start = datetime.now(timezone.utc).isoformat()
        llm_t0 = time.perf_counter()
        response = llm.invoke(messages)
        llm_dur = round((time.perf_counter() - llm_t0) * 1000, 1)
        code = response.content.strip()
        # Strip markdown fences if the model wrapped the code anyway
        if code.startswith("```"):
            lines = code.split("\n")
            code = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        logger.log_tool_call(
            run_id=run_id,
            agent_name="code_executor",
            tool_name="llm_code_generation",
            input_data={"analysis_description": state.get("analysis_description", "")},
            output_data={"code_preview": code[:300]},
            start_time=llm_start,
            duration_ms=llm_dur,
        )

        # Execute the generated code
        exec_start = datetime.now(timezone.utc).isoformat()
        exec_t0 = time.perf_counter()
        code_results = execute_python(code)
        exec_dur = round((time.perf_counter() - exec_t0) * 1000, 1)

        logger.log_tool_call(
            run_id=run_id,
            agent_name="code_executor",
            tool_name="execute_python",
            input_data={"code_preview": code[:300]},
            output_data=code_results,
            start_time=exec_start,
            duration_ms=exec_dur,
            error=code_results.get("stderr") or None,
        )
    except Exception as exc:
        error = str(exc)
        code_results = {"error": error}

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    logger.log_agent_call(
        run_id=run_id,
        agent_name="code_executor",
        input_summary=state.get("analysis_description", "")[:200],
        output_summary=str(code_results.get("stdout", ""))[:200] or str(code_results)[:200],
        start_time=start_time,
        duration_ms=duration_ms,
        error=error,
    )
    logger.log_state_transition(run_id, "literature", "code_executor", state)

    return {
        "code_to_execute": code,
        "code_results": code_results,
        "current_step": "code_executor",
        "step_count": state.get("step_count", 0) + 1,
        "errors": state.get("errors", []) + ([error] if error else []),
    }
