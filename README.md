# Open Runde Variable

A variable-font fork of [Open Runde](https://github.com/lauridskern/open-runde) 1.0.1, with one axis:

| Axis | Tag  | Range     | Default |
|------|------|-----------|---------|
| Weight | `wght` | 400–700 | 400 |

Named instances: Regular, Medium, Semibold, Bold.

## Build

```sh
pip install -r requirements.txt
python3 scripts/build.py
```

Outputs `fonts/OpenRundeVariable[wght].ttf` and `.woff2`.

## How it works

The four static OTFs in `sources/` are used as masters. They were flattened per weight, so about a third
of the glyphs have different node structures from one weight to the next. `scripts/build.py`:

1. Matches contours across masters and fixes direction and start points.
2. Aligns nodes along each contour by normalised arc length, then splits segments wherever one master
   has a node another lacks. Splitting doesn't change any master's shape.
3. Converts the compatible cubics to TrueType quadratics with a single cu2qu conversion shared by all masters.
4. Merges the masters with `fontTools.varLib` and adds STAT.

Each master instance matches its original static font within 2 font units.

## Known limitations

- GPOS (kerning and mark positioning) is structured differently in each master, so the font uses Regular's
  GPOS at every weight.
- 15 rare glyphs change contour topology between weights (Ⓦ, ₦, ₩, Ҋ, Ӎ, …). These stay at their
  Regular shape.

## Specimen

```sh
python3 -m http.server 8765
open http://localhost:8765/specimen/
```
