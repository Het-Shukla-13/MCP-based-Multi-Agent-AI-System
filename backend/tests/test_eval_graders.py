import pytest

from evals.graders import grade_routing, grade_tools, parse_judge, summarize


def test_routing_accepts_any_listed_agent():
    assert grade_routing(["general", "research"], "research")
    assert not grade_routing(["code"], "general")
    assert not grade_routing(["code"], None)  # provider error


def test_tools_any_of_groups_and_forbidden():
    ok, problems = grade_tools([["table_info", "read_file"], ["aggregate"]], ["web_search"], ["read_file", "aggregate"])
    assert ok and problems == []
    ok, problems = grade_tools([["aggregate"]], ["web_search"], ["web_search"])
    assert not ok and problems == ["missing one of ['aggregate']", "called forbidden web_search"]
    assert grade_tools([], ["create_file"], [])[0]  # "no tool needed" case


def test_judge_parsing_tolerates_fences_and_validates_range():
    v = parse_judge('```json\n{"correctness": 5, "grounding": 4, "format": 3, "reason": "ok"}\n```')
    assert v["passed"] and v["correctness"] == 5
    assert not parse_judge('{"correctness": 3, "grounding": 5, "format": 5}')["passed"]
    with pytest.raises(ValueError):
        parse_judge('{"correctness": 9, "grounding": 5, "format": 5}')


def test_summarize():
    assert summarize([{"passed": True}, {"passed": False}]) == {"cases": 2, "passed": 1, "score": 0.5}


def test_retry_after_parses_groq_and_gemini_rate_limits():
    from evals.graders import retry_after_seconds

    groq = "Error code: 429 - Rate limit reached for model `openai/gpt-oss-20b` ... Please try again in 1m2.5s."
    assert retry_after_seconds(groq) == 62.5
    assert retry_after_seconds("429 rate limit ... Please try again in 7.25s") == 7.25
    assert retry_after_seconds("429 RESOURCE_EXHAUSTED {'retryDelay': '12s'}") == 12.0
    assert retry_after_seconds("429 Too Many Requests") == 10.0  # rate limit, no hint
    assert retry_after_seconds("500 internal error") is None  # not a rate limit: don't wait


def test_inconclusive_cases_are_excluded_and_flagged():
    from evals.graders import summarize

    results = [
        {"id": "a1", "passed": True},
        {"id": "a2", "passed": False},
        {"id": "a3", "passed": False, "inconclusive": True},
    ]
    summary = summarize(results)
    assert summary["cases"] == 2 and summary["passed"] == 1 and summary["score"] == 0.5
    assert summary["inconclusive"] == 1 and summary["trustworthy"] is True  # 1/3 is the limit
    many = summarize([{"id": "a", "passed": True}] + [{"id": f"x{i}", "passed": False, "inconclusive": True} for i in range(2)])
    assert many["trustworthy"] is False
    assert "inconclusive" not in summarize([{"id": "a", "passed": True}])
