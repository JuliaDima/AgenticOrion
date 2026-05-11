"""
Evaluation suite: runs 5 pre-defined scientific queries through the workflow
and logs success/failure with latency to both SQLite and a summary table.

Usage:
    python eval.py
"""

import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

sys.path.insert(0, str(Path(__file__).parent))

from main import run_query

EVAL_QUERIES: list[dict] = [
    {
        "id": "eval_01",
        "query": "What are recent advances in transformer architectures for protein structure prediction?",
        "expect_papers": True,
        "expect_report": True,
    },
    {
        "id": "eval_02",
        "query": "How does quantum computing compare to classical algorithms for combinatorial optimisation?",
        "expect_papers": True,
        "expect_report": True,
    },
    {
        "id": "eval_03",
        "query": "What are the latest findings on CRISPR-Cas9 off-target effects and safety improvements?",
        "expect_papers": True,
        "expect_report": True,
    },
    {
        "id": "eval_04",
        "query": "What is the current state of room-temperature superconductivity research?",
        "expect_papers": True,
        "expect_report": True,
    },
    {
        "id": "eval_05",
        "query": "How effective is reinforcement learning from human feedback (RLHF) for language model alignment?",
        "expect_papers": True,
        "expect_report": True,
    },
]

_SEP = "─" * 72
_WIDE = "═" * 72


def _check(state: dict, spec: dict) -> tuple[bool, list[str]]:
    failures = []
    if spec["expect_papers"] and not state.get("literature_results"):
        failures.append("no literature_results")
    if spec["expect_report"] and not state.get("synthesis_report"):
        failures.append("no synthesis_report")
    if state.get("errors"):
        failures.append(f"errors={state['errors']}")
    return (len(failures) == 0, failures)


def run_eval() -> None:
    results = []

    print(f"\n{'EVALUATION SUITE':^72}")
    print(_WIDE)
    print(f"  {len(EVAL_QUERIES)} queries | model: claude-sonnet-4-20250514")
    print(_WIDE + "\n")

    for spec in EVAL_QUERIES:
        print(f"[{spec['id']}] {spec['query'][:65]}")
        t0 = time.perf_counter()
        state = {}
        exc_msg = None
        try:
            state = run_query(spec["query"])
        except Exception as exc:
            exc_msg = str(exc)

        latency_ms = round((time.perf_counter() - t0) * 1000, 1)

        if exc_msg:
            passed, failures = False, [f"exception: {exc_msg}"]
        else:
            passed, failures = _check(state, spec)

        icon = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {icon}  |  {latency_ms:.0f} ms  |  run_id={state.get('run_id', '—')}")
        if failures:
            for f in failures:
                print(f"         → {f}")
        print()

        results.append(
            {
                "eval_id": spec["id"],
                "query": spec["query"],
                "run_id": state.get("run_id"),
                "passed": passed,
                "latency_ms": latency_ms,
                "failures": failures,
                "papers_found": len(state.get("literature_results", [])),
                "has_code_results": bool(state.get("code_results")),
                "report_chars": len(state.get("synthesis_report") or ""),
            }
        )

    # ── Summary table ────────────────────────────────────────────────────
    passed_count = sum(1 for r in results if r["passed"])
    avg_latency = sum(r["latency_ms"] for r in results) / len(results)

    print(_WIDE)
    print(f"  RESULTS  {passed_count}/{len(results)} passed   avg latency {avg_latency:.0f} ms")
    print(_SEP)
    print(f"  {'ID':<10} {'PASS':^6} {'LATENCY':>10}  {'PAPERS':>7}  {'REPORT':>8}")
    print(_SEP)
    for r in results:
        icon = "✓" if r["passed"] else "✗"
        print(
            f"  {r['eval_id']:<10} {icon:^6} {r['latency_ms']:>9.0f}ms  "
            f"{r['papers_found']:>7}  {r['report_chars']:>7}c"
        )
    print(_WIDE)

    # Save JSON summary
    out_path = Path(__file__).parent / "eval_results.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\n  Detailed results written to: {out_path}")
    print(f"  View any trace: python trace_viewer.py <run_id>\n")


if __name__ == "__main__":
    run_eval()
