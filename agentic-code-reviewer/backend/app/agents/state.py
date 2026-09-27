from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentState:
    repo: str = ''
    pull_request: int | None = None
    findings: list[dict[str, Any]] = field(default_factory=list)
    status: str = 'pending'
