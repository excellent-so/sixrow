"""Generate specimen/index.html — a self-contained interactive type tester (fonts embedded).

    .venv/bin/python tools/specimen.py
"""
from __future__ import annotations

import base64
import html
import json
import sys
import unicodedata
from pathlib import Path

from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).parent))
from build import CFG, family_names, vf_path  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "specimen"


def b64(p: Path) -> str:
    return base64.b64encode(p.read_bytes()).decode()


def glyph_cells(ttf: Path, drafts: set[str]) -> str:
    tt = TTFont(ttf)
    cmap = tt.getBestCmap()
    seen, cells = set(), []
    for cp in sorted(cmap):
        ch, name = chr(cp), cmap[cp]
        if name in seen or name in ("space", "uni00A0", "uni00AD") or unicodedata.category(ch).startswith("C"):
            continue
        up = ch.upper()
        if len(up) == 1 and up != ch and cmap.get(ord(up)) == name:
            continue  # lowercase codepoints just alias the capitals
        seen.add(name)
        cls = "cell draft" if name in drafts else "cell"
        shown = ("\u00A0" + ch) if unicodedata.combining(ch) else ch  # a lone mark sits on a no-break space
        cells.append(f'<li class="{cls}" title="{html.escape(name)} · U+{cp:04X}"><span>{html.escape(shown)}</span></li>')
    return "\n".join(cells)


PRICES = [("AAMOU048FA01BLK001", "LIGHTWEIGHT PUFFER JACKET", "$360.00"),
          ("AAM0243FA01BLK0003", "BLACK FLEECE CREWNECK SWEATSHIRT", "$120.00"),
          ("AAMPA64FA01GRY0008", "GRAY STRAIGHT LEG SWEATPANTS", "$235.00"),
          ("AAMSW025A01BRW0006", "WORK BOOT", "$267.00"),
          ("AAUB018FA01MTY0001", "GREY BOXY PULLOVER HOODIE", "$118.00"),
          ("AAU0073LE06BLK0001", "BELT BAG - X", "$296.00")]


def main():
    rep = json.loads((ROOT / "build" / "report.json").read_text())
    mono_name, prop_name = family_names(True)[0], family_names(False)[0]
    rows = "\n".join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>" for a, b, c in PRICES)
    page = TEMPLATE
    for k, v in {
        "%%MONO%%": b64(vf_path(True, "woff2")), "%%PROP%%": b64(vf_path(False, "woff2")), "%%PRICES%%": rows,
        "%%CELLS_MONO%%": glyph_cells(vf_path(True), set(rep[mono_name]["src_draft"])),
        "%%CELLS_PROP%%": glyph_cells(vf_path(False), set(rep[prop_name]["src_draft"])),
        "%%NGLYPH%%": str(rep[mono_name]["glyphs"]), "%%NCP%%": str(rep[mono_name]["codepoints"]),
        "%%NKERN%%": f'{rep[prop_name]["kern_pairs"]:,}',
        "%%MONO_NAME%%": mono_name, "%%PROP_NAME%%": prop_name, "%%NAME_UC%%": prop_name.upper(),
        "%%VERSION%%": CFG["family"]["version"],
        "%%URL%%": CFG["family"]["vendor_url"], "%%URL_SHORT%%": CFG["family"]["vendor_url"].removeprefix("https://www."),
    }.items():
        page = page.replace(k, v)
    OUT.mkdir(exist_ok=True)
    (OUT / "index.html").write_text(page)
    print("specimen →", OUT / "index.html", f"({len(page)//1024} KB)")


TEMPLATE = r"""<meta charset="utf-8">
<title>%%PROP_NAME%% Specimen</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500&display=swap">
<style>
@font-face { font-family: "%%MONO_NAME%%"; src: url(data:font/woff2;base64,%%MONO%%) format("woff2");
  font-weight: 100 800; font-stretch: 75% 150%; font-style: oblique 0deg 16deg; }
@font-face { font-family: "%%PROP_NAME%%"; src: url(data:font/woff2;base64,%%PROP%%) format("woff2");
  font-weight: 100 800; font-stretch: 75% 150%; font-style: oblique 0deg 16deg; }
:root {
  color-scheme: dark;
  --ground: #050505; --panel: #0d0d0b; --rule: #24241f; --ink: #f2f2ee; --dim: #85857c;
  --faint: #4a4a44; --draft: #e3b341;
  --ui: "Instrument Sans", ui-sans-serif, system-ui, sans-serif;
  --wght: 400; --wdth: 100; --slnt: 0; --scan: 10; --size: 120px; --fam: "%%MONO_NAME%%";
}
html, body { background: var(--ground); color: var(--ink); }
body { font: 15px/1.5 var(--ui); padding-inline: clamp(16px, 4vw, 48px); padding-block: 28px 64px; }
.x { font-family: var(--fam), ui-monospace, monospace; font-synthesis: none;
  font-variation-settings: "wght" var(--wght), "wdth" var(--wdth), "slnt" var(--slnt), "SCAN" var(--scan); }
.label { font-family: "%%MONO_NAME%%", ui-monospace, monospace; font-size: 13px; letter-spacing: .04em;
  color: var(--dim); text-transform: uppercase; font-variation-settings: "wght" 400, "SCAN" 10; }
header { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 8px 24px;
  border-bottom: 1px solid var(--rule); padding-bottom: 14px; }
header h1 { margin: 0; font: inherit; }
header h1 .x { font-size: 28px; --fam: "%%MONO_NAME%%"; }
header p { margin: 0; color: var(--dim); max-width: 60ch; }

#tester { font-size: var(--size); line-height: 1.12; margin: 28px 0 8px; outline: none; overflow-wrap: anywhere;
  min-height: 1.2em; caret-color: var(--draft); }
#tester:focus-visible { box-shadow: inset 0 -1px 0 var(--faint); }

.controls { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px 28px;
  padding: 18px 0; border-block: 1px solid var(--rule); }
.ctl { display: grid; grid-template-columns: 1fr auto; gap: 4px 10px; align-items: center; }
.ctl output { font-family: "%%MONO_NAME%%", monospace; font-size: 15px; font-variant-numeric: tabular-nums; }
.ctl input[type=range] { grid-column: 1 / -1; width: 100%; accent-color: var(--ink); }
.ctl small { grid-column: 1 / -1; color: var(--faint); font-size: 12px; }
.row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding-top: 14px; }
.seg { display: inline-flex; border: 1px solid var(--rule); }
.seg button, .chip { font: 13px var(--ui); color: var(--dim); background: none; border: 0; padding: 7px 12px; cursor: pointer; }
.seg button[aria-pressed=true] { background: var(--ink); color: var(--ground); }
.chip { border: 1px solid var(--rule); }
.chip[aria-pressed=true] { border-color: var(--ink); color: var(--ink); }
button:focus-visible, input:focus-visible { outline: 2px solid var(--draft); outline-offset: 2px; }
.presets { display: flex; flex-wrap: wrap; gap: 6px; }

section { margin-top: 56px; }
section > h2 { margin: 0 0 18px; font: inherit; display: flex; flex-wrap: wrap; gap: 6px 16px; align-items: baseline; }
section > h2 .x { font-size: 22px; --wght: 400; --slnt: 0; --wdth: 100; --scan: 10; --fam: "%%MONO_NAME%%"; }
section > h2 span:last-child { color: var(--dim); font-size: 14px; }

.board { background: #000; padding: clamp(16px, 3vw, 32px); overflow-x: auto; }
.prices { border-collapse: collapse; font-family: "%%MONO_NAME%%", monospace; font-size: clamp(11px, 1.35vw, 19px);
  font-variation-settings: "wght" 400, "SCAN" 10; white-space: nowrap; width: 100%; }
.prices td { padding: .28em 0; }
.prices td:nth-child(2), .prices td:nth-child(3) { text-align: right; }
.prices td:nth-child(3) { padding-left: 2.5em; }
.race { font-family: "%%MONO_NAME%%", monospace; font-variation-settings: "wght" 400, "slnt" -16, "SCAN" 12;
  font-size: clamp(24px, 4.4vw, 62px); line-height: 1.15; white-space: nowrap; margin: 0; }
.race.light { font-variation-settings: "wght" 220, "slnt" -16, "SCAN" 15; }
.pair { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; }

.legend { display: flex; flex-wrap: wrap; gap: 6px 22px; color: var(--dim); font-size: 13px; margin-bottom: 14px; }
.legend i { display: inline-block; width: 9px; height: 9px; margin-right: 7px; background: var(--ink); vertical-align: 0; }
.legend i.d { background: var(--draft); }
.grid { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(58px, 1fr));
  border-top: 1px solid var(--rule); border-left: 1px solid var(--rule); }
.cell { aspect-ratio: 1 / 1.15; display: grid; place-items: center; border-right: 1px solid var(--rule);
  border-bottom: 1px solid var(--rule); position: relative; font-size: 34px; }
.cell.draft span { color: var(--draft); }
.cell.draft::after { content: ""; position: absolute; top: 5px; right: 5px; width: 5px; height: 5px; background: var(--draft); }
.grid[hidden] { display: none !important; }
@page { size: A4; margin: 14mm 12mm; }
@media print {
  :root { color-scheme: light; --ground: #fff; --panel: #fff; --rule: #c8c8c2; --ink: #000; --dim: #55554e;
    --faint: #8a8a82; --draft: #9a6400; --size: 72px; }
  body { padding: 0; }
  .controls, .row, #tester:focus-visible { display: none; }
  .board { background: #fff; border: 1px solid var(--rule); }
  section { margin-top: 32px; break-inside: avoid-page; }
  .cell { font-size: 26px; }
}

.water div { white-space: nowrap; overflow: hidden; text-overflow: clip; line-height: 1.25; }
.water small { display: inline-block; width: 44px; color: var(--faint); font: 12px var(--ui); vertical-align: middle; }
footer { margin-top: 56px; padding-top: 16px; border-top: 1px solid var(--rule); color: var(--faint); font-size: 13px;
  display: flex; flex-wrap: wrap; gap: 6px 28px; }
@media (prefers-reduced-motion: no-preference) { .x { transition: font-variation-settings .12s linear; } }
</style>

<header>
  <h1><span class="x">%%NAME_UC%% %%VERSION%%</span></h1>
  <p>A scanline display typeface from Excellent. Type in the line below, or drag the axes. Every glyph is a stack of six scanline rows.</p>
</header>

<div id="tester" class="x" contenteditable="true" spellcheck="false" aria-label="Type to test the font">SIX ROWS, ONE GAP</div>

<div class="controls" role="group" aria-label="Font axes">
  <label class="ctl" for="wght"><span class="label">Weight</span><output id="o-wght">400</output>
    <input id="wght" type="range" min="100" max="800" step="1" value="400"><small>Stem thickness. Bars always fill their row.</small></label>
  <label class="ctl" for="wdth"><span class="label">Width</span><output id="o-wdth">100</output>
    <input id="wdth" type="range" min="75" max="150" step="0.5" value="100"><small>Letter body and spacing.</small></label>
  <label class="ctl" for="slnt"><span class="label">Slant</span><output id="o-slnt">0°</output>
    <input id="slnt" type="range" min="-16" max="0" step="0.5" value="0"><small>Stair-step italic: each row shifts, 16° max.</small></label>
  <label class="ctl" for="scan"><span class="label">Scanline</span><output id="o-scan">10%</output>
    <input id="scan" type="range" min="0" max="30" step="0.5" value="10"><small>Gap between rows. 0 = solid strokes.</small></label>
  <label class="ctl" for="size"><span class="label">Size</span><output id="o-size">120</output>
    <input id="size" type="range" min="16" max="260" step="1" value="120"><small>Pixels.</small></label>
</div>
<div class="row">
  <div class="seg" role="group" aria-label="Family">
    <button id="f-mono" aria-pressed="true">Mono</button><button id="f-prop" aria-pressed="false">Proportional</button>
  </div>
  <button class="chip" id="ss01" aria-pressed="false">Plain zero (ss01)</button>
  <button class="chip" id="tnum" aria-pressed="false">Tabular 1 (tnum)</button>
  <div class="presets" aria-label="Presets">
    <button class="chip" data-p="400,100,0,10">Regular</button>
    <button class="chip" data-p="400,100,-16,10">Italic</button>
    <button class="chip" data-p="700,100,0,10">Bold</button>
    <button class="chip" data-p="100,100,0,10">Thin</button>
    <button class="chip" data-p="800,75,-16,6">Condensed Black Italic</button>
    <button class="chip" data-p="300,150,0,24">Expanded Wide Scan</button>
  </div>
</div>

<section>
  <h2><span class="x">THE REFERENCE LETTERING, REBUILT</span><span>Live text set in the font, not images</span></h2>
  <div class="pair">
    <div class="board"><p class="race">AEROBIC<br>TRAIL RUNNING<br>4X200 RELAY</p></div>
    <div class="board"><p class="race light">2.5L I4<br>TURBO<br>FINISH LINE</p></div>
  </div>
  <div class="board" style="margin-top:16px"><table class="prices"><tbody>%%PRICES%%</tbody></table></div>
</section>

<section>
  <h2><span class="x">CHARACTER SET</span><span>%%NGLYPH%% glyphs · %%NCP%% codepoints · lowercase types as capitals</span></h2>
  <div class="legend"><span><i></i>Traced from the reference lettering</span><span><i class="d"></i>Drawn to match (src=draft)</span></div>
  <ul class="grid x" id="g-mono">%%CELLS_MONO%%</ul>
  <ul class="grid x" id="g-prop" hidden>%%CELLS_PROP%%</ul>
</section>

<section class="water">
  <h2><span class="x">WATERFALL</span><span>Follows the axes above</span></h2>
  <div id="water"></div>
</section>

<footer>
  <span>%%MONO_NAME%% + %%PROP_NAME%% · variable: wght 100–800, wdth 75–150, slnt 0 to −16, SCAN 0–30</span>
  <span>Proportional kerning: %%NKERN%% pairs</span>
  <span>Version %%VERSION%% · SIL Open Font License 1.1 · <a href="%%URL%%" style="color:inherit">%%URL_SHORT%%</a></span>
</footer>

<script>
const root = document.documentElement, $ = s => document.querySelector(s);
const fmt = { wght: v => v, wdth: v => v, slnt: v => v + "°", scan: v => v + "%", size: v => v };
function set(k, v) {
  $("#" + k).value = v; $("#o-" + k).textContent = fmt[k](v);
  root.style.setProperty("--" + k, k === "size" ? v + "px" : v);
}
["wght", "wdth", "slnt", "scan", "size"].forEach(k => $("#" + k).addEventListener("input", e => set(k, e.target.value)));
document.querySelectorAll("[data-p]").forEach(b => b.addEventListener("click", () => {
  const [w, d, s, c] = b.dataset.p.split(","); set("wght", w); set("wdth", d); set("slnt", s); set("scan", c);
}));
function family(prop) {
  root.style.setProperty("--fam", prop ? '"%%PROP_NAME%%"' : '"%%MONO_NAME%%"');
  $("#f-mono").setAttribute("aria-pressed", !prop); $("#f-prop").setAttribute("aria-pressed", prop);
  $("#g-mono").hidden = prop; $("#g-prop").hidden = !prop;
}
$("#f-mono").addEventListener("click", () => family(false));
$("#f-prop").addEventListener("click", () => family(true));
const feats = { ss01: false, tnum: false };
function features() {
  const v = Object.entries(feats).filter(([, on]) => on).map(([k]) => `"${k}" 1`).join(", ") || "normal";
  document.querySelectorAll(".x").forEach(el => el.style.fontFeatureSettings = v);
}
["ss01", "tnum"].forEach(k => $("#" + k).addEventListener("click", e => {
  feats[k] = !feats[k]; e.currentTarget.setAttribute("aria-pressed", feats[k]); features();
}));
const water = $("#water");
[12, 16, 24, 36, 54, 80].forEach(px => {
  const d = document.createElement("div");
  d.innerHTML = `<small>${px}</small><span class="x" style="font-size:${px}px">GLAZES, MUTE CHROME FIXTURES AND VELVET DRAPES. 0123456789</span>`;
  water.appendChild(d);
});
</script>
"""

if __name__ == "__main__":
    main()
