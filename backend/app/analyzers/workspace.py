"""Write untrusted PR files into an isolated workspace."""

from __future__ import annotations

from pathlib import Path

from app.analyzers.language import should_skip_path
from app.core.logging import get_logger

logger = get_logger(__name__)

MAX_FILE_BYTES = 512_000
BLOCKED_NAMES = {".env", ".env.local", ".pem", ".key"}


class UnsafePathError(ValueError):
    pass


def confined_path(root: Path, relative: str) -> Path:
    """Map a repo-relative path into `root`. Reject absolute paths and `..`."""

    raw = relative.replace("\\", "/")
    if Path(relative).is_absolute() or raw.startswith("/") or raw.startswith("~"):
        raise UnsafePathError(relative)
    candidate = raw
    while candidate.startswith("./"):
        candidate = candidate[2:]
    if candidate.startswith("/"):
        raise UnsafePathError(relative)
    if not candidate:
        raise UnsafePathError(relative)
    parts = Path(candidate).parts
    if any(part in {"..", ""} for part in parts):
        raise UnsafePathError(relative)
    root_resolved = root.resolve()
    destination = (root_resolved / candidate).resolve()
    try:
        destination.relative_to(root_resolved)
    except ValueError as exc:
        raise UnsafePathError(relative) from exc
    return destination


def should_materialize(path: str) -> bool:
    name = Path(path.replace("\\", "/")).name.lower()
    if name in BLOCKED_NAMES or name.startswith(".env") or name.endswith(".pem") or name.endswith(".key"):
        return False
    if should_skip_path(path):
        return False
    return True


def materialize_files(root: Path, files: dict[str, str]) -> list[str]:
    """Write text files under `root`. Returns repo-relative paths that were written."""

    written: list[str] = []
    root.mkdir(parents=True, exist_ok=True)
    for relative, content in files.items():
        if not should_materialize(relative):
            continue
        encoded = content.encode("utf-8", errors="replace")
        if len(encoded) > MAX_FILE_BYTES:
            logger.warning("static_analysis_file_skipped_too_large")
            continue
        destination = confined_path(root, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        written.append(relative.replace("\\", "/"))
    return written
