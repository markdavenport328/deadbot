"""One reading of the qualifiers JerryBase appends to a performer's name.

JerryBase sometimes writes a trailing parenthetical onto a person's display
name — ``Bruce Hornsby (complete show)``, ``Marvin Boxley (songs unknown)``.
The parenthetical describes the appearance or the state of the source record;
it never names a second human being. Every caller that has to decide whether
two person rows are one person reads the qualifier through this module, so the
rule cannot drift between the query layer and the normalizers that write the
canonical CSVs.

Reading a qualifier is not permission to merge. A caller merges two rows only
when a plain row of the same base name already exists; a parenthetical on its
own is never evidence that some other row is the same person.
"""

from __future__ import annotations

import re


# Any trailing parenthetical, not just the participation forms: the qualifier
# vocabulary is the source's, and it has already grown past "(complete show)".
QUALIFIER = re.compile(r"\s+\(([^()]+)\)\s*$")

# The qualifiers that describe how much of a show the guest played. These are
# the only ones that earn a participation_scope, because that value reaches the
# reader as a claim about the appearance. Everything else — "songs unknown", a
# note about how complete the source record is — collapses the identity and
# claims nothing. Keeping this an allowlist means a new qualifier form can add
# a duplicate identity to fold, but never a sentence about the performance.
PARTICIPATION_SCOPES = frozenset({"complete show"})


def split_person_qualifier(name: str) -> tuple[str, str | None]:
    """Return the person's base name and any trailing qualifier, casefolded."""

    value = (name or "").strip()
    match = QUALIFIER.search(value)
    if not match:
        return value, None
    return value[: match.start()].strip(), match.group(1).strip().casefold()


def is_plain_name(name: str) -> bool:
    """True when the name carries no qualifier, and so names a person outright."""

    return bool((name or "").strip()) and QUALIFIER.search(name.strip()) is None


def participation_scope_for(qualifier: str | None) -> str | None:
    """Return the qualifier when it describes participation, otherwise None."""

    return qualifier if qualifier in PARTICIPATION_SCOPES else None
