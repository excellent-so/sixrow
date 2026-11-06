"""Render proof sheets from the built variable fonts (white on black, like the samples).

    .venv/bin/python tools/proof.py            # → proof/*.png
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from build import family_names, vf_path  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "proof"
MONO, PROP = vf_path(True), vf_path(False)
MONO_NAME, PROP_NAME = family_names(True)[0], family_names(False)[0]
COMBINING = "\u0300\u0301\u0302\u0303\u0304\u0306\u0307\u0308\u030A\u030B\u030C\u0326\u0327\u0328"

TOBACCO = ["    BLUE TOBACCO SMOKE SPIRALING", "(SERPENTINE) ON WET FILMS & WOOD",
           "GLAZES, MUTE CHROME FIXTURES AND", "VELVET DRAPES. A STYGIAN HALL OF",
           "MIRRORS. INVISIBLE FINGERS FLOOD", "AQUAMARINE VEINS OF THE MAROONED",
           "MARINER AS GHOSTS DISPENSE THEIR", "FROTHY (IGNEOUS) POTIONS."]


CHARSET = ["ABCDEFGHIJKLMNOPQRSTUVWXYZ", "0123456789 $€£¥¢ %&@#*", ".,:;!?¡¿ '\"‘’“”‚„ ‹›«» -–—_",
           "()[]{}/\\|¦ +−=<>×÷± ^~`°©®™§¶•·…¬¤ ªº ¹²³ ¼½¾ µ",
           "ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝÞẞ", "ĀĂĄĆĈĊČĎĐĒĔĖĘĚĜĞĠĢĤĦĨĪĬĮİĴĶĹĻĽĿŁŃŅŇŌŎŐŒŔŖŘŚŜŞŠŢŤŦ",
           "ŨŪŬŮŰŲŴŶŸŹŻŽ ȘȚ ẀẂẄỲ ĲŊŉ ´`ˆˇ˘˙¨˚˝˜¯¸˛",
           "H" + "H".join(COMBINING) + " (H + combining mark)",
           "lowercase sets as caps: the quick brown fox ijŋĸȷ"]


def font(path, size, wght=400, wdth=100, slnt=0, scan=10):
    f = ImageFont.truetype(str(path), size)
    f.set_variation_by_axes([wght, wdth, slnt, scan])
    return f


def text_block(lines, f, line_h, pad=40, width=None):
    w = width or int(max(f.getlength(l) for l in lines)) + 2 * pad
    im = Image.new("L", (w, int(line_h * len(lines)) + 2 * pad), 0)
    d = ImageDraw.Draw(im)
    for i, l in enumerate(lines):
        d.text((pad, pad + i * line_h), l, fill=255, font=f)
    return im


def stack(images, gap=30):
    w = max(i.width for i in images)
    out = Image.new("L", (w, sum(i.height for i in images) + gap * (len(images) - 1)), 0)
    y = 0
    for i in images:
        out.paste(i, (0, y)); y += i.height + gap
    return out


def label(im, text, size=22):
    f = ImageFont.load_default(size)
    lab = Image.new("L", (im.width, size + 16), 0)
    ImageDraw.Draw(lab).text((10, 6), text, fill=140, font=f)
    return stack([lab, im], gap=0)


def main():
    OUT.mkdir(exist_ok=True)
    # 1. tobacco paragraph at the sample's scale: cap = 6 rows × 17.05 px → size ≈ 17.05/120*1000
    size = round(17.05 / 120 * 1000)
    f = font(MONO, size)
    im = text_block(TOBACCO, f, 126, pad=0)
    sample = Image.open(ROOT / "reference/samples/mono-upright-tobacco.png").convert("L").crop((40, 750, 2460, 1745))
    canvas = Image.new("L", sample.size, 0)
    from fontTools.ttLib import TTFont
    asc = TTFont(MONO)["hhea"].ascent  # PIL sets text from the ascender down; caps are 708 tall
    canvas.paste(im, (int(51.6 - 40), 759 - 750 - round(size * (asc - 708) / 1000)))
    a, b0 = np.array(sample) > 128, np.array(canvas) > 128
    best = (0, 0, 0)
    for dy in range(-6, 7):
        for dx in range(-10, 11):
            b = np.roll(np.roll(b0, dy, 0), dx, 1)
            iou = (a & b).sum() / max((a | b).sum(), 1)
            best = max(best, (iou, dx, dy))
    iou, dx, dy = best
    b = np.roll(np.roll(b0, dy, 0), dx, 1)
    rgb = Image.merge("RGB", (Image.fromarray((a * 255).astype("uint8")), Image.fromarray((b * 255).astype("uint8")),
                              Image.fromarray((a * 255).astype("uint8"))))
    rgb.save(OUT / "overlay-tobacco.png")  # magenta = sample only, green = build only, white = both
    print(f"tobacco overlay IoU vs sample: {iou:.3f}")

    # 2. full character set, mono + proportional
    sheets = []
    for path, nm in ((MONO, MONO_NAME), (PROP, f"{PROP_NAME} (proportional)")):
        f = font(path, 64)
        sheets.append(label(text_block(CHARSET, f, 100), f"{nm} - Regular - full character set"))
    stack(sheets).save(OUT / "charset.png")

    # 3. axes
    rows = []
    for wght in (100, 200, 300, 400, 500, 600, 700, 800):
        rows.append(label(text_block(["X-CTRY RACING 2.5L I4 TURBO"], font(MONO, 56, wght=wght), 80), f"wght {wght}"))
    stack(rows, gap=4).save(OUT / "axis-weight.png")
    rows = []
    for wdth in (75, 87.5, 100, 112.5, 125, 150):
        rows.append(label(text_block(["FINISH LINE 4X200 RELAY"], font(PROP, 56, wdth=wdth), 80), f"wdth {wdth}"))
    stack(rows, gap=4).save(OUT / "axis-width.png")
    rows = []
    for slnt in (0, -4, -8, -12, -16):
        rows.append(label(text_block(["AEROBIC TRAIL RUNNING"], font(PROP, 56, slnt=slnt), 80), f"slnt {slnt}"))
    for scan in (0, 10, 20, 30):
        rows.append(label(text_block(["FULLCOURT 2.5L I4 TURBO"], font(PROP, 56, scan=scan, slnt=-16), 80), f"SCAN {scan} (italic)"))
    stack(rows, gap=4).save(OUT / "axis-slant-scan.png")

    # 4. recreate the owner's italic samples for side-by-side review
    f = font(MONO, 150, slnt=-16, wght=300)
    text_block(["2.5L I4 TURBO"], f, 200).save(OUT / "recreate-turbo.png")
    f = font(MONO, 150, slnt=-16)
    text_block(["AEROBIC", "TRAIL RUNNING", "FULLCOURT", "4X200 RELAY", "FINISH LINE"], f, 165).save(OUT / "recreate-aerobic.png")
    print("proofs →", OUT)




def review_sheet():
    """Every glyph drawn large with its name; drafts (designed by Claude, not traced) marked in amber."""
    import json
    from fontTools.ttLib import TTFont
    rep = json.loads((ROOT / "build/report.json").read_text())
    for path, fam, prop in ((MONO, MONO_NAME, False), (PROP, PROP_NAME, True)):
        drafts = set(rep[fam]["src_draft"])
        tt = TTFont(path)
        rev = {}  # glyph → the code point to show: the capital where there is one
        for k, v in sorted(tt.getBestCmap().items()):
            if v not in rev or (chr(k).isupper() and not chr(rev[v]).isupper()):
                rev[v] = k
        names = [n for n in tt.getGlyphOrder() if n in rev and n not in ("space", "uni00A0")]
        f = font(path, 90)
        lf = ImageFont.load_default(16)
        cols, cw, ch = 12, 160, 170
        im = Image.new("RGB", (cols * cw, ((len(names) + cols - 1) // cols) * ch), (0, 0, 0))
        d = ImageDraw.Draw(im)
        for i, n in enumerate(names):
            x, y = (i % cols) * cw, (i // cols) * ch
            col = (255, 190, 60) if n in drafts else (255, 255, 255)
            c = chr(rev[n])
            d.text((x + 25, y + 28), ("\u00A0" + c) if c in COMBINING else c, fill=col, font=f)
            d.text((x + 8, y + 6), n[:18], fill=(120, 120, 120) if n not in drafts else (200, 140, 40), font=lf)
        im.save(OUT / f"review-{fam.replace(' ', '').lower()}.png")


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "review":
    review_sheet()


if __name__ == "__main__" and len(sys.argv) == 1:
    main()
    review_sheet()
