from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CallCreate(BaseModel):
    agent_reference: str = Field(min_length=1, max_length=64)
    agent_name: str | None = Field(default=None, max_length=100)
    agent_classification: str | None = Field(default=None, max_length=100)


class SegmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    call_id: int
    source: str
    transcript: str | None
    created_at: datetime


class CallResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_reference: str
    agent_name: str | None
    agent_classification: str | None
    ai_classification: str | None
    status: str
    transcript: str | None
    analysis_json: str | None
    result: str | None
    score: int | None
    started_at: datetime
    finished_at: datetime | None


class CallAnalysis(BaseModel):
    ai_classification: str = Field(max_length=100)
    result: str = Field(max_length=50)
    score: int = Field(ge=0, le=100)
    summary: str
    report: str
    strengths: list[str]
    issues: list[str]
    evidence: list[str]
    recommendations: list[str]
