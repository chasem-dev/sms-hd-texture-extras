#!/usr/bin/env python3
"""Rebuild this pack's textures from your own Super Mario Sunshine disc.

    python3 tools/make_textures.py DISC --realesrgan PATH/realesrgan-ncnn-vulkan

DISC is a North American disc image (ISO/GCM) or its extracted files/ folder.
Each texture in TEXTURES is read from the disc, upscaled 16x with Real-ESRGAN's
realesrgan-x4plus-anime model (4x, twice), scaled down to 8x with Lanczos (the
scale of the UHD pack's HUD), and written to textures/GMS/<folder>/ under its
Dolphin name. previews/ gets a before/after picture of each.

Needs Python 3 with Pillow, and realesrgan-ncnn-vulkan with its models folder
(https://github.com/xinntao/Real-ESRGAN/releases, v0.2.5.0).
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gcdisc  # noqa: E402
from decode import decode  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (archive on the disc, file in it, folder under textures/GMS, what it is)
TEXTURES = [
    ("data/game_6.szs", "/timg/monte_icon.bti", "gui/icons", "Pianta counter icon (Pianta Village, Piantas in Need)"),
    ("data/game_6.szs", "/timg/balloon_icon.bti", "gui/icons", "balloon counter icon (Pinna Park)"),
]
SCALE, PAD, MODEL = 8, 4, "realesrgan-x4plus-anime"


def upscale(exe, models, src, dst):
    r = subprocess.run([exe, "-i", src, "-o", dst, "-n", MODEL, "-s", "4", "-m", models],
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0 or not os.path.exists(dst):
        sys.exit("realesrgan-ncnn-vulkan failed on %s:\n%s" % (src, r.stderr))


def preview(orig, hd, path):
    font = ImageFont.load_default(size=22)
    w, h = hd.size
    cols = [("original", orig.resize((w, h), Image.BILINEAR)), ("this pack", hd)]
    sheet = Image.new("RGBA", (len(cols) * (w + 20) + 20, h + 70), (40, 44, 52, 255))
    d = ImageDraw.Draw(sheet)
    for i, (title, im) in enumerate(cols):
        x = 20 + i * (w + 20)
        sheet.alpha_composite(im, (x, 50))
        d.text((x, 14), title, fill=(255, 255, 255, 255), font=font)
    sheet.convert("RGB").save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("disc")
    ap.add_argument("--realesrgan", required=True, help="the realesrgan-ncnn-vulkan executable")
    ap.add_argument("--models", help="its models folder (default: next to the executable)")
    args = ap.parse_args()
    models = args.models or os.path.join(os.path.dirname(os.path.abspath(args.realesrgan)), "models")
    disc = gcdisc.Disc(args.disc)
    archives = {}
    with tempfile.TemporaryDirectory() as tmp:
        for arc, member, folder, what in TEXTURES:
            if arc not in archives:
                archives[arc] = dict(gcdisc.rarc(disc.read(arc)))
            fmt, w, h, data, pal, tlut, mip = gcdisc.bti_texture(archives[arc][member])
            name = gcdisc.texture_name(fmt, w, h, data, pal, mip)
            orig = decode(data, fmt, w, h, pal, tlut)
            padded = Image.new("RGBA", (w + 2 * PAD, h + 2 * PAD), (0, 0, 0, 0))
            padded.paste(orig, (PAD, PAD))
            a, b, c = (os.path.join(tmp, "%s_%d.png" % (name, i)) for i in range(3))
            padded.save(a)
            upscale(args.realesrgan, models, a, b)
            upscale(args.realesrgan, models, b, c)
            hd = Image.open(c).convert("RGBA").crop((PAD * 16, PAD * 16, PAD * 16 + w * 16, PAD * 16 + h * 16))
            hd = hd.resize((w * SCALE, h * SCALE), Image.LANCZOS)
            out = os.path.join(ROOT, "textures", "GMS", folder, name + ".png")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            hd.save(out, optimize=True)
            base = os.path.splitext(os.path.basename(member))[0]
            preview(orig, hd, os.path.join(ROOT, "previews", base + ".png"))
            print("%s  %s  %s" % (name, member, what))


if __name__ == "__main__":
    main()
