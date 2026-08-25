# Normalization record: 1972-08-27

## Scope and evidence

This is the first end-to-end normalization pilot: the Grateful Dead event at the Old Renaissance Faire Grounds in Veneta, Oregon, on 27 August 1972.

- Primary show, setlist, and performer source: `data/raw/shows/jerrybase-1972-08-27.jsonl`.
- Primary recording source: `data/raw/recordings/internet-archive-gd1972-08-27-4682.jsonl`.
- Recording-discovery context: `data/raw/recordings/internet-archive-1972-search.jsonl`.

## Canonical output

The pass creates one venue, one show, six people, 20 songs, 20 ordered performances, ten show-performer assignments, one recording, and 20 performance-recording mappings. It does not infer songwriters, birth/death dates, venue coordinates, song first/last performances, or track timestamps.

## Normalization decisions

- **Stable IDs:** IDs are lowercase kebab-case. The recording ID incorporates the show date, source type, and SHNID `4682`; the Archive identifier remains a separate source identifier.
- **Song titles:** JerryBase's show-page titles supply the canonical song titles. Internet Archive's source-specific track titles are retained unchanged in `performance_recordings.track_title` (for example, `Me & My Uncle`, `Playin`, and `E1: Casey Jones`).
- **Performer assignments:** The raw JerryBase instrument labels are normalized into separate canonical instrument rows: `electric guitar (lead)` becomes `lead guitar`, `electric guitar (rhythm)` becomes `rhythm guitar`, `perc` becomes `percussion`, and `electric bass` becomes `bass`. The relationship role is `performer`; no claim about a standing band role is inferred from this single show record.
- **Set and encore treatment:** JerryBase defines three sets. The Archive source calls Casey Jones and Saturday Night `E1` and `E2`; they remain positioned in Set 3 and are marked `encore=true` to retain both source signals.
- **Segues:** `segue_into_next=true` is set only for China Cat Sunflower and Dark Star because both sources explicitly mark their following transition with `>`.
- **Track timing:** Track order is known, but start and duration seconds are left blank. The raw source uses display durations and no normalized timing extraction has been approved.

## Known follow-up questions

- Decide whether a source-specific multi-song or abbreviated track title needs a separate track-segment model later.
- Decide whether the canonical instrument vocabulary should become controlled before wider performer ingestion.
- Confirm whether the Encore Boolean should stay independent of set labels when sources disagree about presentation.
