"""Export Deadbot's FastAPI OpenAPI schema to ``web/openapi.json``.

The browser contract (``deadbot/experience.py``) is the source of truth for
the ``/api/experience`` request/response shapes. FastAPI derives an OpenAPI
schema from those Pydantic models for free, so instead of hand-maintaining a
duplicate TypeScript mirror, the web client's types are generated from this
exported schema (see ``web/src/types.ts`` and ``npm run gen:types``).

Run this script whenever ``deadbot/experience.py`` (or any model it composes)
changes, then regenerate the TypeScript types:

    .venv/bin/python scripts/export_openapi.py
    npm run gen:types --prefix web

CI runs both steps and fails the build if ``web/openapi.json`` or
``web/src/generated/api.ts`` would change (schema/types drift gate).
"""

from __future__ import annotations

import json
from pathlib import Path

from deadbot.api import create_app
from deadbot.config import Settings
from deadbot.data import CanonicalStore, repository_root


def export_schema() -> dict:
    """Build the app with an injected agent and return its OpenAPI schema.

    Passing a plain ``object()`` as the agent avoids constructing a real
    model-service agent (and its network dependencies) purely to read off
    the schema: ``create_app`` treats any non-``None`` agent as a test seam
    and never invokes it while building the application.
    """

    app = create_app(settings=Settings(), store=CanonicalStore(), agent=object())
    return app.openapi()


def main() -> None:
    schema = export_schema()
    output_path = repository_root() / "web" / "openapi.json"
    serialized = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    output_path.write_text(serialized, encoding="utf-8")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
