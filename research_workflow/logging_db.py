"""
Structured SQLite logger for all agent calls, tool calls, and state transitions.
Thread-safe singleton — all modules import the same instance via `get_logger()`.
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DB_PATH = Path(__file__).parent / "research_workflow.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowLogger:
    _instance: Optional["WorkflowLogger"] = None
    _class_lock = threading.Lock()

    def __new__(cls) -> "WorkflowLogger":
        if cls._instance is None:
            with cls._class_lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._db_lock = threading.Lock()
                    inst._init_db()
                    cls._instance = inst
        return cls._instance

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(DB_PATH), check_same_thread=False)

    def _init_db(self) -> None:
        with self._conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id       TEXT PRIMARY KEY,
                    query        TEXT,
                    start_time   TEXT,
                    end_time     TEXT,
                    status       TEXT,
                    duration_ms  REAL
                );

                CREATE TABLE IF NOT EXISTS agent_calls (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id        TEXT,
                    agent_name    TEXT,
                    input_summary TEXT,
                    output_summary TEXT,
                    start_time    TEXT,
                    end_time      TEXT,
                    duration_ms   REAL,
                    error         TEXT
                );

                CREATE TABLE IF NOT EXISTS tool_calls (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id      TEXT,
                    agent_name  TEXT,
                    tool_name   TEXT,
                    input       TEXT,
                    output      TEXT,
                    start_time  TEXT,
                    duration_ms REAL,
                    error       TEXT
                );

                CREATE TABLE IF NOT EXISTS state_transitions (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id         TEXT,
                    from_node      TEXT,
                    to_node        TEXT,
                    timestamp      TEXT,
                    state_snapshot TEXT
                );
            """)

    # ------------------------------------------------------------------
    # Public logging methods
    # ------------------------------------------------------------------

    def log_run_start(self, run_id: str, query: str) -> None:
        with self._db_lock, self._conn() as c:
            c.execute(
                "INSERT OR IGNORE INTO runs (run_id, query, start_time, status) VALUES (?, ?, ?, ?)",
                (run_id, query, _now(), "running"),
            )

    def log_run_end(self, run_id: str, status: str, duration_ms: float) -> None:
        with self._db_lock, self._conn() as c:
            c.execute(
                "UPDATE runs SET end_time=?, status=?, duration_ms=? WHERE run_id=?",
                (_now(), status, duration_ms, run_id),
            )

    def log_agent_call(
        self,
        run_id: str,
        agent_name: str,
        input_summary: str,
        output_summary: str,
        start_time: str,
        duration_ms: float,
        error: Optional[str] = None,
    ) -> None:
        with self._db_lock, self._conn() as c:
            c.execute(
                """INSERT INTO agent_calls
                   (run_id, agent_name, input_summary, output_summary,
                    start_time, end_time, duration_ms, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, agent_name, input_summary[:1000], output_summary[:1000],
                 start_time, _now(), duration_ms, error),
            )

    def log_tool_call(
        self,
        run_id: str,
        agent_name: str,
        tool_name: str,
        input_data: Any,
        output_data: Any,
        start_time: str,
        duration_ms: float,
        error: Optional[str] = None,
    ) -> None:
        def _ser(obj: Any) -> str:
            return json.dumps(obj, default=str)[:2000]

        with self._db_lock, self._conn() as c:
            c.execute(
                """INSERT INTO tool_calls
                   (run_id, agent_name, tool_name, input, output,
                    start_time, duration_ms, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, agent_name, tool_name,
                 _ser(input_data), _ser(output_data),
                 start_time, duration_ms, error),
            )

    def log_state_transition(
        self,
        run_id: str,
        from_node: str,
        to_node: str,
        state: dict,
    ) -> None:
        # Store a lean snapshot — drop the large literature_results list body
        snapshot = {
            k: (f"<{len(v)} papers>" if k == "literature_results" else v)
            for k, v in state.items()
            if k != "code_to_execute"
        }
        with self._db_lock, self._conn() as c:
            c.execute(
                """INSERT INTO state_transitions
                   (run_id, from_node, to_node, timestamp, state_snapshot)
                   VALUES (?, ?, ?, ?, ?)""",
                (run_id, from_node, to_node, _now(),
                 json.dumps(snapshot, default=str)[:4000]),
            )


def get_logger() -> WorkflowLogger:
    return WorkflowLogger()
