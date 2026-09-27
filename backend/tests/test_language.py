"""Language and file-kind detection tests."""

from app.analyzers.language import FileKind, classify_file, detect_kind, detect_language, should_skip_path


def test_detect_language_from_extension_and_filename() -> None:
    assert detect_language("backend/app/main.py") == "python"
    assert detect_language("src/index.ts") == "typescript"
    assert detect_language("Dockerfile") == "dockerfile"
    assert detect_language("Makefile") == "make"
    assert detect_language("notes.txt") is None


def test_detect_kind_for_source_test_docs_and_ci() -> None:
    assert detect_kind("backend/services/user_service.py") is FileKind.SOURCE
    assert detect_kind("backend/tests/test_user_service.py") is FileKind.TEST
    assert classify_file("backend/tests/test_user_service.py").is_test is True
    assert detect_kind("README.md") is FileKind.DOCUMENTATION
    assert detect_kind(".github/workflows/ci.yml") is FileKind.CI
    assert detect_kind("poetry.lock") is FileKind.LOCKFILE
    assert detect_kind("docker-compose.yml") is FileKind.INFRASTRUCTURE


def test_skips_vendor_directories() -> None:
    assert should_skip_path("frontend/node_modules/react/index.js") is True
    assert should_skip_path("backend/app/main.py") is False
