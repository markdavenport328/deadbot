// The research notebook is a signed token the server returns with each
// answer: what this conversation's research has found so far. The browser
// keeps it for the tab's session and sends it back with the next question,
// so a follow-up starts from that research instead of from nothing. Storage
// can be blocked or full; then the token lives only in memory for this page.
const STORAGE_KEY = "deadbot-research-notebook";

export function readStoredNotebook(): string | null {
  try {
    const value = window.sessionStorage.getItem(STORAGE_KEY);
    return value && value.trim() ? value : null;
  } catch {
    return null;
  }
}

export function storeNotebook(token: string | null | undefined): void {
  try {
    if (token) window.sessionStorage.setItem(STORAGE_KEY, token);
    else window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Blocked or full storage: the token still travels from React state.
  }
}

export function clearStoredNotebook(): void {
  storeNotebook(null);
}
