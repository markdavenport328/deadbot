"""Ask the page-quality questions live and score each delivered page.

    PYTHONPATH=. python scripts/page_eval.py [--runs 1] [--case ID ...] [--out DIR]
    PYTHONPATH=. python scripts/page_eval.py --rescore DIR

Each question is one live model turn through scripts/live_check.py (OpenAI,
cache off), run in parallel. The pages are scored by deadbot.page_quality and
summarized in a table; ``summary.json`` in the output folder keeps every
finding. ``--rescore`` scores saved runs again without asking anything, so a
change to the scorer can be checked for free.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from deadbot.page_quality import score_page  # noqa: E402

DEFAULT_SUITE = ROOT / "evals" / "page-quality-v1.json"


def _ask(question: str, out_dir: Path) -> Path | None:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    env.setdefault("DEADBOT_OPENAI_REASONING_EFFORT", "low")
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "live_check.py"), "ask", question, "--out", str(out_dir)],
        capture_output=True,
        text=True,
        env=env,
        timeout=600,
    )
    match = re.search(r"saved (\S+\.ndjson)", completed.stdout)
    return Path(match.group(1)) if match else None


def _response(stream: Path) -> dict | None:
    for line in stream.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("type") == "response":
            return event["response"]
    return None


def _row(case_id: str, run: int, scored: dict | None) -> str:
    if scored is None:
        return f"{case_id:<18} {run:>3}  no response"
    expected = scored.get("expected")
    shape = "—" if expected is None else ("yes" if expected["met"] else f"NO ({expected['wanted']})")
    return (
        f"{case_id:<18} {run:>3}  {shape:<24} {len(scored['repeats']):>7} {len(scored['catalog']):>7} "
        f"{len(scored['narration']):>9} {len(scored['hedges']):>6} {scored['page_words']:>6}"
    )


def report(results: list[dict]) -> None:
    print(f"{'case':<18} {'run':>3}  {'expected shape':<24} {'repeats':>7} {'catalog':>7} {'narration':>9} {'hedges':>6} {'words':>6}")
    for result in results:
        print(_row(result["case"], result["run"], result.get("score")))
    scored = [result["score"] for result in results if result.get("score")]
    if scored:
        shapes = [score["expected"]["met"] for score in scored if "expected" in score]
        print(
            f"\n{len(scored)} pages · clean writing {sum(score['clean'] for score in scored)}/{len(scored)}"
            f" · expected shape {sum(shapes)}/{len(shapes)}"
            f" · repeats {sum(len(score['repeats']) for score in scored)}"
            f" · catalog {sum(len(score['catalog']) for score in scored)}"
            f" · narration {sum(len(score['narration']) for score in scored)}"
            f" · hedges {sum(len(score['hedges']) for score in scored)}"
            f" · median page words {sorted(score['page_words'] for score in scored)[len(scored) // 2]}"
        )
    print("\nFindings:")
    for result in results:
        score = result.get("score") or {}
        for kind in ("repeats", "catalog", "narration", "hedges"):
            for finding in score.get(kind, []):
                print(f"  {result['case']} #{result['run']} {kind}: {finding}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--case", action="append", help="case id to run (repeatable); default all")
    parser.add_argument("--runs", type=int, default=1, help="live runs per case")
    parser.add_argument("--parallel", type=int, default=4)
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "page-eval" / time.strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--rescore", type=Path, help="score a saved output folder again without new model turns")
    args = parser.parse_args()

    suite = json.loads(args.suite.read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in suite["cases"]}

    if args.rescore:
        saved = json.loads((args.rescore / "summary.json").read_text(encoding="utf-8"))
        results = []
        for entry in saved["results"]:
            response = _response(Path(entry["stream"])) if entry.get("stream") else None
            expect = cases.get(entry["case"], {}).get("expect")
            results.append({**entry, "score": score_page(response, expect) if response else None})
        report(results)
        return

    selected = [cases[case_id] for case_id in args.case] if args.case else list(cases.values())
    jobs = [(case, run) for case in selected for run in range(1, args.runs + 1)]
    args.out.mkdir(parents=True, exist_ok=True)
    print(f"Asking {len(jobs)} questions live; saving to {args.out}", file=sys.stderr)

    def run_job(job: tuple[dict, int]) -> dict:
        case, run = job
        stream = _ask(case["question"], args.out)
        response = _response(stream) if stream else None
        if response is None:
            # A turn that never reached the model (a dropped connection under
            # parallel load) is asked once more rather than scored as a page.
            time.sleep(5)
            stream = _ask(case["question"], args.out)
            response = _response(stream) if stream else None
        return {
            "case": case["id"],
            "run": run,
            "question": case["question"],
            "stream": str(stream) if stream else None,
            "score": score_page(response, case.get("expect")) if response else None,
        }

    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        results = list(pool.map(run_job, jobs))
    (args.out / "summary.json").write_text(json.dumps({"suite": suite["suite_id"], "results": results}, indent=1), encoding="utf-8")
    report(results)


if __name__ == "__main__":
    main()
