#!/usr/bin/env python3
"""Serve site/ locally the way Azure Static Web Apps serves it.

Unknown paths without a file extension fall back to index.html, like the
navigationFallback in site/staticwebapp.config.json, so path-based routes work
locally too. Bound to 127.0.0.1 only. Standard library only.

Usage: python3 scripts/serve.py [--port 8000]   (npm start builds first, then runs this)
"""

from __future__ import annotations

import argparse
import functools
import http.server
import posixpath
import sys
import urllib.parse
from pathlib import Path

SITE_DIR = Path(__file__).resolve().parents[1] / "site"


class FallbackHandler(http.server.SimpleHTTPRequestHandler):
    def send_head(self):
        request_path = urllib.parse.urlsplit(self.path).path
        target = Path(self.translate_path(self.path))
        if not target.exists() and not posixpath.splitext(request_path)[1]:
            self.path = "/index.html"
        return super().send_head()

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve site/ on http://127.0.0.1 with SPA fallback.")
    parser.add_argument("--port", type=int, default=8000, help="port to listen on (default: 8000)")
    args = parser.parse_args(argv)

    if not (SITE_DIR / "hub.json").is_file():
        print("site/hub.json is missing: run `npm run build` first.", file=sys.stderr)
        return 1

    handler = functools.partial(FallbackHandler, directory=str(SITE_DIR))
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    except OSError as error:
        print(f"Cannot listen on port {args.port} ({error}). Try: npm start -- --port 8001", file=sys.stderr)
        return 1

    print(f"Serving site/ on http://127.0.0.1:{args.port}  (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
