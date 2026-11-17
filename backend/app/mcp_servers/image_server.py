"""
Image MCP server.
- describe_image: Gemini vision (free tier) on the user's uploaded image.
- generate_image: Pollinations.ai (free, open source, no API key). Gemini image
  generation was verified to have a free-tier quota of 0, so it is not used.
  Note: generation prompts are sent to a third-party service; anonymous images
  carry a small watermark.
"""

import asyncio
import os
from urllib.parse import quote

import httpx
from google import genai
from google.genai import types
from mcp.server.fastmcp import FastMCP

from app.core.config import settings
from app.mcp_servers.common import configure_server_logging, resolve_owned_file, save_generated_file
from app.services.file_generation.file_renderer import filename_timestamp, slugify

configure_server_logging("image")
mcp = FastMCP("image")

IMAGE_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}?width={w}&height={h}&nologo=true"
_client: genai.Client | None = None


def _gemini() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=settings.GEMINI_HTTP_TIMEOUT_MS),
        )
    return _client


@mcp.tool()
async def describe_image(file_name: str, question: str = "Describe this image in detail, including any visible text.",
                         user_id: str = "", conversation_id: str = "") -> str:
    """Look at an uploaded image (JPG/PNG) and answer a question about it: description,
    reading text (OCR), charts, objects. user_id/conversation_id are filled in automatically."""
    target, error = await resolve_owned_file(user_id, conversation_id, file_name)
    if target is None:
        return error
    mime = IMAGE_MIME.get(os.path.splitext(target.filename)[1].lower())
    if mime is None:
        return f"'{target.filename}' is not a JPG/PNG image."
    with open(target.storage_path, "rb") as fh:
        data = fh.read()

    last_error = None
    for model in (settings.AGENT_MODEL, settings.AGENT_FALLBACK_MODEL):
        if not model:
            continue
        try:
            response = await _gemini().aio.models.generate_content(
                model=model, contents=[types.Part.from_bytes(data=data, mime_type=mime), question]
            )
            return f"[{target.filename}] {response.text}"
        except Exception as exc:
            last_error = exc
    return f"Image analysis failed: {last_error}"


@mcp.tool()
async def generate_image(prompt: str, width: int = 1024, height: int = 1024,
                         user_id: str = "", conversation_id: str = "") -> str:
    """Create an image from a text prompt (free Pollinations.ai service). Write a detailed,
    descriptive prompt in English. Returns a link to the saved image.
    user_id/conversation_id are filled in automatically."""
    w, h = max(256, min(width, 1536)), max(256, min(height, 1536))
    response, last_error = None, ""
    # The free service is sometimes overloaded (HTTP 503/429): retry with backoff,
    # and fall back from the "flux" model to the service's default model.
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        for attempt, model in enumerate(("flux", "flux", "", "")):
            url = POLLINATIONS_URL.format(prompt=quote(prompt[:800]), w=w, h=h) + (f"&model={model}" if model else "")
            try:
                candidate = await client.get(url)
                if candidate.status_code == 200 and candidate.headers.get("content-type", "").startswith("image/"):
                    response = candidate
                    break
                last_error = f"HTTP {candidate.status_code}"
            except httpx.HTTPError as exc:
                last_error = str(exc)
            await asyncio.sleep(2 * (attempt + 1))
    if response is None:
        return f"Image generation is temporarily unavailable ({last_error}). Tell the user to try again shortly."
    saved = await save_generated_file(
        user_id, conversation_id, f"{filename_timestamp()}_{slugify(prompt[:60])}.jpg", response.content, "image/jpeg"
    )
    return f"Image created.\n{saved}"


if __name__ == "__main__":
    mcp.run()
