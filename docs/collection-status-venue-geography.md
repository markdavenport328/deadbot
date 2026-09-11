# Collection status: venue geography (Wikidata pass)

Pass date: 2026-09-11. Source: the public Wikidata MediaWiki action API,
collected by `scripts/collect/fetch_wikidata_venues.py` into
`data/raw/venues/wikidata-venue-search.jsonl` (search candidates per venue) and
`data/raw/venues/wikidata-entities.jsonl` (label/alias/claims per QID touched,
including the located-in chain up to a country). `scripts/normalize_wikidata_venues.py`
makes every promotion decision offline from that raw data and writes
`data/raw/venues/venue-geography-review.jsonl` (every venue NOT promoted, with
the candidates this pass actually saw) and `data/raw/venues/venue-geography-run.json`
(this document's counts).

Scope: all 595 rows in `data/canonical/venues.csv`.

## Matching rule

A Wikidata candidate is promoted only when both hold:

- **Name agreement**: the candidate's English label, or one of its English
  aliases, equals the venue's name after normalization (casefolded, diacritics
  stripped, punctuation collapsed to spaces, a leading "the " dropped) — either
  the full venue name or, for a compound name such as "Activity Center, Arizona
  State University", the text before the first comma.
- **City agreement**: walking the candidate's P131 ("located in the
  administrative territorial entity") chain up through its own parents reaches
  an entity whose normalized label equals the venue's canonical city.

Exactly one qualifying candidate is required per venue. Zero, or more than one,
is held for review — the raw candidates are preserved in
`venue-geography-review.jsonl` rather than discarded, so a reviewer does not
have to re-run the search. No venue's coordinates are backed by a city
centroid presented as the venue's own location.

For a promoted match: latitude/longitude come from P625 and the QID is
recorded in `notes`; `setting` is set only when a P31 (instance-of) label
contains one of five outdoor terms (stadium, amphitheatre/amphitheater,
fairground, park, racetrack) or five indoor terms (arena, theatre/theater,
auditorium, ballroom, club) — any other class is left blank; `capacity` is set
only when Wikidata's P1083 states one; `state_region` is filled only for a
venue that started blank, by finding the located-in chain's country node (its
own P31 includes Wikidata's "country") and taking the label of the chain
entry immediately below it, skipped when that label would just repeat the
venue's existing `country` field.

## Counts

| Item | Count |
| --- | --- |
| Venues requested | 595 |
| Confident matches (latitude/longitude filled) | 176 (29.6%) |
| Held for review (candidate(s) seen, none promoted) | 231 |
| Unmatched (no Wikidata search candidate at all) | 188 |

### Setting and capacity coverage (of the 176 confident matches)

| Value | Count |
| --- | --- |
| `setting = indoor` | 91 |
| `setting = outdoor` | 33 |
| `setting` left blank (instance-of class not on the ten-term list) | 52 |
| `capacity` filled | 107 |
| `capacity` left blank (Wikidata states none) | 69 |

### state_region

56 rows had a blank `state_region` going into this pass (all non-US venues:
Canada, England, Scotland, Germany, France, the Netherlands, Denmark, Sweden,
Spain, Luxembourg, Egypt, Jamaica). Of those:

| Item | Count |
| --- | --- |
| Blank going in | 56 |
| Filled this pass | 3 (Concertgebouw, Amsterdam -> North Holland; Copps Coliseum, Hamilton -> Ontario; Place Ville Marie, Montreal -> Quebec) |
| Still blank | 53 |

An initial version of this pass filled 15 of the 56 by taking whatever chain
node sat directly below the venue's country in Wikidata's P131 (located-in)
hierarchy. That heuristic promoted defunct polities that are *also*
instance-of "country" in Wikidata and sit between a city and its modern
country: Toronto's chain reached "Upper Canada" (dissolved 1841) before
reaching Canada, Munich's reached the "Kingdom of Bavaria" (ended 1918)
before Germany, and a Paris venue's reached "metropolitan France" (a
France-minus-overseas grouping, not a region) before France. Those are wrong
for present-day data and are worse than leaving the field blank. The pass now
only accepts a resolved node when it is on an explicit allowlist of current
provinces, territories, states and regions for Canada, the Netherlands,
Germany and France (`ALLOWED_STATE_REGIONS` in
`scripts/normalize_wikidata_venues.py`); every other resolution — including
the four `London`-only chains, where the immediately-below-country node just
repeats the venue's own `city` field with no distinct region in between — is
left blank rather than guessed.

## Held and unmatched reasons

| Reason | Count | Notes |
| --- | --- | --- |
| `no_search_candidates` | 188 | Wikidata's `wbsearchentities` returned nothing for the venue name (or its pre-comma segment). Mostly small clubs, college buildings, and one-off venues with no independent Wikidata coverage. |
| `no_qualifying_candidate`, all candidates rejected on `city_mismatch` (city disagreed; some also had a name match) | 112 | A candidate's label/alias matched the venue name, but its P131 chain never reached an entity whose label equals the canonical city — most often a same-name venue in an unrelated city, or a venue whose Wikidata item exists but is missing a `P131` statement entirely. |
| `no_qualifying_candidate`, all candidates rejected on both `city_mismatch` and `name_mismatch` | 81 | Search returned candidates (often unrelated Wikidata items: albums, films, disambiguation-adjacent topics) that matched neither the name nor the city. |
| `no_qualifying_candidate`, all candidates rejected on `name_mismatch` only | 28 | Search found a plausible venue in the right area, but its Wikidata label/aliases do not literally equal the venue name after normalization -- for example "Winterland" (`data/canonical/venues.csv`) against Wikidata's "Winterland Ballroom" (Q1423180, aliased only as "Winterland Arena", not the bare "Winterland" this catalog uses). A real match, held because Wikidata's own alias list does not cover the shorter name. |
| `multiple_qualifying_candidates` | 9 | More than one Wikidata item's label and city both agree -- expected for a generic venue name reused across a metro area or across eras (e.g. "Academy of Music, New York" has several distinct Wikidata items across different buildings and cities that all pass the automated bar). |

## What this pass did not do

- It did not fall back to a city-level centroid for a held or unmatched venue;
  `get_historical_weather` and `get_astronomy` (`deadbot/tools.py`) already
  check `venues.csv` latitude/longitude first and only geocode live when a row
  is blank, so a held venue keeps working exactly as it did before this pass —
  it geocodes on the city/state/country string, same as today.
- It did not reclassify a venue's `setting` from anything other than an
  explicit Wikidata instance-of label matching one of the ten terms in the
  brief. A university fieldhouse, a "pavilion", or a generic "hall"/"venue"
  class is left blank on purpose.
- It did not touch the 539 US-venue `state_region` values that were already
  filled; only the 56 that started blank were candidates for a fill.

## Human decisions needed

- Review `data/raw/venues/venue-geography-review.jsonl` for the 9 venues held
  with `multiple_qualifying_candidates` (for example "Academy of Music, New
  York") — a human needs to pick the right QID among the candidates already
  recorded there.
- Review the 28 `name_mismatch`-only holds for a case like Winterland: a real,
  unambiguous venue whose Wikidata item is just missing the shorter alias this
  catalog's name uses. A human could add the missing alias upstream on
  Wikidata itself, or hand-confirm a small allowlist of exceptions to promote
  in a follow-up run of `scripts/normalize_wikidata_venues.py`.
- Consider whether a second search pass (venue name + city, rather than venue
  name alone) would recover more of the 188 `no_search_candidates` venues, most
  of which are likely to be small clubs, college buildings, and one-off
  private venues with no independent Wikidata coverage at all.
- Consider extending `ALLOWED_STATE_REGIONS` (in
  `scripts/normalize_wikidata_venues.py`) to more countries or UK counties if
  state_region for the remaining 53 blank rows becomes a priority; today it
  only accepts Canadian, Dutch, German and French subdivisions, so a
  confidently-matched UK or Scandinavian venue never gets a state_region fill
  even when its P131 chain includes one, because none of the actual
  resolutions inspected during this pass were both real regions and distinct
  from the venue's own city.
