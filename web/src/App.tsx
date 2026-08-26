import { type FormEvent, type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import type { ExperienceBlock, ExperienceResponse, SourceReference } from "./types";

const suggestions = [
  "What did they play after Dark Star on 1972-08-27?",
  "Show me the Sugaree performance on 1972-08-27 and its chord source.",
  "Where can I watch the full 1972-08-27 show?"
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

function FollowUpButton({
  prompt,
  onFollowUp,
  children,
  className = "follow-up-button"
}: {
  prompt: string;
  onFollowUp: (prompt: string) => void;
  children: ReactNode;
  className?: string;
}) {
  return (
    <button type="button" className={`follow-up-button ${className}`} onClick={() => onFollowUp(prompt)} title={`Ask Deadbot: ${prompt}`}>
      {children} <span aria-hidden="true">↗</span>
    </button>
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

function Block({
  block,
  sources,
  onFollowUp
}: {
  block: ExperienceBlock;
  sources: SourceReference[];
  onFollowUp: (prompt: string) => void;
}) {
  switch (block.type) {
    case "entity_card": {
      return (
        <article className="card entity-card">
          <p className="eyebrow">{block.entity_type}</p>
          {block.follow_up ? (
            <FollowUpButton prompt={block.follow_up} onFollowUp={onFollowUp} className="card-title-link">
              <span>{block.title}</span>
            </FollowUpButton>
          ) : <h2>{block.title}</h2>}
          {block.subtitle && <p className="subtitle">{block.subtitle}</p>}
          {block.details.length > 0 && (
            <ul className="details">
              {block.details.map((detail) => <li key={detail}>{detail}</li>)}
            </ul>
          )}
        </article>
      );
    }
    case "show_setlist":
      return (
        <section className="card show-setlist">
          <p className="eyebrow">Setlist</p>
          <h2>{block.title}</h2>
          <div className="setlist-sections">
            {block.sets.map((set) => (
              <div className="setlist-section" key={set.label}>
                <p className="fact-label">{set.label}</p>
                <ol>
                  {set.songs.map((song) => (
                    <li key={song.performance_id}>
                      <FollowUpButton prompt={song.follow_up} onFollowUp={onFollowUp} className="list-item-follow-up">
                        <span>{song.title}</span>
                      </FollowUpButton>
                    </li>
                  ))}
                </ol>
              </div>
            ))}
          </div>
        </section>
      );
    case "recording_list":
      return (
        <section className="card recording-list">
          <p className="eyebrow">Listening</p>
          <h2>{block.title}</h2>
          <ul>
            {block.items.map((item) => (
              <li key={item.recording_id}>
                <ExternalLink href={item.url}>{item.title}</ExternalLink>
                <span>{item.source_type}{item.archive_identifier ? ` · ${item.archive_identifier}` : ""}</span>
              </li>
            ))}
          </ul>
        </section>
      );
    case "performer_list":
      return (
        <section className="card performer-list">
          <p className="eyebrow">Lineup</p>
          <h2>{block.title}</h2>
          <ul>
            {block.items.map((item) => (
              <li key={`${item.person_id}-${item.role}`}>
                <FollowUpButton prompt={item.follow_up} onFollowUp={onFollowUp} className="inline-follow-up">
                  <strong>{item.name}</strong>
                </FollowUpButton>
                <span className="performer-role">{item.role === "guest" ? "Guest" : "Performer"}</span>
                <span>{item.instruments.join(", ")}</span>
              </li>
            ))}
          </ul>
        </section>
      );
    case "equipment_list":
      return (
        <section className="card equipment-list">
          <p className="eyebrow">Equipment</p>
          <h2>{block.title}</h2>
          <ul>
            {block.items.map((item) => (
              <li key={`${item.equipment_id}-${item.usage_context}-${item.evidence}`}>
                <FollowUpButton prompt={item.follow_up} onFollowUp={onFollowUp} className="inline-follow-up">
                  <strong>{item.name}</strong>
                </FollowUpButton>
                <span>{[item.manufacturer, item.model].filter(Boolean).join(" · ")}</span>
                <span>{item.usage_context}{item.claim_type === "show" ? " · specific show evidence" : " · dated range evidence"}</span>
                <ExternalLink href={item.source_url}>Source note</ExternalLink>
              </li>
            ))}
          </ul>
        </section>
      );
    case "song_overview":
      return (
        <section className="card song-overview">
          <p className="eyebrow">Song facts</p>
          <h2>{block.title}</h2>
          <dl className="song-facts">
            {block.original_artist && (
              <div>
                <dt>Original artist</dt>
                <dd>{block.original_artist}</dd>
              </div>
            )}
            <div>
              <dt>Known performances</dt>
              <dd>{block.known_performance_count}</dd>
            </div>
          </dl>
          {block.credits.length > 0 && (
            <div className="song-credits">
              <p className="fact-label">Credits</p>
              <ul>
                {block.credits.map((credit) => (
                  <li key={`${credit.person_id}-${credit.role}`}>
                    {credit.follow_up ? (
                      <FollowUpButton prompt={credit.follow_up} onFollowUp={onFollowUp} className="inline-follow-up">
                        <strong>{credit.name}</strong>
                      </FollowUpButton>
                    ) : <strong>{credit.name}</strong>}
                    <span>{credit.role}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      );
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
    case "credit_list":
      return (
        <section className="card credit-list">
          <p className="eyebrow">Composition</p>
          <h2>{block.title}</h2>
          <ul>
            {block.items.map((item) => (
              <li key={`${item.person_id}-${item.role}`}>
                {item.follow_up ? (
                  <FollowUpButton prompt={item.follow_up} onFollowUp={onFollowUp} className="inline-follow-up">
                    <strong>{item.name}</strong>
                  </FollowUpButton>
                ) : <strong>{item.name}</strong>}
                <span>{item.role}</span>
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
    case "performance_list":
      return (
        <section className="card performance-list">
          <p className="eyebrow">Canonical performance evidence</p>
          <h2>{block.title}</h2>
          <p className="subtitle">{block.known_count} known performance{block.known_count === 1 ? "" : "s"}</p>
          <ul>
            {block.items.map((item) => (
              <li key={item.performance_id}>
                <FollowUpButton prompt={item.follow_up} onFollowUp={onFollowUp} className="list-item-follow-up">
                  <strong>{item.show_label}</strong>
                </FollowUpButton>
                {(item.set_label || item.position_in_set) && <span>{item.set_label}{item.position_in_set ? ` · #${item.position_in_set}` : ""}</span>}
              </li>
            ))}
          </ul>
        </section>
      );
    case "performance_extremes": {
      const endpoint = (label: string, item: typeof block.first) => (
        <div className="performance-endpoint" key={label}>
          <p className="fact-label">{label}</p>
          <FollowUpButton prompt={item.follow_up} onFollowUp={onFollowUp} className="list-item-follow-up">
            <strong>{item.show_label}</strong>
          </FollowUpButton>
          {(item.set_label || item.position_in_set) && (
            <span>{item.set_label}{item.position_in_set ? ` · #${item.position_in_set}` : ""}</span>
          )}
        </div>
      );
      return (
        <section className="card performance-extremes">
          <p className="eyebrow">Performance history</p>
          <h2>{block.title}</h2>
          <div className="performance-endpoints">
            {endpoint("First", block.first)}
            {endpoint("Last", block.last)}
          </div>
        </section>
      );
    }
    case "coverage":
      return (
        <aside className="coverage-card">
          <p className="eyebrow">Library coverage</p>
          <h2>{block.title}</h2>
          <p>{block.message}</p>
        </aside>
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
          <FollowUpButton prompt={`Tell me more about ${block.title}.`} onFollowUp={onFollowUp}>
            Ask about this arrangement
          </FollowUpButton>
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
  const questionInput = useRef<HTMLTextAreaElement>(null);

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
        body: JSON.stringify({ question: trimmed, thread_id: activeThreadId, conversation: response?.conversation ?? [] })
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

  function chooseFollowUp(prompt: string) {
    setQuestion(prompt);
    questionInput.current?.focus();
  }

  return (
    <main className="app-shell">
      <div className="workspace">
        <aside className="conversation-pane" aria-label="Conversation">
          <header className="masthead">
            <a className="wordmark" href="/">Deadbot</a>
            <p>Grateful Dead knowledge, listening, and context</p>
          </header>

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
            <div className="question-row">
              <textarea
                id="question"
                aria-label="Question"
                ref={questionInput}
                rows={3}
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
                <h1>{response.title}</h1>
              </div>
              {response.layout.map((section, sectionIndex) => (
                <section className={`layout-section ${section.region}`} key={`${section.region}-${sectionIndex}`}>
                  <div className="block-grid">
                    {section.block_indexes.map((index) => {
                      const block = response.blocks[index];
                      return block ? (
                        <Block
                          key={`${block.type}-${index}`}
                          block={block}
                          sources={response.sources}
                          onFollowUp={chooseFollowUp}
                        />
                      ) : null;
                    })}
                  </div>
                </section>
              ))}
            </>
          ) : (
            <div className="content-empty">
              <p className="eyebrow">Composed results</p>
              <h1>Start with a question.</h1>
              <p>Your short answer will appear in the conversation. Related songs, shows, recordings, and media will appear here.</p>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
