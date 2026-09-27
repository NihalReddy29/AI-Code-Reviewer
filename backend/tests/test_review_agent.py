"""Review agent tests using a fake LLM. No provider API key is required."""

from __future__ import annotations

from app.agents.prompts import build_review_user_prompt
from app.agents.review_agent import generate_structured_review, sanitize_review
from app.analyzers.diff import changed_file_from_github
from app.schemas.findings import FindingCategory, FindingSeverity, ReviewFinding, StructuredReview
from app.schemas.github import PullRequestRef, PullRequestSnapshot
from tests.github_fixtures import FILES_JSON


class FakeLLM:
    def __init__(self, payload: StructuredReview | dict | Exception) -> None:
        self.payload = payload

    def with_structured_output(self, schema: object) -> FakeLLM:
        return self

    def invoke(self, messages: object) -> StructuredReview | dict:
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def _snapshot(patch: str | None = None) -> PullRequestSnapshot:
    item = changed_file_from_github(FILES_JSON[0])
    if patch is not None:
        item = item.model_copy(update={"patch": patch})
    return PullRequestSnapshot(
        pull_request=PullRequestRef(
            owner="acme",
            repo="api",
            number=12,
            title="Harden authentication",
            author="dev",
            source_branch="feature/auth",
            target_branch="main",
            head_sha="abc123def456",
        ),
        changed_files=[item],
        diff=item.patch or "",
    )


def _finding(**overrides: object) -> ReviewFinding:
    payload = {
        "file": "backend/services/user_service.py",
        "line": 11,
        "category": FindingCategory.SECURITY,
        "severity": FindingSeverity.HIGH,
        "title": "SQL built from user input",
        "description": "The query is formatted with a user id.",
        "evidence": "return db.execute(query)",
        "suggested_fix": "Use bound parameters.",
        "confidence": 0.93,
    }
    payload.update(overrides)
    return ReviewFinding.model_validate(payload)


def test_prompt_redacts_secrets_and_skips_env_files() -> None:
    snapshot = _snapshot(patch="Authorization: Bearer ghs_live_token_value\n+query = 1\n")
    prompt = build_review_user_prompt(snapshot, None)
    assert "ghs_live_token_value" not in prompt
    assert "[REDACTED]" in prompt


def test_sanitize_drops_findings_for_unknown_files() -> None:
    review = StructuredReview(
        summary="mixed",
        findings=[
            _finding(),
            _finding(file="totally/invented.py", title="Invented"),
        ],
    )
    cleaned = sanitize_review(review, {"backend/services/user_service.py"})
    assert len(cleaned.findings) == 1
    assert cleaned.findings[0].file.endswith("user_service.py")


def test_prompt_includes_retrieved_context() -> None:
    from app.schemas.rag import RetrievedChunk

    snapshot = _snapshot()
    retrieved = [
        RetrievedChunk(
            file_path="backend/services/user_service.py",
            language="python",
            symbol="get_user",
            start_line=10,
            end_line=12,
            score=0.9,
            text="def get_user(user_id):\n    return db.execute(query)",
        )
    ]
    prompt = build_review_user_prompt(snapshot, None, retrieved)
    assert "Retrieved repository context" in prompt
    assert "get_user" in prompt


def test_generate_structured_review_uses_injected_llm() -> None:
    snapshot = _snapshot()
    llm = FakeLLM(StructuredReview(summary="Look at SQL.", findings=[_finding()]))
    result = generate_structured_review(snapshot, None, llm=llm)
    assert result.summary == "Look at SQL."
    assert result.findings[0].severity is FindingSeverity.HIGH
