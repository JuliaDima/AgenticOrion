"""
Observation Characterization Agent — summarises the packet, identifies modality,
extracts salient features, lists missing evidence, and exposes uncertainties.
This runs before the parallel branch fan-out.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from logging_db import get_logger
from state import ResearchState
from tools import extract_tokens, load_packet_data

_MODEL = "gpt-4o-mini"

_SYSTEM = """\
You are the OrionSpectrum Observation Characterization Agent.

Your role: given an astronomical observation packet, produce a structured
characterization that the downstream parallel triage agents will use.

Focus on:
- Summarising ALL provided data (photometry, metadata, pipeline scores, catalogue rows).
- Identifying the primary modality and any secondary modalities.
- Extracting salient numerical and qualitative features.
- Listing what evidence is MISSING that would disambiguate the object.
- Cataloguing known uncertainties and ambiguities.

Be concise, precise, and factual. Do not speculate.
"""


class ObservationCharacterization(BaseModel):
    modality_summary: str = Field(
        description="Brief description of the observation type and instrument context."
    )
    salient_features: list[str] = Field(
        description="Key numerical and qualitative features extracted from the packet."
    )
    missing_evidence: list[str] = Field(
        description="Evidence not present in this packet that would help classification."
    )
    uncertainties: list[str] = Field(
        description="Known ambiguities or uncertainties in the current data."
    )
    data_quality_notes: list[str] = Field(
        description="Any data quality flags, pipeline warnings, or caveats."
    )
    one_line_summary: str = Field(
        description="A single sentence describing what this observation is and why it might be interesting."
    )


def observation_characterizer_node(state: ResearchState) -> dict:
    logger = get_logger()
    run_id = state["run_id"]
    t0 = time.perf_counter()
    start_time = datetime.now(timezone.utc).isoformat()

    pkt = state["observation_packet"]
    packet_index = state.get("packet_index", 0)

    # Load any data files already on disk for this packet
    data_context = load_packet_data(packet_index)

    pkt_text = (
        f"Mission: {pkt['mission']}\n"
        f"Experiment type: {pkt['experiment_type']}\n"
        f"Object/Event IDs: {json.dumps(pkt['object_or_event_id'], indent=2)}\n"
        f"Modalities: {pkt['modality']}\n"
        f"Summary: {pkt['short_summary']}\n"
        f"Metadata: {json.dumps(pkt['metadata'], indent=2)}\n"
        f"Pipeline labels: {pkt['initial_pipeline_labels']}\n"
    )

    if data_context:
        pkt_text += f"\nData files on disk:\n{data_context}"

    llm = ChatOpenAI(model=_MODEL, temperature=0)
    structured_llm = llm.with_structured_output(ObservationCharacterization, include_raw=True)

    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=f"Observation packet:\n{pkt_text}"),
    ]

    error: str | None = None
    tokens: dict = {"node": "observation_characterizer", "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    char = ObservationCharacterization(
        modality_summary=f"{pkt['modality'][0]} from {pkt['mission']}",
        salient_features=pkt["initial_pipeline_labels"],
        missing_evidence=[],
        uncertainties=[],
        data_quality_notes=[],
        one_line_summary=pkt["short_summary"][:200],
    )
    try:
        raw_result = structured_llm.invoke(messages)
        char = raw_result["parsed"]
        tokens = extract_tokens("observation_characterizer", raw_result["raw"])
    except Exception as exc:
        error = str(exc)

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)

    result_dict = char.model_dump()
    result_dict["duration_ms"] = duration_ms

    logger.log_agent_call(
        run_id=run_id,
        agent_name="observation_characterizer",
        input_summary=f"packet_{packet_index:02d} {pkt['mission']}",
        output_summary=char.one_line_summary,
        start_time=start_time,
        duration_ms=duration_ms,
        error=error,
    )
    logger.log_state_transition(run_id, "supervisor", "observation_characterizer", state)

    timing_entry = {"node": "observation_characterizer", "duration_ms": duration_ms, "timestamp": start_time}

    return {
        "observation_characterization": result_dict,
        "current_step": "observation_characterizer",
        "step_count": 1,
        "errors": [error] if error else [],
        "timing_log": [timing_entry],
        "token_counts": [tokens],
    }
