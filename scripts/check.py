"""Sanity checks for a built Pollen font. Exits non-zero on the first problem.

Run after scripts/build.py; CI runs both.
"""

import json
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
TTF = ROOT / "fonts" / "Pollen[ROND,wght].ttf"
WOFF2 = ROOT / "fonts" / "Pollen[ROND,wght].woff2"
GLYPHS = ROOT / "specimen" / "glyphs.json"

EXPECTED_AXES = {"wght": (400, 400, 700), "ROND": (0, 100, 100)}
EXPECTED_INSTANCES = ["Regular", "Medium", "Semibold", "Bold"]
REQUIRED_CREDITS = ["Inter Project Authors", "Laurids Kern", "Nidheesh Vakharia"]


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def main():
    for path in (TTF, WOFF2, GLYPHS):
        if not path.exists():
            fail(f"missing {path.relative_to(ROOT)}")

    font = TTFont(TTF)
    name = font["name"]

    axes = {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in font["fvar"].axes}
    if axes != EXPECTED_AXES:
        fail(f"axes are {axes}, expected {EXPECTED_AXES}")

    instances = [name.getDebugName(i.subfamilyNameID) for i in font["fvar"].instances]
    if instances != EXPECTED_INSTANCES:
        fail(f"named instances are {instances}, expected {EXPECTED_INSTANCES}")

    if name.getDebugName(1) != "Pollen":
        fail(f"family name is {name.getDebugName(1)!r}, expected 'Pollen'")

    copyright = name.getDebugName(0) or ""
    for credit in REQUIRED_CREDITS:
        if credit not in copyright:
            fail(f"copyright notice is missing {credit!r} (OFL requires the original notices)")
    if "openfontlicense.org" not in (name.getDebugName(14) or ""):
        fail("license URL (name ID 14) is missing")

    for table in ("gvar", "HVAR", "STAT", "GPOS", "GSUB"):
        if table not in font:
            fail(f"{table} table is missing")

    data = json.loads(GLYPHS.read_text())
    if len(data["glyphs"]) < 2000:
        fail(f"glyphs.json lists only {len(data['glyphs'])} glyphs")

    print(f"OK: {len(font.getGlyphOrder())} glyphs, axes {axes}, {len(data['glyphs'])} characters in the specimen")


if __name__ == "__main__":
    main()
