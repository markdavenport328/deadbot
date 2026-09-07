// Fixed, development-only responses for visual acceptance review. They use the
// same browser contract as the API, but never contact the server or a model.
// Open a fixture with `npm run dev --prefix web` and, for example,
// `/?fixture=branford`. The available names are exported below.
import type { ExperienceBlock, ExperienceResponse, ShowUnitBlock } from "./types";

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
  role,
  note,
  visible_facets = ["guests", "listen", "setlist", "sources"],
  setlist_disclosure = "expanded",
  sets,
  guests = [],
  listen = [],
  sources = [],
  follow_up
}: {
  id: string;
  date: string;
  venue: string;
  location: string;
  title?: string;
  role?: ShowUnitBlock["role"];
  note?: string;
  visible_facets?: ShowUnitBlock["visible_facets"];
  setlist_disclosure?: ShowUnitBlock["setlist_disclosure"];
  sets: { label: string; songs: ReturnType<typeof songs> }[];
  guests?: ShowUnitBlock["guests"];
  listen?: ShowUnitBlock["listen"];
  sources?: ShowUnitBlock["sources"];
  follow_up?: string;
}): ShowUnitBlock {
  return {
    type: "show_unit",
    show_id: id,
    show_date: date,
    venue_name: venue,
    location,
    title: title ?? null,
    role: role ?? null,
    note: note ?? null,
    visible_facets,
    setlist_disclosure,
    sets,
    setlist_note: null,
    guests,
    listen,
    sources,
    follow_up: follow_up ?? null
  };
}

function fixture(
  question: string,
  title: string,
  mode: ExperienceResponse["mode"],
  body_lead: string,
  blocks: ExperienceBlock[],
  presentation: NonNullable<ExperienceResponse["groups"]>[number]["presentation"] = "collection",
  group?: Pick<NonNullable<ExperienceResponse["groups"]>[number], "title" | "lead">
): ExperienceResponse {
  return {
    schema_version: "1",
    thread_id: `visual-${title.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-")}`,
    title,
    answer: body_lead,
    body_lead,
    mode,
    conversation: [
      { role: "user", text: question },
      { role: "assistant", text: body_lead }
    ],
    blocks,
    groups: [{ presentation, ...group, block_indexes: blocks.map((_, index) => index) }],
    layout: [{ region: "primary", block_indexes: blocks.map((_, index) => index) }],
    sources: [
      { source_id: "fixture-archive", label: "Internet Archive", url: "https://archive.org", kind: "canonical" },
      { source_id: "fixture-deadnet", label: "Grateful Dead of the Day", url: "https://gratefuldeadoftheday.com", kind: "contextual_resource" }
    ]
  };
}

const branford: ExperienceResponse = fixture(
  "Was Branford on the whole 1991-09-10 Madison Square Garden show, and where should I listen for him?",
  "Branford Marsalis at Madison Square Garden",
  "listening",
  "Branford Marsalis joined the second set on September 10, 1991. Start with the late **Eyes of the World**, then follow the set’s long arc into *Dark Star*.",
  [{
    type: "show_explorer",
    title: "Three ways into Branford’s 1991 run",
    organization: "curated",
    items: [
      show({
        id: "fixture-1991-09-10",
        date: "1991-09-10",
        venue: "Madison Square Garden",
        location: "New York, NY",
        title: "The full guest set",
        role: "anchor",
        note: "Marsalis is present for the complete second set—not just its famous opener. The guest appearance changes the way the jams breathe without making the set feel like a sit-in showcase.",
        guests: [{ person_id: "branford", name: "Branford Marsalis", role: "guest", instruments: ["saxophone"] }],
        listen: [
          { label: "Listen to the complete audience recording", provider: "Internet Archive", url: `${archive}gd1991-09-10.sbd`, is_official: false },
          { label: "Listen to the soundboard transfer", provider: "Internet Archive", url: `${archive}gd1991-09-10.sbd.miller`, is_official: false }
        ],
        sources: [{ label: "Guest appearance notes", url: "https://jerrybase.com/events/19910910-01", source_name: "Jerrybase", note: "Documents Marsalis on the second set." }],
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
        role: "contrast",
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
        role: "supporting",
        note: "The first collaboration is smaller in scale but explains why the 1991 return had such anticipation.",
        visible_facets: ["guests", "setlist"],
        setlist_disclosure: "hidden",
        guests: [{ person_id: "branford", name: "Branford Marsalis", role: "guest", instruments: ["saxophone"] }],
        sets: [{ label: "Second set", songs: songs([["329-01", "Bird Song", `${archive}gd1990-03-29.sbd#track8`, true], ["329-02", "Estimated Prophet", null], ["329-03", "Dark Star", `${archive}gd1990-03-29.sbd#track10`, true]]) }]
      })
    ]
  }]
);

const eyes: ExperienceResponse = fixture(
  "How did Eyes of the World develop?",
  "How Eyes of the World kept changing",
  "comparison",
  "These three performances make a useful route through the song’s changing rhythmic center: fluid 1973, muscular 1974, and the roomier late-period return.",
  [
    {
      type: "era_unit", title: "1973: the open road", span: "1973", role: "anchor",
      note: "The song is newly expansive here, with the vocal and instrumental sections still trading places freely.",
      performances: [{ performance_id: "eyes-73", song_id: "eyes", song_title: "Eyes of the World", show_id: "fixture-1973-11-11", show_date: "1973-11-11", show_label: "1973-11-11 — Winterland Arena", set_label: "Second set", listen: { label: "Listen to Eyes of the World", provider: "Internet Archive", url: `${archive}gd1973-11-11#eyes`, is_official: false } }],
      sources: [{ label: "Performance notes", url: "https://jerrybase.com", source_name: "Jerrybase", note: "Context for the early arrangement." }], follow_up: "What does Phil’s bass do differently in the 1973 versions?"
    },
    {
      type: "era_unit", title: "1974: leaner and more percussive", span: "1974", role: "turning_point",
      note: "The groove becomes more insistent; this is a good place to hear the band turn a floating form into propulsion.",
      performances: [{ performance_id: "eyes-74", song_id: "eyes", song_title: "Eyes of the World", show_id: "fixture-1974-06-18", show_date: "1974-06-18", show_label: "1974-06-18 — Freedom Hall", set_label: "Second set", listen: null }],
      sources: [], follow_up: null
    },
    {
      type: "era_unit", title: "1990: a new kind of space", span: "1990", role: "culmination",
      note: "By 1990 the song can welcome a guest voice without surrendering its internal conversation.",
      performances: [{ performance_id: "eyes-90", song_id: "eyes", song_title: "Eyes of the World", show_id: "fixture-1990-03-29", show_date: "1990-03-29", show_label: "1990-03-29 — Nassau Veterans Memorial Coliseum", set_label: "Second set", listen: { label: "Listen to Eyes of the World", provider: "Internet Archive", url: `${archive}gd1990-03-29#eyes`, is_official: false } }],
      sources: [], follow_up: "What should I listen for when Branford enters this version?"
    }
  ] as ExperienceBlock[],
  "sequence"
);

const cornell: ExperienceResponse = fixture(
  "Is Cornell 5/8/77 really the best show?",
  "Cornell’s case is coherence, not consensus",
  "research",
  "Cornell earns its reputation because the whole evening feels unusually assured. That does not make it the only 1977 show worth hearing—or a universal winner.",
  [
    { type: "editorial", presentation: "narrative", eyebrow: "The argument", title: "What people mean by “best”", paragraphs: ["The case is not that every song is the era’s longest or strangest. It is that **Scarlet > Fire**, the second-set transitions, and the playing’s collective confidence make a persuasive complete-night experience."], items: [] },
    show({
      id: "fixture-1977-05-08", date: "1977-05-08", venue: "Barton Hall, Cornell University", location: "Ithaca, NY", role: "anchor", title: "A remarkably complete night",
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
  "listening",
  "Start with the taut 1978 original, then move to a dance-floor 1981 take and a late-period version that turns the song into a longer conversation.",
  [
      show({ id: "fixture-1978-12-31", date: "1978-12-31", venue: "Winterland Arena", location: "San Francisco, CA", title: "The first New Year’s test", role: "anchor", note: "Compact, sharp-edged, and close to the song’s original late-1978 character.", listen: [{ label: "Listen to the show", provider: "Internet Archive", url: `${archive}gd1978-12-31.sbd`, is_official: false }], sets: [{ label: "Second set", songs: songs([["shake-78", "Shakedown Street", `${archive}gd1978-12-31.sbd#shakedown`, true], ["shake-78-next", "Bertha", null]]) }] }),
      show({ id: "fixture-1981-03-09", date: "1981-03-09", venue: "Madison Square Garden", location: "New York, NY", title: "The dance-floor version", role: "representative", note: "The pulse sits forward; listen for how the band turns a groove tune into a full-room event.", sets: [{ label: "First set", songs: songs([["shake-81", "Shakedown Street", `${archive}gd1981-03-09.sbd#shakedown`, true], ["shake-81-next", "Minglewood Blues", null]]) }] }),
      show({ id: "fixture-1991-06-17", date: "1991-06-17", venue: "Giants Stadium", location: "East Rutherford, NJ", title: "The late-period stretch", role: "contrast", note: "A slower-burning choice with enough room to hear the individual voices inside the rhythm section.", listen: [{ label: "Listen to the audience recording", provider: "Internet Archive", url: `${archive}gd1991-06-17.fob`, is_official: false }, { label: "Listen to the soundboard recording", provider: "Internet Archive", url: `${archive}gd1991-06-17.sbd`, is_official: false }], sets: [{ label: "Second set", songs: songs([["shake-91", "Shakedown Street", `${archive}gd1991-06-17.sbd#shakedown`, true], ["shake-91-next", "Samson and Delilah", null]]) }] })
  ],
  "comparison"
);

const fact: ExperienceResponse = fixture(
  "What opened Veneta?",
  "Veneta opened with The Promised Land",
  "quick_fact",
  "The Grateful Dead opened the August 27, 1972 Veneta show with **The Promised Land**.",
  [{
    type: "editorial", presentation: "fact_grid", eyebrow: "Quick answer", title: null, paragraphs: [],
    items: [
      { marker: "Opener", title: "Opener", value: "The Promised Land", detail: "It led the first set at the Oregon Country Fair benefit." },
      { marker: "Next", title: "Next song", value: "Sugaree", detail: "The early set continues without a break in pace.", follow_up: "What did they play after Dark Star at Veneta?" }
    ]
  }]
);

export const visualFixtureNames = ["branford", "eyes", "cornell", "shakedown", "fact"] as const;

const fixtures: Record<(typeof visualFixtureNames)[number], ExperienceResponse> = { branford, eyes, cornell, shakedown, fact };

export function visualFixtureFromLocation(): ExperienceResponse | null {
  if (!import.meta.env.DEV) return null;
  const name = new URLSearchParams(window.location.search).get("fixture");
  return name && name in fixtures ? fixtures[name as keyof typeof fixtures] : null;
}
