#!/usr/bin/env python3
"""List the disc's textures that no installed texture pack replaces.

    python3 tools/audit/scan.py DISC PACK_DIR [PACK_DIR...] [--csv missing.csv] [--png DIR]

DISC is the North American disc image or its extracted files/ folder. Every
texture the game loads from a file is read: .bti images, the textures inside
J3D models (.bmd/.bdl/.bmt) and particles (.jpa), and font sheets. Each gets the
name the PC port and Dolphin look up, which is matched against the packs in the
same way (with and without _m, a palette hash or "$"). Textures the game makes
or changes while running (EFB copies, the goop maps) cannot be listed here.
Build tools/audit/fast.so first (README) or it takes several minutes.
"""
import argparse
import csv
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gcdisc  # noqa: E402


def pack_names(dirs):
    names = set()
    for root in dirs:
        for _, _, files in os.walk(root):
            for f in files:
                stem, ext = os.path.splitext(f)
                if ext.lower() in (".dds", ".png") and stem.startswith("tex1_"):
                    stem = re.sub(r"_mip\d+$", "", stem[:-4] if stem.endswith("_arb") else stem)
                    names.add(stem)
    return names


class Scan:
    def __init__(self, names):
        self.names, self.seen = names, {}

    def texture(self, buf, off, where, kind):
        t = gcdisc.bti_texture(buf, off)
        if not t:
            return
        fmt, w, h, data, pal, tlut, mip = t
        plain = gcdisc.texture_name(fmt, w, h, data)
        r = self.seen.get(plain)
        if r is None:
            full = gcdisc.texture_name(fmt, w, h, data, pal, mip)
            cands = set()
            for m in (False, True):
                cands.add(gcdisc.texture_name(fmt, w, h, data, b"", m))
                if pal:
                    n = gcdisc.texture_name(fmt, w, h, data, pal, m)
                    cands.update((n, n.rsplit("_", 2)[0] + "_$_%d" % fmt))
            r = self.seen[plain] = dict(name=full, w=w, h=h, fmt=fmt, kind=kind, uses=0, where=where,
                                        found=bool(cands & self.names), tex=(data, pal, tlut))
        r["uses"] += 1

    def glyphs(self, d, where):
        pos = 0x20
        while pos + 8 <= len(d):
            ln = struct.unpack(">I", d[pos + 4:pos + 8])[0]
            if ln < 8:
                break
            if d[pos:pos + 4] == b"GLY1":
                b = d[pos:pos + ln]
                size = struct.unpack(">I", b[0x10:0x14])[0]
                fmt = struct.unpack(">H", b[0x14:0x16])[0]
                w, h = struct.unpack(">HH", b[0x1A:0x1E])
                i = 0x20
                while fmt in gcdisc.TILE and i + size <= len(b):
                    # a font sheet as a texture: a BTI header in front of its data
                    hdr = struct.pack(">BBHH", fmt, 0, w, h) + bytes(22) + struct.pack(">I", 0x20)
                    self.texture(hdr + b[i:i + gcdisc.level_bytes(fmt, w, h)], 0, where, "font")
                    i += size
            pos += ln

    def resource(self, d, where):
        d = gcdisc.yaz0(d)
        if d[:4] == b"RARC":
            for path, data in gcdisc.rarc(d):
                self.resource(data, where + ":" + path)
        elif d[:4] == b"J3D2" or d[:8] == b"JEFFjpa1":
            particle = d[:8] == b"JEFFjpa1"
            pos = 0x20
            for _ in range(struct.unpack(">I", d[0xC:0x10])[0]):
                if pos + 8 > len(d):
                    break
                ln = struct.unpack(">I", d[pos + 4:pos + 8])[0]
                if ln < 8:
                    break
                if d[pos:pos + 4] == b"TEX1":
                    b = d[pos:pos + ln]
                    if particle:
                        self.texture(b, 0x20, where, "particle")
                    else:
                        count, hdr = struct.unpack(">H", b[8:10])[0], struct.unpack(">I", b[0xC:0x10])[0]
                        for j in range(count):
                            self.texture(b, hdr + 0x20 * j, where, "model")
                pos += ln
        elif d[:8] == b"FONTbfn1":
            self.glyphs(d, where)
        elif where.lower().endswith(".bti") and len(d) > 0x20:
            self.texture(d, 0, where, "image")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("disc")
    ap.add_argument("packs", nargs="+")
    ap.add_argument("--csv", help="write the missing textures here")
    ap.add_argument("--png", help="decode the missing textures into this folder")
    args = ap.parse_args()
    disc = gcdisc.Disc(args.disc)
    scan = Scan(pack_names(args.packs))
    for path in sorted(disc.files):
        if path.endswith((".szs", ".arc", ".bti", ".bmd", ".bdl", ".jpa", ".bfn")):
            scan.resource(disc.read(path), path)
    missing = sorted((r for r in scan.seen.values() if not r["found"]), key=lambda r: (r["where"], r["name"]))
    print("%d textures on the disc, %d in the packs, %d missing" % (len(scan.seen), len(scan.seen) - len(missing), len(missing)))
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["name", "width", "height", "gx_format", "kind", "uses", "first_seen_in"])
            for r in missing:
                w.writerow([r["name"], r["w"], r["h"], r["fmt"], r["kind"], r["uses"], r["where"]])
    if args.png:
        from decode import decode
        os.makedirs(args.png, exist_ok=True)
        for r in missing:
            data, pal, tlut = r["tex"]
            decode(data, r["fmt"], r["w"], r["h"], pal, tlut).save(os.path.join(args.png, r["name"] + ".png"))


if __name__ == "__main__":
    main()
