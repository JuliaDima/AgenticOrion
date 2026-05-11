"""
Agentic Orion — entry point.

Runs one or all observation packets through the Agentic Orion multi-agent triage workflow.

Usage
-----
    python main.py --packet 1          # AT2018cow (FBOT)
    python main.py --packet 5          # ALeRCE broker triage
    python main.py --all               # all 12 packets
    python main.py --experiment TRIAGE # run only TRIAGE packets
    python main.py --experiment RETRO
    python main.py --experiment CTRL

Each run logs to research_workflow.db and prints the final Agentic Orion report.
"""

import argparse
import sys
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import os
sys.path.insert(0, str(Path(__file__).parent))

# Import OBSERVATION_PACKETS from the data_fetching module
sys.path.insert(0, str(Path(__file__).parent.parent / "data_fetching"))
from observation_packets_registry import OBSERVATION_PACKETS

from graph import build_graph
from logging_db import get_logger
from state import ResearchState


# ---------------------------------------------------------------------------
# Mission coverage summary (answers: "how much data can we cover?")
# ---------------------------------------------------------------------------

MISSION_DATA_SCALE = {
    "Rubin/LSST":  {"nightly_alerts": "~10 million", "nightly_TB": "~20 TB",  "survey_total": "~60 PB"},
    "JWST":        {"nightly_alerts": "N/A",          "nightly_GB": "~60 GB", "survey_total": "~100 TB (mission lifetime)"},
    "Euclid":      {"nightly_alerts": "N/A",          "nightly_GB": "~100 GB compressed", "survey_total": "tens of PB"},
    "CHIME/FRB":   {"nightly_alerts": "~100s bursts", "raw_rate":   "13.11 Tb/s internal", "catalog": "Catalog 1 = 535 FRBs"},
}

TOKEN_PRICING_MODEL = "gpt-4o-mini production estimate"
TOKEN_INPUT_USD_PER_1M = 0.15
TOKEN_OUTPUT_USD_PER_1M = 0.60


def _token_usage_summary(state: ResearchState) -> dict:
    token_counts = state.get("token_counts") or []
    input_tokens = sum(int(tc.get("input_tokens") or 0) for tc in token_counts)
    output_tokens = sum(int(tc.get("output_tokens") or 0) for tc in token_counts)
    estimated_cost_usd = (
        input_tokens * TOKEN_INPUT_USD_PER_1M
        + output_tokens * TOKEN_OUTPUT_USD_PER_1M
    ) / 1_000_000
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "estimated_cost_usd": estimated_cost_usd,
        "pricing_model": TOKEN_PRICING_MODEL,
        "per_agent": token_counts,
    }


def print_coverage_summary() -> None:
    print("\n" + "═" * 72)
    print("ORION — DATA COVERAGE SUMMARY")
    print("═" * 72)
    print(
        "\nOrion operates DOWNSTREAM of mission pipelines.\n"
        "It receives compact observation packets (~KB each), not raw data.\n"
    )
    print("Mission data scales (raw):")
    for mission, stats in MISSION_DATA_SCALE.items():
        print(f"  {mission}:")
        for k, v in stats.items():
            print(f"    {k}: {v}")

    print(
        "\nOrion triage throughput estimate:\n"
        "  ~30–90s per packet (wall time with parallel branches, GPT-4 class LLM)\n"
        "  With 4 parallel agent instances: ~4x throughput\n"
        "  Rubin LSST @ 10M alerts/night → need ~2800/s; Agentic Orion targets human-expert triage\n"
        "  of the top-N anomalies (broker pre-filtered to ~100–10,000/night)\n"
        "  At 60s/packet × 4 workers: ~240 packets/hour = ~5,760/day\n"
        "  Sufficient to triage ALeRCE/Fink anomaly-flagged subsets, all JWST daily\n"
        "  downlinks, all CHIME detected FRBs, and Euclid lens candidates."
    )
    print("═" * 72 + "\n")


# ---------------------------------------------------------------------------
# Single packet run
# ---------------------------------------------------------------------------

def run_packet(packet_index: int, verbose: bool = True) -> ResearchState:
    """Run one observation packet through the full Agentic Orion workflow."""
    if packet_index < 1 or packet_index > len(OBSERVATION_PACKETS):
        raise ValueError(f"packet_index must be 1–{len(OBSERVATION_PACKETS)}")

    pkt = OBSERVATION_PACKETS[packet_index - 1]
    run_id = str(uuid.uuid4())
    logger = get_logger()
    logger.log_run_start(run_id, f"packet_{packet_index:02d}_{pkt['mission']}")

    if verbose:
        print(f"\n{'─' * 72}")
        print(f"  Packet {packet_index:02d}/{len(OBSERVATION_PACKETS)}")
        print(f"  Mission : {pkt['mission']}")
        print(f"  Experiment: {pkt['experiment_type']}")
        print(f"  Labels  : {pkt['initial_pipeline_labels']}")
        print(f"  Summary : {pkt['short_summary'][:100]}...")
        print(f"  Run ID  : {run_id}")
        print(f"{'─' * 72}\n")

    initial_state: ResearchState = {
        "run_id": run_id,
        "packet_index": packet_index,
        "observation_packet": pkt,
        "mission": pkt["mission"],
        "primary_modality": pkt["modality"][0] if pkt["modality"] else "unknown",
        "needs_code": False,
        "observation_characterization": None,
        "astrophysical_interpretation": None,
        "artefact_assessment": None,
        "novelty_rarity_assessment": None,
        "context_retrieval_results": None,
        "parallel_section_start_utc": None,
        "parallel_section_wall_ms": None,
        "aggregated_evidence": None,
        "followup_recommendations": None,
        "code_to_execute": None,
        "code_execution_output": None,
        "synthesis_report": None,
        "current_step": "init",
        "errors": [],        # Annotated[List[str], operator.add] — start empty
        "step_count": 0,     # Annotated[int, operator.add] — start at 0
        "timing_log": [],    # Annotated[List[dict], operator.add] — start empty
        "token_counts": [],  # Annotated[List[dict], operator.add] — start empty
    }

    graph = build_graph()
    t0 = time.perf_counter()
    status = "success"
    final_state: ResearchState = initial_state

    try:
        final_state = graph.invoke(initial_state)
    except Exception as exc:
        status = "error"
        print(f"[error] Workflow failed: {exc}", file=sys.stderr)
        final_state = {**initial_state, "errors": [str(exc)]}

    wall_ms = round((time.perf_counter() - t0) * 1000, 1)
    if final_state.get("errors"):
        status = "partial"
    logger.log_run_end(run_id, status, wall_ms)
    token_summary = _token_usage_summary(final_state)
    logger.log_run_metrics(
        run_id=run_id,
        input_tokens=token_summary["input_tokens"],
        output_tokens=token_summary["output_tokens"],
        estimated_cost_usd=token_summary["estimated_cost_usd"],
        pricing_model=token_summary["pricing_model"],
        per_agent=token_summary["per_agent"],
    )
    logger.log_final_state(run_id, final_state, wall_ms)

    if verbose:
        _print_report(final_state, wall_ms)

    return final_state


def _print_report(state: ResearchState, total_wall_ms: float) -> None:
    pkt = state.get("observation_packet", {})
    obj_ids = pkt.get("object_or_event_id", {})
    obj_id = (
        obj_ids.get("TNS_name") or obj_ids.get("Euclid_id") or
        obj_ids.get("common_name") or obj_ids.get("survey_id") or
        obj_ids.get("artefact_name") or "Unknown"
    )
    agg = state.get("aggregated_evidence") or {}
    novel = state.get("novelty_rarity_assessment") or {}

    print("\n" + "═" * 72)
    print(f"ORION REPORT — {obj_id}")
    print("═" * 72)
    print(state.get("synthesis_report") or "[no report generated]")

    print("\n" + "─" * 72)
    print("TIMING SUMMARY")
    print("─" * 72)
    timing_log = state.get("timing_log") or []
    for entry in timing_log:
        skip = " [skipped]" if entry.get("skipped") else ""
        speedup = f"  speedup={entry['speedup']:.2f}x" if "speedup" in entry else ""
        print(f"  {entry['node']:<35} {entry['duration_ms']:>8.0f} ms{skip}{speedup}")
    print(f"  {'TOTAL WALL TIME':<35} {total_wall_ms:>8.0f} ms")

    print("\n" + "─" * 72)
    print("TOKEN USAGE")
    print("─" * 72)
    token_counts = state.get("token_counts") or []
    total_in = total_out = 0
    for tc in token_counts:
        node_label = tc.get("node", "?")
        inp  = tc.get("input_tokens",  0)
        out  = tc.get("output_tokens", 0)
        tot  = tc.get("total_tokens",  0) or inp + out
        total_in  += inp
        total_out += out
        print(f"  {node_label:<35}  in={inp:>6}  out={out:>5}  total={tot:>6}")
    grand_total = total_in + total_out
    print(f"  {'TOTAL':<35}  in={total_in:>6}  out={total_out:>5}  total={grand_total:>6}")
    if grand_total > 0:
        cost_usd = (
            total_in * TOKEN_INPUT_USD_PER_1M
            + total_out * TOKEN_OUTPUT_USD_PER_1M
        ) / 1_000_000
        cost_10k = cost_usd * 10_000
        print(f"  Estimated cost (gpt-4o-mini, production): ~${cost_usd:.5f} USD/packet")
        print(f"  At 10,000 packets/night (Rubin anomaly stream): ~${cost_10k:.2f} USD/night")
        print()
        print("  Local open-weight model equivalence (agency-deployable, no data egress):")
        # Throughput assumes A100 80GB. Llama-3-8B: ~2500 tok/s, Mistral-7B: ~2200 tok/s
        # At grand_total tokens/packet:
        tok_per_sec_llama  = 2500
        tok_per_sec_mistral = 2200
        t_llama   = grand_total / tok_per_sec_llama
        t_mistral = grand_total / tok_per_sec_mistral
        # A100 cloud spot: ~$1.50/hr; on-prem amortised ~$0.30/hr
        gpu_cloud_usd_per_hr  = 1.50
        gpu_onprem_usd_per_hr = 0.30
        cost_cloud  = (t_llama  / 3600) * gpu_cloud_usd_per_hr
        cost_onprem = (t_llama  / 3600) * gpu_onprem_usd_per_hr
        print(f"    Llama-3-8B  (~2,500 tok/s on 1×A100): {t_llama:.1f}s/packet")
        print(f"    Mistral-7B  (~2,200 tok/s on 1×A100): {t_mistral:.1f}s/packet")
        print(f"    GPU cost/packet — cloud spot A100 (~$1.50/hr): ~${cost_cloud:.6f}")
        print(f"    GPU cost/packet — on-prem A100   (~$0.30/hr):  ~${cost_onprem:.6f}")
        print(f"    At 10,000 packets/night: ~${cost_cloud*10000:.2f} cloud / ~${cost_onprem*10000:.2f} on-prem")

    print("\n" + "─" * 72)
    print("QUICK VERDICT")
    print("─" * 72)
    print(f"  Triage verdict   : {agg.get('triage_verdict', 'UNKNOWN')}")
    print(f"  Interest score   : {agg.get('overall_interest_score', 'N/A')}")
    print(f"  Novelty score    : {novel.get('novelty_score', 'N/A')}")
    print(f"  Follow-up value  : {novel.get('followup_value_score', 'N/A')}")
    print(f"  Steps completed  : {state['step_count']}")
    if state.get("errors"):
        print(f"  Errors           : {state['errors']}")

    print("\n" + "─" * 72)
    print(f"  Run ID: {state['run_id']}")
    print(f"  View trace: python trace_viewer.py {state['run_id']}")
    print("═" * 72 + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agentic Orion — automated scientific triage for astronomical observation packets"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--packet", type=int, metavar="N", help="Run packet N (1–12)")
    group.add_argument("--all", action="store_true", help="Run all 12 packets")
    group.add_argument(
        "--experiment",
        choices=["RETRO", "TRIAGE", "CTRL"],
        help="Run only packets of this experiment type",
    )
    parser.add_argument("--coverage", action="store_true", help="Print data coverage summary and exit")
    args = parser.parse_args()

    if args.coverage:
        print_coverage_summary()
        return

    if args.all:
        indices = list(range(1, len(OBSERVATION_PACKETS) + 1))
    elif args.experiment:
        indices = [
            i + 1
            for i, p in enumerate(OBSERVATION_PACKETS)
            if p["experiment_type"] == args.experiment
        ]
        print(f"\nRunning {len(indices)} {args.experiment} packets: {indices}")
    elif args.packet:
        indices = [args.packet]
    else:
        # Default: run packet 1 (AT2018cow — the canonical FBOT demo)
        print("No packet specified — running packet 1 (AT2018cow, FBOT demo).")
        print("Use --packet N (1–12), --all, --experiment TRIAGE|RETRO|CTRL, or --coverage")
        indices = [1]

    print_coverage_summary()

    results = []
    for idx in indices:
        result = run_packet(idx)
        results.append(result)

    if len(results) > 1:
        print("\n" + "═" * 72)
        print("BATCH SUMMARY")
        print("═" * 72)
        for r in results:
            pkt = r.get("observation_packet", {})
            agg = r.get("aggregated_evidence") or {}
            timing = r.get("timing_log") or []
            total_ms = sum(e["duration_ms"] for e in timing)
            print(
                f"  P{r.get('packet_index', '?'):02}  {pkt.get('mission', '')[:40]:<40}  "
                f"verdict={agg.get('triage_verdict', '?'):<20}  "
                f"interest={agg.get('overall_interest_score', '?')!s:<6}  "
                f"wall={total_ms:.0f}ms"
            )
        print("═" * 72)


if __name__ == "__main__":
    main()
