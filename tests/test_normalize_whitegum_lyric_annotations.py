"""Tests for the whitegum.com resource-id derivation.

Regression for a real bug caught during this pass: deriving the resource id
from the *canonical song id* collided two distinct pages onto one id whenever
a song was held (two site pages sharing one title's match_key, e.g. "Comes A
Time" as a Grateful Dead original and again as a Phil & Friends cover). The
id must be derived from the page's own URL instead, so two different pages
for the same song never collide.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts" / "normalize"))
import normalize_whitegum_lyric_annotations as nwl  # noqa: E402


def test_resource_id_is_derived_from_the_page_not_the_song():
    first = nwl.resource_id_for("https://www.whitegum.com/~acsa/songfile/COMESTIM.HTM")
    second = nwl.resource_id_for("https://www.whitegum.com/~acsa/songfile/COMESTI2.HTM")
    assert first != second
    assert first == "resource-whitegum-comestim"
    assert second == "resource-whitegum-comesti2"


def test_resource_id_ignores_the_path_prefix_and_extension_case():
    assert nwl.resource_id_for("https://www.whitegum.com/songfile/SUGAREE.HTM") == "resource-whitegum-sugaree"
