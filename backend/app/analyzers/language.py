"""Language and file-kind detection from paths. Independently testable."""

from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath

from pydantic import BaseModel


class FileKind(StrEnum):
    SOURCE = "source"
    TEST = "test"
    DOCUMENTATION = "documentation"
    CONFIGURATION = "configuration"
    LOCKFILE = "lockfile"
    CI = "ci"
    INFRASTRUCTURE = "infrastructure"
    ASSET = "asset"
    GENERATED = "generated"
    OTHER = "other"


class FileClassification(BaseModel):
    path: str
    language: str | None
    kind: FileKind
    is_test: bool = False


_EXTENSION_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".swift": "swift",
    ".scala": "scala",
    ".sh": "shell",
    ".bash": "shell",
    ".ps1": "powershell",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".md": "markdown",
    ".rst": "rst",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".xml": "xml",
    ".tf": "terraform",
    ".dockerfile": "dockerfile",
}

_FILENAME_LANGUAGE: dict[str, str] = {
    "dockerfile": "dockerfile",
    "makefile": "make",
    "cmakelists.txt": "cmake",
    "gemfile": "ruby",
    "rakefile": "ruby",
    "go.mod": "go",
    "go.sum": "go",
}

_LOCK_FILES = {
    "poetry.lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "cargo.lock",
    "go.sum",
    "composer.lock",
    "pipfile.lock",
    "uv.lock",
}

_SKIP_PATH_PARTS = {
    "node_modules",
    "vendor",
    ".git",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "coverage",
    "htmlcov",
    ".next",
    "target",
}


def normalize_path(path: str) -> str:
    posix = path.replace("\\", "/")
    while posix.startswith("./"):
        posix = posix[2:]
    return posix.lstrip("/")


def should_skip_path(path: str) -> bool:
    parts = PurePosixPath(normalize_path(path)).parts
    return any(part in _SKIP_PATH_PARTS for part in parts)


def detect_language(path: str) -> str | None:
    """Return a language id from filename or extension. None if unknown."""

    posix = PurePosixPath(normalize_path(path))
    name = posix.name.lower()
    if name in _FILENAME_LANGUAGE:
        return _FILENAME_LANGUAGE[name]
    if name.startswith("dockerfile"):
        return "dockerfile"
    suffix = posix.suffix.lower()
    if name.endswith(".d.ts"):
        return "typescript"
    return _EXTENSION_LANGUAGE.get(suffix)


def detect_kind(path: str) -> FileKind:
    posix = PurePosixPath(normalize_path(path))
    name = posix.name.lower()
    parts = {part.lower() for part in posix.parts}

    if name in _LOCK_FILES:
        return FileKind.LOCKFILE
    if ".github" in parts or name in {"jenkinsfile", ".gitlab-ci.yml"}:
        return FileKind.CI
    if name in {"dockerfile", "docker-compose.yml", "docker-compose.yaml"} or name.startswith("docker-compose"):
        return FileKind.INFRASTRUCTURE
    if name in {"makefile", "procfile"} or posix.suffix.lower() == ".tf":
        return FileKind.INFRASTRUCTURE
    if _looks_like_test(posix):
        return FileKind.TEST
    if posix.suffix.lower() in {".md", ".rst", ".adoc"} or name.startswith("readme") or "docs" in parts:
        return FileKind.DOCUMENTATION
    if posix.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".woff", ".woff2"}:
        return FileKind.ASSET
    language = detect_language(path)
    if language in {
        "python",
        "javascript",
        "typescript",
        "go",
        "rust",
        "java",
        "kotlin",
        "ruby",
        "php",
        "csharp",
        "cpp",
        "c",
        "swift",
        "scala",
        "shell",
        "sql",
    }:
        return FileKind.SOURCE
    if posix.suffix.lower() in {".toml", ".ini", ".cfg", ".yaml", ".yml", ".json"} or name.startswith(".env"):
        return FileKind.CONFIGURATION
    if language in {"markdown", "json", "yaml", "toml", "xml", "dockerfile", "make"}:
        return FileKind.CONFIGURATION if language != "markdown" else FileKind.DOCUMENTATION
    return FileKind.OTHER


def _looks_like_test(posix: PurePosixPath) -> bool:
    name = posix.name.lower()
    parts = [part.lower() for part in posix.parts[:-1]]
    if any(part in {"test", "tests", "__tests__", "spec", "specs"} for part in parts):
        return True
    stem = posix.stem.lower()
    if stem.startswith("test_") or stem.endswith("_test") or stem.endswith(".test") or stem.endswith(".spec"):
        return True
    if name.endswith(".test.ts") or name.endswith(".test.tsx") or name.endswith(".spec.ts") or name.endswith(".spec.js"):
        return True
    if name.startswith("test_") and posix.suffix.lower() == ".py":
        return True
    return False


def classify_file(path: str) -> FileClassification:
    kind = detect_kind(path)
    return FileClassification(
        path=normalize_path(path),
        language=detect_language(path),
        kind=kind,
        is_test=kind is FileKind.TEST,
    )


def language_counts(paths: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in paths:
        if should_skip_path(path):
            continue
        classification = classify_file(path)
        if classification.kind is not FileKind.SOURCE:
            continue
        if not classification.language:
            continue
        counts[classification.language] = counts.get(classification.language, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))
