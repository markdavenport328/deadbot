"""Ask the song-stops questions live and measure each page's stops against the library.

    PYTHONPATH=. python scripts/stop_eval.py [--runs 1] [--case ID ...] [--out DIR]
    PYTHONPATH=. python scripts/stop_eval.py --rescore DIR

Each question is one live model turn through scripts/live_check.py (OpenAI,
cache off), run in parallel. Each page is measured by deadbot.stop_quality
against the real SQLite library and summarized in a table; ``summary.json`` in
the output folder keeps every measurement. ``--rescore`` measures saved runs
again without asking anything, so a change to the scorer can be checked for
free.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from deadbot import song_life  # noqa: E402
from deadbot.sqlite_build import build_database  # noqa: E402
from deadbot.sqlite_store import SqliteCanonicalStore  # noqa: E402
from deadbot.stop_quality import score_stops  # noqa: E402

DEFAULT_SUITE = ROOT / "evals" / "song-stops-v1.json"


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


def _turn(stream: Path) -> tuple[dict | None, list[str], float | None]:
    """The delivered page, the tools called and the turn's seconds, from live_check's saved files."""

    response = None
    for line in stream.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("type") == "response":
            response = event["response"]
    dump = stream.with_suffix(".json")
    tools: list[str] = []
    seconds = None
    if dump.exists():
        data = json.loads(dump.read_text(encoding="utf-8"))
        tools = [tool.get("name", "?") for tool in data.get("tools", [])]
        seconds = data.get("seconds")
    return response, tools, seconds


def _row(case_id: str, run: int, s: dict | None) -> str:
    if s is None:
        return f"{case_id:<17} {run:>3}  no response"
    card = ("timeline" if s["timeline"] else "card") if s["song_card"] else "—"
    open_ok = "" if s["open_year_ok"] is None else ("yes" if s["open_year_ok"] else f"no ({s['open_year']})")
    return (
        f"{case_id:<17} {run:>3}  {card:<8} {s['stops_resolved']:>2}/{s['stops_total']:<2} {s['with_why']:>4} {s['years_spanned']:>5} "
        f"{s['span_share']:>5.2f} {s['thirds']:>3} {s['beyond_calendar']:>6} {len(s['fact_issues']):>6} {open_ok:<10} "
        f"{'yes' if s['used_song_life'] else '':<5} {len(s['tools']):>3} {s['seconds'] or 0:>6.1f}"
    )


def report(results: list[dict]) -> None:
    print(f"{'case':<17} {'run':>3}  {'card':<8} {'stops':<5} {'why':>4} {'years':>5} {'span':>5} {'3rd':>3} {'beyond':>6} {'wrong':>6} {'open year':<10} {'life':<5} {'tls':>3} {'secs':>6}")
    for result in results:
        print(_row(result["case"], result["run"], result.get("score")))
    scored = [result["score"] for result in results if result.get("score")]
    if not scored:
        return
    cards = [s for s in scored if s["song_card"]]
    with_stops = [s for s in cards if s["stops_resolved"]]
    stops = sum(s["stops_resolved"] for s in cards)
    year_cases = [s for s in scored if s["open_year_ok"] is not None]
    print(
        f"\n{len(scored)} pages · song card {len(cards)}/{len(scored)} · timeline {sum(s['timeline'] for s in cards)}/{len(scored)}"
        f" · cards with stops {len(with_stops)}/{len(cards)}"
        f" · median stops {statistics.median([s['stops_resolved'] for s in cards]) if cards else 0}"
        f" · stops with a why {sum(s['with_why'] for s in cards)}/{sum(s['stops_total'] for s in cards)}"
        f"\nstops beyond first/last/longest {sum(s['beyond_calendar'] for s in cards)}/{stops}"
        f" · median thirds of the song's life touched {statistics.median([s['thirds'] for s in with_stops]) if with_stops else 0}"
        f" · wrong facts {sum(len(s['fact_issues']) for s in scored)} (unverifiable {sum(s['unverifiable'] for s in scored)})"
        f" · open year right {sum(s['open_year_ok'] for s in year_cases)}/{len(year_cases)}"
        f"\nused get_song_life {sum(s['used_song_life'] for s in scored)}/{len(scored)}"
        f" · median tool calls {statistics.median([len(s['tools']) for s in scored])}"
        f" · median seconds {statistics.median([s['seconds'] or 0 for s in scored]):.1f}"
    )
    print("\nWrong facts:")
    for result in results:
        for issue in (result.get("score") or {}).get("fact_issues", []):
            print(f"  {result['case']} #{result['run']}: {issue}")
    print("\nPages without a song card:")
    for result in results:
        s = result.get("score") or {}
        if s and not s["song_card"]:
            print(f"  {result['case']} #{result['run']}: {', '.join(s['other_blocks']) or 'no blocks'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--case", action="append", help="case id to run (repeatable); default all")
    parser.add_argument("--runs", type=int, default=1, help="live runs per case")
    parser.add_argument("--parallel", type=int, default=4)
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "stop-eval" / time.strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--rescore", type=Path, help="measure a saved output folder again without new model turns")
    args = parser.parse_args()

    suite = json.loads(args.suite.read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in suite["cases"]}

    with tempfile.TemporaryDirectory() as folder:
        store = SqliteCanonicalStore(build_database(Path(folder) / "deadbot.sqlite").path, response_cache_path=Path(folder) / "cache.sqlite")
        lives = {case["song_id"]: song_life.life_performances(store, case["song_id"]) for case in cases.values()}

    def measure(case: dict, stream: Path | None) -> dict | None:
        if stream is None:
            return None
        response, tools, seconds = _turn(stream)
        return score_stops(response, case, lives[case["song_id"]], tools, seconds) if response else None

    if args.rescore:
        saved = json.loads((args.rescore / "summary.json").read_text(encoding="utf-8"))
        results = []
        for entry in saved["results"]:
            stream = Path(entry["stream"]) if entry.get("stream") else None
            results.append({**entry, "score": measure(cases[entry["case"]], stream)})
        report(results)
        return

    selected = [cases[case_id] for case_id in args.case] if args.case else list(cases.values())
    jobs = [(case, run) for case in selected for run in range(1, args.runs + 1)]
    args.out.mkdir(parents=True, exist_ok=True)
    print(f"Asking {len(jobs)} questions live; saving to {args.out}", file=sys.stderr)

    def run_job(job: tuple[dict, int]) -> dict:
        case, run = job
        stream = _ask(case["question"], args.out)
        if stream is None:
            # A turn that never reached the model (a dropped connection under
            # parallel load) is asked once more rather than scored as a page.
            time.sleep(5)
            stream = _ask(case["question"], args.out)
        return {"case": case["id"], "run": run, "question": case["question"], "stream": str(stream) if stream else None, "score": measure(case, stream)}

    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        results = list(pool.map(run_job, jobs))
    (args.out / "summary.json").write_text(json.dumps({"suite": suite["suite_id"], "results": results}, indent=1), encoding="utf-8")
    report(results)


if __name__ == "__main__":
    main()
