# Albums as a Data Type Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Deadbot studio albums and a song-to-album relationship, so it can answer which record a song appeared on and present an album as a browsable object.

**Architecture:** Studio albums become rows in the existing `official_releases` table with `release_type='studio'`, rather than a parallel album table. Release tracks gain a nullable `song_id` so a track can name a composition directly — a studio track has no performance, because a performance is a song played at a show. A new `release_personnel` table records who played on a record, and a new `album_unit` semantic unit composes it for the browser.

**Tech Stack:** Python 3.11+, pytest, psycopg 3, FastAPI, Pydantic v2, LangGraph, React + Vite + TypeScript, PostgreSQL, MusicBrainz web service.

**Spec:** `docs/superpowers/specs/2026-09-05-album-data-type-design.md`

## Global Constraints

- Schema version moves 4 → 5. Exactly one migration file per version, named `NNN_*.sql`, and it must set `deadbot_schema_metadata.schema_version` itself or the importer raises `SchemaMigrationRequired`.
- Canonical CSV headers and database columns must match exactly, in order. The importer's `TABLE_SPECS` is the contract for both.
- Canonical IDs are lowercase kebab-case text, never database-generated. Never replace an established ID because a display name changed.
- Collection is fail-closed: an unresolved title match, failed request, or missing value is recorded in a review log and left empty. Never promote a guessed value. See `docs/collection-methodology.md`.
- Normalizer scripts must produce byte-identical output on a rerun, must manage only rows their own `notes` marker identifies, and must reuse previously assigned release IDs.
- MusicBrainz access: one request per second, descriptive User-Agent `DeadBot/0.1 (local studio-release collection; contact unavailable)`, backoff on 429/503, checkpoint after every page.
- The CSV store (`deadbot/data.py`) and the Postgres store (`deadbot/postgres.py`) must change together. A one-sided change makes the two modes disagree silently.
- Catalog scope: Grateful Dead studio albums plus Garcia, Ace, New Riders of the Purple Sage, Old & In the Way, Kingfish, Jerry Garcia Band. No compilations, no singles, no non-Dead-family discography.
- `release_type` vocabulary: `studio`, `live`, `compilation`, `single`.
- Run Python tests with `python -m pytest`. Run web type generation with `npm run gen:types` from `web/`.
- Per `AGENTS.md`, agents cannot push to GitHub. Commit locally; the owner runs `git push`.

---

### Task 1: Schema, CSV shape, and importer contract

Adds the `song_id` column, the `release_personnel` table, and the release-type constraint. No album data yet — this establishes the shape everything else writes into.

**Files:**
- Create: `schema/migrations/005_studio_releases.sql`
- Create: `data/canonical/release_personnel.csv` (header only)
- Modify: `schema/postgres.sql:14` (version seed), `schema/postgres.sql:261-283` (releases and tracks)
- Modify: `deadbot/postgres_import.py:26` (`SCHEMA_VERSION`), `deadbot/postgres_import.py:107-108` (specs)
- Modify: `data/canonical/official_release_tracks.csv` (add `song_id` column)
- Modify: `schema/README.md`, `schema/domain-model.md`, `data/canonical/README.md`
- Test: `tests/test_postgres_import.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `SCHEMA_VERSION = 5`; a `TableSpec` named `release_personnel` with columns `("release_id", "person_id", "role", "instrument", "notes")`; `official_release_tracks` columns become `("release_id", "track_number", "performance_id", "song_id", "track_title", "duration_seconds", "spotify_track_url", "notes")`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_postgres_import.py`:

```python
def test_release_track_spec_carries_a_nullable_song_id():
    spec = next(spec for spec in TABLE_SPECS if spec.name == "official_release_tracks")
    assert spec.columns == (
        "release_id",
        "track_number",
        "performance_id",
        "song_id",
        "track_title",
        "duration_seconds",
        "spotify_track_url",
        "notes",
    )
    assert "song_id" in spec.nullable


def test_release_personnel_spec_follows_show_performers_and_loads_after_releases():
    spec = next(spec for spec in TABLE_SPECS if spec.name == "release_personnel")
    assert spec.columns == ("release_id", "person_id", "role", "instrument", "notes")
    assert spec.nullable == frozenset({"notes"})
    names = [spec.name for spec in TABLE_SPECS]
    assert names.index("release_personnel") > names.index("official_releases")
    assert names.index("release_personnel") > names.index("people")


def test_schema_version_is_five_and_has_exactly_one_migration():
    assert SCHEMA_VERSION == 5
    migrations = sorted(Path("schema/migrations").glob("005_*.sql"))
    assert len(migrations) == 1
    sql = migrations[0].read_text(encoding="utf-8")
    assert "ALTER TABLE official_release_tracks" in sql
    assert "CREATE TABLE release_personnel" in sql
    assert "schema_version" in sql


def test_every_spec_matches_its_canonical_csv_header():
    for spec in TABLE_SPECS:
        path = Path("data/canonical") / spec.csv_name
        with path.open(newline="", encoding="utf-8") as source:
            header = tuple(next(csv.reader(source)))
        assert header == spec.columns, spec.name
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_postgres_import.py -k "song_id or release_personnel or schema_version_is_five or csv_header" -v`
Expected: FAIL — `song_id` not in the spec columns, no `release_personnel` spec, `SCHEMA_VERSION == 4`, no `005_*.sql`.

- [ ] **Step 3: Add the `song_id` column to the tracks CSV**

The file has 10,045 data rows; insert the empty column in position 4 mechanically rather than by hand.

```bash
python - <<'PY'
import csv
from pathlib import Path

path = Path("data/canonical/official_release_tracks.csv")
with path.open(newline="", encoding="utf-8") as source:
    rows = list(csv.DictReader(source))

columns = [
    "release_id", "track_number", "performance_id", "song_id",
    "track_title", "duration_seconds", "spotify_track_url", "notes",
]
with path.open("w", newline="", encoding="utf-8") as target:
    writer = csv.DictWriter(target, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
print(f"rewrote {len(rows)} rows")
PY
```

Expected: `rewrote 10045 rows`.

- [ ] **Step 4: Create the personnel CSV, header only**

```bash
printf 'release_id,person_id,role,instrument,notes\n' > data/canonical/release_personnel.csv
```

- [ ] **Step 5: Write the migration**

Create `schema/migrations/005_studio_releases.sql`:

```sql
-- Studio albums join the release catalog rather than forming a parallel one.
-- A studio track has no performance, because a performance is a song played
-- at a show, so a track may name its composition directly.
BEGIN;

ALTER TABLE official_release_tracks
    ADD COLUMN song_id TEXT REFERENCES songs (song_id) ON DELETE SET NULL;

CREATE INDEX official_release_tracks_song_id_idx
    ON official_release_tracks (song_id);

-- The 294 existing rows are all 'live' and already conform.
ALTER TABLE official_releases
    ADD CONSTRAINT official_releases_release_type_check
    CHECK (release_type IN ('studio', 'live', 'compilation', 'single'));

-- One row per person's role-and-instrument credit on a release, shaped like
-- show_performers.  instrument is NOT NULL because it is part of the key.
CREATE TABLE release_personnel (
    release_id TEXT NOT NULL REFERENCES official_releases (release_id) ON DELETE CASCADE,
    person_id TEXT NOT NULL REFERENCES people (person_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    instrument TEXT NOT NULL,
    notes TEXT,
    PRIMARY KEY (release_id, person_id, role, instrument)
);

UPDATE deadbot_schema_metadata SET schema_version = 5;

COMMIT;
```

- [ ] **Step 6: Apply the same shape to the bootstrap schema**

In `schema/postgres.sql`, change the version seed at line 14 to `VALUES (5);`. In the `official_releases` block, add after `notes TEXT`:

```sql
    CHECK (release_type IN ('studio', 'live', 'compilation', 'single'))
```

In `official_release_tracks`, add `song_id` after `performance_id`:

```sql
    song_id TEXT REFERENCES songs (song_id) ON DELETE SET NULL,
```

After the `official_release_tracks` block, add the table and index:

```sql
CREATE INDEX official_release_tracks_song_id_idx
    ON official_release_tracks (song_id);

CREATE TABLE release_personnel (
    release_id TEXT NOT NULL REFERENCES official_releases (release_id) ON DELETE CASCADE,
    person_id TEXT NOT NULL REFERENCES people (person_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    instrument TEXT NOT NULL,
    notes TEXT,
    PRIMARY KEY (release_id, person_id, role, instrument)
);
```

- [ ] **Step 7: Update the importer contract**

In `deadbot/postgres_import.py`, set `SCHEMA_VERSION = 5` at line 26. Replace the `official_release_tracks` spec and add the personnel spec immediately after it:

```python
    _spec("official_release_tracks", "release_id track_number performance_id song_id track_title duration_seconds spotify_track_url notes", nullable=("performance_id", "song_id", "duration_seconds", "spotify_track_url", "notes"), integers=("track_number", "duration_seconds")),
    _spec("release_personnel", "release_id person_id role instrument notes", nullable=("notes",)),
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `python -m pytest tests/test_postgres_import.py -v`
Expected: PASS, including the pre-existing import tests.

- [ ] **Step 9: Update the schema documentation**

In `schema/README.md`, add `release_personnel.csv` to the numbered import order after `official_release_tracks.csv` (it becomes step 17; renumber the rest), and add a paragraph describing schema version 5:

```markdown
Schema version 5 adds studio albums to the release catalog. `official_releases`
now constrains `release_type` to `studio`, `live`, `compilation` or `single`,
and `official_release_tracks` carries a nullable `song_id` so a track can name
its composition. A live track identifies a performance; a studio track has no
performance, because a performance is a song played at a show. A track may
carry both, one, or neither — an intro, tuning or banter segment carries
neither. `release_personnel` records one row per person's role-and-instrument
credit on a release, shaped like `show_performers`.
```

In `schema/domain-model.md`, add to the entity table:

```markdown
| `release_personnel` | People credited on a release, one row per role-and-instrument assignment. |
```

Change the `official_release_tracks` row to read:

```markdown
| `official_release_tracks` | Release tracks, mapped to a canonical performance for live releases and to a canonical song for studio releases. |
```

Add to the mermaid diagram after the existing `OFFICIAL_RELEASE_TRACK` lines:

```
    SONG ||--o{ OFFICIAL_RELEASE_TRACK : recorded_as
    OFFICIAL_RELEASE ||--o{ RELEASE_PERSONNEL : credits
    PERSON ||--o{ RELEASE_PERSONNEL : credited_on
```

In the "External links and official releases" section, replace the sentence beginning "An official release is more than a link" with:

```markdown
An official release is more than a link. The catalog holds both live releases
and studio albums, distinguished by `release_type`.
`official_release_tracks` makes a release's contents queryable: a live track
identifies the canonical performance it captures, and a studio track
identifies the composition it records. A track can remain unmapped when it is
an introduction, tuning, banter, or another non-song segment.
```

In `data/canonical/README.md`, add after the `show_performers.csv` paragraph:

```markdown
`release_personnel.csv` follows the same one-row-per-assignment convention as
`show_performers.csv`. `instrument` is part of the primary key and cannot be
empty; a credit that names a person and a role but no instrument is held in
the normalizer's review log rather than entered with a placeholder.
```

- [ ] **Step 10: Commit**

```bash
git add schema/ data/canonical/official_release_tracks.csv data/canonical/release_personnel.csv deadbot/postgres_import.py tests/test_postgres_import.py
git commit -m "Add studio releases to the schema contract

Release tracks gain a nullable song_id so a studio track can name its
composition, release_type becomes a checked vocabulary, and release_personnel
records album credits."
```

---

### Task 2: MusicBrainz studio release collector

Fetches raw records. Writes nothing canonical.

**Files:**
- Create: `scripts/collect/fetch_musicbrainz_studio_releases.py`
- Test: `tests/test_fetch_musicbrainz_studio_releases.py`
- Reference: `scripts/collect/fetch_musicbrainz_live_releases.py` (follow its structure, request pacing, checkpointing and User-Agent handling)

**Interfaces:**
- Consumes: `SCHEMA_VERSION` unused here; independent of Task 1.
- Produces: `data/raw/releases/musicbrainz-studio-release-groups.jsonl`, `data/raw/releases/musicbrainz-studio-releases.jsonl`, `data/raw/releases/musicbrainz-studio-releases.run.json`, `data/raw/releases/musicbrainz-studio-releases.checkpoint.json`. Module-level constant `STUDIO_ARTISTS: tuple[str, ...]` and function `is_studio_release_group(group: dict) -> bool`.

- [ ] **Step 1: Read the existing collector**

Run: `sed -n '1,120p' scripts/collect/fetch_musicbrainz_live_releases.py`

Match its argument parsing, rate limiting, checkpoint format, and raw record shape. Do not invent a second convention.

- [ ] **Step 2: Write the failing test**

Create `tests/test_fetch_musicbrainz_studio_releases.py`:

```python
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "fetch_musicbrainz_studio_releases",
    ROOT / "scripts" / "collect" / "fetch_musicbrainz_studio_releases.py",
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_studio_artists_cover_the_dead_family_catalog():
    names = {name.casefold() for name in module.STUDIO_ARTISTS}
    assert "grateful dead" in names
    assert "jerry garcia" in names
    assert "bob weir" in names
    assert "new riders of the purple sage" in names
    assert "old & in the way" in names
    assert "kingfish" in names
    assert "jerry garcia band" in names


def test_a_live_secondary_type_disqualifies_a_release_group():
    live = {"primary-type": "Album", "secondary-types": ["Live"]}
    assert module.is_studio_release_group(live) is False


def test_a_plain_album_qualifies():
    album = {"primary-type": "Album", "secondary-types": []}
    assert module.is_studio_release_group(album) is True


def test_a_compilation_or_single_is_out_of_scope():
    assert module.is_studio_release_group({"primary-type": "Single", "secondary-types": []}) is False
    assert module.is_studio_release_group({"primary-type": "Album", "secondary-types": ["Compilation"]}) is False
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `python -m pytest tests/test_fetch_musicbrainz_studio_releases.py -v`
Expected: FAIL — the script does not exist.

- [ ] **Step 4: Write the collector**

Create `scripts/collect/fetch_musicbrainz_studio_releases.py` mirroring the live collector. The two pieces the test pins:

```python
STUDIO_ARTISTS: tuple[str, ...] = (
    "Grateful Dead",
    "Jerry Garcia",
    "Bob Weir",
    "New Riders of the Purple Sage",
    "Old & In the Way",
    "Kingfish",
    "Jerry Garcia Band",
)

# Catalog scope is studio albums only.  A Live secondary type belongs to the
# 2026-09-01 live pass; Compilation and Single are declared in the schema
# vocabulary but deliberately not collected.
_DISQUALIFYING_SECONDARY_TYPES = frozenset({"Live", "Compilation", "Soundtrack", "Interview", "Remix", "DJ-mix"})


def is_studio_release_group(group: dict) -> bool:
    if (group.get("primary-type") or "") != "Album":
        return False
    secondary = {str(value) for value in group.get("secondary-types") or ()}
    return not (secondary & _DISQUALIFYING_SECONDARY_TYPES)
```

Browse each artist's release groups, keep those `is_studio_release_group` accepts, then browse official releases with `inc=recordings+url-rels+release-groups+artist-credits`. Write compact raw records only — MBIDs, titles, dates, disambiguations, statuses, medium and track titles and lengths, artist credits, URL relationships. No cover art, no annotation text.

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/test_fetch_musicbrainz_studio_releases.py -v`
Expected: PASS.

- [ ] **Step 6: Verify the MusicBrainz source registry entry covers this pass**

Run: `python -m pytest tests/test_source_registry.py tests/test_source_registry_schema.py -v`

Then confirm the MusicBrainz entry in `data/source_registry.json` allows the host and operations this collector performs. If it does not, extend the entry as a reviewed change in this task — an ad-hoc call outside the registry contract is not acceptable.

- [ ] **Step 7: Run the collector against the live service**

Run: `python scripts/collect/fetch_musicbrainz_studio_releases.py`
Expected: every request HTTP 200; the run summary reports the release groups enumerated and releases fetched; raw JSONL files appear under `data/raw/releases/`.

- [ ] **Step 8: Commit**

```bash
git add scripts/collect/fetch_musicbrainz_studio_releases.py tests/test_fetch_musicbrainz_studio_releases.py data/raw/releases/ data/source_registry.json
git commit -m "Collect Grateful Dead family studio releases from MusicBrainz"
```

---

### Task 3: Normalize studio releases into canonical rows

**Files:**
- Create: `scripts/normalize_musicbrainz_studio_releases.py`
- Test: `tests/test_normalize_musicbrainz_studio_releases.py`
- Modify: `data/canonical/official_releases.csv`, `data/canonical/official_release_tracks.csv`, `data/canonical/release_personnel.csv`
- Reference: `scripts/normalize_musicbrainz_live_releases.py`

**Interfaces:**
- Consumes: the raw JSONL from Task 2; the CSV columns from Task 1.
- Produces: studio rows in `official_releases.csv` with `release_type='studio'`; track rows carrying `song_id`; personnel rows. Functions `resolve_song_id(title: str, songs: dict[str, str]) -> str | None` and `release_id_for(title: str, artist: str) -> str`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_normalize_musicbrainz_studio_releases.py`:

```python
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "normalize_musicbrainz_studio_releases",
    ROOT / "scripts" / "normalize_musicbrainz_studio_releases.py",
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

SONGS = {
    "sugaree": "song-sugaree",
    "truckin": "song-truckin",
    "china cat sunflower": "song-china-cat-sunflower",
}


def test_an_exact_title_resolves_to_its_song():
    assert module.resolve_song_id("Sugaree", SONGS) == "song-sugaree"


def test_punctuation_and_case_do_not_block_a_match():
    assert module.resolve_song_id("Truckin'", SONGS) == "song-truckin"
    assert module.resolve_song_id("CHINA CAT SUNFLOWER", SONGS) == "song-china-cat-sunflower"


def test_an_unresolved_title_is_held_rather_than_guessed():
    assert module.resolve_song_id("Untitled Studio Jam", SONGS) is None


def test_release_ids_are_stable_kebab_case():
    assert module.release_id_for("American Beauty", "Grateful Dead") == "release-american-beauty"
    assert module.release_id_for("Ace", "Bob Weir") == "release-ace"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_normalize_musicbrainz_studio_releases.py -v`
Expected: FAIL — the script does not exist.

- [ ] **Step 3: Write the normalizer**

Create `scripts/normalize_musicbrainz_studio_releases.py`. The two functions the test pins:

```python
import re

_PUNCTUATION = re.compile(r"[^a-z0-9]+")


def _fold(title: str) -> str:
    return _PUNCTUATION.sub(" ", title.casefold()).strip()


def resolve_song_id(title: str, songs: dict[str, str]) -> str | None:
    """Resolve a track title to a canonical song, or hold it.

    Fail-closed: a title that does not match a known song returns None and is
    recorded in the review log.  A guessed match would put a wrong song on a
    record permanently.
    """

    return songs.get(_fold(title))


def release_id_for(title: str, artist: str) -> str:
    return "release-" + _PUNCTUATION.sub("-", title.casefold()).strip("-")
```

Build the `songs` mapping by folding `title` and `slug` from `data/canonical/songs.csv`. Mark every managed row's `notes` with `MusicBrainz release <mbid>` so reruns replace only the normalizer's own rows and never the hand-curated Veneta rows. Reuse an existing `release_id` when the same release or release-group MBID was seen before. Log every decision — resolved, held, skipped — to `data/raw/releases/musicbrainz-studio-release-review.jsonl`.

For personnel: emit a `release_personnel` row only when the credit names a person resolvable in `data/canonical/people.csv` *and* an instrument. A credit with a role but no instrument is written to the review log with reason `no_instrument`, because `instrument` is part of the primary key.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_normalize_musicbrainz_studio_releases.py -v`
Expected: PASS.

- [ ] **Step 5: Run the normalizer and confirm reruns are byte-identical**

```bash
python scripts/normalize_musicbrainz_studio_releases.py
md5 -q data/canonical/official_releases.csv data/canonical/official_release_tracks.csv data/canonical/release_personnel.csv > /tmp/first.txt
python scripts/normalize_musicbrainz_studio_releases.py
md5 -q data/canonical/official_releases.csv data/canonical/official_release_tracks.csv data/canonical/release_personnel.csv > /tmp/second.txt
diff /tmp/first.txt /tmp/second.txt && echo "byte-identical"
```

Expected: `byte-identical`.

- [ ] **Step 6: Verify the canonical result**

```bash
python - <<'PY'
import csv
from collections import Counter

releases = list(csv.DictReader(open("data/canonical/official_releases.csv")))
tracks = list(csv.DictReader(open("data/canonical/official_release_tracks.csv")))
print("release types:", Counter(r["release_type"] for r in releases))
studio = {r["release_id"] for r in releases if r["release_type"] == "studio"}
studio_tracks = [t for t in tracks if t["release_id"] in studio]
mapped = [t for t in studio_tracks if t["song_id"].strip()]
print(f"studio albums: {len(studio)}")
print(f"studio tracks: {len(studio_tracks)}, resolved to a song: {len(mapped)}")
assert all(r["release_type"] in {"studio", "live", "compilation", "single"} for r in releases)
PY
```

Expected: roughly 30–45 studio albums; the live count stays at 294; every `release_type` is in the vocabulary.

- [ ] **Step 7: Commit**

```bash
git add scripts/normalize_musicbrainz_studio_releases.py tests/test_normalize_musicbrainz_studio_releases.py data/canonical/ data/raw/releases/
git commit -m "Normalize studio releases into the canonical release catalog"
```

---

### Task 4: Backfill song_id on unmapped live tracks

2,999 existing live tracks carry a title and no performance. Where the title resolves, the track gains a song.

**Files:**
- Create: `scripts/normalize_release_track_songs.py`
- Test: `tests/test_normalize_release_track_songs.py`
- Modify: `data/canonical/official_release_tracks.csv`

**Interfaces:**
- Consumes: `resolve_song_id` from Task 3 — import it rather than copying, so one folding rule governs both passes.
- Produces: `song_id` populated on resolvable live tracks. Function `backfill_song_ids(tracks: list[dict], songs: dict[str, str], performances: dict[str, str]) -> tuple[list[dict], list[dict]]` returning `(rows, held)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_normalize_release_track_songs.py`:

```python
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "normalize_release_track_songs",
    ROOT / "scripts" / "normalize_release_track_songs.py",
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

SONGS = {"sugaree": "song-sugaree", "deal": "song-deal"}
PERFORMANCES = {"gd-1979-11-06-deal-1-11": "song-deal"}


def test_a_mapped_performance_supplies_the_song_directly():
    rows, held = module.backfill_song_ids(
        [{"performance_id": "gd-1979-11-06-deal-1-11", "song_id": "", "track_title": "Deal"}],
        SONGS,
        PERFORMANCES,
    )
    assert rows[0]["song_id"] == "song-deal"
    assert held == []


def test_an_unmapped_track_resolves_by_title():
    rows, held = module.backfill_song_ids(
        [{"performance_id": "", "song_id": "", "track_title": "Sugaree"}], SONGS, PERFORMANCES
    )
    assert rows[0]["song_id"] == "song-sugaree"


def test_an_unresolvable_title_stays_empty_and_is_reported():
    rows, held = module.backfill_song_ids(
        [{"performance_id": "", "song_id": "", "track_title": "Tuning"}], SONGS, PERFORMANCES
    )
    assert rows[0]["song_id"] == ""
    assert held == [{"track_title": "Tuning", "reason": "unresolved_title"}]


def test_an_existing_song_id_is_recomputed_not_trusted():
    rows, _ = module.backfill_song_ids(
        [{"performance_id": "", "song_id": "song-wrong", "track_title": "Sugaree"}], SONGS, PERFORMANCES
    )
    assert rows[0]["song_id"] == "song-sugaree"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_normalize_release_track_songs.py -v`
Expected: FAIL — the script does not exist.

- [ ] **Step 3: Write the backfill**

Create `scripts/normalize_release_track_songs.py`:

```python
def backfill_song_ids(
    tracks: list[dict],
    songs: dict[str, str],
    performances: dict[str, str],
) -> tuple[list[dict], list[dict]]:
    """Give every resolvable release track its canonical song.

    A mapped performance already names the song, so it wins.  Otherwise the
    track title is folded and matched.  An unresolved title stays empty and is
    reported; this pass never guesses.  Every run recomputes the column from
    scratch rather than trusting a prior run.
    """

    rows: list[dict] = []
    held: list[dict] = []
    for track in tracks:
        row = dict(track)
        performance_id = row.get("performance_id", "").strip()
        song_id = performances.get(performance_id) if performance_id else None
        if not song_id:
            song_id = resolve_song_id(row.get("track_title", ""), songs)
        if not song_id and not performance_id:
            held.append({"track_title": row.get("track_title", ""), "reason": "unresolved_title"})
        row["song_id"] = song_id or ""
        rows.append(row)
    return rows, held
```

Import `resolve_song_id` from the Task 3 normalizer by file path, the same way the tests load these scripts. Write held rows to `data/raw/releases/release-track-song-review.jsonl`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_normalize_release_track_songs.py -v`
Expected: PASS.

- [ ] **Step 5: Run the backfill and confirm reruns are stable**

```bash
python scripts/normalize_release_track_songs.py
md5 -q data/canonical/official_release_tracks.csv > /tmp/backfill-first.txt
python scripts/normalize_release_track_songs.py
md5 -q data/canonical/official_release_tracks.csv > /tmp/backfill-second.txt
diff /tmp/backfill-first.txt /tmp/backfill-second.txt && echo "stable"

python - <<'PY'
import csv
tracks = list(csv.DictReader(open("data/canonical/official_release_tracks.csv")))
with_song = [t for t in tracks if t["song_id"].strip()]
no_performance = [t for t in tracks if not t["performance_id"].strip()]
recovered = [t for t in no_performance if t["song_id"].strip()]
print(f"tracks: {len(tracks)}, with a song: {len(with_song)}")
print(f"without a performance: {len(no_performance)}, of those recovered by title: {len(recovered)}")
PY
```

Expected: `stable`; a substantial share of the 2,999 performance-less tracks now carry a song.

- [ ] **Step 6: Commit**

```bash
git add scripts/normalize_release_track_songs.py tests/test_normalize_release_track_songs.py data/canonical/official_release_tracks.csv data/raw/releases/
git commit -m "Backfill song ids on release tracks with no mapped performance"
```

---

### Task 5: Album context in the CSV store

**Files:**
- Modify: `deadbot/data.py` (add `resolve_release`, `album_context` near `official_release_summaries` at line 191)
- Test: `tests/test_data.py`

**Interfaces:**
- Consumes: canonical rows from Tasks 3 and 4.
- Produces: `CanonicalStore.resolve_release(identifier: str) -> dict[str, str] | None` and `CanonicalStore.album_context(release: dict[str, str]) -> dict[str, Any]` returning keys `release`, `tracks`, `personnel`. Each track is `{track_number: int, title: str, song_id: str | None, song_title: str | None, performance_id: str | None, duration_seconds: int | None, spotify_track_url: str | None}`. Each personnel entry is `{person_id, name, role, instrument}`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_data.py`. Replace `American Beauty` and its track titles with a studio album that Task 3 actually produced if the title differs.

```python
def test_resolve_release_matches_on_id_and_on_title():
    store = CanonicalStore()
    by_id = store.resolve_release("release-american-beauty")
    by_title = store.resolve_release("American Beauty")
    assert by_id is not None
    assert by_id == by_title
    assert by_id["release_type"] == "studio"


def test_resolve_release_returns_none_for_an_unknown_name():
    assert CanonicalStore().resolve_release("Kind of Blue") is None


def test_album_context_returns_an_ordered_tracklist_with_resolved_songs():
    store = CanonicalStore()
    payload = store.album_context(store.resolve_release("release-american-beauty"))

    assert payload["release"]["title"] == "American Beauty"
    numbers = [track["track_number"] for track in payload["tracks"]]
    assert numbers == sorted(numbers)
    assert numbers[0] == 1

    truckin = next(track for track in payload["tracks"] if track["song_id"] == "song-truckin")
    assert truckin["song_title"] == "Truckin'"
    assert truckin["performance_id"] is None


def test_album_context_personnel_carry_resolved_names():
    store = CanonicalStore()
    payload = store.album_context(store.resolve_release("release-american-beauty"))
    for entry in payload["personnel"]:
        assert entry["name"]
        assert entry["instrument"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_data.py -k "release or album_context" -v`
Expected: FAIL with `AttributeError: 'CanonicalStore' object has no attribute 'resolve_release'`.

- [ ] **Step 3: Implement both methods**

Add to `deadbot/data.py`:

```python
    def resolve_release(self, identifier: str) -> dict[str, str] | None:
        direct = self.one("official_releases", identifier)
        if direct:
            return direct
        matches = self.matching_rows("official_releases", identifier, ("title",))
        return matches[0] if len(matches) == 1 else None

    def album_context(self, release: dict[str, str]) -> dict[str, Any]:
        """One release as a whole object: its tracklist, credits and links.

        A track names a performance for a live release and a song for a studio
        release; either may be absent for an intro, tuning or banter segment.
        """

        release_id = release["release_id"]

        def number(value: str) -> int:
            return int(value) if value.strip().isdigit() else 10**9

        tracks = []
        for row in self.rows("official_release_tracks"):
            if row["release_id"] != release_id:
                continue
            song_id = row.get("song_id", "").strip() or None
            song = self.one("songs", song_id) if song_id else None
            duration = row.get("duration_seconds", "").strip()
            tracks.append(
                {
                    "track_number": number(row.get("track_number", "")),
                    "title": row.get("track_title") or "",
                    "song_id": song_id,
                    "song_title": song.get("title") if song else None,
                    "performance_id": row.get("performance_id", "").strip() or None,
                    "duration_seconds": int(duration) if duration.isdigit() else None,
                    "spotify_track_url": row.get("spotify_track_url", "").strip() or None,
                }
            )
        tracks.sort(key=lambda track: track["track_number"])

        personnel = []
        for row in self.rows("release_personnel"):
            if row["release_id"] != release_id:
                continue
            person = self.one("people", row["person_id"])
            personnel.append(
                {
                    "person_id": row["person_id"],
                    "name": person.get("name") if person else row["person_id"],
                    "role": row.get("role") or "",
                    "instrument": row.get("instrument") or "",
                }
            )

        return {"release": release, "tracks": tracks, "personnel": personnel}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_data.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deadbot/data.py tests/test_data.py
git commit -m "Read one release as a whole object with its tracklist and credits"
```

---

### Task 6: A song knows its records

This is the change that closes the gap the owner noticed: the model has never seen album information for a song.

**Files:**
- Modify: `deadbot/data.py:204-224` (`song_context`)
- Test: `tests/test_data.py`

**Interfaces:**
- Consumes: `album_context` conventions from Task 5.
- Produces: `song_context` gains a `releases` key — a list of `{release_id, title, artist_name, release_date, release_type, track_number, spotify_album_url}` sorted by release date ascending, with studio before live when dates tie, and undated releases last.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_data.py`:

```python
def test_song_context_lists_the_records_that_carried_the_song():
    store = CanonicalStore()
    payload = store.song_context(store.resolve_song("Truckin'"))

    releases = payload["releases"]
    assert releases, "Truckin' should appear on at least one record"

    studio = next(r for r in releases if r["release_type"] == "studio")
    assert studio["title"] == "American Beauty"
    assert studio["track_number"] == 10


def test_song_releases_are_ordered_by_date_with_studio_first_on_a_tie():
    store = CanonicalStore()
    releases = store.song_context(store.resolve_song("Truckin'"))["releases"]

    dated = [r for r in releases if r["release_date"]]
    assert [r["release_date"] for r in dated] == sorted(r["release_date"] for r in dated)
    assert all(r["release_date"] for r in releases[: len(dated)])


def test_a_song_never_released_has_an_empty_release_list():
    store = CanonicalStore()
    payload = store.song_context(store.resolve_song("song-a-mind-to-give-up-livin"))
    assert payload["releases"] == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_data.py -k "releases" -v`
Expected: FAIL with `KeyError: 'releases'`.

- [ ] **Step 3: Implement**

In `deadbot/data.py`, add this method above `song_context`:

```python
    def song_releases(self, song_id: str, performance_ids: set[str]) -> list[dict[str, Any]]:
        """Every official record carrying this song, earliest first.

        A track reaches the song either by naming it directly or by naming one
        of its performances.  Studio records sort ahead of live ones on an
        equal date, and an undated record sorts last, because a missing date
        is not a claim that it came first.
        """

        by_release: dict[str, dict[str, Any]] = {}
        for row in self.rows("official_release_tracks"):
            matches_song = row.get("song_id", "").strip() == song_id
            matches_performance = row.get("performance_id", "").strip() in performance_ids
            if not (matches_song or matches_performance):
                continue
            release = self.one("official_releases", row["release_id"])
            if not release or row["release_id"] in by_release:
                continue
            track_number = row.get("track_number", "").strip()
            by_release[row["release_id"]] = {
                "release_id": release["release_id"],
                "title": release.get("title") or "",
                "artist_name": release.get("artist_name") or None,
                "release_date": release.get("release_date") or None,
                "release_type": release.get("release_type") or None,
                "track_number": int(track_number) if track_number.isdigit() else None,
                "spotify_album_url": release.get("spotify_album_url") or None,
            }

        def order(item: dict[str, Any]) -> tuple[int, str, int, str]:
            date_value = item["release_date"] or ""
            return (
                0 if date_value else 1,
                date_value,
                0 if item["release_type"] == "studio" else 1,
                item["title"],
            )

        return sorted(by_release.values(), key=order)
```

Then add `releases` to the `song_context` return value, using the `performance_ids` set already built at line 209:

```python
        return {
            "song": song,
            "writers": writers,
            "performances": performance_summaries,
            "releases": self.song_releases(song_id, performance_ids),
            "resources": self.resources_for("resource_songs", "song_id", song_id),
            "arrangements": arrangements,
        }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_data.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deadbot/data.py tests/test_data.py
git commit -m "Give a song the records that carried it

song_context has never carried album information, so the model could not say
which record a song appeared on."
```

---

### Task 7: Postgres store parity

The two stores must return equal payloads or the CSV and Postgres modes disagree silently.

**Files:**
- Modify: `deadbot/postgres.py:50` (key columns), `deadbot/postgres.py:90` (id columns), `deadbot/postgres.py:428-460` (summaries and `song_context`)
- Test: `tests/test_postgres_store.py`

**Interfaces:**
- Consumes: `CanonicalStore.song_releases`, `album_context`, `resolve_release` from Tasks 5 and 6.
- Produces: `PostgresCanonicalStore.resolve_release` and `.album_context` with identical signatures and payloads; `song_context` including `releases`.

- [ ] **Step 1: Read how the Postgres store mirrors the CSV store**

Run: `sed -n '240,260p;420,470p' deadbot/postgres.py`

It narrows rows into a `_projection` and delegates to the `CanonicalStore` method. Follow that pattern; do not reimplement the logic in SQL.

- [ ] **Step 2: Write the failing test**

Add to `tests/test_postgres_store.py`, following the fixture pattern already at line 282:

```python
def test_song_context_matches_the_csv_store(connection):
    postgres_store = PostgresCanonicalStore(connection, schema="canonical")
    csv_store = CanonicalStore()

    song = csv_store.resolve_song("Truckin'")
    assert postgres_store.song_context(song)["releases"] == csv_store.song_context(song)["releases"]


def test_album_context_matches_the_csv_store(connection):
    postgres_store = PostgresCanonicalStore(connection, schema="canonical")
    csv_store = CanonicalStore()

    release = csv_store.resolve_release("release-american-beauty")
    assert postgres_store.album_context(release) == csv_store.album_context(release)


def test_release_personnel_is_a_known_table_with_ordering(connection):
    store = PostgresCanonicalStore(connection, schema="canonical")
    rows = store.rows("release_personnel")
    assert isinstance(rows, list)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest tests/test_postgres_store.py -k "matches_the_csv_store or release_personnel" -v`
Expected: FAIL — `releases` missing from the Postgres payload; no `album_context`.

- [ ] **Step 4: Implement**

In `deadbot/postgres.py`, add `release_personnel` to the ordering map at line 50:

```python
    "release_personnel": ("release_id", "person_id", "role", "instrument"),
```

Add the two methods, narrowing rows and delegating:

```python
    def resolve_release(self, identifier: str) -> dict[str, str] | None:
        direct = self.one("official_releases", identifier)
        if direct:
            return direct
        matches = self.matching_rows("official_releases", identifier, ("title",))
        return matches[0] if len(matches) == 1 else None

    def album_context(self, release: dict[str, str]) -> dict[str, Any]:
        release_id = release["release_id"]
        tracks = self.filtered_rows("official_release_tracks", release_id=release_id)
        personnel = self.filtered_rows("release_personnel", release_id=release_id)
        song_ids = {row["song_id"] for row in tracks if row.get("song_id", "").strip()}
        person_ids = {row["person_id"] for row in personnel}
        return CanonicalStore.album_context(
            self._projection(
                {
                    "official_release_tracks": tracks,
                    "release_personnel": personnel,
                    "songs": self._rows_in("songs", "song_id", song_ids),
                    "people": self._rows_in("people", "person_id", person_ids),
                }
            ),
            release,
        )
```

In the existing `song_context` (line 434), the `official_release_tracks` rows are already narrowed for listening paths. Widen that narrowing to include tracks whose `song_id` matches the song, and add the releases those tracks name, so the delegated `CanonicalStore.song_context` can build the list.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_postgres_store.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add deadbot/postgres.py tests/test_postgres_store.py
git commit -m "Mirror release payloads in the Postgres store"
```

---

### Task 8: Tools and persona

**Files:**
- Modify: `deadbot/tools.py:307-362` (`search_entities`), `deadbot/tools.py:535-548` (`get_song`), and a new `get_album` beside it
- Modify: `deadbot/graph.py:44-53` (the "Structured library" paragraph)
- Test: `tests/test_research_tools.py`, `tests/test_graph.py`

**Interfaces:**
- Consumes: `resolve_release`, `album_context`, `song_context` from Tasks 5–7.
- Produces: a tool named `get_album` taking `release_id_or_title: str`; `search_entities` emitting entries of kind `release`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_research_tools.py`, using the `tool_by_name` helper already defined in `tests/test_data.py`:

```python
def test_search_entities_resolves_an_album_title():
    store = CanonicalStore()
    payload = json.loads(tool_by_name(store, "search_entities").invoke({"query": "American Beauty"}))
    releases = [item for item in payload["matches"] if item["type"] == "release"]
    assert any(item["id"] == "release-american-beauty" for item in releases)


def test_get_album_returns_the_tracklist():
    store = CanonicalStore()
    payload = json.loads(tool_by_name(store, "get_album").invoke({"release_id_or_title": "American Beauty"}))
    assert payload["release"]["release_type"] == "studio"
    assert any(track["song_id"] == "song-truckin" for track in payload["tracks"])


def test_get_album_reports_an_unknown_release_rather_than_guessing():
    store = CanonicalStore()
    payload = json.loads(tool_by_name(store, "get_album").invoke({"release_id_or_title": "Kind of Blue"}))
    assert payload["error"] == "Release not found or ambiguous"


def test_get_song_carries_the_records_that_hold_it():
    store = CanonicalStore()
    payload = json.loads(tool_by_name(store, "get_song").invoke({"song_id_or_title": "Truckin'"}))
    assert any(release["release_type"] == "studio" for release in payload["releases"])
```

Add to `tests/test_graph.py`:

```python
def test_persona_tells_the_model_that_albums_are_held():
    from deadbot.graph import SYSTEM_PROMPT  # use the module's actual prompt constant

    assert "album" in SYSTEM_PROMPT.casefold()
    assert "get_album" in SYSTEM_PROMPT
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_research_tools.py tests/test_graph.py -k "album or release" -v`
Expected: FAIL — `StopIteration` from `tool_by_name` (no `get_album`), and the persona assertion fails.

- [ ] **Step 3: Add the album tool**

In `deadbot/tools.py`, after `get_song`:

```python
    @tool
    def get_album(release_id_or_title: str) -> str:
        """Get one official release: its tracklist, credited personnel, and links.

        Covers studio albums and official live releases alike. A track names a
        canonical song for a studio release and a canonical performance for a
        live one; an intro, tuning or banter segment names neither. Use the
        release date against a song's performance history when the question is
        about how a song lived on stage before or after the record.
        """
        release = store.resolve_release(release_id_or_title)
        if not release:
            return _json({"error": "Release not found or ambiguous", "query": release_id_or_title})
        return _json(store.album_context(release))
```

- [ ] **Step 4: Add releases to entity search**

In `search_entities`, add to the table loop at line 341:

```python
            ("official_releases", ("title",), "release_id", "title"),
```

The loop calls `add(table[:-1], ...)`, which would yield `official_release`. Emit `release` instead by handling this table explicitly after the loop:

```python
        for phrase in phrases:
            for row in store.matching_rows("official_releases", phrase, ("title",))[:10]:
                add("release", row["release_id"], row["title"])
```

Update the docstring's first line to `"""Find canonical songs, shows, people, equipment, venues, and official releases matching a user phrase.`

- [ ] **Step 5: Update `get_song`'s docstring**

Append to the existing docstring, before the closing quotes:

```
        The `releases` list names every official record carrying this song,
        earliest first, with its date and track number.
```

- [ ] **Step 6: Update the persona**

In `deadbot/graph.py`, in the "Structured library" paragraph, change `recordings and official releases, listening links` to:

```
recordings and official releases including studio and solo albums with their
tracklists and credited personnel, listening links
```

and add `get_album` to the tool list in the following sentence. Add one sentence after it:

```
A song carries the records that held it, so you can set a record's release
date against the band's live history when that is what makes the answer.
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest tests/test_research_tools.py tests/test_graph.py tests/test_data.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add deadbot/tools.py deadbot/graph.py tests/test_research_tools.py tests/test_graph.py
git commit -m "Let the model retrieve albums and see a song's records"
```

---

### Task 9: Browser schema for albums

**Files:**
- Modify: `deadbot/experience.py:318-326` (`SongOverviewBlock`), and add new models before the `ExperienceBlock` union at line 491
- Test: `tests/test_experience.py`

**Interfaces:**
- Consumes: nothing from earlier tasks at runtime.
- Produces: `AlbumTrackItem`, `AlbumCreditItem`, `SongReleaseItem`, `AlbumUnitBlock` (`type="album_unit"`), and `SongOverviewBlock.albums: list[SongReleaseItem]`. `AlbumUnitBlock` joins `ExperienceBlock`.

Note: do **not** reuse the existing `PerformerItem` for album credits. It constrains `role` to `Literal["performer", "guest"]`, names the field `instruments: list[str]` with `min_length=1`, and requires a `follow_up` — none of which fits a MusicBrainz instrument credit or the `release_personnel` columns. `AlbumCreditItem` mirrors the table instead.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_experience.py`. That file imports the module as `from deadbot import experience` and refers to models as `experience.X`; follow it. It already imports `ValidationError`; add `import pytest` at the top if it is not there.

```python
def test_album_unit_block_validates_a_full_record():
    block = experience.AlbumUnitBlock(
        type="album_unit",
        release_id="release-american-beauty",
        title="American Beauty",
        artist_name="Grateful Dead",
        release_date="1970-11-01",
        release_type="studio",
        tracks=[
            experience.AlbumTrackItem(
                track_number=10,
                title="Truckin'",
                song_id="song-truckin",
                performance_id=None,
                duration_seconds=311,
                highlighted=True,
                listen_url=None,
            )
        ],
    )
    assert block.tracks[0].highlighted is True
    assert block.personnel == []


def test_album_credits_take_a_free_text_role_and_one_instrument():
    credit = experience.AlbumCreditItem(
        person_id="person-jerry-garcia", name="Jerry Garcia", role="performer", instrument="lead guitar"
    )
    assert credit.instrument == "lead guitar"


def test_album_unit_caps_its_tracklist():
    with pytest.raises(ValidationError):
        experience.AlbumUnitBlock(
            type="album_unit",
            release_id="release-x",
            title="X",
            release_type="studio",
            tracks=[
                experience.AlbumTrackItem(track_number=n, title=f"t{n}", highlighted=False)
                for n in range(1, 32)
            ],
        )


def test_song_overview_carries_the_records_that_held_the_song():
    block = experience.SongOverviewBlock(
        type="song_overview",
        song_id="song-truckin",
        title="Truckin'",
        known_performance_count=520,
        albums=[
            experience.SongReleaseItem(
                release_id="release-american-beauty",
                title="American Beauty",
                release_date="1970-11-01",
                release_type="studio",
            )
        ],
    )
    assert block.albums[0].release_type == "studio"


def test_song_overview_albums_default_to_empty():
    block = experience.SongOverviewBlock(
        type="song_overview", song_id="s", title="S", known_performance_count=0
    )
    assert block.albums == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_experience.py -k "album" -v`
Expected: FAIL with `NameError: name 'AlbumUnitBlock' is not defined`.

- [ ] **Step 3: Add the models**

In `deadbot/experience.py`, add before the union:

```python
class AlbumTrackItem(ExperienceModel):
    track_number: int = Field(ge=1)
    title: str
    song_id: str | None = None
    performance_id: str | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    highlighted: bool = False
    listen_url: str | None = None


class AlbumCreditItem(ExperienceModel):
    """One person's credit on a record, mirroring `release_personnel`."""

    person_id: str
    name: str
    role: str
    instrument: str


class AlbumUnitBlock(ExperienceModel):
    """One official record as a whole object: what is on it and who made it."""

    type: Literal["album_unit"]
    release_id: str
    title: str
    artist_name: str | None = None
    release_date: str | None = None
    release_type: str
    role: UnitRole | None = None
    note: str | None = None
    tracks: list[AlbumTrackItem] = Field(default_factory=list, max_length=30)
    personnel: list[AlbumCreditItem] = Field(default_factory=list, max_length=20)
    listen: list[ListenAction] = Field(default_factory=list, max_length=3)
    sources: list[UnitSource] = Field(default_factory=list, max_length=4)
    follow_up: str | None = None


class SongReleaseItem(ExperienceModel):
    release_id: str
    title: str
    release_date: str | None = None
    release_type: str
```

Add `albums` to `SongOverviewBlock`:

```python
    albums: list[SongReleaseItem] = Field(default_factory=list, max_length=6)
```

Add `AlbumUnitBlock` to the `ExperienceBlock` union, after `EraUnitBlock`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_experience.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deadbot/experience.py tests/test_experience.py
git commit -m "Add the album unit to the browser schema"
```

---

### Task 10: Compose the album unit

**Files:**
- Modify: `deadbot/composition.py:994-1014` (`_song_overview`), and add `_album_unit` after `_era_unit` at line 725
- Test: `tests/test_finish.py`

**Interfaces:**
- Consumes: `album_context` (Task 5), `song_context.releases` (Task 6), the blocks from Task 9.
- Produces: `composition._album_unit(payload, store, *, role=None, note=None, title=None, highlighted_song_ids=None, sources=None, follow_up=None) -> tuple[AlbumUnitBlock | None, list[SourceReference]]`, matching `_show_unit`'s shape.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_finish.py`. That file imports `from deadbot import finish` and `from deadbot.data import CanonicalStore`; add `from deadbot import composition` at the top.

```python
def test_album_unit_hydrates_from_the_release_payload():
    store = CanonicalStore()
    payload = store.album_context(store.resolve_release("release-american-beauty"))
    block, sources = composition._album_unit(payload, store, note="The record that made them a band people bought.")

    assert block.type == "album_unit"
    assert block.title == "American Beauty"
    assert block.release_type == "studio"
    assert [track.track_number for track in block.tracks] == sorted(t.track_number for t in block.tracks)


def test_album_unit_keeps_only_highlights_that_are_on_the_record():
    store = CanonicalStore()
    payload = store.album_context(store.resolve_release("release-american-beauty"))
    block, _ = composition._album_unit(payload, store, highlighted_song_ids=["song-truckin", "song-dark-star"])

    highlighted = {track.song_id for track in block.tracks if track.highlighted}
    assert highlighted == {"song-truckin"}


def test_album_unit_offers_the_record_as_a_listening_action():
    store = CanonicalStore()
    payload = store.album_context(store.resolve_release("release-american-beauty"))
    block, _ = composition._album_unit(payload, store)
    assert all(action.is_official for action in block.listen)


def test_song_overview_shows_the_records_that_held_the_song():
    store = CanonicalStore()
    context = store.song_context(store.resolve_song("Truckin'"))
    block = composition._song_overview(context, store)
    assert any(album.release_type == "studio" for album in block.albums)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_finish.py -k "album" -v`
Expected: FAIL with `AttributeError: module 'deadbot.composition' has no attribute '_album_unit'`.

- [ ] **Step 3: Implement the builder**

Add to `deadbot/composition.py`:

```python
def _album_unit(
    payload: dict[str, Any],
    store: CanonicalStore,
    *,
    role: UnitRole | None = None,
    note: str | None = None,
    title: str | None = None,
    highlighted_song_ids: list[str] | None = None,
    sources: list[UnitSource] | None = None,
    follow_up: str | None = None,
) -> tuple[AlbumUnitBlock | None, list[SourceReference]]:
    """Hydrate one album unit from its release payload.

    Highlights are kept only for songs actually on this record, so a slip in
    the plan cannot mark a song that is not there.
    """

    release = payload.get("release")
    if not isinstance(release, dict) or not release.get("release_id"):
        return None, []

    payload_tracks = payload.get("tracks") if isinstance(payload.get("tracks"), list) else []
    own_song_ids = {track.get("song_id") for track in payload_tracks if isinstance(track, dict) and track.get("song_id")}
    highlighted = frozenset(sid for sid in (highlighted_song_ids or []) if sid in own_song_ids)

    tracks = [
        AlbumTrackItem(
            track_number=track["track_number"],
            title=track.get("song_title") or track.get("title") or "",
            song_id=track.get("song_id"),
            performance_id=track.get("performance_id"),
            duration_seconds=track.get("duration_seconds"),
            highlighted=track.get("song_id") in highlighted,
            listen_url=track.get("spotify_track_url"),
        )
        for track in payload_tracks
        if isinstance(track, dict) and isinstance(track.get("track_number"), int)
    ][:30]

    personnel = [
        AlbumCreditItem(
            person_id=entry["person_id"],
            name=entry.get("name") or entry["person_id"],
            role=entry.get("role") or "performer",
            instrument=entry.get("instrument") or "",
        )
        for entry in (payload.get("personnel") or [])
        if isinstance(entry, dict) and entry.get("person_id")
    ][:20]

    listen: list[ListenAction] = []
    album_url = release.get("spotify_album_url") or release.get("source_url")
    if isinstance(album_url, str) and album_url:
        listen.append(
            ListenAction(
                label=f"Hear {release.get('title') or 'the record'}",
                url=album_url,
                provider=_provider_for(album_url),
                is_official=True,
            )
        )

    block = AlbumUnitBlock(
        type="album_unit",
        release_id=release["release_id"],
        title=(title or "").strip() or release.get("title") or "Untitled release",
        artist_name=release.get("artist_name") or None,
        release_date=release.get("release_date") or None,
        release_type=release.get("release_type") or "studio",
        role=role,
        note=(note or "").strip() or None,
        tracks=tracks,
        personnel=personnel,
        listen=listen,
        sources=(sources or [])[:4],
        follow_up=(follow_up or "").strip() or None,
    )
    return block, []
```

Import `AlbumCreditItem`, `AlbumTrackItem`, `AlbumUnitBlock` and `SongReleaseItem` from `deadbot.experience` at the top of the module, in the existing `from deadbot.experience import (...)` block at line 20.

- [ ] **Step 4: Populate the song overview's albums**

In `_song_overview`, before the `return`:

```python
    albums = [
        SongReleaseItem(
            release_id=release["release_id"],
            title=release.get("title") or release["release_id"],
            release_date=release.get("release_date"),
            release_type=release.get("release_type") or "live",
        )
        for release in (context.get("releases") or [])
        if isinstance(release, dict) and release.get("release_id")
    ][:6]
```

and add `albums=albums,` to the `SongOverviewBlock(...)` call.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_finish.py tests/test_experience.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add deadbot/composition.py tests/test_finish.py
git commit -m "Compose an album as one semantic unit"
```

---

### Task 11: The model can plan an album unit

**Files:**
- Modify: `deadbot/finish.py` — add `AlbumUnitRef` near `EraUnitRef` (line 239), add it to `BodyItem` (line 252), add a branch in `_resolve_reference` (line 382), extend the `body` description (line 291) and the `chat_answer` description (line 597)
- Test: `tests/test_finish.py`

**Interfaces:**
- Consumes: `composition._album_unit` (Task 10), `store.resolve_release` and `store.album_context` (Task 5).
- Produces: `AlbumUnitRef` with fields `type: Literal["album_unit"]`, `release_id: str`, `role`, `note`, `highlighted_song_ids: list[str]` (max 12), `supporting_sources` (max 4), `follow_up`, `title`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_finish.py`, using the `finish.` module prefix the file already uses. Confirm `mode="listening"` is a member of `ExperienceMode`; if it is not, substitute a mode the enum actually declares.

```python
def test_a_plan_may_declare_an_album_unit():
    plan = finish.FinishPlan(
        chat_answer="Truckin' closes American Beauty.",
        title="American Beauty",
        mode="listening",
        body=[{"type": "album_unit", "release_id": "release-american-beauty", "highlighted_song_ids": ["song-truckin"]}],
    )
    assert plan.body[0].release_id == "release-american-beauty"


def test_an_ungrounded_release_id_is_dropped():
    plan = finish.FinishPlan(
        chat_answer="x",
        title="x",
        mode="listening",
        body=[{"type": "album_unit", "release_id": "release-american-beauty"}],
    )
    blocks, _ = finish.resolve_body(
        plan, finish.GroundedContext(ids=frozenset(), urls=frozenset()), [], CanonicalStore()
    )
    assert blocks == []


def test_a_grounded_release_id_hydrates_into_an_album_unit():
    store = CanonicalStore()
    plan = finish.FinishPlan(
        chat_answer="x",
        title="x",
        mode="listening",
        body=[{"type": "album_unit", "release_id": "release-american-beauty", "note": "The turn toward songs."}],
    )
    grounded = finish.GroundedContext(ids=frozenset({"release-american-beauty"}), urls=frozenset())
    blocks, _ = finish.resolve_body(plan, grounded, [], store)
    assert blocks[0].type == "album_unit"
    assert blocks[0].note == "The turn toward songs."
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_finish.py -k "album_unit" -v`
Expected: FAIL with a Pydantic discriminator error — `album_unit` is not a valid body item type.

- [ ] **Step 3: Add the reference model**

In `deadbot/finish.py`, after `EraUnitRef`:

```python
class AlbumUnitRef(_Ref):
    """One official record as a primary object of this answer."""

    type: Literal["album_unit"]
    release_id: str
    role: UnitRole | None = None
    note: str | None = Field(default=None, description="Why this record matters to the question, in your voice.")
    highlighted_song_ids: list[str] = Field(default_factory=list, max_length=12)
    supporting_sources: list[SupportingSource] = Field(default_factory=list, max_length=4)
    follow_up: str | None = None
```

Add `| AlbumUnitRef` to the `BodyItem` union after `EraUnitRef`.

- [ ] **Step 4: Resolve it**

In `_resolve_reference`, after the `era_unit` branch:

```python
    if kind == "album_unit":
        if item.release_id not in grounded.ids:
            return None, []
        release = store.resolve_release(item.release_id)
        if not release:
            return None, []
        unit_sources, sources = composition._unit_sources(item.supporting_sources, grounded.urls, payloads)
        block, listen_sources = composition._album_unit(
            store.album_context(release),
            store,
            role=item.role,
            note=item.note,
            title=item.title,
            highlighted_song_ids=item.highlighted_song_ids,
            sources=unit_sources,
            follow_up=item.follow_up,
        )
        return block, [*listen_sources, *sources]
```

- [ ] **Step 5: Tell the model the unit exists**

In the `body` field description, after the `era_unit` clause, add:

```
album_unit (one official record with its tracklist, personnel and listening),
```

In the `chat_answer` description at line 597, add `album_unit` to the parenthetical list of units.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_finish.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add deadbot/finish.py tests/test_finish.py
git commit -m "Let the model declare an album as a unit of an answer"
```

---

### Task 12: Render albums in the browser

**Files:**
- Modify: `web/openapi.json` (regenerated), `web/src/generated/api.ts` (regenerated)
- Modify: `web/src/types.ts:44-69` (union), `web/src/App.tsx` (new case, and the `song_overview` case at line 557)
- Test: `tests/test_api_import.py`

**Interfaces:**
- Consumes: the browser schema from Task 9.
- Produces: `AlbumUnitBlock` in the TypeScript `ExperienceBlock` union; an `AlbumUnit` React component.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api_import.py`:

```python
def test_openapi_publishes_the_album_unit_block():
    from deadbot.api import app

    schemas = app.openapi()["components"]["schemas"]
    assert "AlbumUnitBlock" in schemas
    assert "AlbumTrackItem" in schemas
    assert "albums" in schemas["SongOverviewBlock"]["properties"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_api_import.py -k album -v`
Expected: FAIL — the block is not reachable from the published schema until it is in the union. If Task 9 was done correctly this may already pass; confirm rather than assume.

- [ ] **Step 3: Regenerate the schema and types**

```bash
python scripts/export_openapi.py
cd web && npm run gen:types && cd ..
git diff --stat web/openapi.json web/src/generated/api.ts
```

Expected: both files show `AlbumUnitBlock`, `AlbumTrackItem`, `SongReleaseItem`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_api_import.py -v`
Expected: PASS.

- [ ] **Step 5: Add the block to the TypeScript union**

In `web/src/types.ts`, after the `FixedEraUnitBlock` entry:

```ts
type FixedAlbumUnitBlock = Require<
  components["schemas"]["AlbumUnitBlock"],
  "tracks" | "personnel" | "listen" | "sources"
>;
```

and add `| FixedAlbumUnitBlock` to the `ExperienceBlock` union. Extend `FixedSongOverviewBlock`'s `Require` list with `"albums"`.

- [ ] **Step 6: Render it**

In `web/src/App.tsx`, add a case beside the other units:

```tsx
    case "album_unit":
      return <AlbumUnit key={key} block={block} />;
```

Write the `AlbumUnit` component next to `ShowUnit`. Read `ShowUnit` first and reuse its class names and its sub-components for role chips, listen actions, sources and follow-ups rather than inventing new ones — the structure below is the content, not the styling:

```tsx
function AlbumUnit({ block }: { block: FixedAlbumUnitBlock }) {
  const year = block.release_date?.slice(0, 4);
  return (
    <section className="unit album-unit">
      <header>
        <h3>
          {block.title}
          {year ? <span className="unit-year"> ({year})</span> : null}
        </h3>
        {block.artist_name && block.artist_name !== "Grateful Dead" ? (
          <p className="unit-subtitle">{block.artist_name}</p>
        ) : null}
        {block.role ? <span className="unit-role">{block.role}</span> : null}
      </header>
      {block.note ? <p className="unit-note">{block.note}</p> : null}
      <ol className="album-tracks">
        {block.tracks.map((track) => (
          <li
            key={track.track_number}
            className={track.highlighted ? "album-track is-highlighted" : "album-track"}
            value={track.track_number}
          >
            {track.listen_url ? (
              <a href={track.listen_url} target="_blank" rel="noreferrer">
                {track.title}
              </a>
            ) : (
              track.title
            )}
          </li>
        ))}
      </ol>
      {block.personnel.length > 0 ? (
        <ul className="album-personnel">
          {block.personnel.map((credit) => (
            <li key={`${credit.person_id}-${credit.instrument}`}>
              {credit.name} — {credit.instrument}
            </li>
          ))}
        </ul>
      ) : null}
      <ListenActions actions={block.listen} />
      <UnitSources sources={block.sources} />
      {block.follow_up ? <p className="unit-follow-up">{block.follow_up}</p> : null}
    </section>
  );
}
```

`ListenActions` and `UnitSources` stand in for whatever `ShowUnit` already uses for those two jobs; call those, do not write new ones.

In the `song_overview` case at line 557, render the records inline after the credits:

```tsx
{block.albums.length > 0 ? (
  <ul className="song-albums">
    {block.albums.map((album) => (
      <li key={album.release_id}>
        {album.title}
        {album.release_date ? ` (${album.release_date.slice(0, 4)})` : ""}
      </li>
    ))}
  </ul>
) : null}
```

- [ ] **Step 7: Build the browser bundle**

Run: `cd web && npm run build && cd ..`
Expected: `tsc -b` reports no type errors and the Vite build succeeds.

- [ ] **Step 8: Commit**

```bash
git add web/ tests/test_api_import.py
git commit -m "Render an album unit and a song's records"
```

---

### Task 13: Cover-song origin curation

`original_artist` is empty for all 436 songs and `song_writers` covers 133. This is authoring, not gap-filling, and is deliberately sequenced last — nothing above depends on it.

**Files:**
- Create: `scripts/build_cover_origin_review.py`
- Create: `data/editorial/cover-origin-review.csv`
- Modify: `data/canonical/songs.csv` (the `original_artist` column)
- Test: `tests/test_cover_origin_review.py`

**Interfaces:**
- Consumes: `data/canonical/songs.csv`, `data/canonical/song_writers.csv`, `data/canonical/people.csv`.
- Produces: `candidate_covers(songs, writers, dead_family_person_ids) -> list[dict]`, each `{song_id, title, writers, signal}` where `signal` is `non_family_writer` or `no_writer_data`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cover_origin_review.py`:

```python
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_cover_origin_review", ROOT / "scripts" / "build_cover_origin_review.py"
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

FAMILY = {"person-jerry-garcia", "person-robert-hunter"}


def test_a_song_written_outside_the_family_is_a_cover_candidate():
    songs = [{"song_id": "song-morning-dew", "title": "Morning Dew"}]
    writers = [{"song_id": "song-morning-dew", "person_id": "person-bonnie-dobson"}]
    candidates = module.candidate_covers(songs, writers, FAMILY)
    assert candidates == [
        {
            "song_id": "song-morning-dew",
            "title": "Morning Dew",
            "writers": ["person-bonnie-dobson"],
            "signal": "non_family_writer",
        }
    ]


def test_a_family_written_song_is_not_a_candidate():
    songs = [{"song_id": "song-ripple", "title": "Ripple"}]
    writers = [
        {"song_id": "song-ripple", "person_id": "person-jerry-garcia"},
        {"song_id": "song-ripple", "person_id": "person-robert-hunter"},
    ]
    assert module.candidate_covers(songs, writers, FAMILY) == []


def test_a_song_with_no_writer_data_is_flagged_for_review_not_assumed():
    songs = [{"song_id": "song-unknown", "title": "Unknown"}]
    candidates = module.candidate_covers(songs, [], FAMILY)
    assert candidates[0]["signal"] == "no_writer_data"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_cover_origin_review.py -v`
Expected: FAIL — the script does not exist.

- [ ] **Step 3: Write the review builder**

Create `scripts/build_cover_origin_review.py`:

```python
def candidate_covers(
    songs: list[dict],
    writers: list[dict],
    dead_family_person_ids: set[str],
) -> list[dict]:
    """Sort songs into cover candidates for human review.

    A writer credit naming nobody in the Dead family is evidence a song came
    from outside, but it does not name the original artist — that stays a
    review decision.  A song with no writer data is flagged rather than
    assumed either way.
    """

    by_song: dict[str, list[str]] = {}
    for row in writers:
        by_song.setdefault(row["song_id"], []).append(row["person_id"])

    candidates = []
    for song in songs:
        credited = by_song.get(song["song_id"], [])
        if not credited:
            signal = "no_writer_data"
        elif set(credited) & dead_family_person_ids:
            continue
        else:
            signal = "non_family_writer"
        candidates.append(
            {
                "song_id": song["song_id"],
                "title": song["title"],
                "writers": sorted(credited),
                "signal": signal,
            }
        )
    return candidates
```

The script writes `data/editorial/cover-origin-review.csv` with columns `song_id,title,writers,signal,original_artist,evidence_url,decision`, leaving `original_artist`, `evidence_url` and `decision` empty for a reviewer to fill.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_cover_origin_review.py -v`
Expected: PASS.

- [ ] **Step 5: Generate the review file**

Run: `python scripts/build_cover_origin_review.py`
Expected: `data/editorial/cover-origin-review.csv` lists every candidate with its signal.

- [ ] **Step 6: Review and apply**

Fill `original_artist`, `evidence_url` and `decision` for the rows the available evidence supports. A row with no supporting evidence keeps an empty `original_artist` and a `decision` of `held` — this pass leaves what it cannot support rather than guessing. Then apply the reviewed values into `data/canonical/songs.csv`, changing only the `original_artist` column.

- [ ] **Step 7: Verify nothing else in the songs file moved**

```bash
git diff --stat data/canonical/songs.csv
python - <<'PY'
import csv
rows = list(csv.DictReader(open("data/canonical/songs.csv")))
filled = [r for r in rows if r["original_artist"].strip()]
print(f"{len(rows)} songs, {len(filled)} with an original artist")
PY
```

Expected: only `songs.csv` changed, and the count of filled rows matches the reviewed decisions.

- [ ] **Step 8: Commit**

```bash
git add scripts/build_cover_origin_review.py tests/test_cover_origin_review.py data/editorial/cover-origin-review.csv data/canonical/songs.csv
git commit -m "Record where the Dead's cover songs came from"
```

---

### Task 14: Evaluations, coverage, and collection status

**Files:**
- Modify: `evals/exploration-v1.json`
- Create: `docs/collection-status-studio-releases.md`
- Modify: `docs/data-sources.md`
- Modify: `data/coverage/canonical-spine-baseline.json` (regenerated)

**Interfaces:**
- Consumes: everything above.
- Produces: no new code interfaces.

- [ ] **Step 1: Read the existing evaluation format**

Run: `python -m json.tool evals/exploration-v1.json | head -60`

Match its case shape exactly.

- [ ] **Step 2: Add three evaluation cases**

Add to `evals/exploration-v1.json`, in the file's own case format:

- "What album is Sugaree on?" — expects the record named with its year, and the solo attribution rather than a Grateful Dead album.
- "Tell me about American Beauty" — expects an `album_unit` in the body with a tracklist, not a bare list of songs.
- "How long had they been playing Truckin' before the record came out?" — expects the release date set against the first documented performance.

- [ ] **Step 3: Run the deterministic evaluation tests**

Run: `python -m pytest tests/test_evaluations.py tests/test_exploration_evaluation.py -v`
Expected: PASS. Model-graded runs need a configured provider and are reported separately.

- [ ] **Step 4: Rebuild coverage**

```bash
python scripts/build_baseline_coverage.py
git diff --stat data/coverage/canonical-spine-baseline.json
```

Expected: the release and track counts move; nothing else changes shape.

- [ ] **Step 5: Write the collection status document**

Create `docs/collection-status-studio-releases.md` following `docs/collection-status-official-releases.md` exactly: pass date, source and User-Agent, what was done, a counts table (artists searched, release groups enumerated, releases fetched, releases promoted, track rows written, tracks resolved to a song, personnel rows written, credits held for no instrument), and a table of held items with reasons.

- [ ] **Step 6: Update the data-sources entry**

In `docs/data-sources.md`, extend the MusicBrainz access-method entry to name `scripts/collect/fetch_musicbrainz_studio_releases.py` and `scripts/normalize_musicbrainz_studio_releases.py`, and extend the coverage line to state that the studio pass added the Dead-family studio catalog with tracklists resolved to canonical songs.

- [ ] **Step 7: Run the full test suite**

Run: `python -m pytest -v`
Expected: PASS, all tests.

- [ ] **Step 8: Commit**

```bash
git add evals/ docs/ data/coverage/
git commit -m "Document and evaluate the studio release pass"
```

---

## Verification

- [ ] `python -m pytest` passes.
- [ ] `cd web && npm run build` passes.
- [ ] `python -c "from deadbot.data import CanonicalStore as S; s=S(); print(s.song_context(s.resolve_song(\"Truckin'\"))['releases'])"` names a studio album.
- [ ] Both normalizers produce byte-identical output on a rerun.
- [ ] Every `release_type` in `official_releases.csv` is one of `studio`, `live`, `compilation`, `single`.
- [ ] The 294 pre-existing live releases and the hand-curated Veneta rows are unchanged except for the added `song_id` column.

Per `AGENTS.md`, agents cannot push. When the branch is ready, the owner runs:

```bash
git push -u origin claude/album-data-type-plan-934ed4
```
