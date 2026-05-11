"""
Instrument / Artefact Check Agent (parallel branch 2 of 4).

Asks: "Could this arise from the telescope, detector, calibration,
image subtraction, or data-pipeline effects rather than a real source?"
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
You are the OrionSpectrum Instrument/Artefact Check Agent.

Your role: given an observation packet, assess whether the signal could arise
from non-astrophysical, instrumental, or pipeline causes.

Artefact modes to consider:
- Optical/NIR: diffraction spike, persistence, saturation bleed, cosmic ray,
  bad pixel cluster, PSF wing, scattered light (wisps/ghosts), hot pixel
- Difference-imaging: subtraction residual, dipole from PSF mismatch,
  template contamination, astrometric misalignment
- Photometric pipeline: deblending failure, aperture bleed from bright neighbour
- Radio: RFI, gain glitch, digitiser saturation, baseline ripple
- Data quality: single-epoch detection (ndet=1), low real/bogus score,
  observation near CCD edge, incomplete calibration

For each plausible artefact mode:
- State the evidence that supports it
- State the evidence that argues against it
- Estimate a probability [0,1]

Also list recommended quality checks (e.g., "inspect difference stamp for dipole").

Respond ONLY via the structured output schema.
"""


class ArtefactMode(BaseModel):
    name: str
    probability: float = Field(ge=0.0, le=1.0)
    evidence_for: list[str]
    evidence_against: list[str]


class ArtefactAssessment(BaseModel):
    possible_artefact_modes: list[ArtefactMode]
    most_likely_non_astrophysical: str = Field(
        description="The single most plausible non-astrophysical explanation."
    )
    artefact_probability: float = Field(
        ge=0.0, le=1.0,
        description="Overall probability that the signal is non-astrophysical."
    )
    evidence_for_artefact: list[str]
    evidence_against_artefact: list[str]
    recommended_quality_checks: list[str]


def artefact_checker_node(state: ResearchState) -> dict:
    logger = get_logger()
    run_id = state["run_id"]
    t0 = time.perf_counter()
    start_time = datetime.now(timezone.utc).isoformat()

    pkt = state["observation_packet"]
    char = state.get("observation_characterization") or {}

    context = (
        f"Mission: {pkt['mission']}\n"
        f"Modalities: {pkt['modality']}\n"
        f"Summary: {pkt['short_summary']}\n"
        f"Metadata: {json.dumps(pkt['metadata'], indent=2)}\n"
        f"Pipeline labels: {pkt['initial_pipeline_labels']}\n"
        f"Characterization: {char.get('one_line_summary', '')}\n"
        f"Data quality notes: {char.get('data_quality_notes', [])}\n"
        f"Salient features: {char.get('salient_features', [])}\n"
    )

    llm = ChatOpenAI(model=_MODEL, temperature=0)
    structured_llm = llm.with_structured_output(ArtefactAssessment, include_raw=True)

    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=f"Observation packet:\n{context}"),
    ]

    error: str | None = None
    tokens: dict = {"node": "artefact_checker", "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    assess = ArtefactAssessment(
        possible_artefact_modes=[],
        most_likely_non_astrophysical="Undetermined",
        artefact_probability=0.1,
        evidence_for_artefact=[],
        evidence_against_artefact=[],
        recommended_quality_checks=[],
    )
    try:
        raw_result = structured_llm.invoke(messages)
        assess = raw_result["parsed"]
        tokens = extract_tokens("artefact_checker", raw_result["raw"])
    except Exception as exc:
        error = str(exc)

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    result_dict = assess.model_dump()
    result_dict["branch_duration_ms"] = duration_ms

    logger.log_agent_call(
        run_id=run_id,
        agent_name="artefact_checker",
        input_summary=f"{pkt['mission'][:60]}",
        output_summary=f"artefact_prob={assess.artefact_probability:.2f} most_likely={assess.most_likely_non_astrophysical!r}",
        start_time=start_time,
        duration_ms=duration_ms,
        error=error,
    )
    logger.log_state_transition(run_id, "observation_characterizer", "artefact_checker", state)

    timing_entry = {"node": "artefact_checker", "duration_ms": duration_ms, "timestamp": start_time}

    return {
        "artefact_assessment": result_dict,
        "step_count": 1,
        "errors": [error] if error else [],
        "timing_log": [timing_entry],
        "token_counts": [tokens],
    }
