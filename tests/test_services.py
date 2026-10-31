from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.config import Settings
from backend.services import FasterWhisperTranscriber, GeminiAnalyzer


class FakeWhisperModel:
    def __init__(self, text: str):
        self.text = text

    def transcribe(self, *_args, **_kwargs):
        return [SimpleNamespace(text=self.text)], SimpleNamespace(language="es")


def test_whisper_adapter_joins_text_without_loading_a_real_model(tmp_path: Path):
    transcriber = FasterWhisperTranscriber(Settings())
    transcriber._model = FakeWhisperModel(" Synthetic speech ")
    assert transcriber.transcribe(tmp_path / "not-opened.wav") == "Synthetic speech"


def test_whisper_adapter_marks_empty_speech(tmp_path: Path):
    transcriber = FasterWhisperTranscriber(Settings())
    transcriber._model = FakeWhisperModel(" ")
    assert transcriber.transcribe(tmp_path / "not-opened.wav") == "[no clear speech]"


def test_gemini_adapter_fails_closed_without_key():
    analyzer = GeminiAnalyzer(Settings(gemini_api_key=None))
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        analyzer.analyze(
            rubric="demo",
            agent_reference="demo-agent",
            agent_name=None,
            agent_classification=None,
            transcript="AGENT: Hello",
        )


def test_gemini_adapter_validates_structured_output(monkeypatch):
    response = SimpleNamespace(
        text=(
            '{"ai_classification":"Support","result":"Correct","score":90,'
            '"summary":"Summary","report":"Report","strengths":[],'
            '"issues":[],"evidence":[],"recommendations":[]}'
        )
    )
    models = SimpleNamespace(generate_content=lambda **_kwargs: response)
    fake_genai = SimpleNamespace(Client=lambda **_kwargs: SimpleNamespace(models=models))
    monkeypatch.setitem(sys.modules, "google", SimpleNamespace(genai=fake_genai))
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)

    result = GeminiAnalyzer(Settings(gemini_api_key="test-placeholder")).analyze(
        rubric="demo",
        agent_reference="demo-agent",
        agent_name="Demo",
        agent_classification="Support",
        transcript="AGENT: Hello",
    )
    assert result.score == 90
