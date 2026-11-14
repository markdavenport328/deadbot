// Where the song timeline draws things: one band per year, bars or dots on a
// shared vertical scale, and gold pins for the model's stops. Pure functions,
// so the chart's layout is tested without a browser.
import type { ChartView } from "./song-timeline-types";

export const MARGIN = { left: 36, right: 6, top: 44, bottom: 26 };
const NARROW = 560;
const PIN_ROW_HEIGHT = 19;

export type Frame = {
  width: number;
  height: number;
  firstYear: number;
  yearCount: number;
  bandWidth: number;
  barWidth: number;
  plotTop: number;
  plotBottom: number;
};

export function chartHeight(view: ChartView, width: number): number {
  const narrow = width < NARROW;
  return view === "length" ? (narrow ? 250 : 290) : narrow ? 230 : 270;
}

// `pinRows` is how many rows of stop pins sit above the plot; each extra row
// adds room at the top so no pin is drawn off the chart.
export function frame(width: number, years: number[], view: ChartView, pinRows = 1): Frame {
  const extra = Math.max(0, pinRows - 1) * PIN_ROW_HEIGHT;
  const height = chartHeight(view, width) + extra;
  const yearCount = Math.max(1, years.length);
  const bandWidth = (width - MARGIN.left - MARGIN.right) / yearCount;
  return {
    width,
    height,
    firstYear: years[0] ?? 0,
    yearCount,
    bandWidth,
    barWidth: Math.min(26, bandWidth * 0.64),
    plotTop: MARGIN.top + extra,
    plotBottom: height - MARGIN.bottom
  };
}

export function bandX(f: Frame, year: number): number {
  return MARGIN.left + (year - f.firstYear) * f.bandWidth;
}

// How far through its year a date falls, from just above 0 to just below 1.
export function dayFraction(date: string): number {
  const year = Number(date.slice(0, 4));
  const day = (Date.UTC(year, Number(date.slice(5, 7)) - 1, Number(date.slice(8, 10))) - Date.UTC(year, 0, 1)) / 86_400_000;
  return (day + 0.5) / 366;
}

// A performance's place inside its year's band, inset so dots stay off the band edges.
export function pointX(f: Frame, date: string): number {
  return bandX(f, Number(date.slice(0, 4))) + f.bandWidth * 0.1 + dayFraction(date) * f.bandWidth * 0.8;
}

const NICE = [1, 2, 5, 10];

// Gridlines for counts: a round step giving four or five intervals.
export function countTicks(max: number): number[] {
  if (max <= 0) return [0, 1];
  const raw = max / 4;
  const power = 10 ** Math.floor(Math.log10(raw));
  // Counts are whole numbers, so the step is never below one.
  const step = Math.max(1, (NICE.find((n) => n * power >= raw) ?? 10) * power);
  const top = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let value = 0; value <= top + step / 2; value += step) ticks.push(Math.round(value));
  return ticks;
}

// Gridlines for lengths, in seconds, every five minutes up past the longest.
export function lengthTicks(maxSeconds: number): number[] {
  const top = Math.max(300, Math.ceil(maxSeconds / 300) * 300);
  const ticks: number[] = [];
  for (let value = 0; value <= top; value += 300) ticks.push(value);
  return ticks;
}

export function yFor(f: Frame, value: number, top: number): number {
  return f.plotBottom - (top > 0 ? value / top : 0) * (f.plotBottom - f.plotTop);
}

// Label every year when there is room, otherwise every third or sixth.
export function yearLabelStep(bandWidth: number): number {
  return bandWidth >= 40 ? 1 : bandWidth >= 22 ? 3 : 6;
}

// Each pin's row above the chart, returned in the input's order: placed left
// to right, a pin too close to the last one in a row moves up a row. Stops
// arrive in the model's listening order, so they are placed by x here.
export function pinRows(xs: number[], minGap = 20): number[] {
  const lastInRow: number[] = [];
  const rows = new Array<number>(xs.length).fill(0);
  const byX = xs.map((x, index) => ({ x, index })).sort((a, b) => a.x - b.x);
  for (const { x, index } of byX) {
    let row = 0;
    while (lastInRow[row] !== undefined && x - lastInRow[row] < minGap) row += 1;
    lastInRow[row] = x;
    rows[index] = row;
  }
  return rows;
}

// Where a tooltip goes so it never covers the pointer: to the right of it,
// flipped to the left when it would run past the chart's right edge, and
// above it, dropped below when there is no room above.
export function tipPosition(
  pointer: { x: number; y: number },
  tip: { width: number; height: number },
  boxWidth: number,
  gap = 14
): { left: number; top: number } {
  let left = pointer.x + gap;
  if (left + tip.width > boxWidth) left = pointer.x - gap - tip.width;
  if (left < 0) left = Math.max(0, Math.min(pointer.x + gap, boxWidth - tip.width));
  const above = pointer.y - gap - tip.height;
  return { left, top: above >= 0 ? above : pointer.y + gap };
}

export function pinY(f: Frame, row: number): number {
  return f.plotTop - 22 - row * PIN_ROW_HEIGHT;
}
