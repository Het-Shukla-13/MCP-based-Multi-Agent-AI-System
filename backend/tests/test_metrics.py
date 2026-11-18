import time
import asyncio
from types import SimpleNamespace as NS
from uuid import uuid4

from app.api.metrics import percentile
from app.services.llm import llm_service
from app.services.metrics.collector import TurnCollector, current_turn, observe_adk_event
from app.services.metrics.redaction import redact_args
from app.services.metrics.writer import metrics_writer


def _drain():
    return metrics_writer._drain()


def test_redaction_masks_pii_drops_identity_and_truncates():
    out = redact_args({
        "user_id": "secret-id", "query": "mail het@example.com or call +91 98765 43210",
        "notes": "x" * 500, "nested": [{"password": "p", "q": "a@b.co"}],
    })
    assert "user_id" not in out
    assert out["query"] == "mail [email] or call [phone]"
    assert out["notes"].endswith("…") and len(out["notes"]) <= 121
    assert out["nested"] == [{"q": "[email]"}]


def test_percentile_nearest_rank():
    assert percentile([], 50) is None
    assert percentile([100, 200, 300, 400], 50) == 200
    assert percentile(list(range(1, 101)), 95) == 95


def test_collector_from_adk_events():
    _drain()
    turn = TurnCollector(user_id=uuid4(), conversation_id=uuid4())
    token = current_turn.set(turn)
    try:
        call = NS(id="c1", name="table_info", args={"file_name": "sales.csv", "user_id": "x"})
        observe_adk_event(NS(author="data", partial=False, usage_metadata=None,
                             content=NS(parts=[NS(text=None, function_call=call, function_response=None)])))
        resp = NS(id="c1", name="table_info", response={"result": "Rows: 10"})
        observe_adk_event(NS(author="data", partial=False, usage_metadata=None,
                             content=NS(parts=[NS(text=None, function_call=None, function_response=resp)])))
        observe_adk_event(NS(author="data", partial=True, usage_metadata=None,
                             content=NS(parts=[NS(text="Hel", function_call=None, function_response=None)])))
        usage = NS(prompt_token_count=120, candidates_token_count=30)
        observe_adk_event(NS(author="data", partial=False, usage_metadata=usage, model_version="gemini-x",
                             content=NS(parts=[NS(text="Hello", function_call=None, function_response=None)])))
    finally:
        current_turn.reset(token)

    assert turn.first_token_at is not None
    assert (turn.input_tokens, turn.output_tokens) == (120, 30)  # final event only, not partials
    assert turn.tools[0]["tool"] == "table_info" and turn.tools[0]["ok"] is True
    assert "user_id" not in turn.tools[0]["args"]
    rows = _drain()
    assert rows == [("llm_call", rows[0][1])] and rows[0][1]["purpose"] == "agent:data"


def test_turn_context_reaches_llm_calls_in_thread_pool(monkeypatch):
    """run_in_executor doesn't propagate ContextVars by itself; our wrapper must."""
    seen = {}

    def fake_get_llm_response(messages, purpose, response_format):
        seen["turn"] = current_turn.get()
        seen["purpose"] = llm_service._purpose_var.get()
        return "ok"

    monkeypatch.setattr(llm_service, "get_llm_response", fake_get_llm_response)
    turn = TurnCollector(user_id=uuid4(), conversation_id=uuid4())

    async def main():
        token = current_turn.set(turn)
        try:
            return await llm_service.get_llm_response_async([{"role": "user", "content": "hi"}], purpose="memory_extraction")
        finally:
            current_turn.reset(token)

    assert asyncio.run(main()) == "ok"
    assert seen["turn"] is turn and seen["purpose"] == "memory_extraction"


def test_finish_queues_one_turn_row_with_derived_totals():
    _drain()
    turn = TurnCollector(user_id=uuid4(), conversation_id=uuid4())
    turn.tool_started("1", "a", {})
    time.sleep(0.04)
    turn.tool_finished("1", "a", ok=True)
    turn.tool_finished("2", "b", ok=False)  # response without a matching call: counted, no time
    turn.finish(message_id=None, agent_name="code", error=False)
    (kind, row), = _drain()
    assert kind == "turn" and row["tool_calls"] == 2 and row["agent_name"] == "code"
    assert 40 <= row["tool_ms"] < 200


def test_tool_success_uses_mcp_iserror_flag_not_text():
    from app.services.metrics.collector import _tool_succeeded
    assert _tool_succeeded({"content": [{"type": "text", "text": "Rows: 10"}], "isError": False}) is True
    assert _tool_succeeded({"content": [], "isError": True}) is False
    assert _tool_succeeded({"error": "boom"}) is False


def test_daily_series_is_zero_filled_oldest_first_and_bounded():
    from datetime import date, datetime
    from types import SimpleNamespace

    from app.api.metrics import daily_series

    today = date(2026, 11, 18)
    turns = [
        SimpleNamespace(created_at=datetime(2026, 11, 18, 9), error=False),
        SimpleNamespace(created_at=datetime(2026, 11, 18, 10), error=True),
        SimpleNamespace(created_at=datetime(2026, 11, 16, 23, 59), error=False),
        SimpleNamespace(created_at=datetime(2026, 11, 1), error=False),  # outside the window
    ]
    tokens = [(date(2026, 11, 18), 1500), (date(2026, 11, 16), None)]
    series = daily_series(turns, tokens, 3, today)
    assert [d["date"] for d in series] == ["2026-11-16", "2026-11-17", "2026-11-18"]
    assert series[1] == {"date": "2026-11-17", "turns": 0, "errors": 0, "tokens": 0}  # empty day kept
    assert series[2] == {"date": "2026-11-18", "turns": 2, "errors": 1, "tokens": 1500}
    assert series[0]["turns"] == 1 and series[0]["tokens"] == 0
