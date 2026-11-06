"""Parse Sixrow glyph grid sources and resolve the per-family glyph sets.

A glyph design is a set of rows keyed by row index k (0 = the row sitting on the
baseline, 5 = cap-top row, 6 = accent row above caps, -1 = descender row). Each row
holds (top_runs, bottom_runs): ink intervals in half-units for its upper and lower
half. A full row simply has identical top and bottom runs.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from fontTools import agl

CAP_ROWS = 6

Run = tuple[float, float]


def runs_of(pattern: str) -> list[Run]:
    out, start = [], None
    for i, ch in enumerate(pattern + "."):
        if ch == "#" and start is None:
            start = i
        elif ch != "#" and start is not None:
            out.append((float(start), float(i)))
            start = None
    return out


def union_runs(a: list[Run], b: list[Run]) -> list[Run]:
    merged: list[list[float]] = []
    for s, e in sorted(a + b):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


@dataclass
class Glyph:
    name: str
    width: float
    rows: dict[int, tuple[list[Run], list[Run]]] = field(default_factory=dict)
    unicodes: list[int] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)

    @property
    def is_mark(self) -> bool:
        """A drawing used only to build accented letters (not a glyph in the font)."""
        return self.tags.get("mark") == "1"

    @property
    def combining(self) -> str | None:
        """'top' or 'bottom' for a zero-width combining mark in the font, else None."""
        return self.tags.get("combining")

    def attach_x(self) -> float:
        """The column (hu) a mark lines up with the base letter's centre: its `attach=` tag,
        else the middle of its ink."""
        if "attach" in self.tags:
            return float(self.tags["attach"])
        ext = self.ink_extent()
        return (ext[0] + ext[1]) / 2 if ext else self.width / 2

    def copy(self, name: str | None = None) -> "Glyph":
        return Glyph(
            name or self.name,
            self.width,
            {k: (list(t), list(b)) for k, (t, b) in self.rows.items()},
            list(self.unicodes) if name is None else [],
            dict(self.tags),
        )

    def ink_extent(self) -> tuple[float, float] | None:
        xs = [x for t, b in self.rows.values() for r in t + b for x in r]
        return (min(xs), max(xs)) if xs else None

    def shifted(self, dx: float) -> "Glyph":
        g = self.copy()
        g.rows = {
            k: ([(a + dx, b + dx) for a, b in t], [(a + dx, b + dx) for a, b in bo])
            for k, (t, bo) in self.rows.items()
        }
        return g

    def profile(self, k: int) -> tuple[float, float] | None:
        """leftmost / rightmost ink in row k (either half)."""
        t, b = self.rows.get(k, ([], []))
        xs = [x for r in t + b for x in r]
        return (min(xs), max(xs)) if xs else None

    def ascii(self) -> list[str]:
        if not self.rows:
            return []
        lines = []
        for k in range(max(self.rows), min(self.rows) - 1, -1):
            t, b = self.rows.get(k, ([], []))
            for runs in ([t] if t == b else [t, b]):
                line = ["."] * int(self.width)
                for a, e in runs:
                    for i in range(int(a), int(e)):
                        if 0 <= i < len(line):
                            line[i] = "#"
                lines.append(("|" if t == b else "'") + " " + "".join(line) + ("  <- baseline" if k == 0 else ""))
        return lines


HEADER = re.compile(r"^@\s+(\S+)(.*)$")


def parse_glyph_file(path: Path) -> dict[str, Glyph]:
    glyphs: dict[str, Glyph] = {}
    cur: dict | None = None

    def finish():
        if cur is None:
            return
        name = cur["name"]
        above, below = cur["above"], cur["below"]
        widths = {len(p) for items in (above, below) for kind, p in items if kind != "empty"}
        if len(widths) != 1:
            raise ValueError(f"{path.name}: glyph {name}: inconsistent row widths {sorted(widths)}")
        width = widths.pop()
        rows: dict[int, tuple[list[Run], list[Run]]] = {}

        def rows_from(items):
            eq = []  # list of (top_pattern|None, bottom_pattern|None)
            i = 0
            while i < len(items):
                kind, p = items[i]
                if kind == "full":
                    eq.append((p, p)); i += 1
                elif kind == "half":
                    if i + 1 >= len(items) or items[i + 1][0] != "half":
                        raise ValueError(f"{path.name}: glyph {name}: unpaired half row")
                    eq.append((p, items[i + 1][1])); i += 2
                else:
                    eq.extend([(None, None)] * p); i += 1
            return eq

        up = rows_from(above)
        for idx, (t, b) in enumerate(up):
            k = len(up) - 1 - idx
            if t is not None:
                rows[k] = (runs_of(t), runs_of(b))
        for idx, (t, b) in enumerate(rows_from(below)):
            if t is not None:
                rows[-1 - idx] = (runs_of(t), runs_of(b))
        rows = {k: v for k, v in rows.items() if v[0] or v[1]}
        if len(up) > CAP_ROWS + 1:
            raise ValueError(f"{path.name}: glyph {name}: more than one row above the caps")
        g = Glyph(name, float(width), rows, cur["unicodes"], cur["tags"])
        if name in glyphs:
            raise ValueError(f"{path.name}: duplicate glyph {name}")
        glyphs[name] = g

    for lineno, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#") and not line.startswith(("|", "'")):
            continue
        m = HEADER.match(line)
        if m:
            finish()
            name, rest = m.group(1), m.group(2).split()
            unis = [int(t[2:], 16) for t in rest if t.upper().startswith("U+")]
            tags = dict(t.split("=", 1) for t in rest if "=" in t)
            cur = {"name": name, "unicodes": unis, "tags": tags, "above": [], "below": [], "in_below": False}
            continue
        if cur is None:
            raise ValueError(f"{path.name}:{lineno}: row outside a glyph")
        target = cur["below"] if cur["in_below"] else cur["above"]
        if line.strip() == "---":
            cur["in_below"] = True
        elif line.startswith("|"):
            target.append(("full", line[1:].strip()))
        elif line.startswith("'"):
            target.append(("half", line[1:].strip()))
        elif line.startswith("~"):
            target.append(("empty", int(line[1:].strip())))
        else:
            raise ValueError(f"{path.name}:{lineno}: cannot parse {line!r}")
    finish()
    for g in glyphs.values():
        if not g.unicodes and "." not in g.name and not g.is_mark:
            u = agl.toUnicode(g.name)
            if len(u) == 1:
                g.unicodes = [ord(u)]
    return glyphs


def parse_composites(path: Path) -> list[tuple[str, str, list[str], dict[str, str]]]:
    """`Name = Base + mark [+ mark] [key=value …]` → (name, base, marks, tags)."""
    out = []
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        name, rhs = (s.strip() for s in line.split("=", 1))
        words = rhs.split()
        tags = dict(w.split("=", 1) for w in words if "=" in w)
        parts = [p.strip() for p in " ".join(w for w in words if "=" not in w).split("+")]
        out.append((name, parts[0], parts[1:], tags))
    return out


def parse_combining(path: Path) -> list[tuple[str, int, str, dict[str, str]]]:
    """`name U+XXXX = drawing [key=value …]` → (name, codepoint, drawing, tags)."""
    out = []
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        lhs, rhs = (s.strip() for s in line.split("=", 1))
        name, cp = lhs.split()
        words = rhs.split()
        out.append((name, int(cp[2:], 16), words[0], dict(w.split("=", 1) for w in words[1:])))
    return out


def compose(name: str, base: Glyph, marks: list[Glyph], tags: dict[str, str] | None = None) -> Glyph:
    """Union the marks onto the base, each lined up on the base's centre (see Glyph.attach_x).
    If a mark is wider than a narrow base (proportional I, J…), the glyph widens to fit it so
    accents never collide with neighbours."""
    width = base.width
    for m in marks:
        ext = m.ink_extent()
        if ext:
            width = max(width, ext[1] - ext[0])
    g = base.shifted((width - base.width) / 2).copy(name)
    g.width = width
    g.tags = {"src": "composite", "base": base.name, **(tags or {})}
    for m in marks:
        dx = width / 2 - m.attach_x()
        for k, (t, b) in m.shifted(dx).rows.items():
            bt, bb = g.rows.get(k, ([], []))
            g.rows[k] = (union_runs(bt, t), union_runs(bb, b))
    u = agl.toUnicode(name)
    g.unicodes = [ord(u)] if len(u) == 1 else []
    return g


def trim(g: Glyph) -> Glyph:
    ext = g.ink_extent()
    if ext is None:
        return g
    lo, hi = max(ext[0], 0), min(ext[1], g.width)
    t = g.shifted(-lo)
    t.width = hi - lo
    return t


def build_family(src: Path, proportional: bool) -> dict[str, Glyph]:
    mono = parse_glyph_file(src / "glyphs-mono.txt")
    if (src / "glyphs-brand.txt").exists():
        mono.update(parse_glyph_file(src / "glyphs-brand.txt"))
    base = dict(mono)
    if proportional:
        over = parse_glyph_file(src / "glyphs-proportional.txt")
        if (src / "glyphs-brand-proportional.txt").exists():
            over.update(parse_glyph_file(src / "glyphs-brand-proportional.txt"))
        for n, g in mono.items():
            if n not in over and not g.is_mark and n != ".notdef":
                tg = trim(g)
                tg.unicodes = g.unicodes
                base[n] = tg
        base.update(over)
    out = dict(base)
    for name, b, marks, tags in parse_composites(src / "composites.txt"):
        out[name] = compose(name, base[b], [base[m] for m in marks], tags)
    if (src / "combining.txt").exists():
        for name, cp, drawing, tags in parse_combining(src / "combining.txt"):
            m = mono[drawing]  # marks are never trimmed: both families share one drawing
            g = m.copy(name)
            g.unicodes = [cp]
            g.tags = {"combining": "bottom" if min(m.rows) < 0 else "top",
                      **({"attach": m.tags["attach"]} if "attach" in m.tags else {}), **tags}
            out[name] = g
    return out


def cmap_for(glyphs: dict[str, Glyph]) -> dict[int, str]:
    """explicit codepoints, plus lowercase → the same capital glyph (uppercase-only font)."""
    cmap: dict[int, str] = {}
    for g in glyphs.values():
        if g.is_mark:
            continue
        if g.combining:  # U+03xx marks are category Mn: never case-mapped
            cmap.update({u: g.name for u in g.unicodes})
            continue
        for u in g.unicodes:
            cmap[u] = g.name
    explicit = dict(cmap)
    for cp in list(range(0x0000, 0x0250)) + list(range(0x1E00, 0x1F00)):
        if cp in explicit:
            continue
        ch = chr(cp)
        if not unicodedata.category(ch).startswith("L"):
            continue
        up = ch.upper()
        if len(up) == 1 and ord(up) in explicit and up != ch:
            cmap[cp] = explicit[ord(up)]
    for cp, gname in explicit.items():
        low = chr(cp).lower()
        if len(low) == 1 and ord(low) not in cmap:
            cmap[ord(low)] = gname
    return cmap
