import { Component, type ErrorInfo, type ReactNode } from "react";
import { clearSavedHistory } from "./history-store";

// Catches an error thrown while drawing its children and shows the fallback
// in their place, so one bad card costs that card and not the page, and one
// bad page costs that page and not the app. Three sit in the app: around each
// card, around each page, and around everything.
type Props = {
  fallback: ReactNode | ((error: Error) => ReactNode);
  // When this changes the boundary tries its children again.
  resetKey?: unknown;
  // Named in the console so a caught error says where it was.
  name: string;
  children: ReactNode;
};

export class ErrorBoundary extends Component<Props, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: unknown) {
    return { error: error instanceof Error ? error : new Error(String(error)) };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`Deadbot could not draw ${this.props.name}.`, error, info.componentStack);
  }

  componentDidUpdate(previous: Props) {
    if (this.state.error && previous.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    const { fallback } = this.props;
    return typeof fallback === "function" ? fallback(error) : fallback;
  }
}

// The words a card carries, read without knowing what kind of card it is:
// its title and the sentences the model wrote for it. This is what stands in
// for a card that could not be drawn.
const TITLE_KEYS = ["title", "headline", "name", "song_title", "release_title", "venue_name", "person_name"];
const TEXT_KEYS = ["overview", "lead", "line", "text", "note", "notes", "message", "summary", "description", "caption", "why"];

export function cardWords(block: unknown): { title: string | null; lines: string[] } {
  if (!block || typeof block !== "object") return { title: null, lines: [] };
  const record = block as Record<string, unknown>;
  const said = (key: string) => (typeof record[key] === "string" && (record[key] as string).trim() ? (record[key] as string).trim() : null);
  const title = TITLE_KEYS.map(said).find(Boolean) ?? null;
  const lines = TEXT_KEYS.map(said).filter((line): line is string => Boolean(line) && line !== title);
  const paragraphs = Array.isArray(record.paragraphs) ? record.paragraphs.filter((item): item is string => typeof item === "string" && Boolean(item.trim())) : [];
  return { title, lines: [...lines, ...paragraphs] };
}

// A card that could not be drawn: its own words, plainly, or nothing.
export function CardFallback({ block }: { block: unknown }) {
  const { title, lines } = cardWords(block);
  if (!title && lines.length === 0) return null;
  return (
    <section className="typography-block card-fallback">
      {title && <p className="card-fallback-title">{title}</p>}
      {lines.map((line, index) => <p key={index}>{line}</p>)}
    </section>
  );
}

// The whole app could not be drawn. Reloading is the usual cure; when what
// is saved in this browser is the cause, clearing it is the other.
export function AppFallback() {
  return (
    <main className="app-crash" role="alert">
      <h1>Deadbot hit a problem showing this page.</h1>
      <p>Reloading usually fixes it. If it comes back, clearing the history saved in this browser will; the music and the library are not affected.</p>
      <div className="app-crash-actions">
        <button type="button" onClick={() => window.location.reload()}>Reload</button>
        <button
          type="button"
          onClick={() => {
            clearSavedHistory();
            window.location.assign("/");
          }}
        >
          Clear saved history and reload
        </button>
      </div>
    </main>
  );
}
