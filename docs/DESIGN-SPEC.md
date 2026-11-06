# Sixrow design spec (measured from the samples)

All numbers measured from `reference/samples/` (Matt Waite's own lettering) and turned into the build geometry in
`sources/config.toml`.

## Vertical: rows
| | Samples | Font (UPM 1000) |
|---|---|---|
| Rows per capital | 6 (+1 descender row for Q, comma, $; +1 accent row above) | 6 |
| Row pitch | 17.05 px (tobacco), 8 px (clothing), 65.6 px (turbo) | 120 units |
| Scanline gap | 9 % of pitch (tobacco), 13–15 % (aerobic/turbo) | 10 % default, **SCAN** axis 0–30 % |
| Cap height | 5 × pitch + inked row | 708 |
| Line spacing | 7.39 × pitch (tobacco) | 1200 (asc 960 / desc −240 / gap 0 in hhea, typo and win; until 1.000: 888 = 768 / −120). The sample's spacing is CSS `line-height: 0.74` |

Every element fills exactly one row (or half a row, for fine detail like the inner C of ©).
The scanline gap cuts through vertical strokes, which gives the dashed look.

## Horizontal: half-unit grid
| | Samples | Font |
|---|---|---|
| Letter body | 47 px at 17.05 px pitch = 2.76 × pitch | 24 hu × 14 = 336 units |
| Stem (vertical dash) | 7.5 px = 0.16 of body | 4 hu (54 units at Regular) |
| Rounded-corner inset | 5 px | 2 hu |
| Mono advance | 75.85 px = 4.45 × pitch | 38 hu = 532 units |
| Proportional sidebearing | — (no samples) | 60 units per side |

## Italic
Each row shifts right by **0.287 × row pitch**, the same in all three italic samples:
tan(16°) = 0.2867. Rows stay upright; it's a staircase, not a shear. Implemented as the **slnt**
axis (0 to −16), centred on mid-cap height so glyphs stay centred in their advance.

## Weight
The lighter TURBO sample has stems at 0.115 of the body; tobacco and aerobic have 0.155–0.16.
Bars always fill the row. Weight changes only how thick the vertical dashes are, and stems grow
inward so the letter's outer width stays constant. **wght** 100 → 800 = 16 → 92 units.

## Construction (why every axis interpolates exactly)
Each glyph is a set of upright rectangles. An x coordinate in the drawings maps to font units
through a fixed piecewise function that is linear in (letter scale, stem width):

    E(x) = x·hu + (stem − 4·hu)·φ(x)    φ: 0 at the edges, ±1 at the stems' inner edges

Runs ≤ 5 hu wide are strokes: they keep their centre at E(centre) and take the stem width.
Wider runs are bars: both ends map through E. y depends only on row height, and italic is a
per-row offset. So 8 masters (default, wght min/max, wdth min/max, slnt min, SCAN min/max)
describe the whole design space with no interpolation error.
