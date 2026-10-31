from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings
from .database import Base, build_engine, get_db
from .models import Call, Segment, utc_now
from .schemas import CallCreate, CallResponse, SegmentResponse
from .services import Analyzer, FasterWhisperTranscriber, GeminiAnalyzer, Transcriber

logger = logging.getLogger(__name__)
ALLOWED_AUDIO_TYPES = {
    "audio/webm": ".webm",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
}
IGNORED_TRANSCRIPTS = {"[no clear speech]", "[inaudible]", "[silence]"}


def get_transcriber(request: Request) -> Transcriber:
    return request.app.state.transcriber


def get_analyzer(request: Request) -> Analyzer:
    return request.app.state.analyzer


DatabaseSession = Annotated[Session, Depends(get_db)]
TranscriberDependency = Annotated[Transcriber, Depends(get_transcriber)]
AnalyzerDependency = Annotated[Analyzer, Depends(get_analyzer)]
AudioUpload = Annotated[UploadFile, File()]
AudioSource = Annotated[str, Form()]


def _has_expected_signature(extension: str, header: bytes) -> bool:
    signatures = {
        ".wav": header.startswith(b"RIFF") and header[8:12] == b"WAVE",
        ".webm": header.startswith(b"\x1aE\xdf\xa3"),
        ".ogg": header.startswith(b"OggS"),
        ".mp3": header.startswith(b"ID3") or header.startswith(b"\xff"),
    }
    return signatures.get(extension, False)


async def _store_upload(upload: UploadFile, settings: Settings) -> Path:
    extension = ALLOWED_AUDIO_TYPES.get(upload.content_type or "")
    if extension is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported audio type",
        )
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    target = settings.upload_dir / f"{uuid4().hex}{extension}"
    total = 0
    try:
        with target.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail="Audio file exceeds configured size limit",
                    )
                output.write(chunk)
        if total == 0:
            raise HTTPException(status_code=400, detail="Audio file is empty")
        with target.open("rb") as stored_audio:
            header = stored_audio.read(12)
        if not _has_expected_signature(extension, header):
            raise HTTPException(status_code=415, detail="Audio content does not match its type")
        return target
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings()
    if active_settings.database_url.startswith("sqlite:///"):
        Path(active_settings.database_url.removeprefix("sqlite:///")).parent.mkdir(
            parents=True, exist_ok=True
        )
    engine = build_engine(active_settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        Base.metadata.create_all(bind=engine)
        yield
        engine.dispose()

    application = FastAPI(
        title="Call Audit AI",
        description="Privacy-aware call transcription and quality-audit prototype",
        version="2.0.0",
        lifespan=lifespan,
    )
    application.state.settings = active_settings
    application.state.session_factory = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False
    )
    application.state.transcriber = FasterWhisperTranscriber(active_settings)
    application.state.analyzer = GeminiAnalyzer(active_settings)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(active_settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/calls", response_model=CallResponse, status_code=201)
    def create_call(payload: CallCreate, db: DatabaseSession) -> Call:
        call = Call(**payload.model_dump())
        db.add(call)
        db.commit()
        db.refresh(call)
        return call

    @application.post("/calls/{call_id}/segments", response_model=SegmentResponse, status_code=201)
    async def create_segment(
        call_id: int,
        source: AudioSource,
        audio: AudioUpload,
        db: DatabaseSession,
        transcriber: TranscriberDependency,
    ) -> Segment:
        call = db.get(Call, call_id)
        if call is None:
            raise HTTPException(status_code=404, detail="Call not found")
        if call.status != "IN_PROGRESS":
            raise HTTPException(status_code=409, detail="Call is not in progress")
        normalized_source = source.strip().upper()
        if normalized_source not in {"AGENT", "CUSTOMER"}:
            raise HTTPException(status_code=422, detail="Source must be AGENT or CUSTOMER")

        audio_path = await _store_upload(audio, active_settings)
        try:
            transcript = transcriber.transcribe(audio_path)
        except Exception as exc:
            logger.exception("Audio transcription failed for call %s", call_id)
            raise HTTPException(status_code=502, detail="Audio transcription failed") from exc
        finally:
            if not active_settings.retain_audio:
                audio_path.unlink(missing_ok=True)

        segment = Segment(call_id=call_id, source=normalized_source, transcript=transcript)
        db.add(segment)
        db.commit()
        db.refresh(segment)
        return segment

    @application.post("/calls/{call_id}/finalize", response_model=CallResponse)
    def finalize_call(
        call_id: int,
        db: DatabaseSession,
        analyzer: AnalyzerDependency,
    ) -> Call:
        call = db.get(Call, call_id)
        if call is None:
            raise HTTPException(status_code=404, detail="Call not found")
        if call.status != "IN_PROGRESS":
            raise HTTPException(status_code=409, detail="Call is not in progress")
        segments = db.scalars(
            select(Segment)
            .where(Segment.call_id == call_id)
            .order_by(Segment.created_at, Segment.id)
        ).all()
        lines = [
            f"{segment.source}: {segment.transcript.strip()}"
            for segment in segments
            if segment.transcript and segment.transcript.strip().lower() not in IGNORED_TRANSCRIPTS
        ]
        if not lines:
            raise HTTPException(status_code=422, detail="No clear speech to analyze")
        try:
            rubric = active_settings.rubric_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.exception("Call rubric could not be read")
            raise HTTPException(status_code=503, detail="Call rubric is unavailable") from exc
        transcript = "\n".join(lines)
        try:
            analysis = analyzer.analyze(
                rubric=rubric,
                agent_reference=call.agent_reference,
                agent_name=call.agent_name,
                agent_classification=call.agent_classification,
                transcript=transcript,
            )
        except Exception as exc:
            logger.exception("AI analysis failed for call %s", call_id)
            raise HTTPException(status_code=502, detail="AI analysis failed") from exc

        call.transcript = transcript
        call.ai_classification = analysis.ai_classification
        call.result = analysis.result
        call.score = analysis.score
        call.analysis_json = analysis.model_dump_json(indent=2)
        call.status = "COMPLETED"
        call.finished_at = utc_now()
        db.commit()
        db.refresh(call)
        return call

    @application.get("/calls", response_model=list[CallResponse])
    def list_calls(db: DatabaseSession) -> list[Call]:
        return list(db.scalars(select(Call).order_by(Call.started_at.desc())).all())

    @application.get("/calls/{call_id}", response_model=CallResponse)
    def get_call(call_id: int, db: DatabaseSession) -> Call:
        call = db.get(Call, call_id)
        if call is None:
            raise HTTPException(status_code=404, detail="Call not found")
        return call

    @application.get("/calls/{call_id}/segments", response_model=list[SegmentResponse])
    def list_segments(call_id: int, db: DatabaseSession) -> list[Segment]:
        if db.get(Call, call_id) is None:
            raise HTTPException(status_code=404, detail="Call not found")
        return list(
            db.scalars(
                select(Segment)
                .where(Segment.call_id == call_id)
                .order_by(Segment.created_at, Segment.id)
            ).all()
        )

    return application


app = create_app()
