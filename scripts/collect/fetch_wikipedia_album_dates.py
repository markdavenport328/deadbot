#!/usr/bin/env python3
"""Collect Wikipedia's infobox release date for studio albums with an imprecise
``official_releases.release_date``.

Follows the conventions of ``fetch_musicbrainz_studio_releases.py``: argparse,
one request per second (plus backoff on 429/503, honoring ``Retry-After``), a
JSON checkpoint that lets an interrupted run resume without repeating a
completed request, and compact JSONL raw records.

Scope: every ``studio`` row in ``data/canonical/official_releases.csv`` whose
``release_date`` is a bare year (4 characters) or a year-month (7 characters).
That set is read from the CSV itself, not hardcoded, so it always matches
whatever the canonical table currently holds.

Per album, two requests:

1. **Search** (``action=query&list=search``) for the album title, artist name
   and the word "album", to find the Wikipedia article. Album titles are
   frequently ambiguous or shared with the artist's own page ("Ace" is
   "Ace (Bob Weir album)"; two different Kingfish albums are both titled
   "Kingfish"), so a candidate is accepted only when it can be identified with
   confidence:

   - ``ARTICLE_TITLES`` below names the exact article for each of the 25
     albums in scope today, decided by inspecting real search results and
     reading the candidate articles' infoboxes (see the accompanying reasons).
     The search step still runs for real and the chosen title must appear
     among its results before it is trusted -- if Wikipedia has renamed or
     removed the article, the album is held rather than silently fetching the
     wrong page.
   - An album added later with no curated entry falls back to a generic rule:
     a candidate qualifies only when its title, with any trailing
     parenthetical removed, folds identically to the album title, and either
     it carries no parenthetical at all or the parenthetical names the artist
     or the word "album". Exactly one qualifying candidate is required; zero
     or several are held as ``ambiguous_search_results``.

2. **Read** (``action=query&prop=revisions`` with ``rvprop=content|ids`` and
   ``rvslots=main``) for that article's current wikitext. The infobox
   ``Released`` field is extracted with a regex that starts at
   ``| released =`` (case-insensitive) and stops at the next line that begins
   a new infobox field or the infobox's closing ``}}``, whichever comes
   first. The captured string is kept exactly as written -- including any
   ``<ref>...</ref>`` citation, wikilink brackets, or ``{{Start date|...}}``
   template -- and normalization happens later, in
   ``scripts/normalize_wikipedia_album_dates.py``.

Every fetched record is written to ``data/raw/releases/wikipedia-album-dates.jsonl``
with the article title, page id, revision id, full article URL, and the raw
``Released`` string. Nothing else about the article is stored: this pass never
retains article prose, images, or full wikitext, matching the
``metadata_only`` / ``store_content: false`` retention policy registered for
``wikipedia-api`` in ``data/source_registry.json``.

An album that cannot be matched to a confident article, or whose article has
no parseable ``Released`` field in its infobox, is recorded in the run
summary's ``held`` list with a reason, and simply has no row in the raw JSONL
-- ``scripts/normalize_wikipedia_album_dates.py`` treats "no raw record" as
"no article", exactly as the governing spec asks.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "releases"
OUTPUT_PATH = RAW_DIR / "wikipedia-album-dates.jsonl"
CHECKPOINT_PATH = RAW_DIR / "wikipedia-album-dates.checkpoint.json"
RUN_SUMMARY_PATH = RAW_DIR / "wikipedia-album-dates.run.json"
CANONICAL_RELEASES_CSV = ROOT / "data" / "canonical" / "official_releases.csv"

API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "DeadBot/0.1 (local album release-date collection; contact unavailable)"
REQUEST_INTERVAL_SECONDS = 1.5
MAX_ATTEMPTS = 6
DEFAULT_BACKOFF_SECONDS = 20
MAX_BACKOFF_SECONDS = 90
SEARCH_LIMIT = 15

# Curated article titles for the 25 albums in scope on 2026-09-06, each decided
# by running the search step for real and then reading the candidate article's
# infobox to confirm the artist and (where two albums share a title) the year.
# Keyed by official_releases.csv's release_id, which is stable and unique.
ARTICLE_TITLES: dict[str, tuple[str, str]] = {
    "release-hooteroll": (
        "Hooteroll?",
        "only Wikipedia article titled 'Hooteroll?'; infobox artist is 'Howard Wales and Jerry Garcia'",
    ),
    "release-new-riders-of-the-purple-sage": (
        "New Riders of the Purple Sage (album)",
        "'(album)' disambiguates the self-titled 1971 debut from the band's own 'New Riders of the Purple Sage' article",
    ),
    "release-gypsy-cowboy": (
        "Gypsy Cowboy",
        "only Wikipedia article titled 'Gypsy Cowboy'",
    ),
    "release-powerglide": (
        "Powerglide (album)",
        "'(album)' disambiguates from unrelated topics named Powerglide",
    ),
    "release-the-adventures-of-panama-red": (
        "The Adventures of Panama Red",
        "only Wikipedia article with this title",
    ),
    "release-compliments-of-garcia": (
        "Garcia (1974 album)",
        "Wikipedia titles this article 'Garcia', subtitled 'also known as Compliments'; infobox cover file is "
        "'GarciaComplimentsCD.jpg' and it is explicitly disambiguated from Jerry Garcia's 1972 self-titled album",
    ),
    "release-oh-what-a-mighty-time": (
        "Oh, What a Mighty Time",
        "only Wikipedia article with this title",
    ),
    "release-new-riders": (
        "New Riders (album)",
        "'(album)' disambiguates from the band's own article and the 1971 self-titled debut",
    ),
    "release-who-are-those-guys": (
        "Who Are Those Guys?",
        "only Wikipedia article with this title",
    ),
    "release-cats-under-the-stars": (
        "Cats Under the Stars",
        "only Wikipedia article with this title",
    ),
    "release-heaven-help-the-fool": (
        "Heaven Help the Fool",
        "only Wikipedia article with this title",
    ),
    "release-trident": (
        "Trident (Kingfish album)",
        "'(Kingfish album)' distinguishes from 'Trident (disambiguation)' and other Tridents",
    ),
    "release-feelin-all-right": (
        "Feelin' All Right",
        "only Wikipedia article with this title",
    ),
    "release-kingfish-1976": (
        "Kingfish (1976 album)",
        "the release_id's own '1976' distinguishes it from the band's second self-titled 1985 album",
    ),
    "release-kingfish-1985": (
        "Kingfish (1985 album)",
        "the release_id's own '1985' distinguishes it from the band's first self-titled 1976 album",
    ),
    "release-before-time-began": (
        "Before Time Began",
        "only Wikipedia article with this title",
    ),
    "release-keep-on-keepin-on": (
        "Keep On Keepin' On (New Riders of the Purple Sage album)",
        "full disambiguated title distinguishes from the unrelated 'Keep On Keeping On' article",
    ),
    "release-jerry-garcia-david-grisman": (
        "Jerry Garcia / David Grisman",
        "only Wikipedia article with this title",
    ),
    "release-marin-county-line": (
        "Marin County Line",
        "only Wikipedia article with this title",
    ),
    "release-midnight-moonlight": (
        "Midnight Moonlight",
        "only Wikipedia article with this title",
    ),
    "release-ace": (
        "Ace (Bob Weir album)",
        "'(Bob Weir album)' distinguishes from 'Ace (disambiguation)' and other unrelated Aces",
    ),
    "release-brujo": (
        "Brujo",
        "only Wikipedia article with this title",
    ),
    "release-reflections": (
        "Reflections (Jerry Garcia album)",
        "'(Jerry Garcia album)' distinguishes from the general 'Reflections' disambiguation page",
    ),
    "release-run-for-the-roses": (
        "Run for the Roses (album)",
        "'(album)' distinguishes from the general 'Run for the Roses' article about the horse race",
    ),
    "release-17-pine-avenue": (
        "17 Pine Avenue",
        "only Wikipedia article with this title",
    ),
}

_PAREN = re.compile(r"^(.*?)\s*\(([^()]*)\)\s*$")
_PUNCTUATION = re.compile(r"[^a-z0-9]+")


def _fold(value: str) -> str:
    return _PUNCTUATION.sub(" ", (value or "").casefold()).strip()


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class Client:
    """Paced Wikipedia MediaWiki API client with bounded retries.

    Honors a numeric ``Retry-After`` header on 429/503 when Wikipedia sends
    one (it reliably does), falling back to exponential backoff otherwise.
    """

    def __init__(self) -> None:
        self.request_count = 0
        self._last_request_at = 0.0

    def get(self, params: dict[str, str]) -> tuple[int, str, dict]:
        query = dict(params)
        query["format"] = "json"
        url = API + "?" + urllib.parse.urlencode(query)
        status, payload = 0, {}
        for attempt in range(MAX_ATTEMPTS):
            wait = self._last_request_at + REQUEST_INTERVAL_SECONDS - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            self._last_request_at = time.monotonic()
            self.request_count += 1
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    status = response.status
                    payload = json.loads(response.read().decode("utf-8"))
                return status, url, payload
            except urllib.error.HTTPError as error:
                status = error.code
                retry_after = error.headers.get("Retry-After") if error.headers else None
                try:
                    payload = json.loads(error.read().decode("utf-8"))
                except (ValueError, OSError):
                    payload = {"error": str(error)}
                if status not in (429, 503):
                    return status, url, payload
                try:
                    backoff = min(int(retry_after), MAX_BACKOFF_SECONDS) if retry_after else DEFAULT_BACKOFF_SECONDS
                except ValueError:
                    backoff = DEFAULT_BACKOFF_SECONDS
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                status, payload = 0, {"error": str(error)}
                backoff = min(2 ** (attempt + 1), MAX_BACKOFF_SECONDS)
            print(f"  retry {attempt + 1}/{MAX_ATTEMPTS} after HTTP {status} in {backoff}s", file=sys.stderr)
            time.sleep(backoff)
        return status, url, payload


def load_target_albums() -> list[dict]:
    """Studio rows whose release_date is a bare year or year-month, from the CSV itself."""

    with CANONICAL_RELEASES_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    targets = [
        row
        for row in rows
        if row.get("release_type") == "studio" and len(row.get("release_date", "")) in (4, 7)
    ]
    return sorted(targets, key=lambda row: row["release_id"])


def choose_article(client: Client, album: dict, request_log: list[dict]) -> dict:
    """Search for the album's article and return a chosen-article decision.

    Always performs the search request for real, even for a curated
    ``ARTICLE_TITLES`` entry -- the curated title must appear in the live
    results before it is trusted, so a renamed or deleted article is held
    rather than silently fetched under a stale title.
    """

    # Deliberately excludes the existing (possibly wrong) release_date's year:
    # feeding a year into the query actively suppresses the correct article
    # whenever that year disagrees with Wikipedia's (exactly the albums this
    # pass most needs to see -- four of the 25 turn out to hold a genuine
    # year conflict). SEARCH_LIMIT is widened instead, to 15, which is enough
    # for every self-titled or low-profile title in this catalog ("Kingfish"
    # by Kingfish, "17 Pine Avenue") to surface without that risk.
    query = f"{album['title']} {album['artist_name']} album"
    status, url, payload = client.get({"action": "query", "list": "search", "srsearch": query, "srlimit": str(SEARCH_LIMIT)})
    request_log.append({"step": "search", "release_id": album["release_id"], "url": url, "http_status": status, "at": now_iso()})
    if status != 200:
        return {"status": "held", "reason": "search_request_failed", "detail": f"HTTP {status}: {payload}"}
    results = payload.get("query", {}).get("search", [])
    candidates = [{"title": item.get("title", ""), "pageid": item.get("pageid")} for item in results]

    curated = ARTICLE_TITLES.get(album["release_id"])
    if curated:
        wanted_title, reason = curated
        for rank, candidate in enumerate(candidates):
            if candidate["title"] == wanted_title:
                return {
                    "status": "chosen",
                    "title": candidate["title"],
                    "pageid": candidate["pageid"],
                    "reason": f"curated: {reason} (rank {rank} of {len(candidates)} search results)",
                    "search_candidates": candidates,
                }
        return {
            "status": "held",
            "reason": "curated_title_not_in_search_results",
            "detail": f"expected {wanted_title!r} among live search results, found {[c['title'] for c in candidates]}",
            "search_candidates": candidates,
        }

    # Generic fallback for an album with no curated entry: a candidate
    # qualifies only when its title folds identically to the album title once
    # a trailing parenthetical is stripped, and the parenthetical (if any)
    # names the artist or says "album". Exactly one qualifying candidate is
    # required.
    want = _fold(album["title"])
    artist_words = [word for word in re.split(r"\s+", album["artist_name"]) if len(word) > 2]
    qualifying = []
    for candidate in candidates:
        match = _PAREN.match(candidate["title"])
        base, paren = (match.group(1), match.group(2)) if match else (candidate["title"], "")
        if _fold(base) != want:
            continue
        paren_folded = paren.casefold()
        if paren and not (paren_folded == "album" or "album" in paren_folded or any(word.casefold() in paren_folded for word in artist_words)):
            continue
        qualifying.append(candidate)
    if len(qualifying) == 1:
        chosen = qualifying[0]
        return {
            "status": "chosen",
            "title": chosen["title"],
            "pageid": chosen["pageid"],
            "reason": "heuristic: unique title match with artist/album-qualified or unqualified disambiguator",
            "search_candidates": candidates,
        }
    return {
        "status": "held",
        "reason": "ambiguous_search_results" if qualifying else "no_confident_match",
        "detail": f"{len(qualifying)} qualifying candidates of {len(candidates)} total",
        "search_candidates": candidates,
    }


RELEASED_FIELD_RE = re.compile(r"\|\s*[Rr]eleased\s*=\s*(.*?)(?=\n\s*\||\n\}\})", re.DOTALL)


def extract_released_raw(wikitext: str) -> str | None:
    """The infobox ``Released`` field's value, exactly as written.

    Matches at the first ``| released =`` (case-insensitive on the initial
    letter, matching MediaWiki's own case-insensitivity for the first
    character of a parameter name) and stops at the next line that opens a
    new infobox field or at the infobox's closing ``}}``. A same-line ``|``
    inside a citation template's arguments does not end the match, because
    the lookahead requires the ``|`` to follow a newline.
    """

    match = RELEASED_FIELD_RE.search(wikitext)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def fetch_article(client: Client, title: str, request_log: list[dict], release_id: str) -> dict | None:
    status, url, payload = client.get(
        {"action": "query", "prop": "revisions", "titles": title, "rvprop": "content|ids", "rvslots": "main"}
    )
    request_log.append({"step": "revisions", "release_id": release_id, "url": url, "http_status": status, "at": now_iso()})
    if status != 200:
        return None
    pages = payload.get("query", {}).get("pages", {})
    for page in pages.values():
        if "missing" in page:
            return None
        revisions = page.get("revisions") or []
        if not revisions:
            return None
        revision = revisions[0]
        content = revision.get("slots", {}).get("main", {}).get("*", "")
        return {
            "pageid": page.get("pageid"),
            "title": page.get("title", title),
            "revid": revision.get("revid"),
            "wikitext": content,
        }
    return None


def load_checkpoint() -> dict:
    if CHECKPOINT_PATH.exists():
        return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    return {"albums": {}, "request_log": []}


def save_checkpoint(state: dict) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(json.dumps(state, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="refetch even when the final raw file already exists")
    args = parser.parse_args()

    if OUTPUT_PATH.exists() and not CHECKPOINT_PATH.exists() and not args.force:
        raise SystemExit(f"{OUTPUT_PATH.relative_to(ROOT)} already exists; pass --force to refetch.")

    albums = load_target_albums()
    if not albums:
        raise SystemExit("no studio rows in official_releases.csv have a year-only or year-month release_date")

    state = load_checkpoint()
    client = Client()
    records: dict[str, dict] = {}
    if OUTPUT_PATH.exists():
        for line in OUTPUT_PATH.read_text(encoding="utf-8").splitlines():
            if line:
                record = json.loads(line)
                records[record["source_record_id"]] = record

    for album in albums:
        release_id = album["release_id"]
        if release_id in records:
            continue
        album_state = state["albums"].setdefault(release_id, {})
        if album_state.get("status") == "held":
            continue

        decision = choose_article(client, album, state["request_log"])
        save_checkpoint(state)
        if decision["status"] != "chosen":
            album_state.update({"status": "held", "reason": decision["reason"], "detail": decision.get("detail", "")})
            save_checkpoint(state)
            print(f"{release_id}: held ({decision['reason']})")
            continue

        article = fetch_article(client, decision["title"], state["request_log"], release_id)
        save_checkpoint(state)
        if article is None:
            album_state.update({"status": "held", "reason": "article_fetch_failed", "detail": decision["title"]})
            save_checkpoint(state)
            print(f"{release_id}: held (article_fetch_failed for {decision['title']!r})")
            continue

        released_raw = extract_released_raw(article["wikitext"])
        retrieved_at = now_iso()
        article_url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(article["title"].replace(" ", "_"))
        if released_raw is None:
            album_state.update(
                {
                    "status": "held",
                    "reason": "no_released_field_in_infobox",
                    "detail": f"article {article['title']!r} (pageid {article['pageid']}) has no infobox 'Released' field",
                }
            )
            save_checkpoint(state)
            print(f"{release_id}: held (no_released_field_in_infobox in {article['title']!r})")
            continue

        record = {
            "source": "wikipedia",
            "source_record_id": release_id,
            "retrieved_at": retrieved_at,
            "source_url": article_url,
            "raw_payload": {
                "release_id": release_id,
                "album_title": album["title"],
                "artist_name": album["artist_name"],
                "csv_release_date": album["release_date"],
                "search_query": f"{album['title']} {album['artist_name']} album",
                "search_candidates": decision.get("search_candidates", []),
                "article_choice_reason": decision["reason"],
                "article_title": article["title"],
                "page_id": article["pageid"],
                "revision_id": article["revid"],
                "article_url": article_url,
                "released_raw": released_raw,
            },
        }
        with OUTPUT_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        records[release_id] = record
        album_state.update({"status": "done"})
        save_checkpoint(state)
        print(f"{release_id}: fetched {article['title']!r} released={released_raw!r}")

    held = [
        {"release_id": release_id, **info}
        for release_id, info in state["albums"].items()
        if info.get("status") == "held"
    ]
    fetched = [record["source_record_id"] for record in records.values()]
    summary = {
        "albums_in_scope": len(albums),
        "fetched": sorted(fetched),
        "held": held,
        "total_requests": len(state["request_log"]),
        "completed_at": now_iso(),
        "request_log": state["request_log"],
    }
    RUN_SUMMARY_PATH.write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    if len(fetched) + len(held) >= len(albums):
        CHECKPOINT_PATH.unlink(missing_ok=True)
    else:
        print(f"Checkpoint kept at {CHECKPOINT_PATH.relative_to(ROOT)}; rerun to continue.")
    print(
        f"Fetched {len(fetched)} of {len(albums)} albums to {OUTPUT_PATH.relative_to(ROOT)}; "
        f"{len(held)} held. See {RUN_SUMMARY_PATH.relative_to(ROOT)}."
    )


if __name__ == "__main__":
    main()
