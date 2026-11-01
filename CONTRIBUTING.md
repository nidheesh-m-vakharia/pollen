# Contributing

## Setup

```sh
pip install -r requirements.txt
```

## Build and check

```sh
python3 scripts/build.py   # writes fonts/Pollen[ROND,wght].ttf + .woff2 and specimen/glyphs.json
python3 scripts/check.py   # axes, names, credits and the glyph list
```

Commit the rebuilt files in `fonts/` and `specimen/glyphs.json` together with the change that produced them.

## Specimen site

```sh
python3 scripts/serve.py   # http://localhost:8765/specimen/ (no-cache, so rebuilt fonts show up)
```

The site is static. On localhost it fetches the font with a fresh query string on every load; in production it uses the fixed version in `specimen/index.html` (`const bust`). **Bump that string whenever you ship a rebuilt font**, so browsers and the CDN pick it up.

### Deploying to Cloudflare Pages

- Framework preset: **None**
- Build command: *(leave empty)*
- Build output directory: `/`

`_redirects` sends `/` to `/specimen/`, and `_headers` sets CORS on `/fonts/*` plus cache lifetimes.

### Banner

`assets/banner.png` is a 1280×640 screenshot of `assets/banner.html` (served from the repo root so the font loads). It doubles as the GitHub social preview and the site's `og:image`.

## How the build works

The four static Open Runde 1.0.1 OTFs in `sources/` are the masters. They were flattened per weight, so about a third of the glyphs have different point structures from one weight to the next. `scripts/build.py`:

1. Matches contours across masters and fixes direction and start points.
2. Aligns nodes along each contour by normalised arc length, then splits segments wherever one master has a node another lacks. Splitting doesn't change any master's shape.
3. Builds a sharp copy of each weight for the roundness axis: every short curve that rounds off a corner between straight edges is collapsed onto the point where those edges meet. Curves between curves (dots, periods, bowls) stay round. The point structure doesn't change, so sharp and round outlines interpolate.
4. Converts the compatible cubics to TrueType quadratics with a single cu2qu conversion shared by all masters.
5. Merges the eight masters (4 weights × 2 roundness values) with `fontTools.varLib` and adds STAT.

At `ROND 100`, each master instance matches its original static font within 2 font units.

## Known limitations

- GPOS (kerning and mark positioning) is structured differently in each source master, so Pollen uses the Regular master's GPOS at every weight.
- 15 rare glyphs change contour topology between weights (Ⓦ, ₦, ₩, Ҋ, Ӎ, …) and keep their Regular shape at every weight.
- A few curve-to-curve terminals, like the hook of `?`, stay slightly rounded at `ROND 0`.

## Pull requests

Branch from `main`, open a pull request, and fill in the template. `main` is protected: changes land through pull requests once CI passes.

## License

By contributing you agree that your contributions are licensed under the [SIL Open Font License 1.1](OFL.txt).
