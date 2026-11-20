import { lazy, type ComponentType } from "react";
import type { ExperienceBlock } from "../types";
import type { FollowUp } from "../core/ask-request";
import { CardHeading } from "./components";

type ChartProps = { block: Extract<ExperienceBlock, { type: "data_chart" }>; embedded?: boolean; onFollowUp?: FollowUp };

// The chart's code did not arrive. After a deploy an open tab still asks for
// the previous build's file, which is gone; a reload picks up the new one.
// The chart's title stays so the page still says what belongs here.
function ChartDidNotLoad({ block }: ChartProps) {
  return (
    <div className="data-chart-unavailable" role="note">
      <CardHeading className="data-chart-title">{block.title}</CardHeading>
      <p className="data-chart-unavailable-reason">
        This chart did not load.{" "}
        <button type="button" className="quiet-action" onClick={() => window.location.reload()}>Reload the page</button>
        {" "}to draw it.
      </p>
    </div>
  );
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Try the import, once more after a moment (a dropped connection), and then
// settle for the note above rather than an error.
export async function loadChart(load: () => Promise<{ DataChart: ComponentType<ChartProps> }>, retryAfterMs = 1200): Promise<{ default: ComponentType<ChartProps> }> {
  try {
    return { default: (await load()).DataChart };
  } catch {
    try {
      await wait(retryAfterMs);
      return { default: (await load()).DataChart };
    } catch {
      return { default: ChartDidNotLoad };
    }
  }
}

// recharts (pulled in by DataChart) is a large dependency relative to how
// rarely a page actually contains a data_chart block, so it loads lazily:
// the main bundle stays small and recharts' own chunk is fetched only when
// a page needs to plot something.
export const DataChart = lazy(() => loadChart(() => import("./DataChart")));
