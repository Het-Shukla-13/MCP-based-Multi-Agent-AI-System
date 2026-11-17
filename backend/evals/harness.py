"""
Runs eval suites against the REAL agents, MCP tools and database (free-tier models).

- routing: does a message reach an acceptable agent?
- tools:   does the agent call the expected tools and avoid forbidden ones?
- answers: an LLM judge (a DIFFERENT model than the one answering, to limit
           self-preference bias) scores answers against reference facts.
"""

import asyncio
import shutil
import uuid
from pathlib import Path
from time import perf_counter

from sqlmodel import select

from app.agent_layer.agents.root_agent import RootAgent
from app.agent_layer.core import agent_registry
from app.agent_layer.core.mentions import parse_agent_mention
from app.agent_layer.schemas import AgentContext
from app.core.config import BACKEND_ROOT, settings
from app.core.security import hash_password
from app.db.database import AsyncSessionLocal
from app.models import Conversation, File, User
from app.services.file_processing.file_ingestion import ingest_file
from app.services.llm.llm_service import _call_model
from app.services.metrics.collector import TurnCollector, current_turn
from evals.graders import grade_routing, grade_tools, parse_judge

EVAL_EMAIL = "evals@example.com"
FIXTURES = Path(__file__).parent / "fixtures"
JUDGE_PROMPT = """You are a strict grader. Compare the ANSWER to the REFERENCE facts for the QUESTION.
Score each 1-5:
- correctness: are the reference facts present and correct? (5 = all correct, 1 = wrong/missing)
- grounding: does it avoid invented facts not supported by the question/reference? (5 = nothing invented)
- format: is it clear and well-formatted (lists/tables/code blocks where useful)?
Return ONLY JSON: {"correctness": n, "grounding": n, "format": n, "reason": "one sentence"}"""


async def setup_workspace() -> tuple[str, str]:
    """Eval user + a fresh conversation with the fixture files ingested."""
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == EVAL_EMAIL))).scalar_one_or_none()
        if user is None:
            user = User(email=EVAL_EMAIL, password_hash=hash_password(uuid.uuid4().hex))
            db.add(user)
            await db.commit()
            await db.refresh(user)
        conversation = Conversation(title="eval run", user_id=user.id)
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)

        upload_dir = BACKEND_ROOT / "uploads"
        upload_dir.mkdir(exist_ok=True)
        jobs = []
        for path in sorted(FIXTURES.iterdir()):
            target = upload_dir / f"{uuid.uuid4()}_{path.name}"
            shutil.copy(path, target)
            record = File(conversation_id=conversation.id, user_id=user.id, filename=path.name,
                          file_type="text/plain", file_size=path.stat().st_size, storage_path=str(target))
            db.add(record)
            await db.commit()
            await db.refresh(record)
            jobs.append((str(record.id), str(target)))
    for file_id, target in jobs:
        await asyncio.to_thread(ingest_file, file_id, target)
    return str(user.id), str(conversation.id)


def _context(user_id: str, conversation_id: str, message: str, agent: str | None = None) -> AgentContext:
    return AgentContext(user_id=user_id, conversation_id=conversation_id, user_message=message, selected_agent=agent)


async def run_routing(cases: list[dict], user_id: str, conversation_id: str) -> list[dict]:
    root, results = RootAgent(), []
    for case in cases:
        mention, text = parse_agent_mention(case["message"], root.valid_agents)
        started = perf_counter()
        try:
            response = await root.run(_context(user_id, conversation_id, text, mention))
            actual, error = response.agent_name, None
        except Exception as exc:  # provider errors are recorded, not fatal
            actual, error = None, str(exc)[:200]
        results.append({"id": case["id"], "expected": case["expected"], "actual": actual, "error": error,
                        "passed": grade_routing(case["expected"], actual), "ms": int((perf_counter() - started) * 1000)})
    return results


async def run_tools(cases: list[dict], user_id: str, conversation_id: str) -> list[dict]:
    results = []
    for case in cases:
        # Reuse the metrics collector to observe which tools the agent called.
        turn = TurnCollector(user_id=uuid.UUID(user_id), conversation_id=uuid.UUID(conversation_id))
        token = current_turn.set(turn)
        try:
            await agent_registry.get(case["agent"]).run(_context(user_id, conversation_id, case["message"], case["agent"]))
            error = None
        except Exception as exc:
            error = str(exc)[:200]
        finally:
            current_turn.reset(token)
        called = [t["tool"] for t in turn.tools]
        passed, problems = grade_tools(case["must_call"], case["must_not_call"], called)
        results.append({"id": case["id"], "agent": case["agent"], "called": called, "problems": problems,
                        "error": error, "passed": passed and error is None})
    return results


async def run_answers(cases: list[dict], user_id: str, conversation_id: str) -> list[dict]:
    results = []
    for case in cases:
        try:
            answer = (await agent_registry.get(case["agent"]).run(
                _context(user_id, conversation_id, case["message"], case["agent"]))).content
            raw = await asyncio.to_thread(_call_model, settings.EVAL_JUDGE_MODEL, [
                {"role": "system", "content": JUDGE_PROMPT},
                {"role": "user", "content": f"QUESTION:\n{case['message']}\n\nREFERENCE:\n{case['reference']}\n\nANSWER:\n{answer}"},
            ], {"type": "json_object"})
            verdict = parse_judge(raw)
            results.append({"id": case["id"], "agent": case["agent"], **verdict, "answer": answer[:400]})
        except Exception as exc:
            results.append({"id": case["id"], "agent": case["agent"], "passed": False, "error": str(exc)[:200]})
    return results
