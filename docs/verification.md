# Verification record

Verification date: 2026-10-30

Environment:

- Windows
- Python 3.11.9
- Node.js 24.16.0 (syntax check only)

Results:

| Check | Result |
|---|---|
| `ruff check .` | Passed |
| `ruff format --check .` | Passed |
| `pytest` | 9 passed |
| Python coverage | 91% overall |
| `node --check frontend/app.js` | Passed |
| `pip check` | No broken requirements |
| `python scripts/check_secrets.py` | No findings in publication candidates |
| Uvicorn startup and `GET /health` | Passed (`200`, `status=ok`) |
| OpenAPI document | Served successfully, version 2.0.0 |

The tests cover the API lifecycle, persistence, invalid source rejection, media-type
and signature validation, upload-size enforcement, temporary-file cleanup, retry
guards, lazy Whisper behavior, missing Gemini configuration, and structured Gemini
response parsing.

No real audio was processed. No Whisper model was downloaded. No request was sent to
Gemini. Browser capture and a live provider integration remain manual validation
items for a consent-based laboratory.
