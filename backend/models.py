from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_reference: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_name: Mapped[str | None] = mapped_column(String(100))
    agent_classification: Mapped[str | None] = mapped_column(String(100))
    ai_classification: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="IN_PROGRESS")
    transcript: Mapped[str | None] = mapped_column(Text)
    analysis_json: Mapped[str | None] = mapped_column(Text)
    result: Mapped[str | None] = mapped_column(String(50))
    score: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    segments: Mapped[list[Segment]] = relationship(
        back_populates="call", cascade="all, delete-orphan"
    )


class Segment(Base):
    __tablename__ = "call_segments"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    transcript: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    call: Mapped[Call] = relationship(back_populates="segments")
