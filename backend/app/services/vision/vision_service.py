"""
Image -> text with Gemini vision (free tier), replacing local Tesseract OCR.

Unlike plain OCR, the model also describes non-text content (charts, photos,
diagrams), so images without much text still become searchable.
"""

import os

from google import genai
from google.genai import types
from loguru import logger

from app.core.config import settings

IMAGE_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
TRANSCRIBE_PROMPT = (
    "Transcribe ALL readable text in this image exactly, preserving headings, lists and table rows. "
    "Then add a section 'Image description:' describing any charts, diagrams, photos or layout "
    "(axes, values, trends, objects). Output plain text only."
)
_client: genai.Client | None = None


def _gemini() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


def transcribe_image(path: str, prompt: str = TRANSCRIBE_PROMPT) -> str:
    """Blocking (used from ingestion worker threads). Tries the agent model, then its fallback."""
    mime = IMAGE_MIME.get(os.path.splitext(path)[1].lower())
    if mime is None:
        raise ValueError(f"Unsupported image type: {path}")
    with open(path, "rb") as fh:
        data = fh.read()

    last_error: Exception | None = None
    for model in (settings.AGENT_MODEL, settings.AGENT_FALLBACK_MODEL):
        if not model:
            continue
        try:
            response = _gemini().models.generate_content(
                model=model, contents=[types.Part.from_bytes(data=data, mime_type=mime), prompt]
            )
            return (response.text or "").strip()
        except Exception as exc:
            last_error = exc
            logger.warning("Vision transcription failed on {}: {}", model, exc)
    raise RuntimeError(f"Image transcription failed: {last_error}")
