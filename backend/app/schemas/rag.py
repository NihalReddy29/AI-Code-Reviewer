"""RAG document and retrieval schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CodeChunk(BaseModel):
    repository: str
    commit_sha: str
    file_path: str
    language: str | None = None
    kind: str = "source"
    symbol: str | None = None
    start_line: int
    end_line: int
    text: str

    def identity_key(self) -> str:
        return f"{self.repository}:{self.commit_sha}:{self.file_path}:{self.start_line}:{self.symbol or ''}"


class RetrievedChunk(BaseModel):
    file_path: str
    language: str | None = None
    symbol: str | None = None
    start_line: int
    end_line: int
    score: float
    text: str
    kind: str = "source"


class RetrievalHit(BaseModel):
    chunk: RetrievedChunk
    reasons: list[str] = Field(default_factory=list)
