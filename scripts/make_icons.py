"""Make the site icons from Pollen's own "P" (wght 600, ROND 100).

Writes specimen/favicon.svg, favicon.ico, apple-touch-icon.png, icon-192.png and icon-512.png.
Needs Pillow (in requirements.txt). Run after scripts/build.py.
"""

from pathlib import Path

from fontTools.pens.basePen import BasePen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "specimen"

LIGHT_BG, LIGHT_FG = "#e8e8ec", "#3b3f45"   # Radix slate 4 / heading ink
DARK_BG, DARK_FG = "#272a2d", "#d4d6da"
GLYPH_HEIGHT = 0.6   # share of the icon the P's height fills
SUPERSAMPLE = 8


class FlattenPen(BasePen):
    """Collects contours as polygons, flattening curves into short lines."""

    def __init__(self, glyphset, steps=24):
        super().__init__(glyphset)
        self.steps, self.contours, self.cur = steps, [], []

    def _moveTo(self, p):
        self.cur = [p]

    def _lineTo(self, p):
        self.cur.append(p)

    def _curveToOne(self, p1, p2, p3):
        p0 = self.cur[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps
            mt = 1 - t
            self.cur.append(tuple(mt**3 * a + 3 * mt * mt * t * b + 3 * mt * t * t * c + t**3 * d
                                  for a, b, c, d in zip(p0, p1, p2, p3)))

    def _qCurveToOne(self, p1, p2):
        p0 = self.cur[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps
            mt = 1 - t
            self.cur.append(tuple(mt * mt * a + 2 * mt * t * b + t * t * c for a, b, c in zip(p0, p1, p2)))

    def _closePath(self):
        self.contours.append(self.cur)
        self.cur = []


def signed_area(poly):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1])) / 2


def glyph_p():
    font = instantiateVariableFont(TTFont(ROOT / "fonts" / "Pollen[ROND,wght].ttf"), {"wght": 600, "ROND": 100})
    gs = font.getGlyphSet()
    bounds = BoundsPen(gs)
    gs["P"].draw(bounds)
    return gs, bounds.bounds


def placement(bounds, size):
    """Scale and offset that centre the glyph's box in a size×size square (y flipped)."""
    x0, y0, x1, y1 = bounds
    s = size * GLYPH_HEIGHT / (y1 - y0)
    tx = (size - (x1 - x0) * s) / 2 - x0 * s
    ty = (size + (y1 - y0) * s) / 2 + y0 * s
    return s, tx, ty


def write_svg(gs, bounds):
    pen = SVGPathPen(gs)
    gs["P"].draw(pen)
    s, tx, ty = placement(bounds, 64)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <style>
    rect {{ fill: {LIGHT_BG}; }} path {{ fill: {LIGHT_FG}; }}
    @media (prefers-color-scheme: dark) {{ rect {{ fill: {DARK_BG}; }} path {{ fill: {DARK_FG}; }} }}
  </style>
  <rect width="64" height="64" rx="16"/>
  <path transform="matrix({s:.6f} 0 0 {-s:.6f} {tx:.3f} {ty:.3f})" d="{pen.getCommands()}"/>
</svg>
"""
    (OUT / "favicon.svg").write_text(svg)


def render(gs, bounds, size, rounded):
    big = size * SUPERSAMPLE
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if rounded:
        draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=big // 4, fill=LIGHT_BG)
    else:
        draw.rectangle((0, 0, big, big), fill=LIGHT_BG)  # iOS and Android mask the corners themselves
    pen = FlattenPen(gs)
    gs["P"].draw(pen)
    s, tx, ty = placement(bounds, big)
    # outer contours fill with ink, counters (opposite winding) cut back to the background
    contours = sorted(pen.contours, key=lambda c: -abs(signed_area(c)))
    outer_sign = signed_area(contours[0]) > 0
    for c in contours:
        pts = [(tx + x * s, ty - y * s) for x, y in c]
        draw.polygon(pts, fill=LIGHT_FG if (signed_area(c) > 0) == outer_sign else LIGHT_BG)
    return img.resize((size, size), Image.LANCZOS)


def main():
    gs, bounds = glyph_p()
    write_svg(gs, bounds)
    render(gs, bounds, 180, rounded=False).save(OUT / "apple-touch-icon.png")
    render(gs, bounds, 192, rounded=False).save(OUT / "icon-192.png")
    render(gs, bounds, 512, rounded=False).save(OUT / "icon-512.png")
    ico = render(gs, bounds, 256, rounded=True)
    ico.save(OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    print("wrote favicon.svg, favicon.ico, apple-touch-icon.png, icon-192.png, icon-512.png")


if __name__ == "__main__":
    main()
