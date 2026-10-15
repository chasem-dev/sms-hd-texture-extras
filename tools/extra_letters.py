"""Letters a translation needs that the game's fonts lack, drawn into font
slots its language does not use.

The fonts are single-byte, laid out as Windows-1252 (Western European). For
Polish, ą ć ę ł ń ś ź ż and their capitals are drawn from the fonts' own
glyphs (acutes from é, the dot from i, a stroke across l/L, a drawn ogonek)
into the slots Windows-1250 gives them, except Ą, whose slot holds the Y
button icon here. ó Ó are in the fonts already."""
from PIL import Image, ImageChops, ImageDraw, ImageFilter

# Polish letter -> font slot: Windows-1250's, except Ą (0xA5 is the Y button
# icon in this font), which takes 0x81, a slot the font leaves empty
POLISH = {'ą': 0xB9, 'ć': 0xE6, 'ę': 0xEA, 'ł': 0xB3, 'ń': 0xF1, 'ś': 0x9C, 'ź': 0x9F, 'ż': 0xBF,
         'Ą': 0x81, 'Ć': 0xC6, 'Ę': 0xCA, 'Ł': 0xA3, 'Ń': 0xD1, 'Ś': 0x8C, 'Ź': 0x8F, 'Ż': 0xAF}


def c(ch):
    return ch.encode('cp1252')[0]


def rows_with_ink(im, thresh=40):
    return [y for y in range(im.height) if any(im.getpixel((x, y)) > thresh for x in range(im.width))]


def cols_with_ink(im, thresh=40):
    return [x for x in range(im.width) if any(im.getpixel((x, y)) > thresh for y in range(im.height))]


def crop_rows(img, y0, y1):
    """img with only rows y0..y1-1 kept"""
    out = Image.new('L', img.size, 0)
    out.paste(img.crop((0, y0, img.width, y1)), (0, y0))
    return out


def shifted(img, dx, dy):
    out = Image.new('L', img.size, 0)
    out.paste(img, (dx, dy))
    return out


def centre_x(A):
    xs = cols_with_ink(A)
    return (xs[0] + xs[-1]) / 2 if xs else A.width / 2


def build(font, outlined):
    """Add the Polish letters to `font` (bfnlib.Font). outlined: the glyphs have
    a dark outline in their alpha (the subtitle font)."""
    out_r = 2 if outlined else 0

    def get(ch):
        return font.get(c(ch))

    def mark(base_ch, accented_ch):
        """the accent of `accented_ch` over `base_ch`: the rows above base's ink"""
        bI, bA = get(base_ch)
        aI, aA = get(accented_ch)
        top = rows_with_ink(bA)[0]
        return crop_rows(aI, 0, top - 1), crop_rows(aA, 0, top - 1), centre_x(crop_rows(aA, 0, top - 1))

    def place(base_ch, mI, mA, mcx, dy=0):
        bI, bA = get(base_ch)
        dx = round(centre_x(bA) - mcx)
        I = ImageChops.lighter(bI, shifted(mI, dx, dy))
        A = ImageChops.lighter(bA, shifted(mA, dx, dy))
        return I, A

    def stroke_shape(I, A, draw_fn):
        """add a drawn white shape (with an outline for the subtitle font)"""
        s = Image.new('L', I.size, 0)
        draw_fn(ImageDraw.Draw(s))
        if outlined:  # the outline goes under what is there; the white on top
            A = ImageChops.lighter(A, s.filter(ImageFilter.MaxFilter(2 * out_r + 1)))
            I = ImageChops.lighter(I, s)
        else:
            I = ImageChops.lighter(I, s)
            A = I
        return I, A

    acute_lo = mark('e', 'é')
    if outlined:
        # É's accent runs into the E's outline: raise é's accent over the capital
        core = lambda ch: rows_with_ink(get(ch)[0], 120)
        lift = (core('e')[0] - rows_with_ink(acute_lo[0], 120)[-1]) - core('E')[0] + rows_with_ink(acute_lo[0], 120)[-1]
        acute_hi = (shifted(acute_lo[0], 0, core('E')[0] - core('e')[0]),
                    shifted(acute_lo[1], 0, core('E')[0] - core('e')[0]), acute_lo[2])
    else:
        acute_hi = mark('E', 'É')
    # the dot of i: its ink above the gap under it
    iI, iA = get('i')
    ys = rows_with_ink(iI if outlined else iA, 120)  # the white core: the outline joins dot and stem
    gap = next(y for y in range(ys[0], ys[-1]) if y not in ys)
    if outlined:
        gap += 1  # keep the dot's outline below it
    dot = (crop_rows(iI, 0, gap), crop_rows(iA, 0, gap), centre_x(crop_rows(iA, 0, gap)))
    dot_lo_dy = rows_with_ink(acute_lo[1])[-1] - rows_with_ink(dot[1])[-1]
    dot_hi_dy = rows_with_ink(acute_hi[1])[-1] - rows_with_ink(dot[1])[-1]

    made = {}
    for lo, up, base_lo, base_up in [('ć', 'Ć', 'c', 'C'), ('ń', 'Ń', 'n', 'N'), ('ś', 'Ś', 's', 'S'), ('ź', 'Ź', 'z', 'Z')]:
        made[lo] = place(base_lo, *acute_lo) + (base_lo,)
        made[up] = place(base_up, *acute_hi) + (base_up,)
    made['ż'] = place('z', dot[0], dot[1], dot[2], dot_lo_dy) + ('z',)
    made['Ż'] = place('Z', dot[0], dot[1], dot[2], dot_hi_dy) + ('Z',)

    # ł Ł: a stroke rising to the right across the stem
    th = 2 if not outlined else 3
    for ch, base in [('ł', 'l'), ('Ł', 'L')]:
        bI, bA = get(base)
        core = bA if not outlined else bI  # the white part
        xs, ys = cols_with_ink(core, 120), rows_with_ink(core, 120)
        stem_x = xs[0] + (2 if outlined else 1)  # the stem's middle (the left part of L)
        mid = (ys[0] + ys[-1]) // 2 + (1 if base == 'l' else 0)
        reach = max(3, (xs[-1] - xs[0]) // 2 if base == 'l' else 3)
        x0, x1 = stem_x - reach - (1 if outlined else 0), stem_x + reach + 1

        def draw(d, x0=x0, x1=x1, mid=mid):
            d.line([(x0, mid + 2), (x1, mid - 2)], fill=255, width=th)
        I, A = stroke_shape(bI, bA, draw)
        made[ch] = (I, A, base)

    # ą ę Ą Ę: an ogonek, a small hook below the bottom right
    for ch, base in [('ą', 'a'), ('ę', 'e'), ('Ą', 'A'), ('Ę', 'E')]:
        bI, bA = get(base)
        core = bA if not outlined else bI
        ys = rows_with_ink(core, 120)
        bottom = ys[-1]
        bx = [x for x in range(core.width) if core.getpixel((x, bottom)) > 120]
        xr = bx[-1] if bx else cols_with_ink(core)[-1]
        if base in ('e', 'E'):
            xr = (bx[0] + bx[-1]) // 2 + (2 if not outlined else 3) if bx else xr
        h = 3 if not outlined else 4
        w = 3 if not outlined else 4

        def draw(d, xr=xr, bottom=bottom, h=h, w=w):
            # down from the letter's foot, curving left, then a little up
            d.arc([xr - 2 * w, bottom - h + 1, xr, bottom + h + 1], 0, 150, fill=255, width=th)
        I, A = stroke_shape(bI, bA, draw)
        made[ch] = (I, A, base)

    for ch, (I, A, base) in made.items():
        slot = POLISH[ch]
        font.put(slot, I, A)
        kern, w = font.width(c(base))
        if ch in ('ł', 'Ł'):
            xs = cols_with_ink(A)
            w = max(w, xs[-1] - kern + 2)
        font.set_width(slot, kern, w)
    return font


# the extra letters of each language that has some: {letter: slot}, and the
# function drawing them into a font
LANGUAGES = {'pl': (POLISH, build)}


def encode(text, slots=None):
    """Text to the font's bytes: a language's extra letters' slots, else
    Windows-1252 (UnicodeEncodeError for a letter the fonts lack)."""
    out = bytearray()
    for ch in text:
        out += bytes([slots[ch]]) if slots and ch in slots else ch.encode('cp1252')
    return bytes(out)


def render(font, text, scale=4, bg=(70, 80, 140)):
    """A line of text drawn with the font, for checking glyphs by eye."""
    data = encode(text, POLISH)
    x, cells = 0, []
    for b in data:
        kern, w = font.width(b)
        cells.append((x - 0, font.get(b)))
        x += w
    im = Image.new('RGB', (x + font.cw, font.ch), bg)
    for x0, (I, A) in cells:
        g = Image.merge('RGB', (I, I, I))
        im.paste(g, (x0, 0), A)
    return im.resize((im.width * scale, im.height * scale), Image.NEAREST)
