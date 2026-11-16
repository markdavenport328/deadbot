// Which shell the visitor sees. The default shell comes from the registry; the
// others are opt-in with ?shell=<name> and remembered until another name is asked for
// (?shell=workspace returns to the default). The key changed when the default
// did, so a "classic" remembered from when that meant the default lets go.
import { defaultShell, shells } from "./shells";

export type ShellMode = keyof typeof shells;

const KEY = "deadbot-shell.v2";

function isMode(value: unknown): value is ShellMode {
  return typeof value === "string" && Object.prototype.hasOwnProperty.call(shells, value);
}

export function readShellMode(search: string = window.location.search): ShellMode {
  try {
    const asked = new URLSearchParams(search).get("shell");
    if (isMode(asked)) {
      window.localStorage.setItem(KEY, asked);
      return asked;
    }
    const stored = window.localStorage.getItem(KEY);
    return isMode(stored) ? stored : defaultShell;
  } catch {
    return defaultShell;
  }
}
