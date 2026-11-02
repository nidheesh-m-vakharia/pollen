"""Make the Pollen logo from the font's own outlines (wght 600, ROND 100).

Writes to assets/:
  logo.svg            mark + wordmark lockup, follows light/dark mode
  logo-mark.svg       the rounded-square "P" on its own
  logo-wordmark.svg   "Pollen" on its own
  logo-light.png      lockup for light backgrounds (transparent, 1200px wide)
  logo-dark.png       lockup for dark backgrounds
  logo-square.svg     the "P" alone on a flat white square, for avatars
  logo-square.png     the same at 1024×1024

The glyphs are outlines, so none of these need the font installed.
Needs Pillow (in requirements.txt). Run after scripts/build.py.
"""

from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import Image, ImageChops, ImageDraw

from make_icons import DARK_BG, DARK_FG, LIGHT_BG, LIGHT_FG, FlattenPen, signed_area

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"

WORD = "Pollen"
LOCATION = {"wght": 600, "ROND": 100}
MARK = 64            # mark side, in SVG units; everything else is sized from it
MARK_GLYPH = 0.6     # share of the mark the P's height fills (same as the favicon)
CAP = 0.5            # wordmark cap height as a share of the mark
GAP = 0.3            # space between mark and wordmark, as a share of the mark
TRACKING = -0.02     # em
PNG_WIDTH = 1200
SQUARE_PNG = 1024
SQUARE_BG = "#ffffff"


def load_font():
    font = instantiateVariableFont(TTFont(ROOT / "fonts" / "Pollen[ROND,wght].ttf"), LOCATION)
    cmap = font.getBestCmap()
    return font, font.getGlyphSet(), cmap


def bounds_of(gs, name):
    pen = BoundsPen(gs)
    gs[name].draw(pen)
    return pen.bounds


def layout(font, gs, cmap):
    """Glyphs as (name, scale, x, baseline_y) in a coordinate space where the mark is MARK tall."""
    upm = font["head"].unitsPerEm
    cap_height = font["OS/2"].sCapHeight

    # mark: centre the P's box inside the square
    p = cmap[ord("P")]
    x0, y0, x1, y1 = bounds_of(gs, p)
    s = MARK * MARK_GLYPH / (y1 - y0)
    mark = (p, s, (MARK - (x1 - x0) * s) / 2 - x0 * s, (MARK + (y1 - y0) * s) / 2 + y0 * s)

    # wordmark: cap height centred on the mark, set with the font's advances plus tracking
    s = MARK * CAP / cap_height
    baseline = (MARK + cap_height * s) / 2
    names = [cmap[ord(c)] for c in WORD]
    pen_x, word = 0.0, []
    for i, name in enumerate(names):
        word.append((name, s, pen_x, baseline))
        pen_x += font["hmtx"][name][0] * s
        if i < len(names) - 1:
            pen_x += TRACKING * upm * s
    # trim side bearings so the wordmark's box is its ink
    left = bounds_of(gs, names[0])[0] * s
    right = word[-1][2] + bounds_of(gs, names[-1])[2] * s
    word = [(n, sc, x - left, y) for n, sc, x, y in word]
    return mark, word, right - left


def svg_path(gs, glyph):
    name, s, x, y = glyph
    pen = SVGPathPen(gs)
    gs[name].draw(pen)
    return f'<path transform="matrix({s:.6f} 0 0 {-s:.6f} {x:.3f} {y:.3f})" d="{pen.getCommands()}"/>'


def fmt(n):
    return f"{n:.3f}".rstrip("0").rstrip(".")


def write_svg(path, width, body, mark=False, height=MARK):
    style = f"path {{ fill: {LIGHT_FG}; }}"
    dark = f"path {{ fill: {DARK_FG}; }}"
    if mark:
        style = f".bg {{ fill: {LIGHT_BG}; }} " + style
        dark = f".bg {{ fill: {DARK_BG}; }} " + dark
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {fmt(width)} {fmt(height)}" role="img" aria-label="{WORD}">
  <style>
    {style}
    @media (prefers-color-scheme: dark) {{ {dark} }}
  </style>
  {body}
</svg>
"""
    path.write_text(svg)


def glyph_mask(gs, glyph, size, k):
    """An L-mode mask of one glyph: outer contours on, counters (opposite winding) cut back out."""
    name, s, x, y = glyph
    pen = FlattenPen(gs)
    gs[name].draw(pen)
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    contours = sorted(pen.contours, key=lambda c: -abs(signed_area(c)))
    outer_sign = signed_area(contours[0]) > 0
    for c in contours:
        pts = [((x + px * s) * k, (y - py * s) * k) for px, py in c]
        draw.polygon(pts, fill=255 if (signed_area(c) > 0) == outer_sign else 0)
    return mask


def render_png(gs, glyphs, mark_at, view, out_width, bg, fg, radius=MARK / 4):
    """Draw the mark's square at mark_at and the glyphs on a transparent view (w, h) canvas."""
    supersample = 4
    k = out_width * supersample / view[0]
    size = (out_width * supersample, round(view[1] * k))
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    x, y = mark_at[0] * k, mark_at[1] * k
    ImageDraw.Draw(img).rounded_rectangle((x, y, x + MARK * k - 1, y + MARK * k - 1), radius=radius * k, fill=bg)
    ink = Image.new("L", size, 0)
    for g in glyphs:
        ink = ImageChops.lighter(ink, glyph_mask(gs, g, size, k))
    img.paste(Image.new("RGBA", size, fg), (0, 0), ink)
    return img.resize((out_width, round(size[1] / supersample)), Image.LANCZOS)


def moved(glyphs, dx, dy):
    return [(n, s, x + dx, y + dy) for n, s, x, y in glyphs]


def rect_at(x, y):
    return f'<rect class="bg" x="{fmt(x)}" y="{fmt(y)}" width="{MARK}" height="{MARK}" rx="{MARK // 4}"/>'


def main():
    font, gs, cmap = load_font()
    mark, word, word_width = layout(font, gs, cmap)
    paths = lambda glyphs: [svg_path(gs, g) for g in glyphs]

    write_svg(OUT / "logo-mark.svg", MARK, "\n  ".join([rect_at(0, 0)] + paths([mark])), mark=True)
    write_svg(OUT / "logo-wordmark.svg", word_width, "\n  ".join(paths(word)))

    # horizontal: mark, then the wordmark with its cap height centred on the mark
    word_x = MARK * (1 + GAP)
    glyphs = [mark] + moved(word, word_x, 0)
    width = word_x + word_width
    write_svg(OUT / "logo.svg", width, "\n  ".join([rect_at(0, 0)] + paths(glyphs)), mark=True)
    render_png(gs, glyphs, (0, 0), (width, MARK), PNG_WIDTH, LIGHT_BG, LIGHT_FG).save(OUT / "logo-light.png")
    render_png(gs, glyphs, (0, 0), (width, MARK), PNG_WIDTH, DARK_BG, DARK_FG).save(OUT / "logo-dark.png")

    # square: the mark's "P" on a plain white square, no rounded tile and no dark mode
    (OUT / "logo-square.svg").write_text(f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {MARK} {MARK}" role="img" aria-label="{WORD}">
  <rect width="{MARK}" height="{MARK}" fill="{SQUARE_BG}"/>
  {svg_path(gs, mark).replace("<path ", f'<path fill="{LIGHT_FG}" ', 1)}
</svg>
""")
    render_png(gs, [mark], (0, 0), (MARK, MARK), SQUARE_PNG, SQUARE_BG, LIGHT_FG, radius=0).save(OUT / "logo-square.png")

    print("wrote logo.svg, logo-mark.svg, logo-wordmark.svg, logo-square.svg and their PNGs")


if __name__ == "__main__":
    main()
