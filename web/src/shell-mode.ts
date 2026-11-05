// Which shell the visitor sees. The classic page is the default; the
// workspace is opt-in with ?shell=workspace and remembered until ?shell=classic.
export type ShellMode = "classic" | "workspace";

const KEY = "deadbot-shell";

function isMode(value: unknown): value is ShellMode {
  return value === "classic" || value === "workspace";
}

export function readShellMode(search: string = window.location.search): ShellMode {
  try {
    const asked = new URLSearchParams(search).get("shell");
    if (isMode(asked)) {
      window.localStorage.setItem(KEY, asked);
      return asked;
    }
    const stored = window.localStorage.getItem(KEY);
    return isMode(stored) ? stored : "classic";
  } catch {
    return "classic";
  }
}
