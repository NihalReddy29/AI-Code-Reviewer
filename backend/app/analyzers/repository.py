"""Repository layout and changed-file analysis from a commit tree."""

from __future__ import annotations

from collections import Counter
from pathlib import PurePosixPath

from pydantic import BaseModel, Field

from app.analyzers.language import (
    FileKind,
    classify_file,
    language_counts,
    normalize_path,
    should_skip_path,
)
from app.schemas.github import ChangedFile

SENSITIVE_PATH_MARKERS = (
    "auth",
    "oauth",
    "jwt",
    "password",
    "secret",
    "crypto",
    "payment",
    "billing",
    "permission",
    "rbac",
    "sql",
    "subprocess",
    "exec",
    "pickle",
    "serialize",
)


class RepositoryLayout(BaseModel):
    """High-level view of a repository at a commit. No file contents required."""

    file_count: int
    truncated: bool = False
    skipped_vendor_files: int = 0
    languages: dict[str, int] = Field(default_factory=dict)
    primary_language: str | None = None
    project_types: list[str] = Field(default_factory=list)
    source_roots: list[str] = Field(default_factory=list)
    test_directories: list[str] = Field(default_factory=list)
    documentation_files: list[str] = Field(default_factory=list)
    ci_files: list[str] = Field(default_factory=list)
    config_files: list[str] = Field(default_factory=list)
    has_docker: bool = False
    has_github_actions: bool = False


class ChangedFileAnalysis(BaseModel):
    path: str
    language: str | None
    kind: FileKind
    is_test: bool
    related_paths: list[str] = Field(default_factory=list)
    hunk_count: int = 0
    added_line_count: int = 0
    removed_line_count: int = 0
    sensitive_areas: list[str] = Field(default_factory=list)


def _path_set(paths: list[str]) -> set[str]:
    return {normalize_path(path) for path in paths if not should_skip_path(path)}


def detect_project_types(paths: list[str]) -> list[str]:
    names = {PurePosixPath(normalize_path(path)).name.lower() for path in paths}
    posix_paths = {normalize_path(path).lower() for path in paths}
    found: list[str] = []
    if {"pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "pipfile"} & names:
        found.append("python")
    if "package.json" in names:
        found.append("node")
    if "go.mod" in names:
        found.append("go")
    if "cargo.toml" in names:
        found.append("rust")
    if any(name.startswith("dockerfile") for name in names) or any(
        name.startswith("docker-compose") for name in names
    ):
        found.append("docker")
    if any(path.endswith("/manage.py") or path == "manage.py" for path in posix_paths):
        found.append("django")
    if any("fastapi" in path for path in posix_paths):
        found.append("fastapi")
    return found


def _source_roots(paths: list[str]) -> list[str]:
    counter: Counter[str] = Counter()
    for path in paths:
        classification = classify_file(path)
        if classification.kind is not FileKind.SOURCE or should_skip_path(path):
            continue
        parts = PurePosixPath(normalize_path(path)).parts
        if len(parts) >= 2:
            counter[parts[0]] += 1
    common = {"src", "app", "backend", "frontend", "lib", "pkg", "cmd"}
    ranked = [root for root, _ in counter.most_common() if root in common or counter[root] >= 3]
    return ranked[:8]


def _directories_of_kind(paths: list[str], kind: FileKind) -> list[str]:
    dirs: set[str] = set()
    for path in paths:
        if classify_file(path).kind is not kind:
            continue
        parent = str(PurePosixPath(normalize_path(path)).parent)
        if parent not in {".", ""}:
            dirs.add(parent)
    return sorted(dirs)[:30]


def analyze_repository(paths: list[str], *, truncated: bool = False) -> RepositoryLayout:
    """Classify files, languages, and project shape from a git tree path list."""

    skipped = sum(1 for path in paths if should_skip_path(path))
    usable = [normalize_path(path) for path in paths if not should_skip_path(path)]
    languages = language_counts(usable)
    primary = next(iter(languages), None)
    docs = [path for path in usable if classify_file(path).kind is FileKind.DOCUMENTATION][:40]
    ci = [path for path in usable if classify_file(path).kind is FileKind.CI][:40]
    config = [path for path in usable if classify_file(path).kind is FileKind.CONFIGURATION][:40]
    names = {PurePosixPath(path).name.lower() for path in usable}
    return RepositoryLayout(
        file_count=len(usable),
        truncated=truncated,
        skipped_vendor_files=skipped,
        languages=languages,
        primary_language=primary,
        project_types=detect_project_types(usable),
        source_roots=_source_roots(usable),
        test_directories=_directories_of_kind(usable, FileKind.TEST),
        documentation_files=docs,
        ci_files=ci,
        config_files=config,
        has_docker=any(name.startswith("dockerfile") or name.startswith("docker-compose") for name in names),
        has_github_actions=any(path.startswith(".github/workflows/") for path in usable),
    )


def related_test_paths(source_path: str, tree_paths: set[str]) -> list[str]:
    posix = PurePosixPath(normalize_path(source_path))
    stem = posix.stem
    if stem.startswith("test_") or stem.endswith("_test"):
        return []
    parent = posix.parent.as_posix()
    candidates = [
        f"{parent}/test_{posix.name}",
        f"{parent}/{stem}_test{posix.suffix}",
        f"{parent}/tests/test_{posix.name}",
        f"tests/test_{posix.name}",
        f"test/test_{posix.name}",
        f"{posix.parts[0]}/tests/test_{posix.name}" if posix.parts else "",
    ]
    matches = [path for path in candidates if path and path in tree_paths]
    extra = [
        path
        for path in tree_paths
        if classify_file(path).is_test
        and PurePosixPath(path).stem in {f"test_{stem}", f"{stem}_test"}
    ]
    return sorted(set(matches + extra))


def related_source_paths(test_path: str, tree_paths: set[str]) -> list[str]:
    posix = PurePosixPath(normalize_path(test_path))
    stem = posix.stem
    if stem.startswith("test_"):
        source_stem = stem.removeprefix("test_")
    elif stem.endswith("_test"):
        source_stem = stem.removesuffix("_test")
    else:
        return []
    source_name = f"{source_stem}{posix.suffix}"
    hits = [path for path in tree_paths if PurePosixPath(path).name == source_name and not classify_file(path).is_test]
    return sorted(hits)[:10]


SQL_HINTS = ("select ", "insert ", "update ", "delete from", "execute(", "cursor.execute")


def _sensitive_areas(path: str, patch: str | None) -> list[str]:
    haystack = normalize_path(path).lower()
    patch_text = patch.lower() if patch else ""
    combined = f"{haystack}\n{patch_text}"
    found = [marker for marker in SENSITIVE_PATH_MARKERS if marker in combined]
    if any(hint in combined for hint in SQL_HINTS) and "sql" not in found:
        found.append("sql")
    return found


def analyze_changed_files(changed_files: list[ChangedFile], tree_paths: list[str]) -> list[ChangedFile]:
    """Attach language, kind, related tests, and diff stats to each changed file."""

    path_set = _path_set(tree_paths)
    enriched: list[ChangedFile] = []
    for item in changed_files:
        classification = classify_file(item.path)
        related: list[str] = []
        if classification.is_test:
            related = related_source_paths(item.path, path_set)
        else:
            related = related_test_paths(item.path, path_set)
        added = sum(len(hunk.added_line_numbers) for hunk in item.hunks) or item.additions
        removed = sum(len(hunk.removed_line_numbers) for hunk in item.hunks) or item.deletions
        analysis = ChangedFileAnalysis(
            path=item.path,
            language=classification.language,
            kind=classification.kind,
            is_test=classification.is_test,
            related_paths=related,
            hunk_count=len(item.hunks),
            added_line_count=added,
            removed_line_count=removed,
            sensitive_areas=_sensitive_areas(item.path, item.patch),
        )
        enriched.append(
            item.model_copy(
                update={
                    "language": analysis.language,
                    "kind": analysis.kind.value,
                    "is_test": analysis.is_test,
                    "related_paths": analysis.related_paths,
                    "hunk_count": analysis.hunk_count,
                    "sensitive_areas": analysis.sensitive_areas,
                }
            )
        )
    return enriched
