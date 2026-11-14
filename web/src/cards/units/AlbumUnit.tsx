import { useContext } from "react";
import { type AlbumUnitBlock } from "../../types";
import { CardHeading, Drawer, MoreAbout, type DrawerTab } from "../components";
import { type FollowUp } from "../../core/ask-request";
import { SpotifyPanelEmbed, SpotifyTextButton, useSpotifyPanel } from "../spotify-embed";
import { ClampText } from "../listening";
import { albumTrack } from "../AlbumNights";
import { ListenControl } from "../listen-control";
import { formatReleaseDate, formatReleaseType, capitalize } from "../../core/format";
import { renderInline } from "../inline";
import { ListenActionList, CardHead, ListenFor, IdRow, Meta, PeopleList, TrackList, GoDeeper } from "../parts";
import { albumSpotify, RowSpotifyContext, UnitFrame, albumQueue, CriteriaTable } from "./shared";
import { sameHeading } from "../headings";

type PersonnelGroup = {
  person_id: string;
  name: string;
  instruments: string[];
  extraRole: string | null;
};

function groupPersonnel(personnel: AlbumUnitBlock["personnel"]): PersonnelGroup[] {
  const groups = new Map<string, PersonnelGroup>();
  for (const credit of personnel) {
    let group = groups.get(credit.person_id);
    if (!group) {
      group = { person_id: credit.person_id, name: credit.name, instruments: [], extraRole: null };
      groups.set(credit.person_id, group);
    }
    if (credit.instrument && !group.instruments.includes(credit.instrument)) {
      group.instruments.push(credit.instrument);
    }
    if (credit.role && credit.role !== "performer" && !group.extraRole) {
      group.extraRole = credit.role;
    }
  }
  return [...groups.values()];
}

export function AlbumUnit({
  block,
  criteria,
  soleUnit,
  onFollowUp,
  inRow = false
}: {
  block: AlbumUnitBlock;
  criteria: string[];
  soleUnit: boolean;
  onFollowUp: FollowUp;
  inRow?: boolean;
}) {
  const openFacets = (block.emphasis === "primary" && soleUnit) || inRow;
  // One primary way to hear the record: its tape in-page, or else its
  // streaming album. A row already shows that control in its header.
  const queue = albumQueue(block);
  const primary = queue.length > 0 ? { play: { start: queue[0], queue }, label: `Play ${block.release_title?.trim() || block.title}` } : null;
  const spotify = albumSpotify(block);
  const rowPanel = useContext(RowSpotifyContext);
  const ownPanel = useSpotifyPanel();
  const spotifyPanel = inRow && rowPanel ? rowPanel : ownPanel;
  const otherListen = (primary ? block.listen : inRow ? block.listen.slice(1) : block.listen).filter((action) => action !== spotify?.action);
  const highlightedTracks = block.tracks.filter((track) => track.highlighted);
  const personnel = groupPersonnel(block.personnel);
  const typeLabel = block.artist_name && block.artist_name !== "Grateful Dead" ? `Album · ${block.artist_name}` : "Album";
  const releaseLong = formatReleaseDate(block.release_date);

  const tabs: DrawerTab[] = [];
  if (block.tracks.length > 0) {
    tabs.push({ id: "tracks", label: "Tracklist", count: block.tracks.length, content: <TrackList tracks={block.tracks} /> });
  }
  if (personnel.length > 0) {
    tabs.push({
      id: "personnel",
      label: "Personnel",
      count: personnel.length,
      content: (
        <PeopleList
          people={personnel.map((person) => ({
            key: person.person_id,
            name: person.name,
            detail: [person.instruments.join(", "), person.extraRole ? capitalize(person.extraRole) : null].filter(Boolean).join(" · ")
          }))}
        />
      )
    });
  }
  const initialOpen = openFacets && tabs.some((tab) => tab.id === "tracks") ? "tracks" : null;
  // Two authors share the top of the card, as on the show card. The library
  // names the record: type, then its title, kind and release date in one
  // identity zone. When the model wrote a headline of its own, it opens the
  // overview beneath that zone; otherwise the record's title is the headline.
  const recordName = block.release_title?.trim() || block.title;
  const modelHeadline = block.title.trim() && !sameHeading(block.title, recordName) ? block.title.trim() : "";
  const kindLine = formatReleaseType(block.release_type);

  return (
    <UnitFrame inRow={inRow} className={`album-unit emphasis-${block.emphasis}`}>
      {inRow ? (
        modelHeadline ? <CardHeading className="overview">{modelHeadline}</CardHeading> : null
      ) : modelHeadline ? (
        <>
          <IdRow type={typeLabel} />
          <CardHead primary={primary} spotify={spotify && !inRow ? { panel: spotifyPanel, label: spotify.action.label } : null}>
            <div className="identity">
              <p className="identity-name">{recordName}</p>
              <Meta parts={[kindLine, releaseLong ? `Released ${releaseLong}` : null]} />
            </div>
            <CardHeading className="overview">{modelHeadline}</CardHeading>
          </CardHead>
        </>
      ) : (
        <>
          <IdRow type={typeLabel} when={releaseLong ? `Released ${releaseLong}` : null} />
          <CardHead primary={primary} spotify={spotify && !inRow ? { panel: spotifyPanel, label: spotify.action.label } : null}>
            <CardHeading>{recordName}</CardHeading>
            <Meta parts={[kindLine]} />
          </CardHead>
        </>
      )}
      {block.note && !inRow && <ClampText className="unit-note">{renderInline(block.note)}</ClampText>}
      <CriteriaTable criteria={criteria} judgments={block.judgments} />
      {spotify && !inRow && <SpotifyPanelEmbed panel={spotifyPanel} embedId={spotify.embedId} title={`${recordName} on Spotify`} height={352} />}
      {spotify && (
        <ul className="listen-links" aria-label="Spotify">
          {primary && (
            <li>
              <SpotifyTextButton panel={spotifyPanel} label="Listen on Spotify" name={`Listen to ${recordName} on Spotify`} />
            </li>
          )}
          <li>
            <ListenControl url={spotify.action.url} label="Open in Spotify" />
          </li>
        </ul>
      )}
      <ListenActionList actions={otherListen} />
      {highlightedTracks.length > 0 && (
        <ListenFor items={highlightedTracks.map((track) => ({ key: String(track.track_number), title: track.title, url: track.listen_url, track: albumTrack(track) }))} />
      )}
      <Drawer tabs={tabs} initialOpen={initialOpen} />
      {(block.sources.length > 0 || (block.follow_ups ?? []).length > 0) && (
        <footer className="unit-footer">
          <GoDeeper sources={block.sources} />
          <MoreAbout topics={block.follow_ups} onFollowUp={onFollowUp} />
        </footer>
      )}
    </UnitFrame>
  );
}
