"""
Context Retrieval Agent (parallel branch 4 of 4).

Retrieves external context to help judge the observation:
- Searches arXiv for related papers on this object type / mission / phenomenon
- Uses LLM knowledge about catalogue context, mission properties, known failure modes
"""

import json
import time
from datetime import datetime, timezone

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from logging_db import get_logger
from state import ResearchState
from tools import extract_tokens, search_arxiv

_MODEL = "gpt-4o-mini"

_SYSTEM = """\
You are the OrionSpectrum Context Retrieval Agent.

You have been provided with:
1. An observation packet and its characterization.
2. A list of arXiv papers retrieved by a targeted search.

Your role: synthesise this context into a structured summary that will
help the downstream evidence aggregation agent interpret the observation.

Produce:
- A summary of the most relevant papers (title, finding, relevance)
- Notes on similar historical observations
- Relevant catalogue context (e.g., known object class statistics, survey rates)
- Mission/instrument specific context that helps interpret this packet
- Known failure modes or pitfalls for this mission and modality

Be factual. If a paper is about a different object class, say so and explain
why you included it. Do not fabricate paper titles or results.
"""


class PaperSummary(BaseModel):
    title: str
    key_finding: str
    relevance: str


class ContextRetrievalResults(BaseModel):
    related_papers: list[PaperSummary]
    similar_observations: list[str] = Field(
        description="Known historical analogues or similar published cases."
    )
    relevant_catalogue_context: str = Field(
        description="Statistical or catalogue context relevant to this object class."
    )
    mission_instrument_notes: str = Field(
        description="Mission-specific context helpful for interpretation."
    )
    known_failure_modes: list[str] = Field(
        description="Known pitfalls, artefact classes, or false-positive modes for this mission/modality."
    )
    arxiv_search_query: str = Field(
        description="The query used to search arXiv."
    )


def _build_arxiv_query(pkt: dict) -> str:
    mission = pkt["mission"]
    labels = pkt["initial_pipeline_labels"]
    summary = pkt["short_summary"][:120]

    # Build a focused query from mission + key labels
    mission_tokens = {
        "Rubin": "Rubin LSST transient",
        "ZTF": "ZTF transient",
        "ALeRCE": "ZTF ALeRCE broker transient",
        "Fink": "ZTF Fink broker classification",
        "JWST": "JWST NIRCam morphology classification",
        "Euclid": "Euclid strong gravitational lens survey",
        "CHIME": "CHIME FRB fast radio burst",
    }

    prefix = next(
        (v for k, v in mission_tokens.items() if k.lower() in mission.lower()),
        mission,
    )

    # Add a distinctive label
    interesting_labels = [
        l for l in labels
        if l not in ("CTRL", "reject", "low_novelty", "standard_plateau")
    ]
    label_hint = " ".join(interesting_labels[:2]) if interesting_labels else ""

    return f"{prefix} {label_hint}".strip()


def context_retriever_node(state: ResearchState) -> dict:
    logger = get_logger()
    run_id = state["run_id"]
    t0 = time.perf_counter()
    start_time = datetime.now(timezone.utc).isoformat()

    pkt = state["observation_packet"]
    char = state.get("observation_characterization") or {}

    # ArXiv search
    arxiv_query = _build_arxiv_query(pkt)
    papers_raw: list[dict] = []
    arxiv_error: str | None = None
    try:
        papers_raw = search_arxiv(arxiv_query, max_results=4)
    except Exception as exc:
        arxiv_error = str(exc)

    logger.log_tool_call(
        run_id=run_id,
        agent_name="context_retriever",
        tool_name="search_arxiv",
        input_data={"query": arxiv_query},
        output_data={"count": len(papers_raw)},
        start_time=start_time,
        duration_ms=round((time.perf_counter() - t0) * 1000, 1),
        error=arxiv_error,
    )

    papers_block = "\n\n".join(
        f"[{i+1}] {p['title']} ({p['published']})\n"
        f"Authors: {', '.join(p['authors'][:3])}\n"
        f"Abstract: {p['abstract'][:500]}"
        for i, p in enumerate(papers_raw)
    ) or "No papers retrieved."

    context = (
        f"Mission: {pkt['mission']}\n"
        f"Summary: {pkt['short_summary']}\n"
        f"Metadata: {json.dumps(pkt['metadata'], indent=2)}\n"
        f"Pipeline labels: {pkt['initial_pipeline_labels']}\n"
        f"Characterization: {char.get('one_line_summary', '')}\n"
        f"arXiv search query used: {arxiv_query!r}\n\n"
        f"Retrieved papers:\n{papers_block}"
    )

    llm = ChatOpenAI(model=_MODEL, temperature=0)
    structured_llm = llm.with_structured_output(ContextRetrievalResults, include_raw=True)

    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=context),
    ]

    error: str | None = None
    tokens: dict = {"node": "context_retriever", "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    ctx_result = ContextRetrievalResults(
        related_papers=[],
        similar_observations=[],
        relevant_catalogue_context="",
        mission_instrument_notes="",
        known_failure_modes=[],
        arxiv_search_query=arxiv_query,
    )
    try:
        raw_result = structured_llm.invoke(messages)
        ctx_result = raw_result["parsed"]
        ctx_result = ctx_result.model_copy(update={"arxiv_search_query": arxiv_query})
        tokens = extract_tokens("context_retriever", raw_result["raw"])
    except Exception as exc:
        error = str(exc) or arxiv_error

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)
    result_dict = ctx_result.model_dump()
    result_dict["branch_duration_ms"] = duration_ms
    result_dict["raw_arxiv_papers"] = papers_raw

    logger.log_agent_call(
        run_id=run_id,
        agent_name="context_retriever",
        input_summary=f"query={arxiv_query!r}",
        output_summary=f"{len(papers_raw)} papers retrieved; {len(ctx_result.related_papers)} summarised",
        start_time=start_time,
        duration_ms=duration_ms,
        error=error,
    )
    logger.log_state_transition(run_id, "observation_characterizer", "context_retriever", state)

    timing_entry = {"node": "context_retriever", "duration_ms": duration_ms, "timestamp": start_time}

    return {
        "context_retrieval_results": result_dict,
        "step_count": 1,
        "errors": [error] if error else [],
        "timing_log": [timing_entry],
        "token_counts": [tokens],
    }
