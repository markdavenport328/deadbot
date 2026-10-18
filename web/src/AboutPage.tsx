import { useEffect, useState } from "react";
import { followInSite } from "./site-nav";
import "./AboutPage.css";
import { libraryStats } from "./library-stats";
import answerShot from "./assets/about/answer.jpg";
import showShot from "./assets/about/show.jpg";
import performanceShot from "./assets/about/performance.jpg";
import timelineShot from "./assets/about/timeline.jpg";
import versionsShot from "./assets/about/versions.jpg";
import albumShot from "./assets/about/album.jpg";
import chartShot from "./assets/about/chart.jpg";
import gridShot from "./assets/about/grid.jpg";
import writingShot from "./assets/about/writing.jpg";

const RESUME_URL = "https://mark-davenport.vercel.app";

const sections = [
  { id: "asking", title: "What you get when you ask" },
  { id: "steps", title: "How a question becomes a page" },
  { id: "library", title: "What's in the library" },
  { id: "split", title: "Who decides what" },
  { id: "blocks", title: "The building blocks" },
  { id: "listening", title: "Listening" },
  { id: "credits", title: "Who made it" }
] as const;

const sources = [
  { name: "JerryBase", gives: "Setlists, lineups, guests, and the guitars Jerry played", for: "Every show and every song on it" },
  { name: "Internet Archive", gives: "Audience and soundboard tapes, with listener reviews", for: "The player, and choosing which tape to hear" },
  { name: "Relisten", gives: "Track-by-track links into those tapes", for: "Playing one song from one night" },
  { name: "MusicBrainz and Wikidata", gives: "Official releases, credits, and band membership", for: "Album cards, and who played what, when" },
  { name: "dead.net and the Deadcast", gives: "The band's own song pages and podcast episodes", for: "Background and stories from the source" },
  { name: "Headyversion and published critics", gives: "Fan votes and critics' picks of favorite versions", for: "Questions about the best version or the best show" },
  { name: "Fan research sites", gives: "Lost Live Dead, the Grateful Dead Guide, and others", for: "The history behind a show or a song" },
  { name: "The Annotated Grateful Dead Lyrics", gives: "David Dodd's notes on every lyric", for: "What a song is about" },
  { name: "Spotify", gives: "Links to the official releases", for: "Listening to the albums" }
];

const specimens = [
  { title: "Shows", text: "Each night with its venue, date, and a play button. Open one for its setlist, lineup, and tapes, or list a whole year as rows.", image: showShot, alt: "Every 1977 show as a row with a gold play button" },
  { title: "A performance", text: "One song on one night, with what came before and after it in the set, and a way to hear it.", image: performanceShot, alt: "A performance card for Dark Star at the Carousel Ballroom in 1968" },
  { title: "A song's life on stage", text: "Every year a song was played, how often, and the stops worth hearing along the way.", image: timelineShot, alt: "Terrapin Station's performances by year, with eight stops to play" },
  { title: "Versions side by side", text: "The same song or pairing across the nights it was played, so you can hear how it changed.", image: versionsShot, alt: "China Cat Sunflower into I Know You Rider on eight nights, drawn to the same clock" },
  { title: "A record", text: "An official release, its tracklist and personnel, the songs to listen for, and a way to play it.", image: albumShot, alt: "An album card for Workingman's Dead" },
  { title: "Counts and rankings", text: "Charts and ranked lists, counted from the whole history rather than estimated.", image: chartShot, alt: "The ten songs the Dead played most" },
  { title: "Grids", text: "Many nights or songs at once, compared on the same measure.", image: gridShot, alt: "A grid of the big jams on each night of Europe '72" },
  { title: "Writing", text: "The model's own voice: the story, the numbers that matter, a timeline of the day.", image: writingShot, alt: "Narrative, figures, and a timeline about the Veneta show" }
];

export function AboutPage() {
  const [active, setActive] = useState<string>(sections[0].id);

  useEffect(() => {
    const previous = document.title;
    document.title = "About Deadbot";
    // Arriving from the app starts at the top; a link to one section lands on it.
    const target = window.location.hash ? document.getElementById(window.location.hash.slice(1)) : null;
    if (target) target.scrollIntoView();
    else window.scrollTo(0, 0);
    return () => {
      document.title = previous;
    };
  }, []);

  // The contents list follows the reader: the section nearest the top of the
  // window is the one marked.
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return undefined;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((entry) => entry.isIntersecting);
        if (visible.length > 0) setActive(visible[0].target.id);
      },
      { rootMargin: "0px 0px -70% 0px" }
    );
    sections.forEach(({ id }) => {
      const element = document.getElementById(id);
      if (element) observer.observe(element);
    });
    return () => observer.disconnect();
  }, []);

  return (
    <main className="about">
      <header className="about-top">
        <a className="wordmark" href="/" onClick={(event) => followInSite(event, "/")}>Deadbot</a>
      </header>

      <div className="about-hero">
        <p className="about-eyebrow">About Deadbot</p>
        <h1>How Deadbot works</h1>
        <p className="about-lead">
          Deadbot is a guide to the Grateful Dead's thirty years on stage. Ask it what a fan would ask, and instead of a
          paragraph of chat it builds you a page: the shows, the versions worth hearing, the recordings, and a way to
          listen. Here is what it does, where its knowledge comes from, and how it keeps the facts straight.
        </p>
      </div>

      <div className="about-layout">
        <nav className="about-toc" aria-label="On this page">
          <p className="about-eyebrow">On this page</p>
          <ol>
            {sections.map(({ id, title }) => (
              <li key={id}>
                <a href={`#${id}`} className={active === id ? "active" : undefined} aria-current={active === id ? "location" : undefined}>
                  {title}
                </a>
              </li>
            ))}
          </ol>
        </nav>

        <article className="about-article">
          <section id="asking" aria-labelledby="asking-title">
            <p className="about-number">01</p>
            <h2 id="asking-title">What you get when you ask</h2>
            <p className="about-lead-in">
              Ask the way you'd ask a friend who has heard every tape. "Best Morning Dew?" "What happened at Veneta?" "How
              did Dark Star change after 1973?" Deadbot answers in two places at once.
            </p>
            <div className="about-pair">
              <div>
                <h3>The conversation</h3>
                <p>A few sentences that answer you directly, in the column on the left.</p>
              </div>
              <div>
                <h3>The page</h3>
                <p>
                  Beside it, a page made for that question: show cards with their setlists, the versions worth hearing,
                  charts and timelines, and play buttons for the recordings.
                </p>
              </div>
            </div>
            <figure className="about-shot wide">
              <img src={answerShot} alt="Deadbot answering a question about the Veneta show: the conversation on the left, the composed page on the right" loading="lazy" />
            </figure>
            <p>
              Every card offers somewhere to go next. Choose one of its suggested questions and the conversation carries
              on, with a new page built around where you went.
            </p>

            <h3>Three kinds of questions</h3>
            <ul className="about-kinds">
              <li>
                <p className="kind-name">Listening</p>
                <p className="kind-ask">"Play me a great Scarlet &gt; Fire."</p>
                <p>Deadbot leads with the music: one night, one tape, ready to play.</p>
              </li>
              <li>
                <p className="kind-name">Digging</p>
                <p className="kind-ask">"When did China &gt; Rider become a pair?"</p>
                <p>Timelines, counts, and versions side by side, to show how something changed.</p>
              </li>
              <li>
                <p className="kind-name">Settling it</p>
                <p className="kind-ask">"Best shows of 1977."</p>
                <p>Picks from critics, fans, and the official releases, with the reasons.</p>
              </li>
            </ul>
          </section>

          <section id="steps" aria-labelledby="steps-title">
            <p className="about-number">02</p>
            <h2 id="steps-title">How a question becomes a page</h2>
            <p className="about-lead-in">
              Each answer takes four steps. A language model makes the judgment calls about what to look up and what to
              say. Software handles the facts.
            </p>
            <ol className="about-flow" aria-label="The four steps">
              <li className="model"><span className="flow-tag">Model</span><p className="flow-title">Understand the question</p><p className="flow-desc">Reads it with the conversation so far</p></li>
              <li className="model"><span className="flow-tag">Model</span><p className="flow-title">Research</p><p className="flow-desc">Looks things up in the library, often many times</p></li>
              <li className="model"><span className="flow-tag">Model</span><p className="flow-title">Plan the page</p><p className="flow-desc">Chooses what to show, in what order, how prominently</p></li>
              <li className="code"><span className="flow-tag">Software</span><p className="flow-title">Fill and show</p><p className="flow-desc">Fills every card from the library and builds the players</p></li>
            </ol>
            <ol className="about-steps">
              <li>
                <strong>Understand the question.</strong> The model reads your question alongside everything already on
                the screen, so "what about the second set?" means the show you were just looking at.
              </li>
              <li>
                <strong>Research.</strong> The model has about thirty research tools, and every one of them only reads. It
                can open a show, a song, a single performance, or an album; count and rank across the whole history; find
                every night a guest sat in; or read a page from a fan research site. It decides which to use, and keeps
                going until it has what a knowledgeable fan would want.
              </li>
              <li>
                <strong>Plan the page.</strong> The model writes a plan: a headline, a short lead, and groups of cards in
                the order that tells the story. It names each show, song, or recording by its place in the library rather
                than writing the details out itself.
              </li>
              <li>
                <strong>Fill and show.</strong> Software takes the plan, looks up each record the model named, and fills
                its card from the library: the date, the venue, the setlist, the credits, the tape. It turns stored links
                into players. The page appears piece by piece while the model is still writing, so you are reading within
                seconds.
              </li>
            </ol>
          </section>

          <section id="library" aria-labelledby="library-title">
            <p className="about-number">03</p>
            <h2 id="library-title">What's in the library</h2>
            <ul className="about-stats">
              {libraryStats.map(({ count, noun }) => (
                <li key={noun}><span className="num">{count}</span><span className="noun">{noun}</span></li>
              ))}
            </ul>
            <p>
              The library is arranged the way fans think about the music. A song is a composition. A show is one night. A
              performance is one song on one night, and that is where most of the interest lies: "Dark Star" at Veneta
              in 1972 is a different thing from "Dark Star" at the Fillmore West in 1969.
            </p>
            <div className="about-model" role="img" aria-label="A song and a show meet in a performance. Recordings and official releases hold performances. People and a venue belong to the show.">
              <div className="node">Song<span>a composition</span></div>
              <div className="link" />
              <div className="node key">Performance<span>one song, one night</span></div>
              <div className="link" />
              <div className="node">Show<span>one night</span></div>
              <div className="under under-performance">
                <div className="node small">Recordings<span>the tapes</span></div>
                <div className="node small">Official releases<span>the albums</span></div>
              </div>
              <div className="under under-show">
                <div className="node small">Venue</div>
                <div className="node small">Lineup and guests</div>
              </div>
            </div>
            <h3>Where it comes from</h3>
            <div className="about-table">
              <table>
                <thead>
                  <tr><th scope="col">Source</th><th scope="col">What it gives</th><th scope="col">Used for</th></tr>
                </thead>
                <tbody>
                  {sources.map((source) => (
                    <tr key={source.name}><th scope="row">{source.name}</th><td>{source.gives}</td><td>{source.for}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p>
              Everything is reviewed and kept as plain files alongside the code, then built into one database each time
              the site is published. When Deadbot is answering you, it only reads.
            </p>
          </section>

          <section id="split" aria-labelledby="split-title">
            <p className="about-number">04</p>
            <h2 id="split-title">Who decides what</h2>
            <blockquote className="about-principle">
              <p>
                A model with the right goal and the right material will give you an intelligent, surprising answer. So
                Deadbot gives the model a goal, a deep library, and a good set of building blocks, and then gets out of
                its way.
              </p>
            </blockquote>
            <div className="about-pair split">
              <div>
                <h3>The model decides</h3>
                <ul>
                  <li>What to say, and what to leave out</li>
                  <li>Which shows, versions, and tapes to feature</li>
                  <li>How deep to go</li>
                  <li>The order and grouping of the page</li>
                  <li>What belongs in the conversation and what belongs on the page</li>
                </ul>
              </div>
              <div>
                <h3>Software guarantees</h3>
                <ul>
                  <li>A show's date, venue, and setlist come straight from the library</li>
                  <li>Credits and lineups are never retyped</li>
                  <li>Every player is built from a stored link</li>
                  <li>A link the model didn't find in its research is removed</li>
                  <li>A record the library can't find keeps the model's words, never invented details</li>
                </ul>
              </div>
            </div>
            <p>
              That split is why the model's instructions hold almost no rules. When an answer falls short, the fix is to
              give the model what it was missing: better material, a clearer goal, or a building block that fits what it
              wanted to say.
            </p>
          </section>

          <section id="blocks" aria-labelledby="blocks-title">
            <p className="about-number">05</p>
            <h2 id="blocks-title">The building blocks</h2>
            <p className="about-lead-in">
              Each block fits a task fans bring to the music. The model can use any of them, in any order, as often as
              the answer needs, and show each one open or folded down to a single row.
            </p>
            <div className="about-specimens">
              {specimens.map((specimen) => (
                <div className="specimen" key={specimen.title}>
                  <div>
                    <h3>{specimen.title}</h3>
                    <p>{specimen.text}</p>
                  </div>
                  <figure className="about-shot">
                    <img src={specimen.image} alt={specimen.alt} loading="lazy" />
                  </figure>
                </div>
              ))}
            </div>
          </section>

          <section id="listening" aria-labelledby="listening-title">
            <p className="about-number">06</p>
            <h2 id="listening-title">Listening</h2>
            <p>
              <span className="gold">Gold always means you can hear it.</span> A gold play button plays that show or that
              song right here, from the tapes fans have shared on the Internet Archive. The player stays at the foot of
              the page and keeps going while you ask more questions, or while you read this. Official releases link to
              Spotify.
            </p>
          </section>

          <section id="credits" aria-labelledby="credits-title">
            <p className="about-number">07</p>
            <h2 id="credits-title">Who made it</h2>
            <p>
              Deadbot is a project by{" "}
              <a href={RESUME_URL} target="_blank" rel="noopener">Mark Davenport<span className="visually-hidden"> (opens in a new tab)</span></a>.
              It stands on decades of work by the tapers, archivists, and fans who documented the band night by night,
              and on the sites above that share that work.
            </p>
            <p className="about-back">
              <a href="/" onClick={(event) => followInSite(event, "/")}>Ask Deadbot a question</a>
            </p>
          </section>
        </article>
      </div>
    </main>
  );
}
