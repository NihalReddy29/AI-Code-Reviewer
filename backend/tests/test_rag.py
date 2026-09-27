"""RAG retrieval tests using in-memory Qdrant and hash embeddings."""

from app.analyzers.diff import changed_file_from_github
from app.rag.chunking import chunk_file
from app.rag.embeddings import HashEmbedder
from app.rag.indexer import QdrantStore, index_chunks, select_index_paths
from app.rag.retriever import extract_changed_symbols, retrieve_for_pull_request
from qdrant_client import QdrantClient
from tests.github_fixtures import FILES_JSON, README_MD, TREE_PATHS, USER_SERVICE_PY


def test_select_index_paths_includes_changed_related_and_docs() -> None:
    changed = [changed_file_from_github(FILES_JSON[0])]
    changed[0] = changed[0].model_copy(update={"related_paths": ["backend/tests/test_user_service.py"]})
    selected = select_index_paths(TREE_PATHS, changed)
    assert "backend/services/user_service.py" in selected
    assert "backend/tests/test_user_service.py" in selected
    assert "README.md" in selected


def test_extract_changed_symbols_from_patch() -> None:
    changed = changed_file_from_github(FILES_JSON[0])
    assert "get_user" in extract_changed_symbols([changed])


def test_retrieve_prefers_changed_function_chunk() -> None:
    embedder = HashEmbedder()
    store = QdrantStore(QdrantClient(location=":memory:"), "test-rag", embedder.dimensions)
    chunks = chunk_file(
        "backend/services/user_service.py",
        USER_SERVICE_PY,
        repository="acme/api",
        commit_sha="abc123def456",
    )
    chunks.extend(
        chunk_file("README.md", README_MD, repository="acme/api", commit_sha="abc123def456")
    )
    index_chunks(store, embedder, chunks)
    changed = [changed_file_from_github(FILES_JSON[0])]
    hits = retrieve_for_pull_request(store, embedder, repository="acme/api", changed_files=changed, limit=4)
    assert hits
    top = hits[0]
    assert top.file_path.endswith("user_service.py")
    assert top.symbol == "get_user"
    assert top.start_line <= 11 <= top.end_line
