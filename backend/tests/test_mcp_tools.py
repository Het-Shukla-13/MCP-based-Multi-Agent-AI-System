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
