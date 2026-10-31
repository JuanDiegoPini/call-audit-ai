from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL", f"sqlite:///{PROJECT_ROOT / 'data' / 'call_audit.db'}"
        )
    )
    upload_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("UPLOAD_DIR", str(PROJECT_ROOT / "data" / "uploads"))
        )
    )
    rubric_path: Path = field(
        default_factory=lambda: Path(
            os.getenv(
                "CALL_RUBRIC_PATH",
                str(PROJECT_ROOT / "config" / "call_quality_rubric.example.md"),
            )
        )
    )
    max_upload_bytes: int = field(
        default_factory=lambda: int(os.getenv("MAX_UPLOAD_MB", "10")) * 1024 * 1024
    )
    retain_audio: bool = field(default_factory=lambda: _as_bool(os.getenv("RETAIN_AUDIO"), False))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            value.strip()
            for value in os.getenv(
                "CORS_ORIGINS", "http://127.0.0.1:5500,http://localhost:5500"
            ).split(",")
            if value.strip()
        )
    )
    gemini_api_key: str | None = field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    whisper_model: str = field(default_factory=lambda: os.getenv("WHISPER_MODEL", "small"))
    whisper_device: str = field(default_factory=lambda: os.getenv("WHISPER_DEVICE", "cpu"))
    whisper_compute_type: str = field(
        default_factory=lambda: os.getenv("WHISPER_COMPUTE_TYPE", "int8")
    )
