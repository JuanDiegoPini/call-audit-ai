from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app, get_analyzer, get_transcriber
from backend.schemas import CallAnalysis


class StubTranscriber:
    def __init__(self, text: str = "Hello, how can I help you today?"):
        self.text = text

    def transcribe(self, audio_path: Path) -> str:
        assert audio_path.exists()
        return self.text


class StubAnalyzer:
    def analyze(self, **kwargs) -> CallAnalysis:
        assert "AGENT: Hello" in kwargs["transcript"]
        return CallAnalysis(
            ai_classification="Support",
            result="Correct",
            score=88,
            summary="Synthetic summary",
            report="The agent followed the demonstration rubric.",
            strengths=["Clear greeting"],
            issues=[],
            evidence=["Hello, how can I help you today?"],
            recommendations=["Confirm the next step"],
        )


@pytest.fixture
def client(tmp_path: Path):
    rubric = tmp_path / "rubric.md"
    rubric.write_text("Synthetic test rubric", encoding="utf-8")
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        upload_dir=tmp_path / "uploads",
        rubric_path=rubric,
        max_upload_bytes=32,
        retain_audio=False,
        cors_origins=("http://localhost:5500",),
    )
    app = create_app(settings)
    app.dependency_overrides[get_transcriber] = lambda: StubTranscriber()
    app.dependency_overrides[get_analyzer] = lambda: StubAnalyzer()
    with TestClient(app) as test_client:
        yield test_client, settings


def create_call(client: TestClient) -> int:
    response = client.post(
        "/calls",
        json={
            "agent_reference": "demo-agent-01",
            "agent_name": "Demo Agent",
            "agent_classification": "Support",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_complete_call_flow_and_audio_cleanup(client):
    test_client, settings = client
    call_id = create_call(test_client)
    segment = test_client.post(
        f"/calls/{call_id}/segments",
        data={"source": "AGENT"},
        files={"audio": ("synthetic.wav", b"RIFF0000WAVEdata", "audio/wav")},
    )
    assert segment.status_code == 201
    assert segment.json()["source"] == "AGENT"
    assert list(settings.upload_dir.glob("*")) == []

    finalized = test_client.post(f"/calls/{call_id}/finalize")
    assert finalized.status_code == 200
    assert finalized.json()["status"] == "COMPLETED"
    assert finalized.json()["score"] == 88
    assert test_client.post(f"/calls/{call_id}/finalize").status_code == 409


def test_rejects_invalid_source_and_content_type(client):
    test_client, _ = client
    call_id = create_call(test_client)
    invalid_source = test_client.post(
        f"/calls/{call_id}/segments",
        data={"source": "UNKNOWN"},
        files={"audio": ("synthetic.wav", b"data", "audio/wav")},
    )
    assert invalid_source.status_code == 422

    invalid_type = test_client.post(
        f"/calls/{call_id}/segments",
        data={"source": "AGENT"},
        files={"audio": ("payload.txt", b"data", "text/plain")},
    )
    assert invalid_type.status_code == 415

    spoofed_audio = test_client.post(
        f"/calls/{call_id}/segments",
        data={"source": "AGENT"},
        files={"audio": ("spoofed.wav", b"not-a-wave", "audio/wav")},
    )
    assert spoofed_audio.status_code == 415


def test_rejects_oversized_and_empty_uploads(client):
    test_client, settings = client
    call_id = create_call(test_client)
    oversized = test_client.post(
        f"/calls/{call_id}/segments",
        data={"source": "AGENT"},
        files={"audio": ("large.wav", b"x" * 33, "audio/wav")},
    )
    assert oversized.status_code == 413
    assert list(settings.upload_dir.glob("*")) == []

    empty = test_client.post(
        f"/calls/{call_id}/segments",
        data={"source": "AGENT"},
        files={"audio": ("empty.wav", b"", "audio/wav")},
    )
    assert empty.status_code == 400


def test_missing_resources_and_no_clear_speech(client):
    test_client, _ = client
    assert test_client.get("/calls/999").status_code == 404
    assert test_client.get("/calls/999/segments").status_code == 404
    call_id = create_call(test_client)
    assert test_client.post(f"/calls/{call_id}/finalize").status_code == 422


def test_validation_and_health(client):
    test_client, _ = client
    assert test_client.get("/health").json() == {"status": "ok"}
    assert test_client.post("/calls", json={"agent_reference": ""}).status_code == 422
    assert test_client.get("/calls").status_code == 200
