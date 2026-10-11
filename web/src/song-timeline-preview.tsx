// A dev-only page for the song timeline, served by `npm run dev` at
// /song-timeline-preview.html and left out of the production build. It reads
// the Terrapin fixtures, so it needs no API; Ask is shown on the page instead
// of starting a turn. Phase 2 registers a visual fixture and retires this.
import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import card from "./fixtures/song-timeline-terrapin.json";
import years from "./fixtures/song-timeline-terrapin-years.json";
import { PlayerProvider, formatClockTime, usePlayer } from "./player";
import { SongTimeline } from "./SongTimeline";
import type { SongTimelineData, SongYearDetail, TimelineFocus } from "./song-timeline-types";
import "./styles.css";

const data = card as unknown as SongTimelineData;
const yearDetails = years as unknown as Record<string, SongYearDetail>;

function fetchYear(_songId: string, year: number): Promise<SongYearDetail> {
  const detail = yearDetails[String(year)];
  return detail ? Promise.resolve(detail) : Promise.reject(new Error(`The ${year} list is not in the fixture.`));
}

function NowPlaying() {
  const player = usePlayer();
  const track = player.currentTrack;
  if (!track) return null;
  return (
    <div className="preview-player" role="status">
      <button type="button" onClick={player.toggle}>
        {player.status === "playing" ? "Pause" : "Play"}
      </button>
      <span>
        {track.title} · {track.showDate} · {track.venueName}
      </span>
      <span>
        {formatClockTime(player.position)} / {formatClockTime(player.duration)}
      </span>
      {player.hasNext && (
        <button type="button" onClick={player.next}>
          Next
        </button>
      )}
    </div>
  );
}

function Preview() {
  const [asked, setAsked] = useState<{ question: string; focus: TimelineFocus }[]>([]);
  return (
    <PlayerProvider>
      <main className="preview-page">
        <p className="preview-note">Preview: real library data; the stops, open year and year questions stand in for the model's choices.</p>
        <h2 className="preview-heading">The song's life on stage</h2>
        <section className="card song-overview preview-card">
          <h3>{data.performance_count} performances across the Dead's career</h3>
          <SongTimeline data={data} fetchYear={fetchYear} onAsk={(question, focus) => setAsked((items) => [...items, { question, focus }])} />
        </section>
        {asked.length > 0 && (
          <section className="preview-asked" aria-label="Questions asked">
            {asked.map((item, index) => (
              <p key={index}>
                <strong>{item.question}</strong> <code>{JSON.stringify(item.focus)}</code>
              </p>
            ))}
          </section>
        )}
      </main>
      <NowPlaying />
    </PlayerProvider>
  );
}

const style = document.createElement("style");
style.textContent = `
  .preview-page { width: min(980px, calc(100% - 2rem)); margin: 0 auto; padding: 2rem 0 6rem; display: flex; flex-direction: column; gap: 1.25rem; }
  .preview-note { margin: 0; color: var(--quiet); font-size: 0.85rem; }
  .preview-heading { color: var(--cream); font-size: 1.6rem; }
  .preview-card { display: flex; flex-direction: column; gap: 1.25rem; }
  .preview-card h3 { color: var(--cream); font-size: 1.65rem; }
  .preview-asked { color: var(--muted); font-size: 0.85rem; }
  .preview-asked code { color: var(--quiet); word-break: break-word; }
  .preview-player { position: fixed; left: 0; right: 0; bottom: 0; display: flex; flex-wrap: wrap; gap: 1rem; align-items: center; padding: 0.75rem 1.5rem; background: var(--bar-scrim); border-top: 1px solid var(--hair); color: var(--text); font-size: 0.85rem; }
  .preview-player button { background: var(--listen); color: var(--listen-ink); border: 0; border-radius: 999px; padding: 0.35rem 0.9rem; font-weight: 600; }
`;
document.head.appendChild(style);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Preview />
  </StrictMode>
);
