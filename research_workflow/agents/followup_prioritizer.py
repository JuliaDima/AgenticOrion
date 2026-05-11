"""
Follow-Up Prioritization Agent.

Given the aggregated evidence and triage verdict, recommends the most
scientifically discriminating follow-up observations.
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

_MODEL = "gpt-4o-mini"

_SYSTEM = """\
You are the OrionSpectrum Follow-Up Prioritization Agent.

Given a triage verdict and ranked hypotheses from the evidence aggregation step,
recommend the most scientifically valuable follow-up actions.

Principles:
- Prioritise actions that would most efficiently discriminate between the top competing hypotheses.
- Consider telescope/instrument availability, time-sensitivity, and feasibility.
- If the triage verdict is REJECT_ARTEFACT or REJECT_CONTROL, the follow-up list should be
  short (e.g., "confirm artefact origin with quality check X", then stop).
- Rank each action by scientific impact (discriminating power) × urgency.
- Be specific: name the instrument, observation mode, and expected outcome.

Available telescope/instrument options (examples):
- Spectroscopy: VLT/X-Shooter, Gemini/GMOS, Keck/LRIS, NOT/ALFOSC
- Multi-band imaging: ZTF (g/r/i), DECam, HST/ACS
- Radio: EVN, VLBI, MeerKAT, VLA
- X-ray: Swift/XRT, Chandra, XMM-Newton
- Archive cross-match: SIMBAD, NED, Gaia, 2MASS, SDSS

Respond ONLY via the structured output schema.
"""


class FollowUpAction(BaseModel):
    action: str = Field(description="Specific follow-up observation or check.")
    instrument_or_method: str
    scientific_rationale: str = Field(description="Which hypothesis this discriminates and how.")
    urgency: str = Field(description="One of: IMMEDIATE (hours) | URGENT (days) | NORMAL (weeks) | LOW")
    expected_outcome: str


class FollowUpPlan(BaseModel):
    priority_actions: list[FollowUpAction] = Field(
        description="Ordered list of recommended follow-up actions (most important first)."
    )
    recommended_facilities: list[str]
    time_sensitivity_note: str = Field(
        description="Overall note on how rapidly follow-up is needed and why."
    )
    scientific_value_summary: str = Field(
        description="What would be gained scientifically from executing this follow-up plan."
    )
    stop_here_if: str = Field(
        description="Condition under which the follow-up plan should be abandoned (e.g., 'if image quality check confirms subtraction artefact')."
    )


def followup_prioritizer_node(state: ResearchState) -> dict:
    logger = get_logger()
    run_id = state["run_id"]
    t0 = time.perf_counter()
    start_time = datetime.now(timezone.utc).isoformat()

    pkt = state["observation_packet"]
    agg = state.get("aggregated_evidence") or {}
    novel = state.get("novelty_rarity_assessment") or {}

    hypotheses_block = json.dumps(
        [
            {
                "hypothesis": h.get("hypothesis"),
                "confidence": h.get("updated_confidence"),
                "key_discriminant": h.get("key_discriminant"),
            }
            for h in agg.get("ranked_hypotheses", [])[:5]
        ],
        indent=2,
    )

    context = (
        f"Mission: {pkt['mission']}\n"
        f"Summary: {pkt['short_summary']}\n"
        f"Triage verdict: {agg.get('triage_verdict', 'UNKNOWN')}\n"
        f"Overall interest score: {agg.get('overall_interest_score', 'N/A')}\n"
        f"Follow-up value score: {novel.get('followup_value_score', 'N/A')}\n"
        f"Time-sensitive: {novel.get('time_sensitive', False)}\n\n"
        f"Ranked hypotheses:\n{hypotheses_block}\n\n"
        f"Unresolved questions:\n{json.dumps(agg.get('unresolved_questions', []), indent=2)}\n\n"
        f"Disagreement between branches:\n{json.dumps(agg.get('disagreement_points', []), indent=2)}"
    )

    llm = ChatOpenAI(model=_MODEL, temperature=0)
    structured_llm = llm.with_structured_output(FollowUpPlan, include_raw=True)

    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=context),
    ]

    error: str | None = None
    tokens: dict = {"node": "followup_prioritizer", "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    plan = FollowUpPlan(
        priority_actions=[],
        recommended_facilities=[],
        time_sensitivity_note="Undetermined.",
        scientific_value_summary="Undetermined.",
        stop_here_if="N/A",
    )
    try:
        raw_result = structured_llm.invoke(messages)
        plan = raw_result["parsed"]
        tokens = extract_tokens("followup_prioritizer", raw_result["raw"])
    except Exception as exc:
        error = str(exc)

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    result_dict = plan.model_dump()

    logger.log_agent_call(
        run_id=run_id,
        agent_name="followup_prioritizer",
        input_summary=f"verdict={agg.get('triage_verdict', '?')} interest={agg.get('overall_interest_score', '?')}",
        output_summary=f"{len(plan.priority_actions)} actions recommended",
        start_time=start_time,
        duration_ms=duration_ms,
        error=error,
    )
    logger.log_state_transition(run_id, "evidence_aggregator", "followup_prioritizer", state)

    timing_entry = {"node": "followup_prioritizer", "duration_ms": duration_ms, "timestamp": start_time}

    return {
        "followup_recommendations": result_dict,
        "current_step": "followup_prioritizer",
        "step_count": 1,
        "errors": [error] if error else [],
        "timing_log": [timing_entry],
        "token_counts": [tokens],
    }
