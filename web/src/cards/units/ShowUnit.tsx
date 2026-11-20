import { useMemo } from "react";
import { type ShowUnitBlock } from "../../types";
import { CardHeading, Drawer, MoreAbout, type DrawerTab } from "../components";
import { type FollowUp } from "../../core/ask-request";
import { type PlayerTrack } from "../../player/player";
import { ClampText, ListenLinks, splitListen, toTrack } from "../listening";
import { formatShowDateLong } from "../../core/format";
import { renderInline } from "../inline";
import { type ShowMeta, thumbnailForIdentifier, toPlayerTrack, CardHead, ListenFor, IdRow, Meta, PlainList, PeopleList, GoDeeper } from "../parts";
import { SetlistPanel } from "../setlist";
import { UnitFrame, CriteriaTable } from "./shared";

export function ShowUnit({
  unit,
  criteria,
  soleUnit,
  onFollowUp,
  inRow = false
}: {
  unit: ShowUnitBlock;
  criteria: string[];
  soleUnit: boolean;
  onFollowUp: FollowUp;
  inRow?: boolean;
}) {
  const shows = (facet: ShowUnitBlock["visible_facets"][number]) => unit.visible_facets.includes(facet);
  const openFacets = unit.emphasis === "primary" && soleUnit;
  const dateLong = formatShowDateLong(unit.show_date);
  const highlights = unit.sets.flatMap((set) => set.songs.filter((song) => song.highlighted));
  const totalSongs = unit.sets.reduce((count, set) => count + set.songs.length, 0);
  const showMeta: ShowMeta = {
    showDate: unit.show_date,
    venueName: unit.venue_name,
    recordingDetailsUrl: unit.recording_details_url,
    thumbnailUrl: thumbnailForIdentifier(unit.recording_identifier)
  };
  // The show's tape: the setlist's tracks when the card shows a setlist,
  // otherwise the tape the card carries on its own, so a card plays and
  // queues the whole show whichever facets it shows.
  const playableQueue = useMemo(
    () => {
      const fromSetlist = unit.sets.flatMap((set) => set.songs.map((song) => toPlayerTrack(song, showMeta)).filter((track): track is PlayerTrack => track !== null));
      return fromSetlist.length > 0 ? fromSetlist : (unit.tracks ?? []).map((track) => toTrack(track, showMeta));
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [unit.sets, unit.tracks, unit.show_date, unit.venue_name, unit.recording_details_url, unit.recording_identifier]
  );

  // The guest joins the meta line: who was there, not a separate labeled row.
  const guestsNode = shows("guests") && unit.guests.length > 0 ? (
    <>
      with{" "}
      {unit.guests.map((guest, index) => (
        <span key={`${guest.person_id}-${index}`}>
          {index > 0 ? ", " : ""}
          <strong>{guest.name}</strong>, {guest.instruments.join(", ")}
        </span>
      ))}
    </>
  ) : null;

  const tabs: DrawerTab[] = [];
  if (shows("setlist") && unit.setlist_disclosure !== "hidden" && unit.sets.length > 0) {
    tabs.push({ id: "setlist", label: "Setlist", count: totalSongs, content: <SetlistPanel sets={unit.sets} showMeta={showMeta} /> });
  }
  if (shows("lineup") && unit.lineup.length > 0) {
    tabs.push({
      id: "lineup",
      label: "Lineup",
      count: unit.lineup.length,
      content: (
        <PeopleList
          people={unit.lineup.map((person) => ({
            key: `${person.person_id}-${person.role}`,
            name: person.name,
            detail: person.instruments.join(", "),
            guest: person.role === "guest"
          }))}
        />
      )
    });
  }
  if (shows("recordings") && unit.recordings.length > 0) {
    tabs.push({
      id: "recordings",
      label: "Recordings",
      count: unit.recordings.length,
      content: (
        <PlainList
          items={unit.recordings.map((recording) => ({
            key: recording.recording_id,
            title: recording.title,
            url: recording.url,
            queue: recording.archive_identifier && recording.archive_identifier === unit.recording_identifier ? playableQueue : undefined,
            detail: [recording.source_type, recording.archive_identifier].filter(Boolean).join(" · ")
          }))}
        />
      )
    });
  }
  // Two authors share the top of the card. The library names the show: type,
  // date, venue and place, in one identity zone. When the model wrote a
  // headline, it opens the overview beneath that zone with its note as the
  // text; without one, the venue is the headline as before.
  const modelHeadline = unit.title?.trim() || "";
  const identityName = unit.venue_name || dateLong;
  const listen = splitListen(shows("listen") ? unit.listen : [], playableQueue);
  // A show with tape in the library plays it in our player: the card's main
  // listen control plays the queue, and any outside links (a Relisten page)
  // stay below as quiet links.
  const primary = listen.primary
    ? { play: listen.primary.play, label: listen.primary.action.label }
    : playableQueue.length > 0
      ? { play: { start: playableQueue[0], queue: playableQueue }, label: `Play ${identityName}` }
      : null;
  const wantsSetlistOpen = unit.setlist_disclosure === "expanded" || openFacets || inRow;
  const initialOpen = wantsSetlistOpen && tabs.some((tab) => tab.id === "setlist") ? "setlist" : null;

  return (
    <UnitFrame inRow={inRow} className={`show-unit emphasis-${unit.emphasis}`}>
      {inRow ? (
        modelHeadline ? <CardHeading className="overview">{modelHeadline}</CardHeading> : null
      ) : modelHeadline ? (
        <>
          <IdRow type="Show" />
          <CardHead primary={primary}>
            <div className="identity">
              <p className="identity-name">
                <span>{unit.venue_name || dateLong}</span>
                {unit.venue_name ? <span>{dateLong}</span> : null}
              </p>
              <Meta parts={[unit.location, guestsNode]} />
            </div>
            <CardHeading className="overview">{modelHeadline}</CardHeading>
          </CardHead>
        </>
      ) : (
        <>
          <IdRow type="Show" when={dateLong} />
          <CardHead primary={primary}>
            <CardHeading>{identityName}</CardHeading>
            <Meta parts={[unit.location, guestsNode]} />
          </CardHead>
        </>
      )}
      {unit.note && !inRow && <ClampText className="unit-note">{renderInline(unit.note)}</ClampText>}
      <CriteriaTable criteria={criteria} judgments={unit.judgments} />
      <ListenLinks actions={listen.restActions} plays={listen.restPlays} />
      {highlights.length > 0 && (
        <ListenFor items={highlights.map((song) => ({ key: song.performance_id, title: song.title, url: song.listen_url, track: toPlayerTrack(song, showMeta) }))} queue={playableQueue} />
      )}
      {shows("setlist") && unit.setlist_disclosure !== "hidden" && unit.sets.length === 0 && unit.setlist_note && (
        <p className="coverage-note">{unit.setlist_note}</p>
      )}
      <Drawer tabs={tabs} initialOpen={initialOpen} />
      {((shows("sources") && unit.sources.length > 0) || (unit.follow_ups ?? []).length > 0) && (
        <footer className="unit-footer">
          {shows("sources") && <GoDeeper sources={unit.sources} />}
          <MoreAbout topics={unit.follow_ups} onFollowUp={onFollowUp} />
        </footer>
      )}
    </UnitFrame>
  );
}
