"""Build and post GitHub pull-request review comments from verified findings."""

from __future__ import annotations

from app.core.logging import get_logger, redact
from app.schemas.findings import FindingCategory, FindingSeverity, ReviewFinding, StructuredReview
from app.schemas.github import ChangedFile, PullRequestSnapshot
from app.tools.github import GitHubAPIError, GitHubClient

logger = get_logger(__name__)

MAX_INLINE_COMMENTS = 15
MAX_COMMENT_CHARS = 3_500
MAX_SUMMARY_CHARS = 8_000
POSTABLE_SEVERITIES = {
    FindingSeverity.CRITICAL,
    FindingSeverity.HIGH,
    FindingSeverity.MEDIUM,
}
_SEVERITY_ORDER = {
    FindingSeverity.CRITICAL: 0,
    FindingSeverity.HIGH: 1,
    FindingSeverity.MEDIUM: 2,
    FindingSeverity.LOW: 3,
    FindingSeverity.INFO: 4,
}


def should_post_finding(finding: ReviewFinding) -> bool:
    if finding.verified is not True:
        return False
    return finding.severity in POSTABLE_SEVERITIES


def _meets_config(
    finding: ReviewFinding,
    min_severity: FindingSeverity,
    categories: list[FindingCategory] | None,
) -> bool:
    """Return True if the finding passes the config filters."""
    if _SEVERITY_ORDER.get(finding.severity, 9) > _SEVERITY_ORDER.get(min_severity, 9):
        return False
    if categories is not None and finding.category not in categories:
        return False
    return True


def comment_anchor(item: ChangedFile, line: int | None) -> dict | None:
    """Map a finding line onto a GitHub review comment location, or None if not in the diff."""

    if line is None:
        return None
    for hunk in item.hunks:
        in_new = hunk.new_start <= line < hunk.new_start + max(hunk.new_count, 1)
        if line in hunk.added_line_numbers or in_new:
            return {"path": item.path, "line": line, "side": "RIGHT"}
    for hunk in item.hunks:
        if line in hunk.removed_line_numbers:
            return {"path": item.path, "line": line, "side": "LEFT"}
    return None


def format_inline_comment(finding: ReviewFinding) -> str:
    body = (
        f"**{finding.severity.value} {finding.category.value}: {finding.title}**\n\n"
        f"{finding.description}\n\n"
        f"**Evidence**\n```\n{finding.evidence}\n```\n\n"
        f"**Suggested fix**\n{finding.suggested_fix}"
    )
    text = redact(body)
    if len(text) > MAX_COMMENT_CHARS:
        text = text[: MAX_COMMENT_CHARS - 20] + "\n... [truncated]"
    return text


def format_review_body(
    review: StructuredReview,
    posted: list[ReviewFinding],
    omitted: int,
    *,
    cap_omitted: list[ReviewFinding] | None = None,
    config_warnings: list[str] | None = None,
) -> str:
    lines = [
        "AI Code Reviewer summary",
        "",
        review.summary.strip(),
        "",
        f"Posted {len(posted)} verified inline comment(s).",
    ]
    if omitted:
        lines.append(f"{omitted} additional verified finding(s) were omitted (limit {MAX_INLINE_COMMENTS}).")
    # Findings cut by max_comments cap are summarised in the body
    if cap_omitted:
        lines.append("")
        lines.append(f"**{len(cap_omitted)} finding(s) above the inline comment cap:**")
        for f in cap_omitted:
            lines.append(
                f"- **{f.severity.value} {f.category.value}** `{f.file}`"
                + (f" line {f.line}" if f.line else "")
                + f": {f.title}"
            )
    unverified = sum(1 for item in review.findings if item.verified is not True)
    if unverified:
        lines.append(f"{unverified} finding(s) were not posted because they failed verification.")
    if config_warnings:
        lines.append("")
        lines.append("⚠️ .codereviewer.yml was invalid; defaults were used.")
    text = redact("\n".join(lines))
    if len(text) > MAX_SUMMARY_CHARS:
        text = text[: MAX_SUMMARY_CHARS - 20] + "\n... [truncated]"
    return text


def build_review_comments(
    review: StructuredReview,
    snapshot: PullRequestSnapshot,
    *,
    min_severity: FindingSeverity = FindingSeverity.MEDIUM,
    categories: list[FindingCategory] | None = None,
    max_comments: int = MAX_INLINE_COMMENTS,
) -> tuple[list[dict], list[ReviewFinding], int, list[ReviewFinding]]:
    """Build inline comments.

    Returns (comments, posted, omitted_not_in_diff, cap_omitted).
    cap_omitted: findings that were eligible but cut by the max_comments cap.
    """
    files = {item.path.replace("\\", "/").lstrip("/"): item for item in snapshot.changed_files}
    eligible = [
        item
        for item in review.findings
        if should_post_finding(item) and _meets_config(item, min_severity, categories)
    ]
    eligible.sort(key=lambda item: (_SEVERITY_ORDER.get(item.severity, 9), item.file, item.line or 0))
    comments: list[dict] = []
    posted: list[ReviewFinding] = []
    cap_omitted: list[ReviewFinding] = []
    for finding in eligible:
        changed = files.get(finding.file)
        if changed is None:
            continue
        anchor = comment_anchor(changed, finding.line)
        if anchor is None:
            continue
        if len(comments) >= max_comments:
            cap_omitted.append(finding)
            continue
        comments.append({**anchor, "body": format_inline_comment(finding)})
        posted.append(finding)
    # "omitted" in the original sense = eligible but not in the diff
    omitted = max(0, len(eligible) - len(posted) - len(cap_omitted))
    return comments, posted, omitted, cap_omitted


def post_verified_review(
    client: GitHubClient,
    snapshot: PullRequestSnapshot,
    review: StructuredReview,
    *,
    config: object | None = None,
    config_warnings: list[str] | None = None,
) -> dict | None:
    """Post a COMMENT review. Returns the GitHub payload, or None if there is nothing useful to post.

    When `config` (a RepoConfig) is supplied, only findings that meet
    review.min_severity and review.categories are posted, and inline comments
    are capped at review.max_comments.
    """
    from app.schemas.repo_config import ReviewConfig

    review_cfg: ReviewConfig | None = getattr(config, "review", None) if config is not None else None

    min_severity = review_cfg.min_severity if review_cfg is not None else FindingSeverity.MEDIUM
    categories = review_cfg.categories if review_cfg is not None else None
    max_comments = review_cfg.max_comments if review_cfg is not None else MAX_INLINE_COMMENTS

    comments, posted, omitted, cap_omitted = build_review_comments(
        review,
        snapshot,
        min_severity=min_severity,
        categories=categories,
        max_comments=max_comments,
    )
    # Decide whether there is anything worth posting
    any_eligible = any(
        should_post_finding(item) and _meets_config(item, min_severity, categories)
        for item in review.findings
    )
    if not posted and not any_eligible and not (config_warnings):
        return None
    ref = snapshot.pull_request
    body = format_review_body(
        review,
        posted,
        omitted,
        cap_omitted=cap_omitted if cap_omitted else None,
        config_warnings=config_warnings,
    )
    try:
        return client.create_pull_request_review(
            ref.owner,
            ref.repo,
            ref.number,
            commit_sha=ref.head_sha,
            body=body,
            comments=comments,
            event="COMMENT",
        )
    except GitHubAPIError:
        logger.exception("github_review_post_failed")
        raise
