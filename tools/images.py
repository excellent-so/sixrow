"""Render the release images from the built fonts: black on white, set only in Sixrow.

    .venv/bin/python tools/images.py            # → release/images/*.png and release/new-glyphs.png

Every word in every image is set in Sixrow or Sixrow Mono (captions included), and the
text is shaped with HarfBuzz (Pillow's raqm layout), so kerning and mark positioning apply.
"""
from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from build import AX, CFG, family_names, vf_path  # noqa: E402
from proof import CHARSET  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REL = ROOT / "release"
IMG = REL / "images"
MONO, PROP = vf_path(True), vf_path(False)
NAME = CFG["family"]["name"].upper()
URL = CFG["family"]["vendor_url"].removeprefix("https://www.").upper()
INK, PAPER, DIM = 0, 255, 120

# Glyphs added for 1.000 (all src=draft), by code point. Mapped-only code points are shown
# with the glyph they use.
ADDED = [
    ([0x021A, 0x021B], "T comma below"), ([0x0162, 0x0163], "T cedilla (was comma)"),
    ([0x00AA], "ordfeminine"), ([0x00BA], "ordmasculine"),
    ([0x02C6], "circumflex"), ([0x02C7], "caron"), ([0x02D8], "breve"), ([0x02D9], "dotaccent"),
    ([0x02DA], "ring"), ([0x02DB], "ogonek"), ([0x02DC], "tilde"), ([0x02DD], "hungarumlaut"),
    *[([cp], "comb") for cp in (0x0300, 0x0301, 0x0302, 0x0303, 0x0304, 0x0306, 0x0307, 0x0308,
                                0x030A, 0x030B, 0x030C, 0x0326, 0x0327, 0x0328)],
    ([0x0132, 0x0133], "IJ"), ([0x014A, 0x014B], "Eng"), ([0x0149], "napostrophe"),
    ([0x00B9], "onesuperior"), ([0x00B2], "twosuperior"), ([0x00B3], "threesuperior"),
    ([0x00BC], "onequarter"), ([0x00BD], "onehalf"), ([0x00BE], "threequarters"), ([0x00B5], "mu"),
    ([0x0237], "= J"), ([0x0138], "= K"),
]
SAMPLES = [
    ("ROMANIAN", "Știința și învățătura sunt ale țării. Ţ ţ cedilla, Ț ț comma."),
    ("CZECH", "Příliš žluťoučký kůň úpěl ďábelské ódy."),
    ("DANISH", "Høj bølge på åen; blåbærgrød, æbleskiver og rødgrød."),
]


def font(path: Path, size: float, wght=400, wdth=100, slnt=0, scan=None) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(path), round(size), layout_engine=ImageFont.Layout.RAQM)
    f.set_variation_by_axes([wght, wdth, slnt, AX["SCAN"]["default"] if scan is None else scan])
    return f


def fit(path: Path, text: str, width: float, **axes) -> ImageFont.FreeTypeFont:
    """The largest size at which `text` fits in `width` px."""
    size = 400.0
    for _ in range(3):
        size *= width / font(path, size, **axes).getlength(text)
    return font(path, size, **axes)


def cap(f: ImageFont.FreeTypeFont) -> float:
    return f.size * 0.708  # cap height (708/1000 at the default scanline gap)


def put(d: ImageDraw.ImageDraw, x: float, base: float, text: str, f, fill=INK):
    """Set text with its baseline at y=base."""
    d.text((x, base), text, font=f, fill=fill, anchor="ls")


def canvas(w: int, h: int):
    im = Image.new("L", (w, h), PAPER)
    return im, ImageDraw.Draw(im)


def caption(d, x, base, text, size=22, fill=INK, **axes):
    put(d, x, base, text, font(MONO, size, **axes), fill)


# ───────────────────────────── release images ─────────────────────────────
def card():
    im, d = canvas(1200, 630)
    m = 72
    f = fit(PROP, NAME, 1200 - 2 * m, wght=700)
    f = font(PROP, min(f.size, 250 / 0.708), wght=700)  # cap height at most 250 px
    put(d, m, 80 + cap(f), NAME, f)
    caption(d, m, 430, "A FREE SCANLINE TYPEFACE FROM EXCELLENT", 34)
    caption(d, m, 486, "WEIGHT 100–800 · WIDTH 75–150 · SLANT 0 TO −16° · SCANLINE 0–30%", 22, DIM)
    caption(d, m, 558, f"{URL} · OFL-1.1", 22)
    im.save(IMG / "card-1200x630.png")


def preview(path: Path, out: str):
    fam = family_names(path == MONO)[0].upper()
    im, d = canvas(1600, 800)
    m = 80
    f = fit(path, fam, 1600 - 2 * m, wght=700)
    if cap(f) > 240:
        f = font(path, 240 / 0.708, wght=700)
    put(d, m, 80 + cap(f), fam, f)
    y = 80 + cap(f) + 70
    body = font(path, 64)
    for line in ("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "0123456789 ÀÉÎÕÜ ÇŞȚ ÆØÅ ẞ &@$€£ ?!"):
        size = min(64, 64 * (1600 - 2 * m) / body.getlength(line))
        fl = font(path, size)
        put(d, m, y + cap(fl), line, fl)
        y += cap(fl) + 46
    caption(d, m, 800 - 56, f"{fam} {CFG['family']['version']} · 4 VARIABLE AXES · 16 STATIC STYLES · {URL}", 22, DIM)
    im.save(IMG / out)


def square():
    """SIX over ROW at full width: the same weight, the scanline gap shut and then wide open."""
    im, d = canvas(1080, 1080)
    m = 80
    lines = [("SIX", dict(wght=800, scan=0)), ("ROW", dict(wght=800, scan=30))]
    size = min(fit(PROP, t, 1080 - 2 * m, **ax).size for t, ax in lines)
    size = min(size, (1080 - 2 * m - 150) / 2 / 0.708)
    y = m
    for t, ax in lines:
        f = font(PROP, size, **ax)
        put(d, m, y + cap(f), t, f)
        y += cap(f) + 60
    caption(d, m, 1080 - m - 44, "SCANLINE 0 AND 30", 26, DIM)
    caption(d, m, 1080 - m, f"A FREE TYPEFACE FROM EXCELLENT · {URL}", 26)
    im.save(IMG / "square-1080.png")


def charset():
    im, d = canvas(2000, 1000)
    m = 60
    f = font(MONO, 10)
    widest = max(CHARSET, key=lambda l: f.getlength(l))
    size = min(10 * (2000 - 2 * m) / f.getlength(widest), (1000 - 2 * m - 60) / len(CHARSET) / 0.708 / 1.45)
    f = font(MONO, size)
    y = m
    for line in CHARSET:
        put(d, m, y + cap(f), line, f)
        y += cap(f) * 1.45
    caption(d, m, 1000 - 40, f"{family_names(True)[0].upper()} · REGULAR · CHARACTER SET · LOWERCASE SETS AS CAPITALS", 20, DIM)
    im.save(IMG / "charset-2000x1000.png")


def axes():
    m = 70
    spec = {
        "wght": ([(w, dict(wght=w)) for w in (100, 200, 300, 400, 500, 600, 700, 800)], "WEIGHT", "FINISH LINE 4X200 TRAIL RUNNING"),
        "wdth": ([(w, dict(wdth=w)) for w in (75, 87.5, 100, 112.5, 125, 150)], "WIDTH", "TRAIL RUNNING"),
        "slnt": ([(s, dict(slnt=s)) for s in (0, -4, -8, -12, -16)], "SLANT", "AEROBIC TRAIL RELAY"),
        "scan": ([(s, dict(scan=s)) for s in (0, 5, 10, 15, 20, 25, 30)], "SCANLINE", "SIX ROWS AND ONE GAP"),
    }
    for tag, (steps, label, text) in spec.items():
        im, d = canvas(1600, 800)
        avail = 800 - 2 * 60 - 40
        pitch = avail / len(steps)
        size = pitch / 0.708 / 1.3
        widest = max(font(PROP, size, **ax).getlength(text) for _, ax in steps)
        size = min(size, size * (1600 - 2 * m - 150) / widest)
        y = 60
        for v, ax in steps:
            f = font(PROP, size, **ax)
            base = y + (pitch + cap(f)) / 2
            caption(d, m, base, f"{v:g}".replace("-", "−"), 22, DIM)
            put(d, m + 150, base, text, f)
            y += pitch
        caption(d, m, 800 - 40, f"{NAME} · {label} ({tag if tag != 'scan' else 'SCAN'})", 22, DIM)
        im.save(IMG / f"axes-{tag}-1600x800.png")


# ───────────────────────────── new-glyphs sheet ─────────────────────────────
def new_glyphs():
    """Every glyph added for 1.000, large, in both families; then running text in Romanian,
    Czech and Danish, composed (NFC) and decomposed (NFD)."""
    cols, cw, chh = 8, 250, 300
    rows_n = (len(ADDED) + cols - 1) // cols
    W = cols * cw + 80
    text_h = 1500
    im, d = canvas(W, 150 + rows_n * chh + text_h)
    caption(d, 40, 70, f"{NAME} {CFG['family']['version']} · GLYPHS ADDED (SRC=DRAFT) · BLACK = MONO, GREY = PROPORTIONAL", 26)
    caption(d, 40, 112, "COMBINING MARKS ARE SHOWN ON A GREY H. MAPPED CODE POINTS (= J, = K) USE AN EXISTING GLYPH.", 20, DIM)
    gm, gp = font(MONO, 170), font(PROP, 170)
    lab = font(MONO, 18)
    for i, (cps, note) in enumerate(ADDED):
        x0, y0 = 40 + (i % cols) * cw, 150 + (i // cols) * chh
        d.rectangle([x0, y0, x0 + cw - 10, y0 + chh - 10], outline=210)
        base = y0 + 40 + cap(gm) + 30
        ch = chr(cps[0])
        if unicodedata.combining(ch):  # a lone mark is centred on its origin: place it over H's centre
            adv = gm.getlength("H")
            put(d, x0 + 20, base, "H", gm, 190)
            put(d, x0 + 20 + adv / 2, base, ch, gm)
            pa = gp.getlength("H")
            put(d, x0 + 20 + adv + 18, base, "H", gp, 225)
            put(d, x0 + 20 + adv + 18 + pa / 2, base, ch, gp, 150)
        else:
            put(d, x0 + 20, base, ch, gm)
            put(d, x0 + 30 + gm.getlength(ch), base, ch, gp, 150)
        put(d, x0 + 12, y0 + chh - 46, " ".join(f"U+{c:04X}" for c in cps), lab)
        put(d, x0 + 12, y0 + chh - 22, note.upper(), lab, DIM)
    y = 150 + rows_n * chh + 40
    big, dec_note = font(PROP, 64), font(MONO, 20)
    for lang, text in SAMPLES:
        for form in ("NFC", "NFD"):
            s = unicodedata.normalize(form, text)
            f = big if big.getlength(s) < W - 80 else font(PROP, 64 * (W - 80) / big.getlength(s))
            caption(d, 40, y + 24, f"{lang} · {'COMPOSED (NFC)' if form == 'NFC' else 'DECOMPOSED (NFD): ' + str(len(s)) + ' CODE POINTS'}", 20, DIM)
            put(d, 40, y + 40 + cap(f) + 26, s, f)
            y += cap(f) + 120
    caption(d, 40, y + 30, "MARKS ON LETTERS WITH NO PRECOMPOSED FORM (GPOS MARK + MKMK):", 20, DIM)
    s = "B́ F̈ J̌ M̧ Q̊ V̆ X̄ Z̦ Ł̃ Ĳ́ Ǟ Ḉ"
    put(d, 40, y + 60 + cap(big) + 30, s, big)
    put(d, 40, y + 60 + 2 * cap(big) + 110, s, font(MONO, 64, wght=800, wdth=125, slnt=-16, scan=20))
    caption(d, 40, y + 60 + 2 * cap(big) + 160, "SAME LINE IN SIXROW MONO AT WGHT 800, WDTH 125, SLNT −16, SCAN 20", 20, DIM)
    h = int(y + 60 + 2 * cap(big) + 200)
    im.crop((0, 0, W, h)).save(REL / "new-glyphs.png")


def main():
    IMG.mkdir(parents=True, exist_ok=True)
    new_glyphs()
    card()
    preview(PROP, "preview-1600x800.png")
    preview(MONO, "preview-mono-1600x800.png")
    square()
    charset()
    axes()
    print("images →", IMG, "and", REL / "new-glyphs.png")


if __name__ == "__main__":
    main()
