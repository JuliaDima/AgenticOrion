"""
Tool implementations for the OrionSpectrum workflow.

- search_arxiv: ArXiv full-text search (used by context_retriever)
- execute_python: sandboxed subprocess execution (used by code_executor)
- load_packet_data: reads on-disk data files for a packet and returns a summary
- extract_tokens: normalises token-usage metadata from any LangChain response
"""

import json
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Any

import arxiv


# ---------------------------------------------------------------------------
# Token usage extraction
# ---------------------------------------------------------------------------

def extract_tokens(node_name: str, response) -> dict:
    """
    Return a token-count dict from any LangChain AIMessage-like response.
    Works with both direct .invoke() responses and the 'raw' key from
    with_structured_output(include_raw=True).
    """
    input_t = output_t = 0
    try:
        # LangChain >= 0.2: usage_metadata is a dict on AIMessage
        um = getattr(response, "usage_metadata", None)
        if um and isinstance(um, dict):
            input_t  = um.get("input_tokens",  0) or 0
            output_t = um.get("output_tokens", 0) or 0
        elif um:
            # Older versions may expose as object attributes
            input_t  = getattr(um, "input_tokens",  0) or 0
            output_t = getattr(um, "output_tokens", 0) or 0
        else:
            # Fallback: response_metadata dict (openai-style)
            rm = getattr(response, "response_metadata", {}) or {}
            tu = rm.get("token_usage", {}) or {}
            input_t  = tu.get("prompt_tokens",     0) or 0
            output_t = tu.get("completion_tokens", 0) or 0
    except Exception:
        pass
    return {
        "node":         node_name,
        "input_tokens":  input_t,
        "output_tokens": output_t,
        "total_tokens":  input_t + output_t,
    }


# ---------------------------------------------------------------------------
# ArXiv search
# ---------------------------------------------------------------------------

def search_arxiv(query: str, max_results: int = 5) -> list[dict]:
    """Return a list of paper dicts from the ArXiv API."""
    client = arxiv.Client()
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.Relevance,
    )
    results = []
    for paper in client.results(search):
        results.append(
            {
                "title": paper.title,
                "authors": [str(a) for a in paper.authors[:5]],
                "abstract": paper.summary[:800],
                "url": paper.entry_id,
                "published": str(paper.published.date()),
                "categories": paper.categories,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Sandboxed Python execution
# ---------------------------------------------------------------------------

def execute_python(code: str, timeout: int = 30) -> dict[str, Any]:
    """Execute Python in a subprocess with a hard timeout."""
    code = textwrap.dedent(code)
    t0 = time.perf_counter()
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        return {
            "stdout": result.stdout[:3000],
            "stderr": result.stderr[:1000],
            "returncode": result.returncode,
            "elapsed_ms": elapsed,
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Execution timed out after {timeout}s",
            "returncode": -1,
            "elapsed_ms": timeout * 1000,
        }
    except Exception as exc:
        return {
            "stdout": "",
            "stderr": str(exc),
            "returncode": -2,
            "elapsed_ms": 0,
        }


# ---------------------------------------------------------------------------
# Packet data loader
# ---------------------------------------------------------------------------

_PACKETS_ROOT = Path(__file__).parent.parent / "packets"


def load_packet_data(packet_index: int) -> str:
    """
    Reads the on-disk data files for a given packet (1-indexed) and returns
    a text summary suitable for injection into LLM prompts.

    Returns an empty string if no data directory is found.
    """
    pkt_dirs = sorted(_PACKETS_ROOT.glob(f"packet_{packet_index:02d}_*"))
    if not pkt_dirs:
        return ""

    pkt_dir = pkt_dirs[0]
    data_dir = pkt_dir / "data"
    if not data_dir.exists():
        return ""

    lines = [f"Data directory: {pkt_dir.name}/data/"]

    for fpath in sorted(data_dir.iterdir()):
        size_kb = fpath.stat().st_size // 1024
        lines.append(f"\n--- {fpath.name} ({size_kb} kB) ---")

        try:
            if fpath.suffix == ".json":
                raw = json.loads(fpath.read_text())
                # Flatten to a readable snippet
                if isinstance(raw, list):
                    lines.append(f"  [{len(raw)} rows] first row: {json.dumps(raw[0], default=str)[:400]}")
                else:
                    lines.append(json.dumps(raw, default=str)[:600])

            elif fpath.suffix == ".csv":
                text = fpath.read_text()
                csv_lines = text.strip().splitlines()
                header = csv_lines[0] if csv_lines else ""
                n_rows = len(csv_lines) - 1
                lines.append(f"  {n_rows} rows. Header: {header[:200]}")
                # First 2 data rows
                for row in csv_lines[1:3]:
                    lines.append(f"  {row[:200]}")

            elif fpath.suffix == ".fits":
                lines.append(f"  FITS file ({size_kb} kB) — binary; not read inline")

            elif fpath.suffix == ".txt":
                lines.append(f"  {fpath.read_text()[:200]}")

        except Exception as exc:
            lines.append(f"  [read error: {exc}]")

    return "\n".join(lines)
