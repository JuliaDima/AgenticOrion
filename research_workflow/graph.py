"""
OrionSpectrum LangGraph workflow.

Architecture:
  START → supervisor → observation_characterizer
                              ↓
          ┌──────────────────────────────────────┐
          ↓         ↓            ↓               ↓
  astrophysical  artefact   novelty_assessor  context_retriever
  _interpreter   _checker              (parallel fan-out)
          ↓         ↓            ↓               ↓
          └──────────────────────────────────────┘
                              ↓
                    evidence_aggregator
                              ↓
              ┌───────────────────────────────┐
              ↓                               ↓
    followup_prioritizer           code_executor (optional)
              ↓                               ↓
              └───────────────────────────────┘
                              ↓
                           synthesis
                              ↓
                             END

The parallel section (4 branches) is timed with wall-clock precision.
A TimingBarrier node wraps the fan-in to record the true parallel wall time.
"""

import sys
import os
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

from langgraph.graph import END, START, StateGraph

from agents.astrophysical_interpreter import astrophysical_interpreter_node
from agents.artefact_checker import artefact_checker_node
from agents.code_executor import code_executor_node
from agents.context_retriever import context_retriever_node
from agents.evidence_aggregator import evidence_aggregator_node
from agents.followup_prioritizer import followup_prioritizer_node
from agents.novelty_assessor import novelty_assessor_node
from agents.observation_characterizer import observation_characterizer_node
from agents.supervisor import supervisor_node
from agents.synthesis import synthesis_node
from state import ResearchState


# ---------------------------------------------------------------------------
# Timing barrier: records the wall-clock time when ALL 4 parallel branches
# have completed and the state is merged. Runs immediately before the
# evidence aggregator.
# ---------------------------------------------------------------------------

_PARALLEL_WALL_START: float = 0.0


def _parallel_start_node(state: ResearchState) -> dict:
    """Thin node that fires just before the fan-out to record wall start."""
    global _PARALLEL_WALL_START
    _PARALLEL_WALL_START = time.perf_counter()
    ts = datetime.now(timezone.utc).isoformat()
    timing_entry = {"node": "_parallel_start", "duration_ms": 0.0, "timestamp": ts}
    return {
        "parallel_section_start_utc": ts,
        "timing_log": [timing_entry],   # delta only
    }


def _parallel_end_node(state: ResearchState) -> dict:
    """Thin node that fires after fan-in to measure wall elapsed time."""
    wall_ms = round((time.perf_counter() - _PARALLEL_WALL_START) * 1000, 1)
    ts = datetime.now(timezone.utc).isoformat()

    # Compute per-branch times for the log
    timing_log = state.get("timing_log", [])
    parallel_nodes = {
        "astrophysical_interpreter", "artefact_checker",
        "novelty_assessor", "context_retriever",
    }
    branch_times = {
        e["node"]: e["duration_ms"]
        for e in timing_log
        if e["node"] in parallel_nodes
    }
    seq_total = sum(branch_times.values())
    speedup = round(seq_total / wall_ms, 2) if wall_ms > 0 else 1.0

    timing_entry = {
        "node": "_parallel_end",
        "duration_ms": wall_ms,
        "timestamp": ts,
        "parallel_wall_ms": wall_ms,
        "sequential_estimate_ms": seq_total,
        "speedup": speedup,
        "branch_times_ms": branch_times,
    }

    print(
        f"\n  ⏱  Parallel section:  wall={wall_ms:.0f} ms "
        f"| sequential estimate={seq_total:.0f} ms "
        f"| speedup={speedup:.2f}x"
    )
    for node_name, dur in branch_times.items():
        print(f"      {node_name}: {dur:.0f} ms")

    return {
        "parallel_section_wall_ms": wall_ms,
        "timing_log": [timing_entry],   # delta only
    }


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def _route_after_aggregation(state: ResearchState) -> str:
    """Both followup and code_executor run after aggregation."""
    return "followup_prioritizer"


def _route_code_executor(state: ResearchState) -> str:
    """Run code_executor if needed, otherwise skip straight to synthesis."""
    return "code_executor" if state.get("needs_code", False) else "synthesis"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    g = StateGraph(ResearchState)

    # Sequential preamble
    g.add_node("supervisor", supervisor_node)
    g.add_node("observation_characterizer", observation_characterizer_node)

    # Timing bookend (start)
    g.add_node("_parallel_start", _parallel_start_node)

    # Parallel branches
    g.add_node("astrophysical_interpreter", astrophysical_interpreter_node)
    g.add_node("artefact_checker", artefact_checker_node)
    g.add_node("novelty_assessor", novelty_assessor_node)
    g.add_node("context_retriever", context_retriever_node)

    # Timing bookend (end / fan-in barrier)
    g.add_node("_parallel_end", _parallel_end_node)

    # Aggregation + follow-up
    g.add_node("evidence_aggregator", evidence_aggregator_node)
    g.add_node("followup_prioritizer", followup_prioritizer_node)
    g.add_node("code_executor", code_executor_node)
    g.add_node("synthesis", synthesis_node)

    # ── Edges ────────────────────────────────────────────────────────────

    g.add_edge(START, "supervisor")
    g.add_edge("supervisor", "observation_characterizer")
    g.add_edge("observation_characterizer", "_parallel_start")

    # Fan-out: all 4 parallel branches fire simultaneously
    g.add_edge("_parallel_start", "astrophysical_interpreter")
    g.add_edge("_parallel_start", "artefact_checker")
    g.add_edge("_parallel_start", "novelty_assessor")
    g.add_edge("_parallel_start", "context_retriever")

    # Fan-in: all 4 must complete before _parallel_end
    g.add_edge("astrophysical_interpreter", "_parallel_end")
    g.add_edge("artefact_checker", "_parallel_end")
    g.add_edge("novelty_assessor", "_parallel_end")
    g.add_edge("context_retriever", "_parallel_end")

    g.add_edge("_parallel_end", "evidence_aggregator")
    g.add_edge("evidence_aggregator", "followup_prioritizer")

    # Conditional: code_executor only if needed
    g.add_conditional_edges(
        "followup_prioritizer",
        _route_code_executor,
        {"code_executor": "code_executor", "synthesis": "synthesis"},
    )
    g.add_edge("code_executor", "synthesis")
    g.add_edge("synthesis", END)

    return g.compile()
