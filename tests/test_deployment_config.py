"""The deployment config is load-bearing, so it gets the same treatment as code.

Two things used to go wrong silently. Research inputs were shipped to Vercel and
bundled into the function even though the running site never opens them, which
filled the storage allowance. And the client shell was served by a catch-all
route, so every browser URL woke Python just to hand back one HTML file.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Read at request time by source_registry, site_search and lore_source_trails.
RUNTIME_DATA = (
    "data/source_registry.json",
    "data/research_sites.json",
    "data/lore-source-trails.json",
)
# Import inputs. Large, and never opened by the deployed function.
NEVER_DEPLOYED = ("data/raw", "data/canonical", "docs", "tests", "scripts", "evals")

MAX_DEPLOY_MB = 25.0


def _shipped_files() -> list[str]:
    """The tracked files a deployment would carry, per .vercelignore."""

    def git(*args: str) -> list[str]:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.split()

    tracked = git("ls-files")
    # -c -i applies the exclude file to tracked entries, honouring the "!"
    # re-include lines, which is exactly how Vercel reads .vercelignore.
    excluded = set(git("ls-files", "-c", "-i", "--exclude-from=.vercelignore"))
    return [f for f in tracked if f not in excluded]


def test_the_deployment_stays_small() -> None:
    shipped = _shipped_files()
    megabytes = sum((ROOT / f).stat().st_size for f in shipped) / 1_048_576

    assert megabytes < MAX_DEPLOY_MB, (
        f"the deployment would carry {megabytes:.1f} MB. Something large was added "
        f"that .vercelignore lets through. Add it to .vercelignore rather than "
        f"raising this limit, unless the running site genuinely needs it."
    )


def test_research_inputs_are_not_deployed() -> None:
    shipped = _shipped_files()

    for prefix in NEVER_DEPLOYED:
        leaked = [f for f in shipped if f.startswith(f"{prefix}/")]
        assert not leaked, f"{prefix}/ should not be deployed, but {leaked[:3]} would be"


def test_the_files_the_request_path_reads_are_deployed() -> None:
    shipped = set(_shipped_files())

    for path in RUNTIME_DATA:
        assert path in shipped, (
            f"{path} is read while serving a request but .vercelignore excludes it, "
            f"so the deployed site would fail when it reached that code"
        )


def test_the_client_shell_is_never_cached() -> None:
    """A stale shell points a browser at hashed bundles that no longer exist."""

    config = json.loads((ROOT / "vercel.json").read_text())
    rules = {rule["source"]: rule["headers"] for rule in config["headers"]}

    shell = next(v for k, v in rules.items() if "assets" in k and "!" in k)
    assert any(
        h["key"] == "Cache-Control" and "no-store" in h["value"] for h in shell
    ), "the client shell must be served with no-store"


def test_hashed_bundles_are_cached_forever() -> None:
    """Filenames carry a content hash, so a cached copy can never be wrong."""

    config = json.loads((ROOT / "vercel.json").read_text())

    for prefix in ("/assets/", "/fonts/"):
        rule = next(r for r in config["headers"] if r["source"].startswith(prefix))
        assert any(
            h["key"] == "Cache-Control" and "immutable" in h["value"] for h in rule["headers"]
        ), f"{prefix} should be immutable"
