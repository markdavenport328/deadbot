#!/usr/bin/env python3
"""Give every venue the metro area a fan would name it by.

A fan asking "did they play Chicago?" means Rosemont and Tinley Park too, and
"Denver" means Red Rocks. ``metro_area`` holds that name. Suburbs, nearby
amphitheaters and stadiums take the metro's name (US groupings follow the
Census combined statistical areas, with fan usage deciding the edges, such as
Alpine Valley under Chicago). Any other venue's metro area is its own city.

The groupings below are the reviewed source of truth; rerunning the script
rewrites the column from them, so a change goes here, not in the CSV.

    python scripts/assign_metro_areas.py
"""

from __future__ import annotations

import csv
from pathlib import Path

VENUES = Path(__file__).resolve().parents[1] / "data" / "canonical" / "venues.csv"

# metro area -> the (city, state_region) pairs inside it
METROS: dict[str, list[tuple[str, str]]] = {
    "San Francisco Bay Area": [
        (city, "CA") for city in (
            "Belmont", "Berkeley", "Crockett", "Daly City", "Hayward", "Hillsborough", "Kentfield", "Ladera",
            "Marin County", "Menlo Park", "Mill Valley", "Moraga", "Mountain View", "Muir Beach", "Napa", "Novato",
            "Oakand", "Oakland", "Palo Alto", "Pescadero", "Rio Nido", "San Anselmo", "San Francisco", "San Jose",
            "San Mateo", "San Quentin", "San Rafael", "Santa Clara", "Santa Rosa", "Sausalito", "Suisun City",
            "Vallejo", "Walnut Creek",
        )
    ],
    "Los Angeles": [
        (city, "CA") for city in (
            "Anaheim", "Carson", "Compton", "Costa Mesa", "Devore", "El Monte", "Hollywood", "Inglewood", "Irvine",
            "Long Beach", "Los Angeles", "North Hills", "Pasadena", "San Bernardino", "San Pedro", "Santa Monica",
            "Torrance", "Universal City", "Venice", "Ventura", "West Hollywood",
        )
    ],
    "San Diego": [(city, "CA") for city in ("Chula Vista", "Del Mar", "La Jolla", "San Diego")],
    "Sacramento": [(city, "CA") for city in ("Davis", "Rocklin", "Sacramento")],
    "Lake Tahoe": [("Lake Tahoe", "CA"), ("South Lake Tahoe", "CA"), ("Donner Summit", "CA")],
    "Santa Barbara": [("Goleta", "CA"), ("Santa Barbara", "CA")],
    "Denver": [("Boulder", "CO"), ("Denver", "CO"), ("Franktown", "CO"), ("Morrison", "CO")],
    "Chicago": [
        ("Chicago", "IL"), ("Evanston", "IL"), ("Hoffman Estates", "IL"), ("Rosemont", "IL"), ("Tinley Park", "IL"),
        ("East Troy", "WI"),
    ],
    "New York": [
        ("Bronx", "NY"), ("Brooklyn", "NY"), ("New York", "NY"), ("Queens", "NY"), ("Island Park", "NY"),
        ("Uniondale", "NY"), ("Stony Brook", "NY"), ("Port Chester", "NY"), ("East Rutherford", "NJ"),
        ("Jersey City", "NJ"), ("Passaic", "NJ"), ("Wayne", "NJ"), ("Edison", "NJ"), ("Piscataway", "NJ"),
        ("Englishtown", "NJ"), ("Norwalk", "CT"),
    ],
    "Philadelphia": [("Philadelphia", "PA"), ("Upper Darby", "PA")],
    "Boston": [("Boston", "MA"), ("Cambridge", "MA"), ("Foxboro", "MA"), ("North Billerica", "MA")],
    "Washington–Baltimore": [
        ("Washington", "DC"), ("Landover", "MD"), ("College Park", "MD"), ("Columbia", "MD"), ("Baltimore", "MD"),
    ],
    "Miami": [
        (city, "FL") for city in (
            "Dania", "Hallandale", "Miami", "North Miami Beach", "Pembroke Pines", "Sunny Isles Beach",
            "West Hollywood", "West Palm Beach",
        )
    ],
    "Tampa Bay": [("Tampa", "FL"), ("St. Petersburg", "FL")],
    "Detroit": [("Detroit", "MI"), ("Auburn Hills", "MI"), ("Clarkston", "MI"), ("Ann Arbor", "MI")],
    "Minneapolis–St. Paul": [("Minneapolis", "MN"), ("St. Paul", "MN"), ("Bloomington", "MN")],
    "St. Louis": [("St. Louis", "MO"), ("Maryland Heights", "MO"), ("Edwardsville", "IL")],
    "Kansas City": [("Kansas City", "KS"), ("Kansas City", "MO"), ("Bonner Springs", "KS")],
    "Cleveland": [("Cleveland", "OH"), ("Richfield", "OH"), ("Cuyahoga Falls", "OH"), ("Akron", "OH")],
    "Columbus": [("Columbus", "OH"), ("Thornville", "OH")],
    "Pittsburgh": [("Pittsburgh", "PA"), ("Burgettstown", "PA")],
    "Indianapolis": [("Indianapolis", "IN"), ("Noblesville", "IN")],
    "Dallas–Fort Worth": [("Dallas", "TX"), ("Fort Worth", "TX")],
    "Portland": [("Portland", "OR"), ("Gresham", "OR"), ("St. Helens", "OR")],
    "Seattle": [("Seattle", "WA"), ("Tacoma", "WA"), ("Sultan", "WA")],
    "Phoenix": [("Phoenix", "AZ"), ("Tempe", "AZ"), ("Chandler", "AZ")],
    "Raleigh–Durham": [("Raleigh", "NC"), ("Durham", "NC"), ("Chapel Hill", "NC")],
    "Albany": [("Albany", "NY"), ("Troy", "NY"), ("Saratoga Springs", "NY")],
    "Hartford": [("Hartford", "CT"), ("Middletown", "CT")],
    "Salt Lake City": [("Salt Lake City", "UT"), ("Park City", "UT")],
    "Hampton Roads": [("Hampton", "VA"), ("Norfolk", "VA"), ("Virginia Beach", "VA")],
    "Toronto": [("Toronto", ""), ("Maple", "")],
}

# A city spelled wrong in the source keeps its row, but its metro is spelled right.
SPELLING = {"Niagra Falls": "Niagara Falls", "Glen Falls": "Glens Falls"}

LOOKUP = {pair: metro for metro, pairs in METROS.items() for pair in pairs}


def metro_area(city: str, state_region: str) -> str:
    city = (city or "").strip()
    if not city:
        return ""
    return LOOKUP.get((city, (state_region or "").strip())) or SPELLING.get(city, city)


def main() -> None:
    with VENUES.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    if "metro_area" not in fields:
        fields.append("metro_area")
    for row in rows:
        row["metro_area"] = metro_area(row.get("city", ""), row.get("state_region", ""))
    with VENUES.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    unused = sorted(set(LOOKUP) - {(row.get("city", ""), row.get("state_region", "")) for row in rows})
    grouped = sum(1 for row in rows if (row.get("city", ""), row.get("state_region", "")) in LOOKUP)
    print(f"wrote metro_area for {len(rows)} venues ({grouped} inside a named metro)")
    if unused:
        print("groupings that matched no venue:", unused)


if __name__ == "__main__":
    main()
