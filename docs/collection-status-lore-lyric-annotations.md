# Collection status: lyric-annotation index (2026-09-11)

Indexes lyric-annotation pages for the canonical song catalog as metadata-only
stored resources. David Dodd's *Annotated Grateful Dead Lyrics* is the
standard reference for lyric history; its original home does not respond, so
this pass indexes the reachable alternative instead.

- Source review, first: see "Source review" below and the
  `whitegum-lyric-finder` entry in `data/source_registry.json`.
- Collector: `scripts/collect/collect_whitegum_lyric_annotations.py`
- Normalizer: `scripts/normalize/normalize_whitegum_lyric_annotations.py`
- Raw: `data/raw/songs/whitegum-lyric-annotations.jsonl` (first line is the
  pass metadata, one line per confirmed page after it)
- Held queue: `data/editorial/lore-mapping-held-whitegum.jsonl`
- Canonical: appended rows in `data/canonical/resources.csv` and
  `resource_songs.csv`

This pass changes CSVs, the raw file, the registry and docs only. Production
PostgreSQL is loaded by the owner's import step
(`deadbot/postgres_import.py`); nothing here writes to a database.

## Source review

**UC Santa Cruz home (`artsites.ucsc.edu/GDead/agdl/`).** Does not respond at
all from this environment — a connection failure, not a 404 — both when
verified 2026-09-10 and reconfirmed at the start of this pass, 2026-09-11.
Recorded as unreachable, not absent: the annotations exist (they are also
published as *The Complete Annotated Grateful Dead Lyrics*, Free Press,
2005), this environment simply cannot reach the original web host.

**Alex Allan's whitegum.com.** Reachable (HTTP 200). Findings, in the order
the task asks for them:

1. **`robots.txt`.** HTTP 200, two lines: `Disallow: /contact.htm` and its
   duplicate as a full URL. Every other path, including `/longlist.htm` and
   `/songfile/`, is unrestricted, and there is no `Crawl-delay`.
2. **The site's own statement of terms or attribution.** None exists. Three
   pages were checked for one: the home page (`/`, a personal page for Alex
   Allan with unrelated personal links), `/alex.htm` (his biography — a
   career summary, no mention of the lyric site's terms), and the footer of
   a sampled `/songfile/` page (`SUGAREE.HTM`, checked in full) — a plain
   navigation bar, no copyright line, no licence, no request for attribution.
   No search of the site turned up a dedicated terms/FAQ/credits page either.
3. **What a page displays.** A `/songfile/` page shows the full lyric text
   in a blockquote, footnoted annotations (lyric variants, recording history,
   cover versions), and a "Further Information" block of outbound links —
   one of which, on every page checked, points to David Dodd's own AGDL essay
   for that song via the Wayback Machine (the original URL no longer
   resolving directly, which is the same absence noted above).
4. **Decision.** An index is permitted, on the same metadata-only terms this
   project already applies to sources with no stated reuse licence (the five
   research blogs, Deadhead High): store a page title and a URL per canonical
   song, never the lyrics or annotation prose the page displays. The full
   lyric text on each whitegum.com page is that site's own copyright
   exposure in displaying it, not something this pass touches, copies, or
   redistributes. This is a judgment call rather than a site policy stated in
   so many words, since the site states no policy at all; a human reviewer
   may want a second look before this index is relied on further, though
   nothing found during this review argues against it.

## What is stored, and what is not

A stored record keeps the page's own `<TITLE>`, its URL, and the canonical
song it was resolved for. No lyrics, footnote text, recording history, or any
other page content is read into any file — the collector reads each page only
far enough to extract the `<TITLE>` tag with a regex; the rest of the
response is discarded once read.

## Discovery: one index, then one confirming request per song

`https://www.whitegum.com/longlist.htm` is the site's own full index: every
song's title, its `/songfile/<SLUG>.HTM` (in practice `/~acsa/songfile/
<SLUG>.HTM` — Alex Allan's Apache user-directory alias; a plain `/songfile/`
path answers the same content, spot-checked, but this pass stores the exact
URL the index gave) URL and its section (Originals, Covers, Grateful Dead
Jams, Guest Singers, Pigpen Solos, Weir/Hunter/Garcia/Hart solos, Dead &
Company, NRPS, ...), including "X *see* Y" cross-reference aliases for
alternate titles. One request (3,343 entries parsed) therefore supplies every
candidate title/URL pair the pass needs; no URL was guessed.

For each of the 436 canonical songs, its title's `match_key` (shared with the
Dead.net essay normalizer — apostrophes removed, "&" read as "and",
punctuation and stopwords dropped, `-ing`/`-in'` treated alike) is looked up
against every site entry's title and alias under the same key. A song
resolving to exactly one distinct URL has that page fetched once, to confirm
it still returns 200 and to read its own `<TITLE>` rather than trust the
index's link text. A song resolving to more than one distinct URL has every
one of those pages fetched too (so each still gets a resource row) but the
relationship is held. 390 page fetches in total: 376 single matches plus 14
pages across the 7 ambiguous songs.

## What was collected and mapped

| Measure | Count |
| --- | --- |
| Canonical songs considered | 436 |
| Site index entries parsed (`/longlist.htm`) | 3,343 |
| Resolved to exactly one page | 376 |
| Held (title matches more than one distinct page) | 7 |
| Not found at source | 53 |
| Page fetches | 390 |
| New `resources.csv` rows | 390 |
| New `resource_songs.csv` rows | 376 |

`resource_type` is `lyric-annotation` for every row, `relationship_type` is
`annotates`, `creator` is `Alex Allan`, `source_name` is `Grateful Dead Lyric
and Song Finder / whitegum.com`, per the task's instruction.

## Held for review — 7 songs

Written to `data/editorial/lore-mapping-held-whitegum.jsonl`, each with both
candidate URLs (both still cataloged as resources; only the `annotates`
relationship is withheld):

| Song | Candidate pages |
| --- | --- |
| Comes A Time | `COMESTIM.HTM` (Originals) vs `COMESTI2.HTM` (Phil & Friends) |
| Down In The Bottom | `DOWNBOTT.HTM` (Covers, "Down In The Bottom") vs `DOWNONTH.HTM` (Phil & Friends, "Down On The Bottom" — a different title that happens to share a `match_key`) |
| Forever Young | `FOREVERY.HTM` (Guest Singers) vs `FOREVER2.HTM` (Phil & Friends) |
| Let The Good Times Roll | `GOODTIME.HTM` (Covers, filed as "Good Times" with a "Let The Good Times Roll *see*" alias) vs `LETTHEGO.HTM` (Phil & Friends, filed under its full name directly) |
| Rain | `RAINBEAT.HTM` (Covers) vs `RAINDONA.HTM` (Garcia Solos) |
| Walking The Dog | `WALKINTH.HTM` (Covers) vs `WALKIND2.HTM` (Pre-Dead) |
| Yellow Moon | `YELLOWMO.HTM` (Hunter Solos) vs `YELLOWM2.HTM` (Bill Kreutzmann Solos) |

Every case is the same shape: the site holds a page for the Grateful Dead's
own performance of the song and a second page for the same title as
performed by a member's other project (Phil & Friends most often), each
filed in its own section but reached by the same title's `match_key`. This
pass does not guess which page a canonical song_id — which does not itself
distinguish "as played by the Grateful Dead" from "as played by Phil &
Friends" — should prefer.

## Known limitations

- **A canonical/site title-spelling mismatch is a real gap.** 53 canonical
  songs found no matching page. Most are genuine absences (side-project
  jams, Deadbot-internal placeholder ids for unidentified performances that
  were never going to be on an external site), but a handful are spelling
  variants this pass's exact-match rule does not bridge: "Cosmic Charlie"
  (canonical) vs. the site's "Cosmic Charley"; "Turn On Your Lovelight" vs.
  "Turn On Your Love Light"; "And We Bid You Good Night" vs. "...Goodnight";
  "Minglewood Blues" (the site only has "New Minglewood Blues"); "Mississippi
  Half Step" (the site's fuller "...Uptown Toodeloo" title). Building a
  curated alias list to close these was judged not worth the risk of
  introducing a false match for a one-off pass; a future pass could add one
  deliberately, spelling variant by spelling variant.
- **The UCSC original stays the more authoritative host.** If
  `artsites.ucsc.edu/GDead/agdl/` becomes reachable again, it should be
  indexed directly — this pass's whitegum.com rows point to an independent
  fan compilation that cites Dodd's work, not to Dodd's essays themselves.
- **A resolved page is a link, not a reading.** The `annotates` relationship
  says the page is Alex Allan's lyric-and-annotation page for that song; it
  is not a claim that its lyric-variant notes are canonical fact.

## Validation

- Foreign keys: every appended `song_id` and `resource_id` resolves; no
  duplicate resource id, source URL, or `(resource_id, song_id,
  relationship_type)` triple.
- Idempotency: rerunning the normalizer over the unchanged raw file reports 0
  new resources, 0 new relationship rows, and the same 7 held entries, and a
  byte-for-byte diff of `resources.csv`, `resource_songs.csv` and the held
  queue against the prior run is empty.
- Tests: `tests/test_collect_whitegum_lyric_annotations.py` (3) and
  `tests/test_normalize_whitegum_lyric_annotations.py` (2, one a direct
  regression for the resource-id collision described above), both
  fixture-only.
- `deadbot/pathways.py`'s `_EXCLUDED_RESOURCE_TYPES` now also excludes
  `lyric-annotation`: like `lyrics-and-credits` and `catalog-song-page`, a
  whitegum.com page is a reference lookup, not discursive lore, so it should
  not by itself flip a song from "not cataloged" to "cataloged" in the
  pathways a visitor sees. `tests/test_pathways.py` already covered this
  distinction with a song (`Ballad Of Casey Jones`) that this pass happened
  to add a whitegum.com page for; that test's expectation is unchanged.
- `PYTHONPATH=. pytest -q` passes after this pass (one pre-existing,
  unrelated failure remains: `tests/test_evaluations.py::
  test_evaluate_cli_exits_non_zero_when_a_case_fails` requires
  `DEADBOT_DATABASE_URL`, which this worktree does not have configured).
