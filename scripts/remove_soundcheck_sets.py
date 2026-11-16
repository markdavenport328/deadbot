#!/usr/bin/env python3
"""Take soundchecks (and one tape filler) out of the shows' setlists.

gdshowsdb has no set labels, so a soundcheck taped before a show arrives as an
unnamed first set, and the import made it "Set 1" with the real sets numbered
2, 3, 4. That put soundcheck takes into play counts, debuts and bust-out gaps:
Unbroken Chain's "debut" became the 3/17/95 soundcheck, It's a Man's World's
6/30/95 soundcheck read as a 24-year comeback.

Each show below has archive.org tape notes that name the first set as a
soundcheck (or, for 1973-10-23, as filler after the encore). For those shows
the script removes Set 1, removes rows that point at it, numbers the remaining
sets from 1 (performance IDs stay as they are), and appends every removed row
to data/raw/corrections/soundcheck-sets-removed.jsonl so it can be restored.
Shows with a small first set but no such note are left for review.

    python scripts/remove_soundcheck_sets.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "canonical"
REMOVED = ROOT / "data" / "raw" / "corrections" / "soundcheck-sets-removed.jsonl"

# show_id -> the archive.org item whose notes say what the first set was
EVIDENCE = {
    "gd-1970-11-06": "deadlists via archive.org: 'SET 1 is the acoustic soundcheck'",
    "gd-1973-02-15": "archive.org: 'Soundcheck: Jack Straw, Box of Rain'",
    "gd-1973-10-23": "archive.org gd1973-10-23.sbd.miller.92792: Wang Dang Doodle is the last file, after the encore, and absent from the taper's setlist",
    "gd-1974-02-22": "archive.org: 'Reported Soundcheck before this show'; gd1974-02-22.114556.sbd.miller track 7 'Estimated Prophet Jam'",
    "gd-1974-09-18": "archive.org: 'Soundcheck: Jerry Space, Cumberland Blues, Brokedown Palace'",
    "gd-1980-12-30": "archive.org (Paul Scotton): 'Set up was done on the fly with the soundcheck already underway'",
    "gd-1988-09-23": "archive.org: 'Soundcheck Setlist: Every Time You Go, What's Goin' On'",
    "gd-1991-03-20": "archive.org: 'Soundcheck: Might As Well (multiple takes)'",
    "gd-1993-06-25": "archive.org: 'Soundcheck: Ain't That Peculiar, New Speedway Boogie, Lucy In The Sky With Diamonds'",
    "gd-1993-12-13": "archive.org: 'Soundcheck: Piano and drum machine, Mississippi Half Step, I Fought The Law'",
    "gd-1994-03-23": "archive.org: 'Soundcheck: Might As Well Take 1, Chord School, Might As Well Take 2, Take 3'",
    "gd-1994-04-06": "archive.org: soundcheck tape 'Tuning, Comes A Time > The Days Between Intro', listed as Soundcheck",
    "gd-1994-07-26": "archive.org: 'Soundcheck: Drummers join Vince Bob & Phil, Vince little keyboard jam'",
    "gd-1995-03-17": "archive.org: 'Several takes of Unbroken Chain were done for soundcheck/rehearsal'",
    "gd-1995-06-21": "archive.org: 'Soundcheck: Vince on piano solo, It's All Too Much (three takes)'",
    "gd-1995-06-30": "archive.org: 'Soundcheck: It's A Man's World, Truckin''",
    # Second pass (2026-11-16): JerryBase (jerrybase.com/events/<date>) labels each
    # of these first sets a soundcheck; none of the songs is on any archive.org
    # tape of the show itself unless noted.
    "gd-1971-10-21": "JerryBase: 'Soundcheck: Get Back'; shared on The Tapers Section 2007-05-28",
    "gd-1972-04-07": "JerryBase: 'Soundcheck: Hey Bo Diddley, Mr. Charlie, Tennessee Jed, Looks Like Rain' (recollection on dead.net, per Jesse Jarnow)",
    "gd-1972-04-17": "JerryBase: 'Partial Soundcheck: Uncle John's Band'",
    "gd-1972-05-16": "JerryBase: 'Soundcheck: Big River, Sugar Magnolia'; archive.org gd1972-05-16.141754 lists the same soundcheck",
    "gd-1972-09-26": "JerryBase: 'Soundcheck: Box Of Rain, Cumberland Blues, Around And Around, Jack Straw' (setlist from taper Jay Kerley)",
    "gd-1973-02-19": "JerryBase: 'Soundcheck: Uncle John's Band'",
    "gd-1974-06-18": "JerryBase: 'Soundcheck: They Love Each Other, U.S. Blues'",
    "gd-1976-06-14": "JerryBase: 'Partial Soundcheck: U.S. Blues, Not Fade Away, Cold Rain And Snow' (soundcheck video exists)",
    "gd-1976-12-31": "JerryBase: 'Soundcheck: River Deep Mountain High', per Alex Allan",
    "gd-1978-04-10": "JerryBase: 'Soundcheck: Salt Lake City'",
    "gd-1979-12-26": "JerryBase: 'Soundcheck: Brokedown Palace, Black Throated Wind'; archive.org: soundcheck recorded by David Gans",
    "gd-1980-05-02": "JerryBase: 'Soundcheck: Morning Dew'",
    "gd-1980-12-31": "JerryBase: 'Acoustic Soundcheck: Young Blood'",
    "gd-1981-03-20": "JerryBase: 'Soundcheck: Man Smart (Woman Smarter), Althea, Lost Sailor > Saint Of Circumstance'; archive.org gd1981-03-20.sndchk.aud.seaweed.113433",
    "gd-1983-03-29": "JerryBase: 'Soundcheck: Comes A Time, China Doll' (from Mike Dolgushkin)",
    "gd-1983-10-09": "JerryBase: 'Soundcheck: Saint Stephen' (DLeopold at Lost Live Dead, confirmed by an eyewitness)",
    "gd-1983-10-22": "JerryBase: 'Soundcheck: Here Comes Sunshine' (eyewitness, no tape)",
    "gd-1986-03-23": "JerryBase: 'Soundcheck: I Heard It Through The Grapevine'",
    "gd-1987-03-26": "JerryBase: 'Partial Soundcheck: Cumberland Blues' (seen in Grateful Dead Home Movies 1980s-90s)",
    "gd-1987-06-30": "JerryBase: 'Partial Soundcheck: Bertha' (Tyler Roy-Hart heard it)",
    "gd-1989-04-17": "JerryBase: 'Partial Soundcheck: Lost Sailor' (Willie Culkin heard it three times)",
    "gd-1990-03-24": "JerryBase: 'Soundcheck: The Weight' (Minches saw the soundcheck)",
    "gd-1993-02-22": "JerryBase: 'Soundcheck: The Days Between'; the first public performance is in the second set",
    "gd-1993-03-24": "JerryBase: 'Soundcheck: Whiskey In The Jar' (smarcus, WELL)",
    "gd-1993-03-28": "JerryBase: 'Soundcheck: Whiskey In The Jar, Alabama Bound'",
    "gd-1994-12-11": "JerryBase lists no Saint Stephen for this show, and none of its three archive.org tapes has it",
    "gd-1995-03-22": "JerryBase: 'Soundcheck: Watchin' The Wheels'",
    "gd-1995-06-24": "JerryBase: 'Soundcheck: Into The Mystic, Black Muddy River, Wang Dang Doodle' (eyewitnesses Dan Sokulski, Josh Davis)",
    # Third pass: shows with an extra set ahead of the show, found by set count;
    # archive.org tape notes name it a soundcheck or rehearsal.
    "gd-1973-12-12": "archive.org gd1973-12-12.sbd.miller.124585: 'Sound check: Sleigh Ride. Rip It Up. Blue Suede Shoes. Peggy-O, Jack Straw, Cumberland Blues, 30 Days'",
    "gd-1976-07-12": "archive.org gd1976-07-12.sbd.unknown.10362: 'Soundcheck: Dancin in the Streets, They Love Each Other, The Music Never Stopped (x2), Stella Blue (x7), Let It Grow jam, Eyes of the World'",
    "gd-1993-03-17": "archive.org gd1993-03-17.snchk.miller.34421 and gd1993-03-17.aud-schk.unknown.86711: soundcheck of The Days Between, Wave To The Wind, Lucy In The Sky, I Fought The Law",
    "gd-1993-03-31": "archive.org gd93-03-31.soundcheck.kenk-tmnsp.31000: 'Cumberland Blues, Lazy River Road, I Fought The Law ... Soundcheck'",
    "gd-1994-02-25": "archive.org gd1994-02-25.141174.mk4.ebel: 'Soundcheck: Lucy In The Sky With Diamonds, Like a Rolling Stone, Phil, Bob & Vince Jam, Lazy River Road, Liberty, Rain'; gd1994-02-25.rehearsal.fm-sbd.gmb.91250",
    "gd-1994-09-16": "archive.org gd1994-09-16.141688: 'Soundcheck: It Takes A Lot To Laugh It Takes A Train To Cry, I Want To Tell You, Childhood's End, Attics Of My Life'",
    "gd-1995-05-24": "archive.org gd1995-05-24.141527: 'Soundcheck: Tough Mama, Childhood's End, Rain'; gd1995-05-24.sndchk.fm.gmb.91237",
    "gd-1995-07-02": "archive.org gd1995-07-02.139737: 'Soundcheck: Hoochie Coochie Man, Death Don't Have No Mercy, Visions Of Johanna, Here Comes Sunshine'; gd1995-07-02.soundcheck.fm.gmb.91256",
}


def _read(name: str) -> tuple[list[str], list[dict[str, str]]]:
    with (CANONICAL / name).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _write(name: str, fields: list[str], rows: list[dict[str, str]]) -> None:
    with (CANONICAL / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _saved() -> list[dict]:
    if not REMOVED.exists():
        return []
    return [json.loads(line) for line in REMOVED.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    # Safe to run again: a show whose soundcheck is already saved is not touched twice.
    saved = _saved()
    done = {record["row"]["show_id"] for record in saved if record["file"] == "performances.csv"}
    shows = {show_id for show_id in EVIDENCE if show_id not in done}
    fields, rows = _read("performances.csv")
    removed = [row for row in rows if row["show_id"] in shows and row["set_number"] == "1"]
    gone = {row["performance_id"] for row in removed}
    kept = []
    for row in rows:
        if row["performance_id"] in gone:
            continue
        if row["show_id"] in shows:
            number = int(row["set_number"]) - 1
            row = {**row, "set_number": str(number), "set_label": f"Set {number}"}
        kept.append(row)
    _write("performances.csv", fields, kept)

    records = [{"file": "performances.csv", "row": row, "evidence": EVIDENCE[row["show_id"]]} for row in removed]
    for name in sorted(path.name for path in CANONICAL.glob("*.csv")):
        if name == "performances.csv":
            continue
        other_fields, other_rows = _read(name)
        if "performance_id" not in other_fields:
            continue
        dropped = [row for row in other_rows if row.get("performance_id") in gone]
        if dropped:
            _write(name, other_fields, [row for row in other_rows if row.get("performance_id") not in gone])
            records += [{"file": name, "row": row} for row in dropped]

    # A song heard only in these soundchecks leaves the catalog with them, along
    # with the rows that point at it. A release track keeps its row and title
    # with no song link, as tracks of songs the Dead never played already do
    # (Young Blood on a Kingfish album, Whiskey in the Jar on Shady Grove).
    soundcheck_songs = {r["row"]["song_id"] for r in saved if r["file"] == "performances.csv"} | {r["song_id"] for r in removed}
    played = {row["song_id"] for row in kept}
    song_fields, songs = _read("songs.csv")
    orphans = {row["song_id"] for row in songs if row["song_id"] in soundcheck_songs and row["song_id"] not in played}
    if orphans:
        _write("songs.csv", song_fields, [row for row in songs if row["song_id"] not in orphans])
        records += [{"file": "songs.csv", "row": row} for row in songs if row["song_id"] in orphans]
        for name in sorted(path.name for path in CANONICAL.glob("*.csv")):
            if name in ("songs.csv", "performances.csv"):
                continue
            other_fields, other_rows = _read(name)
            if "song_id" not in other_fields:
                continue
            if name == "official_release_tracks.csv":
                unlinked = [row for row in other_rows if row["song_id"] in orphans]
                if unlinked:
                    _write(name, other_fields, [{**row, "song_id": ""} if row["song_id"] in orphans else row for row in other_rows])
                    records += [{"file": name, "row": row, "change": "song_id cleared"} for row in unlinked]
                continue
            dropped = [row for row in other_rows if row.get("song_id") in orphans]
            if dropped:
                _write(name, other_fields, [row for row in other_rows if row.get("song_id") not in orphans])
                records += [{"file": name, "row": row} for row in dropped]

    REMOVED.parent.mkdir(parents=True, exist_ok=True)
    with REMOVED.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"removed {len(removed)} soundcheck performances from {len({r['show_id'] for r in removed})} shows, "
          f"{len(orphans)} songs heard only in soundchecks, and {len(records) - len(removed) - len(orphans)} other rows; "
          f"saved to {REMOVED.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
