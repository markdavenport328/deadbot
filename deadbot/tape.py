"""A performance's tape track: the file, or files, the in-page player plays for it.

Most songs are one whole file on a tape. Some are not:

- a song inside a file it shares with another song (a later song of a medley
  file, a reprise after a drum break) plays a window of that file: the link
  carries ``start_seconds`` and its ``duration_seconds`` is the song's length
  inside the file, so the song ends at ``start + duration``;
- a song the tape cuts into several files (a long jam over a reel change) is
  one link per file, on one tape, played back to back. The first keeps the
  usual ``…-archive-track`` ID and the rest add ``-part-02``, ``-part-03``,
  so ordering the links by ID orders the parts.

Every reader that plays or states a tape length goes through ``tape_tracks``,
so the same files and the same length appear on every card. A song whose
length is the sum of its parts states that sum, and states no length when any
part has none.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlparse


def archive_identifier(url: str) -> str | None:
    """The Internet Archive item in a ``/download/<identifier>/<file>`` URL."""

    parsed = urlparse(url or "")
    if parsed.netloc.casefold().removeprefix("www.") != "archive.org":
        return None
    parts = [part for part in parsed.path.split("/") if part]
    return parts[1] if len(parts) >= 2 and parts[0] == "download" else None


def _seconds(value: Any) -> int | None:
    text = str(value if value is not None else "").strip()
    return int(text) if text.isdigit() else None


@dataclass(frozen=True)
class TapePart:
    url: str
    # Where the song starts in this file; None plays the file from its top.
    start_seconds: int | None
    # The song's length in this file (the whole file when there is no start).
    duration_seconds: int | None

    @property
    def windowed(self) -> bool:
        return self.start_seconds is not None

    @property
    def end_seconds(self) -> int | None:
        """Where the song stops in this file; None plays to the file's end."""

        if not self.windowed or self.duration_seconds is None:
            return None
        return (self.start_seconds or 0) + self.duration_seconds


@dataclass(frozen=True)
class TapeTrack:
    parts: tuple[TapePart, ...]

    @classmethod
    def whole_file(cls, url: str, duration_seconds: int | None) -> "TapeTrack":
        return cls(parts=(TapePart(url=url, start_seconds=None, duration_seconds=duration_seconds),))

    @property
    def url(self) -> str:
        return self.parts[0].url

    @property
    def identifier(self) -> str | None:
        return archive_identifier(self.url)

    @property
    def duration_seconds(self) -> int | None:
        """The song's length: the sum of its parts, or None when any part has none.

        A zero length is a cataloging gap, not a length.
        """

        lengths = [part.duration_seconds for part in self.parts]
        if any(not length for length in lengths):
            return None
        return sum(lengths)  # type: ignore[arg-type]

    def audio_parts(self) -> list[dict[str, Any]] | None:
        """What the player needs beyond ``audio_url``: None for one whole file."""

        if len(self.parts) == 1 and not self.parts[0].windowed:
            return None
        # Every part states where it ends, so the player can place any moment
        # of the song in the right file before it has loaded any of them.
        return [
            {
                "audio_url": part.url,
                "start_seconds": part.start_seconds or 0,
                "end_seconds": part.end_seconds
                if part.windowed
                else (part.duration_seconds if part.duration_seconds else None),
            }
            for part in self.parts
        ]


def is_tape_link(row: dict[str, Any]) -> bool:
    return row.get("platform") == "archive" and row.get("link_type") == "recording-track" and bool(row.get("url"))


def tape_tracks(links: Iterable[dict[str, Any]]) -> dict[str, TapeTrack]:
    """Each performance's tape track from its ``performance_links`` rows.

    The link with the lowest ID names the tape; every link of that
    performance on that tape is a part, in ID order.
    """

    by_performance: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in links:
        if is_tape_link(row) and row.get("performance_id"):
            by_performance[row["performance_id"]].append(row)
    tracks: dict[str, TapeTrack] = {}
    for performance_id, rows in by_performance.items():
        rows.sort(key=lambda row: row.get("performance_link_id") or "")
        tape = archive_identifier(rows[0]["url"])
        parts = tuple(
            TapePart(url=row["url"], start_seconds=_seconds(row.get("start_seconds")), duration_seconds=_seconds(row.get("duration_seconds")))
            for row in rows
            if archive_identifier(row["url"]) == tape
        )
        tracks[performance_id] = TapeTrack(parts=parts)
    return tracks
