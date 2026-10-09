#!/usr/bin/env python3
"""Write the original textures from your disc as PNGs, under their Dolphin names.

    python3 tools/extract_textures.py DISC              the textures in TEXTURES.tsv
    python3 tools/extract_textures.py DISC --all        every texture the game loads from its files

DISC is a North American disc image (ISO/GCM) or its extracted files/ folder.
Files go to originals/ (or --out): originals/<kind>/<archive>/ for the
manifest, the same layout as textures/GMS/ so a file and its HD version share
a name, and originals/all/<archive>/ with --all. Edit or upscale one, keep its
name, and it replaces that texture in the PC port or Dolphin.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "audit"))
import gcdisc  # noqa: E402
from decode import decode  # noqa: E402
from make_textures import FOLDER, ROOT, read_manifest  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("disc")
    ap.add_argument("--all", action="store_true", help="every texture, not only the manifest's")
    ap.add_argument("--out", default=os.path.join(ROOT, "originals"))
    args = ap.parse_args()
    disc = gcdisc.Disc(args.disc)
    count = 0
    if args.all:
        import scan
        s = scan.Scan(set())
        for path in sorted(disc.files):
            if path.endswith((".szs", ".arc", ".bti", ".bmd", ".bdl", ".jpa", ".bfn")):
                s.resource(disc.read(path), path)
        for r in s.seen.values():
            data, pal, tlut = r["tex"]
            stem = os.path.splitext(os.path.basename(r["where"].split(":")[0]))[0]
            out = os.path.join(args.out, "all", stem, r["name"] + ".png")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            decode(data, r["fmt"], r["w"], r["h"], pal, tlut).save(out)
            count += 1
    else:
        for row in read_manifest():
            fmt, w, h, data, pal, tlut, mip = gcdisc.find_texture(disc, row["archive"], row["member"], row["texture"])
            stem = os.path.splitext(os.path.basename(row["archive"]))[0]
            out = os.path.join(args.out, FOLDER[row["kind"]], stem, gcdisc.texture_name(fmt, w, h, data, pal, mip) + ".png")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            decode(data, fmt, w, h, pal, tlut).save(out)
            count += 1
    print("%d textures in %s" % (count, os.path.relpath(args.out)))


if __name__ == "__main__":
    main()
