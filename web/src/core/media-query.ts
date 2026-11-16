import { useEffect, useState } from "react";

// Below this width the layout is one column and the ask box and player move
// into a dock fixed at the foot of the screen.
export const PHONE_QUERY = "(max-width: 860px)";

// Below this width a desktop has no room for the queue's own rail; the queue
// opens above the player instead.
export const NO_QUEUE_RAIL_QUERY = "(max-width: 1099px)";

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(query).matches);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const list = window.matchMedia(query);
    const update = () => setMatches(list.matches);
    update();
    list.addEventListener("change", update);
    return () => list.removeEventListener("change", update);
  }, [query]);
  return matches;
}
