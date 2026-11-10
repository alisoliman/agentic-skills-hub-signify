#!/usr/bin/env python3
"""Dev server: rebuilds hub.json on source changes and live-reloads the browser.

Watches:
  skills/**/*    -> rebuild hub.json (drop/edit SKILL.md and see it appear)
  catalog/**/*   -> rebuild hub.json (edit config or external skills)
  site/**/*      -> live-reload only (HTML/CSS/JS edits)

Serves site/ on http://127.0.0.1:8000 with auto browser reload. Needs livereload
(`uv run` installs it from uv.lock). Unlike `npm start`, it has no fallback for
path-based routes: reload those from `/` or use `npm start`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from build_catalog import SITE_DIR, build  # noqa: E402

try:
    from livereload import Server
except ImportError:
    sys.exit(
        "livereload is required for the dev server.\n"
        "Run it through uv: npm run dev (or: uv run --frozen python scripts/dev.py)"
    )


def safe_build() -> None:
    try:
        build()
    except ValueError as error:
        print(f"Build failed: {error}", file=sys.stderr)


def main() -> None:
    build()

    server = Server()
    server.watch("skills/", safe_build)
    server.watch("catalog/", safe_build)
    server.watch("site/")

    print("Dev server: http://127.0.0.1:8000")
    server.serve(
        root=str(SITE_DIR),
        port=8000,
        host="127.0.0.1",
        open_url_delay=None,
    )


if __name__ == "__main__":
    main()
