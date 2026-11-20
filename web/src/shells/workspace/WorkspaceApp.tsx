// The page: every answer is one exploration, with a history of earlier
// explorations kept mounted behind it. See docs/UX-NEXT-STEPS.md,
// "persistent exploration workspace".
import { useAskFromPage } from "../../core/site-nav";
import { WorkspaceShell } from "./WorkspaceShell";
import { NowPlayingBar } from "../../player/NowPlayingBar";
import { NO_QUEUE_RAIL_QUERY, PHONE_QUERY, useMediaQuery } from "../../core/media-query";
import { QueueRail } from "../../player/QueuePanel";

export function WorkspaceApp() {
  const isPhone = useMediaQuery(PHONE_QUERY);
  const narrow = useMediaQuery(NO_QUEUE_RAIL_QUERY);
  const roomForRail = !isPhone && !narrow;
  return (
    <WorkspaceShell
      player={<NowPlayingBar queueInRail={roomForRail} />}
      queueRail={roomForRail ? <QueueRail /> : null}
      phonePlayer={(composerFocused) => <NowPlayingBar collapsible queueSheet forceCollapsed={composerFocused} />}
      isPhone={isPhone}
      registerAskFromPage={useAskFromPage}
    />
  );
}
