#!/usr/bin/env python3
"""Download Real-ESRGAN (ncnn Vulkan) into tools/realesrgan/ for make_textures.py.

    python3 tools/get_realesrgan.py

Gets the official v0.2.5.0 release for this system (Linux, Windows or macOS)
from https://github.com/xinntao/Real-ESRGAN, checks it against the known
SHA-256, and unpacks the executable and its models. It runs on any GPU with
Vulkan; make_textures.py finds it there by itself.
"""
import hashlib
import io
import os
import platform
import shutil
import stat
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(HERE, "realesrgan")
BASE = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/"
RELEASES = {  # system: (file, size, sha256)
    "Linux": ("realesrgan-ncnn-vulkan-20220424-ubuntu.zip", 46931474,
              "e5aa6eb131234b87c0c51f82b89390f5e3e642b7b70f2b9bbe95b6a285a40c96"),
    "Windows": ("realesrgan-ncnn-vulkan-20220424-windows.zip", 45474481,
                "abc02804e17982a3be33675e4d471e91ea374e65b70167abc09e31acb412802d"),
    "Darwin": ("realesrgan-ncnn-vulkan-20220424-macos.zip", 51817124,
               "e0ad05580abfeb25f8d8fb55aaf7bedf552c375b5b4d9bd3c8d59764d2cc333a"),
}


def executable():
    """The installed executable's path (whether or not it exists yet)."""
    return os.path.join(DEST, "realesrgan-ncnn-vulkan" + (".exe" if platform.system() == "Windows" else ""))


def main():
    system = platform.system()
    if system not in RELEASES:
        sys.exit("no Real-ESRGAN release for %s" % system)
    name, size, sha = RELEASES[system]
    print("Downloading %s%s" % (BASE, name), flush=True)
    req = urllib.request.Request(BASE + name, headers={"User-Agent": "sms-hd-texture-extras"})
    with urllib.request.urlopen(req) as r:
        data = r.read()
    got = hashlib.sha256(data).hexdigest()
    if len(data) != size or got != sha:
        sys.exit("the download is not the expected release (%d bytes, SHA-256 %s)" % (len(data), got))
    shutil.rmtree(DEST, ignore_errors=True)
    os.makedirs(DEST)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for member in z.namelist():
            base = os.path.basename(member)
            keep = member.startswith("models/") or base.startswith("realesrgan-ncnn-vulkan") or base.endswith(".dll")
            if not base or not keep or ".." in member.split("/"):
                continue
            out = os.path.join(DEST, *member.split("/"))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "wb") as f:
                f.write(z.read(member))
    exe = executable()
    os.chmod(exe, os.stat(exe).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print("Installed %s" % os.path.relpath(exe, os.path.dirname(HERE)))


if __name__ == "__main__":
    main()
