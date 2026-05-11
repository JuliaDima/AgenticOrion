"""
Literature search agent: queries the ArXiv API and returns structured paper records.
"""

import time
from datetime import datetime, timezone

from logging_db import get_logger
from state import ResearchState
from tools import search_arxiv


def literature_node(state: ResearchState) -> dict:
    logger = get_logger()
    run_id = state["run_id"]
    search_query = state.get("search_query") or state["query"]

    t0 = time.perf_counter()
    start_time = datetime.now(timezone.utc).isoformat()
    tool_start = start_time

    error: str | None = None
    results: list[dict] = []
    try:
        results = search_arxiv(search_query, max_results=5)
    except Exception as exc:
        error = str(exc)

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)

    logger.log_tool_call(
        run_id=run_id,
        agent_name="literature",
        tool_name="search_arxiv",
        input_data={"query": search_query, "max_results": 5},
        output_data={"count": len(results), "titles": [r["title"] for r in results]},
        start_time=tool_start,
        duration_ms=duration_ms,
        error=error,
    )
    logger.log_agent_call(
        run_id=run_id,
        agent_name="literature",
        input_summary=f"ArXiv search: {search_query!r}",
        output_summary=f"Found {len(results)} papers",
        start_time=start_time,
        duration_ms=duration_ms,
        error=error,
    )
    logger.log_state_transition(run_id, "supervisor", "literature", state)

    return {
        "literature_results": results,
        "current_step": "literature",
        "step_count": state.get("step_count", 0) + 1,
        "errors": state.get("errors", []) + ([error] if error else []),
    }
