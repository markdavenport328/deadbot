import { beforeEach, expect, test } from "vitest";
import { readShellMode } from "./shell-mode";

beforeEach(() => window.localStorage.clear());

test("the workspace by default", () => expect(readShellMode("")).toBe("workspace"));
test("the query opts in and is remembered", () => {
  expect(readShellMode("?shell=classic")).toBe("classic");
  expect(readShellMode("")).toBe("classic");
  expect(readShellMode("?shell=workspace")).toBe("workspace");
  expect(readShellMode("")).toBe("workspace");
});
test("unknown values are ignored", () => expect(readShellMode("?shell=fancy")).toBe("workspace"));
test("a choice remembered under the old key no longer holds", () => {
  window.localStorage.setItem("deadbot-shell", "classic");
  expect(readShellMode("")).toBe("workspace");
});
