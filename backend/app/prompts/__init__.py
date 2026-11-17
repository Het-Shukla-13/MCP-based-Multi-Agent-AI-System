"""Background-job prompts (memory, summaries, metadata). Text lives in background/*.md."""
from app.prompts.loader import load_prompt, render_prompt

CHAT_SYSTEM_PROMPT = load_prompt("background/chat.system")
SUMMARIZATION_SYSTEM_PROMPT = load_prompt("background/summarization.system")
SUMMARIZATION_USER_PROMPT = load_prompt("background/summarization.user")
CONVERSATION_METADATA_SYSTEM_PROMPT = load_prompt("background/conversation_metadata.system")
CONVERSATION_METADATA_USER_PROMPT = load_prompt("background/conversation_metadata.user")
MEMORY_COMPARISON_SYSTEM_PROMPT = load_prompt("background/memory_comparison.system")
MEMORY_COMPARISON_USER_PROMPT = load_prompt("background/memory_comparison.user")
MEMORY_EXTRACTION_SYSTEM_PROMPT = load_prompt("background/memory_extraction.system")
MEMORY_EXTRACTION_USER_PROMPT = load_prompt("background/memory_extraction.user")
METADATA_ANNOTATION_SYSTEM_PROMPT = load_prompt("background/metadata_annotation.system")
METADATA_ANNOTATION_USER_PROMPT = load_prompt("background/metadata_annotation.user")
PROFILE_CANDIDATE_SYSTEM_PROMPT = load_prompt("background/profile_candidate.system")
PROFILE_CANDIDATE_USER_PROMPT = load_prompt("background/profile_candidate.user")

__all__ = [
    "load_prompt",
    "render_prompt",
    "CHAT_SYSTEM_PROMPT",
    "SUMMARIZATION_SYSTEM_PROMPT",
    "SUMMARIZATION_USER_PROMPT",
    "CONVERSATION_METADATA_USER_PROMPT",
    "CONVERSATION_METADATA_SYSTEM_PROMPT",
    "MEMORY_COMPARISON_USER_PROMPT",
    "MEMORY_COMPARISON_SYSTEM_PROMPT",
    "MEMORY_EXTRACTION_SYSTEM_PROMPT",
    "MEMORY_EXTRACTION_USER_PROMPT",
    "METADATA_ANNOTATION_SYSTEM_PROMPT",
    "METADATA_ANNOTATION_USER_PROMPT",
    "PROFILE_CANDIDATE_SYSTEM_PROMPT",
    "PROFILE_CANDIDATE_USER_PROMPT",
]
