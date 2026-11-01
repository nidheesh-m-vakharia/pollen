"""Serve the project for the specimen, telling browsers to revalidate every file.

Plain `python3 -m http.server` sends no Cache-Control header, so browsers keep using a
stale font after a rebuild.
"""

import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    server = ThreadingHTTPServer(("127.0.0.1", port), partial(NoCacheHandler, directory=str(ROOT)))
    print(f"http://localhost:{port}/specimen/")
    server.serve_forever()


if __name__ == "__main__":
    main()
