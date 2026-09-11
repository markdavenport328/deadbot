# Band membership status

Updated 2026-09-11.

Goal: a small canonical answer to "who was in the band, in what role, over
what dates" without scanning all 26,265 rows of `show_performers.csv`. Before
this pass there was no `band_memberships` table, and `birth_date`/
`death_date` were empty on every row of `people.csv`.

## What was done

1. `scripts/collect/fetch_band_membership_sources.py` made two read-only,
   unauthenticated requests, one second apart, with the descriptive
   User-Agent `Deadbot/0.1 (band membership research; contact via
   repository)`:
   - MusicBrainz `GET /ws/2/artist/6faa7ca7-0d99-4a5e-bfa6-1fd5037520c6?inc=artist-rels`,
     read for `member of band` relations (`begin`, `end`, `ended`,
     `attributes`).
   - Wikidata `wbgetclaims` for the Grateful Dead item (`Q212533`), property
     `P527` ("has part(s)"), to enumerate member QIDs and the qualifiers on
     that statement; then `wbgetentities` on those QIDs for each member's
     label, date of birth (`P569`), date of death (`P570`), and their own
     `P463` ("member of") statement for the band with its own `P580`/`P582`
     start/end qualifiers.
   Raw output: `data/raw/people/musicbrainz-grateful-dead-members.jsonl` (15
   relations) and `data/raw/people/wikidata-grateful-dead-members.jsonl` (12
   member records).
2. `scripts/normalize_band_membership.py` read those raw files plus
   `show_performers.csv`'s `role == "performer"` rows (a `guest` row is a
   sit-in, never counted as tenure) joined to `shows.csv` for each person's
   first and last documented show, and wrote
   `data/canonical/band_memberships.csv`: 13 rows for 12 people.
3. The same 12 people's `birth_date`/`death_date` (and the two JerryBase
   `(complete show)` duplicate identities, `person-bruce-hornsby-complete-show`
   and `person-tom-constanten-complete-show`) were filled in
   `data/canonical/people.csv` from the Wikidata records above. No other
   column changed and no row was added, so the file stays a clean merge
   alongside a concurrent writer-row pass.

## Scope

Only core and officially recognized members: the twelve people both
MusicBrainz and Wikidata document as Grateful Dead members. MusicBrainz's
`member of band` relation for the Grateful Dead also names Robert Hunter
(the band's primary lyricist, who never performed with the band) and Rob
Wasserman (a solo/duo collaborator, not a member); both are excluded, matching
the exclusion already applied to every guest and sit-in musician retained only
in `show_performers.csv`.

## The lineup, cross-checked

Every tenure was checked against the first and last `show_performers` row with
`role == "performer"` for that person (a `guest` row never counts). Where a
source's date and the lineup evidence differ by more than a few weeks, the
row is held with both values recorded in its `notes`, not resolved silently.

| Person | Role | Start | End | MusicBrainz | Wikidata | Agreement |
| --- | --- | --- | --- | --- | --- | --- |
| Jerry Garcia | guitar, vocals | 1965-05-05 | 1995-07-09 | 1965-1995 | 1965-1995 | Agree |
| Bob Weir | guitar, vocals | 1965-05-05 | 1995-07-09 | 1965-1995 | 1965-1995 | Agree |
| Bill Kreutzmann | drums | 1965-05-05 | 1995-07-09 | 1965-1995 | 1965-1995 | Agree |
| Phil Lesh | bass, vocals | 1965-06-18 | 1995-07-09 | 1965-1995 | 1965-1995 | Agree (sharpened; see below) |
| Ron "Pigpen" McKernan | keyboards, harmonica, vocals | 1965-05-05 | 1972-06-17 | 1965-**1973** | 1965-1972 | **Held** |
| Mickey Hart (tenure 1) | drums, percussion | 1967-09-30 | 1971-02-18 | 1967-1971 | 1967-1971 | Agree |
| Mickey Hart (tenure 2) | drums, percussion | 1975-03-23 | 1995-07-09 | 1975-1995 | **1974**-1995 | Agree (see below) |
| Tom Constanten | keyboards | 1968-11-25 | 1970-01-30 | 1968-1970-01 | 1968-1970 | Agree |
| Keith Godchaux | keyboards | 1971-10-19 | 1979-02-17 | 1971-1979 | 1971-1979 | Agree |
| Donna Jean Godchaux | vocals | 1972-03-25 | 1979-02-17 | 1972-1979 | 1971-1979 | Agree (see below) |
| Brent Mydland | keyboards, vocals | 1979-04-22 | 1990-07-23 | 1979-1990-07-26 | 1979-1990 | Agree (3-day gap; see below) |
| Vince Welnick | keyboards, vocals | 1990-09-07 | 1995-07-09 | 1990-1995 | 1990-1995 | Agree |
| Bruce Hornsby | keyboards, accordion, vocals | 1990-09-15 | 1992-03-24 | (no dates on relation) | 1990-1992 | Agree |

Every date above is day precision except the four source columns, which
carry whatever precision MusicBrainz/Wikidata record (usually year, Tom
Constanten's MusicBrainz end at month precision).

### Held disagreement: Pigpen's end date

MusicBrainz's `member of band` relation gives Ron "Pigpen" McKernan's tenure
as `1965`-`1973` -- his year of death. Wikidata's own member-of statement and
the lineup evidence both agree on `1972`: his last documented `performer`-role
show is 1972-06-17, matching well-known history that he stopped touring in
mid-1972 due to declining health and died 1973-03-08, several months later
without having performed again. `band_memberships.csv` uses the last
documented performance (1972-06-17) as `end_date` and records the MusicBrainz
alternative in `notes` rather than picking one silently.

### Sharpened, not held: Phil Lesh's start date

Wikidata and MusicBrainz both give only `1965` (the band's founding year) for
Lesh. `show_performers`' first `performer`-role row for him is 1965-06-18, a
few weeks after the band's first documented show (1965-05-05). This matches
published Grateful Dead history that original bassist Dana Morgan Jr. played
the band's first several shows before Lesh joined; it is not a disagreement,
since neither source claims a specific day.

### Sharpened, not held: Mickey Hart's second start date

Wikidata's member-of statement gives `1974`-`1995` for Hart's second tenure;
MusicBrainz gives `1975`-`1995`. The lineup evidence explains both: Hart sat
in as a **guest** (not `performer`) on 1974-10-20, during the band's final
Winterland run before its 1974-1976 touring hiatus, then returned as a full
`performer`-role member at the SNACK benefit on 1975-03-23. `band_memberships.csv`
uses 1975-03-23, matching MusicBrainz and the performer-role evidence, and
notes Wikidata's coarser 1974 alongside the specific guest appearance it
likely reflects.

### Sharpened, not held: Donna Jean Godchaux's start date

Wikidata gives `1971` (matching a single **guest**-role appearance on
1971-12-31, New Year's Eve); MusicBrainz gives `1972` and the lineup evidence's
first `performer`-role row is 1972-03-25. The guest sit-in preceded her formal
membership and is not counted as tenure start.

### Sharpened, not held: Brent Mydland's end date

MusicBrainz's relation ends `1990-07-26`, Mydland's date of death.
`show_performers`' last `performer`-role row is 1990-07-23, three days
earlier -- his last actual performance. `band_memberships.csv` uses the last
performance; the three-day gap is noted but not treated as a substantive
disagreement (unlike Pigpen's nine-month gap between last performance and
death).

## Birth and death dates

All twelve people's `birth_date` came from Wikidata's `P569`. Ten also carry
`death_date` from `P570`: Jerry Garcia (1995-08-09), Ron "Pigpen" McKernan
(1973-03-08), Keith Godchaux (1980-07-23), Brent Mydland (1990-07-26), Vince
Welnick (2006-06-02), Phil Lesh (2024-10-25), Donna Jean Godchaux
(2025-11-02), and Bob Weir (2026-01-10). Bill Kreutzmann, Mickey Hart, Tom
Constanten, and Bruce Hornsby carry no `death_date` (no Wikidata `P570`
statement as of collection). Bob Weir's and Donna Jean Godchaux's 2025-2026
death dates were cross-checked against the current English Wikipedia infobox
for each (`{{death date and age}}`) and agree with Wikidata to the day.

## Counts

- `band_memberships.csv`: 13 rows, 12 people, one act (`grateful-dead`).
- `people.csv`: 14 rows touched (12 people plus their 2 `(complete show)`
  duplicate identities) -- `birth_date` filled for all 14, `death_date` filled
  for 10.
- Raw records: 15 MusicBrainz relations (13 promoted, 2 excluded as
  non-members), 12 Wikidata member records (all 12 promoted).
- 1 row held with a documented source disagreement (Pigpen's end date); no
  row was dropped for missing data.

## Known limitations

This is a bounded, reviewed pass over the twelve people both sources agree
were Grateful Dead members. It does not attempt other acts (`act` is always
`grateful-dead`), does not model bands as their own entities, and does not
promote a guest or sit-in appearance to membership regardless of how many
shows that guest played. A future pass adding another act should follow the
same lineup cross-check discipline documented here rather than trusting a
single source's date.
