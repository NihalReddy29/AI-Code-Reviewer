import logging

import yaml
from pydantic import ValidationError

from app.schemas.repo_config import RepoConfig

logger = logging.getLogger(__name__)

CONFIG_FILENAME = ".codereviewer.yml"
MAX_CONFIG_BYTES = 20_000


def parse_repo_config(raw):
    """Takes the text of a config file. Returns (config, warnings). Never crashes."""
    if raw is None:
        return RepoConfig(), []

    if len(raw.encode("utf-8")) > MAX_CONFIG_BYTES:
        return RepoConfig(), [f"{CONFIG_FILENAME} is too large; using defaults."]

    try:
        data = yaml.safe_load(raw) or {}
        if not isinstance(data, dict):
            return RepoConfig(), [f"{CONFIG_FILENAME} must be a mapping; using defaults."]
        return RepoConfig.model_validate(data), []
    except (yaml.YAMLError, ValidationError) as exc:
        logger.warning("Invalid repo config: %s", exc)
        return RepoConfig(), [f"Invalid {CONFIG_FILENAME}; using defaults."]


def load_repo_config(fetch_file, ref):
    """fetch_file(path, ref) returns the file text, or None if it doesn't exist."""
    try:
        raw = fetch_file(CONFIG_FILENAME, ref)
    except Exception as exc:
        logger.warning("Could not fetch repo config: %s", exc)
        return RepoConfig(), [f"Could not fetch {CONFIG_FILENAME}; using defaults."]
    return parse_repo_config(raw)