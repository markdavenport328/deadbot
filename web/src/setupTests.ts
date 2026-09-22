import "@testing-library/jest-dom/vitest";

// jsdom has no ResizeObserver; recharts' ResponsiveContainer needs one.
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- test shim, not app code
(globalThis as any).ResizeObserver = ResizeObserverMock;

// jsdom's layout engine always reports zero-size boxes. recharts'
// ResponsiveContainer reads the container's initial size via
// getBoundingClientRect() (before any ResizeObserver callback fires) and
// renders nothing (`null`) until it sees a positive width/height -- without
// this, no chart-dependent test could ever see rendered axes/bars. recharts
// also uses a hidden `#recharts_measurement_span` element measured the same
// way to size/collision-detect axis tick labels (see
// recharts/es6/util/DOMUtils.js's measureTextWithDOM); a single fixed-size
// rect for every element would make every tick label measure as the full
// container size and collision avoidance would then drop all but one tick.
// So the container gets a real usable size, and the measurement span gets a
// rough (monospace-ish) estimate from its own text length -- close enough
// for jsdom's purposes, real font metrics aren't available here anyway.
// Added while building DataChart.tsx (Task 2), which is the first component
// in this codebase to actually render a recharts chart in tests.
Element.prototype.getBoundingClientRect = function getBoundingClientRect(): DOMRect {
  const isMeasurementSpan = this.id === "recharts_measurement_span";
  const width = isMeasurementSpan ? Math.max(1, (this.textContent ?? "").length) * 7 : 600;
  const height = isMeasurementSpan ? 14 : 320;
  return {
    width,
    height,
    top: 0,
    left: 0,
    right: width,
    bottom: height,
    x: 0,
    y: 0,
    toJSON() {
      return this;
    }
  };
};
