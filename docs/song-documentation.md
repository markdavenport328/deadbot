# Song documentation

## Scope

The song layer begins with canonical composition identity and then attaches attributable resources and arrangements. This supports chords now and leaves room for videos, lessons, transcription pointers, performance-specific analysis, and other musician knowledge later.

```text
Song
  └── Resource relationship (tab, lesson, video, transcription pointer)
        └── Song arrangement (source-specific key and scope)
              └── Ordered chord sections
```

## Chord conventions

- A chord progression belongs to an **arrangement**, not directly to a song.
- `progression` uses plain chord symbols separated by `|`; it is intentionally displayable and not yet machine-parsed harmonic analysis.
- A resource can document an original-recording interpretation, a general teaching version, or a specific live performance.
- Key, capo, and tuning are recorded only when the source establishes them.
- Preserve source-specific track or arrangement terminology in notes; do not silently treat a transposed lesson as a universal key.
- Store links and concise structured chord symbols, not complete tablature, lyrics, staff notation, or audio.

## First example

The first documented arrangement is RUKIND / GDPedia's Sugaree tab. Its source statement describes an original-recording interpretation transposed from C to B. The canonical data therefore records it specifically as a B-key `recorded-song-interpretation`, with its section-level chord changes and a link to the source.
