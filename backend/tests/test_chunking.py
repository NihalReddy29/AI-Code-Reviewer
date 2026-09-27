"""AST-aware chunking tests. No Qdrant or embedding API required."""

from app.rag.chunking import chunk_file, chunk_python
from tests.github_fixtures import README_MD, USER_SERVICE_PY


def test_python_chunking_preserves_function_metadata() -> None:
    chunks = chunk_python(
        "backend/services/user_service.py",
        USER_SERVICE_PY,
        repository="acme/api",
        commit_sha="abc123",
    )
    symbols = {chunk.symbol: chunk for chunk in chunks}
    assert "get_user" in symbols
    fn = symbols["get_user"]
    assert fn.language == "python"
    assert fn.start_line == 10
    assert "def get_user" in fn.text
    assert fn.file_path == "backend/services/user_service.py"


def test_markdown_chunking_uses_headings() -> None:
    chunks = chunk_file(
        "README.md",
        README_MD,
        repository="acme/api",
        commit_sha="abc123",
    )
    assert chunks
    assert chunks[0].kind == "documentation"
    assert chunks[0].symbol == "API"


def test_invalid_python_falls_back_without_raising() -> None:
    chunks = chunk_python(
        "broken.py",
        "def nope(\n",
        repository="acme/api",
        commit_sha="abc",
    )
    assert chunks
    assert chunks[0].start_line >= 1
