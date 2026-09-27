"""Dependency and test-framework detection tests."""

from app.analyzers.dependencies import analyze_dependencies, parse_pyproject, parse_requirements_txt
from tests.github_fixtures import PYPROJECT_TOML, TREE_PATHS


def test_parse_requirements_txt_ignores_comments_and_flags() -> None:
    text = "fastapi==0.115.0\n# comment\n-r other.txt\nsqlalchemy\n"
    assert parse_requirements_txt(text) == ["fastapi", "sqlalchemy"]


def test_parse_pyproject_dependencies() -> None:
    packages = parse_pyproject(PYPROJECT_TOML)
    assert "fastapi" in packages
    assert "sqlalchemy" in packages


def test_analyze_dependencies_from_tree_and_manifest() -> None:
    analysis = analyze_dependencies(TREE_PATHS, {"pyproject.toml": PYPROJECT_TOML})
    assert "pip" in analysis.package_managers
    assert "pytest" in analysis.test_frameworks
    assert "fastapi" in analysis.python_packages
