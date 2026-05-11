"""
Evidence Aggregation / Debate Agent.

Receives all 4 parallel branch outputs, compares them, identifies agreement
and disagreement, ranks hypotheses, and decides whether code analysis is needed.

This is the scientific heart of Agentic Orion: it performs the "debate" step where
competing interpretations are weighed against each other.
"""

import json
import time
from datetime import datetime, timezone

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from logging_db import get_logger
from tools import extract_tokens
from state import ResearchState

_MODEL = "gpt-4o"

_SYSTEM = """\
You are the Agentic Orion Evidence Aggregation and Debate Agent.

You receive the outputs of four parallel scientific analysis branches:
1. Astrophysical Interpretation — what astrophysical object could this be?
2. Instrument/Artefact Check — could this be a non-astrophysical artefact?
3. Novelty/Rarity Assessment — how scientifically interesting is this?
4. Context Retrieval — what do the literature and catalogues say?

Your role: perform a structured scientific debate across these outputs and produce:
- A ranked list of hypotheses with updated confidences
- An explicit list of what the 4 branches AGREE on
- An explicit list of where they DISAGREE and why the disagreement matters
- Updated confidence estimates (may differ from individual branch estimates)
- Unresolved scientific questions that the current data cannot answer
- An overall scientific interest score [0,1] for this observation
- A verdict on whether lightweight code analysis would sharpen the interpretation

Scientific debate rules:
- If the artefact branch assigns high artefact_probability, penalise astrophysical confidence.
- If novelty scores are very low AND artefact probability is high, the object is likely a control/reject.
- Disagreement between branches is scientifically valuable — surface it explicitly.
- Do NOT homogenise. If branch A says 0.8 confidence SN Ia and branch B disagrees, say so.

Respond ONLY via the structured output schema.
"""


class RankedHypothesis(BaseModel):
    hypothesis: str
    updated_confidence: float = Field(ge=0.0, le=1.0)
    supporting_branches: list[str]
    opposing_branches: list[str]
    key_discriminant: str = Field(
        description="The single observation that would most definitively confirm or reject this hypothesis."
    )


class AggregatedEvidence(BaseModel):
    ranked_hypotheses: list[RankedHypothesis] = Field(
        description="All plausible hypotheses, ranked by updated confidence (descending)."
    )
    agreement_points: list[str] = Field(
        description="Points where all or most branches agree."
    )
    disagreement_points: list[str] = Field(
        description="Points of genuine scientific disagreement between branches."
    )
    confidence_updates: list[str] = Field(
        description="Brief notes (one per branch) on how each branch influenced final confidence estimates."
    )
    unresolved_questions: list[str] = Field(
        description="Scientific questions the current data cannot answer."
    )
    overall_interest_score: float = Field(
        ge=0.0, le=1.0,
        description="Composite scientific attention score. >0.5 = warrants follow-up action."
    )
    triage_verdict: str = Field(
        description="One of: HIGH_PRIORITY | MEDIUM_PRIORITY | LOW_PRIORITY | REJECT_ARTEFACT | REJECT_CONTROL"
    )
    needs_code_analysis: bool = Field(
        description="True if quantitative metrics from available data would sharpen the assessment."
    )


def evidence_aggregator_node(state: ResearchState) -> dict:
    logger = get_logger()
    run_id = state["run_id"]
    t0 = time.perf_counter()
    start_time = datetime.now(timezone.utc).isoformat()

    pkt = state["observation_packet"]

    astro = state.get("astrophysical_interpretation") or {}
    artef = state.get("artefact_assessment") or {}
    novel = state.get("novelty_rarity_assessment") or {}
    ctx   = state.get("context_retrieval_results") or {}

    # Record parallel section wall time
    timing_log = state.get("timing_log", [])
    parallel_nodes = {"astrophysical_interpreter", "artefact_checker", "novelty_assessor", "context_retriever"}
    parallel_entries = [e for e in timing_log if e["node"] in parallel_nodes]
    parallel_durations = [e["duration_ms"] for e in parallel_entries]
    parallel_wall_ms = state.get("parallel_section_wall_ms")

    branches_block = f"""
=== BRANCH 1: Astrophysical Interpretation ===
Best explanation: {astro.get('best_explanation', 'N/A')}
Confidence (astrophysical): {astro.get('confidence', 'N/A')}
Candidate classes: {json.dumps([c.get('name') for c in astro.get('candidate_classes', [])], indent=0)}
Uncertainty: {astro.get('uncertainty_notes', '')}
Branch duration: {astro.get('branch_duration_ms', 'N/A')} ms

=== BRANCH 2: Instrument/Artefact Check ===
Artefact probability: {artef.get('artefact_probability', 'N/A')}
Most likely non-astrophysical: {artef.get('most_likely_non_astrophysical', 'N/A')}
Evidence for artefact: {artef.get('evidence_for_artefact', [])}
Recommended checks: {artef.get('recommended_quality_checks', [])}
Branch duration: {artef.get('branch_duration_ms', 'N/A')} ms

=== BRANCH 3: Novelty/Rarity Assessment ===
Rarity: {novel.get('rarity_score', 'N/A')}  Novelty: {novel.get('novelty_score', 'N/A')}
Uncertainty: {novel.get('uncertainty_score', 'N/A')}  Follow-up value: {novel.get('followup_value_score', 'N/A')}
Overall interest: {novel.get('overall_interest_score', 'N/A')}
Reason: {novel.get('reason_for_scientific_interest', '')}
OOD notes: {novel.get('ood_notes', '')}
Branch duration: {novel.get('branch_duration_ms', 'N/A')} ms

=== BRANCH 4: Context Retrieval ===
Papers retrieved: {len(ctx.get('raw_arxiv_papers', []))}
Catalogue context: {ctx.get('relevant_catalogue_context', '')}
Mission notes: {ctx.get('mission_instrument_notes', '')}
Known failure modes: {ctx.get('known_failure_modes', [])}
Branch duration: {ctx.get('branch_duration_ms', 'N/A')} ms
"""

    if parallel_durations:
        seq_total = sum(parallel_durations)
        wall = parallel_wall_ms or max(parallel_durations)
        speedup = seq_total / wall if wall > 0 else 1.0
        branches_block += (
            f"\n=== PARALLEL TIMING ===\n"
            f"Sequential total would be: {seq_total:.0f} ms\n"
            f"Actual parallel wall time: {wall:.0f} ms\n"
            f"Parallel speedup: {speedup:.2f}x\n"
        )

    context = (
        f"Mission: {pkt['mission']}\n"
        f"Experiment type: {pkt['experiment_type']}\n"
        f"Summary: {pkt['short_summary']}\n"
        f"Pipeline labels: {pkt['initial_pipeline_labels']}\n\n"
        f"PARALLEL BRANCH OUTPUTS:\n{branches_block}"
    )

    llm = ChatOpenAI(model=_MODEL, temperature=0)
    structured_llm = llm.with_structured_output(AggregatedEvidence, include_raw=True)

    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=context),
    ]

    error: str | None = None
    tokens: dict = {"node": "evidence_aggregator", "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    agg = AggregatedEvidence(
        ranked_hypotheses=[],
        agreement_points=[],
        disagreement_points=[],
        confidence_updates=[],
        unresolved_questions=[],
        overall_interest_score=novel.get("overall_interest_score", 0.5),
        triage_verdict="MEDIUM_PRIORITY",
        needs_code_analysis=state.get("needs_code", False),
    )
    try:
        raw_result = structured_llm.invoke(messages)
        agg = raw_result["parsed"]
        tokens = extract_tokens("evidence_aggregator", raw_result["raw"])
    except Exception as exc:
        error = str(exc)

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    result_dict = agg.model_dump()

    logger.log_agent_call(
        run_id=run_id,
        agent_name="evidence_aggregator",
        input_summary=f"4 branches from {pkt['mission'][:50]}",
        output_summary=(
            f"verdict={agg.triage_verdict} "
            f"interest={agg.overall_interest_score:.2f} "
            f"top_hypothesis={agg.ranked_hypotheses[0].hypothesis if agg.ranked_hypotheses else 'none'}"
        ),
        start_time=start_time,
        duration_ms=duration_ms,
        error=error,
    )
    logger.log_state_transition(run_id, "parallel_branches", "evidence_aggregator", state)

    timing_entry = {"node": "evidence_aggregator", "duration_ms": duration_ms, "timestamp": start_time}
    supervisor_code_decision = state.get("supervisor_code_decision") or {}
    supervisor_needs_code = supervisor_code_decision.get("needs_code", state.get("needs_code", False))
    code_decision_agreement = {
        "supervisor_needs_code": bool(supervisor_needs_code),
        "aggregator_needs_code": bool(agg.needs_code_analysis),
        "agree": bool(supervisor_needs_code) == bool(agg.needs_code_analysis),
        "supervisor_reasoning": supervisor_code_decision.get("reasoning", ""),
        "aggregator_reasoning": "Aggregator judged whether quantitative metrics from available data would sharpen the assessment.",
    }

    return {
        "aggregated_evidence": result_dict,
        "needs_code": agg.needs_code_analysis,
        "aggregator_code_decision": {
            "needs_code": agg.needs_code_analysis,
            "triage_verdict": agg.triage_verdict,
            "unresolved_questions": result_dict.get("unresolved_questions", []),
        },
        "code_decision_agreement": code_decision_agreement,
        "current_step": "evidence_aggregator",
        "step_count": 1,
        "errors": [error] if error else [],
        "timing_log": [timing_entry],
        "token_counts": [tokens],
    }
