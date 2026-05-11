"""
Supervisor agent: analyses the research query and produces a structured plan
that downstream agents follow.
"""

import time
from datetime import datetime, timezone

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from logging_db import get_logger
from state import ResearchState


class SupervisorPlan(BaseModel):
    needs_code_execution: bool = Field(
        description="True when quantitative analysis, simulation, or computation would strengthen the answer."
    )
    search_query: str = Field(
        description="Optimised ArXiv search query (keywords + optional field tags)."
    )
    analysis_description: str = Field(
        description="If needs_code_execution is true: concise description of what the Python code should compute."
    )
    reasoning: str = Field(
        description="One-sentence rationale for this plan."
    )


_SYSTEM = """\
You are the research supervisor for a scientific literature and analysis workflow.
Given a research query, produce a structured plan:
1. A well-optimised ArXiv search query (use field prefixes like ti:, abs: when helpful).
2. Whether a Python data-analysis step would add value (e.g. statistics, curve fitting, simulations).
3. If yes, a brief description of what that analysis should compute.
Respond ONLY via the structured output schema — no free text.
"""


def supervisor_node(state: ResearchState) -> dict:
    logger = get_logger()
    run_id = state["run_id"]
    t0 = time.perf_counter()
    start_time = datetime.now(timezone.utc).isoformat()

    llm = ChatAnthropic(model="claude-sonnet-4-20250514", temperature=0)
    structured_llm = llm.with_structured_output(SupervisorPlan)

    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=f"Research query: {state['query']}"),
    ]

    error: str | None = None
    plan = SupervisorPlan(
        needs_code_execution=False,
        search_query=state["query"],
        analysis_description="",
        reasoning="Fallback plan.",
    )
    try:
        plan = structured_llm.invoke(messages)
    except Exception as exc:
        error = str(exc)

    duration_ms = round((time.perf_counter() - t0) * 1000, 1)

    logger.log_agent_call(
        run_id=run_id,
        agent_name="supervisor",
        input_summary=state["query"],
        output_summary=f"search_query={plan.search_query!r} needs_code={plan.needs_code_execution}",
        start_time=start_time,
        duration_ms=duration_ms,
        error=error,
    )
    logger.log_state_transition(run_id, "START", "supervisor", state)

    return {
        "supervisor_plan": plan.model_dump(),
        "needs_code": plan.needs_code_execution,
        "search_query": plan.search_query,
        "analysis_description": plan.analysis_description,
        "current_step": "supervisor",
        "step_count": state.get("step_count", 0) + 1,
        "errors": state.get("errors", []) + ([error] if error else []),
    }
