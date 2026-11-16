import { usePlayer, formatClockTime, type PlayerTrack } from "../player/player";
import { AddToQueue, ListenControl } from "./listen-control";
import { type SetlistSections, type SetlistSongType, type ShowMeta, toPlayerTrack } from "./parts";
import { PlayPauseIcon } from "../player/icons";

// One playable setlist row: a 44px round play button at left with + beside
// it (adds the track to the queue), the title
// (still a listening link when the library has one), and a right-aligned
// duration. Segue rows carry a muted " >" and a thin connector down to the
// next row's button; the current track's row gets a faint gold wash and a
// progress line along its bottom edge.
function SetlistRow({
  song,
  track,
  isCurrent,
  isPlaying,
  isLoading,
  isError,
  position,
  duration,
  onPlay
}: {
  song: SetlistSongType;
  track: PlayerTrack | null;
  isCurrent: boolean;
  isPlaying: boolean;
  isLoading: boolean;
  isError: boolean;
  position: number;
  duration: number;
  onPlay: () => void;
}) {
  const className = [
    song.highlighted ? "hi" : null,
    isCurrent ? "current" : null,
    song.segue_into_next ? "segue" : null,
    isError ? "errored" : null
  ]
    .filter(Boolean)
    .join(" ");
  const progressPct = isCurrent && duration > 0 ? Math.min(100, (position / duration) * 100) : 0;
  const playLabel = !track ? `No recording for ${song.title}` : isError ? `Retry ${song.title}` : `${isCurrent && isPlaying ? "Pause" : "Play"} ${song.title}`;
  return (
    <li className={className || undefined} role="listitem">
      <div className="row-play-cell">
        <button
          type="button"
          className={`row-play${isCurrent ? " current" : ""}${track ? "" : " disabled"}${isError ? " errored" : ""}`}
          onClick={() => {
            if (isLoading) return;
            onPlay();
          }}
          disabled={!track}
          aria-busy={isLoading}
          aria-label={playLabel}
          data-tip={!track ? undefined : isError ? "Try again" : isCurrent && isPlaying ? "Pause" : "Play now"}
        >
          <PlayPauseIcon playing={isCurrent && isPlaying} />
        </button>
        {track ? <AddToQueue tracks={[track]} name={song.title} variant="round" /> : <span className="queue-add-space" aria-hidden="true" />}
      </div>
      <span className="row-title">
        {/* The row's own button plays the track; the title leaves the site only for another destination. */}
        <ListenControl url={song.listen_url} label={song.title} track={track} playsElsewhere />
        {song.segue_into_next && (
          <span className="segue-mark" aria-hidden="true">
            {" "}
            &gt;
          </span>
        )}
      </span>
      <span className="row-duration">{track || song.duration_seconds ? formatClockTime(song.duration_seconds) : "—"}</span>
      {isCurrent && <span className="row-progress" style={{ width: `${progressPct}%` }} aria-hidden="true" />}
    </li>
  );
}

// The setlist panel: one column per set, numbering continuing across sets
// (Set 2 starts at 9 when Set 1 has 8 songs). Clicking a row's play button
// plays that track and queues the rest of that set (its own playable songs,
// in order) after it.
export function SetlistPanel({ sets, showMeta }: { sets: SetlistSections; showMeta: ShowMeta }) {
  const player = usePlayer();
  let runningCount = 0;
  return (
    <div className="setlist-panel">
      {sets.map((set) => {
        const start = runningCount + 1;
        runningCount += set.songs.length;
        const setTracks = set.songs.map((song) => toPlayerTrack(song, showMeta));
        return (
          <div key={set.label}>
            <span className="k">{set.label}</span>
            <ol className="setlist-rows" start={start} role="list">
              {set.songs.map((song, index) => {
                const track = setTracks[index];
                const isCurrent = Boolean(track && player.currentTrack?.id === track.id);
                return (
                  <SetlistRow
                    key={song.performance_id}
                    song={song}
                    track={track}
                    isCurrent={isCurrent}
                    isPlaying={isCurrent && player.status === "playing"}
                    isLoading={isCurrent && player.status === "loading"}
                    isError={isCurrent && player.status === "error"}
                    position={player.position}
                    duration={player.duration}
                    onPlay={() => {
                      if (!track) return;
                      if (isCurrent) {
                        if (player.status === "playing") player.pause();
                        else if (player.status === "error") player.retry();
                        else player.toggle();
                        return;
                      }
                      const queue = setTracks.slice(index).filter((item): item is PlayerTrack => item !== null);
                      player.play(track, queue);
                    }}
                  />
                );
              })}
            </ol>
          </div>
        );
      })}
    </div>
  );
}
