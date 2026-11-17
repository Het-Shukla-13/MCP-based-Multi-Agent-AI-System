"""Usage and performance metrics for the signed-in user."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_current_user
from app.db.database import get_db
from app.models import User
from app.models.metrics import LlmCall, TurnMetric

router = APIRouter(prefix="/metrics", tags=["Metrics"])


def percentile(values: list[int], pct: float) -> int | None:
    """Nearest-rank percentile (p50 = median, p95 = 'slow but not worst-case')."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, round(pct / 100 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


@router.get("/turns")
async def recent_turns(limit: int = Query(20, ge=1, le=200), user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(TurnMetric).where(TurnMetric.user_id == user.id).order_by(TurnMetric.created_at.desc()).limit(limit)
    )).scalars().all()
    return [row.model_dump() for row in rows]


@router.get("/summary")
async def summary(days: int = Query(7, ge=1, le=90), user: User = Depends(get_current_user),
                  db: AsyncSession = Depends(get_db)):
    since = datetime.utcnow() - timedelta(days=days)
    turns = (await db.execute(
        select(TurnMetric).where(TurnMetric.user_id == user.id, TurnMetric.created_at >= since)
    )).scalars().all()

    tokens_by_model = (await db.execute(
        select(LlmCall.model, func.count(), func.sum(LlmCall.input_tokens), func.sum(LlmCall.output_tokens))
        .where(LlmCall.user_id == user.id, LlmCall.created_at >= since)
        .group_by(LlmCall.model)
    )).all()
    tokens_by_purpose = (await db.execute(
        select(LlmCall.purpose, func.count(), func.sum(LlmCall.input_tokens + LlmCall.output_tokens))
        .where(LlmCall.user_id == user.id, LlmCall.created_at >= since)
        .group_by(LlmCall.purpose)
    )).all()

    tool_stats: dict[str, dict] = {}
    for turn in turns:
        for tool in turn.tools or []:
            stat = tool_stats.setdefault(tool["tool"], {"calls": 0, "failures": 0, "ms": []})
            stat["calls"] += 1
            stat["failures"] += 0 if tool.get("ok", True) else 1
            if tool.get("ms") is not None:
                stat["ms"].append(tool["ms"])

    ttft = [t.ttft_ms for t in turns if t.ttft_ms is not None]
    total = [t.total_ms for t in turns]
    agents: dict[str, int] = {}
    for t in turns:
        agents[t.agent_name or "unknown"] = agents.get(t.agent_name or "unknown", 0) + 1

    return {
        "days": days,
        "turns": len(turns),
        "error_rate": round(sum(t.error for t in turns) / len(turns), 3) if turns else 0,
        "fallback_rate": round(sum(t.fallback_used for t in turns) / len(turns), 3) if turns else 0,
        "latency_ms": {
            "ttft_p50": percentile(ttft, 50), "ttft_p95": percentile(ttft, 95),
            "total_p50": percentile(total, 50), "total_p95": percentile(total, 95),
        },
        "agents": agents,
        "tools": {
            name: {"calls": s["calls"], "failures": s["failures"], "p50_ms": percentile(s["ms"], 50)}
            for name, s in sorted(tool_stats.items(), key=lambda kv: -kv[1]["calls"])
        },
        "tokens_by_model": [
            {"model": m, "calls": n, "input_tokens": int(i or 0), "output_tokens": int(o or 0)} for m, n, i, o in tokens_by_model
        ],
        "tokens_by_purpose": [
            {"purpose": p, "calls": n, "tokens": int(t or 0)} for p, n, t in sorted(tokens_by_purpose, key=lambda r: -(r[2] or 0))
        ],
        # All models used are free tiers; tokens are tracked so a paid model's cost
        # could be computed later (tokens x price per token).
        "cost_usd": 0.0,
    }
