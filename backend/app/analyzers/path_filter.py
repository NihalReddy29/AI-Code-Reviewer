"""Filter ignored paths out of a pull-request snapshot."""

from __future__ import annotations

import re

from pathspec import GitIgnoreSpec

_DIFF_HEADER = re.compile(r"^diff --git a/(.+?) b/(.+)$")


def build_ignore_spec(patterns):
    """Turn a list of gitignore-style patterns into a matcher (or None if empty)."""
    cleaned = [p.strip() for p in (patterns or []) if isinstance(p, str) and p.strip()]
    if not cleaned:
        return None
    return GitIgnoreSpec.from_lines(cleaned)


def file_path(changed_file) -> str:
    return getattr(changed_file, "path", None) or getattr(changed_file, "filename", None) or ""


def filter_diff(diff, spec):
    """Remove the sections of a unified diff that belong to ignored files."""
    if spec is None or not diff:
        return diff
    kept = []
    keep = True
    for line in diff.splitlines(keepends=True):
        match = _DIFF_HEADER.match(line.rstrip("\r\n"))
        if match:
            keep = not spec.match_file(match.group(2))
        if keep:
            kept.append(line)
    return "".join(kept)


def filter_snapshot(snapshot, spec):
    """Return (snapshot, number_of_files_removed). Unchanged if nothing matched."""
    if spec is None:
        return snapshot, 0
    kept = [f for f in snapshot.changed_files if not spec.match_file(file_path(f))]
    removed = len(snapshot.changed_files) - len(kept)
    if removed == 0:
        return snapshot, 0
    updated = snapshot.model_copy(
        update={"changed_files": kept, "diff": filter_diff(snapshot.diff, spec)}
    )
    return updated, removed