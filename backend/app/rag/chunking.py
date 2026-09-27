"""Code-aware chunking. Python uses the AST; other languages use structure-aware fallbacks."""

from __future__ import annotations

import ast
import re
from pathlib import PurePosixPath

from app.analyzers.language import classify_file, detect_language, normalize_path
from app.core.logging import redact
from app.schemas.rag import CodeChunk

MAX_CHUNK_CHARS = 4_000
_JS_SYMBOL = re.compile(
    r"^(?P<indent>\s*)(?:export\s+)?(?:async\s+)?(?:function\s+|class\s+|const\s+|let\s+|var\s+)(?P<name>[A-Za-z0-9_]+)",
    re.MULTILINE,
)
_MD_HEADING = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
_GUIDELINE_NAMES = {
    "contributing.md",
    "code_of_conduct.md",
    "architecture.md",
    "agents.md",
    "coding-guidelines.md",
}


def _lines(text: str) -> list[str]:
    return text.splitlines()


def _slice(lines: list[str], start: int, end: int) -> str:
    return "\n".join(lines[start - 1 : end])


def _truncate(text: str) -> str:
    redacted = redact(text)
    if len(redacted) <= MAX_CHUNK_CHARS:
        return redacted
    return redacted[:MAX_CHUNK_CHARS] + "\n... [chunk truncated]"


def _chunk(
    *,
    repository: str,
    commit_sha: str,
    file_path: str,
    language: str | None,
    kind: str,
    symbol: str | None,
    start_line: int,
    end_line: int,
    text: str,
) -> CodeChunk:
    return CodeChunk(
        repository=repository,
        commit_sha=commit_sha,
        file_path=file_path,
        language=language,
        kind=kind,
        symbol=symbol,
        start_line=max(1, start_line),
        end_line=max(start_line, end_line),
        text=_truncate(text),
    )


def chunk_python(path: str, source: str, *, repository: str, commit_sha: str) -> list[CodeChunk]:
    """Split a Python module into module, class, and function chunks with line ranges."""

    lines = _lines(source)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return chunk_by_blocks(path, source, language="python", repository=repository, commit_sha=commit_sha)

    chunks: list[CodeChunk] = []
    if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(getattr(tree.body[0], "value", None), ast.Constant):
        doc_end = getattr(tree.body[0], "end_lineno", 1) or 1
        chunks.append(
            _chunk(
                repository=repository,
                commit_sha=commit_sha,
                file_path=path,
                language="python",
                kind="documentation",
                symbol=PurePosixPath(path).stem,
                start_line=1,
                end_line=doc_end,
                text=_slice(lines, 1, doc_end),
            )
        )

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = int(getattr(node, "lineno", 1))
            end = int(getattr(node, "end_lineno", start) or start)
            chunks.append(
                _chunk(
                    repository=repository,
                    commit_sha=commit_sha,
                    file_path=path,
                    language="python",
                    kind="function",
                    symbol=node.name,
                    start_line=start,
                    end_line=end,
                    text=_slice(lines, start, end),
                )
            )
        elif isinstance(node, ast.ClassDef):
            class_start = int(getattr(node, "lineno", 1))
            class_end = int(getattr(node, "end_lineno", class_start) or class_start)
            chunks.append(
                _chunk(
                    repository=repository,
                    commit_sha=commit_sha,
                    file_path=path,
                    language="python",
                    kind="class",
                    symbol=node.name,
                    start_line=class_start,
                    end_line=class_end,
                    text=_slice(lines, class_start, class_end),
                )
            )
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    start = int(getattr(child, "lineno", class_start))
                    end = int(getattr(child, "end_lineno", start) or start)
                    chunks.append(
                        _chunk(
                            repository=repository,
                            commit_sha=commit_sha,
                            file_path=path,
                            language="python",
                            kind="function",
                            symbol=f"{node.name}.{child.name}",
                            start_line=start,
                            end_line=end,
                            text=_slice(lines, start, end),
                        )
                    )
    if not chunks:
        return chunk_by_blocks(path, source, language="python", repository=repository, commit_sha=commit_sha)
    return chunks


def chunk_markdown(path: str, source: str, *, repository: str, commit_sha: str) -> list[CodeChunk]:
    lines = _lines(source)
    if not lines:
        return []
    headings = [(match.start(), match.group(2).strip()) for match in _MD_HEADING.finditer(source)]
    if not headings:
        return [
            _chunk(
                repository=repository,
                commit_sha=commit_sha,
                file_path=path,
                language="markdown",
                kind="documentation",
                symbol=PurePosixPath(path).name,
                start_line=1,
                end_line=len(lines),
                text=source,
            )
        ]
    chunks: list[CodeChunk] = []
    positions = [0]
    for match in _MD_HEADING.finditer(source):
        positions.append(match.start())
    positions.append(len(source))
    for index in range(len(positions) - 1):
        start_char = positions[index]
        end_char = positions[index + 1]
        block = source[start_char:end_char].strip("\n")
        if not block:
            continue
        start_line = source[:start_char].count("\n") + 1
        end_line = start_line + block.count("\n")
        heading = _MD_HEADING.match(block)
        symbol = heading.group(2).strip() if heading else PurePosixPath(path).stem
        chunks.append(
            _chunk(
                repository=repository,
                commit_sha=commit_sha,
                file_path=path,
                language="markdown",
                kind="documentation",
                symbol=symbol,
                start_line=start_line,
                end_line=end_line,
                text=block,
            )
        )
    return chunks


def chunk_javascript(path: str, source: str, *, repository: str, commit_sha: str) -> list[CodeChunk]:
    lines = _lines(source)
    matches = list(_JS_SYMBOL.finditer(source))
    if not matches:
        return chunk_by_blocks(path, source, language=detect_language(path), repository=repository, commit_sha=commit_sha)
    chunks: list[CodeChunk] = []
    for index, match in enumerate(matches):
        start_line = source[: match.start()].count("\n") + 1
        end_char = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        end_line = source[:end_char].count("\n") or start_line
        chunks.append(
            _chunk(
                repository=repository,
                commit_sha=commit_sha,
                file_path=path,
                language=detect_language(path) or "javascript",
                kind="function",
                symbol=match.group("name"),
                start_line=start_line,
                end_line=max(start_line, end_line),
                text=_slice(lines, start_line, max(start_line, end_line)),
            )
        )
    return chunks


def chunk_by_blocks(
    path: str,
    source: str,
    *,
    language: str | None,
    repository: str,
    commit_sha: str,
    kind: str = "source",
) -> list[CodeChunk]:
    """Fallback: keep blank-line separated regions with real line numbers."""

    lines = _lines(source)
    if not lines:
        return []
    chunks: list[CodeChunk] = []
    start = 1
    current: list[str] = []
    for index, line in enumerate(lines, start=1):
        if line.strip():
            if not current:
                start = index
            current.append(line)
            continue
        if current:
            chunks.append(
                _chunk(
                    repository=repository,
                    commit_sha=commit_sha,
                    file_path=path,
                    language=language,
                    kind=kind,
                    symbol=None,
                    start_line=start,
                    end_line=index - 1,
                    text="\n".join(current),
                )
            )
            current = []
    if current:
        chunks.append(
            _chunk(
                repository=repository,
                commit_sha=commit_sha,
                file_path=path,
                language=language,
                kind=kind,
                symbol=None,
                start_line=start,
                end_line=len(lines),
                text="\n".join(current),
            )
        )
    return chunks


def chunk_file(
    path: str,
    source: str,
    *,
    repository: str,
    commit_sha: str,
) -> list[CodeChunk]:
    """Choose a chunker from language and file kind. Never uses naive fixed windows first."""

    path = normalize_path(path)
    classification = classify_file(path)
    language = classification.language
    name = PurePosixPath(path).name.lower()
    if language == "python":
        return chunk_python(path, source, repository=repository, commit_sha=commit_sha)
    if language == "markdown" or name in _GUIDELINE_NAMES or classification.kind.value == "documentation":
        return chunk_markdown(path, source, repository=repository, commit_sha=commit_sha)
    if language in {"javascript", "typescript"}:
        return chunk_javascript(path, source, repository=repository, commit_sha=commit_sha)
    kind = classification.kind.value
    if kind in {"configuration", "infrastructure"}:
        return chunk_by_blocks(
            path,
            source,
            language=language,
            repository=repository,
            commit_sha=commit_sha,
            kind="configuration",
        )
    return chunk_by_blocks(path, source, language=language, repository=repository, commit_sha=commit_sha, kind=kind)
