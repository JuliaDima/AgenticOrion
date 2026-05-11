"""
Trace viewer: reads the SQLite database and prints a human-readable,
timestamped execution trace for a given run_id (or the latest run).

Usage:
    python trace_viewer.py                  # latest run
    python trace_viewer.py <run_id>         # specific run
    python trace_viewer.py --list           # list all runs
"""

import json
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent / "research_workflow.db"

_SEP = "─" * 72
_WIDE = "═" * 72


def _conn() -> sqlite3.Connection:
    if not DB_PATH.exists():
        print("[error] Database not found. Run the workflow first.")
        sys.exit(1)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _ts(raw: str | None) -> str:
    if not raw:
        return "—"
    # Trim to HH:MM:SS.mmm for readability
    t = raw.split("T")[-1]
    return t[:12] if len(t) > 12 else t


def list_runs() -> None:
    with _conn() as c:
        rows = c.execute(
            "SELECT run_id, query, start_time, status, duration_ms FROM runs ORDER BY start_time DESC"
        ).fetchall()
    if not rows:
        print("No runs found.")
        return
    print(f"\n{'RUN ID':<38} {'STATUS':<10} {'DURATION':>10}  QUERY")
    print(_WIDE)
    for r in rows:
        dur = f"{r['duration_ms']:.0f} ms" if r["duration_ms"] else "running"
        print(f"{r['run_id']:<38} {r['status']:<10} {dur:>10}  {r['query'][:60]}")


def show_trace(run_id: str | None = None) -> None:
    with _conn() as c:
        if run_id is None:
            row = c.execute(
                "SELECT * FROM runs ORDER BY start_time DESC LIMIT 1"
            ).fetchone()
        else:
            row = c.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()

        if not row:
            print("Run not found.")
            return

        run_id = row["run_id"]

        agents = c.execute(
            "SELECT * FROM agent_calls WHERE run_id=? ORDER BY start_time",
            (run_id,),
        ).fetchall()

        tools = c.execute(
            "SELECT * FROM tool_calls WHERE run_id=? ORDER BY start_time",
            (run_id,),
        ).fetchall()

        transitions = c.execute(
            "SELECT * FROM state_transitions WHERE run_id=? ORDER BY timestamp",
            (run_id,),
        ).fetchall()

    # ── Header ──────────────────────────────────────────────────────────
    print(f"\n{_WIDE}")
    print(f"  EXECUTION TRACE")
    print(f"  Run ID  : {run_id}")
    print(f"  Query   : {row['query']}")
    print(f"  Started : {_ts(row['start_time'])}")
    dur = f"{row['duration_ms']:.0f} ms" if row["duration_ms"] else "still running"
    print(f"  Status  : {row['status']}  ({dur})")
    print(f"{_WIDE}\n")

    # ── State transitions ────────────────────────────────────────────────
    print("STATE TRANSITIONS")
    print(_SEP)
    for t in transitions:
        snap = {}
        try:
            snap = json.loads(t["state_snapshot"])
        except Exception:
            pass
        step = snap.get("step_count", "?")
        print(f"  [{_ts(t['timestamp'])}]  {t['from_node']:>14}  →  {t['to_node']}")
        if snap.get("errors"):
            print(f"    ⚠  errors: {snap['errors']}")
    print()

    # ── Agent calls ──────────────────────────────────────────────────────
    print("AGENT CALLS")
    print(_SEP)
    for a in agents:
        status = "✓" if not a["error"] else "✗"
        print(
            f"  [{_ts(a['start_time'])}]  {status}  {a['agent_name']:<16}  "
            f"{a['duration_ms']:>7.0f} ms"
        )
        print(f"    IN : {a['input_summary'][:80]}")
        print(f"    OUT: {a['output_summary'][:80]}")
        if a["error"]:
            print(f"    ERR: {a['error'][:100]}")
    print()

    # ── Tool calls ───────────────────────────────────────────────────────
    print("TOOL CALLS")
    print(_SEP)
    for t in tools:
        status = "✓" if not t["error"] else "✗"
        print(
            f"  [{_ts(t['start_time'])}]  {status}  {t['agent_name']}.{t['tool_name']:<30}  "
            f"{t['duration_ms']:>7.0f} ms"
        )
        try:
            inp = json.loads(t["input"])
            print(f"    IN : {json.dumps(inp)[:100]}")
        except Exception:
            print(f"    IN : {str(t['input'])[:100]}")
        try:
            out = json.loads(t["output"])
            print(f"    OUT: {json.dumps(out)[:120]}")
        except Exception:
            print(f"    OUT: {str(t['output'])[:120]}")
        if t["error"]:
            print(f"    ERR: {t['error'][:100]}")
    print()
    print(_WIDE)


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--list" in args:
        list_runs()
    elif args:
        show_trace(args[0])
    else:
        show_trace()
