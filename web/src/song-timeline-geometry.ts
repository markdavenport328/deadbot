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

export function frame(width: number, years: number[], view: ChartView): Frame {
  const height = chartHeight(view, width);
  const yearCount = Math.max(1, years.length);
  const bandWidth = (width - MARGIN.left - MARGIN.right) / yearCount;
  return {
    width,
    height,
    firstYear: years[0] ?? 0,
    yearCount,
    bandWidth,
    barWidth: Math.min(26, bandWidth * 0.64),
    plotTop: MARGIN.top,
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
  const step = (NICE.find((n) => n * power >= raw) ?? 10) * power;
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

// Each pin's row above the chart: a pin too close to the last one in a row
// moves up a row. Input xs are in date order.
export function pinRows(xs: number[], minGap = 20): number[] {
  const lastInRow: number[] = [];
  return xs.map((x) => {
    let row = 0;
    while (lastInRow[row] !== undefined && x - lastInRow[row] < minGap) row += 1;
    lastInRow[row] = x;
    return row;
  });
}

export function pinY(f: Frame, row: number): number {
  return f.plotTop - 22 - row * PIN_ROW_HEIGHT;
}
