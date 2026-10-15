"""Read and write the game's BFN fonts: glyph sheets (I4 or IA4) and widths."""
import struct
from PIL import Image

def blocks(d):
    o, out = 0x20, {}
    while o + 8 <= len(d):
        t, s = d[o:o+4], struct.unpack('>I', d[o+4:o+8])[0]
        if s == 0: break
        out[t] = (o, s); o += s
    return out

class Font:
    def __init__(self, d):
        self.d = bytearray(d); b = blocks(d)
        go, gs = b[b'GLY1']
        self.gly = go
        (self.first, self.last, self.cw, self.ch, self.sheet_size, self.fmt, self.cols, self.rows,
         self.sw, self.sh) = struct.unpack('>HHHHIHHHHH', d[go+8:go+30])
        self.sheets = (gs - 0x20) // self.sheet_size
        mo, ms = b[b'MAP1']
        self.map_kind, self.map_first, self.map_last = struct.unpack('>HHH', d[mo+8:mo+14])
        wo, ws = b[b'WID1']
        self.wid = wo
        self.wfirst, self.wlast = struct.unpack('>HH', d[wo+8:wo+12])
    def index(self, code):  # linear map (kind 0) from map_first
        assert self.map_kind == 0
        return code - self.map_first
    def _px(self, g, x, y):
        """byte offset and nibble/byte layout of glyph g's pixel (x, y)"""
        per = self.cols * self.rows
        sheet, k = divmod(g, per); r, c = divmod(k, self.cols)
        X, Y = c * self.cw + x, r * self.ch + y
        base = self.gly + 0x20 + sheet * self.sheet_size
        if self.fmt == 0:   # I4: 8x8 blocks of 4-bit
            blk = ((Y // 8) * (self.sw // 8) + X // 8) * 32; p = (Y % 8) * 8 + X % 8
            return base + blk + p // 2, p % 2
        if self.fmt == 2:   # IA4: 8x4 blocks of 8-bit (A hi, I lo)
            blk = ((Y // 4) * (self.sw // 8) + X // 8) * 32; p = (Y % 4) * 8 + X % 8
            return base + blk + p, None
        raise ValueError(self.fmt)
    def get(self, code):
        """(I, A) images of a glyph, 0-255"""
        g = self.index(code); I = Image.new('L', (self.cw, self.ch)); A = Image.new('L', (self.cw, self.ch))
        for y in range(self.ch):
            for x in range(self.cw):
                o, half = self._px(g, x, y); b = self.d[o]
                if self.fmt == 0:
                    v = (b >> 4) if half == 0 else b & 15; I.putpixel((x, y), v * 17); A.putpixel((x, y), v * 17)
                else:
                    I.putpixel((x, y), (b & 15) * 17); A.putpixel((x, y), (b >> 4) * 17)
        return I, A
    def put(self, code, I, A=None):
        g = self.index(code)
        for y in range(self.ch):
            for x in range(self.cw):
                o, half = self._px(g, x, y); i = round(I.getpixel((x, y)) / 17)
                if self.fmt == 0:
                    b = self.d[o]
                    self.d[o] = (b & 0x0F) | (i << 4) if half == 0 else (b & 0xF0) | i
                else:
                    a = round((A or I).getpixel((x, y)) / 17)
                    self.d[o] = (a << 4) | i
    def width(self, code):
        g = self.index(code) - self.wfirst; o = self.wid + 12 + 2 * g
        return self.d[o], self.d[o + 1]  # kerning (left), width
    def set_width(self, code, kern, w):
        g = self.index(code) - self.wfirst; o = self.wid + 12 + 2 * g
        self.d[o], self.d[o + 1] = kern, w
