import { useLayoutEffect, useRef } from "react";
import { PlayerProvider } from "./player/player";
import { Rosettes } from "./cards/listening";
import { AboutPage } from "./AboutPage";
import { usePath } from "./core/site-nav";
import { WorkspaceApp } from "./shells/workspace/WorkspaceApp";
import { NowPlayingBar } from "./player/NowPlayingBar";

// The About page replaces the app on screen without unmounting it, so the
// conversation, its page, and its scroll position are all still there on the
// way back, and the player bar comes along.
export default function AppWithPlayer() {
  const path = usePath();
  const onAbout = path === "/about";
  const homeScroll = useRef(0);

  useLayoutEffect(() => {
    if (onAbout) return undefined;
    window.scrollTo(0, homeScroll.current);
    const remember = () => {
      homeScroll.current = window.scrollY;
    };
    window.addEventListener("scroll", remember, { passive: true });
    return () => window.removeEventListener("scroll", remember);
  }, [onAbout]);

  return (
    <PlayerProvider>
      <Rosettes />
      <div className="app-view" hidden={onAbout}>
        <WorkspaceApp />
      </div>
      {onAbout && (
        <>
          <AboutPage />
          <div className="about-player"><NowPlayingBar /></div>
        </>
      )}
    </PlayerProvider>
  );
}
