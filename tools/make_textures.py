#!/usr/bin/env python3
"""Rebuild this pack's textures from your own Super Mario Sunshine disc.

    python3 tools/get_realesrgan.py      (once: downloads Real-ESRGAN into tools/realesrgan/)
    python3 tools/make_textures.py DISC

DISC is a North American disc image (ISO/GCM) or its extracted files/ folder.
Every texture listed in TEXTURES.tsv is read from the disc and upscaled with
Real-ESRGAN's realesrgan-x4plus-anime model, at the UHD pack's scales:
  ui     menus and HUD: 8x (16x, scaled down with Lanczos), with a
         transparent border so the edges stay clean
  model  stage and character textures: 4x, with the texture wrapped around
         its edges so tiling textures stay seamless
(at most 2048 pixels a side). Each is written to textures/GMS/<kind>/<archive>/
under its Dolphin name, and previews/<archive>.png shows them before and after.
Textures with no transparency stay fully opaque.

Needs Python 3 with Pillow and a GPU with Vulkan. --realesrgan names another
realesrgan-ncnn-vulkan (https://github.com/xinntao/Real-ESRGAN/releases,
v0.2.5.0) than the one get_realesrgan.py installs.
"""
import argparse
import math
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageMath

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gcdisc  # noqa: E402
import get_realesrgan  # noqa: E402
from decode import decode  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = "realesrgan-x4plus-anime"
MAX_SIDE = 2048
FOLDER = {"ui": "gui", "model": "models"}


def read_manifest():
    rows = []
    with open(os.path.join(ROOT, "TEXTURES.tsv"), encoding="utf-8") as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                kind, archive, member, texture, note = (line.rstrip("\n").split("\t") + [""] * 5)[:5]
                rows.append(dict(kind=kind, archive=archive, member=member, texture=texture, note=note))
    return rows


def scale_for(kind, w, h):
    want = 8 if kind == "ui" else 4
    return max(1, min(want, 2 ** int(math.log2(MAX_SIDE / max(w, h)))))


def bleed(img):
    """The RGB of img, with its fully transparent pixels coloured like their
    nearest visible ones, so the upscaler draws no dark fringes into edges."""
    *rgb, a = img.split()
    filled = a.point(lambda v: 255 if v else 0)
    radius = 1
    while filled.getextrema() == (0, 255) and radius <= 1024:
        weight = filled.filter(ImageFilter.BoxBlur(radius))
        new = ImageChops.multiply(ImageChops.invert(filled), weight.point(lambda v: 255 if v else 0))
        for i, c in enumerate(rgb):
            total = ImageChops.multiply(c, filled).filter(ImageFilter.BoxBlur(radius))
            guess = ImageMath.eval("convert(min(t * 255 / max(w, 1), 255), 'L')", t=total, w=weight)
            rgb[i] = Image.composite(guess, c, new)
        filled = ImageChops.lighter(filled, new)
        radius *= 2
    return Image.merge("RGB", rgb)


def padded(img, kind):
    w, h = img.size
    if kind == "ui":
        pad = 4
        out = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
        out.paste(img, (pad, pad))
        return out, pad
    pad = min(16, w, h)
    tiled = Image.new("RGBA", (3 * w, 3 * h))
    for y in range(3):
        for x in range(3):
            tiled.paste(img, (x * w, y * h))
    return tiled.crop((w - pad, h - pad, 2 * w + pad, 2 * h + pad)), pad


def upscale_dir(exe, models, src, dst):
    os.makedirs(dst, exist_ok=True)
    r = subprocess.run([exe, "-i", src, "-o", dst, "-n", MODEL, "-s", "4", "-m", models, "-f", "png"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    missing = set(os.listdir(src)) - set(os.listdir(dst))
    if r.returncode != 0 or missing:
        sys.exit("realesrgan-ncnn-vulkan failed (%d files not written):\n%s" % (len(missing), r.stderr[-2000:]))


def preview(pairs, path):
    font = ImageFont.load_default(size=13)
    cell, cols = 220, 3
    rows = (len(pairs) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * (2 * cell + 30) + 10, rows * (cell + 34) + 10), (40, 44, 52, 255))
    d = ImageDraw.Draw(sheet)
    for i, (label, orig, hd) in enumerate(pairs):
        x0, y0 = 10 + (i % cols) * (2 * cell + 30), 10 + (i // cols) * (cell + 34)
        for j, im in enumerate((orig.resize(hd.size, Image.BILINEAR), hd)):
            im = im.copy()
            im.thumbnail((cell, cell), Image.LANCZOS)
            sheet.alpha_composite(im, (x0 + j * (cell + 6), y0))
        d.text((x0, y0 + cell + 4), label[:60], fill=(230, 230, 230, 255), font=font)
    sheet.convert("RGB").save(path, optimize=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("disc")
    ap.add_argument("--realesrgan", default=get_realesrgan.executable(),
                    help="the realesrgan-ncnn-vulkan executable (default: the one get_realesrgan.py installs)")
    ap.add_argument("--models", help="its models folder (default: next to the executable)")
    args = ap.parse_args()
    if not os.path.isfile(args.realesrgan):
        sys.exit("no %s: run python3 tools/get_realesrgan.py first" % args.realesrgan)
    models = args.models or os.path.join(os.path.dirname(os.path.abspath(args.realesrgan)), "models")
    disc = gcdisc.Disc(args.disc)

    jobs = {}  # texture name -> job, so a texture listed twice is made once
    for row in read_manifest():
        fmt, w, h, data, pal, tlut, mip = gcdisc.find_texture(disc, row["archive"], row["member"], row["texture"])
        name = gcdisc.texture_name(fmt, w, h, data, pal, mip)
        if name in jobs:
            continue
        orig = decode(data, fmt, w, h, pal, tlut)
        stem = os.path.splitext(os.path.basename(row["archive"]))[0]
        label = row["note"] or "%s %s" % (os.path.basename(row["member"]), row["texture"])
        jobs[name] = dict(row, name=name, orig=orig, scale=scale_for(row["kind"], w, h), stem=stem, label=label,
                          opaque=orig.getextrema()[3][0] == 255)

    with tempfile.TemporaryDirectory() as tmp:
        # pass 1 (4x) for everything, pass 2 (4x again) for 8x textures
        p0, p1, p2 = (os.path.join(tmp, n) for n in ("in", "x4", "x16"))
        os.makedirs(p0)
        # colour and transparency are upscaled separately: the colour with its
        # hidden pixels filled in, the transparency as a grey picture
        for j in jobs.values():
            img, j["pad"] = padded(j["orig"], j["kind"])
            bleed(img).save(os.path.join(p0, j["name"] + ".png"))
            if not j["opaque"]:
                a = img.getchannel("A")
                Image.merge("RGB", (a, a, a)).save(os.path.join(p0, j["name"] + ".alpha.png"))
        upscale_dir(args.realesrgan, models, p0, p1)
        second = [f for j in jobs.values() if j["scale"] > 4
                  for f in (j["name"] + ".png", j["name"] + ".alpha.png") if os.path.exists(os.path.join(p1, f))]
        if second:
            p1b = os.path.join(tmp, "x4-again")
            os.makedirs(p1b)
            for f in second:
                shutil.copy(os.path.join(p1, f), p1b)
            upscale_dir(args.realesrgan, models, p1b, p2)

        out_root = os.path.join(ROOT, "textures", "GMS")
        shutil.rmtree(out_root, ignore_errors=True)
        pairs = {}
        for j in jobs.values():
            f = 16 if j["scale"] > 4 else 4
            src = p2 if f == 16 else p1
            big = Image.open(os.path.join(src, j["name"] + ".png")).convert("RGBA")
            big.putalpha(255 if j["opaque"] else Image.open(os.path.join(src, j["name"] + ".alpha.png")).getchannel("R"))
            w, h = j["orig"].size
            p = j["pad"] * f
            hd = big.crop((p, p, p + w * f, p + h * f)).resize((w * j["scale"], h * j["scale"]), Image.LANCZOS)
            out = os.path.join(out_root, FOLDER[j["kind"]], j["stem"], j["name"] + ".png")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            hd.save(out, optimize=True)
            pairs.setdefault(j["stem"], []).append((j["label"], j["orig"], hd))
            print("%-44s %dx  %s:%s %s" % (j["name"], j["scale"], j["archive"], j["member"], j["texture"]))

    prev = os.path.join(ROOT, "previews")
    for f in os.listdir(prev):
        if f.endswith(".png") and not f.endswith("_ingame.png"):
            os.remove(os.path.join(prev, f))
    for stem, items in pairs.items():
        preview(items, os.path.join(prev, stem + ".png"))
    print("%d textures" % len(jobs))


if __name__ == "__main__":
    main()
