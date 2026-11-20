// The version of the page contract this build of the client draws. It is
// read from web/openapi.json when the client is built (see vite.config.ts),
// so it moves with the server's models and the generated types. A page saved
// under another version may hold cards this build no longer has; saved
// history drops those pages instead of trying to draw them.
declare const __DEADBOT_SCHEMA_VERSION__: string;

export const SCHEMA_VERSION: string = __DEADBOT_SCHEMA_VERSION__;
