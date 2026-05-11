"""
Astrophysical Interpretation Agent (parallel branch 1 of 4).

Asks: "Could this observation be explained by a known astrophysical object or event?"
Produces candidate classes, evidence for/against, and a calibrated confidence.
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
You are the Agentic Orion Astrophysical Interpretation Agent.

Your role: given an astronomical observation packet and its characterization,
assess whether this observation can be explained by known astrophysical phenomena.

Candidate astrophysical classes to consider (non-exhaustive):
- Transients: supernova (Ia, Ib/c, IIP, IIn, SLSN), FBOT, TDE, kilonova, nova
- AGN: AGN flare, changing-look AGN, blazar
- Compact objects: magnetar, pulsar, neutron star merger
- Galaxies: merger, starburst, lensed source, high-z galaxy
- Radio: FRB (repeating / non-repeating), pulsar, RFI masquerading as FRB
- Solar system: asteroid, comet (moving object contamination)
- Other: microlensing, stellar flare, cataclysmic variable

For EACH plausible class, state:
- Evidence in the packet that supports it
- Evidence in the packet that argues against it
- An estimated probability [0,1] (these need NOT sum to 1; they are independent plausibilities)

Respond ONLY via the structured output schema.
"""


class CandidateClass(BaseModel):
    name: str
    probability: float = Field(ge=0.0, le=1.0)
    evidence_for: list[str]
    evidence_against: list[str]


class AstrophysicalInterpretation(BaseModel):
    candidate_classes: list[CandidateClass] = Field(
        description="Plausible astrophysical explanations, each with evidence and probability."
    )
    best_explanation: str = Field(
        description="The single most likely astrophysical explanation given current evidence."
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Overall confidence that this IS an astrophysical event (not an artefact)."
    )
    uncertainty_notes: str = Field(
        description="Key reasons why the astrophysical interpretation remains uncertain."
    )


def astrophysical_interpreter_node(state: ResearchState) -> dict:
    logger = get_logger()
    run_id = state["run_id"]
    t0 = time.perf_counter()
    start_time = datetime.now(timezone.utc).isoformat()

    pkt = state["observation_packet"]
    char = state.get("observation_characterization") or {}

    context = (
        f"Mission: {pkt['mission']}\n"
        f"Summary: {pkt['short_summary']}\n"
        f"Metadata: {json.dumps(pkt['metadata'], indent=2)}\n"
        f"Pipeline labels: {pkt['initial_pipeline_labels']}\n"
        f"Characterization summary: {char.get('one_line_summary', '')}\n"
        f"Salient features: {char.get('salient_features', [])}\n"
        f"Uncertainties: {char.get('uncertainties', [])}\n"
    )

    llm = ChatOpenAI(model=_MODEL, temperature=0)
    structured_llm = llm.with_structured_output(AstrophysicalInterpretation, include_raw=True)

    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=f"Observation packet:\n{context}"),
    ]

    error: str | None = None
    tokens: dict = {"node": "astrophysical_interpreter", "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    interp = AstrophysicalInterpretation(
        candidate_classes=[],
        best_explanation="Undetermined",
        confidence=0.5,
        uncertainty_notes="Fallback — LLM call failed.",
    )
    try:
        raw_result = structured_llm.invoke(messages)
        interp = raw_result["parsed"]
        tokens = extract_tokens("astrophysical_interpreter", raw_result["raw"])
    except Exception as exc:
        error = str(exc)

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    result_dict = interp.model_dump()
    result_dict["branch_duration_ms"] = duration_ms

    logger.log_agent_call(
        run_id=run_id,
        agent_name="astrophysical_interpreter",
        input_summary=f"{pkt['mission'][:60]}",
        output_summary=f"best={interp.best_explanation!r} confidence={interp.confidence:.2f}",
        start_time=start_time,
        duration_ms=duration_ms,
        error=error,
    )
    logger.log_state_transition(run_id, "observation_characterizer", "astrophysical_interpreter", state)

    timing_entry = {"node": "astrophysical_interpreter", "duration_ms": duration_ms, "timestamp": start_time}

    return {
        "astrophysical_interpretation": result_dict,
        "step_count": 1,
        "errors": [error] if error else [],
        "timing_log": [timing_entry],
        "token_counts": [tokens],
    }
