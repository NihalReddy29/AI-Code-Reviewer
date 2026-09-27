"""Detect package managers, manifests, and test frameworks from a repository tree."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import PurePosixPath

from pydantic import BaseModel, Field

from app.analyzers.language import normalize_path

MANIFEST_CANDIDATES = (
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
    "requirements.txt",
    "requirements-dev.txt",
    "Pipfile",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "pytest.ini",
    "tox.ini",
    "uv.lock",
    "poetry.lock",
)


class DependencyManifest(BaseModel):
    path: str
    ecosystem: str
    dependencies: list[str] = Field(default_factory=list)


class DependencyAnalysis(BaseModel):
    package_managers: list[str] = Field(default_factory=list)
    test_frameworks: list[str] = Field(default_factory=list)
    manifests: list[DependencyManifest] = Field(default_factory=list)
    python_packages: list[str] = Field(default_factory=list)
    node_packages: list[str] = Field(default_factory=list)


def find_manifest_paths(tree_paths: list[str]) -> list[str]:
    wanted = {name.lower() for name in MANIFEST_CANDIDATES}
    found: list[str] = []
    for path in tree_paths:
        normalized = normalize_path(path)
        name = PurePosixPath(normalized).name
        if name.lower() in wanted and normalized.count("/") <= 2:
            found.append(normalized)
    return sorted(set(found))


def detect_package_managers(tree_paths: list[str]) -> list[str]:
    names = {PurePosixPath(normalize_path(path)).name.lower() for path in tree_paths}
    managers: list[str] = []
    if "pyproject.toml" in names or "requirements.txt" in names or "setup.py" in names:
        managers.append("pip")
    if "poetry.lock" in names or "pyproject.toml" in names:
        if "poetry.lock" in names:
            managers.append("poetry")
    if "uv.lock" in names:
        managers.append("uv")
    if "pipfile" in names:
        managers.append("pipenv")
    if "package.json" in names:
        managers.append("npm")
    if "yarn.lock" in names:
        managers.append("yarn")
    if "pnpm-lock.yaml" in names:
        managers.append("pnpm")
    if "go.mod" in names:
        managers.append("go")
    if "cargo.toml" in names:
        managers.append("cargo")
    return list(dict.fromkeys(managers))


def detect_test_frameworks(tree_paths: list[str], manifests: dict[str, str] | None = None) -> list[str]:
    names = {PurePosixPath(normalize_path(path)).name.lower() for path in tree_paths}
    paths = {normalize_path(path).lower() for path in tree_paths}
    frameworks: list[str] = []
    if "pytest.ini" in names or "conftest.py" in names or any(path.endswith("/conftest.py") for path in paths):
        frameworks.append("pytest")
    if any(path.endswith("_test.go") for path in paths):
        frameworks.append("go-test")
    contents = manifests or {}
    for path, text in contents.items():
        lowered = path.lower()
        if lowered.endswith("pyproject.toml") and "[tool.pytest" in text.replace(" ", ""):
            if "pytest" not in frameworks:
                frameworks.append("pytest")
        if lowered.endswith("package.json"):
            try:
                scripts = json.loads(text).get("scripts") or {}
            except json.JSONDecodeError:
                scripts = {}
            if "test" in scripts:
                frameworks.append("npm-test")
            if "jest" in json.dumps(scripts).lower():
                frameworks.append("jest")
    if "tox.ini" in names and "pytest" not in frameworks:
        frameworks.append("tox")
    return list(dict.fromkeys(frameworks))


def _requirement_name(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith("-"):
        return None
    match = re.match(r"^([A-Za-z0-9_.-]+)", stripped)
    return match.group(1) if match else None


def parse_requirements_txt(text: str) -> list[str]:
    names = [_requirement_name(line) for line in text.splitlines()]
    return [name for name in names if name]


def parse_pyproject(text: str) -> list[str]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    packages: list[str] = []
    project = data.get("project") or {}
    for item in project.get("dependencies") or []:
        if isinstance(item, str) and _requirement_name(item):
            packages.append(_requirement_name(item) or item)
    tool = data.get("tool") or {}
    poetry = tool.get("poetry") or {}
    deps = poetry.get("dependencies") or {}
    if isinstance(deps, dict):
        packages.extend(name for name in deps if name.lower() != "python")
    return list(dict.fromkeys(packages))


def parse_package_json(text: str) -> tuple[list[str], bool]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return [], False
    names = list((data.get("dependencies") or {}).keys()) + list((data.get("devDependencies") or {}).keys())
    has_test_script = "test" in (data.get("scripts") or {})
    return list(dict.fromkeys(names)), has_test_script


def analyze_dependencies(tree_paths: list[str], manifest_contents: dict[str, str] | None = None) -> DependencyAnalysis:
    """Deterministic dependency analysis. Does not install or execute packages."""

    contents = manifest_contents or {}
    managers = detect_package_managers(tree_paths)
    frameworks = detect_test_frameworks(tree_paths, contents)
    manifests: list[DependencyManifest] = []
    python_packages: list[str] = []
    node_packages: list[str] = []

    for path, text in contents.items():
        lowered = path.lower()
        if lowered.endswith("requirements.txt") or lowered.endswith("requirements-dev.txt"):
            packages = parse_requirements_txt(text)
            python_packages.extend(packages)
            manifests.append(DependencyManifest(path=path, ecosystem="python", dependencies=packages))
        elif lowered.endswith("pyproject.toml"):
            packages = parse_pyproject(text)
            python_packages.extend(packages)
            manifests.append(DependencyManifest(path=path, ecosystem="python", dependencies=packages))
            if "[tool.poetry" in text and "poetry" not in managers:
                managers.append("poetry")
        elif lowered.endswith("package.json"):
            packages, has_test = parse_package_json(text)
            node_packages.extend(packages)
            manifests.append(DependencyManifest(path=path, ecosystem="node", dependencies=packages))
            if has_test and "npm-test" not in frameworks:
                frameworks.append("npm-test")

    return DependencyAnalysis(
        package_managers=list(dict.fromkeys(managers)),
        test_frameworks=list(dict.fromkeys(frameworks)),
        manifests=manifests,
        python_packages=list(dict.fromkeys(python_packages)),
        node_packages=list(dict.fromkeys(node_packages)),
    )
