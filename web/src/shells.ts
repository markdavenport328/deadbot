// The registry of page shells. A new layout experiment is a new folder under
// shells/ plus one line here; retiring one means deleting both. ?shell=<name>
// picks a shell (see shell-mode.ts), and the default is used otherwise.
import { ClassicApp } from "./shells/classic/ClassicApp";
import { WorkspaceApp } from "./shells/workspace/WorkspaceApp";

export const shells = { classic: ClassicApp, workspace: WorkspaceApp };
// The workspace has been the default since step 6 of the shells plan
// (2026-11-16); ?shell=classic keeps the old page for one release.
export const defaultShell = "workspace";
