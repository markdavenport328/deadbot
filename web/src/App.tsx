import { type FormEvent, type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import type { ExperienceBlock, ExperienceResponse, SourceReference } from "./types";

const suggestions = [
  "What did they play after Dark Star at Veneta?",
  "Show me the Veneta Sugaree and its chord source.",
  "Where can I watch the full Veneta show?"
];

function threadId(): string {
  const storageKey = "deadbot-thread-id";
  const existing = window.localStorage.getItem(storageKey);
  if (existing) return existing;
  const value = `web-${crypto.randomUUID()}`;
  window.localStorage.setItem(storageKey, value);
  return value;
}

function sourceFor(sources: SourceReference[], sourceId: string): SourceReference | undefined {
  return sources.find((source) => source.source_id === sourceId);
}

function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noreferrer">
      {children} <span aria-hidden="true">↗</span>
    </a>
  );
}

function MediaEmbed({ block }: { block: Extract<ExperienceBlock, { type: "media_link" }> }) {
  if (block.embed_kind === "youtube" && block.embed_id) {
    return (
      <iframe
        className="media-frame"
        src={`https://www.youtube-nocookie.com/embed/${block.embed_id}`}
        title={block.title}
        loading="lazy"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
        allowFullScreen
      />
    );
  }
  if (block.embed_kind === "spotify" && block.embed_id) {
    return (
      <iframe
        className="spotify-frame"
        src={`https://open.spotify.com/embed/${block.embed_id}`}
        title={block.title}
        loading="lazy"
        allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"
      />
    );
  }
  return null;
}

function Block({ block, sources }: { block: ExperienceBlock; sources: SourceReference[] }) {
  switch (block.type) {
    case "entity_card": {
      const source = sourceFor(sources, block.source_id);
      return (
        <article className="card entity-card">
          <p className="eyebrow">{block.entity_type}</p>
          <h2>{block.title}</h2>
          {block.subtitle && <p className="subtitle">{block.subtitle}</p>}
          {block.details.length > 0 && (
            <ul className="details">
              {block.details.map((detail) => <li key={detail}>{detail}</li>)}
            </ul>
          )}
          {source && <p className="source-label">{source.label}</p>}
        </article>
      );
    }
    case "resource_list":
      return (
        <section className="card resource-list">
          <p className="eyebrow">Sources</p>
          <h2>{block.title}</h2>
          <ul>
            {block.items.map((item) => (
              <li key={item.resource_id}>
                <ExternalLink href={item.url}>{item.title}</ExternalLink>
                <span>{item.resource_type} · {item.source_name}</span>
              </li>
            ))}
          </ul>
        </section>
      );
    case "media_link":
      return (
        <section className="card media-card">
          <p className="eyebrow">{block.provider}{block.is_official ? " · official" : ""}</p>
          <h2>{block.title}</h2>
          <MediaEmbed block={block} />
          <ExternalLink href={block.url}>Open on {block.provider}</ExternalLink>
        </section>
      );
    case "arrangement": {
      const source = sourceFor(sources, block.source_id);
      return (
        <section className="card arrangement-card">
          <p className="eyebrow">Source-specific arrangement</p>
          <h2>{block.title}</h2>
          {block.key_signature && <p className="subtitle">Key: {block.key_signature}</p>}
          {block.progressions.length > 0 && (
            <ul className="chords">
              {block.progressions.map((progression, index) => <li key={`${index}-${progression}`}>{progression}</li>)}
            </ul>
          )}
          {source?.url && <ExternalLink href={source.url}>Open the source</ExternalLink>}
        </section>
      );
    }
    case "provenance_note":
      return <aside className="provenance">{block.text}</aside>;
    case "gap_state":
      return <aside className="gap-state">{block.message}</aside>;
  }
}

export default function App() {
  const [question, setQuestion] = useState("");
  const [response, setResponse] = useState<ExperienceResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const activeThreadId = useMemo(threadId, []);
  const threadEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    threadEnd.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [loading, response]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || loading) return;
    setLoading(true);
    setError(null);
    try {
      const result = await fetch("/api/experience", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: trimmed, thread_id: activeThreadId })
      });
      if (!result.ok) {
        const body = await result.json().catch(() => null) as { detail?: string } | null;
        throw new Error(body?.detail ?? "Deadbot could not answer just now.");
      }
      setResponse(await result.json() as ExperienceResponse);
      setQuestion("");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Deadbot could not answer just now.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <header className="masthead">
        <a className="wordmark" href="/">Deadbot</a>
        <p>Grateful Dead knowledge, listening, and context.</p>
      </header>

      <div className="workspace">
        <aside className="conversation-pane" aria-label="Conversation">
          <div className="conversation-intro">
            <p className="eyebrow">Veneta 1972 pilot</p>
            <h1>Follow the thread.</h1>
            <p>Ask a question, then refine it. Deadbot retains this conversation as context.</p>
          </div>

          <section className="thread" aria-label="Deadbot conversation" aria-live="polite">
            {!response && (
              <div className="thread-empty">
                <p>Try a starting point:</p>
                {suggestions.map((suggestion) => (
                  <button key={suggestion} type="button" onClick={() => setQuestion(suggestion)} disabled={loading}>{suggestion}</button>
                ))}
              </div>
            )}
            {response?.conversation.map((turn, index) => (
              <article className={`message ${turn.role}`} key={`${turn.role}-${index}`}>
                <p>{turn.role === "user" ? "You" : "Deadbot"}</p>
                <div>{turn.text}</div>
              </article>
            ))}
            {loading && <article className="message assistant pending"><p>Deadbot</p><div>Looking through the library…</div></article>}
            <div ref={threadEnd} />
          </section>

          {error && <p className="error" role="alert">{error}</p>}

          <form className="composer" onSubmit={submit}>
            <label htmlFor="question">Ask a follow-up</label>
            <div className="question-row">
              <input
                id="question"
                placeholder="Ask about a song, show, source, or recording"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                disabled={loading}
              />
              <button type="submit" disabled={loading || !question.trim()}>{loading ? "Looking…" : "Send"}</button>
            </div>
          </form>
        </aside>

        <section className="content-pane" aria-live="polite" aria-label="Composed results">
          {response ? (
            <>
              <div className="content-heading">
                <p className="eyebrow">Composed from the latest turn</p>
                <h1>{response.title}</h1>
                <p>Explore the grounded details, media, and sources connected to this answer.</p>
              </div>
              <div className="block-grid">
                {response.blocks.map((block, index) => <Block key={`${block.type}-${index}`} block={block} sources={response.sources} />)}
              </div>
            </>
          ) : (
            <div className="content-empty">
              <p className="eyebrow">Composed results</p>
              <h1>Start with a question.</h1>
              <p>Your short answer will appear in the conversation. The related songs, shows, recordings, media, and source links will appear here.</p>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
