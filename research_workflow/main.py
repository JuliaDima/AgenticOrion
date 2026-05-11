"""
Entry point: run a single research query through the LangGraph workflow.

Usage:
    python main.py "What are recent advances in transformer models for protein folding?"
    python main.py  # uses a default query
"""

import sys
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import os
sys.path.insert(0, str(Path(__file__).parent))

from graph import build_graph
from logging_db import get_logger
from state import ResearchState

_DEFAULT_QUERY = (
    "What are the latest advances in quantum error correction for fault-tolerant quantum computing?"
)


def run_query(query: str) -> ResearchState:
    run_id = str(uuid.uuid4())
    logger = get_logger()
    logger.log_run_start(run_id, query)

    initial_state: ResearchState = {
        "run_id": run_id,
        "query": query,
        "supervisor_plan": None,
        "needs_code": False,
        "search_query": query,
        "analysis_description": "",
        "literature_results": [],
        "code_to_execute": None,
        "code_results": None,
        "synthesis_report": None,
        "current_step": "init",
        "errors": [],
        "step_count": 0,
    }

    graph = build_graph()

    t0 = time.perf_counter()
    status = "success"
    final_state: ResearchState = initial_state
    try:
        final_state = graph.invoke(initial_state)
    except Exception as exc:
        status = "error"
        print(f"[error] Workflow failed: {exc}", file=sys.stderr)
        final_state = {**initial_state, "errors": [str(exc)]}

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    if final_state.get("errors"):
        status = "partial"
    logger.log_run_end(run_id, status, duration_ms)

    return final_state


def main() -> None:
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else _DEFAULT_QUERY
    print(f"\nRunning research workflow for query:\n  {query}\n")

    result = run_query(query)

    print("\n" + "═" * 72)
    print("SYNTHESIS REPORT")
    print("═" * 72)
    print(result.get("synthesis_report") or "[no report generated]")
    print("\n" + "═" * 72)
    print(f"Run ID : {result['run_id']}")
    print(f"Steps  : {result['step_count']}")
    if result.get("errors"):
        print(f"Errors : {result['errors']}")
    print("\nView full trace with:")
    print(f"  python trace_viewer.py {result['run_id']}")


if __name__ == "__main__":
    main()
