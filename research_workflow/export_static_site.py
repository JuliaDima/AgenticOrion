"""
Export dashboard API data as static JSON for GitHub Pages.

GitHub Pages cannot run the local Python API server, so this script snapshots
the same data served by web_server.py into research_workflow/web/static-data.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from benchmark import write_benchmark_outputs
from web_server import AGENTS, EDGES, _read_manifest, list_runs, run_detail

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
WEB_ROOT = ROOT / "web"
STATIC_ROOT = WEB_ROOT / "static-data"
ASSET_ROOT = WEB_ROOT / "assets"


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, default=str, indent=2), encoding="utf-8")


def main() -> None:
    if STATIC_ROOT.exists():
        shutil.rmtree(STATIC_ROOT)
    ASSET_ROOT.mkdir(parents=True, exist_ok=True)

    runs = list_runs()
    _write_json(STATIC_ROOT / "workflow.json", {"agents": AGENTS, "edges": EDGES})
    _write_json(STATIC_ROOT / "packets.json", _read_manifest())
    _write_json(STATIC_ROOT / "runs.json", runs)

    for run in runs:
        detail = run_detail(run["run_id"])
        if detail:
            _write_json(STATIC_ROOT / "runs" / f"{run['run_id']}.json", detail)

    write_benchmark_outputs(STATIC_ROOT)

    main_image = REPO_ROOT / "assets" / "main_page.png"
    if main_image.exists():
        shutil.copy2(main_image, ASSET_ROOT / "main_page.png")

    # Disable Jekyll processing so assets and JSON paths are served literally.
    (WEB_ROOT / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Exported {len(runs)} runs to {STATIC_ROOT}")


if __name__ == "__main__":
    main()
