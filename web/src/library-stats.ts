// Catalog counts shown on the home screen and the About page. These are read
// from the canonical CSVs, not the live database, so they cost the page
// nothing to display.
// tests/test_home_stats.py fails when an import moves them; recompute with:
//   python scripts/home_stats.py
export const libraryStats = [
  { count: "2,358", noun: "shows" },
  { count: "436", noun: "songs" },
  { count: "39,774", noun: "performances" },
  { count: "18,002", noun: "recordings" },
  { count: "139", noun: "guests" }
];
