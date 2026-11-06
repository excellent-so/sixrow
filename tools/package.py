"""Package a Sixrow release from build/: the download zip, the registry zips, checksums,
webfonts, and (with --repo) the clean tree for the public repository.

    .venv/bin/python tools/build.py && .venv/bin/python tools/proof.py \
      && .venv/bin/python tools/specimen.py && .venv/bin/python tools/images.py
    .venv/bin/python tools/package.py                      # → release/
    .venv/bin/python tools/package.py --repo ~/Sites/sixrow  # also the public repo tree (git init, one commit)

Outputs (version from sources/config.toml):
  release/Sixrow-1.000.zip                 the public download (fonts, licence, FONTLOG, specimen PDF)
  release/registry/Sixrow-1.000-ttf.zip     one family per zip: TTFs, OFL.txt and a preview image
  release/registry/SixrowMono-1.000-ttf.zip
  release/registry/Sixrow-fontlibrary.zip   both families, OFL.txt, FONTLOG.txt and a sample image
  release/CHECKSUMS.txt                     shasum -a 256 of each zip
  release/webfonts/                         the variable WOFF2 files, for the download page
  release/Sixrow-specimen.pdf               specimen/index.html printed by headless Chrome

Zips are deterministic (sorted entries, fixed dates), and build.py's output is byte-identical
from run to run, so the same sources give the same checksums.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build import CFG, OUT, family_names, vf_path  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REL = ROOT / "release"
FAM = CFG["family"]
VER = FAM["version"]
NAME = FAM["name"]
DATE = tuple(int(x) for x in FAM["release_date"].split("-")) + (0, 0, 0)
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

README_TXT = f"""{NAME} {VER} and {NAME} Mono {VER}: a scanline display typeface by {FAM['designer']} for {FAM['manufacturer']}.
Free for personal and commercial use under the SIL Open Font License 1.1 (OFL.txt).
variable/ has the variable fonts, static/ has 16 styles per family, webfonts/ has the WOFF2 files.
{NAME}-specimen.pdf shows the axes and the character set; FONTLOG.txt says how the fonts were made.
{FAM['vendor_url']}
"""

# What the public repo gets (relative to ROOT), and what it leaves out: brand/ (Excellent's
# company work), MEDIA-MANIFEST.tsv, docs other than the design spec, release/, .venv/.
REPO_FILES = ["OFL.txt", "FONTLOG.txt", "AUTHORS.txt", "CONTRIBUTORS.txt", "README.md", "requirements.txt",
              "docs/DESIGN-SPEC.md", "specimen/index.html"]
REPO_DIRS = ["sources", "proof", "reference/samples"]
REPO_TOOLS = ["build.py", "glyphs.py", "star.py", "proof.py", "specimen.py", "images.py", "package.py",
              "extract.py", "shot.sh"]
REPO_GITIGNORE = ".venv/\nbuild/\nrelease/\n__pycache__/\n.DS_Store\n"


def statics(mono: bool, ext: str = "ttf") -> list[Path]:
    files = sorted((OUT / "static" / family_names(mono)[1]).glob(f"*.{ext}"))
    assert len(files) == 16, f"expected 16 static {ext} files for {family_names(mono)[0]}, found {len(files)}"
    return files


def write_zip(path: Path, entries: dict[str, Path | bytes]) -> Path:
    """Deterministic zip: sorted names, the release date on every entry, 0644."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in sorted(entries):
            src = entries[name]
            data = src if isinstance(src, bytes) else src.read_bytes()
            info = zipfile.ZipInfo(name, date_time=DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
    return path


def specimen_pdf() -> Path | None:
    """Print specimen/index.html with headless Chrome. Chrome stamps the time into the PDF;
    the stamps are replaced with the release date (same length, so the xref stays valid)."""
    pdf = REL / f"{NAME}-specimen.pdf"
    if not CHROME.exists():
        print("! Chrome not found: the specimen PDF is left out")
        return None
    subprocess.run([str(CHROME), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    "--virtual-time-budget=8000", f"--print-to-pdf={pdf}",
                    (ROOT / "specimen" / "index.html").as_uri()], check=True, capture_output=True)
    stamp = "D:{:04d}{:02d}{:02d}000000".format(*DATE[:3]).encode()
    data = re.sub(rb"D:\d{14}", stamp, pdf.read_bytes())
    pdf.write_bytes(data)
    return pdf


def package() -> list[Path]:
    for mono in (True, False):
        assert vf_path(mono).exists(), "run tools/build.py first"
    REL.mkdir(exist_ok=True)
    ofl, fontlog = ROOT / "OFL.txt", ROOT / "FONTLOG.txt"
    img = REL / "images"
    pdf = specimen_pdf()

    # the public download
    top = f"{NAME}-{VER}/"
    main: dict[str, Path | bytes] = {top + "OFL.txt": ofl, top + "FONTLOG.txt": fontlog,
                                     top + "README.txt": README_TXT.encode()}
    for mono in (True, False):
        ps = family_names(mono)[1]
        main[top + f"variable/{vf_path(mono).name}"] = vf_path(mono)
        main[top + f"webfonts/{vf_path(mono, 'woff2').name}"] = vf_path(mono, "woff2")
        for f in statics(mono):
            main[top + f"static/{ps}/{f.name}"] = f
        for f in statics(mono, "woff2"):
            main[top + f"webfonts/{f.name}"] = f
    if pdf:
        main[top + pdf.name] = pdf
    zips = [write_zip(REL / f"{NAME}-{VER}.zip", main)]

    # registries that want one family per zip, and nothing but fonts, licence and images
    for mono, preview in ((False, "preview-1600x800.png"), (True, "preview-mono-1600x800.png")):
        ps = family_names(mono)[1]
        entries: dict[str, Path | bytes] = {"OFL.txt": ofl, vf_path(mono).name: vf_path(mono),
                                            f"{ps}-preview.png": img / preview}
        entries.update({f.name: f for f in statics(mono)})
        zips.append(write_zip(REL / "registry" / f"{ps}-{VER}-ttf.zip", entries))

    # Font Library: both families, FONTLOG and a sample image
    lib: dict[str, Path | bytes] = {"OFL.txt": ofl, "FONTLOG.txt": fontlog, f"{NAME}-sample.png": img / "preview-1600x800.png"}
    for mono in (True, False):
        lib[vf_path(mono).name] = vf_path(mono)
        lib.update({f.name: f for f in statics(mono)})
    zips.append(write_zip(REL / "registry" / f"{NAME}-fontlibrary.zip", lib))

    (REL / "CHECKSUMS.txt").write_text("".join(
        f"{hashlib.sha256(z.read_bytes()).hexdigest()}  {z.relative_to(REL)}\n" for z in zips))

    web = REL / "webfonts"
    web.mkdir(exist_ok=True)
    for mono in (True, False):
        shutil.copyfile(vf_path(mono, "woff2"), web / vf_path(mono, "woff2").name)

    for z in zips:
        with zipfile.ZipFile(z) as zf:
            print(f"{z.relative_to(ROOT)}: {len(zf.namelist())} files, {z.stat().st_size // 1024} KB")
    return zips


def repo(dest: Path, force: bool):
    """Assemble the public repository tree at dest and make its first commit on main."""
    dest = dest.expanduser().resolve()
    if dest.exists() and any(dest.iterdir()):
        if not force:
            sys.exit(f"{dest} exists and is not empty (use --force to rebuild it)")
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for f in REPO_FILES:
        (dest / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / f, dest / f)
    for d in REPO_DIRS:
        shutil.copytree(ROOT / d, dest / d, ignore=shutil.ignore_patterns(".DS_Store"))
    (dest / "tools").mkdir()
    for t in REPO_TOOLS:
        shutil.copy2(ROOT / "tools" / t, dest / "tools" / t)
    for mono in (True, False):
        ps = family_names(mono)[1]
        (dest / "fonts" / "variable").mkdir(parents=True, exist_ok=True)
        for ext in ("ttf", "woff2"):
            shutil.copyfile(vf_path(mono, ext), dest / "fonts" / "variable" / vf_path(mono, ext).name)
            (dest / "fonts" / "static" / ps).mkdir(parents=True, exist_ok=True)
            for f in statics(mono, ext):
                shutil.copyfile(f, dest / "fonts" / "static" / ps / f.name)
    (dest / ".gitignore").write_text(REPO_GITIGNORE)
    leak = re.compile(rb"/Users/|/private/tmp|brand/(social|growth|home)|excellent-site")
    leaks = [str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file() and p.name != "package.py"
             and p.suffix in (".py", ".md", ".txt", ".toml", ".html", ".sh") and leak.search(p.read_bytes())]
    if leaks:
        print("! check these files for local paths or company references:", leaks)
    # The public commit is authored as the first entry in AUTHORS.txt, not the machine's git identity.
    who = next(l for l in (ROOT / "AUTHORS.txt").read_text().splitlines() if l.strip() and not l.startswith("#"))
    name, email = re.fullmatch(r"(.+?)\s*<(.+)>", who.strip()).groups()
    env = {"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_COMMITTER_NAME": name,
           "GIT_COMMITTER_EMAIL": email, "GIT_AUTHOR_DATE": f"{FAM['release_date']}T12:00:00Z",
           "GIT_COMMITTER_DATE": f"{FAM['release_date']}T12:00:00Z"}
    git = ["git", "-C", str(dest)]
    subprocess.run(git + ["init", "-q", "-b", "main"], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    msg = (f"{NAME} {VER}\n\nFirst public release of {NAME} and {NAME} Mono, a scanline display typeface by "
           f"{FAM['designer']} for {FAM['manufacturer']}. SIL Open Font License 1.1.\n\n"
           "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>\n")
    import os
    subprocess.run(git + ["commit", "-q", "-m", msg], check=True, env={**os.environ, **env})
    n = subprocess.run(git + ["ls-files"], capture_output=True, text=True, check=True).stdout.count("\n")
    print(f"public repo → {dest} ({n} files, one commit on main)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, help="also assemble the public repo tree here")
    ap.add_argument("--force", action="store_true", help="replace an existing --repo tree")
    a = ap.parse_args()
    package()
    if a.repo:
        repo(a.repo, a.force)
