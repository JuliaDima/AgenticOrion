"""
Local Agentic Orion dashboard server.

Usage:
    python web_server.py --port 8765

The server intentionally uses only the Python standard library so the
dashboard can run wherever the workflow already runs.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
WEB_ROOT = ROOT / "web"
DB_PATH = ROOT / "research_workflow.db"
PACKETS_ROOT = REPO_ROOT / "packets"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(REPO_ROOT / "data_fetching"))

AGENTS = [
    {
        "id": "supervisor",
        "label": "Supervisor",
        "role": "Routes the packet and decides whether quantitative code analysis could help.",
        "group": "routing",
    },
    {
        "id": "observation_characterizer",
        "label": "Observation Characterizer",
        "role": "Extracts salient features, missing evidence, uncertainties, and data-quality notes.",
        "group": "characterization",
    },
    {
        "id": "astrophysical_interpreter",
        "label": "Astrophysical Interpreter",
        "role": "Tests plausible astrophysical explanations and class confidences.",
        "group": "parallel",
    },
    {
        "id": "artefact_checker",
        "label": "Artefact Checker",
        "role": "Estimates whether instrument, detector, or pipeline effects explain the signal.",
        "group": "parallel",
    },
    {
        "id": "novelty_assessor",
        "label": "Novelty Assessor",
        "role": "Scores rarity, novelty, uncertainty, follow-up value, and time sensitivity.",
        "group": "parallel",
    },
    {
        "id": "context_retriever",
        "label": "Context Retriever",
        "role": "Searches literature/context and summarizes relevant historical analogues.",
        "group": "parallel",
    },
    {
        "id": "evidence_aggregator",
        "label": "Evidence Aggregator",
        "role": "Debates branch outputs, updates confidences, and sets a triage verdict.",
        "group": "debate",
    },
    {
        "id": "followup_prioritizer",
        "label": "Follow-up Prioritizer",
        "role": "Ranks discriminating follow-up observations by urgency and scientific value.",
        "group": "action",
    },
    {
        "id": "code_executor",
        "label": "Code Executor",
        "role": "Optionally generates and executes lightweight Python metrics on local data.",
        "group": "analysis",
    },
    {
        "id": "synthesis",
        "label": "Synthesis",
        "role": "Produces the final traceable Agentic Orion scientific report.",
        "group": "report",
    },
]

EDGES = [
    ["START", "supervisor"],
    ["supervisor", "observation_characterizer"],
    ["observation_characterizer", "astrophysical_interpreter"],
    ["observation_characterizer", "artefact_checker"],
    ["observation_characterizer", "novelty_assessor"],
    ["observation_characterizer", "context_retriever"],
    ["astrophysical_interpreter", "evidence_aggregator"],
    ["artefact_checker", "evidence_aggregator"],
    ["novelty_assessor", "evidence_aggregator"],
    ["context_retriever", "evidence_aggregator"],
    ["evidence_aggregator", "followup_prioritizer"],
    ["followup_prioritizer", "code_executor"],
    ["followup_prioritizer", "synthesis"],
    ["code_executor", "synthesis"],
]

STATE_BY_AGENT = {
    "supervisor": ["mission", "primary_modality", "needs_code"],
    "observation_characterizer": ["observation_characterization"],
    "astrophysical_interpreter": ["astrophysical_interpretation"],
    "artefact_checker": ["artefact_assessment"],
    "novelty_assessor": ["novelty_rarity_assessment"],
    "context_retriever": ["context_retrieval_results"],
    "evidence_aggregator": ["aggregated_evidence"],
    "followup_prioritizer": ["followup_recommendations"],
    "code_executor": ["code_to_execute", "code_execution_output"],
    "synthesis": ["synthesis_report"],
}


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS final_states (
           run_id TEXT PRIMARY KEY,
           timestamp TEXT,
           total_wall_ms REAL,
           state_json TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS run_metrics (
           run_id TEXT PRIMARY KEY,
           timestamp TEXT,
           input_tokens INTEGER,
           output_tokens INTEGER,
           total_tokens INTEGER,
           estimated_cost_usd REAL,
           pricing_model TEXT,
           per_agent_json TEXT
        )"""
    )
    return conn


def _rows(query: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    with _conn() as conn:
        return [dict(row) for row in conn.execute(query, args).fetchall()]


def _row(query: str, args: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    rows = _rows(query, args)
    return rows[0] if rows else None


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


def _object_id(packet: dict[str, Any]) -> str:
    ids = packet.get("object_or_event_id", {})
    for key in ("TNS_name", "Euclid_id", "common_name", "survey_id", "artefact_name", "canonical_name", "IAU_coord_name"):
        if ids.get(key):
            return str(ids[key])
    return "Unknown"


def _read_packet(index: int | None) -> dict[str, Any] | None:
    if index is None:
        return None
    for path in sorted(PACKETS_ROOT.glob(f"packet_{index:02d}_*/packet.json")):
        return _json_loads(path.read_text(), {})
    return None


def _read_manifest() -> list[dict[str, Any]]:
    manifest = PACKETS_ROOT / "manifest.json"
    if manifest.exists():
        return _json_loads(manifest.read_text(), [])
    packets = []
    for path in sorted(PACKETS_ROOT.glob("packet_*/packet.json")):
        match = re.search(r"packet_(\d+)", str(path))
        packet = _json_loads(path.read_text(), {})
        if match:
            packets.append(
                {
                    "index": int(match.group(1)),
                    "packet_dir": str(path.parent.relative_to(REPO_ROOT)),
                    "mission": packet.get("mission"),
                    "experiment": packet.get("experiment_type"),
                    "modalities": packet.get("modality", []),
                    "labels": packet.get("initial_pipeline_labels", []),
                    "files": [],
                }
            )
    return packets


def _packet_dir(index: int | None) -> Path | None:
    if index is None:
        return None
    matches = sorted(PACKETS_ROOT.glob(f"packet_{index:02d}_*"))
    return matches[0] if matches else None


def _read_lightcurve(index: int | None) -> list[dict[str, Any]]:
    pdir = _packet_dir(index)
    if not pdir:
        return []
    lc = pdir / "data" / "lightcurve.csv"
    if not lc.exists():
        return []
    rows: list[dict[str, Any]] = []
    with lc.open(newline="") as handle:
        for row in csv.DictReader(handle):
            parsed: dict[str, Any] = {}
            for key, value in row.items():
                if value == "":
                    parsed[key] = None
                    continue
                try:
                    parsed[key] = float(value)
                except ValueError:
                    parsed[key] = value
            rows.append(parsed)
    return rows[:400]


def _read_probabilities(index: int | None) -> list[dict[str, Any]]:
    pdir = _packet_dir(index)
    if not pdir:
        return []
    path = pdir / "data" / "probabilities.json"
    values = _json_loads(path.read_text(), []) if path.exists() else []
    values = [v for v in values if isinstance(v, dict) and "probability" in v]
    values.sort(key=lambda item: item.get("probability", 0), reverse=True)
    return values[:16]


def _summary_float(summary: str | None, key: str) -> float | None:
    if not summary:
        return None
    match = re.search(rf"\b{re.escape(key)}=([0-9]*\.?[0-9]+)", summary)
    return float(match.group(1)) if match else None


def _summary_text(summary: str | None, key: str) -> str | None:
    if not summary:
        return None
    match = re.search(rf"\b{re.escape(key)}=([A-Z_]+)", summary)
    return match.group(1) if match else None


def _agent_summary_fallbacks(run_id: str, agents: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    calls = agents if agents is not None else _rows(
        "SELECT agent_name, output_summary, duration_ms FROM agent_calls WHERE run_id=?",
        (run_id,),
    )
    by_agent = {call.get("agent_name"): call for call in calls}
    aggregator = by_agent.get("evidence_aggregator", {})
    novelty = by_agent.get("novelty_assessor", {})

    interest = (
        _summary_float(aggregator.get("output_summary"), "interest")
        or _summary_float(novelty.get("output_summary"), "overall")
    )
    verdict = _summary_text(aggregator.get("output_summary"), "verdict")

    parallel_nodes = {
        "astrophysical_interpreter",
        "artefact_checker",
        "novelty_assessor",
        "context_retriever",
    }
    branch_durations = [
        float(call.get("duration_ms") or 0)
        for call in calls
        if call.get("agent_name") in parallel_nodes and call.get("duration_ms") is not None
    ]
    sequential_estimate_ms = sum(branch_durations) if branch_durations else None
    parallel_wall_ms = max(branch_durations) if branch_durations else None
    speedup = (
        round(sequential_estimate_ms / parallel_wall_ms, 2)
        if sequential_estimate_ms and parallel_wall_ms
        else None
    )

    return {
        "interest_score": interest,
        "triage_verdict": verdict,
        "parallel_wall_ms": parallel_wall_ms,
        "sequential_estimate_ms": sequential_estimate_ms,
        "speedup": speedup,
    }


def _run_metrics(run_id: str) -> dict[str, Any] | None:
    row = _row("SELECT * FROM run_metrics WHERE run_id=?", (run_id,))
    if not row:
        return None
    row["per_agent"] = _json_loads(row.get("per_agent_json"), [])
    return row


def _token_metrics_from_state(state: dict[str, Any]) -> dict[str, Any] | None:
    token_counts = state.get("token_counts") or []
    if not token_counts:
        return None
    input_tokens = sum(int(tc.get("input_tokens") or 0) for tc in token_counts)
    output_tokens = sum(int(tc.get("output_tokens") or 0) for tc in token_counts)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "estimated_cost_usd": (input_tokens * 0.15 + output_tokens * 0.60) / 1_000_000,
        "pricing_model": "gpt-4o-mini production estimate",
        "per_agent": token_counts,
    }


def _ensure_run_metrics(run_id: str, state: dict[str, Any]) -> dict[str, Any] | None:
    existing = _run_metrics(run_id)
    if existing:
        return existing
    metrics = _token_metrics_from_state(state)
    if not metrics:
        return None
    with _conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO run_metrics
               (run_id, timestamp, input_tokens, output_tokens, total_tokens,
                estimated_cost_usd, pricing_model, per_agent_json)
               VALUES (?, datetime('now'), ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                metrics["input_tokens"],
                metrics["output_tokens"],
                metrics["total_tokens"],
                metrics["estimated_cost_usd"],
                metrics["pricing_model"],
                json.dumps(metrics["per_agent"], default=str),
            ),
        )
    return _run_metrics(run_id)


def _run_summary(row: dict[str, Any]) -> dict[str, Any]:
    state_row = _row("SELECT state_json FROM final_states WHERE run_id=?", (row["run_id"],))
    state = _json_loads(state_row["state_json"], {}) if state_row else {}
    run_metrics = _ensure_run_metrics(row["run_id"], state) or {}
    packet_index = state.get("packet_index") or _packet_index_from_query(row.get("query"))
    packet = state.get("observation_packet") or (_read_packet(packet_index) if packet_index else None) or {}
    agg = state.get("aggregated_evidence") or {}
    novel = state.get("novelty_rarity_assessment") or {}
    fallback = _agent_summary_fallbacks(row["run_id"]) if not state else {}
    return {
        **row,
        "packet_index": packet_index,
        "object_id": _object_id(packet),
        "mission": packet.get("mission") or row.get("query"),
        "experiment_type": packet.get("experiment_type"),
        "triage_verdict": agg.get("triage_verdict") or fallback.get("triage_verdict"),
        "interest_score": (
            agg.get("overall_interest_score")
            or novel.get("overall_interest_score")
            or fallback.get("interest_score")
        ),
        "total_tokens": run_metrics.get("total_tokens"),
        "estimated_cost_usd": run_metrics.get("estimated_cost_usd"),
        "has_final_state": bool(state),
    }


def list_runs() -> list[dict[str, Any]]:
    rows = _rows(
        "SELECT run_id, query, start_time, end_time, status, duration_ms FROM runs ORDER BY start_time DESC LIMIT 100"
    )
    return [_run_summary(row) for row in rows]


def run_detail(run_id: str) -> dict[str, Any] | None:
    run = _row("SELECT * FROM runs WHERE run_id=?", (run_id,))
    if not run:
        return None

    agents = _rows("SELECT * FROM agent_calls WHERE run_id=? ORDER BY start_time", (run_id,))
    tools = _rows("SELECT * FROM tool_calls WHERE run_id=? ORDER BY start_time", (run_id,))
    transitions = _rows("SELECT * FROM state_transitions WHERE run_id=? ORDER BY timestamp", (run_id,))
    state_row = _row("SELECT * FROM final_states WHERE run_id=?", (run_id,))
    state = _json_loads(state_row["state_json"], {}) if state_row else {}
    run_metrics = _ensure_run_metrics(run_id, state) or {}
    packet_index = state.get("packet_index") or _packet_index_from_query(run.get("query"))
    packet = state.get("observation_packet") or _read_packet(packet_index) or {}

    token_counts = state.get("token_counts") or run_metrics.get("per_agent") or []
    timing_log = state.get("timing_log") or [
        {"node": a["agent_name"], "duration_ms": a["duration_ms"], "timestamp": a["start_time"]}
        for a in agents
    ]

    tool_by_agent: dict[str, list[dict[str, Any]]] = {}
    for tool in tools:
        tool["input_json"] = _json_loads(tool.get("input"), tool.get("input"))
        tool["output_json"] = _json_loads(tool.get("output"), tool.get("output"))
        tool_by_agent.setdefault(tool["agent_name"], []).append(tool)

    calls_by_agent: dict[str, dict[str, Any]] = {}
    for call in agents:
        calls_by_agent[call["agent_name"]] = call

    agent_details = []
    for meta in AGENTS:
        call = calls_by_agent.get(meta["id"], {})
        outputs = {key: state.get(key) for key in STATE_BY_AGENT.get(meta["id"], []) if key in state}
        agent_details.append(
            {
                **meta,
                "call": call,
                "tools": tool_by_agent.get(meta["id"], []),
                "outputs": outputs,
                "tokens": next((t for t in token_counts if t.get("node") == meta["id"]), None),
                "timing": next((t for t in timing_log if t.get("node") == meta["id"]), None),
            }
        )

    parallel_end = next((t for t in timing_log if t.get("node") == "_parallel_end"), {})
    has_token_metrics = bool(run_metrics) or bool(token_counts)
    input_tokens = run_metrics.get("input_tokens")
    output_tokens = run_metrics.get("output_tokens")
    total_tokens = run_metrics.get("total_tokens")
    if has_token_metrics and input_tokens is None:
        input_tokens = sum((t.get("input_tokens") or 0) for t in token_counts)
    if has_token_metrics and output_tokens is None:
        output_tokens = sum((t.get("output_tokens") or 0) for t in token_counts)
    if has_token_metrics and total_tokens is None:
        total_tokens = sum((t.get("total_tokens") or 0) for t in token_counts)
    cost_usd = run_metrics.get("estimated_cost_usd")
    if has_token_metrics and cost_usd is None:
        cost_usd = (input_tokens * 0.15 + output_tokens * 0.60) / 1_000_000
    fallback = _agent_summary_fallbacks(run_id, agents)

    return {
        "run": _run_summary(run),
        "packet": packet,
        "packet_index": packet_index,
        "agents": agent_details,
        "tools": tools,
        "transitions": transitions,
        "state": state,
        "timing_log": timing_log,
        "token_counts": token_counts,
        "metrics": {
            "total_wall_ms": run.get("duration_ms") or (state_row or {}).get("total_wall_ms"),
            "parallel_wall_ms": (
                state.get("parallel_section_wall_ms")
                or parallel_end.get("parallel_wall_ms")
                or fallback.get("parallel_wall_ms")
            ),
            "sequential_estimate_ms": parallel_end.get("sequential_estimate_ms") or fallback.get("sequential_estimate_ms"),
            "speedup": parallel_end.get("speedup") or fallback.get("speedup"),
            "total_tokens": total_tokens,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": cost_usd,
            "pricing_model": run_metrics.get("pricing_model") or "gpt-4o-mini production estimate",
            "consumption_note": None if has_token_metrics else "Token counts were not logged for this older run.",
            "metric_note": None if packet_index else "This is a legacy non-packet run, so Orion triage metrics are not applicable.",
        },
        "data_products": {
            "lightcurve": _read_lightcurve(packet_index),
            "probabilities": _read_probabilities(packet_index),
        },
    }


class OrionHandler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".js": "application/javascript",
        ".css": "text/css",
    }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[dashboard] {self.address_string()} - {format % args}")

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/workflow":
            self._send_json({"agents": AGENTS, "edges": EDGES})
            return
        if path == "/api/packets":
            self._send_json(_read_manifest())
            return
        if path == "/api/runs":
            self._send_json(list_runs())
            return
        if path.startswith("/api/runs/"):
            run_id = path.rsplit("/", 1)[-1]
            detail = run_detail(run_id)
            self._send_json(detail if detail else {"error": "Run not found"}, 200 if detail else 404)
            return
        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/run":
            self._send_json({"error": "Not found"}, 404)
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        payload = _json_loads(self.rfile.read(length).decode("utf-8"), {}) if length else {}
        packet_index = int(payload.get("packet_index") or parse_qs(parsed.query).get("packet", ["1"])[0])
        try:
            from main import run_packet

            final_state = run_packet(packet_index, verbose=False)
            detail = run_detail(final_state["run_id"])
            self._send_json(detail)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 500)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the Agentic Orion local dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), OrionHandler)
    print(f"Agentic Orion dashboard: http://{args.host}:{args.port}")
    print("Press Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Agentic Orion dashboard.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
