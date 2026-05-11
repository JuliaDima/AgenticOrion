"""
Benchmark Agentic Orion against a deterministic mock single-agent baseline.

The benchmark is intentionally offline and repeatable. It uses actual logged
multi-agent traces from SQLite, then estimates a single generalist baseline that
has to perform the same characterization work serially, without independent
branch debate or specialist cross-checks.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
DB_PATH = ROOT / "research_workflow.db"
PACKETS_ROOT = REPO_ROOT / "packets"
WEB_ROOT = ROOT / "web"
STATIC_ROOT = WEB_ROOT / "static-data"
PLOTS_ROOT = STATIC_ROOT / "plots"
RESULTS_PATH = ROOT / "benchmark_results.json"

PARALLEL_NODES = {
    "astrophysical_interpreter",
    "artefact_checker",
    "novelty_assessor",
    "context_retriever",
}


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _packet_index_from_query(query: str | None) -> int | None:
    if not query:
        return None
    match = re.search(r"packet_(\d+)", query)
    return int(match.group(1)) if match else None


def _read_packet(index: int | None) -> dict[str, Any]:
    if index is None:
        return {}
    for path in sorted(PACKETS_ROOT.glob(f"packet_{index:02d}_*/packet.json")):
        return _json_loads(path.read_text(encoding="utf-8"), {})
    return {}


def _read_manifest() -> list[dict[str, Any]]:
    manifest = PACKETS_ROOT / "manifest.json"
    return _json_loads(manifest.read_text(encoding="utf-8"), []) if manifest.exists() else []


def _object_id(packet: dict[str, Any]) -> str:
    ids = packet.get("object_or_event_id", {}) or {}
    for key in ("TNS_name", "Euclid_id", "common_name", "survey_id", "artefact_name", "canonical_name", "IAU_coord_name"):
        if ids.get(key):
            return str(ids[key])
    return "Unknown"


def _clip(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _count_stdout_metrics(state: dict[str, Any]) -> int:
    output = state.get("code_execution_output") or {}
    if output.get("skipped"):
        return 0
    stdout = str(output.get("stdout") or "")
    return len([line for line in stdout.splitlines() if line.strip()])


def _tokens_from_state(state: dict[str, Any]) -> dict[str, Any]:
    token_counts = state.get("token_counts") or []
    input_tokens = sum(int(item.get("input_tokens") or 0) for item in token_counts)
    output_tokens = sum(int(item.get("output_tokens") or 0) for item in token_counts)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "per_agent": token_counts,
    }


def _tokens_from_row(row: dict[str, Any] | None, state: dict[str, Any]) -> dict[str, Any]:
    if row and row.get("total_tokens") is not None:
        return {
            "input_tokens": int(row.get("input_tokens") or 0),
            "output_tokens": int(row.get("output_tokens") or 0),
            "total_tokens": int(row.get("total_tokens") or 0),
            "per_agent": _json_loads(row.get("per_agent_json"), []),
        }
    return _tokens_from_state(state)


def _load_all_runs() -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    """
    Returns (latest_per_packet, all_per_packet).

    latest_per_packet: one item per packet index (most recent successful run).
    all_per_packet: maps packet_index -> list of all successful run items,
                    used for computing within-packet σ across repeated runs.
    """
    if not DB_PATH.exists():
        return [], {}
    with _conn() as conn:
        runs = [dict(row) for row in conn.execute(
            "SELECT * FROM runs WHERE status='success' ORDER BY start_time DESC"
        ).fetchall()]
        final_rows = {
            row["run_id"]: dict(row)
            for row in conn.execute("SELECT * FROM final_states").fetchall()
        }
        metric_rows = {
            row["run_id"]: dict(row)
            for row in conn.execute("SELECT * FROM run_metrics").fetchall()
        }

    latest: dict[int, dict[str, Any]] = {}
    all_by_packet: dict[int, list[dict[str, Any]]] = {}
    for run in runs:
        state_row = final_rows.get(run["run_id"])
        state = _json_loads(state_row.get("state_json") if state_row else None, {})
        packet_index = state.get("packet_index") or _packet_index_from_query(run.get("query"))
        if not packet_index:
            continue
        item = {
            "run": run,
            "state": state,
            "state_row": state_row,
            "metrics_row": metric_rows.get(run["run_id"]),
        }
        idx = int(packet_index)
        all_by_packet.setdefault(idx, []).append(item)
        if idx not in latest:
            latest[idx] = item
    return [latest[key] for key in sorted(latest)], all_by_packet


def _within_packet_std(all_by_packet: dict[int, list[dict[str, Any]]], metric_fn) -> float:
    """
    Compute the mean within-packet σ for a given metric function.

    For each packet that has ≥2 runs, compute the std dev of the metric
    across those runs, then average those σ values.  Returns 0.0 when no
    packet has repeated runs (no error bars shown).
    """
    per_packet_stds = []
    for items in all_by_packet.values():
        if len(items) < 2:
            continue
        values = []
        for item in items:
            try:
                v = metric_fn(item)
                if isinstance(v, (int, float)) and math.isfinite(v):
                    values.append(v)
            except Exception:
                pass
        if len(values) >= 2:
            per_packet_stds.append(_std(values))
    return _avg(per_packet_stds) if per_packet_stds else 0.0


def _timing_by_node(state: dict[str, Any]) -> dict[str, float]:
    timings: dict[str, float] = {}
    for item in state.get("timing_log") or []:
        node = item.get("node")
        if not node or str(node).startswith("_"):
            continue
        timings[str(node)] = float(item.get("duration_ms") or 0.0)
    return timings


def _expected_interest(packet: dict[str, Any]) -> float:
    experiment = str(packet.get("experiment_type") or "").upper()
    labels = {str(label).lower() for label in packet.get("initial_pipeline_labels") or []}
    score = {"RETRO": 0.78, "TRIAGE": 0.68, "CTRL": 0.12}.get(experiment, 0.5)
    if any("high_z" in label or "fbot" in label or "strong_lens" in label for label in labels):
        score += 0.08
    if any("follow_up" in label or "triage_priority" in label or "novelty" in label for label in labels):
        score += 0.06
    if any("reject" in label or "bogus" in label or "artefact" in label or "rfi" in label or "ctrl" == label for label in labels):
        score -= 0.08
    return round(_clip(score), 3)


def _mock_single_interest(packet: dict[str, Any]) -> float:
    experiment = str(packet.get("experiment_type") or "").upper()
    labels = [str(label).lower() for label in packet.get("initial_pipeline_labels") or []]
    modalities = packet.get("modality") or []
    score = {"RETRO": 0.66, "TRIAGE": 0.56, "CTRL": 0.26}.get(experiment, 0.48)
    for label in labels:
        if any(term in label for term in ("high", "priority", "novelty", "follow", "fbot", "lens")):
            score += 0.04
        if any(term in label for term in ("ambiguous", "unconfirmed", "candidate")):
            score += 0.02
        if any(term in label for term in ("ctrl", "reject", "bogus", "artefact", "rfi", "excluded")):
            score -= 0.05
    if len(modalities) >= 3:
        score += 0.03
    return round(_clip(score), 3)


def _verdict_from_interest(score: float, packet: dict[str, Any]) -> str:
    labels = " ".join(str(label).lower() for label in packet.get("initial_pipeline_labels") or [])
    if any(term in labels for term in ("artefact", "bogus", "rfi", "reject", "excluded")):
        return "REJECT_ARTEFACT"
    if "ctrl" in labels and score < 0.35:
        return "REJECT_CONTROL"
    if score >= 0.76:
        return "HIGH_PRIORITY"
    if score >= 0.46:
        return "MEDIUM_PRIORITY"
    return "LOW_PRIORITY"


def _priority_class(verdict: str | None) -> str:
    verdict = str(verdict or "").upper()
    if verdict.startswith("REJECT"):
        return "reject"
    if verdict in {"HIGH_PRIORITY", "MEDIUM_PRIORITY"}:
        return "priority"
    return "low"


def _expected_priority(packet: dict[str, Any]) -> str:
    experiment = str(packet.get("experiment_type") or "").upper()
    if experiment == "CTRL":
        return "reject"
    return "priority"


def _coverage_metrics(state: dict[str, Any]) -> dict[str, Any]:
    agg = state.get("aggregated_evidence") or {}
    fup = state.get("followup_recommendations") or {}
    ctx = state.get("context_retrieval_results") or {}
    channels = [
        bool(state.get("observation_characterization")),
        bool(state.get("astrophysical_interpretation")),
        bool(state.get("artefact_assessment")),
        bool(state.get("novelty_rarity_assessment")),
        bool(ctx),
        bool(agg),
        bool(fup.get("priority_actions")),
        bool(state.get("code_execution_output")) and not (state.get("code_execution_output") or {}).get("skipped"),
    ]
    debate_points = (
        len(agg.get("agreement_points") or [])
        + len(agg.get("disagreement_points") or [])
        + len(agg.get("unresolved_questions") or [])
    )
    hypotheses = len(agg.get("ranked_hypotheses") or [])
    followups = len(fup.get("priority_actions") or [])
    code_metrics = _count_stdout_metrics(state)
    context_items = len(ctx.get("raw_arxiv_papers") or [])
    score = (
        0.35 * (sum(channels) / len(channels))
        + 0.20 * _clip(hypotheses / 4)
        + 0.20 * _clip(debate_points / 8)
        + 0.15 * _clip(followups / 4)
        + 0.10 * _clip((code_metrics + context_items) / 8)
    )
    return {
        "evidence_channels": sum(channels),
        "hypotheses": hypotheses,
        "debate_points": debate_points,
        "followup_actions": followups,
        "code_metric_lines": code_metrics,
        "context_items": context_items,
        "characterization_score": round(_clip(score), 3),
    }


def _mock_single_quality(packet: dict[str, Any], expected_interest: float) -> dict[str, Any]:
    labels = packet.get("initial_pipeline_labels") or []
    files = packet.get("data_files_on_disk") or []
    modalities = packet.get("modality") or []
    evidence_channels = 3
    if len(modalities) >= 3:
        evidence_channels += 1
    if files:
        evidence_channels += 1
    debate_points = 1 if any("ambiguous" in str(label).lower() for label in labels) else 0
    hypotheses = 2 if expected_interest > 0.45 else 1
    followups = 1 if expected_interest > 0.45 else 0
    code_metrics = 1 if any(str(name).endswith((".csv", ".json")) for name in files) else 0
    score = (
        0.35 * _clip(evidence_channels / 8)
        + 0.20 * _clip(hypotheses / 4)
        + 0.20 * _clip(debate_points / 8)
        + 0.15 * _clip(followups / 4)
        + 0.10 * _clip(code_metrics / 4)
    )
    return {
        "evidence_channels": evidence_channels,
        "hypotheses": hypotheses,
        "debate_points": debate_points,
        "followup_actions": followups,
        "code_metric_lines": code_metrics,
        "context_items": 0,
        "characterization_score": round(_clip(score), 3),
    }


def _single_wall_estimate_ms(timing: dict[str, float], multi_wall_ms: float) -> float:
    serial_same_work = sum(timing.values())
    if serial_same_work <= 0:
        return multi_wall_ms * 1.8
    # A single generalist avoids some orchestration overhead, but cannot run
    # the four specialist checks in parallel.
    return max(multi_wall_ms * 1.15, serial_same_work * 0.88)


def _single_token_estimate(packet: dict[str, Any], multi_tokens: int, quality: dict[str, Any]) -> int:
    files = packet.get("data_files_on_disk") or []
    modalities = packet.get("modality") or []
    labels = packet.get("initial_pipeline_labels") or []
    packet_complexity = 1600 + 260 * len(files) + 220 * len(modalities) + 90 * len(labels)
    quality_budget = 750 * quality["hypotheses"] + 420 * quality["followup_actions"] + 280 * quality["code_metric_lines"]
    estimate = packet_complexity + quality_budget
    if multi_tokens:
        estimate = max(estimate, multi_tokens * 0.55)
        estimate = min(estimate, multi_tokens * 0.82)
    return int(round(estimate))


def _make_record(item: dict[str, Any]) -> dict[str, Any]:
    run = item["run"]
    state = item["state"]
    packet_index = int(state.get("packet_index") or _packet_index_from_query(run.get("query")) or 0)
    packet = state.get("observation_packet") or _read_packet(packet_index)
    metrics = _tokens_from_row(item.get("metrics_row"), state)
    timing = _timing_by_node(state)
    agg = state.get("aggregated_evidence") or {}
    novel = state.get("novelty_rarity_assessment") or {}
    expected_interest = _expected_interest(packet)
    multi_interest = float(agg.get("overall_interest_score") or novel.get("overall_interest_score") or expected_interest)
    multi_verdict = agg.get("triage_verdict") or _verdict_from_interest(multi_interest, packet)
    multi_wall_ms = float(run.get("duration_ms") or item.get("state_row", {}).get("total_wall_ms") or sum(timing.values()) or 0)
    multi_tokens = int(metrics.get("total_tokens") or 0)
    multi_quality = _coverage_metrics(state)

    single_interest = _mock_single_interest(packet)
    single_verdict = _verdict_from_interest(single_interest, packet)
    single_quality = _mock_single_quality(packet, expected_interest)
    single_wall_ms = _single_wall_estimate_ms(timing, multi_wall_ms)
    single_tokens = _single_token_estimate(packet, multi_tokens, single_quality)
    expected_priority = _expected_priority(packet)

    return {
        "packet_index": packet_index,
        "object_id": _object_id(packet),
        "mission": packet.get("mission"),
        "experiment_type": packet.get("experiment_type"),
        "expected": {
            "interest_score": expected_interest,
            "priority_class": expected_priority,
        },
        "multi_agent": {
            "run_id": run.get("run_id"),
            "wall_ms": round(multi_wall_ms, 1),
            "total_tokens": multi_tokens,
            "interest_score": round(multi_interest, 3),
            "triage_verdict": multi_verdict,
            "priority_class": _priority_class(multi_verdict),
            "interest_abs_error": round(abs(multi_interest - expected_interest), 3),
            **multi_quality,
        },
        "single_agent_mock": {
            "wall_ms": round(single_wall_ms, 1),
            "total_tokens": single_tokens,
            "interest_score": single_interest,
            "triage_verdict": single_verdict,
            "priority_class": _priority_class(single_verdict),
            "interest_abs_error": round(abs(single_interest - expected_interest), 3),
            **single_quality,
        },
        "delta": {
            "wall_speedup": round(single_wall_ms / multi_wall_ms, 2) if multi_wall_ms else None,
            "token_ratio_multi_over_single": round(multi_tokens / single_tokens, 2) if single_tokens else None,
            "characterization_gain": round(multi_quality["characterization_score"] - single_quality["characterization_score"], 3),
        },
    }


def _avg(values: list[float]) -> float:
    values = [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    values = [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))


def _build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(records)
    multi = [r["multi_agent"] for r in records]
    single = [r["single_agent_mock"] for r in records]
    multi_accuracy = _avg([1.0 if m["priority_class"] == r["expected"]["priority_class"] else 0.0 for r, m in zip(records, multi)])
    single_accuracy = _avg([1.0 if s["priority_class"] == r["expected"]["priority_class"] else 0.0 for r, s in zip(records, single)])
    multi_wall = _avg([m["wall_ms"] for m in multi])
    single_wall = _avg([s["wall_ms"] for s in single])
    multi_tokens = _avg([m["total_tokens"] for m in multi])
    single_tokens = _avg([s["total_tokens"] for s in single])
    return {
        "objects_compared": n,
        "multi_agent": {
            "avg_wall_ms": round(multi_wall, 1),
            "avg_total_tokens": round(multi_tokens, 1),
            "avg_interest_abs_error": round(_avg([m["interest_abs_error"] for m in multi]), 3),
            "priority_accuracy": round(multi_accuracy, 3),
            "avg_characterization_score": round(_avg([m["characterization_score"] for m in multi]), 3),
            "avg_evidence_channels": round(_avg([m["evidence_channels"] for m in multi]), 2),
            "avg_debate_points": round(_avg([m["debate_points"] for m in multi]), 2),
        },
        "single_agent_mock": {
            "avg_wall_ms": round(single_wall, 1),
            "avg_total_tokens": round(single_tokens, 1),
            "avg_interest_abs_error": round(_avg([s["interest_abs_error"] for s in single]), 3),
            "priority_accuracy": round(single_accuracy, 3),
            "avg_characterization_score": round(_avg([s["characterization_score"] for s in single]), 3),
            "avg_evidence_channels": round(_avg([s["evidence_channels"] for s in single]), 2),
            "avg_debate_points": round(_avg([s["debate_points"] for s in single]), 2),
        },
        "comparison": {
            "avg_speedup_multi_vs_single": round(single_wall / multi_wall, 2) if multi_wall else None,
            "token_ratio_multi_over_single": round(multi_tokens / single_tokens, 2) if single_tokens else None,
            "characterization_gain": round(
                _avg([m["characterization_score"] for m in multi])
                - _avg([s["characterization_score"] for s in single]),
                3,
            ),
            "interest_error_reduction": round(
                _avg([s["interest_abs_error"] for s in single])
                - _avg([m["interest_abs_error"] for m in multi]),
                3,
            ),
        },
    }


def _svg_bar_chart(
    title: str,
    groups: list[dict[str, Any]],
    y_label: str,
    path: Path,
    errors: list[list[float]] | None = None,
) -> None:
    width, height = 980, 560
    margin_l, margin_r, margin_t, margin_b = 112, 30, 74, 116
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b
    all_values = [value for group in groups for value in group["values"]]
    all_sigmas = [s for row in (errors or []) for s in row]
    max_v = max((all_values[i] + (all_sigmas[i] if errors else 0) for i in range(len(all_values))), default=1)
    scale = plot_h / max_v if max_v else 1
    group_w = plot_w / max(1, len(groups))
    bar_w = min(74, group_w / 3.4)
    cap_w = bar_w * 0.3
    colors = ["#176c72", "#c74732"]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img">',
        "<style>text{font-family:Inter,Arial,sans-serif;fill:#17202a}.muted{fill:#66717e}.grid{stroke:#d9dee5}.axis{stroke:#17202a}.bartext{font-size:20px;font-weight:700}.title{font-size:36px;font-weight:800}</style>",
        f'<rect width="{width}" height="{height}" fill="#fff"/>',
        f'<text class="title" x="{margin_l}" y="48">{title}</text>',
    ]
    for i in range(5):
        y = margin_t + plot_h - (plot_h / 4) * i
        value = max_v * i / 4
        parts.append(f'<line class="grid" x1="{margin_l}" y1="{y:.1f}" x2="{width-margin_r}" y2="{y:.1f}"/>')
        parts.append(f'<text class="muted" x="10" y="{y+7:.1f}" font-size="21">{value:.1f}</text>')
    parts.append(f'<line class="axis" x1="{margin_l}" y1="{margin_t+plot_h}" x2="{width-margin_r}" y2="{margin_t+plot_h}"/>')
    for idx, group in enumerate(groups):
        cx = margin_l + group_w * idx + group_w / 2
        for j, value in enumerate(group["values"]):
            x = cx + (j - 0.5) * (bar_w + 10) - bar_w / 2
            h = value * scale
            y = margin_t + plot_h - h
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" rx="6" fill="{colors[j]}"/>')
            parts.append(f'<text class="bartext" x="{x + bar_w/2:.1f}" y="{y - 8:.1f}" text-anchor="middle">{value:.2f}</text>')
            if errors and (sigma := errors[idx][j]) > 0:
                ex = x + bar_w / 2
                ey_top = max(margin_t, y - sigma * scale)
                ey_bot = min(margin_t + plot_h, y + sigma * scale)
                parts.append(f'<line x1="{ex:.1f}" y1="{ey_top:.1f}" x2="{ex:.1f}" y2="{ey_bot:.1f}" stroke="#17202a" stroke-width="2.5"/>')
                parts.append(f'<line x1="{ex-cap_w:.1f}" y1="{ey_top:.1f}" x2="{ex+cap_w:.1f}" y2="{ey_top:.1f}" stroke="#17202a" stroke-width="2.5"/>')
                parts.append(f'<line x1="{ex-cap_w:.1f}" y1="{ey_bot:.1f}" x2="{ex+cap_w:.1f}" y2="{ey_bot:.1f}" stroke="#17202a" stroke-width="2.5"/>')
        parts.append(f'<text class="muted" x="{cx:.1f}" y="{height-62}" text-anchor="middle" font-size="21">{group["label"]}</text>')
    parts.append(f'<text class="muted" x="{width/2}" y="{height-18}" text-anchor="middle" font-size="21">{y_label}</text>')
    parts.append(f'<rect x="{width-300}" y="22" width="18" height="18" fill="{colors[0]}"/><text x="{width-272}" y="36" font-size="21">Multi-agent</text>')
    parts.append(f'<rect x="{width-148}" y="22" width="18" height="18" fill="{colors[1]}"/><text x="{width-120}" y="36" font-size="21">Single mock</text>')
    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts), encoding="utf-8")


def _write_plots(
    payload: dict[str, Any],
    all_by_packet: dict[int, list[dict[str, Any]]],
    plots_root: Path = PLOTS_ROOT,
) -> dict[str, str]:
    summary = payload["summary"]
    records = payload["records"]
    plots_root.mkdir(parents=True, exist_ok=True)
    speed_path = plots_root / "benchmark_speed_tokens.svg"
    quality_path = plots_root / "benchmark_quality.svg"
    object_path = plots_root / "benchmark_per_object.svg"

    # Within-packet σ: std dev of a metric across repeated runs of the same packet,
    # then averaged across packets. Returns 0 when every packet has only 1 run.
    def ms(item): return float(item["run"].get("duration_ms") or 0) / 10_000
    def tok(item):
        tokens = _tokens_from_row(item.get("metrics_row"), item["state"])
        return tokens.get("total_tokens", 0) / 1_000
    def char(item): return _coverage_metrics(item["state"])["characterization_score"]
    def acc(item):
        state = item["state"]
        pkt = state.get("observation_packet") or _read_packet(state.get("packet_index"))
        agg = state.get("aggregated_evidence") or {}
        novel = state.get("novelty_rarity_assessment") or {}
        interest = float(agg.get("overall_interest_score") or novel.get("overall_interest_score") or 0.5)
        verdict = agg.get("triage_verdict") or _verdict_from_interest(interest, pkt)
        return 1.0 if _priority_class(verdict) == _expected_priority(pkt) else 0.0
    def calib(item):
        state = item["state"]
        pkt = state.get("observation_packet") or _read_packet(state.get("packet_index"))
        agg = state.get("aggregated_evidence") or {}
        novel = state.get("novelty_rarity_assessment") or {}
        interest = float(agg.get("overall_interest_score") or novel.get("overall_interest_score") or _expected_interest(pkt))
        return 1 - abs(interest - _expected_interest(pkt))

    sigma_ms   = _within_packet_std(all_by_packet, ms)
    sigma_tok  = _within_packet_std(all_by_packet, tok)
    sigma_char = _within_packet_std(all_by_packet, char)
    sigma_acc  = _within_packet_std(all_by_packet, acc)
    sigma_cal  = _within_packet_std(all_by_packet, calib)

    # Per-object σ: std dev of characterization_score across repeated runs of that packet
    def _packet_sigma(packet_index: int) -> float:
        items = all_by_packet.get(packet_index, [])
        if len(items) < 2:
            return 0.0
        return _std([char(item) for item in items])

    _svg_bar_chart(
        "Average Runtime and Token Use",
        [
            {
                "label": "Wall time / 10s",
                "values": [
                    summary["multi_agent"]["avg_wall_ms"] / 10_000,
                    summary["single_agent_mock"]["avg_wall_ms"] / 10_000,
                ],
            },
            {
                "label": "Tokens / 1k",
                "values": [
                    summary["multi_agent"]["avg_total_tokens"] / 1_000,
                    summary["single_agent_mock"]["avg_total_tokens"] / 1_000,
                ],
            },
        ],
        "Lower is better for both groups  (error bars = 1σ across repeated runs)",
        speed_path,
        errors=[[sigma_ms, 0.0], [sigma_tok, 0.0]],
    )
    _svg_bar_chart(
        "Decision and Characterization Quality",
        [
            {
                "label": "Priority accuracy",
                "values": [
                    summary["multi_agent"]["priority_accuracy"],
                    summary["single_agent_mock"]["priority_accuracy"],
                ],
            },
            {
                "label": "Characterization",
                "values": [
                    summary["multi_agent"]["avg_characterization_score"],
                    summary["single_agent_mock"]["avg_characterization_score"],
                ],
            },
            {
                "label": "Interest calibration",
                "values": [
                    1 - summary["multi_agent"]["avg_interest_abs_error"],
                    1 - summary["single_agent_mock"]["avg_interest_abs_error"],
                ],
            },
        ],
        "Higher is better  (error bars = 1σ across repeated runs)",
        quality_path,
        errors=[[sigma_acc, 0.0], [sigma_char, 0.0], [sigma_cal, 0.0]],
    )
    _svg_bar_chart(
        "Per-object Characterization Score",
        [
            {
                "label": f"P{record['packet_index']:02d}",
                "values": [
                    record["multi_agent"]["characterization_score"],
                    record["single_agent_mock"]["characterization_score"],
                ],
            }
            for record in records
        ],
        "Higher is better  (error bars = 1σ across repeated runs per packet)",
        object_path,
        errors=[
            [_packet_sigma(record["packet_index"]), 0.0]
            for record in records
        ],
    )
    return {
        "speed_tokens": f"static-data/plots/{speed_path.name}",
        "quality": f"static-data/plots/{quality_path.name}",
        "per_object": f"static-data/plots/{object_path.name}",
    }


def build_benchmark_payload(write_plots: bool = False, plots_root: Path = PLOTS_ROOT) -> dict[str, Any]:
    latest, all_by_packet = _load_all_runs()
    records = [_make_record(item) for item in latest]
    total_runs = sum(len(v) for v in all_by_packet.values())
    repeated_packets = sum(1 for v in all_by_packet.values() if len(v) >= 2)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "methodology": {
            "multi_agent": "Actual latest successful packet runs from SQLite traces.",
            "single_agent_mock": "Deterministic offline baseline: one generalist performs the same characterization serially, uses packet labels/local files only, and has no independent branch debate.",
            "speed": "Single-agent wall time is estimated from serial same-work timing; multi-agent wall time is the logged run wall time.",
            "tokens": "Multi-agent tokens are logged model tokens; single-agent tokens are deterministic mock estimates from packet complexity and reduced output scope.",
            "quality": "Priority accuracy uses packet experiment labels as coarse expected classes; characterization score rewards evidence channels, hypotheses, debate points, follow-up actions, code metrics, and context.",
            "error_bars": f"1σ computed from within-packet variance across repeated runs. Total runs in DB: {total_runs}. Packets with ≥2 runs: {repeated_packets}. Error bars are hidden when a packet has only one run.",
        },
        "summary": _build_summary(records),
        "records": records,
    }
    if write_plots:
        payload["plots"] = _write_plots(payload, all_by_packet, plots_root)
    return payload


def write_benchmark_outputs(static_root: Path = STATIC_ROOT, results_path: Path = RESULTS_PATH) -> dict[str, Any]:
    plots_root = static_root / "plots"
    payload = build_benchmark_payload(write_plots=True, plots_root=plots_root)
    static_root.mkdir(parents=True, exist_ok=True)
    (static_root / "benchmark.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    results_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark multi-agent traces against a mock single-agent baseline.")
    parser.add_argument("--no-plots", action="store_true", help="Only print/write JSON; do not generate SVG plots.")
    args = parser.parse_args()

    if args.no_plots:
        payload = build_benchmark_payload(write_plots=False)
        RESULTS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    else:
        payload = write_benchmark_outputs()

    summary = payload["summary"]
    print("Agentic Orion benchmark")
    print(f"  Objects compared: {summary['objects_compared']}")
    print(f"  Speedup multi vs serial single mock: {summary['comparison']['avg_speedup_multi_vs_single']}x")
    print(f"  Characterization gain: +{summary['comparison']['characterization_gain']}")
    print(f"  Token ratio multi/single mock: {summary['comparison']['token_ratio_multi_over_single']}x")
    print(f"  Results: {RESULTS_PATH}")


if __name__ == "__main__":
    main()
