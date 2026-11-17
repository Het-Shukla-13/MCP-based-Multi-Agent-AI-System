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
