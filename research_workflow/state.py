from typing import TypedDict, List, Optional


class ResearchState(TypedDict):
    run_id: str
    query: str
    # Supervisor outputs
    supervisor_plan: Optional[dict]
    needs_code: bool
    search_query: str
    analysis_description: str
    # Literature agent outputs
    literature_results: List[dict]
    # Code executor outputs
    code_to_execute: Optional[str]
    code_results: Optional[dict]
    # Synthesis output
    synthesis_report: Optional[str]
    # Routing / bookkeeping
    current_step: str
    errors: List[str]
    step_count: int
