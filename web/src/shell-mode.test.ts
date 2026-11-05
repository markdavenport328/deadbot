import { beforeEach, expect, test } from "vitest";
import { readShellMode } from "./shell-mode";

beforeEach(() => window.localStorage.clear());

test("classic by default", () => expect(readShellMode("")).toBe("classic"));
test("the query opts in and is remembered", () => {
  expect(readShellMode("?shell=workspace")).toBe("workspace");
  expect(readShellMode("")).toBe("workspace");
  expect(readShellMode("?shell=classic")).toBe("classic");
  expect(readShellMode("")).toBe("classic");
});
test("unknown values are ignored", () => expect(readShellMode("?shell=fancy")).toBe("classic"));
