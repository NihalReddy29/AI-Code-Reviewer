"""Retrieve chunks relevant to changed functions and classes."""

from __future__ import annotations

import re

from app.core.logging import redact
from app.rag.embeddings import Embedder
from app.rag.indexer import QdrantStore
from app.schemas.github import ChangedFile
from app.schemas.rag import RetrievedChunk

_DEF = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
_CLASS = re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
_HUNK_CONTEXT = re.compile(r"@@ .* @@\s*(?:(?:async\s+)?def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")
_JS_FN = re.compile(r"\b(?:function|class|const|let)\s+([A-Za-z_][A-Za-z0-9_]*)")


def extract_changed_symbols(changed_files: list[ChangedFile]) -> list[str]:
    symbols: list[str] = []
    for item in changed_files:
        patch = item.patch or ""
        symbols.extend(_DEF.findall(patch))
        symbols.extend(_CLASS.findall(patch))
        symbols.extend(_HUNK_CONTEXT.findall(patch))
        symbols.extend(_JS_FN.findall(patch))
    return list(dict.fromkeys(symbols))


def build_queries(changed_files: list[ChangedFile]) -> list[tuple[ChangedFile, str, list[int]]]:
    queries: list[tuple[ChangedFile, str, list[int]]] = []
    for item in changed_files:
        symbols = extract_changed_symbols([item])
        changed_lines: list[int] = []
        for hunk in item.hunks:
            changed_lines.extend(hunk.added_line_numbers)
        patch = redact((item.patch or "")[:1_500])
        query = " ".join(
            [
                item.path,
                " ".join(symbols),
                " ".join(item.related_paths[:6]),
                patch,
            ]
        ).strip()
        queries.append((item, query, changed_lines))
    return queries


def _rerank(
    hits: list[RetrievedChunk],
    *,
    changed_file: ChangedFile,
    changed_lines: list[int],
    symbols: list[str],
    limit: int,
) -> list[RetrievedChunk]:
    symbol_set = set(symbols)
    related = set(changed_file.related_paths)
    scored: list[RetrievedChunk] = []
    for hit in hits:
        score = hit.score
        reasons: list[str] = []
        if hit.file_path == changed_file.path:
            score += 0.35
            reasons.append("same_file")
            if changed_lines and hit.start_line <= max(changed_lines) and hit.end_line >= min(changed_lines):
                score += 0.45
                reasons.append("line_overlap")
        elif hit.file_path in related:
            score += 0.2
            reasons.append("related_path")
        if hit.symbol and (hit.symbol in symbol_set or any(hit.symbol.endswith(f".{name}") or hit.symbol == name for name in symbol_set)):
            score += 0.3
            reasons.append("symbol_match")
        scored.append(hit.model_copy(update={"score": score}))
    scored.sort(key=lambda item: item.score, reverse=True)
    unique: list[RetrievedChunk] = []
    seen: set[tuple[str, int, int]] = set()
    for hit in scored:
        key = (hit.file_path, hit.start_line, hit.end_line)
        if key in seen:
            continue
        seen.add(key)
        unique.append(hit)
        if len(unique) >= limit:
            break
    return unique


def retrieve_for_pull_request(
    store: QdrantStore,
    embedder: Embedder,
    *,
    repository: str,
    changed_files: list[ChangedFile],
    limit: int = 6,
) -> list[RetrievedChunk]:
    """Return chunks around the changed function/class, then related docs/tests."""

    combined: list[RetrievedChunk] = []
    for changed_file, query, changed_lines in build_queries(changed_files):
        if not query:
            continue
        vector = embedder.embed_query(query)
        raw = store.search(vector, repository=repository, limit=limit)
        symbols = extract_changed_symbols([changed_file])
        combined.extend(
            _rerank(
                raw,
                changed_file=changed_file,
                changed_lines=changed_lines,
                symbols=symbols,
                limit=limit,
            )
        )
    unique: list[RetrievedChunk] = []
    seen: set[tuple[str, int, int]] = set()
    for hit in sorted(combined, key=lambda item: item.score, reverse=True):
        key = (hit.file_path, hit.start_line, hit.end_line)
        if key in seen or not hit.text.strip():
            continue
        seen.add(key)
        unique.append(hit)
        if len(unique) >= limit:
            break
    return unique
