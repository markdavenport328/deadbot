import { afterEach, expect, test, vi } from "vitest";
import { clearStoredNotebook, readStoredNotebook, storeNotebook } from "./research-notebook";

afterEach(() => {
  vi.restoreAllMocks();
  window.sessionStorage.clear();
});

test("a stored notebook comes back for the tab, and clearing it forgets it", () => {
  storeNotebook("v1.body.sig");
  expect(readStoredNotebook()).toBe("v1.body.sig");
  clearStoredNotebook();
  expect(readStoredNotebook()).toBeNull();
});

test("an answer without a notebook clears the stored one", () => {
  storeNotebook("v1.body.sig");
  storeNotebook(undefined);
  expect(readStoredNotebook()).toBeNull();
});

test("blocked or full storage is ignored", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new DOMException("blocked", "SecurityError");
  });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new DOMException("full", "QuotaExceededError");
  });
  vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
    throw new DOMException("blocked", "SecurityError");
  });
  expect(() => storeNotebook("v1.body.sig")).not.toThrow();
  expect(() => storeNotebook(null)).not.toThrow();
  expect(() => clearStoredNotebook()).not.toThrow();
  expect(readStoredNotebook()).toBeNull();
});

test("an unreachable sessionStorage object is ignored", () => {
  vi.spyOn(window, "sessionStorage", "get").mockImplementation(() => {
    throw new DOMException("blocked", "SecurityError");
  });
  expect(() => storeNotebook("v1.body.sig")).not.toThrow();
  expect(readStoredNotebook()).toBeNull();
});
