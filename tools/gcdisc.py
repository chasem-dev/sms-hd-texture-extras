"""Reading Super Mario Sunshine's files: a GameCube disc image (ISO/GCM) or an
extracted files/ folder, Yaz0-compressed RARC archives, and texture names in
Dolphin's custom texture format."""
import os
import struct

try:  # optional speed-up: tools/audit/fast.c (see tools/audit/README.md)
    import ctypes
    _fast = ctypes.CDLL(os.path.join(os.path.dirname(os.path.abspath(__file__)), "audit", "fast.so"))
    _fast.yaz0.restype = ctypes.c_size_t
    _fast.yaz0.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_size_t]
    _fast.xxh64.restype = ctypes.c_uint64
    _fast.xxh64.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_uint64]
except OSError:
    _fast = None


class Disc:
    """Files of a disc image or an extracted files/ folder, by path ("data/game_6.szs")."""

    def __init__(self, path):
        self.dir = path if os.path.isdir(path) else None
        self.files = {}
        if self.dir:
            for dp, _, names in os.walk(path):
                for n in names:
                    p = os.path.join(dp, n)
                    self.files[os.path.relpath(p, path).replace(os.sep, "/")] = p
            return
        self.f = open(path, "rb")
        self.f.seek(0x424)
        fst, fst_size = struct.unpack(">II", self.f.read(8))
        self.f.seek(fst)
        t = self.f.read(fst_size)
        count = struct.unpack(">I", t[8:12])[0]
        names = 12 * count

        def name(i):
            o = names + (struct.unpack(">I", t[12 * i:12 * i + 4])[0] & 0xFFFFFF)
            return t[o:t.index(b"\0", o)].decode("latin1")

        def walk(first, end, prefix):
            i = first
            while i < end:
                flags_name, a, b = struct.unpack(">III", t[12 * i:12 * i + 12])
                if flags_name >> 24:
                    walk(i + 1, b, prefix + name(i) + "/")
                    i = b
                else:
                    self.files[prefix + name(i)] = (a, b)
                    i += 1

        walk(1, count, "")

    def read(self, path):
        e = self.files[path]
        if self.dir:
            with open(e, "rb") as f:
                return f.read()
        self.f.seek(e[0])
        return self.f.read(e[1])


def yaz0(d):
    if d[:4] != b"Yaz0":
        return d
    size = struct.unpack(">I", d[4:8])[0]
    if _fast:
        o = ctypes.create_string_buffer(size)
        _fast.yaz0(d, len(d), o, size)
        return o.raw
    out = bytearray()
    i = 16
    while len(out) < size:
        code = d[i]
        i += 1
        for b in range(8):
            if len(out) >= size:
                break
            if code & (0x80 >> b):
                out.append(d[i])
                i += 1
            else:
                b1, b2 = d[i], d[i + 1]
                i += 2
                dist = ((b1 & 15) << 8 | b2) + 1
                n = b1 >> 4
                if n == 0:
                    n = d[i] + 0x12
                    i += 1
                else:
                    n += 2
                for _ in range(n):
                    out.append(out[-dist])
    return bytes(out)


def rarc(d):
    """(path, bytes) of every file in a RARC archive (Yaz0 data is decompressed first)."""
    d = yaz0(d)
    assert d[:4] == b"RARC", "not a RARC archive"
    nn, no, nf, fo, _, so = struct.unpack(">IIIIII", d[0x20:0x38])
    data = struct.unpack(">I", d[0xC:0x10])[0] + 0x20
    no, fo, so = no + 0x20, fo + 0x20, so + 0x20
    out = []

    def s(o):
        return d[so + o:d.index(b"\0", so + o)].decode("latin1")

    def walk(n, path):
        _, _, _, cnt, first = struct.unpack(">IIHHI", d[no + n * 16:no + n * 16 + 16])
        for k in range(cnt):
            e = fo + (first + k) * 20
            _, _, ty, nmo, off, sz = struct.unpack(">HHHHII", d[e:e + 16])
            nm = s(nmo)
            if nm in (".", ".."):
                continue
            if (ty >> 8) & 2:
                walk(off, path + nm + "/")
            else:
                out.append((path + nm, d[data + off:data + off + sz]))

    walk(0, "/")
    return out


_M = (1 << 64) - 1
_P1, _P2, _P3, _P4, _P5 = (11400714785074694791, 14029467366897019727, 1609587929392839161,
                           9650029242287828579, 2870177450012600261)


def xxh64(b, seed=0):
    if _fast:
        return _fast.xxh64(b, len(b), seed)
    rotl = lambda x, r: ((x << r) | (x >> (64 - r))) & _M
    rnd = lambda a, i: (rotl((a + i * _P2) & _M, 31) * _P1) & _M
    n, p = len(b), 0
    if n >= 32:
        v = [(seed + _P1 + _P2) & _M, (seed + _P2) & _M, seed, (seed - _P1) & _M]
        while p + 32 <= n:
            for k in range(4):
                v[k] = rnd(v[k], struct.unpack_from("<Q", b, p + 8 * k)[0])
            p += 32
        h = (rotl(v[0], 1) + rotl(v[1], 7) + rotl(v[2], 12) + rotl(v[3], 18)) & _M
        for k in range(4):
            h = ((h ^ rnd(0, v[k])) * _P1 + _P4) & _M
    else:
        h = (seed + _P5) & _M
    h = (h + n) & _M
    while p + 8 <= n:
        h ^= rnd(0, struct.unpack_from("<Q", b, p)[0])
        h = (rotl(h, 27) * _P1 + _P4) & _M
        p += 8
    if p + 4 <= n:
        h ^= (struct.unpack_from("<I", b, p)[0] * _P1) & _M
        h = (rotl(h, 23) * _P2 + _P3) & _M
        p += 4
    while p < n:
        h ^= (b[p] * _P5) & _M
        h = (rotl(h, 11) * _P1) & _M
        p += 1
    h ^= h >> 33
    h = (h * _P2) & _M
    h ^= h >> 29
    h = (h * _P3) & _M
    return h ^ (h >> 32)


# GX formats: tile width, height and bytes
TILE = {0: (8, 8, 32), 1: (8, 4, 32), 2: (8, 4, 32), 3: (4, 4, 32), 4: (4, 4, 32), 5: (4, 4, 32),
        6: (4, 4, 64), 8: (8, 8, 32), 9: (8, 4, 32), 10: (4, 4, 32), 14: (8, 8, 32)}


def level_bytes(fmt, w, h):
    tw, th, tb = TILE[fmt]
    return ((w + tw - 1) // tw) * ((h + th - 1) // th) * tb


def palette_range(data, fmt):
    if fmt == 8:
        vals = set()
        for b in set(data):
            vals.update((b & 15, b >> 4))
    elif fmt == 9:
        vals = set(data)
    else:
        vals = {(data[i] << 8 | data[i + 1]) & 0x3FFF for i in range(0, len(data) - 1, 2)}
    return (min(vals), max(vals)) if vals else (0, 0)


def bti_texture(buf, off=0):
    """A BTI-style texture header at buf[off:]: (fmt, w, h, base level bytes, palette bytes, tlut format, mipmapped)."""
    t = buf[off:off + 0x20]
    fmt, w, h = t[0], *struct.unpack(">HH", t[2:6])
    if fmt not in TILE or not w or not h or w > 1024 or h > 1024:
        return None
    img = struct.unpack(">I", t[0x1C:0x20])[0]
    nb = level_bytes(fmt, w, h)
    if img < 0x20 or off + img + nb > len(buf):
        return None
    pal = b""
    if fmt in (8, 9, 10):
        po = struct.unpack(">I", t[0x0C:0x10])[0]
        pal = buf[off + po:off + po + struct.unpack(">H", t[0x0A:0x0C])[0] * 2]
    return fmt, w, h, buf[off + img:off + img + nb], pal, t[9], t[0x14] >= 2 and t[0x17] != 0


def texture_name(fmt, w, h, data, pal=b"", mipmapped=False):
    """Dolphin's custom texture name, as the PC port and Dolphin look it up."""
    name = "tex1_%dx%d%s_%016x" % (w, h, "_m" if mipmapped else "", xxh64(data))
    if fmt in (8, 9, 10) and pal:
        lo, hi = palette_range(data, fmt)
        name += "_%016x" % xxh64(pal[2 * lo:2 * (hi + 1)])
    return "%s_%d" % (name, fmt)


def j3d_textures(d):
    """(name, offset of its header in d) of each texture in a J3D model or material table."""
    if d[:4] != b"J3D2":
        return []
    pos = 0x20
    for _ in range(struct.unpack(">I", d[0xC:0x10])[0]):
        if pos + 8 > len(d):
            break
        ln = struct.unpack(">I", d[pos + 4:pos + 8])[0]
        if ln < 8:
            break
        if d[pos:pos + 4] == b"TEX1":
            count, hdr, names = struct.unpack(">H", d[pos + 8:pos + 10])[0], *struct.unpack(">II", d[pos + 0xC:pos + 0x14])
            tab = pos + names
            out = []
            for i in range(count):
                o = tab + struct.unpack(">H", d[tab + 6 + 4 * i:tab + 8 + 4 * i])[0]
                out.append((d[o:d.index(b"\0", o)].decode("latin1"), pos + hdr + 0x20 * i))
            return out
        pos += ln
    return []


def find_texture(disc, archive, member, texture="", cache={}):
    """The texture `texture` of model `member` (or the .bti `member` itself) in `archive`."""
    if archive not in cache:
        cache.clear()
        cache[archive] = dict(rarc(disc.read(archive)))
    d = yaz0(cache[archive][member])
    if not texture:
        return bti_texture(d, 0)
    for name, off in j3d_textures(d):
        if name == texture:
            return bti_texture(d, off)
    raise KeyError("%s has no texture %s" % (member, texture))
