from __future__ import annotations

from typing import Iterable

from sqlalchemy.orm import Session

from app.db.models import ReviewRecord


class ReviewRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self) -> Iterable[ReviewRecord]:
        return self.session.query(ReviewRecord).all()

    def create(self, repository: str, pull_request: int, status: str = 'pending') -> ReviewRecord:
        record = ReviewRecord(repository=repository, pull_request=pull_request, status=status)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record
