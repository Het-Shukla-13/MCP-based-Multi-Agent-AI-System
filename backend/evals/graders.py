"""Pure grading functions: no LLM, no I/O, so they are unit-tested."""

import json
import re


def grade_routing(expected: list[str], actual: str | None) -> bool:
    """Pass if the chosen agent is one of the acceptable ones."""
    return actual in expected


def grade_tools(must_call: list[list[str]], must_not_call: list[str], called: list[str]) -> tuple[bool, list[str]]:
    """
    must_call is a list of ANY-OF groups: [["table_info", "read_file"], ["aggregate"]]
    means (table_info OR read_file) AND aggregate. must_not_call: none may appear.
    """
    problems = []
    for group in must_call:
        if not any(tool in called for tool in group):
            problems.append(f"missing one of {group}")
    for tool in must_not_call:
        if tool in called:
            problems.append(f"called forbidden {tool}")
    return not problems, problems


def parse_judge(raw: str) -> dict:
    """Parse the judge's JSON (tolerating code fences) and decide pass/fail."""
    text = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    data = json.loads(text)
    scores = {k: int(data[k]) for k in ("correctness", "grounding", "format")}
    if not all(1 <= v <= 5 for v in scores.values()):
        raise ValueError(f"score out of range: {scores}")
    return {**scores, "reason": str(data.get("reason", ""))[:300], "passed": scores["correctness"] >= 4}


def grade_retrieval(context: str, expect: list[str]) -> list[str]:
    """Expected snippets missing from the retrieved context (case-insensitive)."""
    haystack = " ".join(context.lower().split())
    return [e for e in expect if " ".join(e.lower().split()) not in haystack]


def summarize(results: list[dict]) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    summary = {"cases": total, "passed": passed, "score": round(passed / total, 3) if total else 0.0}
    groups = sorted({r["group"] for r in results if r.get("group")})
    if groups:
        summary["by_group"] = {
            g: f"{sum(r['passed'] for r in results if r.get('group') == g)}/{sum(r.get('group') == g for r in results)}"
            for g in groups
        }
    if any("context_chars" in r for r in results):
        summary["avg_context_chars"] = int(sum(r.get("context_chars", 0) for r in results) / total)
    return summary
