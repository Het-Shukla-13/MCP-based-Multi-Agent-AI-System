"""
Agent eval runner.

    .venv/bin/python -m evals.run                      # all suites, compare to baseline
    .venv/bin/python -m evals.run --suite routing      # one suite
    .venv/bin/python -m evals.run --update-baseline    # accept current scores as the new baseline

Calls the real free-tier models (takes a few minutes; quotas apply). Exits 1 when a
suite's score drops more than --tolerance below the baseline, so it can gate CI.
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

from evals import harness
from evals.graders import summarize

ROOT = Path(__file__).parent
SUITES = {"routing": harness.run_routing, "tools": harness.run_tools, "answers": harness.run_answers}
BASELINE = ROOT / "baseline.json"


def load(name: str) -> list[dict]:
    return [json.loads(line) for line in (ROOT / "datasets" / f"{name}.jsonl").read_text().splitlines() if line.strip()]


async def main(args) -> int:
    logger.remove()
    logger.add(sys.stderr, level="WARNING")  # keep eval output readable
    suites = list(SUITES) if args.suite == "all" else [args.suite]
    user_id, conversation_id = await harness.setup_workspace()
    report = {"run_at": datetime.utcnow().isoformat(timespec="seconds"), "suites": {}}

    for name in suites:
        print(f"\n=== {name} ===", flush=True)
        results = await SUITES[name](load(name), user_id, conversation_id)
        for r in results:
            detail = {k: r[k] for k in ("expected", "actual", "called", "problems", "correctness", "reason", "error") if r.get(k)}
            print(f"  {'PASS' if r['passed'] else 'FAIL'} {r['id']}  {json.dumps(detail)[:180]}", flush=True)
        report["suites"][name] = {"summary": summarize(results), "results": results}
        print(f"  -> {report['suites'][name]['summary']}", flush=True)

    out = ROOT / "results" / f"{report['run_at'].replace(':', '')}.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nSaved {out.relative_to(ROOT.parent)}")

    scores = {name: s["summary"]["score"] for name, s in report["suites"].items()}
    if args.update_baseline:
        baseline = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
        baseline.update(scores)
        BASELINE.write_text(json.dumps(baseline, indent=2) + "\n")
        print(f"Baseline updated: {baseline}")
        return 0
    if not BASELINE.exists():
        print("No baseline yet: run with --update-baseline to record one.")
        return 0
    baseline = json.loads(BASELINE.read_text())
    regressions = {n: (baseline[n], s) for n, s in scores.items() if n in baseline and s < baseline[n] - args.tolerance}
    for n, s in scores.items():
        print(f"  {n:8} {s:.3f}  (baseline {baseline.get(n, '-')})")
    if regressions:
        print(f"REGRESSION: {regressions}")
        return 1
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--suite", choices=["all", *SUITES], default="all")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--tolerance", type=float, default=0.05, help="allowed score drop before failing")
    sys.exit(asyncio.run(main(parser.parse_args())))
