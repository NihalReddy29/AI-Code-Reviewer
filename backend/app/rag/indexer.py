"""Qdrant vector store wrapper."""

from __future__ import annotations

import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from app.core.config import Settings, get_settings
from app.core.logging import get_logger, log_event
from app.schemas.rag import CodeChunk, RetrievedChunk

logger = get_logger(__name__)


class QdrantStore:
    def __init__(self, client: QdrantClient, collection: str, dimensions: int) -> None:
        self.client = client
        self.collection = collection
        self.dimensions = dimensions
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        existing = {item.name for item in self.client.get_collections().collections}
        if self.collection in existing:
            return
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=self.dimensions, distance=Distance.COSINE),
        )

    def upsert(self, chunks: list[CodeChunk], vectors: list[list[float]]) -> int:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must be the same length")
        points = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, chunk.identity_key()))
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "repository": chunk.repository,
                        "commit_sha": chunk.commit_sha,
                        "file_path": chunk.file_path,
                        "language": chunk.language,
                        "kind": chunk.kind,
                        "symbol": chunk.symbol,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "text": chunk.text,
                    },
                )
            )
        if not points:
            return 0
        self.client.upsert(collection_name=self.collection, points=points)
        log_event(logger, "rag_indexed", count=len(points), collection=self.collection)
        return len(points)

    def search(
        self,
        vector: list[float],
        *,
        repository: str,
        limit: int = 8,
    ) -> list[RetrievedChunk]:
        results = self.client.search(
            collection_name=self.collection,
            query_vector=vector,
            query_filter=Filter(
                must=[FieldCondition(key="repository", match=MatchValue(value=repository))]
            ),
            limit=limit * 3,
            with_payload=True,
        )
        hits: list[RetrievedChunk] = []
        for item in results:
            payload: dict[str, Any] = dict(item.payload or {})
            hits.append(
                RetrievedChunk(
                    file_path=str(payload.get("file_path") or ""),
                    language=payload.get("language"),
                    symbol=payload.get("symbol"),
                    start_line=int(payload.get("start_line") or 1),
                    end_line=int(payload.get("end_line") or 1),
                    score=float(item.score or 0.0),
                    text=str(payload.get("text") or ""),
                    kind=str(payload.get("kind") or "source"),
                )
            )
        return hits[: limit * 3]


def build_qdrant_store(dimensions: int, settings: Settings | None = None) -> QdrantStore:
    settings = settings or get_settings()
    url = settings.qdrant_url.strip()
    api_key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
    if url in {":memory:", "memory"} or settings.environment == "test":
        client = QdrantClient(location=":memory:")
    else:
        client = QdrantClient(url=url, api_key=api_key, timeout=settings.tool_timeout_seconds)
    return QdrantStore(client, settings.qdrant_collection, dimensions)


def select_index_paths(tree_paths: list[str], changed_files: list) -> list[str]:
    """Prefer changed files, related tests/sources, and project documentation."""

    from pathlib import PurePosixPath

    from app.analyzers.language import classify_file, should_skip_path
    from app.schemas.github import ChangedFile

    doc_names = {
        "readme.md",
        "readme.rst",
        "contributing.md",
        "architecture.md",
        "agents.md",
        "security.md",
        "code_of_conduct.md",
    }
    selected: list[str] = []
    seen: set[str] = set()

    def add(path: str) -> None:
        normalized = path.replace("\\", "/").lstrip("/")
        if not normalized or normalized in seen or should_skip_path(normalized):
            return
        kind = classify_file(normalized).kind.value
        if kind in {"lockfile", "asset", "generated"}:
            return
        seen.add(normalized)
        selected.append(normalized)

    for item in changed_files:
        add(item.path)
        for related in getattr(item, "related_paths", []) or []:
            add(related)
    for path in tree_paths:
        name = PurePosixPath(path).name.lower()
        if name in doc_names or path.lower().startswith("docs/"):
            add(path)
    return selected[:25]


def index_chunks(store: QdrantStore, embedder: object, chunks: list[CodeChunk]) -> int:
    if not chunks:
        return 0
    vectors = embedder.embed_documents([chunk.text for chunk in chunks])  # type: ignore[attr-defined]
    return store.upsert(chunks, vectors)
