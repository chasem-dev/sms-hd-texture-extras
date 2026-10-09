#!/usr/bin/env python3
"""Pack textures/GMS into dist/sms-hd-texture-extras-<VERSION>.zip for a release.

The zip holds GMS/<folders>/tex1_*.png, so it unpacks straight into Dolphin's
Load/Textures/ folder. Entries are sorted with fixed dates, so the same
textures always give the same file (and checksum).
"""
import hashlib
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    version = open(os.path.join(ROOT, "VERSION")).read().strip()
    src = os.path.join(ROOT, "textures")
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    out = os.path.join(ROOT, "dist", "sms-hd-texture-extras-%s.zip" % version)
    files = sorted(os.path.relpath(os.path.join(dp, f), src).replace(os.sep, "/")
                   for dp, _, names in os.walk(src) for f in names if f.startswith("tex1_"))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
        for rel in files:
            info = zipfile.ZipInfo(rel, (2020, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            with open(os.path.join(src, rel), "rb") as f:
                z.writestr(info, f.read())
    data = open(out, "rb").read()
    print("%s: %d textures, %d bytes, MD5 %s" % (os.path.relpath(out, ROOT), len(files), len(data),
                                                hashlib.md5(data).hexdigest()))


if __name__ == "__main__":
    main()
