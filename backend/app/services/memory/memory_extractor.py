import json

from loguru import logger
from pydantic import ValidationError

from app.prompts import MEMORY_EXTRACTION_SYSTEM_PROMPT, MEMORY_EXTRACTION_USER_PROMPT
from app.schemas.memory import ExtractedMemory
from app.services.llm.llm_service import get_llm_response_async


async def extract_memories_from_text(conversation_text: str) -> list[ExtractedMemory]:
    """
    Validate memories ONE BY ONE. Validating the whole response at once meant a
    single item with e.g. an unknown enum value discarded every valid memory in
    the batch.
    """
    user_prompt = MEMORY_EXTRACTION_USER_PROMPT.format(conversation_text=conversation_text.strip())
    try:
        raw = await get_llm_response_async(
            [{"role": "system", "content": MEMORY_EXTRACTION_SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
            purpose="memory_extraction",
            response_format={"type": "json_object"},
        )
        items = json.loads(raw).get("memories", [])
    except Exception:
        logger.exception("Memory extraction failed; no memories promoted this turn")
        return []

    memories: list[ExtractedMemory] = []
    for item in items if isinstance(items, list) else []:
        try:
            memories.append(ExtractedMemory.model_validate(item))
        except ValidationError as exc:
            logger.warning("Skipping invalid extracted memory | item={} | errors={}", item, exc.errors()[:2])
    return memories
