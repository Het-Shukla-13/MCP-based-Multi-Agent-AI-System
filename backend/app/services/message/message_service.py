import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
from time import perf_counter

from app.models import Message
from app.schemas.message import MessageCreate
from app.crud.message import create_message
from app.crud.conversation import get_conversation, update_conversation_metadata
from app.services.llm import llm
from app.services.rag.retriever import retrieve_pipeline
from app.services.memory.unified_memory_service import build_unified_memory_context
from app.services.memory.memory_services import set_stm_state
from app.services.time.timing import elapsed_minutes, log_async_timing
from app.services.tokenization.token_service import get_message_token_count
from app.prompts import CHAT_SYSTEM_PROMPT
from app.services.memory.background_memory_pipeline import (
    schedule_memory_maintenance_pipeline,
)
from app.services.user_profile.user_profile_cache_service import schedule_profile_snapshot_update
from app.agent_layer.agents.root_agent import AgentExecutionError, RootAgent, StatusCallback
from app.agent_layer.core.mentions import parse_agent_mention
from app.services.metrics.collector import TurnCollector, current_turn
from app.agent_layer.schemas import AgentContext, HistoryMessage
from app.agent_layer.core.state import get_agent_state, set_active_agent

root_agent = RootAgent()

AGENT_ERROR_REPLY = (
    "Sorry, I couldn't complete that request: the AI provider failed or is rate-limited "
    "right now. Please try again in a moment."
)

EMPTY_RESPONSE_FALLBACK = (
    "I lost the thread for a moment. Please repeat the last line you want me to continue from, "
    "and I'll pick it up directly."
)


def build_message_history(
    messages: list[Message],
    rag_context: str = "",
) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for message in messages:
        attached_files = getattr(message, "files", []) or []
        file_lines = [
            f"- {file.filename} ({file.status})"
            for file in attached_files
        ]
        file_block = ""
        if file_lines:
            file_block = "\n\nAttached files:\n" + "\n".join(file_lines)

        history.append(
            {
                "role": message.role,
                "content": f"{message.content}{file_block}",
            }
        )

    logger.info("RAG/LTM context attached | has_context={}", bool(rag_context))

    if rag_context and history:
        last_message = history[-1]
        history[-1] = {
            **last_message,
            "content": (
                f"{last_message['content']}\n\n"
                f"Relevant context:\n{rag_context}"
            ),
        }

    return history

def parse_latest_message(content: str) -> tuple[str, str, str]:
    context_marker = "\n\nRelevant context:\n"
    attachment_marker = "\n\nAttached files:\n"

    if context_marker in content:
        user_portion, context = content.split(context_marker, 1)
    else:
        user_portion = content
        context = ""

    if attachment_marker in user_portion:
        user_query, attached_files = user_portion.split(attachment_marker, 1)
    else:
        user_query = user_portion
        attached_files = ""

    return user_query.strip(), attached_files.strip(), context.strip()

def build_llm_messages(
    history: list[dict[str, str]],
    system_prompt: str | None = None,
) -> list[dict[str, str]]:
    system_content = system_prompt or CHAT_SYSTEM_PROMPT
    if not history:
        return [{"role": "system", "content": system_content}]

    messages = [{"role": "system", "content": system_content}]

    for message in history[:-1]:
        messages.append(
            {
                "role": message["role"],
                "content": message["content"].strip(),
            }
        )

    user_query, attached_files, context = parse_latest_message(history[-1]["content"])

    final_sections = [f"User question:\n{user_query}"]
    if attached_files:
        final_sections.append(f"Attached files:\n{attached_files}")
    if context:
        final_sections.append(f"Relevant context:\n{context}")

    messages.append(
        {
            "role": history[-1]["role"],
            "content": "\n\n".join(final_sections),
        }
    )
    return messages

@log_async_timing("generate_ai_response")
async def generate_ai_response(
    messages: list[Message],
    rag_context: str = "",
) -> str:
    history = build_message_history(messages, rag_context=rag_context)
    if history:
        logger.info("Final prompt roles | roles={}", [message["role"] for message in history])
        logger.info("Final prompt last message | content={}", history[-1]["content"])
    messages=build_llm_messages(history, system_prompt=CHAT_SYSTEM_PROMPT)
    response = await llm.chat(
        messages=messages,
        purpose="chat_response",
    )
    return (response or "").strip()


def build_ai_message_payload(
    user_message: Message,
    ai_content: str,
    agent_name: str | None = None,
    file_ids: list | None = None,
) -> MessageCreate:
    # Uploaded files belong to the USER message (passing them here used to re-point
    # file.message_id to the AI reply). file_ids here are only files the agent's
    # tools CREATED during this turn (e.g. create_file, generate_image).
    return MessageCreate(
        user_id=user_message.user_id,
        conversation_id=user_message.conversation_id,
        content=ai_content,
        role="assistant",
        token_count=None,
        agent_name=agent_name,
        file_ids=file_ids or [],
    )


# def merge_conversation_metadata(existing_metadata: dict | None, new_metadata: dict) -> dict:
#     metadata = dict(existing_metadata or {})
#     stm_data = metadata.get("stm")

#     merged_topics = sorted(set((metadata.get("topics") or []) + (new_metadata.get("topics") or [])))
#     merged_entities = sorted(set((metadata.get("entities") or []) + (new_metadata.get("entities") or [])))
#     merged_goals = sorted(set((metadata.get("active_goals") or []) + (new_metadata.get("active_goals") or [])))

#     metadata["topics"] = merged_topics
#     metadata["entities"] = merged_entities
#     metadata["active_goals"] = merged_goals
#     metadata["sentiment"] = new_metadata.get("sentiment", metadata.get("sentiment", "neutral"))
#     metadata["summary_hint"] = new_metadata.get("summary_hint", metadata.get("summary_hint", ""))

#     if stm_data is not None:
#         metadata["stm"] = stm_data

#     return metadata


AGENT_VISIBLE_METADATA_KEYS = ("topics", "entities", "active_goals", "sentiment", "summary_hint")


def _metadata_for_agent(convo_metadata: dict | None) -> dict:
    """Only the descriptive metadata; internal state (stm, agent_state) stays out of the prompt."""
    metadata = convo_metadata or {}
    return {key: metadata[key] for key in AGENT_VISIBLE_METADATA_KEYS if metadata.get(key)}


@log_async_timing("send_message")
async def send_message(
    db: AsyncSession,
    payload: MessageCreate,
    rag_context: str = "",
    selected_agent: str | None = None,
    on_status: StatusCallback | None = None,
    requested_format: str | None = None,
) -> dict[str, Message]:
    """
    One chat turn, measured. The collector is published in a ContextVar for the
    duration of the turn and ALWAYS reset afterwards: every message on a WebSocket
    runs in the same task, so a leftover value would leak into the next turn.
    Metrics are queued (non-blocking) after the reply is saved.
    """
    collector = TurnCollector(user_id=payload.user_id, conversation_id=payload.conversation_id)
    token = current_turn.set(collector)
    try:
        result = await _send_message(db, payload, rag_context, selected_agent, on_status, requested_format)
        collector.finish(
            message_id=result["ai_message"].id,
            agent_name=result["active_agent"],
            error=result["error"],
        )
        return result
    except asyncio.CancelledError:  # Stop pressed: not an error, still a measured turn
        collector.finish(message_id=None, agent_name=None, error=False)
        raise
    except Exception:
        collector.finish(message_id=None, agent_name=None, error=True)
        raise
    finally:
        current_turn.reset(token)


async def _send_message(
    db: AsyncSession,
    payload: MessageCreate,
    rag_context: str,
    selected_agent: str | None,
    on_status: StatusCallback | None,
    requested_format: str | None,
) -> dict[str, Message]:
    turn_started_at = perf_counter()
    collector = current_turn.get()
    payload.token_count = get_message_token_count(payload)

    create_user_started_at = perf_counter()
    user_message = await create_message(db, payload)
    logger.info(
        "Chat timing | stage=create_user_message | duration_min={}",
        elapsed_minutes(create_user_started_at),
    )

    # The turn runner records this id so a stopped/interrupted turn can still be
    # answered (partial text) instead of leaving the question dangling.
    if on_status is not None:
        await on_status({"status": "accepted", "user_message_id": str(user_message.id)})

    # Profile extraction runs in the background: it doesn't affect this reply.
    schedule_profile_snapshot_update(user_message)

    unified_memory_started_at = perf_counter()
    unified_memory = await build_unified_memory_context(
        db,
        conversation_id=payload.conversation_id,
        user_id=payload.user_id,
        query_text=payload.content,
        rag_context=rag_context,
    )
    logger.info(
        "Chat timing | stage=build_unified_memory_context | duration_min={}",
        elapsed_minutes(unified_memory_started_at),
    )

    conversation = await get_conversation(db, payload.conversation_id)
    update_stm_started_at = perf_counter()
    updated_metadata = set_stm_state(conversation.convo_metadata, unified_memory.stm_state)
    await update_conversation_metadata(
        db,
        payload.conversation_id,
        updated_metadata,
    )
    logger.info(
        "Chat timing | stage=update_stm_state | duration_min={}",
        elapsed_minutes(update_stm_started_at),
    )

    logger.info("STM state | state={}", unified_memory.stm_state)
    logger.info("Retrieved LTM memories | count={}", len(unified_memory.ltm_results))
    logger.info(
        "User profile context ready | has_profile={}",
        bool(unified_memory.user_profile_text),
    )

    logger.info(
        "Unified context ready | has_context={}",
        bool(unified_memory.combined_context),
    )

    agent_state = get_agent_state(conversation.convo_metadata)
    previous_active_agent = agent_state.get("active_agent", "general")

    # Never default explicit_agent to previous_active_agent: that would bypass routing
    # forever. Stickiness is a *hint* to the router instead (previous_agent).
    # Explicit choice: UI pick first, otherwise an "@agent" typed in the message.
    # The stored user message keeps the mention; the agent gets the text without it.
    mentioned_agent, agent_input = parse_agent_mention(payload.content, root_agent.valid_agents)
    explicit_agent = selected_agent if selected_agent in root_agent.valid_agents else mentioned_agent
    if requested_format:  # UI format picker: ask the agent to deliver a file
        agent_input += f"\n\n(Deliver the result as a .{requested_format} file using the create_file tool.)"

    logger.info(
        "Agent routing | explicit_agent={} | previous_active_agent={} | mode={}",
        explicit_agent,
        previous_active_agent,
        "explicit" if explicit_agent else "llm_routing",
    )

    # Recent window from our DB (already token-limited by build_smart_history).
    # Skip the rolling-summary pseudo-message (passed separately as stm_context)
    # and the current user message (sent as the new turn).
    history = [
        HistoryMessage(role=m.role, content=m.content)
        for m in unified_memory.messages
        if m.role in ("user", "assistant") and m.id != user_message.id and m.content
    ]

    agent_context = AgentContext(
        user_id=str(payload.user_id),
        conversation_id=str(payload.conversation_id),
        user_message=agent_input,
        selected_agent=explicit_agent,          # None → LLM router picks; string → forced
        previous_agent=previous_active_agent,   # stickiness hint for the LLM router
        history=history,
        stm_context=unified_memory.stm_summary,
        ltm_context=unified_memory.ltm_context,
        profile_context=unified_memory.user_profile_text,
        related_conversations_context=unified_memory.related_conversations_context,
        rag_context=unified_memory.rag_context,
        conversation_metadata=_metadata_for_agent(conversation.convo_metadata),
    )

    ai_response_started_at = perf_counter()
    collector.context_ms = int((ai_response_started_at - collector.started) * 1000)
    collector.mode = "explicit" if explicit_agent else "routed"
    agent_error = False
    generated_file_ids: list = []
    try:
        agent_response = await root_agent.run(agent_context, on_status=on_status)
        answered_by = agent_response.agent_name
        ai_content = agent_response.content
        generated_file_ids = agent_response.generated_file_ids
        updated_metadata = set_active_agent(conversation.convo_metadata, answered_by)
        await update_conversation_metadata(db, payload.conversation_id, updated_metadata)
    except AgentExecutionError as exc:
        # Keep the conversation consistent (every user message gets a reply) and
        # tell the user plainly, instead of a generic socket error and a dangling question.
        logger.exception("Agent execution failed | agent={}", exc.agent_name)
        agent_error = True
        answered_by = exc.agent_name
        ai_content = AGENT_ERROR_REPLY
    
    collector.agent_ms = int((perf_counter() - ai_response_started_at) * 1000)
    logger.info(
            "Chat timing | stage=generate_ai_response | duration_min={}",
            elapsed_minutes(ai_response_started_at),
        )
    if not ai_content:
        ai_content = EMPTY_RESPONSE_FALLBACK

    ai_message = build_ai_message_payload(
        user_message, ai_content, agent_name=answered_by, file_ids=generated_file_ids
    )
    ai_message.token_count = get_message_token_count(ai_message)
    create_ai_started_at = perf_counter()
    ai_message = await create_message(db, ai_message)
    logger.info(
        "Chat timing | stage=create_ai_message | duration_min={}",
        elapsed_minutes(create_ai_started_at),
    )
        

    schedule_maintenance_started_at = perf_counter()
    if not agent_error:  # don't mine an error reply for memories
        schedule_memory_maintenance_pipeline(
            user_id=payload.user_id,
            conversation_id=payload.conversation_id,
        )
    logger.info(
        "Chat timing | stage=schedule_memory_maintenance | duration_min={}",
        elapsed_minutes(schedule_maintenance_started_at),
    )

    logger.info(
        "Chat timing | stage=total_turn | duration_min={}",
        elapsed_minutes(turn_started_at),
    )
    return {
        "user_message": user_message,
        "ai_message": ai_message,
        "active_agent": answered_by,
        "agent_switched": (not agent_error) and answered_by != previous_active_agent,
        "error": agent_error,
    }
    

@log_async_timing("send_message_from_payload")
async def send_message_from_payload(
    db: AsyncSession,
    conversation_id,
    payload: dict,
    authenticated_user_id,
    on_status: StatusCallback | None = None,
)-> dict[str, Message]:
    # File generation is now an agent TOOL (artifacts MCP server). The old
    # pre-flight path ran a keyword check plus often an extra LLM call on every
    # message and bypassed the agents entirely.
    request_started_at = perf_counter()
    requested_format = payload.get("format")
    if requested_format not in (None, "txt", "md", "json", "csv", "pdf"):
        requested_format = None

    message_payload = MessageCreate(
        user_id=authenticated_user_id,
        conversation_id=conversation_id,
        content=payload["content"],
        role="user",
        token_count=None,
        file_ids=payload.get("file_ids", []),
    )

    logger.info("Incoming message file IDs | file_ids={}", message_payload.file_ids)

    rag_started_at = perf_counter()
    rag_context = await retrieve_pipeline(
        payload["content"],
        message_payload.file_ids or [],
        conversation_id,
        authenticated_user_id,
        db,
    )

    logger.info("Retrieved RAG context | has_context={}", bool(rag_context))
    logger.info(
        "Chat timing | stage=retrieve_pipeline | duration_min={}",
        elapsed_minutes(rag_started_at),
    )

    result = await send_message(
        db,
        message_payload,
        rag_context=rag_context,
        selected_agent=payload.get("selected_agent"),
        on_status=on_status,
        requested_format=requested_format,
    )
    logger.info(
        "Chat timing | stage=send_message_from_payload_total | duration_min={}",
        elapsed_minutes(request_started_at),
    )
    return result
