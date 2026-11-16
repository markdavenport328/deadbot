import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { refreshIfServerChanged, resetVersionCheckForTests } from "./server-version";

const reload = vi.fn();

function serve(commit: string) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ git_commit: commit }), { status: 200 })));
}

beforeEach(() => {
  resetVersionCheckForTests();
  sessionStorage.clear();
  reload.mockReset();
  Object.defineProperty(window, "location", { value: { ...window.location, reload }, configurable: true });
});
afterEach(() => vi.unstubAllGlobals());

test("the first check only remembers the version", async () => {
  serve("aaa");
  await refreshIfServerChanged();
  expect(reload).not.toHaveBeenCalled();
  expect(sessionStorage.getItem("deadbot-server-version")).toBe("aaa");
});

test("a new version reloads the page", async () => {
  sessionStorage.setItem("deadbot-server-version", "aaa");
  serve("bbb");
  await refreshIfServerChanged();
  expect(reload).toHaveBeenCalledTimes(1);
});

test("an answer being written holds the reload until the next check", async () => {
  sessionStorage.setItem("deadbot-server-version", "aaa");
  serve("bbb");
  await refreshIfServerChanged(() => true);
  expect(reload).not.toHaveBeenCalled();
  expect(sessionStorage.getItem("deadbot-server-version")).toBe("aaa");
  await refreshIfServerChanged(() => false);
  expect(reload).toHaveBeenCalledTimes(1);
});

test("checks are spaced out", async () => {
  sessionStorage.setItem("deadbot-server-version", "aaa");
  serve("aaa");
  await refreshIfServerChanged();
  serve("bbb");
  await refreshIfServerChanged();
  expect(reload).not.toHaveBeenCalled();
});

test("a failed request changes nothing", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("offline"); }));
  await expect(refreshIfServerChanged()).resolves.toBeUndefined();
  expect(reload).not.toHaveBeenCalled();
});
