"""Parse unified diffs and GitHub pull-request file payloads."""

from __future__ import annotations

import re

from app.schemas.github import ChangedFile, DiffHunk, PullRequestSnapshot

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_GIT_DIFF_HEADER = re.compile(r"^diff --git a/(.+) b/(.+)$")
_RENAME_FROM = re.compile(r"^rename from (.+)$")
_RENAME_TO = re.compile(r"^rename to (.+)$")
_PLUS_PLUS_PLUS = re.compile(r"^\+\+\+ (?:b/)?(.+)$")
_MINUS_MINUS_MINUS = re.compile(r"^--- (?:a/)?(.+)$")


def parse_patch(patch: str | None) -> list[DiffHunk]:
    """Extract hunks and changed line numbers from a GitHub `patch` string."""

    if not patch:
        return []

    hunks: list[DiffHunk] = []
    current: DiffHunk | None = None
    old_line = 0
    new_line = 0

    for raw_line in patch.splitlines():
        header_match = _HUNK_HEADER.match(raw_line)
        if header_match:
            old_start = int(header_match.group(1))
            old_count = int(header_match.group(2) or "1")
            new_start = int(header_match.group(3))
            new_count = int(header_match.group(4) or "1")
            current = DiffHunk(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                header=raw_line,
            )
            hunks.append(current)
            old_line = old_start
            new_line = new_start
            continue
        if current is None:
            continue
        if raw_line.startswith("\\"):
            continue
        if raw_line.startswith("+"):
            current.added_line_numbers.append(new_line)
            new_line += 1
        elif raw_line.startswith("-"):
            current.removed_line_numbers.append(old_line)
            old_line += 1
        else:
            old_line += 1
            new_line += 1
    return hunks


def changed_file_from_github(payload: dict) -> ChangedFile:
    """Convert a GitHub `pulls/.../files` item into a structured changed file."""

    path = str(payload.get("filename") or "")
    previous = payload.get("previous_filename")
    patch = payload.get("patch")
    return ChangedFile(
        path=path,
        previous_path=str(previous) if previous else None,
        status=str(payload.get("status") or "modified"),
        additions=int(payload.get("additions") or 0),
        deletions=int(payload.get("deletions") or 0),
        sha=str(payload["sha"]) if payload.get("sha") else None,
        patch=patch if isinstance(patch, str) else None,
        hunks=parse_patch(patch if isinstance(patch, str) else None),
    )


def parse_unified_diff(diff_text: str) -> list[ChangedFile]:
    """Parse a raw unified diff (`git diff` / GitHub `vnd.github.diff`)."""

    if not diff_text.strip():
        return []

    files: list[ChangedFile] = []
    current_path: str | None = None
    previous_path: str | None = None
    status = "modified"
    patch_lines: list[str] = []

    def flush() -> None:
        nonlocal current_path, previous_path, status, patch_lines
        if not current_path:
            return
        patch = "\n".join(patch_lines) if patch_lines else None
        hunks = parse_patch(patch)
        files.append(
            ChangedFile(
                path=current_path,
                previous_path=previous_path,
                status=status,
                patch=patch,
                hunks=hunks,
                additions=sum(len(hunk.added_line_numbers) for hunk in hunks),
                deletions=sum(len(hunk.removed_line_numbers) for hunk in hunks),
            )
        )
        current_path = None
        previous_path = None
        status = "modified"
        patch_lines = []

    for line in diff_text.splitlines():
        git_header = _GIT_DIFF_HEADER.match(line)
        if git_header:
            flush()
            previous_path = git_header.group(1)
            current_path = git_header.group(2)
            if previous_path == current_path:
                previous_path = None
            continue
        rename_from = _RENAME_FROM.match(line)
        if rename_from:
            previous_path = rename_from.group(1)
            status = "renamed"
            continue
        rename_to = _RENAME_TO.match(line)
        if rename_to:
            current_path = rename_to.group(1)
            status = "renamed"
            continue
        if line.startswith("new file mode"):
            status = "added"
            previous_path = None
            continue
        if line.startswith("deleted file mode"):
            status = "removed"
            continue
        plus_header = _PLUS_PLUS_PLUS.match(line)
        if plus_header and plus_header.group(1) != "/dev/null":
            current_path = plus_header.group(1)
        minus_header = _MINUS_MINUS_MINUS.match(line)
        if minus_header and minus_header.group(1) != "/dev/null" and status == "renamed":
            previous_path = minus_header.group(1)
        if line.startswith("@@") or (patch_lines and (line[:1] in {"+", "-", " ", "\\"})):
            patch_lines.append(line)

    flush()
    return files


def snapshot_to_dict(snapshot: PullRequestSnapshot) -> list[dict]:
    return [item.model_dump() for item in snapshot.changed_files]
