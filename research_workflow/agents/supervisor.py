"""
Supervisor agent — identifies mission, primary modality, and whether a
lightweight code-analysis step would add value for this observation packet.
"""

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
You are the Agentic Orion workflow supervisor for scientific triage of astronomical observations.

Given an observation packet, produce a structured routing decision:
1. Confirm the mission and primary observation modality.
2. Decide whether a lightweight Python code step (e.g. light-curve statistics,
   image metrics, CSV summary) would add measurable value to the analysis.
   Set needs_code_execution=True ONLY when a CSV light curve or tabular data
   is present and quantitative metrics would strengthen the triage assessment.
3. Provide a brief rationale.

Respond ONLY via the structured output schema — no free text.
"""


class SupervisorDecision(BaseModel):
    mission: str = Field(description="Mission name extracted from the packet.")
    primary_modality: str = Field(
        description="Primary observation modality: alert | light_curve | image_cutout | spectrum | catalogue_entry"
    )
    needs_code_execution: bool = Field(
        description="True only when tabular/CSV data is present and quantitative analysis adds value."
    )
    reasoning: str = Field(description="One-sentence rationale for the routing decision.")


def supervisor_node(state: ResearchState) -> dict:
    logger = get_logger()
    run_id = state["run_id"]
    t0 = time.perf_counter()
    start_time = datetime.now(timezone.utc).isoformat()

    pkt = state["observation_packet"]
    pkt_summary = (
        f"Mission: {pkt['mission']}\n"
        f"Experiment type: {pkt['experiment_type']}\n"
        f"Modalities: {pkt['modality']}\n"
        f"Pipeline labels: {pkt['initial_pipeline_labels']}\n"
        f"Summary: {pkt['short_summary']}\n"
        f"Data files: {pkt.get('data_files_on_disk', pkt.get('query_hints', {}).keys())}"
    )

    llm = ChatOpenAI(model=_MODEL, temperature=0)
    structured_llm = llm.with_structured_output(SupervisorDecision, include_raw=True)

    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=f"Observation packet:\n{pkt_summary}"),
    ]

    error: str | None = None
    tokens: dict = {"node": "supervisor", "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    decision = SupervisorDecision(
        mission=pkt["mission"],
        primary_modality=pkt["modality"][0] if pkt["modality"] else "unknown",
        needs_code_execution="light_curve" in pkt["modality"] or "alert" in pkt["modality"],
        reasoning="Fallback routing.",
    )
    try:
        raw_result = structured_llm.invoke(messages)
        decision = raw_result["parsed"]
        tokens = extract_tokens("supervisor", raw_result["raw"])
    except Exception as exc:
        error = str(exc)

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)

    logger.log_agent_call(
        run_id=run_id,
        agent_name="supervisor",
        input_summary=f"packet mission={pkt['mission']!r}",
        output_summary=f"mission={decision.mission!r} modality={decision.primary_modality!r} needs_code={decision.needs_code_execution}",
        start_time=start_time,
        duration_ms=duration_ms,
        error=error,
    )
    logger.log_state_transition(run_id, "START", "supervisor", state)

    timing_entry = {"node": "supervisor", "duration_ms": duration_ms, "timestamp": start_time}

    return {
        "mission": decision.mission,
        "primary_modality": decision.primary_modality,
        "needs_code": decision.needs_code_execution,
        "current_step": "supervisor",
        "step_count": 1,
        "errors": [error] if error else [],
        "timing_log": [timing_entry],
        "token_counts": [tokens],
    }
