import { libraryStats as stats } from "../../core/library-stats";

const startingPoints = [
  {
    category: "Shows",
    questions: [
      "Put on a hot second set from fall '73",
      "What's the story with Veneta?",
      "How many times did they play Madison Square Garden?"
    ]
  },
  {
    category: "Songs",
    questions: [
      "What songs did they play the most?",
      "When did China-Rider become a combo?",
      "Which American Beauty songs stayed in the rotation?"
    ]
  },
  {
    category: "Performances",
    questions: [
      "How often did they play Dark Star each year?",
      "Best Morning Dew?",
      "Did Playing in the Band keep getting longer?"
    ]
  },
  {
    category: "Recordings",
    questions: [
      "Which Dick's Picks should I start with?",
      "Which songs defined Europe '72, night by night?",
      "What shows did Reckoning draw from?"
    ]
  },
  {
    category: "Guests",
    questions: [
      "Best Santana contributions",
      "Which guests kept coming back year after year?",
      "Who sat in with the Dead?"
    ]
  }
];

// The home screen's lead and the library with its starting points.
export function StartLibrary({ onAsk }: { onAsk(prompt: string): void }) {
  return (
    <>
      <h1 className="start-lead">Exploration and listening across the entire Dead catalog.</h1>
      <div className="library">
        {stats.map(({ count, noun }) => {
          const group = startingPoints.find((candidate) => candidate.category.toLowerCase() === noun);
          return (
            <section className="library-stat" key={noun}>
              <p className="num">{count}</p>
              <p className="noun">{noun}</p>
              {group && (
                <ul className="qs">
                  {group.questions.map((prompt) => (
                    <li key={prompt}>
                      <button type="button" onClick={() => onAsk(prompt)}>
                        {prompt}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          );
        })}
      </div>
    </>
  );
}
