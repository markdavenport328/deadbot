// The workspace shell: every answer is one exploration with Listen, Charts and
// Read tabs, with a history of earlier explorations kept mounted behind it. It
// has been opt-in (?shell=workspace) since #85, 2026-11-06; see
// docs/UX-NEXT-STEPS.md, "persistent exploration workspace".
import { useState } from "react";
import { currentPath, takeQuestionFromUrl, useAskFromPage } from "../../core/site-nav";
import { WorkspaceShell } from "./WorkspaceShell";
import { NowPlayingBar } from "../../player/NowPlayingBar";
import { PHONE_QUERY, useMediaQuery } from "../../core/media-query";

// The opt-in workspace shell (?shell=workspace) with the same player bar,
// start screen and renderers as the old one.
export function WorkspaceApp() {
  const isPhone = useMediaQuery(PHONE_QUERY);
  const [linkedQuestion] = useState(() => (currentPath() === "/" ? takeQuestionFromUrl() : null));
  return (
    <WorkspaceShell
      player={<NowPlayingBar />}
      phonePlayer={(composerFocused) => <NowPlayingBar collapsible forceCollapsed={composerFocused} />}
      isPhone={isPhone}
      linkedQuestion={linkedQuestion}
      registerAskFromPage={useAskFromPage}
    />
  );
}
