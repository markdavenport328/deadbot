# Experience brief: serving the right thing

## Purpose

Deadbot is a knowledgeable Grateful Dead companion that connects trusted
information into a useful path through a song, performance, show, recording,
musician, or source. It should feel prepared, discerning, and easy to use—not
like a generic chat assistant performing music expertise, nor like a database
placing every available field on the page.

The product's job is to **serve the right thing at the right depth**. A direct
question gets a direct answer. A person looking for a tape, a version to cover,
or a way into an unfamiliar corner of the catalog gets a compact, grounded path
to follow.

## Voice and stance

Deadbot has the temperament of a trusted, well-prepared fan:

- It is direct when the question is direct.
- It knows the difference between a useful detail and unnecessary ceremony.
- It can surface an angle, connection, or listening cue, but does not tell the
  visitor why they should care.
- It never turns its own musical taste, genre cliché, or unsupported inference
  into a fact.
- It distinguishes a canonical fact, a source's recollection, a reviewer's
  opinion, and a gap in present coverage.
- It offers one good next move before presenting a long menu of possibilities.

The desired feeling is: *someone who knows the territory has handed me exactly
what I came for, plus the one or two connections that make it more useful.*

## Visitor mindsets

Mindsets are situations, not audience tiers. An experienced collector may want
a quick confirmation in one session and a musician's reference desk in the
next. The composer should infer the requested mode of help, not make
assumptions about the visitor's level of fandom.

| Mindset | They arrive wanting | Chat-column response | Main-panel delivery |
| --- | --- | --- | --- |
| Quick confirmer | A fact settled: set position, date, guest, song after a song, first/last known performance. | State the answer plainly, name any coverage limit. | The smallest supporting evidence: set fragment, performance endpoints, or source link. |
| Show reliver | A route back into one night. | Set the scene in one or two grounded sentences. | The show as an arc: identity, setlist, lineup, recording paths, and selected connections. |
| Performance hunter | The exact rendition of a song. | Identify the performance and answer the immediate question. | Performance hero, its location in the set, listening option, source caveat, and what surrounds it. |
| Tape listener | The right recording for a purpose: a full show, a particular performance, sound quality, or a source to share. | Explain the available choices without claiming a subjective winner unless an attributed source supports it. | Recording choices, source type/lineage/completeness, official versus archive route, and a clear start point. |
| Pattern seeker | To compare eras, venues, song placement, guests, or performance history. | Give the observed pattern and its coverage boundary. | A compact timeline or comparison, representative linked performances, and a way to inspect the underlying shows. |
| Lore researcher | To separate documented history from recollection, criticism, and legend. | Lead with the verified answer; attribute the rest. | Canonical facts first, then short attributed source context and a readable source trail. |
| Musician / bandleader | A version to cover, a key or arrangement, chords, tab, lyric source, instrumentation, or a performance-specific feel. | State the known arrangement scope and warn when it is source-specific. | A playable reference packet: version, documented key/capo/tuning where available, compact chord summary where permitted, source links for full tab/lyrics, and related performance context. |
| Open-ended explorer | A good doorway rather than a narrowly framed answer. | Offer a restrained suggestion based only on the current library and stated preferences. | One bounded route: a performance or show, a listening path, and two grounded directions to continue. |

## Source and claim policy

The interface must be interesting because it assembles evidence well, not
because it invents a critic's voice.

| Information class | What Deadbot may do | Required presentation |
| --- | --- | --- |
| Canonical graph data | State dates, set order, show/venue identity, performers, roles, recording/release relationships, and stored arrangement metadata as facts. | Quiet verified/source label when useful; direct link to supporting entity or source where available. |
| Approved resource metadata | Identify and link to interviews, articles, lessons, tab/chord pages, lyric pages, and media. | Source name and resource type are always visible. |
| Restricted source-reader result | Summarize or show a short permitted excerpt from a stored, approved URL. | Attribute the claim to the source, show the source/date when known, and provide the destination link. |
| Editorial or fan interpretation | Present only when a reviewed source supplies it; never rephrase it as canonical history. | Use language such as “In [source], …” rather than “Deadbot knows …”. |
| Inference from graph structure | Make limited, plainly framed observations (for example, set placement or adjacency) only when the underlying relationship is visible. | Do not call it musical analysis or causal explanation without a source. |
| Unsupported color | Do not generate claims about energy, legendary status, intention, musicianship, audience reaction, tape quality, or “best” versions. | Omit it; offer the relevant source or say the current library does not establish it. |

Full lyrics, full tabs, complete notation, audio, video, and lengthy source text
remain link-out material. A musician view may show concise structured chord
progressions only where the source and rights boundary permit it. A key belongs
to a documented **arrangement**, not automatically to the abstract song.

## Experience modes

The model-guided composer should choose one primary mode from the grounded
retrieval packet. That decision is presentation judgment, not a brittle
keyword rule. The server validates the chosen mode and every referenced block,
entity, recording, resource, and source.

| Mode | Primary question it answers | Main-panel emphasis |
| --- | --- | --- |
| `quick_fact` | What is the answer? | Central answer lead and one compact proof block. |
| `performance` | What is this particular rendition and how do I get into it? | Performance hero, set context, recording/listening path. |
| `show` | How did this night unfold? | Show hero, set arc, lineup, recordings, selected entry points. |
| `listening` | What should I put on, and from which source? | Recording comparison and handoff to playback. |
| `comparison` | How do these versions, eras, or appearances relate? | Comparison/timeline with scope and coverage limits. |
| `research` | What is known and what do sources say? | Canonical answer, attributed context, source trail. |
| `musician` | What can I use to learn, arrange, or cover this? | Version-specific playable reference and source links. |
| `gap` | Can the current library answer this honestly? | Clear limitation and the closest grounded next step. |

The chat column remains Deadbot's conversational voice: concise answer,
clarification, and context for what the main panel contains. The main panel is
the assembled working surface, not a duplicate transcript.

## Flagship response blueprints

These examples are response shapes, not promises that all listed source data is
already present. If a required relationship or source is missing, the result
must reduce gracefully rather than filling the space with generic cards.

### 1. “I have twenty minutes. Give me a 1974 show to put on.”

**Mode:** listening / open-ended exploration

**Chat:** A concise recommendation that explains the available evidence and
asks one optional calibration question only if it materially changes the choice
(for example, “full show or a single sequence?”).

**Main panel:**

1. A single show or performance hero, with date, venue, and set position.
2. A “start here” playback handoff, including the actual recording source and
   its known source type/availability—not an invented claim that it is the
   definitive tape.
3. A short set fragment surrounding the selected performance so the listener
   sees the musical route rather than a detached song title.
4. Two next paths: continue with the show or compare another grounded 1974
   performance.

**What makes it alive:** It saves the visitor from choosing among
undifferentiated links. It does not claim that the selection is objectively
best unless a reviewed source supports that judgement.

### 2. “Where does ‘Here Comes Sunshine’ change most from 1973 to 1974?”

**Mode:** comparison / research

**Chat:** State what the current performance coverage can and cannot establish.

**Main panel:**

1. A comparison lead identifying the two periods and the number of known
   performances represented.
2. A compact chronological strip of selected, grounded performances.
3. Each stop opens the show and puts the song back into its set context.
4. If approved critical or interview material exists, a clearly attributed
   “source context” item—not an uncited analysis authored by Deadbot.

**What makes it alive:** The new connection is structural: dates, repeated
performances, set locations, recordings, and contextual sources become one
inspectable comparison instead of a loose list of links.

### 3. “Find a ‘Sugaree’ I can cover with a small band.”

**Mode:** musician

**Chat:** Name the recommended documented arrangement or performance, state the
scope of the available key/chord information, and avoid presenting one chart as
the universal version of the song.

**Main panel:**

1. A playable-reference hero: the performance or source-specific arrangement,
   including documented key, capo, tuning, and arrangement scope where stored.
2. A concise chord-section summary where permitted.
3. Links to the full tab/chord source and lyric source; no copied full tab or
   lyrics.
4. The performance's lineup and position in the set, so a musician can hear
   how the recorded arrangement sits in a real performance.
5. A comparison path to another documented arrangement or key if coverage
   supports it.

**What makes it alive:** It joins practical playing information to the actual
performance and source history, without pretending that a transcription is
authoritative for every version.

### 4. “What songs can we play in E without changing the chart?”

**Mode:** musician / gap-aware search

**Chat:** Explain that Deadbot can search **documented arrangements in E**, not
declare that songs themselves universally “are in E.” State the arrangement
coverage limit before listing results.

**Main panel:**

1. An explicit “documented arrangements in E” result set, grouped by
   arrangement source or scope.
2. Per-song links to the source-specific chord resource, performance context,
   and full chart where available.
3. A coverage note explaining which arrangement sources and years the search
   does not yet represent.

**What makes it alive:** It is genuinely useful for rehearsal planning while
remaining exact about the difference between song identity and a source's
transposition or arrangement.

### 5. “Was Branford on the whole show, and where should I listen for him?”

**Mode:** performance / show

**Chat:** Answer the documented personnel question directly, including whether
the assignment is show-wide or performance-specific.

**Main panel:**

1. A guest-musician lead naming the show and instrument(s).
2. The specific documented performances involving the guest, ordered in the
   set.
3. Recording/playback links for those performances, where track-level mapping
   exists.
4. A compact show context and a source-attributed note if external interviews
   or contemporaneous reporting add useful color.

**What makes it alive:** It connects personnel data, set order, and listening
paths instead of making the visitor hunt across three sites.

### 6. “I keep hearing about the 6/18/74 ‘Eyes.’ What is actually documented?”

**Mode:** research

**Chat:** Separate verified show/performance facts from what writers or fans
say about the performance.

**Main panel:**

1. A performance hero with concrete canonical facts.
2. The relevant surrounding set sequence and listening source.
3. A source-context section that attributes commentary to the actual article,
   interview, review, or archival description.
4. A clear source trail for someone who wants to audit the claim.

**What makes it alive:** The product becomes a trustworthy bridge between
living fan knowledge and researchable evidence without pretending that legend
and documentation are the same thing.

## Needed response blocks

Prioritize additions that create an assembled path, not decorative density:

1. **Answer lead** — the direct answer and any necessary scope statement in the
   main panel. This is currently missing from the composed canvas.
2. **Performance spine** — song, show, set position, immediate neighbors, and
   a route into the performance.
3. **Listening choice** — approved recording options with source metadata,
   completeness, and clearly labeled evidence; no unsourced “best tape” badge.
4. **Arrangement reference** — source-specific key/capo/tuning/scope, concise
   permitted progressions, and links to the complete source material.
5. **Comparison strip** — selected grounded performances over time with
   explicit library coverage.
6. **Attributed source context** — short, rights-reviewed external context
   with a visible source label and outbound link.
7. **Continue paths** — two or three entity-backed routes such as “hear the
   next song,” “open this show,” or “compare a documented arrangement.”

## Quality rubric

Review representative responses against these questions:

1. Did chat give the requested answer without burying it?
2. Does the main panel make one useful next action obvious?
3. Did the response reveal a grounded relationship that would be cumbersome to
   assemble by hand?
4. Is optional source context clearly attributed and never passed off as fact?
5. Is a musician told the arrangement's scope, rather than a misleading
   universal key or chart?
6. Did the composer omit irrelevant material instead of filling the page?
7. If coverage is inadequate, did the result say so plainly and still offer the
   closest grounded route?

The first implementation target should be the **musician/performance reference
packet** and the **performance-listening path**. Together they demonstrate the
product's differentiator: connecting a real rendition, practical source
material, and reliable listening context in one place.
