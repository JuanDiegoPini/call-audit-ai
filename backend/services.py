from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

from .config import Settings
from .schemas import CallAnalysis

logger = logging.getLogger(__name__)


class Transcriber(Protocol):
    def transcribe(self, audio_path: Path) -> str: ...


class Analyzer(Protocol):
    def analyze(
        self,
        *,
        rubric: str,
        agent_reference: str,
        agent_name: str | None,
        agent_classification: str | None,
        transcript: str,
    ) -> CallAnalysis: ...


class FasterWhisperTranscriber:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError(
                    "faster-whisper is not installed; install requirements-ai.txt"
                ) from exc
            self._model = WhisperModel(
                self.settings.whisper_model,
                device=self.settings.whisper_device,
                compute_type=self.settings.whisper_compute_type,
            )
        return self._model

    def transcribe(self, audio_path: Path) -> str:
        segments, _ = self._get_model().transcribe(
            str(audio_path), language="es", vad_filter=True, beam_size=5
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return text if len(text) >= 3 else "[no clear speech]"


class GeminiAnalyzer:
    def __init__(self, settings: Settings):
        self.settings = settings

    def analyze(
        self,
        *,
        rubric: str,
        agent_reference: str,
        agent_name: str | None,
        agent_classification: str | None,
        transcript: str,
    ) -> CallAnalysis:
        if not self.settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError(
                "google-genai is not installed; install requirements-ai.txt"
            ) from exc

        prompt = (
            "Audit this call against the supplied rubric. Use only evidence present in "
            "the transcript. Return JSON with these keys: ai_classification, result, "
            "score (0-100), summary, report, strengths, issues, evidence, "
            "recommendations.\n\n"
            f"RUBRIC:\n{rubric}\n\n"
            f"AGENT REFERENCE: {agent_reference}\n"
            f"AGENT NAME: {agent_name or 'not provided'}\n"
            f"AGENT CLASSIFICATION: {agent_classification or 'not provided'}\n\n"
            f"TRANSCRIPT:\n{transcript}"
        )
        client = genai.Client(api_key=self.settings.gemini_api_key)
        response = client.models.generate_content(
            model=self.settings.gemini_model,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": CallAnalysis,
            },
        )
        if not response.text:
            raise RuntimeError("Gemini returned an empty response")
        try:
            return CallAnalysis.model_validate_json(response.text)
        except ValueError as exc:
            logger.warning("Gemini returned an invalid structured response")
            raise RuntimeError("Gemini returned an invalid structured response") from exc
