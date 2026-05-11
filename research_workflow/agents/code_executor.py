"""
Optional Code Executor Agent.

Runs only when the evidence aggregator decides quantitative analysis would help.
Generates and executes astronomy-specific Python: light-curve statistics,
brightness-variation metrics, spectral index checks, CSV summaries.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from logging_db import get_logger
from state import ResearchState
from tools import execute_python, extract_tokens

_MODEL = "gpt-4o-mini"

_SYSTEM = """\
You are an astronomical data analysis assistant.

You will be given:
- An observation packet (mission, modality, metadata)
- A description of what data files are available on disk (CSV light curves, JSON metadata)
- The triage context from prior analysis agents
- The supervisor and aggregator code-use decisions
- The follow-up recommendations, which should be treated as the highest-priority
  guide for which quantitative checks to compute

Write a self-contained Python script that:
1. Reads the available data files using only standard library + numpy/pandas/scipy
2. Computes quantitative metrics that would sharpen the triage assessment,
   prioritising metrics that directly support or de-risk the recommended
   follow-up actions:
   - For light curves: peak magnitude, rise/decline rate (mag/day), colour at peak,
     plateau detection, amplitude, time above half-maximum
   - For alert metadata: real/bogus scores, number of detections, alert flags
   - For FRB/radio: DM, burst rate if multiple bursts, scattering time
3. Prints a concise summary of findings, one metric per line
4. Flags any metrics that are unusual or diagnostic (e.g., "FAST_RISE: 2.3 mag/day — unusually fast")

Rules:
- Use only: os, json, csv, math, numpy, pandas, scipy (if needed)
- Do NOT use matplotlib.show() or any GUI calls
- Do NOT hardcode absolute paths — use relative paths relative to the script or
  use the DATA_DIR environment variable if set
- The script must be fully self-contained; print all results
- Output ONLY valid Python — no markdown fences, no explanations
"""


def code_executor_node(state: ResearchState) -> dict:
    logger = get_logger()
    run_id = state["run_id"]
    start_time = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()

    if not state.get("needs_code", False):
        logger.log_agent_call(
            run_id=run_id,
            agent_name="code_executor",
            input_summary="skipped (needs_code=False)",
            output_summary="no-op",
            start_time=start_time,
            duration_ms=0.0,
        )
        timing_entry = {"node": "code_executor", "duration_ms": 0.0, "timestamp": start_time, "skipped": True}
        return {
            "code_to_execute": None,
            "code_execution_output": {"skipped": True, "reason": "Evidence aggregator determined no code needed."},
            "current_step": "code_executor",
            "step_count": 1,
            "errors": [],
            "timing_log": [timing_entry],
            "token_counts": [],
        }

    pkt = state["observation_packet"]
    packet_index = state.get("packet_index", 0)
    agg = state.get("aggregated_evidence") or {}
    supervisor_code = state.get("supervisor_code_decision") or {}
    aggregator_code = state.get("aggregator_code_decision") or {}
    code_agreement = state.get("code_decision_agreement") or {}
    followup = state.get("followup_recommendations") or {}

    # Find available data directory
    packets_root = Path(__file__).parent.parent.parent / "packets"
    pkt_dirs = sorted(packets_root.glob(f"packet_{packet_index:02d}_*"))
    if not pkt_dirs and 13 <= packet_index <= 24:
        # BLIND packets are stored as packet_01_BLIND … packet_12_BLIND
        orig = packet_index - 12
        pkt_dirs = sorted(packets_root.glob(f"packet_{orig:02d}_BLIND"))
    data_dir = (pkt_dirs[0] / "data") if pkt_dirs else None

    available_files = ""
    if data_dir and data_dir.exists():
        files = list(data_dir.iterdir())
        available_files = "\n".join(
            f"  {f.name} ({f.stat().st_size // 1024} kB)" for f in files
        )
    else:
        available_files = "No local data files found."

    unresolved = agg.get("unresolved_questions", [])
    top_hyp = [h.get("hypothesis") for h in agg.get("ranked_hypotheses", [])[:3]]
    priority_actions = [
        {
            "action": item.get("action"),
            "instrument_or_method": item.get("instrument_or_method"),
            "scientific_rationale": item.get("scientific_rationale"),
            "expected_outcome": item.get("expected_outcome"),
        }
        for item in followup.get("priority_actions", [])[:5]
    ]

    analysis_goal = (
        f"Observation: {pkt['mission']} — {pkt['short_summary'][:120]}\n"
        f"Triage verdict: {agg.get('triage_verdict', 'UNKNOWN')}\n"
        f"Top hypotheses: {top_hyp}\n"
        f"Unresolved questions: {unresolved}\n"
        f"Supervisor code decision: {json.dumps(supervisor_code, indent=2)}\n"
        f"Aggregator code decision: {json.dumps(aggregator_code, indent=2)}\n"
        f"Supervisor/aggregator code-use agreement: {json.dumps(code_agreement, indent=2)}\n"
        f"Follow-up recommendations to prioritise: {json.dumps(priority_actions, indent=2)}\n"
        f"Follow-up value summary: {followup.get('scientific_value_summary', 'N/A')}\n"
        f"Time sensitivity: {followup.get('time_sensitivity_note', 'N/A')}\n"
        f"Available data files in: {str(data_dir) if data_dir else 'N/A'}\n"
        f"{available_files}\n\n"
        f"Compute metrics that would help distinguish between the top hypotheses, "
        f"but give strongest priority to metrics that directly test the follow-up "
        f"recommendations above. Also print whether the supervisor and aggregator "
        f"agreed on code use."
    )

    llm = ChatOpenAI(model=_MODEL, temperature=0)
    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=analysis_goal),
    ]

    error: str | None = None
    tokens: dict = {"node": "code_executor", "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    code = ""
    code_results: dict = {}

    try:
        llm_start = datetime.now(timezone.utc).isoformat()
        llm_t0 = time.perf_counter()
        response = llm.invoke(messages)
        llm_dur = round((time.perf_counter() - llm_t0) * 1000, 1)
        tokens = extract_tokens("code_executor", response)
        code = response.content.strip()
        if code.startswith("```"):
            lines = code.split("\n")
            code = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        logger.log_tool_call(
            run_id=run_id,
            agent_name="code_executor",
            tool_name="llm_code_generation",
            input_data={"analysis_goal": analysis_goal[:300]},
            output_data={"code_preview": code[:300]},
            start_time=llm_start,
            duration_ms=llm_dur,
        )

        # Inject DATA_DIR if we know where the data is
        if data_dir and data_dir.exists():
            code = f"import os\nos.environ.setdefault('DATA_DIR', {str(data_dir)!r})\n\n" + code

        exec_start = datetime.now(timezone.utc).isoformat()
        exec_t0 = time.perf_counter()
        code_results = execute_python(code)
        exec_dur = round((time.perf_counter() - exec_t0) * 1000, 1)

        logger.log_tool_call(
            run_id=run_id,
            agent_name="code_executor",
            tool_name="execute_python",
            input_data={"code_preview": code[:300]},
            output_data=code_results,
            start_time=exec_start,
            duration_ms=exec_dur,
            error=code_results.get("stderr") or None,
        )
    except Exception as exc:
        error = str(exc)
        code_results = {"error": error}

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    logger.log_agent_call(
        run_id=run_id,
        agent_name="code_executor",
        input_summary=analysis_goal[:200],
        output_summary=str(code_results.get("stdout", ""))[:200] or str(code_results)[:200],
        start_time=start_time,
        duration_ms=duration_ms,
        error=error,
    )
    logger.log_state_transition(run_id, "followup_prioritizer", "code_executor", state)

    timing_entry = {"node": "code_executor", "duration_ms": duration_ms, "timestamp": start_time}

    return {
        "code_to_execute": code,
        "code_execution_output": code_results,
        "current_step": "code_executor",
        "step_count": 1,
        "errors": [error] if error else [],
        "timing_log": [timing_entry],
        "token_counts": [tokens],
    }
