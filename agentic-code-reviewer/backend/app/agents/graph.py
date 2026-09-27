from __future__ import annotations

from app.agents.nodes import analyze_code, synthesize_report
from app.agents.state import AgentState


def run_agentic_review(repo: str, pull_request: int) -> AgentState:
    state = AgentState(repo=repo, pull_request=pull_request)
    state = analyze_code(state)
    return synthesize_report(state)
