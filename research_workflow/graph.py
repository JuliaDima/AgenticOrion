"""
LangGraph workflow graph: wires supervisor → literature → [code_executor] → synthesis.
"""

import sys
import os

# Ensure sibling modules resolve when graph.py is imported from sub-directories
sys.path.insert(0, os.path.dirname(__file__))

from langgraph.graph import END, START, StateGraph

from agents.code_executor import code_executor_node
from agents.literature import literature_node
from agents.supervisor import supervisor_node
from agents.synthesis import synthesis_node
from state import ResearchState


def _route_after_literature(state: ResearchState) -> str:
    """Send to code_executor if the supervisor requested it, otherwise skip to synthesis."""
    return "code_executor" if state.get("needs_code", False) else "synthesis"


def build_graph() -> StateGraph:
    g = StateGraph(ResearchState)

    g.add_node("supervisor", supervisor_node)
    g.add_node("literature", literature_node)
    g.add_node("code_executor", code_executor_node)
    g.add_node("synthesis", synthesis_node)

    g.add_edge(START, "supervisor")
    g.add_edge("supervisor", "literature")
    g.add_conditional_edges(
        "literature",
        _route_after_literature,
        {"code_executor": "code_executor", "synthesis": "synthesis"},
    )
    g.add_edge("code_executor", "synthesis")
    g.add_edge("synthesis", END)

    return g.compile()
