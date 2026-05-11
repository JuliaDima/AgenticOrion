"""
Novelty / Rarity Assessment Agent (parallel branch 3 of 4).

Asks: "Is this observation rare, scientifically uncertain, out-of-distribution,
or unusually valuable for follow-up?"
Produces scores and a justification for scientific attention.
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
You are the OrionSpectrum Novelty/Rarity Assessment Agent.

Your role: given an observation packet, assess its scientific attention-worthiness
across four dimensions. Score each dimension on [0, 1] where 1 is highest.

Dimensions:
1. rarity_score — How rare is this type of object/event in a typical survey?
   (1 = extremely rare, occurs <1 per year in ZTF/Rubin-scale surveys)
2. novelty_score — How much does this challenge or extend existing models?
   (1 = fully OOD / unexplained by current astrophysics)
3. uncertainty_score — How uncertain is the current classification?
   (1 = completely ambiguous between multiple hypotheses)
4. followup_value_score — How scientifically valuable would follow-up observations be?
   (1 = time-sensitive, high-impact, would strongly constrain models)

Also provide:
- A qualitative justification for the overall scientific interest level
- Any notes on out-of-distribution features ("this light-curve rise time is unusually fast")
- Whether time-sensitivity is relevant (ephemeral transient vs. static source)

Calibration anchors:
- A standard SN Ia or SN IIP in a nearby galaxy → rarity 0.1, novelty 0.1
- A repeating FRB with known host → rarity 0.6, novelty 0.5
- An FBOT like AT2018cow at discovery → rarity 0.9, novelty 0.8, followup 0.95
- A diffraction artefact → rarity 0.05, novelty 0.0, followup 0.0

Respond ONLY via the structured output schema.
"""


class NoveltyRarityAssessment(BaseModel):
    rarity_score: float = Field(ge=0.0, le=1.0)
    novelty_score: float = Field(ge=0.0, le=1.0)
    uncertainty_score: float = Field(ge=0.0, le=1.0)
    followup_value_score: float = Field(ge=0.0, le=1.0)
    overall_interest_score: float = Field(
        ge=0.0, le=1.0,
        description="Composite score: recommended threshold for triage attention is >0.5."
    )
    reason_for_scientific_interest: str = Field(
        description="Qualitative justification for the overall interest level."
    )
    ood_notes: str = Field(
        description="Specific out-of-distribution features that stand out, if any."
    )
    time_sensitive: bool = Field(
        description="True if follow-up must happen within days to weeks."
    )


def novelty_assessor_node(state: ResearchState) -> dict:
    logger = get_logger()
    run_id = state["run_id"]
    t0 = time.perf_counter()
    start_time = datetime.now(timezone.utc).isoformat()

    pkt = state["observation_packet"]
    char = state.get("observation_characterization") or {}

    context = (
        f"Mission: {pkt['mission']}\n"
        f"Experiment type: {pkt['experiment_type']}\n"
        f"Summary: {pkt['short_summary']}\n"
        f"Metadata: {json.dumps(pkt['metadata'], indent=2)}\n"
        f"Pipeline labels: {pkt['initial_pipeline_labels']}\n"
        f"Salient features: {char.get('salient_features', [])}\n"
        f"Missing evidence: {char.get('missing_evidence', [])}\n"
        f"Uncertainties: {char.get('uncertainties', [])}\n"
    )

    llm = ChatOpenAI(model=_MODEL, temperature=0)
    structured_llm = llm.with_structured_output(NoveltyRarityAssessment, include_raw=True)

    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=f"Observation packet:\n{context}"),
    ]

    error: str | None = None
    tokens: dict = {"node": "novelty_assessor", "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    assessment = NoveltyRarityAssessment(
        rarity_score=0.5,
        novelty_score=0.5,
        uncertainty_score=0.5,
        followup_value_score=0.5,
        overall_interest_score=0.5,
        reason_for_scientific_interest="Undetermined — LLM call failed.",
        ood_notes="",
        time_sensitive=False,
    )
    try:
        raw_result = structured_llm.invoke(messages)
        assessment = raw_result["parsed"]
        tokens = extract_tokens("novelty_assessor", raw_result["raw"])
    except Exception as exc:
        error = str(exc)

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    result_dict = assessment.model_dump()
    result_dict["branch_duration_ms"] = duration_ms

    logger.log_agent_call(
        run_id=run_id,
        agent_name="novelty_assessor",
        input_summary=f"{pkt['mission'][:60]}",
        output_summary=(
            f"rarity={assessment.rarity_score:.2f} novelty={assessment.novelty_score:.2f} "
            f"followup={assessment.followup_value_score:.2f} overall={assessment.overall_interest_score:.2f}"
        ),
        start_time=start_time,
        duration_ms=duration_ms,
        error=error,
    )
    logger.log_state_transition(run_id, "observation_characterizer", "novelty_assessor", state)

    timing_entry = {"node": "novelty_assessor", "duration_ms": duration_ms, "timestamp": start_time}

    return {
        "novelty_rarity_assessment": result_dict,
        "step_count": 1,
        "errors": [error] if error else [],
        "timing_log": [timing_entry],
        "token_counts": [tokens],
    }
