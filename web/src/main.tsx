import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { AppFallback, ErrorBoundary } from "./core/error-boundary";
import "./styles.css";

// The service worker (public/sw.js) plays songs saved for offline and lets
// the app open without a signal. Production only: in development it would
// hold on to stale scripts between edits.
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  });
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary name="the app" fallback={<AppFallback />}>
      <App />
    </ErrorBoundary>
  </StrictMode>
);
