from app.agents.graph import run_agentic_review


def test_run_agentic_review_returns_state() -> None:
    state = run_agentic_review('example/repo', 42)
    assert state.repo == 'example/repo'
    assert state.pull_request == 42
    assert state.status == 'ready'
