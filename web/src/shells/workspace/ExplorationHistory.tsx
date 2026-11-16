import { isAsking, type Entry, type ExplorationState, type Pending } from "../../core/exploration-state";
import { threadStarts } from "../../core/history-store";
import { PenIcon } from "../../core/side-panel";
import "./WorkspaceShell.css";

// The visitor's explorations, saved in this browser: New chat at the top,
// then Recent, one thread per question asked fresh (newest first), each
// opening with that question and its follow-ups indented beneath it in the
// order they were asked. A row reopens its page without asking again. A
// request in flight shows where it will land; so does one that did not
// finish. Clear, on the Recent line, empties the list, with Undo for a few
// seconds.
export function ExplorationHistory({ state, onNavigate, onStop, onRetry, onNewChat, onClear, onUndo, cleared = false, headingId }: {
  state: ExplorationState;
  onNavigate(index: number): void;
  onStop(): void;
  onRetry(): void;
  onNewChat(): void;
  onClear?(): void;
  onUndo?(): void;
  cleared?: boolean;
  headingId: string;
}) {
  const { entries, cursor, pending, startView } = state;
  const asking = isAsking(state);
  const starts = threadStarts(entries);
  const threads = starts.map((start, index) => ({ start, end: starts[index + 1] ?? entries.length }));

  function pendingRow(item: Pending) {
    return (
      <li key="pending" className={item.error === null ? "history-pending" : "history-pending failed"}>
        <span>{item.error === null ? "Asking" : "Didn't finish"} · {item.question}</span>
        {item.error === null
          ? <button type="button" onClick={onStop}>Stop</button>
          : <button type="button" onClick={onRetry}>Retry</button>}
      </li>
    );
  }

  function row(entry: Entry, index: number, followUp: boolean) {
    return (
      <li key={entry.id}>
        <button
          type="button"
          className={["history-row", followUp ? "follow-up" : null, index > cursor ? "ahead" : null].filter(Boolean).join(" ")}
          aria-current={index === cursor && !startView ? "true" : undefined}
          onClick={() => onNavigate(index)}
        >
          {followUp && <span className="visually-hidden">Follow-up: </span>}
          {entry.request}
        </button>
      </li>
    );
  }

  const freshPending = pending && pending.baseEntryId === null ? pending : null;
  return (
    <div className="exploration-history">
      <button type="button" className="history-new" disabled={asking} onClick={onNewChat}><PenIcon />New chat</button>
      <div className="history-head">
        <h2 id={headingId}>Recent</h2>
        {(entries.length > 0 || cleared) && onClear && (
          cleared ? (
            <button type="button" className="history-clear" onClick={onUndo} aria-label="Undo clearing history">Undo</button>
          ) : (
            <button type="button" className="history-clear" disabled={asking} onClick={onClear} aria-label="Clear history">Clear</button>
          )
        )}
      </div>
      {entries.length === 0 && !pending ? (
        <p className="history-empty">{cleared ? "History cleared." : "Your questions will gather here."}</p>
      ) : (
        <ul className="history-threads" aria-labelledby={headingId}>
          {freshPending && <li className="history-thread">{<ol className="history-list">{pendingRow(freshPending)}</ol>}</li>}
          {threads.slice().reverse().map(({ start, end }) => {
            const inThread = (id: string | null) => id !== null && entries.slice(start, end).some((entry) => entry.id === id);
            return (
              <li key={entries[start].id} className="history-thread">
                <ol className="history-list">
                  {entries.slice(start, end).map((entry, offset) => row(entry, start + offset, offset > 0))}
                  {pending && pending.baseEntryId !== null && inThread(pending.baseEntryId) && pendingRow(pending)}
                </ol>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
