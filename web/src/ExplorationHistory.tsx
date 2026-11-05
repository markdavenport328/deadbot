import { isAsking, type ExplorationState } from "./exploration-state";
import "./WorkspaceShell.css";

// The visitor's explorations in order, with back and forward through them. A
// request in flight shows as its own row; so does one that did not finish.
export function ExplorationHistory({ state, onNavigate, onStop, onRetry, onNewChat, headingId }: {
  state: ExplorationState;
  onNavigate(index: number): void;
  onStop(): void;
  onRetry(): void;
  onNewChat(): void;
  headingId: string;
}) {
  const { entries, cursor, pending, startView } = state;
  const asking = isAsking(state);
  const sourceLabel = (source: string) => (source === "chip" ? "Chip" : "Typed");

  return (
    <div className="exploration-history">
      <div className="history-head">
        <h2 id={headingId}>Your explorations</h2>
        <div className="history-arrows">
          <button type="button" aria-label="Previous exploration" disabled={startView || cursor <= 0} onClick={() => onNavigate(cursor - 1)}>←</button>
          <button type="button" aria-label="Next exploration" disabled={cursor >= entries.length - 1} onClick={() => onNavigate(cursor + 1)}>→</button>
        </div>
      </div>
      <ol className="history-list" aria-labelledby={headingId}>
        {entries.map((entry, index) => [
          entry.root && index > 0 ? <li key={`${entry.id}-divider`} className="thread-divider">New thread</li> : null,
          <li key={entry.id}>
            <button
              type="button"
              className={index > cursor ? "history-row ahead" : "history-row"}
              aria-current={index === cursor && !startView ? "true" : undefined}
              onClick={() => onNavigate(index)}
            >
              <small>{index + 1} · {sourceLabel(entry.source)}</small>
              {entry.request}
            </button>
          </li>
        ])}
        {pending && (
          <li className={pending.error === null ? "history-pending" : "history-pending failed"}>
            <span>{pending.error === null ? "Asking" : "Didn't finish"} · {pending.question}</span>
            {pending.error === null
              ? <button type="button" onClick={onStop}>Stop</button>
              : <button type="button" onClick={onRetry}>Retry</button>}
          </li>
        )}
      </ol>
      <button type="button" className="history-new" disabled={asking} onClick={onNewChat}>New chat</button>
    </div>
  );
}
