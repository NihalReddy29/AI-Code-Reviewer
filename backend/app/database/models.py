"""ORM models for repositories, pull requests, review runs, and findings."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, TypeDecorator

from app.database.session import Base
from app.schemas.findings import FindingCategory, FindingSeverity


class PortableUUID(TypeDecorator):
    """UUID that stores as native UUID on PostgreSQL and string on SQLite."""

    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[no-untyped-def]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):  # type: ignore[no-untyped-def]
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return str(value)

    def process_result_value(self, value, dialect):  # type: ignore[no-untyped-def]
        if value is None:
            return value
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


class PortableJSON(TypeDecorator):
    """JSON that uses JSONB on PostgreSQL and JSON elsewhere."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[no-untyped-def]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class ReviewRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = mapped_column(PortableUUID(), primary_key=True, default=uuid.uuid4)
    github_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    default_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    html_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    pull_requests: Mapped[list[PullRequest]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )


class PullRequest(Base):
    __tablename__ = "pull_requests"
    __table_args__ = (UniqueConstraint("repository_id", "number", name="uq_pull_request_repo_number"),)

    id: Mapped[uuid.UUID] = mapped_column(PortableUUID(), primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        PortableUUID(), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    head_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    html_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    repository: Mapped[Repository] = relationship(back_populates="pull_requests")
    review_runs: Mapped[list[ReviewRun]] = relationship(
        back_populates="pull_request", cascade="all, delete-orphan"
    )


class ReviewRun(Base):
    __tablename__ = "review_runs"

    id: Mapped[uuid.UUID] = mapped_column(PortableUUID(), primary_key=True, default=uuid.uuid4)
    pull_request_id: Mapped[uuid.UUID] = mapped_column(
        PortableUUID(), ForeignKey("pull_requests.id", ondelete="CASCADE"), nullable=False
    )
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[ReviewRunStatus] = mapped_column(
        Enum(ReviewRunStatus, name="review_run_status", native_enum=False),
        nullable=False,
        default=ReviewRunStatus.PENDING,
    )
    trigger: Mapped[str] = mapped_column(String(64), nullable=False, default="webhook")
    github_delivery_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    changed_files: Mapped[list | dict | None] = mapped_column(PortableJSON(), nullable=True)
    repository_context: Mapped[dict | list | None] = mapped_column(PortableJSON(), nullable=True)
    retrieved_context: Mapped[list | dict | None] = mapped_column(PortableJSON(), nullable=True)
    static_analysis_results: Mapped[list | dict | None] = mapped_column(PortableJSON(), nullable=True)
    test_results: Mapped[list | dict | None] = mapped_column(PortableJSON(), nullable=True)
    agent_trace: Mapped[list | dict | None] = mapped_column(PortableJSON(), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    errors: Mapped[list | dict | None] = mapped_column(PortableJSON(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Per-repo config that was resolved for this run.
    # resolved_config: the full RepoConfig as a JSON dict (None if no config file was found).
    # config_sha: SHA-256 hex of the raw .codereviewer.yml bytes (None if no config file).
    # NOTE: these columns are added via ALTER TABLE in production if Alembic is not present;
    # in SQLite test databases they are created from scratch by Base.metadata.create_all().
    resolved_config: Mapped[dict | None] = mapped_column(PortableJSON(), nullable=True)
    config_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)

    pull_request: Mapped[PullRequest] = relationship(back_populates="review_runs")
    reviews: Mapped[list[Review]] = relationship(back_populates="review_run", cascade="all, delete-orphan")
    findings: Mapped[list[Finding]] = relationship(
        back_populates="review_run", cascade="all, delete-orphan"
    )


class Review(Base):
    """Posted or generated review summary for a single run."""

    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(PortableUUID(), primary_key=True, default=uuid.uuid4)
    review_run_id: Mapped[uuid.UUID] = mapped_column(
        PortableUUID(), ForeignKey("review_runs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_to_github: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    github_review_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    review_run: Mapped[ReviewRun] = relationship(back_populates="reviews")


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[uuid.UUID] = mapped_column(PortableUUID(), primary_key=True, default=uuid.uuid4)
    review_run_id: Mapped[uuid.UUID] = mapped_column(
        PortableUUID(), ForeignKey("review_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[FindingCategory] = mapped_column(
        Enum(FindingCategory, name="finding_category", native_enum=False), nullable=False
    )
    severity: Mapped[FindingSeverity] = mapped_column(
        Enum(FindingSeverity, name="finding_severity", native_enum=False), nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_fix: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    verification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    review_run: Mapped[ReviewRun] = relationship(back_populates="findings")
