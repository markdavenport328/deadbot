import { useLayoutEffect, useRef, useState } from "react";
import { PlayerProvider } from "./player/player";
import { MenuSlotProvider } from "./core/menu-slot";
import { Rosettes } from "./cards/listening";
import { AboutPage } from "./AboutPage";
import { SiteMenu } from "./SiteMenu";
import { usePath } from "./core/site-nav";
import { readShellMode } from "./shell-mode";
import { shells } from "./shells";
import { NowPlayingBar } from "./player/NowPlayingBar";

// The About page replaces the app on screen without unmounting it, so the
// conversation, its page, and its scroll position are all still there on the
// way back, and the player bar comes along.
export default function AppWithPlayer() {
  const path = usePath();
  const onAbout = path === "/about";
  const homeScroll = useRef(0);
  const [mode] = useState(() => readShellMode(window.location.search));
  const Shell = shells[mode];

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
      <MenuSlotProvider>
        <Rosettes />
        <SiteMenu />
        <div className="app-view" hidden={onAbout}>
          <Shell />
        </div>
        {onAbout && (
          <>
            <AboutPage />
            <div className="about-player"><NowPlayingBar /></div>
          </>
        )}
      </MenuSlotProvider>
    </PlayerProvider>
  );
}
