import "@testing-library/jest-dom/vitest";

// jsdom has no ResizeObserver; recharts' ResponsiveContainer needs one.
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- test shim, not app code
(globalThis as any).ResizeObserver = ResizeObserverMock;
