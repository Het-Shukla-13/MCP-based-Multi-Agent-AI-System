from app.services.memory.context_router import build_context_policy
from app.services.conversation.conversation_metadata_service import merge_conversation_metadata
from app.services.memory.unified_memory_service import filter_messages_for_policy
from app.services.memory.context_router import ContextPolicy


def test_context_policy_always_retrieves_memory():
    policy = build_context_policy(has_rag_context=False)

    assert policy.needs_recent_history is True
    assert policy.needs_stm_summary is True
    assert policy.needs_long_term_memory is True
    assert policy.needs_related_conversations is True
    assert policy.needs_user_profile is True
    assert policy.needs_file_context is False


def test_context_policy_never_drops_attached_file_context():
    assert build_context_policy(has_rag_context=True).needs_file_context is True


def test_merge_conversation_metadata_replaces_stale_active_goals():
    merged = merge_conversation_metadata(
        {
            "topics": ["platypus"],
            "entities": ["pgvector"],
            "active_goals": ["Provide platypus facts"],
            "sentiment": "neutral",
            "summary_hint": "Old focus",
        },
        {
            "topics": ["emotional support"],
            "entities": ["family"],
            "active_goals": ["Talk through relationship uncertainty"],
            "sentiment": "mixed",
            "summary_hint": "Current focus",
        },
    )

    assert merged["active_goals"] == ["Talk through relationship uncertainty"]
    assert "platypus" in merged["topics"]
    assert "family" in merged["entities"]


def test_filter_messages_for_policy_drops_stm_summary_when_not_requested():
    summary_message = type(
        "Message",
        (),
        {
            "role": "system",
            "content": "Compressed memory from earlier conversation.\nUse it only as background context.",
        },
    )()
    user_message = type(
        "Message",
        (),
        {
            "role": "user",
            "content": "Hey",
        },
    )()

    filtered = filter_messages_for_policy(
        [summary_message, user_message],
        # ContextPolicy now requires every field; start from a real policy and override.
        build_context_policy(has_rag_context=False).model_copy(
            update={"needs_recent_history": True, "needs_stm_summary": False}
        ),
    )

    assert len(filtered) == 1
    assert filtered[0].content == "Hey"
