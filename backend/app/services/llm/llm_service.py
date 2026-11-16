import atexit
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from time import perf_counter

from loguru import logger
from openai import OpenAI
from groq import Groq

from app.core.config import settings

CHAT_PURPOSE_PREFIXES = ("chat_response", "stm_summarization")
MAINTENANCE_PURPOSE_PREFIXES = (
    "memory_extraction",
    "memory_annotation",
    "profile_extraction",
    "conversation_metadata_extraction",
    "memory_comparison",
)

LLM_EXECUTOR = ThreadPoolExecutor(max_workers=max(1, settings.LLM_MAX_WORKERS))
MAINTENANCE_LLM_EXECUTOR = ThreadPoolExecutor(
    max_workers=max(1, settings.MAINTENANCE_LLM_MAX_WORKERS)
)
atexit.register(lambda: LLM_EXECUTOR.shutdown(wait=False))
atexit.register(lambda: MAINTENANCE_LLM_EXECUTOR.shutdown(wait=False))



_groq_client = None
_gemini_client = None


def get_groq_client():
    global _groq_client

    if _groq_client is None:
        if not settings.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is not configured.")
        _groq_client = Groq(api_key=settings.GROQ_API_KEY)

    return _groq_client


def get_gemini_client():
    global _gemini_client

    if _gemini_client is None:
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not configured.")
        _gemini_client = OpenAI(
            api_key=settings.GEMINI_API_KEY,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )

    return _gemini_client

def _serialize_prompt_for_logs(messages: list[dict[str, str]]) -> str:
    try:
        return json.dumps(messages, ensure_ascii=True)
    except Exception:
        return str(messages)


def _estimate_prompt_chars(messages: list[dict[str, str]]) -> int:
    return sum(len(message.get("content", "")) for message in messages)


def _is_maintenance_purpose(purpose: str) -> bool:
    normalized = (purpose or "unspecified").strip().lower()
    return any(
        normalized.startswith(prefix)
        for prefix in MAINTENANCE_PURPOSE_PREFIXES
    )


def _resolve_model_for_purpose(purpose: str) -> str:
    if _is_maintenance_purpose(purpose):
        model_name = settings.MAINTENANCE_MODEL or settings.MODEL
    else:
        model_name = settings.CHAT_MODEL or settings.MODEL

    if not model_name:
        raise ValueError("No LLM model is configured for this purpose.")

    return model_name.strip()


def _resolve_executor_for_purpose(purpose: str) -> ThreadPoolExecutor:
    if _is_maintenance_purpose(purpose):
        return MAINTENANCE_LLM_EXECUTOR
    return LLM_EXECUTOR


def _is_gemini_model(model_name: str) -> bool:
    return model_name.startswith("gemini")


def _is_reasoning_model(model_name: str) -> bool:
    # gpt-oss models "think" before answering; without limits they can spend the
    # whole token budget on hidden reasoning and return empty content.
    return model_name.startswith("openai/gpt-oss")


def _is_retryable_with_fallback(exc: Exception) -> bool:
    """Rate limits, quota exhaustion, retired models and provider outages."""
    status = getattr(exc, "status_code", None)
    if status in (404, 429, 500, 502, 503, 504):
        return True
    text = str(exc).lower()
    return any(
        marker in text
        for marker in ("rate limit", "quota", "resource_exhausted", "does not exist", "decommissioned")
    )


def _call_model(model_name: str, messages, response_format: dict | None):
    if _is_gemini_model(model_name):
        client = get_gemini_client()
    else:
        client = get_groq_client()
        # Accept LiteLLM-style "groq/<model>" names from older .env files.
        if model_name.startswith("groq/"):
            model_name = model_name[len("groq/"):]

    params = {"model": model_name, "messages": messages}
    if response_format:
        params["response_format"] = response_format
    if settings.LLM_TEMPERATURE is not None:
        params["temperature"] = settings.LLM_TEMPERATURE
    if _is_reasoning_model(model_name):
        params["extra_body"] = {
            "reasoning_effort": settings.LLM_REASONING_EFFORT,
            "include_reasoning": False,  # we only want the final answer back
        }

    response = client.chat.completions.create(**params)
    return response.choices[0].message.content


def get_llm_response(
    messages,
    purpose: str = "unspecified",
    response_format: dict | None = None,
):
    model_name = _resolve_model_for_purpose(purpose)
    started_at = perf_counter()
    logger.info(
        "LLM request | purpose={} | model={} | lane={} | temperature={} | message_count={} | prompt_chars={} | messages={}",
        purpose,
        model_name,
        "maintenance" if _is_maintenance_purpose(purpose) else "foreground",
        settings.LLM_TEMPERATURE,
        len(messages),
        _estimate_prompt_chars(messages),
        _serialize_prompt_for_logs(messages),
    )

    try:
        content = _call_model(model_name, messages, response_format)
    except Exception as exc:
        fallback = settings.LLM_FALLBACK_MODEL
        if not fallback or fallback == model_name or not _is_retryable_with_fallback(exc):
            raise
        logger.warning(
            "LLM primary failed, using fallback | purpose={} | primary={} | fallback={} | error={}",
            purpose, model_name, fallback, exc,
        )
        model_name = fallback
        content = _call_model(model_name, messages, response_format)

    duration_min = round((perf_counter() - started_at) / 60, 4)
    logger.info(
        "LLM response | purpose={} | model={} | duration_min={} | response_chars={} | content={}",
        purpose,
        model_name,
        duration_min,
        len((content or "").strip()),
        (content or "").strip(),
    )
    return (content or "").strip()

async def get_llm_response_async(
    messages,
    purpose: str = "unspecified",
    response_format: dict | None = None,
):
    loop = asyncio.get_running_loop()
    executor = _resolve_executor_for_purpose(purpose)
    return await loop.run_in_executor(
        executor,
        get_llm_response,
        messages,
        purpose,
        response_format,
    )

