from loguru import logger

from app.services.llm import llm

from app.schemas import MemoryExtractionResponse
from app.prompts import MEMORY_EXTRACTION_SYSTEM_PROMPT, MEMORY_EXTRACTION_USER_PROMPT




async def extract_memories_from_text(conversation_text: str) -> list[MemoryExtractionResponse]:
    user_prompt = MEMORY_EXTRACTION_USER_PROMPT.format(conversation_text=conversation_text.strip())
    try:
        result = await llm.structured(
            [{"role": "system", "content": MEMORY_EXTRACTION_SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
            purpose="memory_extraction",
            response_model=MemoryExtractionResponse
        )
    except Exception:
        logger.exception("Memory extraction failed; no memories promoted this turn")
        return []

    return result.memories