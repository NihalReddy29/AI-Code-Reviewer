from app.github.auth import is_github_configured, validate_github_token


def test_validate_github_token_accepts_valid_tokens() -> None:
    assert validate_github_token('ghp_1234567890abcdef') is True


def test_validate_github_token_rejects_missing_tokens() -> None:
    assert validate_github_token(None) is False


def test_github_configured_is_boolean() -> None:
    assert isinstance(is_github_configured(), bool)
