"""Normalized static-analysis results. Tool output is mapped into this shape."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ToolIssue(BaseModel):
    tool: str
    file: str
    line: int | None = None
    column: int | None = None
    rule: str | None = None
    message: str
    severity: str | None = None


class ToolRun(BaseModel):
    tool: str
    command: list[str]
    exit_code: int | None = None
    available: bool = True
    stdout: str = ""
    stderr: str = ""
    issues: list[ToolIssue] = Field(default_factory=list)
    error: str | None = None


class StaticAnalysisReport(BaseModel):
    workspace_files: list[str] = Field(default_factory=list)
    runs: list[ToolRun] = Field(default_factory=list)

    @property
    def issues(self) -> list[ToolIssue]:
        return [issue for run in self.runs for issue in run.issues]
