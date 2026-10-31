"""Build Open Runde Variable (wght 400-700) from the four static Open Runde masters.

The static OTFs were flattened per weight, so many glyphs have slightly different
node structures between weights. This script makes every glyph point-compatible by
aligning nodes along each contour (by normalised arc length) and splitting segments
where one master has a node another lacks. Splitting never changes a master's shape.
The compatible cubic outlines are then converted to TrueType quadratics with a shared
cu2qu conversion and merged with fontTools.varLib.
"""

import math
import sys
from pathlib import Path

from fontTools.cu2qu import curves_to_quadratic
from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument, InstanceDescriptor, SourceDescriptor
from fontTools.otlLib.builder import buildStatTable
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools import varLib

ROOT = Path(__file__).resolve().parent.parent
MASTERS = [("Regular", 400), ("Medium", 500), ("Semibold", 600), ("Bold", 700)]
FAMILY = "Open Runde Variable"
PS_FAMILY = "OpenRundeVariable"

MATCH_GAP = 0.02  # DP gap cost; nodes closer than 2x this (in contour fraction) get matched
CU2QU_ERROR = 1.0  # font units (UPM 2048)


# ---------------------------------------------------------------- geometry

def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def split_cubic(p0, p1, p2, p3, t):
    a, b, c = lerp(p0, p1, t), lerp(p1, p2, t), lerp(p2, p3, t)
    d, e = lerp(a, b, t), lerp(b, c, t)
    f = lerp(d, e, t)
    return (p0, a, d, f), (f, e, c, p3)


def cubic_at(p0, p1, p2, p3, t):
    mt = 1 - t
    return (
        mt**3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t**3 * p3[0],
        mt**3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t**3 * p3[1],
    )


def seg_length_table(seg, n=32):
    """Cumulative arc length at n+1 evenly spaced t values."""
    if len(seg) == 2:
        L = math.dist(*seg)
        return [L * i / n for i in range(n + 1)]
    pts = [cubic_at(*seg, i / n) for i in range(n + 1)]
    acc = [0.0]
    for i in range(n):
        acc.append(acc[-1] + math.dist(pts[i], pts[i + 1]))
    return acc


def seg_length(seg):
    return seg_length_table(seg)[-1]


def t_at_length_fraction(seg, f):
    table = seg_length_table(seg)
    target = f * table[-1]
    n = len(table) - 1
    for i in range(n):
        if table[i + 1] >= target:
            span = table[i + 1] - table[i]
            local = 0 if span == 0 else (target - table[i]) / span
            return (i + local) / n
    return 1.0


def split_segment(seg, t):
    if len(seg) == 2:
        m = lerp(seg[0], seg[1], t)
        return (seg[0], m), (m, seg[1])
    return split_cubic(*seg, t)


# ---------------------------------------------------------------- contours

def read_contours(glyphset, name):
    """Return list of contours; each contour is a list of segments.
    A segment is a 2-tuple (line) or 4-tuple (cubic). Contours are explicitly closed."""
    pen = RecordingPen()
    glyphset[name].draw(pen)
    contours, cur, start, pos = [], None, None, None
    for op, args in pen.value:
        if op == "moveTo":
            cur, start = [], args[0]
            pos = start
        elif op == "lineTo":
            cur.append((pos, args[0]))
            pos = args[0]
        elif op == "curveTo":
            cur.append((pos, *args))
            pos = args[-1]
        elif op in ("closePath", "endPath"):
            if pos != start:
                cur.append((pos, start))
            # make closure exact and drop zero-length segments
            cur = [s for s in cur if seg_length(s) > 1e-6 or len(s) == 4 and len(set(s)) > 1]
            if cur:
                last = cur[-1]
                cur[-1] = (*last[:-1], cur[0][0])
                contours.append(cur)
        else:
            raise ValueError(f"unexpected pen op {op} in {name}")
    return contours


def signature(contours):
    return tuple(tuple(len(s) for s in c) for c in contours)


def signed_area(contour):
    a = 0.0
    for s in contour:
        pts = [s[0], s[-1]] if len(s) == 2 else [cubic_at(*s, i / 8) for i in range(9)]
        for p, q in zip(pts, pts[1:]):
            a += p[0] * q[1] - q[0] * p[1]
    return a / 2


def bbox(points):
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def contour_bbox(c):
    return bbox([p for s in c for p in s])


def reverse_contour(c):
    return [tuple(reversed(s)) for s in reversed(c)]


def rotate_contour(c, i):
    return c[i:] + c[:i]


def node_fractions(c):
    lengths = [seg_length(s) for s in c]
    total = sum(lengths) or 1.0
    fr, acc = [], 0.0
    for L in lengths:
        fr.append(acc / total)
        acc += L
    return fr


def rel(p, box):
    w = (box[2] - box[0]) or 1.0
    h = (box[3] - box[1]) or 1.0
    return ((p[0] - box[0]) / w, (p[1] - box[1]) / h)


def match_contours(ref, other):
    """Reorder/reverse/rotate `other` contours to correspond to `ref` contours."""
    if len(ref) != len(other):
        return None
    gbox_r = bbox([p for c in ref for s in c for p in s])
    gbox_o = bbox([p for c in other for s in c for p in s])

    def key(c, gbox):
        b = contour_bbox(c)
        return rel(((b[0] + b[2]) / 2, (b[1] + b[3]) / 2), gbox), rel((b[0], b[1]), gbox), rel((b[2], b[3]), gbox)

    ref_keys = [key(c, gbox_r) for c in ref]
    oth_keys = [key(c, gbox_o) for c in other]
    remaining = list(range(len(other)))
    out = []
    for i, rk in enumerate(ref_keys):
        best = min(remaining, key=lambda j: sum(math.dist(a, b) for a, b in zip(rk, oth_keys[j])))
        remaining.remove(best)
        # contours that don't occupy roughly the same box have changed topology
        if max(math.dist(a, b) for a, b in zip(rk, oth_keys[best])) > 0.15:
            return None
        c = other[best]
        if (signed_area(c) > 0) != (signed_area(ref[i]) > 0):
            c = reverse_contour(c)
        # rotate so the start node corresponds to ref's start node
        rb, ob = contour_bbox(ref[i]), contour_bbox(c)
        rs = rel(ref[i][0][0], rb)
        rf = node_fractions(ref[i])
        of = node_fractions(c)
        best_k = min(
            range(len(c)),
            key=lambda k: math.dist(rel(c[k][0], ob), rs),
        )
        if best_k != 0 and math.dist(rel(c[best_k][0], ob), rs) + 1e-9 < math.dist(rel(c[0][0], ob), rs) - 0.02:
            c = rotate_contour(c, best_k)
        out.append(c)
    return out


def align(a, b):
    """Needleman-Wunsch alignment of two sorted fraction lists (both start with 0).
    Returns list of pairs (i or None, j or None)."""
    n, m = len(a), len(b)
    INF = float("inf")
    D = [[INF] * (m + 1) for _ in range(n + 1)]
    P = [[None] * (m + 1) for _ in range(n + 1)]
    D[1][1] = 0.0  # start nodes always match
    P[1][1] = "M"
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if i == 1 and j == 1:
                continue
            best, how = INF, None
            if i > 1 and j > 1 and D[i - 1][j - 1] < INF:
                c = D[i - 1][j - 1] + abs(a[i - 1] - b[j - 1])
                if c < best:
                    best, how = c, "M"
            if i > 1 and D[i - 1][j] + MATCH_GAP < best:
                best, how = D[i - 1][j] + MATCH_GAP, "A"
            if j > 1 and D[i][j - 1] + MATCH_GAP < best:
                best, how = D[i][j - 1] + MATCH_GAP, "B"
            D[i][j], P[i][j] = best, how
    pairs, i, j = [], n, m
    while i > 0 and j > 0:
        how = P[i][j]
        if how == "M":
            pairs.append((i - 1, j - 1)); i -= 1; j -= 1
        elif how == "A":
            pairs.append((i - 1, None)); i -= 1
        else:
            pairs.append((None, j - 1)); j -= 1
    return list(reversed(pairs))


def estimate(entries, m, nmasters):
    """Fraction for master m at every entry, interpolating where m has no native node."""
    native = [e.get(m) for e in entries]
    out = list(native)
    idx = [k for k, v in enumerate(native) if v is not None]
    for k, v in enumerate(native):
        if v is not None:
            continue
        prev = max(i for i in idx if i < k)
        nxt = next((i for i in idx if i > k), None)
        lo = native[prev]
        hi = native[nxt] if nxt is not None else 1.0
        # borrow the relative position from the nearest master that has prev, k and nxt
        ratio = None
        for d in sorted(range(nmasters), key=lambda x: abs(x - m)):
            e = entries
            if e[k].get(d) is None or e[prev].get(d) is None:
                continue
            dlo = e[prev][d]
            dhi = e[nxt].get(d) if nxt is not None else 1.0
            if dhi is None:
                continue
            if dhi > dlo:
                ratio = (e[k][d] - dlo) / (dhi - dlo)
                break
        if ratio is None:
            ratio = 0.5
        out[k] = lo + (hi - lo) * ratio
    return out


def make_compatible_contour(contours):
    """contours: one corresponding contour per master. Returns per-master segment lists
    with identical node counts."""
    nm = len(contours)
    fracs = [node_fractions(c) for c in contours]
    entries = [{0: f} for f in fracs[0]]
    for m in range(1, nm):
        prev_est = estimate(entries, m - 1, nm)
        pairs = align(prev_est, fracs[m])
        new_entries = []
        for i, j in pairs:
            if i is not None:
                e = entries[i]
                if j is not None:
                    e[m] = fracs[m][j]
                new_entries.append(e)
            else:
                new_entries.append({m: fracs[m][j]})
        entries = new_entries

    result = []
    for m, c in enumerate(contours):
        target = estimate(entries, m, nm)
        native_idx = {round(f, 12): k for k, f in enumerate(fracs[m])}
        segs = []
        # walk native segments, inserting splits for the non-native targets that fall inside
        bounds = fracs[m] + [1.0]
        for k, s in enumerate(c):
            lo, hi = bounds[k], bounds[k + 1]
            inner = [t for e, t in zip(entries, target) if m not in e and lo < t < hi]
            inner.sort()
            rest, consumed = s, lo
            for t in inner:
                span = hi - consumed
                if span <= 0:
                    break
                f = (t - consumed) / span
                tt = t_at_length_fraction(rest, f)
                a, rest = split_segment(rest, tt)
                segs.append(a)
                consumed = t
            segs.append(rest)
        result.append(segs)
    # unify segment types: if any master has a curve, promote lines to cubics
    n = {len(r) for r in result}
    if len(n) != 1:
        return None
    for k in range(len(result[0])):
        if any(len(r[k]) == 4 for r in result):
            for r in result:
                if len(r[k]) == 2:
                    p0, p3 = r[k]
                    r[k] = (p0, lerp(p0, p3, 1 / 3), lerp(p0, p3, 2 / 3), p3)
    return result


def make_compatible(glyph_contours):
    """glyph_contours: per-master contour lists. Returns per-master compatible lists or None."""
    if len({signature(c) for c in glyph_contours}) == 1:
        return glyph_contours, "native"
    aligned = [glyph_contours[0]]
    for m in range(1, len(glyph_contours)):
        o = match_contours(aligned[m - 1], glyph_contours[m])
        if o is None:
            return None, "contour-count"
        aligned.append(o)
    if len({signature(c) for c in aligned}) == 1:
        return aligned, "reordered"
    out = [[] for _ in aligned]
    for ci in range(len(aligned[0])):
        r = make_compatible_contour([a[ci] for a in aligned])
        if r is None:
            return None, "align-failed"
        for m, segs in enumerate(r):
            out[m].append(segs)
    if len({signature(c) for c in out}) != 1:
        return None, "align-failed"
    return out, "repaired"


# ---------------------------------------------------------------- TrueType output

def draw_tt(contours_per_master):
    """Draw compatible cubic contours into TTGlyphPens with shared cu2qu conversion."""
    pens = [TTGlyphPen(None) for _ in contours_per_master]
    for ci in range(len(contours_per_master[0])):
        cs = [c[ci] for c in contours_per_master]
        for pen, c in zip(pens, cs):
            pen.moveTo(c[0][0])
        for si in range(len(cs[0])):
            segs = [c[si] for c in cs]
            if len(segs[0]) == 2:
                for pen, s in zip(pens, segs):
                    pen.lineTo(s[1])
            else:
                splines = curves_to_quadratic([list(s) for s in segs], [CU2QU_ERROR] * len(segs))
                for pen, sp in zip(pens, splines):
                    pen.qCurveTo(*sp[1:])
        for pen in pens:
            pen.closePath()
    return [p.glyph() for p in pens]


def to_truetype(font, glyphs):
    del font["CFF "]
    font.sfntVersion = "\x00\x01\x00\x00"
    glyf = newTable("glyf")
    glyf.glyphOrder = font.getGlyphOrder()
    glyf.glyphs = glyphs
    font["glyf"] = glyf
    font["loca"] = newTable("loca")
    font["head"].glyphDataFormat = 0
    maxp = font["maxp"]
    maxp.tableVersion = 0x00010000
    for attr in ("maxZones", "maxTwilightPoints", "maxStorage", "maxFunctionDefs",
                 "maxInstructionDefs", "maxStackElements", "maxSizeOfInstructions"):
        setattr(maxp, attr, 0)
    maxp.maxZones = 1
    maxp.maxComponentElements = maxp.maxComponentDepth = 0
    post = font["post"]
    post.formatType = 2.0
    post.extraNames, post.mapping = [], {}
    # TrueType expects lsb == xMin of the control box; CFF lsbs don't follow that rule
    hmtx = font["hmtx"]
    for name in font.getGlyphOrder():
        g = glyf[name]
        g.recalcBounds(glyf)
        hmtx[name] = (hmtx[name][0], g.xMin if g.numberOfContours else 0)
    return font


def set_names(font, style, weight):
    name = font["name"]
    for rec in list(name.names):
        if rec.nameID in (1, 2, 3, 4, 6, 16, 17):
            name.removeNames(nameID=rec.nameID)
    name.setName(FAMILY, 1, 3, 1, 0x409)
    name.setName("Regular", 2, 3, 1, 0x409)
    name.setName(f"{PS_FAMILY}-{style}", 3, 3, 1, 0x409)
    name.setName(FAMILY, 4, 3, 1, 0x409)
    name.setName(f"{PS_FAMILY}-{style}", 6, 3, 1, 0x409)
    name.setName(FAMILY, 16, 3, 1, 0x409)
    name.setName(style, 17, 3, 1, 0x409)


# ---------------------------------------------------------------- main

def main():
    fonts = [TTFont(ROOT / "sources" / f"OpenRunde-{s}.otf") for s, _ in MASTERS]
    order = fonts[0].getGlyphOrder()
    assert all(f.getGlyphOrder() == order for f in fonts), "glyph orders differ"
    gsets = [f.getGlyphSet() for f in fonts]

    stats, fallbacks = {}, []
    tt_glyphs = [{} for _ in fonts]
    for name in order:
        per_master = [read_contours(gs, name) for gs in gsets]
        compat, how = make_compatible(per_master)
        if compat is None:
            # keep the glyph static: use the Regular outline in every master
            fallbacks.append((name, how))
            compat = [per_master[0]] * len(fonts)
            how = "static"
        stats[how] = stats.get(how, 0) + 1
        for m, g in enumerate(draw_tt(compat)):
            tt_glyphs[m][name] = g

    print("glyph stats:", stats)
    if fallbacks:
        print(f"{len(fallbacks)} glyphs kept static:", ", ".join(n for n, _ in fallbacks))

    ds = DesignSpaceDocument()
    axis = AxisDescriptor()
    axis.tag, axis.name = "wght", "Weight"
    axis.minimum, axis.default, axis.maximum = 400, 400, 700
    ds.addAxis(axis)
    for (style, weight), font, glyphs in zip(MASTERS, fonts, tt_glyphs):
        to_truetype(font, glyphs)
        set_names(font, style, weight)
        src = SourceDescriptor()
        src.font = font
        src.styleName = style
        src.location = {"Weight": weight}
        ds.addSource(src)
        inst = InstanceDescriptor()
        inst.familyName, inst.styleName = FAMILY, style
        inst.postScriptFontName = f"{PS_FAMILY}-{style}"
        inst.location = {"Weight": weight}
        ds.addInstance(inst)

    # GPOS lookups are structured differently per master, so they can't be merged.
    # Build without them and reuse Regular's kerning/mark positioning (static for now).
    default_gpos = fonts[0]["GPOS"]
    for f in fonts:
        del f["GPOS"]
    vf, _, _ = varLib.build(ds)
    vf["GPOS"] = default_gpos
    buildStatTable(vf, [{
        "tag": "wght", "name": "Weight",
        "values": [
            {"value": 400, "name": "Regular", "flags": 0x2, "linkedValue": 700},
            {"value": 500, "name": "Medium"},
            {"value": 600, "name": "Semibold"},
            {"value": 700, "name": "Bold"},
        ],
    }])
    vf["name"].setName(f"{PS_FAMILY}", 25, 3, 1, 0x409)  # variations PostScript name prefix

    out = ROOT / "fonts"
    out.mkdir(exist_ok=True)
    ttf = out / f"{PS_FAMILY}[wght].ttf"
    vf.save(ttf)
    vf.flavor = "woff2"
    vf.save(out / f"{PS_FAMILY}[wght].woff2")
    print("wrote", ttf, "and .woff2")
    return 0


if __name__ == "__main__":
    sys.exit(main())
