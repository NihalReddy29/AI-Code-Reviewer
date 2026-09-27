from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ReviewRequest:
    repository: str
    pull_request: int
    commit_sha: str | None = None


class ReviewService:
    def __init__(self) -> None:
        self._reviews: list[ReviewRequest] = []

    def enqueue(self, review: ReviewRequest) -> None:
        self._reviews.append(review)

    def list(self) -> list[ReviewRequest]:
        return list(self._reviews)

    def get(self, pull_request: int) -> ReviewRequest | None:
        for review in self._reviews:
            if review.pull_request == pull_request:
                return review
        return None
