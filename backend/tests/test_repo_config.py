from app.schemas.findings import FindingCategory, FindingSeverity
from app.services.repo_config_service import parse_repo_config


def test_missing_file_gives_defaults():
    cfg, warnings = parse_repo_config(None)
    assert cfg.review.max_comments == 20
    assert cfg.review.min_severity == FindingSeverity.MEDIUM
    assert warnings == []


def test_partial_file_keeps_defaults():
    cfg, _ = parse_repo_config("tools:\n  pytest: false\n")
    assert cfg.tools.pytest is False
    assert cfg.tools.ruff is True


def test_invalid_yaml_falls_back():
    cfg, warnings = parse_repo_config("tools: [unclosed")
    assert cfg.tools.ruff is True
    assert len(warnings) == 1


def test_bad_value_falls_back():
    cfg, warnings = parse_repo_config("review:\n  max_comments: 9999\n")
    assert cfg.review.max_comments == 20
    assert len(warnings) == 1


def test_valid_min_severity():
    cfg, warnings = parse_repo_config("review:\n  min_severity: HIGH\n")
    assert cfg.review.min_severity == FindingSeverity.HIGH
    assert warnings == []


def test_invalid_min_severity_falls_back_to_medium():
    """An unrecognised severity string falls back to MEDIUM (not an error)."""
    cfg, warnings = parse_repo_config("review:\n  min_severity: BOGUS\n")
    assert cfg.review.min_severity == FindingSeverity.MEDIUM
    # The YAML parsed fine; the coercion is silent, so no overall config warning.
    assert warnings == []


def test_valid_categories():
    cfg, _ = parse_repo_config("review:\n  categories:\n    - SECURITY\n    - BUG\n")
    assert FindingCategory.SECURITY in cfg.review.categories
    assert FindingCategory.BUG in cfg.review.categories


def test_invalid_categories_are_dropped():
    """Invalid category entries are dropped; valid ones are kept."""
    cfg, _ = parse_repo_config("review:\n  categories:\n    - SECURITY\n    - NOT_A_CATEGORY\n")
    assert cfg.review.categories == [FindingCategory.SECURITY]


def test_all_invalid_categories_become_none():
    """If all categories are invalid the field becomes None (no filter)."""
    cfg, _ = parse_repo_config("review:\n  categories:\n    - BAD\n    - WORSE\n")
    assert cfg.review.categories is None