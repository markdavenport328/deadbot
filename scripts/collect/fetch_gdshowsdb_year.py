#!/usr/bin/env python3
"""Preserve one gdshowsdb year file as a source record in raw JSONL.

Usage:
    python3 scripts/collect/fetch_gdshowsdb_year.py 1972

The GitHub Contents API response, including its base64-encoded file body and
blob SHA, is retained without parsing or normalization. This script fetches no
audio and overwrites no existing raw record unless --force is supplied.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen


REPOSITORY = "jefmsmit/gdshowsdb"


def fetch_json(url: str) -> dict:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "deadbot-raw-collection-pilot",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("year", type=int, help="four-digit Grateful Dead show year")
    parser.add_argument(
        "--output",
        type=Path,
        help="raw JSONL destination (defaults to data/raw/shows/gdshowsdb-<year>.jsonl)",
    )
    parser.add_argument("--force", action="store_true", help="replace an existing output file")
    args = parser.parse_args()

    if args.year < 1965 or args.year > 1995:
        parser.error("year must be between 1965 and 1995")

    source_path = f"data/gdshowsdb/{args.year}.yaml"
    api_url = f"https://api.github.com/repos/{REPOSITORY}/contents/{source_path}?ref=main"
    output = args.output or Path(f"data/raw/shows/gdshowsdb-{args.year}.jsonl")

    if output.exists() and not args.force:
        parser.error(f"refusing to overwrite {output}; use --force to replace it")

    payload = fetch_json(api_url)
    record = {
        "source": "gdshowsdb",
        "source_record_id": f"github-blob:{payload['sha']}",
        "retrieved_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_url": payload["html_url"],
        "raw_payload": payload,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Preserved {source_path} at {output} (blob {payload['sha']}).")


if __name__ == "__main__":
    main()
