from loguru import logger

from app.services.llm import llm

from app.schemas import ConversationMetadata

from app.prompts import CONVERSATION_METADATA_SYSTEM_PROMPT, CONVERSATION_METADATA_USER_PROMPT



async def extract_conversation_metadata(conversation_text: str) -> ConversationMetadata:
    if not conversation_text.strip():
        return ConversationMetadata()

    try:
        user_prompt=CONVERSATION_METADATA_USER_PROMPT.format(conversation_text=conversation_text.strip())
        metadata = await llm.structured(
            messages=[{"role": "system", "content": CONVERSATION_METADATA_SYSTEM_PROMPT},{"role": "user", "content": user_prompt}],
            purpose="conversation_metadata_extraction",
            response_model=ConversationMetadata,
        )
        return metadata
    except Exception:
        logger.exception("Conversation metadata extraction failed; using empty metadata")
        return ConversationMetadata()

    
