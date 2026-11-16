"""Network-free tests for MCP tool logic."""

import asyncio

from app.mcp_servers.code_server import _analyze
from app.mcp_servers.web_server import is_public_url
from app.services.memory import memory_extractor


def test_ssrf_guard_blocks_internal_addresses():
    for url in ["http://127.0.0.1:8010/users", "http://169.254.169.254/latest", "http://10.1.2.3",
                "http://192.168.0.1", "http://[::1]/", "file:///etc/passwd", "ftp://example.com"]:
        assert is_public_url(url)[0] is False, url


def test_code_analysis_finds_python_syntax_error_and_structure():
    report = _analyze("class Cart:\n    def add(self, x):\n        self.items.append((x)\n", "python")
    assert "problem" in report and "line" in report
    assert "`Cart`" in report


def test_code_analysis_outline_for_typescript():
    report = _analyze("export function greet(n: string): string { return n }\nclass A {}\n", "ts")
    assert "Syntax: OK" in report and "`greet`" in report and "`A`" in report


def test_memory_extraction_keeps_valid_items_when_one_is_invalid(monkeypatch):
    raw = ('{"memories": ['
           '{"content": "User likes Python.", "memory_type": "preference", "importance_score": 0.8,'
           ' "confidence_score": 0.9, "evidence": "explicit", "temporal_scope": "durable", "memory_metadata": {}},'
           '{"content": "bad", "memory_type": "not-a-type", "importance_score": 0.8,'
           ' "confidence_score": 0.9, "evidence": "explicit", "temporal_scope": "durable"}]}')

    async def fake_llm(*args, **kwargs):
        return raw

    monkeypatch.setattr(memory_extractor, "get_llm_response_async", fake_llm)
    memories = asyncio.run(memory_extractor.extract_memories_from_text("user: I like Python"))
    assert [m.content for m in memories] == ["User likes Python."]


def test_compatible_more_detailed_memory_is_treated_as_refinement(monkeypatch):
    from types import SimpleNamespace
    from app.schemas.memory import MemoryComparisonResult
    from app.services.memory import ltm_service

    async def fake_compare(**kwargs):
        return MemoryComparisonResult(relationship="compatible", confidence=0.95, reason="adds detail")

    monkeypatch.setattr(ltm_service, "compare_memories", fake_compare)
    old = SimpleNamespace(content="User prefers Python.")
    matched, comparison, _ = asyncio.run(ltm_service._check_duplicate_candidates(
        content="User prefers Python and says it is their favourite language.",
        memory_type="preference",
        similar_matches=[{"memory": old, "distance": 0.22}],
    ))
    assert matched is old and comparison["relationship"] == "refinement"


def test_profile_rebuild_drops_all_memory_derived_items():
    from app.services.user_profile.user_profile_cache_service import _message_derived_items

    items = [
        {"value": "old wording", "metadata": {"memory_id": "m1"}},   # edited memory: recompute
        {"value": "gone", "metadata": {"memory_id": "m2"}},          # deleted memory: drop
        {"value": "from a message", "metadata": {}},                 # no memory: keep
    ]
    assert [i["value"] for i in _message_derived_items(items)] == ["from a message"]
