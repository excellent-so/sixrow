"""Build Sixrow Mono + Sixrow (proportional) variable fonts and static instances.

    .venv/bin/python tools/build.py            # full build → build/
    .venv/bin/python tools/build.py --fast     # variable fonts only (no statics)

Geometry: every glyph is a set of upright rectangles generated from the grid drawings.
x-coordinates are a fixed function linear in (letter scale, stem width), y-coordinates are
linear in row height, and the italic is a per-row shift — so 8 masters reproduce the whole
design space exactly and every axis interpolates without distortion.

Family names, file names and the name table all come from sources/config.toml.
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import sys
import tomllib
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument, InstanceDescriptor, SourceDescriptor
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.otlLib.builder import buildStatTable
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import ttProgram
from fontTools.varLib import build as varlib_build
from fontTools.varLib.instancer import instantiateVariableFont

sys.path.insert(0, str(Path(__file__).parent))
from glyphs import Glyph, build_family, cmap_for, parse_composites  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "sources"
OUT = ROOT / "build"
CFG = tomllib.loads((SRC / "config.toml").read_text())
# Reproducible output: fontTools stamps head.created/modified from SOURCE_DATE_EPOCH when it is set.
os.environ.setdefault("SOURCE_DATE_EPOCH", str(int(datetime.datetime.fromisoformat(
    CFG["family"]["release_date"]).replace(tzinfo=datetime.timezone.utc).timestamp())))
G = CFG["grid"]
AX = CFG["axes"]
P = G["row_pitch"]
S_DESIGN = G["design_stem"]
DASH_MAX = 5  # runs this narrow (hu) are vertical strokes: they take the weight's stem width

WEIGHTS = [(100, "Thin"), (200, "ExtraLight"), (300, "Light"), (400, "Regular"),
           (500, "Medium"), (600, "SemiBold"), (700, "Bold"), (800, "ExtraBold")]
WIDTHS = [(75, "Condensed"), (87.5, "SemiCondensed"), (100, "Normal"),
          (112.5, "SemiExpanded"), (125, "Expanded"), (150, "ExtraExpanded")]


def stem_for(wght: float) -> float:
    pts = sorted((float(k), float(v)) for k, v in AX["wght"]["stem"].items())
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= wght <= x1:
            return y0 + (y1 - y0) * (wght - x0) / (x1 - x0)
    raise ValueError(wght)


@dataclass(frozen=True)
class Params:
    wght: float = AX["wght"]["default"]
    wdth: float = AX["wdth"]["default"]
    slnt: float = AX["slnt"]["default"]
    scan: float = AX["SCAN"]["default"]

    @property
    def hu(self):  # font units per half-unit
        return G["hu"] * self.wdth / 100

    @property
    def stem(self):
        return stem_for(self.wght)

    @property
    def h(self):  # inked height of a row
        return P * (1 - self.scan / 100)

    @property
    def shear(self):  # stair-step shift per row
        return math.tan(math.radians(-self.slnt)) * P


def x_map(g: Glyph, p: Params):
    """Return (E, W') — design x (hu) → font units, and the drawn body width."""
    s, W, sp, hu = S_DESIGN, g.width, p.stem, p.hu
    if W < 2 * s:  # single-stroke glyph (proportional I, | …): pure stem scaling
        return (lambda x: x * sp / s), W * sp / s

    def phi(x):
        if x <= s:
            return x / s
        if x >= W - s:
            return (x - W) / s
        return 1 - 2 * (x - s) / (W - 2 * s)

    def E(x):
        if W == 2 * s and x == s:
            return x * hu
        return x * hu + (sp - s * hu) * phi(x)

    return E, W * hu


def rects(g: Glyph, p: Params) -> list[tuple[float, float, float, float]]:
    E, _ = x_map(g, p)
    h, out = p.h, []

    def xr(a, b):
        if b - a <= DASH_MAX:
            c, half = E((a + b) / 2), p.stem * (b - a) / (2 * S_DESIGN)
            return c - half, c + half
        return E(a), E(b)

    for k in sorted(g.rows, reverse=True):
        top, bot = g.rows[k]
        y0, dx = k * P, (k - 2.5) * p.shear
        for a, b in top:
            x0, x1 = xr(a, b)
            if (a, b) in bot:
                out.append((x0 + dx, y0, x1 + dx, y0 + h))
            else:
                out.append((x0 + dx, y0 + h / 2, x1 + dx, y0 + h))
        for a, b in bot:
            if (a, b) not in top:
                x0, x1 = xr(a, b)
                out.append((x0 + dx, y0, x1 + dx, y0 + h / 2))
    return out


def vector_pieces(g: Glyph) -> list[tuple[int, list[tuple[float, float]]]]:
    """Brand glyphs drawn from a true vector outline (the Excellent star), sliced into the
    font's rows at the default scanline gap. Returns [(row k, polygon in wdth=100 units)].
    Computed once, so every master shares the same contour structure."""
    import pathops
    import star
    v = star.vertices()
    x0, y0, x1, y1 = star.bbox(v)
    W = g.width * G["hu"]
    cap = 5 * P + Params().h
    k = W / (x1 - x0)
    H = (y1 - y0) * k
    if H > cap:  # height-limited
        k, H = cap / (y1 - y0), cap
    ox = (W - (x1 - x0) * k) / 2
    oy = (cap - H) / 2
    pts = [(ox + (x - x0) * k, oy + (y1 - y) * k) for x, y in v]  # y up
    out = []
    h0 = Params().h
    for row in range(CAP_ROWS_FONT):
        band = pathops.Path()
        band.moveTo(-10, row * P); band.lineTo(W + 10, row * P); band.lineTo(W + 10, row * P + h0)
        band.lineTo(-10, row * P + h0); band.close()
        sp = pathops.Path()
        sp.moveTo(*pts[0])
        for q in pts[1:]:
            sp.lineTo(*q)
        sp.close()
        res = pathops.op(sp, band, pathops.PathOp.INTERSECTION)
        for contour in res.contours:
            poly = [seg[1][-1] for seg in contour.segments if seg[1]]
            if len(poly) >= 3:
                out.append((row, poly))
    return out


CAP_ROWS_FONT = 6
_VEC_CACHE: dict = {}


def vector_contours(g: Glyph, p: Params) -> list[list[tuple[float, float]]]:
    key = (g.name, g.width)
    if key not in _VEC_CACHE:
        _VEC_CACHE[key] = vector_pieces(g)
    h0, ws, polys = Params().h, p.wdth / 100, []
    for row, poly in _VEC_CACHE[key]:
        dx = (row - 2.5) * p.shear
        poly2 = [(x * ws + dx, row * P + (y - row * P) * p.h / h0) for x, y in poly]
        area = sum(xa * yb - xb * ya for (xa, ya), (xb, yb) in zip(poly2, poly2[1:] + poly2[:1]))
        polys.append(poly2[::-1] if area > 0 else poly2)  # TrueType: clockwise outer contours
    return polys


def layout(g: Glyph, p: Params, mono: bool) -> tuple[float, float]:
    """(advance, x-offset of the glyph body)."""
    E, Wp = x_map(g, p)
    if g.combining:  # zero width, attach point on the origin: the mark feature always moves it
        return 0, -E(g.attach_x())
    if mono:
        adv = G["mono_advance"] * p.hu
        return adv, (adv - Wp) / 2
    sb = G["prop_sidebearing"] * p.wdth / 100
    return Wp + 2 * sb, sb


def family_names(mono: bool):
    """("Sixrow Mono", "SixrowMono") — the family name and its PostScript/file form."""
    fam = CFG["family"]["name"] + (" " + CFG["family"]["mono_suffix"] if mono else "")
    return fam, fam.replace(" ", "")


def vf_path(mono: bool, ext: str = "ttf") -> Path:
    """build/variable/Sixrow[SCAN,slnt,wdth,wght].ttf (or …Mono…, or .woff2)."""
    return OUT / "variable" / f"{family_names(mono)[1]}[SCAN,slnt,wdth,wght].{ext}"


# ───────────────────────────── kerning ─────────────────────────────
KERN_PUNCT = ("period comma colon semicolon hyphen endash emdash quotesingle quotedbl quoteleft quoteright "
              "quotedblleft quotedblright quotesinglbase quotedblbase slash exclam question parenleft "
              "parenright bracketleft bracketright guilsinglleft guilsinglright guillemotleft guillemotright "
              "asterisk ampersand").split()


def auto_kern(glyphs: dict[str, Glyph]) -> tuple[dict[str, list[str]], list[tuple[str, str, int]]]:
    """Row-profile kerning in hu. Rows are rigid, so the gap between two glyphs is fully
    described by their per-row left/right ink extents; close up pairs whose tightest row
    leaves more air than a pair of straight stems would."""
    members: dict[str, list[str]] = {}
    for name, base, *_ in parse_composites(SRC / "composites.txt"):
        members.setdefault(base, [base]).append(name)
    keys = [n for n in glyphs if (len(n) == 1 and n.isalpha()) or n in KERN_PUNCT or n in
            ("zero one two three four five six seven eight nine AE OE Oslash Eth Thorn Eng IJ".split())]
    rows = [k for k in range(-1, 6)]
    pairs = []
    for a in keys:
        ga = glyphs[a]
        for b in keys:
            gb = glyphs[b]
            gaps = []
            for k in rows:
                pa, pb = ga.profile(k), gb.profile(k)
                if pa and pb:
                    gaps.append((ga.width - pa[1]) + pb[0])
            if not gaps:
                continue
            lo, mean = min(gaps), sum(gaps) / len(gaps)
            if lo < 2:  # some row already sits stem-to-stem: leave the pair alone
                continue
            v = max(round(-(0.5 * lo + 0.15 * (mean - lo))), -7)
            if v <= -1:
                pairs.append((a, b, v))
    classes = {k: members.get(k, [k]) for k in keys}
    return classes, pairs


def mark_code(glyphs: dict[str, Glyph], cmap: dict[int, str], mono: bool, p: Params) -> list[str]:
    """mark + mkmk: combining marks (U+0300…) attach to every letter, so decomposed text sets
    like the precomposed letters. The marks are drawn in their rows (6 above, -1 below);
    anchors are only horizontal centres, plus one row up/down when a letter or mark already
    fills the accent row."""
    marks = [n for n, g in glyphs.items() if g.combining]
    if not marks:
        return []
    letters = sorted({n for cp, n in cmap.items()
                      if unicodedata.category(chr(cp)).startswith("L") and not glyphs[n].combining}
                     | {"space", "uni00A0"})  # a lone mark is shown on a (no-break) space

    def cx(n, col=None):
        g = glyphs[n]
        E, _ = x_map(g, p)
        return round(layout(g, p, mono)[1] + E(g.width / 2 if col is None else col))

    ys = {"top": (6 * P, 7 * P), "bottom": (0, -P)}  # (attach, stack) heights per class
    fea = [f"markClass {n} <anchor {cx(n, glyphs[n].attach_x())} {ys[glyphs[n].combining][0]}> "
           f"@{glyphs[n].combining};" for n in marks]
    fea.append("feature mark {")
    for n in letters:
        g = glyphs[n]
        top = ys["top"][1] if 6 in g.rows else ys["top"][0]
        bot = ys["bottom"][1] if min(g.rows, default=0) < 0 else ys["bottom"][0]
        fea.append(f"  pos base {n} <anchor {cx(n)} {top}> mark @top <anchor {cx(n)} {bot}> mark @bottom;")
    fea += ["} mark;", "", "feature mkmk {"]
    for n in marks:
        c = glyphs[n].combining
        fea.append(f"  pos mark {n} <anchor {cx(n, glyphs[n].attach_x())} {ys[c][1]}> mark @{c};")
    fea += ["} mkmk;", "", "table GDEF {",
            f"  GlyphClassDef [{' '.join(n for n in glyphs if n != '.notdef' and n not in marks)}], , "
            f"[{' '.join(marks)}], ;", "} GDEF;", ""]
    return fea


def feature_code(glyphs: dict[str, Glyph], cmap: dict[int, str], mono: bool, p: Params, kern) -> str:
    fea = ["languagesystem DFLT dflt;", "languagesystem latn dflt;", ""]
    fea += mark_code(glyphs, cmap, mono, p)
    fea += ["feature ss01 {", '  featureNames { name "Plain zero"; };', "  sub zero by zero.plain;", "} ss01;", ""]
    if not mono:
        fea += ["feature tnum {", "  sub one by one.tf;", "} tnum;", ""]
        classes, pairs = kern
        for k, mem in classes.items():
            fea.append(f"@k_{k.replace('.', '_')} = [{' '.join(m for m in mem if m in glyphs)}];")
        fea += ["feature kern {", "  lookupflag IgnoreMarks;"]
        for a, b, v in pairs:
            fea.append(f"  pos @k_{a} @k_{b} {round(v * p.hu)};")
        fea.append("} kern;")
    return "\n".join(fea)


# ───────────────────────────── masters ─────────────────────────────
def build_master(glyphs: dict[str, Glyph], order: list[str], cmap: dict[int, str], mono: bool,
                 p: Params, kern) -> TTFont:
    fam, _ = family_names(mono)
    fb = FontBuilder(G["upm"], isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    ttglyphs, metrics = {}, {}
    for n in order:
        g = glyphs[n]
        adv, off = layout(g, p, mono)
        pen = TTGlyphPen(None)
        xs = []
        for poly in (vector_contours(g, p) if g.tags.get("vector") else []):
            pts = [(round(x + off), round(y)) for x, y in poly]
            pen.moveTo(pts[0])
            for q in pts[1:]:
                pen.lineTo(q)
            pen.closePath()
            xs += [q[0] for q in pts]
        for x0, y0, x1, y1 in ([] if g.tags.get("vector") else rects(g, p)):
            x0, x1, y0, y1 = round(x0 + off), round(x1 + off), round(y0), round(y1)
            pen.moveTo((x0, y0)); pen.lineTo((x0, y1)); pen.lineTo((x1, y1)); pen.lineTo((x1, y0))
            pen.closePath()
            xs.append(x0)
        ttglyphs[n] = pen.glyph()
        metrics[n] = (round(adv), min(xs) if xs else 0)
    fb.setupGlyf(ttglyphs)
    fb.setupHorizontalMetrics(metrics)
    M = CFG["metrics"]
    asc, desc, gap = M["ascender"], M["descender"], M["line_gap"]
    fb.setupHorizontalHeader(ascent=asc, descent=desc, lineGap=gap)
    fb.setupNameTable({"familyName": fam, "styleName": "Regular"})
    fb.setupOS2(
        version=4, achVendID=CFG["family"]["vendor_id"], usWeightClass=int(p.wght), usWidthClass=5,
        fsType=0, sTypoAscender=asc, sTypoDescender=desc, sTypoLineGap=gap,
        usWinAscent=asc, usWinDescent=-desc,
        sxHeight=round(5 * P + p.h), sCapHeight=round(5 * P + p.h), fsSelection=0x40 | 0x80,
        panose=_panose(mono),
    )
    fb.setupPost(isFixedPitch=int(mono), underlinePosition=-P // 2, underlineThickness=P // 4)
    addOpenTypeFeaturesFromString(fb.font, feature_code(glyphs, cmap, mono, p, kern))
    return fb.font


def _panose(mono: bool):
    from fontTools.ttLib.tables.O_S_2f_2 import Panose
    pn = Panose()
    pn.bFamilyType, pn.bSerifStyle, pn.bProportion = 2, 11, (9 if mono else 3)
    return pn


MASTERS = {
    "default": Params(),
    "wght_min": Params(wght=AX["wght"]["min"]),
    "wght_max": Params(wght=AX["wght"]["max"]),
    "wdth_min": Params(wdth=AX["wdth"]["min"]),
    "wdth_max": Params(wdth=AX["wdth"]["max"]),
    "slnt_min": Params(slnt=AX["slnt"]["min"]),
    "scan_min": Params(scan=AX["SCAN"]["min"]),
    "scan_max": Params(scan=AX["SCAN"]["max"]),
}


def designspace(masters: dict[str, TTFont], mono: bool) -> DesignSpaceDocument:
    fam, _ = family_names(mono)
    ds = DesignSpaceDocument()
    for tag, name in (("wght", "Weight"), ("wdth", "Width"), ("slnt", "Slant"), ("SCAN", "Scanline")):
        a = AxisDescriptor()
        a.tag, a.name = tag, name
        a.minimum, a.default, a.maximum = AX[tag]["min"], AX[tag]["default"], AX[tag]["max"]
        a.labelNames = {"en": name}
        ds.addAxis(a)
    for key, font in masters.items():
        p = MASTERS[key]
        s = SourceDescriptor()
        s.font, s.name = font, key
        s.familyName, s.styleName = fam, key
        s.location = {"Weight": p.wght, "Width": p.wdth, "Slant": p.slnt, "Scanline": p.scan}
        ds.addSource(s)
    for wght, wname in WEIGHTS:
        for slnt in (0, AX["slnt"]["min"]):
            style = wname if slnt == 0 else ("Italic" if wname == "Regular" else f"{wname} Italic")
            i = InstanceDescriptor()
            i.familyName, i.styleName = fam, style
            i.location = {"Weight": wght, "Width": 100, "Slant": slnt, "Scanline": AX["SCAN"]["default"]}
            ds.addInstance(i)
    for wdth, wdname in WIDTHS:
        if wdth == 100:
            continue
        for wght, wname in ((400, "Regular"), (700, "Bold")):
            i = InstanceDescriptor()
            i.familyName = fam
            i.styleName = f"{wdname} {wname}" if wname != "Regular" else wdname
            i.location = {"Weight": wght, "Width": wdth, "Slant": 0, "Scanline": AX["SCAN"]["default"]}
            ds.addInstance(i)
    return ds


def finish_vf(vf: TTFont, mono: bool):
    fam, ps = family_names(mono)
    fcfg = CFG["family"]
    name = vf["name"]
    ver = fcfg["version"]
    for nid, val in {
        0: fcfg["copyright"], 1: fam, 2: "Regular", 3: f"{ver};{fcfg['vendor_id']};{ps}-Regular",
        4: f"{fam} Regular", 5: f"Version {ver}", 6: f"{ps}-Regular", 8: fcfg["manufacturer"],
        9: fcfg["designer"], 11: fcfg["vendor_url"], 12: fcfg["designer_url"], 13: fcfg["license"],
        14: fcfg["license_url"], 25: ps,
    }.items():
        name.setName(val, nid, 3, 1, 0x409)
    vf["head"].fontRevision = float(ver)
    name.removeNames(nameID=1, platformID=1)
    buildStatTable(vf, [
        dict(tag="wght", name="Weight", values=[
            dict(value=w, name=n, **({"flags": 0x2, "linkedValue": 700} if w == 400 else {})) for w, n in WEIGHTS]),
        dict(tag="wdth", name="Width", values=[
            dict(value=w, name=n, **({"flags": 0x2} if w == 100 else {})) for w, n in WIDTHS]),
        dict(tag="slnt", name="Slant", values=[
            dict(value=0, name="Upright", flags=0x2), dict(value=AX["slnt"]["min"], name="Italic")]),
        dict(tag="SCAN", name="Scanline", values=[
            dict(value=0, name="Solid"), dict(value=AX["SCAN"]["default"], name="Scan", flags=0x2),
            dict(value=AX["SCAN"]["max"], name="Wide Scan")]),
    ], elidedFallbackName=2)
    for g in vf["glyf"].glyphs.values():
        if g.numberOfContours > 0:
            g.flags[0] |= 0x40  # OVERLAP_SIMPLE: rects may touch/overlap at axis extremes
    fix_nonhinting(vf)
    vf["OS/2"].recalcUnicodeRanges(vf)
    vf["OS/2"].recalcCodePageRanges(vf)
    vf["OS/2"].recalcAvgCharWidth(vf)


def fix_nonhinting(f: TTFont):
    """What `gftools fix-nonhinting` does to an unhinted TTF: a gasp table set to smooth at
    every size, and a prep program that turns on smart dropout control (SCANCTRL 511,
    SCANTYPE 4) so thin stems don't drop out on Windows."""
    gasp = newTable("gasp")
    gasp.gaspRange = {0xFFFF: 0x000F}
    prog = ttProgram.Program()
    prog.fromAssembly(["PUSHW[]", "511", "SCANCTRL[]", "PUSHB[]", "4", "SCANTYPE[]"])
    prep = newTable("prep")
    prep.program = prog
    f["gasp"], f["prep"] = gasp, prep


def make_static(vf: TTFont, mono: bool, wght: int, wname: str, italic: bool) -> tuple[TTFont, str]:
    fam, ps = family_names(mono)
    loc = {"wght": wght, "wdth": 100, "slnt": AX["slnt"]["min"] if italic else 0, "SCAN": AX["SCAN"]["default"]}
    f = instantiateVariableFont(vf, loc, inplace=False)
    for t in ("STAT",):
        if t in f:
            del f[t]
    ribbi = wname in ("Regular", "Bold")
    style = ("Italic" if wname == "Regular" else f"{wname} Italic") if italic else wname
    sub = style if ribbi else ("Italic" if italic else "Regular")
    fam1 = fam if ribbi else f"{fam} {wname}"
    psn = f"{ps}-{style.replace(' ', '')}"
    name = f["name"]
    for nid in (1, 2, 3, 4, 6, 16, 17, 25):
        name.removeNames(nameID=nid)
    for nid, val in {1: fam1, 2: sub, 3: f"{CFG['family']['version']};{CFG['family']['vendor_id']};{psn}",
                     4: f"{fam} {style}", 6: psn, 16: fam, 17: style}.items():
        name.setName(val, nid, 3, 1, 0x409)
    os2 = f["OS/2"]
    os2.usWeightClass = wght
    sel = 0x80
    if italic:
        sel |= 0x01
    if wname == "Bold":
        sel |= 0x20
    if not italic and wname != "Bold":
        sel |= 0x40
    os2.fsSelection = sel
    f["head"].macStyle = (1 if wname == "Bold" else 0) | (2 if italic else 0)
    if italic:
        f["post"].italicAngle = float(AX["slnt"]["min"])
        f["hhea"].caretSlopeRise, f["hhea"].caretSlopeRun = 1000, round(1000 * math.tan(math.radians(-AX["slnt"]["min"])))
    return f, psn


def build(fast: bool = False):
    OUT.mkdir(exist_ok=True)
    report = {}
    for mono in (True, False):
        fam, ps = family_names(mono)
        glyphs = {n: g for n, g in build_family(SRC, proportional=not mono).items() if not g.is_mark}
        if mono:
            glyphs.pop("one.tf", None)
            wide = [n for n, g in glyphs.items() if g.width > G["mono_advance"]]
            assert not wide, f"mono glyphs wider than the cell: {wide}"
        order = [".notdef"] + [n for n in glyphs if n != ".notdef"]
        cmap = cmap_for(glyphs)
        kern = None if mono else auto_kern(glyphs)
        masters = {k: build_master(glyphs, order, cmap, mono, p, kern) for k, p in MASTERS.items()}
        ds = designspace(masters, mono)
        vf, _, _ = varlib_build(ds)
        finish_vf(vf, mono)
        vdir = OUT / "variable"
        vdir.mkdir(exist_ok=True)
        vf.save(vf_path(mono))
        vf.flavor = "woff2"
        vf.save(vf_path(mono, "woff2"))
        vf.flavor = None
        rep = {"glyphs": len(order), "codepoints": len(cmap),
               "combining": sorted(n for n, g in glyphs.items() if g.combining),
               "kern_pairs": len(kern[1]) if kern else 0,
               "src_sample": sorted(n for n, g in glyphs.items() if g.tags.get("src") == "sample"),
               "src_draft": sorted(n for n, g in glyphs.items() if g.tags.get("src") == "draft")}
        if not fast:
            sdir = OUT / "static" / ps
            sdir.mkdir(parents=True, exist_ok=True)
            for wght, wname in WEIGHTS:
                for italic in (False, True):
                    f, psn = make_static(TTFont(vf_path(mono)), mono, wght, wname, italic)
                    f.save(sdir / f"{psn}.ttf")
                    f.flavor = "woff2"
                    f.save(sdir / f"{psn}.woff2")
            rep["statics"] = len(WEIGHTS) * 2
        report[fam] = rep
        print(f"{fam}: {rep['glyphs']} glyphs, {rep['codepoints']} codepoints, "
              f"{rep['kern_pairs']} kern pairs → {vf_path(mono).relative_to(ROOT)}")
    (OUT / "report.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    build(ap.parse_args().fast)
