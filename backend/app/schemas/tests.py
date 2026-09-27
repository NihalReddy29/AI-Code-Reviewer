"""Test-run results. Parsed from JUnit XML produced by pytest."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TestCaseResult(BaseModel):
    __test__ = False
    nodeid: str
    file: str | None = None
    outcome: str
    message: str | None = None
    duration_seconds: float | None = None


class TestRunReport(BaseModel):
    __test__ = False
    runner: str = "pytest"
    available: bool = True
    skipped: bool = False
    skip_reason: str | None = None
    discovered: list[str] = Field(default_factory=list)
    executed: list[str] = Field(default_factory=list)
    exit_code: int | None = None
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped_cases: int = 0
    cases: list[TestCaseResult] = Field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    error: str | None = None

    @property
    def failed_cases(self) -> list[TestCaseResult]:
        return [case for case in self.cases if case.outcome in {"failed", "error"}]
