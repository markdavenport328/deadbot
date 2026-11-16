import { useEffect, useRef } from "react";

// Reload after a deploy, checked only when a tab comes back into view and at
// most every few minutes. A timer would keep every forgotten background tab
// calling the server around the clock.
const VERSION_CHECK_INTERVAL_MS = 5 * 60_000;
const STORAGE_KEY = "deadbot-server-version";

let lastVersionCheck = 0;

// `busy` holds the reload while an answer is being written; the next check
// catches the new version once it is done.
export async function refreshIfServerChanged(busy: () => boolean = () => false): Promise<void> {
  const now = Date.now();
  if (now - lastVersionCheck < VERSION_CHECK_INTERVAL_MS) return;
  lastVersionCheck = now;
  try {
    const result = await fetch("/api/version", { cache: "no-store" });
    if (!result.ok) return;
    const health = await result.json() as { git_commit?: string };
    const current = health.git_commit;
    if (!current || current === "unknown") return;
    const previous = sessionStorage.getItem(STORAGE_KEY);
    if (previous && previous !== current) {
      if (busy()) {
        lastVersionCheck = 0;
        return;
      }
      sessionStorage.setItem(STORAGE_KEY, current);
      window.location.reload();
      return;
    }
    sessionStorage.setItem(STORAGE_KEY, current);
  } catch {
    // Offline or storage blocked: try again next time the tab comes back.
  }
}

// Checks on arrival and whenever the tab comes back into view; off for
// development fixtures, which have no server to compare against.
export function useReloadOnDeploy(enabled: boolean, busy?: () => boolean): void {
  const busyRef = useRef(busy);
  busyRef.current = busy;
  useEffect(() => {
    if (!enabled) return;
    const check = () => refreshIfServerChanged(() => busyRef.current?.() ?? false);
    void check();
    const onVisible = () => {
      if (document.visibilityState === "visible") void check();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [enabled]);
}

// For tests: forget when the last check ran.
export function resetVersionCheckForTests(): void {
  lastVersionCheck = 0;
}
