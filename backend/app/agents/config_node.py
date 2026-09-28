"""LangGraph node that loads .codereviewer.yml and applies path ignores."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from app.agents.state import ReviewGraphState
from app.analyzers.path_filter import build_ignore_spec, filter_snapshot
from app.core.logging import get_logger, log_event
from app.services.repo_config_service import (
    MAX_CONFIG_BYTES,
    load_repo_config,
    parse_repo_config,
)

if TYPE_CHECKING:
    from app.agents.nodes import ReviewGraphDeps

logger = get_logger(__name__)


def make_load_config_node(deps: "ReviewGraphDeps"):
    def load_config(state: ReviewGraphState) -> dict:
        snapshot = state["snapshot"]
        pull_request = snapshot.pull_request
        # Read from the base commit, so a PR can't edit its own review rules.
        ref = pull_request.base_sha or pull_request.target_branch
        raw_text: str | None = None
        if not ref:
            config, warnings = parse_repo_config(None)
        else:
            owner, repo = state["owner"], state["repo"]

            def fetch(path: str, ref_: str):
                nonlocal raw_text
                try:
                    raw_text = deps.client.get_text_file(
                        owner, repo, path, ref=ref_, max_bytes=MAX_CONFIG_BYTES
                    )
                except Exception:
                    raw_text = None
                return raw_text

            config, warnings = load_repo_config(fetch, ref)

        spec = build_ignore_spec(config.paths.ignore)
        filtered, removed = filter_snapshot(snapshot, spec)

        config_sha: str | None = None
        resolved_config: dict | None = None
        if raw_text is not None:
            config_sha = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
            resolved_config = config.model_dump(mode="json")

        log_event(
            logger,
            "repo_config_loaded",
            repository=f"{state['owner']}/{state['repo']}",
            warnings=len(warnings),
            ignored_files=removed,
        )
        result = {
            "repo_config": config,
            "config_warnings": warnings,
            "resolved_config": resolved_config,
            "config_sha": config_sha,
            "events": [{"node": "load_config", "status": "ok", "ignored_files": removed}],
        }
        if removed:
            result["snapshot"] = filtered
        return result

    return load_config