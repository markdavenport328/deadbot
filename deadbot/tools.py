"""Read-only tools exposed to the agent loop."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import BaseTool, tool

from deadbot.data import CanonicalStore


def _json(value: Any) -> str:
    """Serialize a lean tool payload for the local-model context window."""

    def compact(item: Any) -> Any:
        if isinstance(item, dict):
            return {key: compact(nested) for key, nested in item.items() if nested not in (None, "")}
        if isinstance(item, list):
            return [compact(nested) for nested in item]
        return item

    return json.dumps(compact(value), ensure_ascii=False, separators=(",", ":"))


def build_tools(store: CanonicalStore) -> list[BaseTool]:
    """Build read-only, provenance-aware tools bound to one canonical store."""

    @tool
    def search_entities(query: str) -> str:
        """Find canonical songs, shows, performers, and venues matching a user phrase.

        Use this before other entity tools when an ID is unknown or ambiguous.
        Returns stable IDs and display names only; it never searches the web.
        """
        words = query.casefold().split()
        stop_words = {"a", "an", "and", "at", "for", "in", "of", "on", "the", "to"}
        phrases = [query]
        # A user often combines entities (for example, "Veneta Bird Song").
        # Search meaningful contiguous phrases as well as the full question so
        # the agent receives both the show and song IDs it needs to continue.
        for size in range(min(3, len(words)), 0, -1):
            for start in range(len(words) - size + 1):
                phrase = " ".join(words[start : start + size])
                if (
                    (size > 1 and len(phrase) >= 3)
                    or (size == 1 and len(phrase) >= 4)
                ) and phrase not in stop_words and phrase not in phrases:
                    phrases.append(phrase)

        matches = []
        seen = set()

        def add(entity_type: str, entity_id: str, label: str) -> None:
            key = (entity_type, entity_id)
            if key not in seen:
                seen.add(key)
                matches.append({"entity_type": entity_type, "id": entity_id, "label": label})

        for table, fields, id_field, label_field in [
            ("songs", ("title", "slug"), "song_id", "title"),
            ("people", ("name",), "person_id", "name"),
            ("venues", ("name", "city", "state_region"), "venue_id", "name"),
        ]:
            for phrase in phrases:
                for row in store.matching_rows(table, phrase, fields)[:10]:
                    add(table[:-1], row[id_field], row[label_field])

        venues = store.by_id.get("venues", {})
        for show in store.rows("shows"):
            venue = venues.get(show["venue_id"], {})
            searchable = " ".join(
                [show["show_id"], show["show_date"], show.get("event_name", ""), show.get("tour_name", ""), venue.get("name", ""), venue.get("city", ""), venue.get("state_region", "")]
            ).casefold()
            if any(phrase.casefold() in searchable for phrase in phrases):
                add("show", show["show_id"], f'{show["show_date"]} — {venue.get("name", "Unknown venue")}')
        return _json({"query": query, "matches": matches[:20]})

    @tool
    def get_song(song_id_or_title: str) -> str:
        """Get one song's canonical data, resource links, arrangements, and known performances.

        Use the returned resource URLs for interviews, articles, tabs, or other
        context. Treat source notes and interviews as attributed material.
        """
        song = store.resolve_song(song_id_or_title)
        if not song:
            return _json({"error": "Song not found or ambiguous", "query": song_id_or_title})
        return _json(store.song_context(song))

    @tool
    def get_show(show_id_or_date: str) -> str:
        """Get a show's canonical data, venue, ordered performances, recording metadata, and links.

        Use a canonical show ID or an unambiguous date such as 1972-08-27.
        """
        show = store.resolve_show(show_id_or_date)
        if not show:
            return _json({"error": "Show not found or ambiguous", "query": show_id_or_date})
        return _json(store.show_context(show))

    @tool
    def get_performance(performance_id: str) -> str:
        """Get one rendition's song/show context, performance-specific sources, recordings, and media links.

        Performance-specific commentary concerns this rendition only and must
        not be generalized to every performance of the song.
        """
        context = store.performance_context(performance_id)
        if not context:
            return _json({"error": "Performance not found", "performance_id": performance_id})
        return _json(context)

    @tool
    def get_media_links(entity_type: str, entity_id: str) -> str:
        """Get listening and viewing links for a canonical show or performance.

        entity_type must be either 'show' or 'performance'. For a show, use a
        canonical ID or unambiguous date such as 1972-08-27. URLs are external
        link-outs; do not claim they prove facts beyond their stored metadata.
        """
        if entity_type == "show":
            show = store.resolve_show(entity_id)
            if not show:
                return _json({"error": "Show not found or ambiguous", "query": entity_id})
            show_id = show["show_id"]
            return _json({"show_id": show_id, "links": [row for row in store.rows("show_links") if row["show_id"] == show_id]})
        if entity_type == "performance":
            if not store.performance_context(entity_id):
                return _json({"error": "Performance not found", "performance_id": entity_id})
            return _json({"performance_id": entity_id, "links": [row for row in store.rows("performance_links") if row["performance_id"] == entity_id]})
        return _json({"error": "entity_type must be 'show' or 'performance'"})

    return [search_entities, get_song, get_show, get_performance, get_media_links]
