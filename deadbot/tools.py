"""Read-only tools exposed to the agent loop."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timezone
from functools import lru_cache
from http.client import HTTPException as HTTPClientException
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from langchain_core.tools import BaseTool, tool

from deadbot.data import CanonicalStore
from deadbot.deadnet import (
    DeadnetConfig,
    DeadnetResearchAdapter,
    EntityReadRequest,
    EntitySearchRequest,
    EntityType,
    UrlLibMetadataTransport,
)
from deadbot.source_registry import RegistryValidationError, load_registry
from deadbot.lore_source_trails import source_trails_for_entity
from deadbot.selection_signals import (
    SelectionSignalError,
    load_selection_signals,
    load_show_selections,
)
from deadbot.site_search import SiteSearcher
from deadbot.source_reader import PageReader, default_reader


OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
USNO_RISE_SET_URL = "https://aa.usno.navy.mil/api/rstt/oneday"


class ExternalServiceError(RuntimeError):
    """A safe, user-facing failure from a read-only external data source."""


def _fetch_json(url: str) -> dict[str, Any]:
    """Fetch one JSON object without adding a third-party HTTP dependency."""

    request = Request(url, headers={"User-Agent": "Deadbot/0.1 (historical-show-context)"})
    try:
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, HTTPClientException) as error:
        raise ExternalServiceError("The external historical-data service was unavailable.") from error
    if not isinstance(payload, dict):
        raise ExternalServiceError("The external historical-data service returned an unexpected response.")
    if payload.get("error") is True:
        raise ExternalServiceError(str(payload.get("reason") or "The external service returned an error."))
    return payload


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _show_date(show: dict[str, str]) -> date:
    return date.fromisoformat(show["show_date"])


@lru_cache(maxsize=128)
def _geocode(query: str) -> dict[str, Any]:
    url = f"{OPEN_METEO_GEOCODING_URL}?{urlencode({'name': query, 'count': 1, 'language': 'en', 'format': 'json'})}"
    payload = _fetch_json(url)
    results = payload.get("results")
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        raise ExternalServiceError(f"No coordinates were found for {query}.")
    result = results[0]
    if not isinstance(result.get("latitude"), (int, float)) or not isinstance(result.get("longitude"), (int, float)):
        raise ExternalServiceError(f"The geocoder returned no usable coordinates for {query}.")
    return result


def _unresolved_show_payload(store: CanonicalStore, identifier: str) -> dict[str, Any]:
    """Distinguish an unknown show from a date with multiple shows.

    Sixties dates often carry an early and a late show. Returning the concrete
    candidates lets the model choose the right show_id or ask the visitor,
    instead of hitting a dead end on a date the library actually covers.
    """

    candidates = store.show_candidates(identifier)
    if len(candidates) < 2:
        return {"error": "Show not found", "query": identifier}
    summaries = []
    for show in candidates[:8]:
        venue = store.one("venues", show.get("venue_id", "")) or {}
        summaries.append(
            {
                "show_id": show["show_id"],
                "show_date": show.get("show_date", ""),
                "venue_name": venue.get("name", ""),
                "city": venue.get("city", ""),
                "state_region": venue.get("state_region", ""),
                "event_name": show.get("event_name", ""),
            }
        )
    return {
        "error": "Multiple shows match. Choose one candidate show_id and call the tool again.",
        "query": identifier,
        "candidates": summaries,
    }


def _show_location(store: CanonicalStore, identifier: str) -> tuple[dict[str, str], dict[str, Any]] | None:
    """Resolve a show and its venue to coordinates, including a geocoder fallback."""

    show = store.resolve_show(identifier)
    if not show:
        return None
    venue = store.one("venues", show["venue_id"]) or {}
    latitude = venue.get("latitude", "").strip()
    longitude = venue.get("longitude", "").strip()
    if latitude and longitude:
        location = {
            "name": ", ".join(part for part in (venue.get("city"), venue.get("state_region"), venue.get("country")) if part),
            "latitude": float(latitude),
            "longitude": float(longitude),
            "timezone": "",
            "source": "canonical venue coordinates",
        }
    else:
        query = ", ".join(
            part for part in (venue.get("city"), venue.get("state_region"), venue.get("country")) if part
        )
        if not query:
            raise ExternalServiceError("The show's venue has no location details to geocode.")
        geocoded = _geocode(query)
        location = {
            "name": geocoded.get("name") or query,
            "latitude": geocoded["latitude"],
            "longitude": geocoded["longitude"],
            "timezone": geocoded.get("timezone", ""),
            "country": geocoded.get("country", ""),
            "source": "Open-Meteo Geocoding API",
        }
    return show, location


def _location_payload(location: dict[str, Any]) -> dict[str, Any]:
    return {
        key: location[key]
        for key in ("name", "latitude", "longitude", "timezone", "country", "source")
        if location.get(key) not in (None, "")
    }


def _timezone_offset(location: dict[str, Any], requested_date: date) -> float:
    timezone_name = location.get("timezone")
    if not timezone_name:
        return 0
    try:
        offset = datetime.combine(requested_date, time(12), tzinfo=ZoneInfo(timezone_name)).utcoffset()
    except (KeyError, ValueError):
        return 0
    hours = (offset or timezone.utc.utcoffset(None)).total_seconds() / 3600
    return int(hours) if hours.is_integer() else hours


def _weather_description(code: Any) -> str | None:
    descriptions = {
        0: "clear sky",
        1: "mainly clear",
        2: "partly cloudy",
        3: "overcast",
        45: "fog",
        48: "depositing rime fog",
        51: "light drizzle",
        53: "moderate drizzle",
        55: "dense drizzle",
        61: "slight rain",
        63: "moderate rain",
        65: "heavy rain",
        71: "slight snow",
        73: "moderate snow",
        75: "heavy snow",
        80: "slight rain showers",
        81: "moderate rain showers",
        82: "violent rain showers",
        95: "thunderstorm",
        96: "thunderstorm with slight hail",
        99: "thunderstorm with heavy hail",
    }
    try:
        return descriptions.get(int(code))
    except (TypeError, ValueError):
        return None


def _daily_value(daily: dict[str, Any], key: str) -> Any:
    values = daily.get(key)
    return values[0] if isinstance(values, list) and values else None


def _astrology_sign(requested_date: date) -> dict[str, str]:
    month_day = (requested_date.month, requested_date.day)
    signs = [
        ((3, 21), (4, 19), "Aries", "fire", "cardinal", "Mars"),
        ((4, 20), (5, 20), "Taurus", "earth", "fixed", "Venus"),
        ((5, 21), (6, 20), "Gemini", "air", "mutable", "Mercury"),
        ((6, 21), (7, 22), "Cancer", "water", "cardinal", "Moon"),
        ((7, 23), (8, 22), "Leo", "fire", "fixed", "Sun"),
        ((8, 23), (9, 22), "Virgo", "earth", "mutable", "Mercury"),
        ((9, 23), (10, 22), "Libra", "air", "cardinal", "Venus"),
        ((10, 23), (11, 21), "Scorpio", "water", "fixed", "Mars/Pluto"),
        ((11, 22), (12, 21), "Sagittarius", "fire", "mutable", "Jupiter"),
        ((12, 22), (12, 31), "Capricorn", "earth", "cardinal", "Saturn"),
        ((1, 1), (1, 19), "Capricorn", "earth", "cardinal", "Saturn"),
        ((1, 20), (2, 18), "Aquarius", "air", "fixed", "Saturn/Uranus"),
        ((2, 19), (3, 20), "Pisces", "water", "mutable", "Jupiter/Neptune"),
    ]
    for start, end, name, element, modality, ruler in signs:
        if start <= month_day <= end:
            return {"sign": name, "element": element, "modality": modality, "traditional_ruler": ruler}
    raise ValueError(f"Could not determine a zodiac sign for {requested_date.isoformat()}.")


def _json(value: Any) -> str:
    """Serialize a lean tool payload for the local-model context window."""

    def compact(item: Any) -> Any:
        if isinstance(item, dict):
            return {key: compact(nested) for key, nested in item.items() if nested not in (None, "")}
        if isinstance(item, list):
            return [compact(nested) for nested in item]
        return item

    return json.dumps(compact(value), ensure_ascii=False, separators=(",", ":"))


def _adapter_from_reviewed_source(source_id: str, *, needs_search: bool = False) -> DeadnetResearchAdapter | None:
    """Create the one reviewed metadata adapter from the local registry seed.

    The registry remains the policy source: a missing, invalid, or unapproved
    entry disables this optional research path rather than widening access.
    """

    try:
        sources = {source["source_id"]: source for source in load_registry()}
        source = sources[source_id]
    except (KeyError, RegistryValidationError):
        return None
    if (
        source.get("review_state") != "approved"
        or source.get("access_state") != "allowed"
        or "read" not in source.get("allowed_operations", [])
        or (needs_search and "search" not in source.get("allowed_operations", []))
    ):
        return None
    policies = source.get("operation_policies", {})
    paths = tuple(
        path
        for policy in policies.values()
        if isinstance(policy, dict)
        for path in policy.get("paths", [])
        if isinstance(path, str)
    )
    hosts = frozenset(source.get("host_allowlist", []))
    if not paths or not hosts:
        return None
    config = DeadnetConfig(
        base_url="https://www.dead.net",
        allowed_hosts=hosts,
        allowed_paths=paths,
        search_path="/search" if "/search" in paths else paths[0],
        max_results=10 if needs_search else 1,
    )
    return DeadnetResearchAdapter(UrlLibMetadataTransport(hosts), config)


def _reviewed_deadnet_adapter() -> DeadnetResearchAdapter | None:
    return _adapter_from_reviewed_source("deadnet-editorial", needs_search=True)


def _reviewed_deadcast_adapter() -> DeadnetResearchAdapter | None:
    return _adapter_from_reviewed_source("deadcast-metadata")


def build_tools(
    store: CanonicalStore,
    *,
    page_reader: PageReader | None = None,
    site_searcher: SiteSearcher | None = None,
) -> list[BaseTool]:
    """Build read-only, grounded tools bound to one canonical store.

    ``page_reader`` and ``site_searcher`` are injectable so tests can drive the
    research tools with fixture pages instead of the network.
    """

    deadnet_adapter = _reviewed_deadnet_adapter()
    deadcast_adapter = _reviewed_deadcast_adapter()
    reader = page_reader or default_reader()
    searcher = site_searcher or SiteSearcher()

    @tool
    def search_entities(query: str) -> str:
        """Find canonical songs, shows, people, equipment, and venues matching a user phrase.

        Use this before other entity tools when an ID is unknown or ambiguous.
        The people search covers the whole canonical people table, including
        people who appear only in guest credits. Use search_guest_musicians
        when the distinction between a guest credit and the regular lineup is
        material. Returns stable IDs and display names only; it never searches
        the web.
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

        for phrase in phrases:
            for item in store.matching_rows("equipment", phrase, ("name", "manufacturer", "model"))[:10]:
                add("equipment", item["equipment_id"], item["name"])

        for show in store.search_shows(phrases, limit=20):
            add(
                "show",
                show["show_id"],
                f'{show["show_date"]} — {show.get("venue_name", "Unknown venue")}',
            )
        return _json({"query": query, "matches": matches[:20]})

    @tool
    def search_guest_musicians(query: str = "") -> str:
        """Find guest musicians and their documented Grateful Dead show appearances.

        A name or phrase narrows the results. Each appearance includes its show,
        venue, location, credited instruments, and any known participation scope.
        """
        needle = query.casefold().strip()
        people = {person["person_id"]: person for person in store.rows("people")}
        shows = {show["show_id"]: show for show in store.rows("shows")}
        venues = {venue["venue_id"]: venue for venue in store.rows("venues")}
        # JerryBase sometimes appends a participation qualifier to a person's
        # display name (for example, ``Branford Marsalis (complete show)``).
        # That qualifier describes the appearance, not a second human being.
        # Collapse legacy rows here as well as at import time so an operational
        # database created from an older snapshot still returns one identity.
        canonical_people_by_name = {
            person.get("name", "").casefold(): person
            for person in people.values()
            if person.get("name") and not re.search(r"\s+\(complete show\)\s*$", person["name"], re.IGNORECASE)
        }

        def canonical_person(person_id: str) -> tuple[str, dict[str, str], str | None]:
            person = people[person_id]
            source_name = person.get("name", person_id)
            match = re.search(r"\s+\((complete show)\)\s*$", source_name, re.IGNORECASE)
            if not match:
                return person_id, person, None
            base_name = source_name[: match.start()].strip()
            canonical = canonical_people_by_name.get(base_name.casefold())
            if canonical:
                return canonical["person_id"], canonical, match.group(1).casefold()
            return person_id, {**person, "name": base_name}, match.group(1).casefold()

        by_person: dict[str, list[dict[str, str | None]]] = {}
        for assignment in store.rows("show_performers"):
            if assignment.get("role") == "guest" and assignment.get("person_id") in people:
                person_id, _, participation_scope = canonical_person(assignment["person_id"])
                if not participation_scope:
                    scope_match = re.search(
                        r"JerryBase source participation scope:\s*([^.;]+)",
                        assignment.get("notes", ""),
                        re.IGNORECASE,
                    )
                    participation_scope = scope_match.group(1).strip().casefold() if scope_match else None
                by_person.setdefault(person_id, []).append(
                    {**assignment, "participation_scope": participation_scope}
                )
        guests = []
        for person_id, assignments in by_person.items():
            _, person, _ = canonical_person(person_id)
            person_name = person.get("name", person_id)
            query_words = {
                word
                for word in re.findall(r"[a-z0-9]+", needle)
                if len(word) >= 4 and word not in {"many", "times", "play", "played", "with", "them", "show", "shows"}
            }
            name_words = set(re.findall(r"[a-z0-9]+", person_name.casefold()))
            if needle and needle not in person_name.casefold() and needle not in person_id.casefold() and not (query_words & name_words):
                continue
            appearances_by_show: dict[str, dict[str, Any]] = {}
            for assignment in assignments:
                show = shows.get(assignment.get("show_id", ""))
                if not show:
                    continue
                venue = venues.get(show.get("venue_id", ""), {})
                venue_name = venue.get("name") or None
                location = ", ".join(
                    part for part in (venue.get("city"), venue.get("state_region")) if part
                ) or None
                appearance = appearances_by_show.setdefault(
                    show["show_id"],
                    {
                        "show_id": show["show_id"],
                        "show_date": show.get("show_date"),
                        "venue_name": venue_name,
                        "location": location,
                        "instruments": [],
                        "participation_scope": assignment.get("participation_scope"),
                    },
                )
                instrument = assignment.get("instrument")
                if instrument and instrument not in appearance["instruments"]:
                    appearance["instruments"].append(instrument)
                if assignment.get("participation_scope"):
                    appearance["participation_scope"] = assignment["participation_scope"]
            appearances = sorted(
                appearances_by_show.values(),
                key=lambda appearance: (appearance.get("show_date") or "", appearance["show_id"]),
            )
            guests.append(
                {
                    "person_id": person_id,
                    "name": person_name,
                    "guest_show_count": len(appearances),
                    "appearances": appearances,
                }
            )
        guests.sort(key=lambda guest: guest["name"].casefold())
        return _json(
            {
                "query": query,
                "guests": guests,
            }
        )

    @tool
    def search_stored_resources(query: str) -> str:
        """Search all locally cataloged external links and their provenance notes.

        This is the broadest local route to interviews, oral histories,
        eyewitness accounts, official features, song history, release context,
        and other anecdotal material already cataloged for Grateful Dead topics.
        It searches resource title, creator, source, type, and catalog notes;
        results identify their song, show, or performance relationships when
        known. Returned links are metadata and source descriptions, not the
        source text or proof of a claim beyond that description.
        """
        needle = query.casefold().strip()
        if not needle:
            return _json({"query": query, "resources": [], "message": "A topic or source phrase is required."})
        query_words = {
            word for word in re.findall(r"[a-z0-9]+", needle)
            if len(word) >= 4 and word not in {"about", "commentary", "community", "source", "sources"}
        }
        song_ids_by_resource: dict[str, list[str]] = {}
        show_ids_by_resource: dict[str, list[str]] = {}
        performance_ids_by_resource: dict[str, list[str]] = {}
        for relation, destination in (
            ("resource_songs", song_ids_by_resource),
            ("resource_shows", show_ids_by_resource),
            ("resource_performances", performance_ids_by_resource),
        ):
            id_field = {"resource_songs": "song_id", "resource_shows": "show_id", "resource_performances": "performance_id"}[relation]
            for row in store.rows(relation):
                resource_id, entity_id = row.get("resource_id"), row.get(id_field)
                if resource_id and entity_id:
                    destination.setdefault(resource_id, []).append(entity_id)
        resources = []
        for resource in store.rows("resources"):
            searchable = " ".join(
                resource.get(field, "")
                for field in ("title", "creator", "source_name", "resource_type", "notes")
            ).casefold()
            if needle not in searchable and not any(word in searchable for word in query_words):
                continue
            parsed = urlparse(resource.get("source_url", ""))
            if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
                continue
            resource_id = resource["resource_id"]
            resources.append(
                {
                    "resource_id": resource_id,
                    "title": resource.get("title"),
                    "resource_type": resource.get("resource_type"),
                    "creator": resource.get("creator") or None,
                    "source_name": resource.get("source_name"),
                    "url": resource["source_url"],
                    "notes": resource.get("notes") or None,
                    "song_ids": song_ids_by_resource.get(resource_id, []),
                    "show_ids": show_ids_by_resource.get(resource_id, []),
                    "performance_ids": performance_ids_by_resource.get(resource_id, []),
                }
            )
        return _json(
            {
                "query": query,
                "coverage_note": "All matching cataloged resource metadata; source text is not retrieved.",
                "resources": resources,
            }
        )

    @tool
    def get_song(song_id_or_title: str) -> str:
        """Get one song's canonical data, resource links, arrangements, and known performances.

        Use the returned resource URLs for interviews, articles, tabs, or other
        context. Treat source notes and interviews as attributed material. Each
        performance may carry a `listen` object with an archive track URL and,
        when mapped, a release track URL, ready to offer as a listening link.
        """
        song = store.resolve_song(song_id_or_title)
        if not song:
            return _json({"error": "Song not found or ambiguous", "query": song_id_or_title})
        return _json(store.song_context(song))

    @tool
    def get_song_performance_profile(song_id_or_title: str) -> str:
        """Get derived counts, dated endpoints, and frequent set neighbors for a song.

        This is an on-demand observation of the current documented library.
        It is not editorial lore, a complete band-history total, or a ranking
        of the best performance. Neighbor counts include their denominator.
        """
        song = store.resolve_song(song_id_or_title)
        if not song:
            return _json({"error": "Song not found or ambiguous", "query": song_id_or_title})
        return _json(store.song_performance_profile(song))

    @tool
    def get_deadnet_song_context(song_id_or_title: str) -> str:
        """Find the reviewed Dead.net metadata page for one canonical song.

        Use after resolving a song when an outside editorial or lyric/source
        trail could make an answer more useful. This tool returns only a
        title, link, and short page metadata for the main panel; it does not
        retrieve article text, lyrics, audio, or a verdict about the song.
        Do not use it for every direct factual question.
        """
        song = store.resolve_song(song_id_or_title)
        if not song:
            return _json({"error": "Song not found or ambiguous", "query": song_id_or_title})
        if deadnet_adapter is None:
            return _json(
                {
                    "research": {
                        "state": "unavailable",
                        "coverage": "metadata_only",
                        "source": "dead.net",
                        "message": "The reviewed Dead.net metadata adapter is not enabled.",
                    }
                }
            )
        result = deadnet_adapter.read(
            EntityReadRequest(entity_type=EntityType.SONG, identifier=song["slug"])
        )
        return _json(
            {
                "song": song,
                "research": {
                    "state": result.state.value,
                    "coverage": result.coverage,
                    "source": result.source,
                    "message": result.message,
                    "requested": dict(result.requested),
                    "records": [
                        {
                            "entity_type": record.entity_type,
                            "identifier": record.identifier,
                            "title": record.title,
                            "url": record.url,
                            "description": record.description,
                            "published_at": record.published_at,
                            "source": record.source,
                        }
                        for record in result.records
                    ],
                },
            }
        )

    # Note: a search_deadnet_editorial tool used to live here. Dead.net's site
    # search is Google-powered and runs in the browser, so the adapter only ever
    # returned the "Search Results" page title. It was removed on 2026-09-04 so
    # the model does not spend a research round on it; Dead.net pages are
    # reached through stored links, get_deadnet_song_context, and read_page.

    @tool
    def get_deadcast_metadata(episode_id_or_slug: str) -> str:
        """Read metadata for one official Deadcast episode.

        Returns only the episode title, link, and short page metadata. It never
        retrieves or returns transcript, article body, or audio content.
        Use a slug or identifier from an official Deadcast link.
        """
        identifier = episode_id_or_slug.strip()
        if not identifier:
            return _json({"research": {"state": "invalid", "coverage": "metadata_only", "source": "dead.net", "message": "An episode identifier is required."}})
        if deadcast_adapter is None:
            return _json({"research": {"state": "unavailable", "coverage": "metadata_only", "source": "dead.net", "message": "The reviewed Deadcast metadata adapter is not enabled."}})
        result = deadcast_adapter.read(EntityReadRequest(entity_type=EntityType.DEADCAST, identifier=identifier))
        return _json({
            "research": {
                "state": result.state.value,
                "coverage": result.coverage,
                "source": result.source,
                "message": result.message,
                "requested": dict(result.requested),
                "records": [
                    {"entity_type": record.entity_type, "identifier": record.identifier,
                     "title": record.title, "url": record.url, "description": record.description,
                     "published_at": record.published_at, "source": record.source}
                    for record in result.records
                ],
            }
        })

    @tool
    def get_lore_source_trails(entity_type: str, entity_id_or_name: str) -> str:
        """Return reviewed, metadata-only lore links for one canonical song or show.

        Use after resolving an entity when the visitor's question invites
        history, evolution, reputation, or show-context color. This offline
        catalog supplies source titles, URLs, themes, and why-to-open hints;
        it does not contain source text or canonical facts. Use the canonical
        tools for the direct answer first, and treat linked editorial claims
        as attributed until separately researched.
        """
        if entity_type == "song":
            entity = store.resolve_song(entity_id_or_name)
        elif entity_type == "show":
            entity = store.resolve_show(entity_id_or_name)
        else:
            return _json({"research": {"state": "invalid", "coverage": "metadata_only", "records": [], "message": "entity_type must be song or show."}})
        if not entity:
            return _json({"research": {"state": "empty", "coverage": "metadata_only", "records": [], "message": "Canonical entity not found or ambiguous.", "query": entity_id_or_name}})
        entity_id = entity["song_id"] if entity_type == "song" else entity["show_id"]
        result = source_trails_for_entity(entity_type, entity_id)
        return _json({"entity": {"entity_type": entity_type, "entity_id": entity_id}, "research": result})

    @tool
    def find_arrangements(key_signature: str) -> str:
        """Find source-documented song arrangements in one key, such as B, E, or A minor.

        Use this for musician questions about keys, transpositions, charts, or
        songs to cover. Results describe only arrangements whose source records
        that key; never say the abstract song is universally in that key. Use
        get_song on a returned song when the visitor wants its full chord/tab
        resource, lyrics-source link, or performance history.
        """
        key = key_signature.strip()
        if not key:
            return _json({"error": "A key signature is required."})
        return _json(store.arrangement_search(key))

    @tool
    def get_equipment_history(equipment_id_or_name: str) -> str:
        """Get the first and last documented Grateful Dead show assignments for a named instrument.

        Use this before answering questions such as when Jerry first or last
        played Tiger, Wolf, Rosebud, or another named guitar. The result names
        the source-dated show assignment and its evidence scope. Follow with
        get_show for the returned show when the visitor wants venue location,
        setlist, recordings, or other show context.
        """
        equipment = store.resolve_equipment(equipment_id_or_name)
        if not equipment:
            return _json({"error": "Equipment not found or ambiguous", "query": equipment_id_or_name})
        return _json(store.equipment_history(equipment))

    @tool
    def get_show(show_id_or_date: str) -> str:
        """Get a show's canonical data, lineup, named guitar/equipment claims, venue, ordered performances, recording metadata, and links.

        Use a canonical show ID returned by another tool, or an unambiguous
        date explicitly supplied by the visitor. Never use a date or show ID
        from model memory. For follow-up questions about who played,
        instruments, guests, or Jerry Garcia's named guitars, reuse the most
        recent retrieved show ID/date and call this tool before answering.
        """
        show = store.resolve_show(show_id_or_date)
        if not show:
            return _json(_unresolved_show_payload(store, show_id_or_date))
        return _json(store.show_context(show))

    @tool
    def get_show_selections() -> str:
        """Get reviewed, source-attributed show selections for discovery questions.

        Use when a visitor asks which shows are notable, essential,
        recommended, or worth exploring. The results are a source's selection,
        not a Deadbot ranking or consensus; never claim omitted shows matter
        less. Do not use this for a direct question about a named show.
        """
        try:
            return _json({"show_selections": load_show_selections(store)})
        except SelectionSignalError as error:
            return _json({"show_selections": [], "error": str(error)})

    @tool
    def get_selection_signals() -> str:
        """Get the complete reviewed critic, fan, official, and curator selection inventory.

        It retains each source's signal type, source/access constraint, and
        canonical resolution state. Use it to investigate a recommendation,
        performance-version, release, or individual-curator question. It is
        evidence from distinct sources, never a combined score, consensus, or
        automatic ranking. Fully resolved editorial show selections are also
        included as browser-ready grounded selections.
        """
        try:
            payload = load_selection_signals(store)
            payload["show_selections"] = load_show_selections(store)
            return _json(payload)
        except SelectionSignalError as error:
            return _json({"selection_signals": [], "show_selections": [], "error": str(error)})

    @tool
    def search_site(site: str, query: str) -> str:
        """Search one research site through its own search and get pages worth reading.

        site is a name from get_research_source_directory (for example
        "Lost Live Dead", "Dead Essays", "Dead Sources", "gdao", "archive.org")
        or any host such as example-blog.org. Each hit is a title, URL, snippet
        and date; open the ones that matter with read_page. For archive.org a
        date such as 1977-05-08 lists that show's recordings with ratings.
        Dead.net, Whitegum and HeadyVersion have no callable search: reach
        their pages through stored links and read_page instead.
        """
        return _json(searcher.search(site, query).as_payload())

    @tool
    def read_page(url: str, focus: str = "", offset: int = 0) -> str:
        """Read a web page and get its text: title, byline, date and the article body.

        Works on any URL: a search_site hit, a stored resource or lore-trail
        link, a Dead.net song or essay page, an archive.org item, or one you
        know. Navigation, comments and footers are stripped. Long pages come
        back in chunks of about 12,000 characters: pass next_offset back as
        offset to keep reading, or pass a focus phrase (a date, venue, song or
        musician) to get the passages about it first.
        """
        try:
            start = max(0, int(offset or 0))
        except (TypeError, ValueError):
            start = 0
        return _json(reader.read(url, focus=focus or None, offset=start).as_payload())

    @tool
    def get_recording_reviews(recording: str, limit: int = 8) -> str:
        """Get archive.org listeners' reviews and star ratings for a recording or a show.

        recording may be a canonical recording_id, an archive.org identifier,
        or a show ID or date such as 1977-05-08. For a show, the reviews come
        from its most-reviewed recording and every other recording's rating is
        listed too, so you can see which source listeners prefer and why.
        Reviews are listener opinion, longest first, each trimmed to a
        paragraph.
        """
        wanted = recording.strip()
        if not wanted:
            return _json({"error": "A recording id, archive identifier, show id or date is required."})
        try:
            review_limit = max(1, min(int(limit or 8), 20))
        except (TypeError, ValueError):
            review_limit = 8

        payload: dict[str, Any] = {"query": wanted}
        rows = [row for row in store.rows("recordings") if row.get("recording_id") == wanted]
        chosen: dict[str, Any] | None = None
        others: list[dict[str, Any]] = []
        if rows:
            chosen = rows[0]
        else:
            show = store.resolve_show(wanted)
            if show:
                payload["show"] = {"show_id": show["show_id"], "show_date": show.get("show_date"), "venue_id": show.get("venue_id")}
                show_rows = [row for row in store.filtered_rows("recordings", show_id=show["show_id"]) if row.get("archive_identifier")]
                if not show_rows:
                    payload["message"] = "The library has no archive.org recording for this show."
                    return _json(payload)
                ratings = searcher.archive_ratings([row["archive_identifier"] for row in show_rows])
                show_rows.sort(key=lambda row: -(ratings.get(row["archive_identifier"], {}).get("num_reviews") or 0))
                chosen = show_rows[0]
                for row in show_rows[1:8]:
                    rating = ratings.get(row["archive_identifier"], {})
                    others.append({
                        "recording_id": row.get("recording_id"),
                        "archive_identifier": row["archive_identifier"],
                        "url": f"https://archive.org/details/{row['archive_identifier']}",
                        "source_type": row.get("source_type") or None,
                        "source": rating.get("source"),
                        "avg_rating": rating.get("avg_rating"),
                        "num_reviews": rating.get("num_reviews"),
                    })
                payload["rating"] = ratings.get(chosen["archive_identifier"])
        if chosen and not chosen.get("archive_identifier"):
            payload["recording"] = {"recording_id": chosen.get("recording_id"), "show_id": chosen.get("show_id"), "source_url": chosen.get("source_url") or None}
            payload["state"] = "empty"
            payload["reviews"] = []
            payload["message"] = "This recording has no archive.org identifier in the library, so it has no listener reviews to fetch. Pass its show date to see the show's reviewed recordings instead."
            return _json(payload)
        identifier = (chosen or {}).get("archive_identifier") or wanted
        if chosen:
            payload["recording"] = {
                "recording_id": chosen.get("recording_id"),
                "show_id": chosen.get("show_id"),
                "archive_identifier": identifier,
                "source_type": chosen.get("source_type") or None,
                "taper": chosen.get("taper") or None,
                "transferer": chosen.get("transferer") or None,
                "lineage": (chosen.get("lineage") or None),
            }
            if "rating" not in payload:
                payload["rating"] = searcher.archive_ratings([identifier]).get(identifier)
        else:
            payload["rating"] = searcher.archive_ratings([identifier]).get(identifier)
        payload.update(searcher.archive_reviews(identifier, review_limit))
        if others:
            payload["other_recordings"] = others
        return _json(payload)

    @tool
    def get_research_source_directory() -> str:
        """List the research sites worth searching and reading, with what each is good for.

        Use this to choose where to look for the story, criticism, listener
        opinion, history or musical character behind a question. Each site
        says how it can be searched (search_site) or, when it has no search,
        how to reach its pages with read_page. The list is a suggestion, not a
        boundary: read_page opens any URL. Also describes the stored link
        catalogs and reviewed metadata adapters.
        """
        try:
            registry = load_registry()
        except RegistryValidationError as error:
            registry = ()
        sources = [
            {
                "source_id": source["source_id"],
                "name": source["name"],
                "authority_level": source["authority_level"],
                "access_state": source["access_state"],
                "allowed_operations": source["allowed_operations"],
                "retention_mode": source["retention_policy"].get("mode"),
                "notes": source.get("notes"),
            }
            for source in registry
        ]
        research_sites = [
            {
                "site_id": site.get("site_id"),
                "name": site.get("name"),
                "host": site.get("host"),
                "good_for": site.get("good_for"),
                "search_method": site.get("search", {}).get("method", "none"),
                "search_notes": site.get("search", {}).get("notes"),
                "read_hints": site.get("read_hints"),
            }
            for site in searcher.sites
        ]
        return _json(
            {
                "research_sites": research_sites,
                "research_tools": {
                    "search_site": "Search one site (by name or host) through its own search; returns titles, URLs, snippets.",
                    "read_page": "Read any page's text; focus phrase and offset for long pages.",
                    "get_recording_reviews": "archive.org listener reviews and star ratings for a recording or show.",
                },
                "reviewed_metadata_adapters": sources,
                "stored_context_link_coverage": {
                    "entity_scope": "specific canonical songs and shows only",
                    "access": "metadata links only; source content is not in the library",
                    "tool": "get_lore_source_trails",
                },
                "stored_resource_catalog": {
                    "access": "searchable metadata and provenance notes for locally cataloged external links",
                    "tool": "search_stored_resources",
                },
                "selection_signal_coverage": {
                    "tool": "get_selection_signals",
                    "access": "reviewed local source-attributed signals with explicit constraints",
                },
            }
        )

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
                return _json(_unresolved_show_payload(store, entity_id))
            show_id = show["show_id"]
            return _json(
                {"show_id": show_id, "links": store.filtered_rows("show_links", show_id=show_id)}
            )
        if entity_type == "performance":
            if not store.performance_context(entity_id):
                return _json({"error": "Performance not found", "performance_id": entity_id})
            return _json(
                {
                    "performance_id": entity_id,
                    "links": store.filtered_rows(
                        "performance_links", performance_id=entity_id
                    ),
                }
            )
        return _json({"error": "entity_type must be 'show' or 'performance'"})

    @tool
    def get_historical_weather(show_id_or_date: str) -> str:
        """Get historical weather for the venue and date of a canonical show.

        Use a show ID or an unambiguous show date such as 1972-08-27. The result
        comes from Open-Meteo's historical reanalysis, so it is an estimate for
        the venue area rather than a claim about a particular weather station.
        """
        try:
            resolved = _show_location(store, show_id_or_date)
            if not resolved:
                return _json(_unresolved_show_payload(store, show_id_or_date))
            show, location = resolved
            requested_date = _show_date(show)
            params = {
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "start_date": requested_date.isoformat(),
                "end_date": requested_date.isoformat(),
                "daily": ",".join([
                    "weather_code", "temperature_2m_max", "temperature_2m_min",
                    "precipitation_sum", "rain_sum", "snowfall_sum",
                    "precipitation_hours", "wind_speed_10m_max",
                ]),
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "precipitation_unit": "inch",
                "timezone": "auto",
            }
            url = f"{OPEN_METEO_ARCHIVE_URL}?{urlencode(params)}"
            payload = _fetch_json(url)
            daily = payload.get("daily")
            if not isinstance(daily, dict):
                raise ExternalServiceError("The weather service returned no daily data.")
            weather_code = _daily_value(daily, "weather_code")
            return _json({
                "show": {"show_id": show["show_id"], "show_date": show["show_date"], "venue_id": show["venue_id"]},
                "location": _location_payload(location),
                "weather": {
                    "date": requested_date.isoformat(),
                    "temperature_max_f": _daily_value(daily, "temperature_2m_max"),
                    "temperature_min_f": _daily_value(daily, "temperature_2m_min"),
                    "precipitation_in": _daily_value(daily, "precipitation_sum"),
                    "rain_in": _daily_value(daily, "rain_sum"),
                    "snowfall_in": _daily_value(daily, "snowfall_sum"),
                    "precipitation_hours": _daily_value(daily, "precipitation_hours"),
                    "wind_speed_max_mph": _daily_value(daily, "wind_speed_10m_max"),
                    "weather_code": weather_code,
                    "weather_description": _weather_description(weather_code),
                },
                "source": {
                    "name": "Open-Meteo Historical Weather API",
                    "url": url,
                    "retrieved_at": _iso_now(),
                    "note": "Historical weather is modelled reanalysis for the nearby grid cell, not a station observation.",
                },
            })
        except (ExternalServiceError, ValueError) as error:
            return _json({"error": str(error), "query": show_id_or_date})

    @tool
    def get_astronomy(show_id_or_date: str) -> str:
        """Get Sun and Moon events for the venue and date of a canonical show.

        Use a show ID or an unambiguous show date such as 1972-08-27. Returns
        local rise, set, transit, twilight, lunar phase, and illumination data
        from the U.S. Naval Observatory's astronomical calculations.
        """
        try:
            resolved = _show_location(store, show_id_or_date)
            if not resolved:
                return _json(_unresolved_show_payload(store, show_id_or_date))
            show, location = resolved
            requested_date = _show_date(show)
            offset = _timezone_offset(location, requested_date)
            params = {
                "date": requested_date.isoformat(),
                "coords": f"{location['latitude']},{location['longitude']}",
                "tz": offset,
            }
            url = f"{USNO_RISE_SET_URL}?{urlencode(params)}"
            payload = _fetch_json(url)
            properties = payload.get("properties", {})
            data = properties.get("data", {}) if isinstance(properties, dict) else {}
            if not isinstance(data, dict):
                raise ExternalServiceError("The astronomy service returned no daily data.")

            def phenomena(key: str) -> list[dict[str, Any]]:
                values = data.get(key, [])
                if not isinstance(values, list):
                    return []
                return [{"event": item.get("phen"), "time": item.get("time")} for item in values if isinstance(item, dict)]

            return _json({
                "show": {"show_id": show["show_id"], "show_date": show["show_date"], "venue_id": show["venue_id"]},
                "location": _location_payload(location),
                "astronomy": {
                    "date": requested_date.isoformat(),
                    "timezone_offset_hours": offset,
                    "sun": phenomena("sundata"),
                    "moon": phenomena("moondata"),
                    "moon_phase": data.get("curphase"),
                    "moon_illumination_fraction": data.get("fracillum"),
                    "nearest_primary_phase": data.get("closestphase"),
                },
                "source": {
                    "name": "U.S. Naval Observatory Astronomical Applications API",
                    "url": url,
                    "retrieved_at": _iso_now(),
                },
            })
        except (ExternalServiceError, ValueError) as error:
            return _json({"error": str(error), "query": show_id_or_date})

    @tool
    def get_astrology(show_id_or_date: str) -> str:
        """Get date-based Western zodiac context for a canonical show.

        Use a show ID or an unambiguous show date such as 1972-08-27. This is
        cultural/interpretive context based on the Sun's zodiac sign; astrology
        is not scientific evidence and the result does not infer a person's
        character, fate, or a show's cause.
        """
        try:
            show = store.resolve_show(show_id_or_date)
            if not show:
                return _json(_unresolved_show_payload(store, show_id_or_date))
            requested_date = _show_date(show)
            sign = _astrology_sign(requested_date)
            return _json({
                "show": {"show_id": show["show_id"], "show_date": show["show_date"], "venue_id": show["venue_id"]},
                "astrology": {
                    "system": "Western tropical zodiac",
                    "sun_sign": sign["sign"],
                    "element": sign["element"],
                    "modality": sign["modality"],
                    "traditional_ruler": sign["traditional_ruler"],
                    "interpretation": f"The show date falls in {sign['sign']} season in this astrological system.",
                },
                "disclaimer": "Astrology is cultural/interpretive context, not scientific evidence; this does not infer personality, fate, or causation.",
            })
        except (ExternalServiceError, ValueError) as error:
            return _json({"error": str(error), "query": show_id_or_date})

    return [
        search_entities,
        search_guest_musicians,
        search_stored_resources,
        get_song,
        get_song_performance_profile,
        get_deadnet_song_context,
        get_deadcast_metadata,
        get_lore_source_trails,
        find_arrangements,
        get_equipment_history,
        get_show,
        get_show_selections,
        get_selection_signals,
        get_research_source_directory,
        search_site,
        read_page,
        get_recording_reviews,
        get_performance,
        get_media_links,
        get_historical_weather,
        get_astronomy,
        get_astrology,
    ]
