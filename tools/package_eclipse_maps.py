#!/usr/bin/env python3
"""Package the radar's maps of Super Mario Eclipse's stages for the PC port.

usage: tools/package_eclipse_maps.py MAPS OUT.zip [--previous OLD.zip]

MAPS is the PC port's tools/radar/gen_maps.py output for the Eclipse disc
(GMSE04), made with --except assets/maps/maps.txt so it holds only the stages
the retail maps lack: maps.txt and a JPEG per map, at gen_maps.py's quality 95.
Each picture is encoded again at quality 90 with 4:2:0 chroma (about half the
size; the radar draws them scaled down) into eclipse/ in the zip, which the
port installs as mods/maps/eclipse. Entries get a fixed date, so the same maps
give the same zip. With --previous, the last release's zip: a map whose
maps.txt line is the same there is copied from it as it is, so an update (a
few stages added: MAPS is that release's files with gen_maps.py --only run
over them) encodes only the new pictures again. Needs Pillow.
"""
import io
import os
import sys
import zipfile

from PIL import Image


def manifest(text):
    """{picture: its maps.txt line}"""
    return {line.split()[1]: line for line in text.splitlines() if line.strip() and not line.startswith('#')}


def main():
    args = sys.argv[1:]
    previous = None
    if len(args) == 4 and args[2] == '--previous':
        previous = zipfile.ZipFile(args[3])
        args = args[:2]
    if len(args) != 2:
        sys.exit(__doc__.split('\n\n')[1])
    src, out = args
    if not os.path.isfile(os.path.join(src, 'maps.txt')):
        sys.exit('%s has no maps.txt' % src)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    lines = manifest(open(os.path.join(src, 'maps.txt'), encoding='utf-8').read())
    kept = {}
    if previous:
        old = manifest(previous.read('eclipse/maps.txt').decode('utf-8'))
        kept = {name for name, line in lines.items() if old.get(name) == line}
    count = copied = 0
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_STORED) as z:
        for name in sorted(os.listdir(src)):
            path = os.path.join(src, name)
            if name == 'maps.txt':
                data = open(path, 'rb').read()
            elif name.endswith('.jpg') and name in kept:
                data = previous.read('eclipse/' + name)
                count += 1
                copied += 1
            elif name.endswith('.jpg'):
                buf = io.BytesIO()
                Image.open(path).convert('RGB').save(buf, 'JPEG', quality=90, subsampling=2, optimize=True)
                data = buf.getvalue()
                count += 1
            else:
                continue
            info = zipfile.ZipInfo('eclipse/' + name, date_time=(2026, 10, 21, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED if name.endswith('.txt') else zipfile.ZIP_STORED
            z.writestr(info, data)
    print('%s: %d maps (%d as they were), %d bytes' % (out, count, copied, os.path.getsize(out)))


if __name__ == '__main__':
    main()
