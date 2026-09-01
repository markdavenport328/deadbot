import { type FormEvent, type KeyboardEvent, type ReactNode, useEffect, useRef, useState } from "react";
import type { ExperienceBlock, ExperienceResponse, SourceReference } from "./types";

const suggestions = [
  "Was Branford on the whole 1991-09-10 Madison Square Garden show, and where should I listen for him?",
  "What are the chords to Sugaree?",
  "What did they play after Dark Star on 1972-08-27?"
];

const modeLabels: Record<ExperienceResponse["mode"], string> = {
  quick_fact: "Answer",
  performance: "Performance guide",
  show: "Show guide",
  listening: "Listening guide",
  comparison: "Comparison",
  research: "Research desk",
  musician: "Musician’s reference",
  gap: "Library note"
};

const regionLabels: Partial<Record<"primary" | "supporting" | "context" | "media", string>> = {
  supporting: "Keep exploring",
  context: "Details and context",
  media: "Listen and watch"
};

function createThreadId(): string {
  return `web-${crypto.randomUUID()}`;
}

async function refreshIfServerChanged(): Promise<void> {
  const result = await fetch("/api/health", { cache: "no-store" });
  if (!result.ok) return;
  const health = await result.json() as { git_commit?: string };
  const current = health.git_commit;
  if (!current || current === "unknown") return;
  const storageKey = "deadbot-server-version";
  const previous = sessionStorage.getItem(storageKey);
  sessionStorage.setItem(storageKey, current);
  if (previous && previous !== current) window.location.reload();
}

function sourceFor(sources: SourceReference[], sourceId: string): SourceReference | undefined {
  return sources.find((source) => source.source_id === sourceId);
}

function dedupeSources(sources: SourceReference[]): SourceReference[] {
  const seen = new Set<string>();
  const result: SourceReference[] = [];
  for (const source of sources) {
    const key = `${source.label}|${source.url ?? ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(source);
  }
  return result;
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
  className = ""
}: {
  prompt: string;
  onFollowUp: (prompt: string) => void;
  children: ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      className={className ? `follow-up-button ${className}` : "follow-up-button"}
      onClick={() => onFollowUp(prompt)}
      title={`Ask Deadbot: ${prompt}`}
    >
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
    case "show_selection":
      return (
        <section className="card show-selection">
          <p className="eyebrow">{block.selection_type}</p>
          <h2>{block.title}</h2>
          <p className="subtitle">Selected by {block.selector_name}</p>
          <ol className="show-selection-list">
            {block.items.map((item) => (
              <li key={item.show_id}>
                <FollowUpButton prompt={item.follow_up} onFollowUp={onFollowUp} className="list-item-follow-up">
                  <span>{item.show_date} · {item.venue_name}</span>
                </FollowUpButton>
                {item.location && <span>{item.location}</span>}
              </li>
            ))}
          </ol>
          <p className="coverage-note">{block.coverage_note}</p>
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
    case "guest_appearance_list":
      return (
        <section className="card guest-appearance-list">
          <p className="eyebrow">Guest appearances</p>
          <h2>{block.person_name}</h2>
          <p className="subtitle">
            {block.known_show_count} documented show{block.known_show_count === 1 ? "" : "s"}
          </p>
          <ol>
            {block.items.map((item) => (
              <li key={item.show_id}>
                <FollowUpButton prompt={item.follow_up} onFollowUp={onFollowUp} className="list-item-follow-up">
                  <strong>{item.show_date}{item.venue_name ? ` · ${item.venue_name}` : ""}</strong>
                </FollowUpButton>
                <span>{[item.location, item.instruments.join(", "), item.participation_scope].filter(Boolean).join(" · ")}</span>
              </li>
            ))}
          </ol>
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
                {item.context_note && <p>{item.context_note}</p>}
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
    case "comparison_strip":
      return (
        <section className="card comparison-strip">
          <p className="eyebrow">Performance history</p>
          <h2>{block.title}</h2>
          <p className="subtitle">
            {block.known_count} known performance{block.known_count === 1 ? "" : "s"} · one representative per year
          </p>
          <ol className="comparison-track" aria-label="Selected performances by year">
            {block.items.map((item) => (
              <li className="comparison-stop" key={item.performance_id}>
                <p className="comparison-year">{item.year}</p>
                <FollowUpButton prompt={item.follow_up} onFollowUp={onFollowUp} className="list-item-follow-up">
                  <strong>{item.show_label}</strong>
                </FollowUpButton>
                {(item.set_label || item.position_in_set) && (
                  <span className="comparison-placement">
                    {item.set_label}{item.position_in_set ? ` · #${item.position_in_set}` : ""}
                  </span>
                )}
              </li>
            ))}
          </ol>
          <p className="coverage-note">{block.coverage_note}</p>
        </section>
      );
    case "performance_spine":
      return (
        <section className="card performance-spine">
          <p className="eyebrow">Performance context</p>
          <h2>{block.title}</h2>
          <p className="subtitle">{block.show_label}{block.set_label ? ` · ${block.set_label}` : ""}{block.position_in_set ? ` · #${block.position_in_set}` : ""}</p>
          <div className="set-thread" aria-label="Adjacent songs in the set">
            <div>
              <p className="fact-label">Before</p>
              {block.previous ? (
                <FollowUpButton prompt={block.previous.follow_up} onFollowUp={onFollowUp} className="list-item-follow-up">
                  {block.previous.title}
                </FollowUpButton>
              ) : <span className="thread-boundary">Set opener</span>}
            </div>
            <div className="current-performance" aria-label="Current performance">This performance</div>
            <div>
              <p className="fact-label">After</p>
              {block.next ? (
                <FollowUpButton prompt={block.next.follow_up} onFollowUp={onFollowUp} className="list-item-follow-up">
                  {block.next.title}
                </FollowUpButton>
              ) : <span className="thread-boundary">Set closer</span>}
            </div>
          </div>
        </section>
      );
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
          <dl className="arrangement-facts">
            {block.key_signature && <div><dt>Documented key</dt><dd>{block.key_signature}</dd></div>}
            <div><dt>Scope</dt><dd>{block.arrangement_scope.replaceAll("-", " ")}</dd></div>
            {block.capo && <div><dt>Capo</dt><dd>{block.capo}</dd></div>}
            {block.tuning && <div><dt>Tuning</dt><dd>{block.tuning}</dd></div>}
          </dl>
          {block.notes && <p className="arrangement-note">{block.notes}</p>}
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
    case "arrangement_search":
      return (
        <section className="card arrangement-search">
          <p className="eyebrow">Musician’s reference</p>
          <h2>{block.title}</h2>
          <p className="arrangement-note">{block.coverage_note}</p>
          <ul>
            {block.items.map((item) => (
              <li key={item.arrangement_id}>
                <FollowUpButton prompt={item.follow_up} onFollowUp={onFollowUp} className="inline-follow-up">
                  <strong>{item.title}</strong>
                </FollowUpButton>
                <span>{item.arrangement_scope.replaceAll("-", " ")} · documented key {item.key_signature}</span>
                <ExternalLink href={item.url}>{item.resource_title}</ExternalLink>
                <span>{item.source_name}</span>
              </li>
            ))}
          </ul>
        </section>
      );
    case "editorial":
      if (block.presentation === "narrative") return (
        <section className="editorial-block narrative-block">
          {block.eyebrow && <p className="eyebrow">{block.eyebrow}</p>}
          {block.title && <h2>{block.title}</h2>}
          {block.paragraphs.map((paragraph, index) => <p key={index}>{paragraph}</p>)}
        </section>
      );
      if (block.presentation === "fact_grid") return (
        <section className="editorial-block fact-grid-block">
          {block.eyebrow && <p className="eyebrow">{block.eyebrow}</p>}
          {block.title && <h2>{block.title}</h2>}
          <dl>
            {block.items.map((item, index) => (
              <div key={`${item.marker ?? item.title}-${index}`}>
                <dt>{item.marker ?? item.title}</dt>
                <dd>
                  {item.follow_up ? (
                    <FollowUpButton prompt={item.follow_up} onFollowUp={onFollowUp}>{item.value ?? item.title}</FollowUpButton>
                  ) : item.value ?? item.title}
                </dd>
                {item.detail && <dd className="fact-detail">{item.detail}</dd>}
              </div>
            ))}
          </dl>
        </section>
      );
      return (
        <section className="editorial-block timeline-block">
          {block.eyebrow && <p className="eyebrow">{block.eyebrow}</p>}
          {block.title && <h2>{block.title}</h2>}
          <ol>
            {block.items.map((item, index) => (
              <li key={`${item.marker ?? item.title}-${index}`}>
                {item.marker && <span className="timeline-marker">{item.marker}</span>}
                <strong>
                  {item.follow_up ? (
                    <FollowUpButton prompt={item.follow_up} onFollowUp={onFollowUp}>{item.title}</FollowUpButton>
                  ) : item.title}
                </strong>
                {item.detail && <span>{item.detail}</span>}
              </li>
            ))}
          </ol>
        </section>
      );
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
  const [activeThreadId, setActiveThreadId] = useState(createThreadId);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [pendingStartsFresh, setPendingStartsFresh] = useState(false);
  const threadEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    threadEnd.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [loading, pendingQuestion, response]);

  useEffect(() => {
    void refreshIfServerChanged();
    const check = window.setInterval(() => void refreshIfServerChanged(), 60_000);
    return () => window.clearInterval(check);
  }, []);

  async function askQuestion(nextQuestion?: string, { fresh = false }: { fresh?: boolean } = {}) {
    const trimmed = (nextQuestion ?? question).trim();
    if (!trimmed || loading) return;
    const requestThreadId = fresh ? createThreadId() : activeThreadId;
    const conversation = fresh ? [] : response?.conversation ?? [];
    if (fresh) {
      setActiveThreadId(requestThreadId);
      setResponse(null);
    }
    setPendingQuestion(trimmed);
    setPendingStartsFresh(fresh);
    setQuestion("");
    setLoading(true);
    setError(null);
    try {
      const result = await fetch("/api/experience", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: trimmed, thread_id: requestThreadId, conversation })
      });
      if (!result.ok) {
        const body = await result.json().catch(() => null) as { detail?: string } | null;
        throw new Error(body?.detail ?? "Deadbot could not answer just now.");
      }
      setResponse(await result.json() as ExperienceResponse);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Deadbot could not answer just now.");
    } finally {
      setLoading(false);
      setPendingQuestion(null);
      setPendingStartsFresh(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await askQuestion();
  }

  function chooseFollowUp(prompt: string) {
    void askQuestion(prompt);
  }

  function startNewChat() {
    if (loading) return;
    setActiveThreadId(createThreadId());
    setResponse(null);
    setError(null);
    setQuestion("");
  }

  const visibleConversation = pendingQuestion
    ? [
        ...(pendingStartsFresh ? [] : response?.conversation ?? []),
        { role: "user" as const, text: pendingQuestion }
      ]
    : response?.conversation ?? [];

  function submitOnEnter(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    void askQuestion();
  }

  return (
    <main className="app-shell">
      <div className="workspace">
        <aside className="conversation-pane" aria-label="Conversation">
          <header className="masthead">
            <div className="masthead-row">
              <a className="wordmark" href="/">Deadbot</a>
              <button type="button" className="new-chat-button" onClick={startNewChat} disabled={loading}>
                New chat
              </button>
            </div>
            <p>Grateful Dead knowledge, listening, and context</p>
          </header>

          <section className="thread" aria-label="Deadbot conversation" aria-live="polite">
            {visibleConversation.map((turn, index) => (
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
                rows={3}
                placeholder="Ask about a song, show, source, or recording"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={submitOnEnter}
                disabled={loading}
              />
              <button type="submit" disabled={loading || !question.trim()}>{loading ? "Looking…" : "Send"}</button>
            </div>
          </form>
        </aside>

        <section className="content-pane" aria-live="polite" aria-label="Deadbot guide">
          {response ? (
            <>
              <div className="content-heading">
                <p className="eyebrow">{modeLabels[response.mode]}</p>
                <h1>{response.title}</h1>
              </div>
              {response.body_lead && <p className="answer-lead">{response.body_lead}</p>}
              {response.layout.map((section, sectionIndex) => (
                <section className={`layout-section ${section.region}`} key={`${section.region}-${sectionIndex}`}>
                  {regionLabels[section.region] && <p className="region-label">{regionLabels[section.region]}</p>}
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
              {response.sources.length > 0 && (
                <footer className="sources-footer">
                  <p className="sources-footer-label">Sources</p>
                  <ul>
                    {dedupeSources(response.sources).map((source) => (
                      <li key={`${source.label}-${source.url ?? source.source_id}`}>
                        <span className="source-kind-chip">
                          {source.kind === "canonical" ? "Canonical" : "External source"}
                        </span>
                        {source.url ? (
                          <ExternalLink href={source.url}>{source.label}</ExternalLink>
                        ) : (
                          <span>{source.label}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </footer>
              )}
            </>
          ) : (
            <div className="content-empty">
              <p className="eyebrow">Starting points</p>
              <div className="starting-points">
                {suggestions.map((suggestion) => (
                  <button key={suggestion} type="button" onClick={() => void askQuestion(suggestion, { fresh: true })} disabled={loading}>
                    {suggestion} <span aria-hidden="true">↗</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
