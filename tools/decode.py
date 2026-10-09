import struct
from PIL import Image
TILE = {0:(8,8),1:(8,4),2:(8,4),3:(4,4),4:(4,4),5:(4,4),6:(4,4),8:(8,8),9:(8,4),10:(4,4),14:(8,8)}
def c565(v): r,g,b=(v>>11)&31,(v>>5)&63,v&31; return (r<<3|r>>2, g<<2|g>>4, b<<3|b>>2, 255)
def c5a3(v):
    if v & 0x8000: r,g,b=(v>>10)&31,(v>>5)&31,v&31; return (r<<3|r>>2, g<<3|g>>2, b<<3|b>>2, 255)
    a,r,g,b=(v>>12)&7,(v>>8)&15,(v>>4)&15,v&15; return (r*17,g*17,b*17,(a<<5)|(a<<2)|(a>>1))
def cia8(v): i,a=v&255,v>>8; return (i,i,i,a)
def decode(data, f, w, h, pal=b'', tfmt=0):
    tw, th = TILE[f]; img = Image.new('RGBA', (w, h)); px = img.load()
    pc = [cia8, c565, c5a3][min(tfmt, 2)]
    palc = [pc(struct.unpack_from('>H', pal, 2*i)[0]) for i in range(len(pal)//2)]
    P = lambda i: palc[i] if i < len(palc) else (255, 0, 255, 255)
    p = 0
    for by in range(0, h, th):
        for bx in range(0, w, tw):
            if f == 14:
                for sub in range(4):
                    sx, sy = bx + (sub & 1) * 4, by + (sub >> 1) * 4
                    c0, c1 = struct.unpack_from('>HH', data, p); bits = struct.unpack_from('>I', data, p+4)[0]; p += 8
                    a, b = c565(c0), c565(c1)
                    if c0 > c1: cols = [a, b, tuple((2*a[k]+b[k])//3 for k in range(3))+(255,), tuple((a[k]+2*b[k])//3 for k in range(3))+(255,)]
                    else: cols = [a, b, tuple((a[k]+b[k])//2 for k in range(3))+(255,), (0,0,0,0)]
                    for i in range(16):
                        x, y = sx + (i & 3), sy + (i >> 2)
                        if x < w and y < h: px[x, y] = cols[(bits >> (30 - 2*i)) & 3]
                continue
            if f == 6:
                ar = data[p:p+32]; gb = data[p+32:p+64]; p += 64
                for i in range(16):
                    x, y = bx + (i & 3), by + (i >> 2)
                    if x < w and y < h: px[x, y] = (ar[2*i+1], gb[2*i], gb[2*i+1], ar[2*i])
                continue
            for y in range(th):
                for x in range(tw):
                    X, Y = bx + x, by + y
                    if f in (0, 8):
                        b = data[p + (y*tw + x)//2]; v = (b >> 4) if x % 2 == 0 else (b & 15)
                        c = (v*17,)*3 + (v*17,) if f == 0 else P(v)
                    elif f in (1, 9):
                        v = data[p + y*tw + x]; c = (v, v, v, v) if f == 1 else P(v)
                    elif f == 2:
                        b = data[p + y*tw + x]; i, a = (b & 15)*17, (b >> 4)*17; c = (i, i, i, a)
                    else:
                        v = struct.unpack_from('>H', data, p + 2*(y*tw + x))[0]
                        c = cia8(v) if f == 3 else c565(v) if f == 4 else c5a3(v) if f == 5 else P(v & 0x3FFF)
                    if X < w and Y < h: px[X, Y] = c
            p += 32
    return img
