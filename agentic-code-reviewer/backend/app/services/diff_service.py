from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DiffSummary:
    files_changed: int
    additions: int
    deletions: int


class DiffService:
    def summarize(self, diff_text: str) -> DiffSummary:
        additions = diff_text.count('\n+')
        deletions = diff_text.count('\n-')
        files_changed = 1 if diff_text else 0
        return DiffSummary(files_changed=files_changed, additions=additions, deletions=deletions)
