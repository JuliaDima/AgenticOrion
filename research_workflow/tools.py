"""
Tool implementations: ArXiv search and sandboxed Python execution.
These are plain functions; agents call them directly and log via WorkflowLogger.
"""

import subprocess
import sys
import textwrap
import time
from typing import Any

import arxiv


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
    """
    Execute Python code in a subprocess with a hard timeout.
    Returns stdout, stderr, returncode, and elapsed time.
    """
    # Dedent so the LLM-produced code works even if indented inside a prompt
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
