import { lazy } from "react";

// recharts (pulled in by DataChart) is a large dependency relative to how
// rarely a page actually contains a data_chart block, so it loads lazily:
// the main bundle stays small and recharts' own chunk is fetched only when
// a page needs to plot something.
export const DataChart = lazy(() => import("./DataChart").then((module) => ({ default: module.DataChart })));
