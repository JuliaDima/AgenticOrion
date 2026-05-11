"""
Agentic Orion shared state — flows through the entire LangGraph workflow.

Fields written by parallel branches use Annotated reducers so LangGraph
can merge concurrent updates correctly.

Rules for nodes:
  - errors    → return [] or [error_str], NOT the full accumulated list
  - timing_log → return [entry], NOT state.get("timing_log", []) + [entry]
  - step_count → return 1 (the delta), NOT state.get("step_count", 0) + 1
  - current_step → only sequential nodes write this (parallel branches skip it)
"""

import operator
from typing import Annotated, List, Optional, TypedDict


class ResearchState(TypedDict):
    # ── Run metadata ──────────────────────────────────────────────────────
    run_id: str
    packet_index: int

    # ── Input ─────────────────────────────────────────────────────────────
    observation_packet: dict

    # ── Supervisor outputs ────────────────────────────────────────────────
    mission: str
    primary_modality: str
    needs_code: bool

    # ── Observation characterization ──────────────────────────────────────
    observation_characterization: Optional[dict]

    # ── Parallel branch outputs (each branch writes a unique key) ─────────
    astrophysical_interpretation: Optional[dict]
    artefact_assessment: Optional[dict]
    novelty_rarity_assessment: Optional[dict]
    context_retrieval_results: Optional[dict]

    # ── Parallel section timing ───────────────────────────────────────────
    parallel_section_start_utc: Optional[str]
    parallel_section_wall_ms: Optional[float]

    # ── Evidence aggregation ──────────────────────────────────────────────
    aggregated_evidence: Optional[dict]

    # ── Follow-up + optional code ─────────────────────────────────────────
    followup_recommendations: Optional[dict]
    code_to_execute: Optional[str]
    code_execution_output: Optional[dict]

    # ── Final Agentic Orion report ────────────────────────────────────────────────
    synthesis_report: Optional[str]

    # ── Bookkeeping — Annotated so parallel writes are merged ─────────────
    current_step: str                              # sequential nodes only
    errors: Annotated[List[str], operator.add]     # each node returns []|[msg]
    step_count: Annotated[int, operator.add]       # each node returns 1
    timing_log: Annotated[List[dict], operator.add]  # each node returns [entry]
    token_counts: Annotated[List[dict], operator.add]
    # each node returns [{"node": str, "input_tokens": int,
    #                     "output_tokens": int, "total_tokens": int}]
