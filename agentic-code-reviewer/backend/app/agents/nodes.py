from __future__ import annotations

from app.agents.state import AgentState


def analyze_code(state: AgentState) -> AgentState:
    state.status = 'analyzing'
    return state


def synthesize_report(state: AgentState) -> AgentState:
    state.status = 'ready'
    return state
