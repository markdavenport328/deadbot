// Fixed, development-only responses for visual acceptance review. They use the
// same browser contract as the API, but never contact the server or a model.
// Open a fixture with `npm run dev --prefix web` and, for example,
// `/?fixture=branford`. The available names are exported below.
import type { ExperienceBlock, ExperienceResponse, ShowUnitBlock } from "./types";
import type { StreamEvent } from "./stream-events";

type FixtureSong = readonly [id: string, title: string, url: string | null, highlighted?: boolean];

const archive = "https://archive.org/details/";

function songs(entries: FixtureSong[]) {
  return entries.map(([id, title, listen_url, highlighted = false]) => ({
    performance_id: id,
    song_id: `song-${id}`,
    title,
    listen_url,
    highlighted,
    position_in_set: null
  }));
}

function show({
  id,
  date,
  venue,
  location,
  title,
  emphasis,
  note,
  visible_facets = ["guests", "listen", "setlist", "sources"],
  setlist_disclosure = "expanded",
  sets,
  guests = [],
  listen = [],
  sources = [],
  lineup = [],
  recordings = [],
  follow_up
}: {
  id: string;
  date: string;
  venue: string;
  location: string;
  title?: string;
  emphasis?: ShowUnitBlock["emphasis"];
  note?: string;
  visible_facets?: ShowUnitBlock["visible_facets"];
  setlist_disclosure?: ShowUnitBlock["setlist_disclosure"];
  sets: { label: string; songs: ReturnType<typeof songs> }[];
  guests?: ShowUnitBlock["guests"];
  listen?: ShowUnitBlock["listen"];
  sources?: ShowUnitBlock["sources"];
  lineup?: ShowUnitBlock["lineup"];
  recordings?: ShowUnitBlock["recordings"];
  follow_up?: string;
}): ShowUnitBlock {
  return {
    type: "show_unit",
    show_id: id,
    show_date: date,
    venue_name: venue,
    location,
    title: title ?? null,
    emphasis: emphasis ?? "supporting",
    note: note ?? null,
    visible_facets,
    setlist_disclosure,
    sets,
    setlist_note: null,
    guests,
    listen,
    sources,
    lineup,
    recordings,
    judgments: [],
    follow_up: follow_up ?? null
  };
}

function fixture(
  question: string,
  title: string,
  body_lead: string,
  blocks: ExperienceBlock[],
  presentation: NonNullable<ExperienceResponse["groups"]>[number]["presentation"] = "collection",
  group?: Pick<NonNullable<ExperienceResponse["groups"]>[number], "title" | "lead">
): ExperienceResponse {
  return {
    schema_version: "2",
    thread_id: `visual-${title.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-")}`,
    title,
    answer: body_lead,
    body_lead,
    mode: "answer",
    conversation: [
      { role: "user", text: question },
      { role: "assistant", text: body_lead }
    ],
    blocks,
    groups: [{ presentation, criteria: [], ...group, block_indexes: blocks.map((_, index) => index) }],
    sources: [
      { source_id: "fixture-archive", label: "Internet Archive", url: "https://archive.org", kind: "canonical" },
      { source_id: "fixture-deadnet", label: "Grateful Dead of the Day", url: "https://gratefuldeadoftheday.com", kind: "contextual_resource" }
    ]
  };
}

const branford: ExperienceResponse = fixture(
  "Was Branford on the whole 1991-09-10 Madison Square Garden show, and where should I listen for him?",
  "Branford Marsalis at Madison Square Garden",
  "Branford Marsalis joined the second set on September 10, 1991. Start with the late **Eyes of the World**, then follow the set’s long arc into *Dark Star*.",
  [
    show({
      id: "fixture-1991-09-10",
      date: "1991-09-10",
      venue: "Madison Square Garden",
      location: "New York, NY",
      title: "The full guest set",
      emphasis: "primary",
      note: "Marsalis is present for the complete second set—not just its famous opener. The guest appearance changes the way the jams breathe without making the set feel like a sit-in showcase.",
      visible_facets: ["guests", "listen", "setlist", "sources", "lineup", "recordings"],
      guests: [{ person_id: "branford", name: "Branford Marsalis", role: "guest", instruments: ["saxophone"] }],
      listen: [
        { label: "Listen to the complete audience recording", provider: "Internet Archive", url: `${archive}gd1991-09-10.sbd`, is_official: false },
        { label: "Listen to the soundboard transfer", provider: "Internet Archive", url: `${archive}gd1991-09-10.sbd.miller`, is_official: false }
      ],
      sources: [{ label: "Guest appearance notes", url: "https://jerrybase.com/events/19910910-01", source_name: "Jerrybase", note: "Documents Marsalis on the second set." }],
      lineup: [
        { person_id: "jerry-garcia", name: "Jerry Garcia", role: "performer", instruments: ["guitar", "vocals"] },
        { person_id: "bob-weir", name: "Bob Weir", role: "performer", instruments: ["guitar", "vocals"] },
        { person_id: "phil-lesh", name: "Phil Lesh", role: "performer", instruments: ["bass"] },
        { person_id: "bill-kreutzmann", name: "Bill Kreutzmann", role: "performer", instruments: ["drums"] },
        { person_id: "mickey-hart", name: "Mickey Hart", role: "performer", instruments: ["drums"] },
        { person_id: "vince-welnick", name: "Vince Welnick", role: "performer", instruments: ["keyboards"] },
        { person_id: "bruce-hornsby", name: "Bruce Hornsby", role: "performer", instruments: ["piano"] },
        { person_id: "branford-marsalis", name: "Branford Marsalis", role: "guest", instruments: ["saxophone"] }
      ],
      recordings: [
        { recording_id: "fixture-1991-09-10-sbd", title: "Soundboard recording", source_type: "Soundboard", archive_identifier: "gd1991-09-10.sbd.miller", url: `${archive}gd1991-09-10.sbd.miller`, source_id: "recording:fixture-1991-09-10-sbd" },
        { recording_id: "fixture-1991-09-10-aud", title: "Audience recording", source_type: "Audience", archive_identifier: "gd1991-09-10.aud", url: `${archive}gd1991-09-10.aud`, source_id: "recording:fixture-1991-09-10-aud" }
      ],
      sets: [
        { label: "Set 1", songs: songs([["910-01", "Hell in a Bucket", null], ["910-02", "Loser", null], ["910-03", "Stuck Inside of Mobile with the Memphis Blues Again", null]]) },
        { label: "Set 2", songs: songs([["910-11", "Eyes of the World", `${archive}gd1991-09-10.sbd#track11`, true], ["910-12", "Estimated Prophet", `${archive}gd1991-09-10.sbd#track12`, true], ["910-13", "Dark Star", `${archive}gd1991-09-10.sbd#track13`, true], ["910-14", "Drums", null], ["910-15", "Space", null], ["910-16", "Dark Star", `${archive}gd1991-09-10.sbd#track16`, true], ["910-17", "The Other One", null], ["910-18", "Wharf Rat", null], ["910-19", "Turn On Your Love Light", null]]) }
      ],
      follow_up: "How does Branford’s September 1991 approach differ from his 1990 appearance?"
    }),
    show({
      id: "fixture-1991-09-20",
      date: "1991-09-20",
      venue: "Madison Square Garden",
      location: "New York, NY",
      title: "The next night’s contrast",
      emphasis: "supporting",
      note: "A deliberately shorter path for comparing the two Garden appearances.",
      setlist_disclosure: "collapsed",
      guests: [{ person_id: "branford", name: "Branford Marsalis", role: "guest", instruments: ["saxophone"] }],
      sets: [{ label: "Second set", songs: songs([["920-01", "Eyes of the World", `${archive}gd1991-09-20.sbd#track9`, true], ["920-02", "Estimated Prophet", null], ["920-03", "Dark Star", `${archive}gd1991-09-20.sbd#track11`, true]]) }]
    }),
    show({
      id: "fixture-1990-03-29",
      date: "1990-03-29",
      venue: "Nassau Veterans Memorial Coliseum",
      location: "Uniondale, NY",
      title: "The earlier template",
      emphasis: "supporting",
      note: "The first collaboration is smaller in scale but explains why the 1991 return had such anticipation.",
      visible_facets: ["guests", "setlist"],
      setlist_disclosure: "hidden",
      guests: [{ person_id: "branford", name: "Branford Marsalis", role: "guest", instruments: ["saxophone"] }],
      sets: [{ label: "Second set", songs: songs([["329-01", "Bird Song", `${archive}gd1990-03-29.sbd#track8`, true], ["329-02", "Estimated Prophet", null], ["329-03", "Dark Star", `${archive}gd1990-03-29.sbd#track10`, true]]) }]
    })
  ]
);

const evolution: ExperienceResponse = fixture(
  "How did Eyes of the World evolve?",
  "Eyes of the World kept changing shape across two decades",
  "The song moved from a floating, conversational groove in 1973 to a tighter, more propulsive vehicle by 1974, then opened back up in 1990 to make room for a guest voice.",
  [
    {
      type: "era_unit", title: "1973: the open road", span: "1973",
      note: "The song is newly expansive here, with the vocal and instrumental sections still trading places freely.",
      performances: [
        { performance_id: "eyes-73-winterland", song_id: "song-eyes-of-the-world", song_title: "Eyes of the World", show_id: "fixture-1973-11-11", show_date: "1973-11-11", show_label: "1973-11-11 — Winterland Arena", set_label: "Second set", listen: { label: "Listen to Eyes of the World", provider: "Internet Archive", url: `${archive}gd1973-11-11#eyes`, is_official: false } },
        { performance_id: "eyes-73-roosevelt", song_id: "song-eyes-of-the-world", song_title: "Eyes of the World", show_id: "fixture-1973-08-04", show_date: "1973-08-04", show_label: "1973-08-04 — Roosevelt Stadium", set_label: "Second set", listen: { label: "Listen to Eyes of the World", provider: "Internet Archive", url: `${archive}gd1973-08-04#eyes`, is_official: false } }
      ],
      sources: [{ label: "Performance notes", url: "https://jerrybase.com", source_name: "Jerrybase", note: "Context for the early arrangement." }], follow_up: "What does Phil’s bass do differently in the 1973 versions?"
    },
    {
      type: "era_unit", title: "1974: leaner and more percussive", span: "1974",
      note: "The groove becomes more insistent here; this is a good place to hear the band turn a floating form into propulsion.",
      performances: [
        { performance_id: "eyes-74-freedom", song_id: "song-eyes-of-the-world", song_title: "Eyes of the World", show_id: "fixture-1974-06-18", show_date: "1974-06-18", show_label: "1974-06-18 — Freedom Hall", set_label: "Second set", listen: { label: "Listen to Eyes of the World", provider: "Internet Archive", url: `${archive}gd1974-06-18#eyes`, is_official: false } },
        { performance_id: "eyes-74-providence", song_id: "song-eyes-of-the-world", song_title: "Eyes of the World", show_id: "fixture-1974-06-23", show_date: "1974-06-23", show_label: "1974-06-23 — Providence Civic Center", set_label: "Second set", listen: { label: "Listen to Eyes of the World", provider: "Internet Archive", url: `${archive}gd1974-06-23#eyes`, is_official: false } }
      ],
      sources: [], follow_up: null
    },
    {
      type: "era_unit", title: "1990: a new kind of space", span: "1990",
      note: "By 1990 the song can welcome a guest voice without surrendering its internal conversation.",
      performances: [
        { performance_id: "eyes-90-nassau", song_id: "song-eyes-of-the-world", song_title: "Eyes of the World", show_id: "fixture-1990-03-29", show_date: "1990-03-29", show_label: "1990-03-29 — Nassau Veterans Memorial Coliseum", set_label: "Second set", listen: { label: "Listen to Eyes of the World", provider: "Internet Archive", url: `${archive}gd1990-03-29#eyes`, is_official: false } },
        { performance_id: "eyes-90-msg", song_id: "song-eyes-of-the-world", song_title: "Eyes of the World", show_id: "fixture-1990-09-16", show_date: "1990-09-16", show_label: "1990-09-16 — Madison Square Garden", set_label: "Second set", listen: { label: "Listen to Eyes of the World", provider: "Internet Archive", url: `${archive}gd1990-09-16#eyes`, is_official: false } }
      ],
      sources: [], follow_up: "What should I listen for when Branford enters this version?"
    },
    {
      type: "song_overview", song_id: "song-eyes-of-the-world", title: "Eyes of the World", original_artist: null, known_performance_count: 384,
      emphasis: "primary",
      note: "Across two decades the song moved from a floating, conversational groove to a tighter, more propulsive vehicle, then opened up again to welcome guest voices.",
      representative_performances: [], credits: [], source_ids: ["canonical:song-eyes-of-the-world"],
      albums: [{ release_id: "release-wake-of-the-flood", title: "Wake of the Flood", release_date: "1973-11-15", release_type: "studio" }],
      sources: [],
      visible_facets: ["history"], judgments: [],
      history: {
        known_count: 384,
        first: { performance_id: "eyes-history-first", show_id: "fixture-1973-02-09", show_date: "1973-02-09", show_label: "1973-02-09 — Maples Pavilion", set_label: "Second set", position_in_set: null, listen_url: null },
        last: { performance_id: "eyes-history-last", show_id: "fixture-1994-06-25", show_date: "1994-06-25", show_label: "1994-06-25 — Sam Boyd Silver Bowl", set_label: "Second set", position_in_set: null, listen_url: null },
        by_year: [
          { performance_id: "eyes-1973-sample", show_id: "fixture-1973-11-11", show_date: "1973-11-11", show_label: "1973-11-11 — Winterland Arena", set_label: "Second set", position_in_set: null, year: 1973, listen_url: `${archive}gd1973-11-11#eyes` },
          { performance_id: "eyes-1978-sample", show_id: "fixture-1978-05-07", show_date: "1978-05-07", show_label: "1978-05-07 — Boston Garden", set_label: "Second set", position_in_set: null, year: 1978, listen_url: `${archive}gd1978-05-07#eyes` },
          { performance_id: "eyes-1985-sample", show_id: "fixture-1985-06-18", show_date: "1985-06-18", show_label: "1985-06-18 — Greek Theatre", set_label: "Second set", position_in_set: null, year: 1985, listen_url: null },
          { performance_id: "eyes-1990-sample", show_id: "fixture-1990-09-16", show_date: "1990-09-16", show_label: "1990-09-16 — Madison Square Garden", set_label: "Second set", position_in_set: null, year: 1990, listen_url: `${archive}gd1990-09-16#eyes` }
        ]
      },
      follow_up: "Which other songs show a similarly gradual rhythmic shift?"
    }
  ] as ExperienceBlock[],
  "sequence"
);

const cornell: ExperienceResponse = fixture(
  "Is Cornell 5/8/77 really the best show?",
  "Cornell’s case is coherence, not consensus",
  "Cornell earns its reputation because the whole evening feels unusually assured. That does not make it the only 1977 show worth hearing—or a universal winner.",
  [
    { type: "editorial", presentation: "narrative", eyebrow: "The argument", title: "What people mean by “best”", paragraphs: ["The case is not that every song is the era’s longest or strangest. It is that **Scarlet > Fire**, the second-set transitions, and the playing’s collective confidence make a persuasive complete-night experience."], items: [] },
    show({
      id: "fixture-1977-05-08", date: "1977-05-08", venue: "Barton Hall, Cornell University", location: "Ithaca, NY", emphasis: "primary", title: "A remarkably complete night",
      note: "Use the second set as the evidence, then decide whether its polished momentum is what you want from this era.",
      listen: [{ label: "Listen to Betty Board recording", provider: "Internet Archive", url: `${archive}gd1977-05-08.sbd.hicks`, is_official: false }],
      sources: [{ label: "Show overview", url: "https://jerrybase.com/events/19770508-01", source_name: "Jerrybase", note: "Setlist and venue context." }],
      sets: [{ label: "Second set", songs: songs([["cornell-1", "Scarlet Begonias", `${archive}gd1977-05-08.sbd#scarlet`, true], ["cornell-2", "Fire on the Mountain", `${archive}gd1977-05-08.sbd#fire`, true], ["cornell-3", "Estimated Prophet", null], ["cornell-4", "The Other One", `${archive}gd1977-05-08.sbd#otherone`, true], ["cornell-5", "Morning Dew", `${archive}gd1977-05-08.sbd#morningdew`, true]]) }],
      follow_up: "Which other May 1977 show makes the strongest counterargument?"
    })
  ],
  "argument",
  {
    title: "The case for Cornell",
    lead: "A complete night can be persuasive without settling the question for everyone."
  }
);

const shakedown: ExperienceResponse = fixture(
  "Give me three Shakedown Street recommendations.",
  "Three Shakedowns, three temperatures",
  "Start with the taut 1978 original, then move to a dance-floor 1981 take and a late-period version that turns the song into a longer conversation.",
  [
      show({ id: "fixture-1978-12-31", date: "1978-12-31", venue: "Winterland Arena", location: "San Francisco, CA", title: "The first New Year’s test", emphasis: "primary", note: "Compact, sharp-edged, and close to the song’s original late-1978 character.", listen: [{ label: "Listen to the show", provider: "Internet Archive", url: `${archive}gd1978-12-31.sbd`, is_official: false }], sets: [{ label: "Second set", songs: songs([["shake-78", "Shakedown Street", `${archive}gd1978-12-31.sbd#shakedown`, true], ["shake-78-next", "Bertha", null]]) }] }),
      show({ id: "fixture-1981-03-09", date: "1981-03-09", venue: "Madison Square Garden", location: "New York, NY", title: "The dance-floor version", emphasis: "supporting", note: "The pulse sits forward; listen for how the band turns a groove tune into a full-room event.", sets: [{ label: "First set", songs: songs([["shake-81", "Shakedown Street", `${archive}gd1981-03-09.sbd#shakedown`, true], ["shake-81-next", "Minglewood Blues", null]]) }] }),
      show({ id: "fixture-1991-06-17", date: "1991-06-17", venue: "Giants Stadium", location: "East Rutherford, NJ", title: "The late-period stretch", emphasis: "supporting", note: "A slower-burning choice with enough room to hear the individual voices inside the rhythm section.", listen: [{ label: "Listen to the audience recording", provider: "Internet Archive", url: `${archive}gd1991-06-17.fob`, is_official: false }, { label: "Listen to the soundboard recording", provider: "Internet Archive", url: `${archive}gd1991-06-17.sbd`, is_official: false }], sets: [{ label: "Second set", songs: songs([["shake-91", "Shakedown Street", `${archive}gd1991-06-17.sbd#shakedown`, true], ["shake-91-next", "Samson and Delilah", null]]) }] })
  ],
  "comparison"
);

const fact: ExperienceResponse = {
  schema_version: "2",
  thread_id: "visual-fact",
  title: "American Beauty came out in November 1970",
  answer: "American Beauty was released on November 1, 1970.",
  body_lead: null,
  mode: "answer",
  conversation: [
    { role: "user", text: "When was American Beauty released?" },
    { role: "assistant", text: "American Beauty was released on November 1, 1970." }
  ],
  blocks: [
    {
      type: "album_unit",
      release_id: "release-american-beauty",
      title: "American Beauty",
      release_date: "1970-11-01",
      release_type: "studio",
      artist_name: "Grateful Dead",
      emphasis: "primary",
      note: "It is the band's second studio album of 1970, following Workingman's Dead by about five months.",
      listen: [{ label: "Listen to American Beauty", provider: "Spotify", url: "https://open.spotify.com/album/1CBhqfy4uwiWhPMZ2sqjRc", is_official: true }],
      tracks: [],
      personnel: [],
      sources: [],
      judgments: [],
      follow_up: "How did these songs settle into the live repertoire?"
    }
  ] as ExperienceBlock[],
  groups: [{ presentation: "collection", criteria: [], block_indexes: [0] }],
  sources: [
    { source_id: "fixture-archive", label: "Internet Archive", url: "https://archive.org", kind: "canonical" },
    { source_id: "fixture-deadnet", label: "Grateful Dead of the Day", url: "https://gratefuldeadoftheday.com", kind: "contextual_resource" }
  ]
};

const legacy: ExperienceResponse = {
  schema_version: "2",
  thread_id: "visual-legacy",
  title: "American Beauty split into durable staples and forgotten songs",
  answer: "Four American Beauty songs became durable parts of the touring vocabulary, while two nearly disappeared after the album's early tours.",
  body_lead: "Four American Beauty songs became durable parts of the touring vocabulary, while two nearly disappeared after the album's early tours.",
  mode: "answer",
  conversation: [
    { role: "user", text: "What was the live legacy of American Beauty?" },
    { role: "assistant", text: "Four American Beauty songs became durable parts of the touring vocabulary, while two nearly disappeared after the album's early tours." }
  ],
  blocks: [
    {
      type: "song_overview", song_id: "song-sugar-magnolia", title: "Sugar Magnolia", original_artist: null, known_performance_count: 606,
      emphasis: "supporting", note: "A compact studio song became one of the band's recurring celebratory vehicles.",
      representative_performances: [{ performance_id: "fixture-sugar", show_id: "fixture-1972-08-27", show_date: "1972-08-27", show_label: "1972-08-27 — Oregon Country Fair", set_label: "Second set", listen_url: `${archive}gd1972-08-27#sugar-magnolia` }],
      credits: [], source_ids: ["canonical:song-sugar-magnolia"], albums: [{ release_id: "release-american-beauty", title: "American Beauty", release_date: "1970-11-01", release_type: "studio" }], sources: [],
      visible_facets: ["representatives"], judgments: [], history: null, follow_up: null
    },
    {
      type: "song_overview", song_id: "song-truckin", title: "Truckin'", original_artist: null, known_performance_count: 538,
      emphasis: "supporting", note: "Its travel narrative became a durable live setlist engine across the documented touring span.",
      representative_performances: [{ performance_id: "fixture-truckin", show_id: "fixture-1970-11-08", show_date: "1970-11-08", show_label: "1970-11-08 — Capitol Theatre", set_label: "Second set", listen_url: `${archive}gd1970-11-08#truckin` }],
      credits: [], source_ids: ["canonical:song-truckin"], albums: [{ release_id: "release-american-beauty", title: "American Beauty", release_date: "1970-11-01", release_type: "studio" }], sources: [],
      visible_facets: ["representatives"], judgments: [], history: null, follow_up: null
    },
    {
      type: "song_overview", song_id: "song-friend-of-the-devil", title: "Friend of the Devil", original_artist: null, known_performance_count: 308,
      emphasis: "supporting", note: "It survived the acoustic period by repeatedly changing shape inside the band's larger concert sound.",
      representative_performances: [{ performance_id: "fixture-friend", show_id: "fixture-1978-04-16", show_date: "1978-04-16", show_label: "1978-04-16 — Huntington Civic Center", set_label: "First set", listen_url: `${archive}gd1978-04-16#friend-of-the-devil` }],
      credits: [], source_ids: ["canonical:song-friend-of-the-devil"], albums: [{ release_id: "release-american-beauty", title: "American Beauty", release_date: "1970-11-01", release_type: "studio" }], sources: [],
      visible_facets: ["representatives"], judgments: [], history: null, follow_up: null
    },
    {
      type: "song_overview", song_id: "song-brokedown-palace", title: "Brokedown Palace", original_artist: null, known_performance_count: 287,
      emphasis: "supporting", note: "Its theatrical emotional arc made it a recurring Garcia showcase rather than a fixed studio replica.",
      representative_performances: [{ performance_id: "fixture-brokedown", show_id: "fixture-1989-10-09", show_date: "1989-10-09", show_label: "1989-10-09 — Hampton Coliseum", set_label: "Encore", listen_url: `${archive}gd1989-10-09#brokedown-palace` }],
      credits: [], source_ids: ["canonical:song-brokedown-palace"], albums: [{ release_id: "release-american-beauty", title: "American Beauty", release_date: "1970-11-01", release_type: "studio" }], sources: [],
      visible_facets: ["representatives"], judgments: [], history: null, follow_up: null
    },
    {
      type: "song_overview", song_id: "song-candyman", title: "Candyman", original_artist: null, known_performance_count: 114,
      emphasis: "mention", note: "Candyman found only occasional space in the sets after the mid-1970s, well below the album's other songs.",
      representative_performances: [], credits: [], source_ids: ["canonical:song-candyman"],
      albums: [{ release_id: "release-american-beauty", title: "American Beauty", release_date: "1970-11-01", release_type: "studio" }], sources: [],
      visible_facets: [], judgments: [], history: null, follow_up: null
    },
    {
      type: "song_overview", song_id: "song-attics-of-my-life", title: "Attics of My Life", original_artist: null, known_performance_count: 24,
      emphasis: "mention", note: "Attics of My Life stopped appearing for most of the 1970s and 1980s, returning only briefly late in the band's touring history.",
      representative_performances: [], credits: [], source_ids: ["canonical:song-attics-of-my-life"],
      albums: [{ release_id: "release-american-beauty", title: "American Beauty", release_date: "1970-11-01", release_type: "studio" }], sources: [],
      visible_facets: [], judgments: [], history: null, follow_up: null
    },
    {
      type: "editorial", presentation: "narrative", eyebrow: "The pattern", title: null,
      paragraphs: [
        "The four durable songs share open, flexible structures that let the band reinterpret them for two decades, while **Candyman** and **Attics of My Life** kept tighter, more fixed arrangements that left less room to grow alongside the rest of the live show."
      ],
      items: []
    }
  ] as ExperienceBlock[],
  groups: [
    { presentation: "collection", title: "The durable songs", criteria: [], block_indexes: [0, 1, 2, 3] },
    { presentation: "collection", title: "The ones that faded", criteria: [], block_indexes: [4, 5] },
    { presentation: "argument", lead: "American Beauty split into songs the band kept reinventing and songs it mostly left behind.", criteria: [], block_indexes: [6] }
  ],
  sources: [
    { source_id: "fixture-archive", label: "Internet Archive", url: "https://archive.org", kind: "canonical" },
    { source_id: "fixture-deadnet", label: "Grateful Dead of the Day", url: "https://gratefuldeadoftheday.com", kind: "contextual_resource" }
  ]
};

// A comparison group of three judged performance_unit blocks, next to a
// fact_grid group, so a review can compare both presentations without
// scrolling between unrelated fixtures.
const viewsBlocks: ExperienceBlock[] = [
  {
    type: "performance_unit", performance_id: "fixture-1995-07-09-so-many-roads", song_id: "song-so-many-roads", song_title: "So Many Roads",
    show_id: "fixture-1995-07-09", show_date: "1995-07-09", show_label: "1995-07-09 — Soldier Field", venue_name: "Soldier Field", location: "Chicago, IL",
    set_label: "Second set", position_in_set: "3", emphasis: "supporting",
    note: "Garcia's voice is worn, but the song's slow build still lands as a real emotional high point of the second set.",
    judgments: [
      "A vocal high point despite Garcia's declining range",
      "One of the last times the song's climb fully pays off",
      "Divides listeners who hear strain and listeners who hear feeling"
    ],
    listen: [{ label: "Listen to So Many Roads", provider: "Internet Archive", url: `${archive}gd1995-07-09.sbd.miller.97483.flac16#somanyroads`, is_official: false }],
    sources: [{ label: "Show overview", url: "https://jerrybase.com/events/19950709-01", source_name: "Jerrybase", note: "Setlist and venue context." }],
    follow_up: null
  },
  {
    type: "performance_unit", performance_id: "fixture-1995-07-09-black-muddy-river", song_id: "song-black-muddy-river", song_title: "Black Muddy River",
    show_id: "fixture-1995-07-09", show_date: "1995-07-09", show_label: "1995-07-09 — Soldier Field", venue_name: "Soldier Field", location: "Chicago, IL",
    set_label: "Encore", position_in_set: "1", emphasis: "supporting",
    note: "A warm, unhurried reading that many listeners point to as evidence the band still had something to give.",
    judgments: [
      "A gentle, well-sung encore choice",
      "One of the night's clearest moments of connection",
      "Reads as a quiet farewell in hindsight"
    ],
    listen: [{ label: "Listen to Black Muddy River", provider: "Internet Archive", url: `${archive}gd1995-07-09.sbd.miller.97483.flac16#blackmuddyriver`, is_official: false }],
    sources: [],
    follow_up: null
  },
  {
    type: "performance_unit", performance_id: "fixture-1995-07-09-box-of-rain", song_id: "song-box-of-rain", song_title: "Box of Rain",
    show_id: "fixture-1995-07-09", show_date: "1995-07-09", show_label: "1995-07-09 — Soldier Field", venue_name: "Soldier Field", location: "Chicago, IL",
    set_label: "Encore", position_in_set: "2", emphasis: "supporting",
    note: "The closing song of the band's final show, delivered without much fanfare at the time.",
    judgments: [
      "Gains its weight only in retrospect",
      "A modest performance on its own musical terms",
      "The detail most retrospective accounts lead with"
    ],
    listen: [{ label: "Listen to Box of Rain", provider: "Internet Archive", url: `${archive}gd1995-07-09.sbd.miller.97483.flac16#boxofrain`, is_official: false }],
    sources: [],
    follow_up: null
  },
  {
    type: "editorial", presentation: "fact_grid", eyebrow: null, title: null, paragraphs: [],
    items: [
      { title: "Mississippi Half-Step Uptown Toodeloo", value: "237 performances", detail: "It became a durable early-set standard across most of the touring era." },
      { title: "Row Jimmy", value: "277 performances", detail: "The song settled into occasional but steady use rather than heavy rotation." },
      { title: "Stella Blue", value: "330", detail: "It remained a signature late-set ballad through the band's final years." },
      { title: "Let Me Sing Your Blues Away", value: "6 performances, all in 1973", detail: "The Pigpen-era song largely left the setlist after 1973." }
    ]
  }
];

const views: ExperienceResponse = {
  schema_version: "2",
  thread_id: "visual-views",
  title: "Soldier Field 1995 through three performances, and the songs that stayed",
  answer: "Three performances from Soldier Field 1995 show real, if modest, highlights, and four Wake of the Flood songs kept very different footholds in the live repertoire.",
  body_lead: "Three performances from Soldier Field 1995 show real, if modest, highlights, and four Wake of the Flood songs kept very different footholds in the live repertoire.",
  mode: "answer",
  conversation: [
    { role: "user", text: "How do Soldier Field 1995-07-09's key performances hold up, and which Wake of the Flood songs stuck around live?" },
    { role: "assistant", text: "Three performances from Soldier Field 1995 show real, if modest, highlights, and four Wake of the Flood songs kept very different footholds in the live repertoire." }
  ],
  blocks: viewsBlocks,
  groups: [
    { presentation: "comparison", title: "How three of the night's performances land", criteria: ["Musical quality", "Emotional weight", "Worth hearing"], block_indexes: [0, 1, 2] },
    { presentation: "collection", title: "The album songs in the live repertoire", criteria: [], block_indexes: [3] }
  ],
  sources: [
    { source_id: "fixture-archive", label: "Internet Archive", url: "https://archive.org", kind: "canonical" },
    { source_id: "fixture-deadnet", label: "Grateful Dead of the Day", url: "https://gratefuldeadoftheday.com", kind: "contextual_resource" }
  ]
};

const workingmansDeadTracks: readonly [title: string, highlighted?: boolean][] = [
  ["Uncle John's Band"],
  ["High Time"],
  ["Dire Wolf"],
  ["New Speedway Boogie"],
  ["Cumberland Blues", true],
  ["Black Peter"],
  ["Easy Wind"],
  ["Casey Jones", true]
];

const album: ExperienceResponse = fixture(
  "What made Workingman's Dead a turning point for the band?",
  "Workingman's Dead brought songs back to the fore",
  "Workingman's Dead gave the band a second repertoire engine: concise, character-driven songs that could anchor a set without limiting the improvisation around them.",
  [
    {
      type: "album_unit",
      release_id: "workingmans-dead",
      title: "Workingman's Dead",
      release_date: "1970-06-14",
      release_type: "studio",
      artist_name: "Grateful Dead",
      emphasis: "primary",
      note: "Its eight songs collectively became a second repertoire engine for the band: concise, character-driven material that could anchor a set without limiting the surrounding improvisation.",
      listen: [
        { label: "Listen to Workingman's Dead", provider: "Spotify", url: "https://open.spotify.com/album/0Dx3ntxFk1ZzIWFp2mL6oN", is_official: true }
      ],
      tracks: workingmansDeadTracks.map(([title, highlighted = false], index) => ({
        track_number: index + 1,
        title,
        highlighted,
        duration_seconds: null,
        listen_url: `${archive}workingmans-dead#track${index + 1}`,
        performance_id: null,
        song_id: null
      })),
      personnel: [
        { person_id: "bill-kreutzmann", name: "Bill Kreutzmann", instrument: "Drums (Drum Set)", role: "performer" },
        { person_id: "bill-kreutzmann", name: "Bill Kreutzmann", instrument: "Percussion", role: "performer" },
        { person_id: "bob-weir", name: "Bob Weir", instrument: "Guitar", role: "performer" },
        { person_id: "bob-weir", name: "Bob Weir", instrument: "Lead Vocals", role: "performer" },
        { person_id: "david-nelson", name: "David Nelson", instrument: "Acoustic Guitar", role: "guest" },
        { person_id: "jerry-garcia", name: "Jerry Garcia", instrument: "Banjo", role: "performer" },
        { person_id: "jerry-garcia", name: "Jerry Garcia", instrument: "Guitar", role: "performer" },
        { person_id: "jerry-garcia", name: "Jerry Garcia", instrument: "Lead Vocals", role: "performer" },
        { person_id: "jerry-garcia", name: "Jerry Garcia", instrument: "Pedal Steel Guitar", role: "performer" },
        { person_id: "mickey-hart", name: "Mickey Hart", instrument: "Drums (Drum Set)", role: "performer" },
        { person_id: "mickey-hart", name: "Mickey Hart", instrument: "Percussion", role: "performer" },
        { person_id: "phil-lesh", name: "Phil Lesh", instrument: "Bass", role: "performer" },
        { person_id: "pigpen-mckernan", name: "Ron \"Pigpen\" McKernan", instrument: "Harmonica", role: "performer" },
        { person_id: "pigpen-mckernan", name: "Ron \"Pigpen\" McKernan", instrument: "Keyboard", role: "performer" }
      ],
      sources: [
        { label: "Album credits", url: "https://www.discogs.com/release/workingmans-dead", source_name: "Discogs", note: "Personnel and release details." }
      ],
      judgments: [],
      follow_up: "Why did the band turn toward acoustic material in 1970?"
    }
  ] as ExperienceBlock[],
  "collection",
  { title: "The record" }
);

// One primary performance_unit judged on four criteria, with its set
// neighbors, so the labeled groups and the before/after strip can be reviewed
// at full width.
const performanceBlocks: ExperienceBlock[] = [
  {
    type: "performance_unit", performance_id: "fixture-1968-02-14-dark-star", song_id: "song-dark-star", song_title: "Dark Star",
    show_id: "fixture-1968-02-14", show_date: "1968-02-14", show_label: "1968-02-14 — Carousel Ballroom", venue_name: "Carousel Ballroom", location: "San Francisco, CA",
    set_label: "Set 1", position_in_set: "3", emphasis: "primary",
    note: "A useful early comparison: the 1968 approach is more compressed and eventful, with abrupt changes of color and intensity.",
    judgments: [
      "Dense, echoing, and sharply colored; early psychedelia still feels close to the studio experiment.",
      "Garcia is foregrounded while Lesh and Weir increasingly respond in loose counterpoint.",
      "The form feels like a route through episodes—verse, exploratory jam, return—rather than a long, spacious arc.",
      "Unstable and electric: the music seems to be discovering what the song can become."
    ],
    previous: { performance_id: "fixture-1968-02-14-schoolgirl", title: "Good Morning Little Schoolgirl" },
    next: { performance_id: "fixture-1968-02-14-china-cat", title: "China Cat Sunflower" },
    listen: [
      { label: "Hear Dark Star on the official release", provider: "Dead.net", url: "https://www.dead.net/", is_official: true },
      { label: "Hear the full show", provider: "Internet Archive", url: `${archive}gd1968-02-14.sbd`, is_official: false }
    ],
    sources: [{ label: "Show notes", url: "https://jerrybase.com/events/19680214-01", source_name: "Jerrybase", note: "Set order and venue context." }],
    follow_up: "How does the 1968 Dark Star differ from the 1972 versions?"
  }
];

const performance: ExperienceResponse = {
  schema_version: "2",
  thread_id: "visual-performance",
  title: "The 1968 Dark Star is a route through episodes",
  answer: "The Carousel Ballroom reading compresses the song into sharp, eventful episodes rather than the long arc it grew into.",
  body_lead: "The Carousel Ballroom reading compresses the song into sharp, eventful episodes rather than the long arc it grew into.",
  mode: "answer",
  conversation: [
    { role: "user", text: "What is the 1968 Carousel Ballroom Dark Star like?" },
    { role: "assistant", text: "The Carousel Ballroom reading compresses the song into sharp, eventful episodes rather than the long arc it grew into." }
  ],
  blocks: performanceBlocks,
  groups: [
    { presentation: "comparison", title: null, criteria: ["Texture", "Band interaction", "Form", "Emotional effect"], block_indexes: [0] }
  ],
  sources: [
    { source_id: "fixture-archive", label: "Internet Archive", url: "https://archive.org", kind: "canonical" }
  ]
};

export const visualFixtureNames = ["branford", "cornell", "shakedown", "fact", "legacy", "evolution", "views", "album", "performance"] as const;

export type VisualFixtureName = (typeof visualFixtureNames)[number];

const fixtures: Record<VisualFixtureName, ExperienceResponse> = { branford, cornell, shakedown, fact, legacy, evolution, views, album, performance };

export function visualFixtureFromLocation(): ExperienceResponse | null {
  if (!import.meta.env.DEV) return null;
  const name = new URLSearchParams(window.location.search).get("fixture");
  return name && name in fixtures ? fixtures[name as keyof typeof fixtures] : null;
}

// A fixture replayed as the same event sequence the server streams: statuses,
// the answer growing word by word, the page head, then each group opening,
// its blocks, and closing, finishing with the full response. Used only by the
// development `?stream=` replay in App.tsx.
export function streamEventsFor(name: VisualFixtureName): StreamEvent[] {
  const response = fixtures[name];
  const events: StreamEvent[] = [
    { type: "status", text: "Looking through the library" },
    { type: "status", text: "Reading the show" }
  ];
  const words = response.answer.split(" ");
  words.forEach((_, index) => events.push({ type: "answer", text: words.slice(0, index + 1).join(" ") }));
  events.push({ type: "status", text: "Composing the page" });
  events.push({ type: "page_head", title: response.title, lead: response.body_lead ?? null });
  response.groups.forEach((group, index) => {
    const meta = { index, title: group.title ?? null, lead: group.lead ?? null, presentation: group.presentation, criteria: group.criteria ?? [] };
    events.push({ type: "group_open", ...meta });
    group.block_indexes.forEach((blockIndex) => {
      const block = response.blocks[blockIndex];
      if (block) events.push({ type: "block", group_index: index, block });
    });
    events.push({ type: "group_close", ...meta });
  });
  events.push({ type: "response", response });
  return events;
}
