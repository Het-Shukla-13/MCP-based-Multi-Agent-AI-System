"""
Runs eval suites against the REAL agents, MCP tools and database (free-tier models).

- routing: does a message reach an acceptable agent?
- tools:   does the agent call the expected tools and avoid forbidden ones?
- answers: an LLM judge (a DIFFERENT model than the one answering, to limit
           self-preference bias) scores answers against reference facts.
"""

import asyncio
import hashlib
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
from app.services.rag.retriever import retrieve_pipeline
from evals.graders import grade_retrieval, grade_routing, grade_tools, parse_judge, retry_after_seconds

EVAL_EMAIL = "evals@example.com"
FIXTURES = Path(__file__).parent / "fixtures"
# Recall alone rewards dumping whole files into the prompt; a retrieval also has a cost.
RETRIEVAL_CONTEXT_BUDGET = 6000  # characters (~1.5k tokens) of file context per turn
JUDGE_PROMPT = """You are a strict grader. Compare the ANSWER to the REFERENCE facts for the QUESTION.
Score each 1-5:
- correctness: are the reference facts present and correct? (5 = all correct, 1 = wrong/missing)
- grounding: does it avoid invented facts not supported by the question/reference? (5 = nothing invented)
- format: is it clear and well-formatted (lists/tables/code blocks where useful)?
Return ONLY JSON: {"correctness": n, "grounding": n, "format": n, "reason": "one sentence"}"""


def fixtures_fingerprint(fixtures: Path) -> str:
    """Changes when any fixture file (name or bytes) or the chunking code changes."""
    digest = hashlib.sha256()
    for path in sorted(p for p in fixtures.iterdir() if p.is_file()):
        digest.update(path.name.encode() + b"\0" + path.read_bytes())
    for module in ("hierarchy.py", "file_chunkers.py", "file_ingestion.py"):
        digest.update((BACKEND_ROOT / "app/services/file_processing" / module).read_bytes())
    return digest.hexdigest()[:16]


async def setup_workspace(fixtures: Path = FIXTURES) -> tuple[str, str]:
    """
    Eval user + a conversation with the fixture files ingested.

    Reused when the fixtures and the chunking code are unchanged: ingestion
    embeds every chunk, and re-embedding ~200 chunks per run used up the free
    tier's DAILY embedding quota in one afternoon of A/B runs.
    """
    title = f"eval workspace {fixtures.name} {fixtures_fingerprint(fixtures)}"
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == EVAL_EMAIL))).scalar_one_or_none()
        if user is None:
            user = User(email=EVAL_EMAIL, password_hash=hash_password(uuid.uuid4().hex))
            db.add(user)
            await db.commit()
            await db.refresh(user)
        expected = sum(1 for p in fixtures.iterdir() if p.is_file())
        for existing in (await db.execute(select(Conversation).where(
                Conversation.user_id == user.id, Conversation.title == title))).scalars():
            statuses = (await db.execute(select(File.status).where(File.conversation_id == existing.id))).scalars().all()
            if len(statuses) == expected and all(s == "processed" for s in statuses):
                return str(user.id), str(existing.id)
        conversation = Conversation(title=title, user_id=user.id)
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)

        upload_dir = BACKEND_ROOT / "uploads"
        upload_dir.mkdir(exist_ok=True)
        jobs = []
        for path in sorted(p for p in fixtures.iterdir() if p.is_file()):
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


JUDGE_MAX_ATTEMPTS = 4
JUDGE_MAX_WAIT_SECONDS = 60.0


async def _judge(case: dict, answer: str) -> tuple[str, str]:
    """
    -> (raw verdict, judge model). Short rate limits (per minute) are waited out;
    a long one (e.g. tokens per DAY) moves on to the fallback judge model.
    """
    messages = [
        {"role": "system", "content": JUDGE_PROMPT},
        {"role": "user", "content": f"QUESTION:\n{case['message']}\n\nREFERENCE:\n{case['reference']}\n\nANSWER:\n{answer}"},
    ]
    judges = [m for m in (settings.EVAL_JUDGE_MODEL, settings.EVAL_JUDGE_FALLBACK_MODEL) if m]
    last_error: Exception | None = None
    for model in judges:
        for attempt in range(JUDGE_MAX_ATTEMPTS):
            try:
                raw = await asyncio.to_thread(_call_model, model, messages, {"type": "json_object"})
                return raw, model
            except Exception as exc:
                last_error = exc
                delay = retry_after_seconds(exc)
                if delay is None or delay > JUDGE_MAX_WAIT_SECONDS or attempt == JUDGE_MAX_ATTEMPTS - 1:
                    if delay is not None:
                        print(f"  (judge {model} unavailable for ~{delay:.0f}s; trying the next judge)", flush=True)
                    break
                print(f"  (judge {model} rate-limited; waiting {delay:.1f}s)", flush=True)
                await asyncio.sleep(delay + 0.5)
    raise last_error or RuntimeError("no judge model configured")


async def run_answers(cases: list[dict], user_id: str, conversation_id: str) -> list[dict]:
    results = []
    for case in cases:
        try:
            answer = (await agent_registry.get(case["agent"]).run(
                _context(user_id, conversation_id, case["message"], case["agent"]))).content
        except Exception as exc:  # the PRODUCT failed to answer: a real failure
            results.append({"id": case["id"], "agent": case["agent"], "passed": False, "error": str(exc)[:200]})
            continue
        try:
            raw, judge_model = await _judge(case, answer)
            verdict = parse_judge(raw)
            results.append({"id": case["id"], "agent": case["agent"], **verdict, "judge": judge_model,
                            "answer": answer[:400]})
        except Exception as exc:  # the JUDGE (eval infrastructure) failed: inconclusive, not a failure
            results.append({"id": case["id"], "agent": case["agent"], "passed": False, "inconclusive": True,
                            "error": f"judge unavailable: {str(exc)[:160]}", "answer": answer[:400]})
    return results


async def run_retrieval(cases: list[dict], user_id: str, conversation_id: str) -> list[dict]:
    """
    Retrieval only (no LLM): is every expected snippet in the context the agent
    would receive? Uses its own conversation with long, confusable fixtures so
    the other suites' workspace stays unchanged.
    """
    user_id, conversation_id = await setup_workspace(FIXTURES / "retrieval")
    results = []
    for case in cases:
        async with AsyncSessionLocal() as db:
            context = await retrieve_pipeline(case["query"], [], uuid.UUID(conversation_id), uuid.UUID(user_id), db)
        missing = grade_retrieval(context, case["expect"])
        over_budget = len(context) > RETRIEVAL_CONTEXT_BUDGET
        problems = missing + ([f"context {len(context)} chars > budget {RETRIEVAL_CONTEXT_BUDGET}"] if over_budget else [])
        results.append({"id": case["id"], "group": case.get("group"), "passed": not problems,
                        "problems": problems, "context_chars": len(context)})
    return results
