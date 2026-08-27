"""Read-only tools exposed to the agent loop."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timezone
from functools import lru_cache
from http.client import HTTPException as HTTPClientException
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from langchain_core.tools import BaseTool, tool

from deadbot.data import CanonicalStore


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

        for phrase in phrases:
            for item in store.matching_rows("equipment", phrase, ("name", "manufacturer", "model"))[:10]:
                add("equipment", item["equipment_id"], item["name"])

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

        Use a canonical show ID or an unambiguous date such as 1972-08-27. For
        follow-up questions about who played, instruments, guests, or Jerry
        Garcia's named guitars, reuse the most recent show ID/date and call
        this tool before answering.
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
                return _json({"error": "Show not found or ambiguous", "query": show_id_or_date})
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
                return _json({"error": "Show not found or ambiguous", "query": show_id_or_date})
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
                return _json({"error": "Show not found or ambiguous", "query": show_id_or_date})
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
        get_song,
        find_arrangements,
        get_equipment_history,
        get_show,
        get_performance,
        get_media_links,
        get_historical_weather,
        get_astronomy,
        get_astrology,
    ]
