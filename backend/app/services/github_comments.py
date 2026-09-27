"""Build and post GitHub pull-request review comments from verified findings."""

from __future__ import annotations

from app.core.logging import get_logger, redact
from app.schemas.findings import FindingSeverity, ReviewFinding, StructuredReview
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


def format_review_body(review: StructuredReview, posted: list[ReviewFinding], omitted: int) -> str:
    lines = [
        "AI Code Reviewer summary",
        "",
        review.summary.strip(),
        "",
        f"Posted {len(posted)} verified inline comment(s).",
    ]
    if omitted:
        lines.append(f"{omitted} additional verified finding(s) were omitted (limit {MAX_INLINE_COMMENTS}).")
    unverified = sum(1 for item in review.findings if item.verified is not True)
    if unverified:
        lines.append(f"{unverified} finding(s) were not posted because they failed verification.")
    text = redact("\n".join(lines))
    if len(text) > MAX_SUMMARY_CHARS:
        text = text[: MAX_SUMMARY_CHARS - 20] + "\n... [truncated]"
    return text


def build_review_comments(
    review: StructuredReview,
    snapshot: PullRequestSnapshot,
) -> tuple[list[dict], list[ReviewFinding], int]:
    files = {item.path.replace("\\", "/").lstrip("/"): item for item in snapshot.changed_files}
    eligible = [item for item in review.findings if should_post_finding(item)]
    eligible.sort(key=lambda item: (_SEVERITY_ORDER.get(item.severity, 9), item.file, item.line or 0))
    comments: list[dict] = []
    posted: list[ReviewFinding] = []
    for finding in eligible:
        if len(comments) >= MAX_INLINE_COMMENTS:
            break
        changed = files.get(finding.file)
        if changed is None:
            continue
        anchor = comment_anchor(changed, finding.line)
        if anchor is None:
            continue
        comments.append({**anchor, "body": format_inline_comment(finding)})
        posted.append(finding)
    omitted = max(0, len(eligible) - len(posted))
    return comments, posted, omitted


def post_verified_review(
    client: GitHubClient,
    snapshot: PullRequestSnapshot,
    review: StructuredReview,
) -> dict | None:
    """Post a COMMENT review. Returns the GitHub payload, or None if there is nothing useful to post."""

    comments, posted, omitted = build_review_comments(review, snapshot)
    if not posted and not any(should_post_finding(item) for item in review.findings):
        return None
    ref = snapshot.pull_request
    body = format_review_body(review, posted, omitted)
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
