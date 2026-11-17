"""Prompts live in app/prompts/**.md; these tests guard the loader and the call-site contracts."""
import string

import pytest

import app.prompts as prompts
from app.agent_layer.agents.root_agent import _router_instruction
from app.agent_layer.core import agent_registry
from app.agent_layer.schemas.schemas import AgentContext, HistoryMessage
from app.prompts.loader import PROMPTS_DIR, PromptError, load_prompt, render_prompt

# .format(...) keywords each background call site passes. If a prompt edit adds or
# drops a {placeholder}, the call would KeyError (or silently ignore data) at runtime.
FORMAT_KEYS = {
    "SUMMARIZATION_USER_PROMPT": {"existing_summary_block", "text"},
    "CONVERSATION_METADATA_USER_PROMPT": {"conversation_text"},
    "MEMORY_COMPARISON_USER_PROMPT": {"existing_content", "new_content", "memory_type"},
    "MEMORY_EXTRACTION_USER_PROMPT": {"conversation_text"},
    "METADATA_ANNOTATION_USER_PROMPT": {"content", "memory_type"},
    "PROFILE_CANDIDATE_USER_PROMPT": {"latest_user_content", "recent_messages"},
}


@pytest.mark.parametrize("const,keys", FORMAT_KEYS.items())
def test_background_user_prompts_match_call_sites(const, keys):
    text = getattr(prompts, const)
    fields = {f for _, f, _, _ in string.Formatter().parse(text) if f}
    assert fields == keys
    text.format(**{k: "x" for k in keys})  # renders without KeyError


def test_every_agent_has_a_prompt_file_without_unresolved_markers():
    for name in agent_registry.list_agents():
        instruction = agent_registry.get(name)._build_adk_agent().instruction
        assert instruction.strip(), name
        assert "{{" not in instruction, f"{name}: unresolved include/placeholder"


def test_shared_fragment_is_included_once_per_agent():
    fragment = load_prompt("fragments/file_output")
    users = [n for n in agent_registry.list_agents() if fragment in load_prompt(f"agents/{n}")]
    assert set(users) == {"general", "code", "data", "research", "document"}


def test_router_prompt_renders_context():
    ctx = AgentContext(
        user_id="u", conversation_id="c", user_message="x", previous_agent="data",
        history=[HistoryMessage(role="user", content="plot sales")],
    )
    agents = [agent_registry.get(n) for n in agent_registry.list_agents()]
    text = _router_instruction(ctx, agents)
    assert "exactly one of: general, code, data, research, document, image." in text
    assert "handled the previous turn: data." in text
    assert "USER: plot sales" in text
    assert text.endswith("USER: plot sales\n")


def test_render_prompt_rejects_missing_and_unused_values():
    with pytest.raises(PromptError, match="missing"):
        render_prompt("agents/router", names="a")
    with pytest.raises(PromptError, match="unused"):
        render_prompt("agents/router", names="a", previous_agent="b", default_agent="c",
                      recent="d", typo="e")


def test_loader_drops_exactly_one_trailing_newline(tmp_path, monkeypatch):
    (tmp_path / "fragments").mkdir()
    (tmp_path / "fragments" / "f.md").write_text("FRAG\n")
    (tmp_path / "p.md").write_text("a\n{{> f}}\n{{who}}\n\n")
    monkeypatch.setattr("app.prompts.loader.PROMPTS_DIR", tmp_path)
    load_prompt.cache_clear()
    try:
        assert render_prompt("p", who="me") == "a\nFRAG\nme\n"
        with pytest.raises(PromptError):
            load_prompt("nope")
    finally:
        load_prompt.cache_clear()


def test_prompt_files_are_all_used():
    """No orphaned .md files: every file is a background prompt, agent, router or fragment."""
    files = {p.relative_to(PROMPTS_DIR).with_suffix("").as_posix() for p in PROMPTS_DIR.rglob("*.md")}
    agents = {f"agents/{n}" for n in agent_registry.list_agents()} | {"agents/router"}
    background = {f for f in files if f.startswith("background/")}
    fragments = {f for f in files if f.startswith("fragments/")}
    assert files == agents | background | fragments
    assert len(background) == len([c for c in prompts.__all__ if c.endswith("_PROMPT")])
