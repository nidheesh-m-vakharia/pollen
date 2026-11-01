"""Point every absolute site URL at your domain.

    python3 scripts/set_domain.py https://pollentype.com

Rewrites the canonical URL, Open Graph and structured data in specimen/index.html,
plus robots.txt, sitemap.xml and llms.txt. Safe to run again with a new domain.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ["specimen/index.html", "robots.txt", "sitemap.xml", "llms.txt"]
MARKER = ROOT / ".site-url"  # remembers the current domain
DEFAULT = "https://pollen.pages.dev"


def main():
    if len(sys.argv) != 2 or not re.match(r"^https://[^/\s]+$", sys.argv[1].rstrip("/")):
        sys.exit("usage: set_domain.py https://example.com")
    new = sys.argv[1].rstrip("/")
    old = MARKER.read_text().strip() if MARKER.exists() else DEFAULT
    for name in FILES:
        path = ROOT / name
        path.write_text(path.read_text().replace(old, new))
    MARKER.write_text(new + "\n")
    print(f"{old} -> {new} in {', '.join(FILES)}")


if __name__ == "__main__":
    main()
