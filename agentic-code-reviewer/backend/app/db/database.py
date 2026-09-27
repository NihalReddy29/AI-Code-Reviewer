from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


engine = create_engine('sqlite:///./reviews.db', future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
