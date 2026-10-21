#!/usr/bin/env python3
"""Package the radar's maps of Super Mario Eclipse's stages for the PC port.

usage: tools/package_eclipse_maps.py MAPS OUT.zip

MAPS is the PC port's tools/radar/gen_maps.py output for the Eclipse disc
(GMSE04), made with --except assets/maps/maps.txt so it holds only the stages
the retail maps lack: maps.txt and a JPEG per map, at gen_maps.py's quality 95.
Each picture is encoded again at quality 90 with 4:2:0 chroma (about half the
size; the radar draws them scaled down) into eclipse/ in the zip, which the
port installs as mods/maps/eclipse. Entries get a fixed date, so the same maps
give the same zip. Needs Pillow.
"""
import io
import os
import sys
import zipfile

from PIL import Image


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__.split('\n\n')[1])
    src, out = sys.argv[1], sys.argv[2]
    if not os.path.isfile(os.path.join(src, 'maps.txt')):
        sys.exit('%s has no maps.txt' % src)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    count = 0
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_STORED) as z:
        for name in sorted(os.listdir(src)):
            path = os.path.join(src, name)
            if name == 'maps.txt':
                data = open(path, 'rb').read()
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
    print('%s: %d maps, %d bytes' % (out, count, os.path.getsize(out)))


if __name__ == '__main__':
    main()
