#!/usr/bin/env python3
"""Build the language packs for sms-pc-port from the European disc.

usage: tools/make_language_packs.py PAL_ISO US_ISO OUT_DIR [LANG...]

PAL_ISO is Super Mario Sunshine for Europe (GMSP01), US_ISO the North
American disc (GMSE01) the port plays. LANG is fr, de, es or it (default:
all four). Writes OUT_DIR/<lang>/files/..., which the port reads from
mods/languages/<lang>/ with `language = <lang>` in settings.txt.

The European disc keeps each language's 2D archives as <name>_<xx>.szs and
its text and pictures as <name>_<xx>.bmg and timg/<xx>/ inside shared
archives; the US game reads the plain names. A pack holds, for the US game:
  files/data/<name>.szs                 the language's game_6, guide, select,
                                        subtitle and endsave archives
  files/data/option.szs                 the US archive with the language's
                                        menus: text, title and score
                                        layouts, word pictures (their boxes
                                        widened to fit), and the help line
  files/data/common.szs/2d/...          files the port puts inside the US
  files/data/nintendo.szs/font/...      archive of that name: the system
  files/data/scene/<stage>.szs/map/...  text, the font, each stage's lines
The text keeps the European words but takes each message's attributes from
the US file: Europe moved the voice byte two places later in its stage and
system messages, and inserted one options help line in the memory card text.
"""
import os, re, struct, sys

LANGS = {'fr': 'fr', 'de': 'ge', 'es': 'sp', 'it': 'it'}  # pack code -> disc suffix
WHOLE = ['game_6', 'guide', 'select', 'subtitle', 'endsave']
COMMON_TEXT = ['balloon', 'infomess', 'savemessage', 'scenarioname', 'stagename', 'sys_message']
# the file select's menus of START, COPY, ERASE and SCORE, one per file
MENU_WINDOWS = {'load': ('w_4', 'w_5', 'w_6')}
LOADMESSAGE_PAL_ONLY = 28  # the options help line, which the US game has in option.blo
# option.blo's help line, styled as the US one: a green icon, then white text
HELP_ICON = b'\x1bFX[24]\x1bFY[24]\x1bCC[64FF64]\x1bGC[64FF64]%s\x1bFX[18]\x1bCC[FFFFFF]\x1bGC[FFFFFF]'


# ---------------------------------------------------------------- disc
class Disc:
    def __init__(self, path):
        self.f = open(path, 'rb')
        self.id = self.f.read(6).decode('latin1')
        self.f.seek(0x424)
        fo, fs = struct.unpack('>II', self.f.read(8))
        self.f.seek(fo)
        fst = self.f.read(fs)
        n = struct.unpack('>I', fst[8:12])[0]
        strt = n * 12
        self.files = {}

        def name(o):
            return fst[strt + o:fst.index(b'\0', strt + o)].decode('latin1')

        def walk(i, end, path):
            while i < end:
                w0, a, b = struct.unpack('>III', fst[i * 12:i * 12 + 12])
                nm = name(w0 & 0xFFFFFF)
                if w0 >> 24:
                    walk(i + 1, b, path + nm + '/')
                    i = b
                else:
                    self.files[path + nm] = (a, b)
                    i += 1

        walk(1, n, '/')

    def read(self, path):
        a, b = self.files[path]
        self.f.seek(a)
        return self.f.read(b)


# ---------------------------------------------------------------- Yaz0
def yaz0_decode(d):
    if d[:4] != b'Yaz0':
        return d
    n = struct.unpack('>I', d[4:8])[0]
    o = bytearray()
    i = 16
    while len(o) < n:
        c = d[i]
        i += 1
        for b in range(8):
            if len(o) >= n:
                break
            if c & (0x80 >> b):
                o.append(d[i])
                i += 1
            else:
                b1, b2 = d[i], d[i + 1]
                i += 2
                dist = ((b1 & 15) << 8 | b2) + 1
                if b1 >> 4:
                    ln = (b1 >> 4) + 2
                else:
                    ln = d[i] + 0x12
                    i += 1
                for _ in range(ln):
                    o.append(o[-dist])
    return bytes(o)


def yaz0_store(raw):
    """A valid Yaz0 stream holding `raw` as literals only (the zip packs it)."""
    out = bytearray(b'Yaz0' + struct.pack('>I', len(raw)) + bytes(8))
    for i in range(0, len(raw), 8):
        out.append(0xFF)
        out += raw[i:i + 8]
    return bytes(out)


# ---------------------------------------------------------------- RARC
class Rarc:
    """An archive as folders of named entries, which can be changed and written."""

    def __init__(self, d):
        nn, no, fn, fo, sl, so, nfiles, self.sync = struct.unpack('>IIIIIIHB', d[0x20:0x3B])
        no += 0x20
        fo += 0x20
        so += 0x20
        doff = 0x20 + struct.unpack('>I', d[0x0C:0x10])[0]

        def name(o):
            return d[so + o:d.index(b'\0', so + o)].decode('latin1')

        self.nodes = []
        for i in range(nn):
            typ, nmo, h, cnt, first = struct.unpack('>4sIHHI', d[no + i * 16:no + i * 16 + 16])
            ents = []
            for k in range(first, first + cnt):
                e = fo + k * 20
                fid, eh, flags, nmoff, off, size = struct.unpack('>HHHHII', d[e:e + 16])
                ent = {'name': name(nmoff), 'flags': flags, 'hash': eh}
                if flags & 0x0200:
                    ent['node'] = off
                else:
                    ent['data'] = d[doff + off:doff + off + size]
                ents.append(ent)
            self.nodes.append({'type': typ, 'name': name(nmo), 'hash': h, 'ents': ents})

    def _find(self, path):
        parts = [p for p in path.lower().split('/') if p]
        node = 0
        for p in parts[:-1]:
            node = next(e['node'] for e in self.nodes[node]['ents'] if 'node' in e and e['name'].lower() == p)
        return node, parts[-1]

    def files(self):
        out = {}

        def walk(node, path):
            for e in self.nodes[node]['ents']:
                if e['name'] in ('.', '..'):
                    continue
                if 'node' in e:
                    walk(e['node'], path + '/' + e['name'])
                else:
                    out[(path + '/' + e['name']).lower()] = e

        walk(0, '')
        return out

    def get(self, path):
        return self.files()[path.lower()]['data']

    def has(self, path):
        return path.lower() in self.files()

    def put(self, path, data):
        """Replace a file, or add it to its (existing) folder."""
        f = self.files()
        if path.lower() in f:
            f[path.lower()]['data'] = data
            return
        node, leaf = self._find(path)
        ents = self.nodes[node]['ents']
        h = 0
        for c in leaf.encode('latin1'):
            h = (h * 3 + c) & 0xFFFF
        like = next(e for e in ents if 'data' in e)  # same flags as its neighbours
        at = next((i for i, e in enumerate(ents) if e['name'] in ('.', '..')), len(ents))
        ents.insert(at, {'name': path.split('/')[-1], 'flags': like['flags'], 'hash': h, 'data': data})

    def build(self):
        strings = bytearray(b'.\0..\0')
        offs = {'.': 0, '..': 2}

        def soff(s):
            if s not in offs:
                offs[s] = len(strings)
                strings.extend(s.encode('latin1') + b'\0')
            return offs[s]

        nodes = bytearray()
        ents = bytearray()
        data = bytearray()
        index = 0
        for nd in self.nodes:
            nodes += struct.pack('>4sIHHI', nd['type'], soff(nd['name']), nd['hash'], len(nd['ents']), index)
            for e in nd['ents']:
                if 'node' in e:
                    ents += struct.pack('>HHHHIII', 0xFFFF, e['hash'], e['flags'], soff(e['name']), e['node'], 0x10, 0)
                else:
                    data += bytes(-len(data) % 32)
                    fid = index if self.sync else 0
                    ents += struct.pack('>HHHHIII', fid, e['hash'], e['flags'], soff(e['name']), len(data),
                                        len(e['data']), 0)
                    data += e['data']
                index += 1
        data += bytes(-len(data) % 32)

        def pad(b):
            return bytes(b) + bytes(-len(b) % 32)

        nodes, ents_b, strings = pad(nodes), pad(ents), pad(strings)
        info_len = 0x20
        node_off = info_len
        ent_off = node_off + len(nodes)
        str_off = ent_off + len(ents_b)
        data_off = str_off + len(strings)
        nfiles = index
        info = struct.pack('>IIIIIIHBB', len(self.nodes), node_off, nfiles, ent_off, len(strings), str_off,
                           nfiles, self.sync, 0) + bytes(4)
        body = info + nodes + ents_b + strings
        head = struct.pack('>4sIIIIIII', b'RARC', 0x20 + len(body) + len(data), 0x20, len(body), len(data),
                           len(data), 0, 0)
        return head + body + bytes(data)


# ---------------------------------------------------------------- BMG
def bmg_sections(d):
    assert d[:8] == b'MESGbmg1', d[:8]
    n = struct.unpack('>I', d[0x0C:0x10])[0]
    o, out = 0x20, []
    for _ in range(n):
        tag, size = d[o:o + 4], struct.unpack('>I', d[o + 4:o + 8])[0]
        out.append([tag, d[o + 8:o + size]])
        o += size
    return d[:0x20], out


def bmg_build(head, sections):
    body = b''
    for tag, payload in sections:
        sec = tag + bytes(4) + payload
        sec += bytes(-len(sec) % 32)
        body += sec[:4] + struct.pack('>I', len(sec)) + sec[8:]
    head = bytearray(head)
    struct.pack_into('>II', head, 0x08, 0x20 + len(body), len(sections))
    return bytes(head) + body


def bmg_entries(d):
    _, secs = bmg_sections(d)
    p = [s for s in secs if s[0] == b'INF1'][0][1]
    n, es = struct.unpack('>HH', p[:4])
    return es, [p[8 + i * es:8 + (i + 1) * es] for i in range(n)]


def bmg_text(d, i):
    _, secs = bmg_sections(d)
    es, ents = bmg_entries(d)
    dat = [s for s in secs if s[0] == b'DAT1'][0][1]
    o = struct.unpack('>I', ents[i][:4])[0]
    return dat[o:dat.index(b'\0', o)]


def convert_bmg(pal, us, name, drop=None):
    """The European text with the US message attributes."""
    head, secs = bmg_sections(pal)
    i = [k for k, s in enumerate(secs) if s[0] == b'INF1'][0]
    es, ents = bmg_entries(pal)
    if drop is not None:
        del ents[drop]
    ues, uents = bmg_entries(us)
    if (len(ents), es) != (len(uents), ues):
        raise SystemExit('%s: %d entries of %d bytes, the US file %d of %d' % (name, len(ents), es, len(uents), ues))
    out = []
    for p, u in zip(ents, uents):
        if p[4:] != u[4:] and not (es == 12 and p[4:8] + p[10:12] + b'\0\0' == u[4:]):
            raise SystemExit('%s: message attributes %s vs US %s fit no known layout' % (name, p[4:].hex(), u[4:].hex()))
        out.append(p[:4] + u[4:])
    old = secs[i][1]
    secs[i][1] = struct.pack('>HH', len(out), es) + old[4:8] + b''.join(out)
    return bmg_build(head, secs)


# ---------------------------------------------------------------- BLO
def blo_chunks(d):
    o, out = 0x20, []
    while o + 8 <= len(d):
        t, s = d[o:o + 4], struct.unpack('>I', d[o + 4:o + 8])[0]
        if s == 0:
            break
        out.append((o, t, s))
        if t == b'EXT1':
            break
        o += s
    return out


def blo_panes(d):
    """{tag: (chunk offset, kind, x, y, w, h, texture name)}"""
    out = {}
    for o, t, s in blo_chunks(d):
        if t in (b'PAN1', b'PIC1', b'WIN1', b'TBX1'):
            tag = d[o + 12:o + 16].lstrip(b'\0').decode('latin1')
            x, y, w, h = struct.unpack('>hhhh', d[o + 16:o + 24])
            tex = ''
            if t == b'PIC1':  # its picture: 02, the name's length, the name
                m = re.search(rb'\x02([\x01-\x7f])([\w.]+?\.bti)', d[o + 24:o + s])
                if m and m.group(1)[0] == len(m.group(2)):
                    tex = m.group(2).decode('latin1')
            out[tag] = (o, t, x, y, w, h, tex)
    return out


def blo_children(d):
    """{tag: [its direct children's tags]} from the layout's BGN1/END1 nesting"""
    kids, stack, last = {}, [], None
    for o, t, s in blo_chunks(d):
        if t == b'BGN1':
            stack.append(last)
        elif t == b'END1':
            stack.pop()
        elif t in (b'PAN1', b'PIC1', b'WIN1', b'TBX1'):
            last = d[o + 12:o + 16].lstrip(b'\0').decode('latin1')
            if stack and stack[-1]:
                kids.setdefault(stack[-1], []).append(last)
    return kids


def blo_set_text(d, tag, text):
    """A copy of layout `d` with text box `tag`'s string replaced."""
    for o, t, s in blo_chunks(d):
        if t == b'TBX1' and d[o + 12:o + 16].lstrip(b'\0').decode('latin1') == tag:
            body = d[o + 8:o + s]
            p = body.index(b'standard_font.bfn')
            # after the font name: 8 bytes of colours, a byte of settings and
            # four u16s (font size and spacing), then the string's u16 length
            # and the string
            sl = p + len(b'standard_font.bfn') + 8 + 1 + 8
            ln = struct.unpack('>H', body[sl:sl + 2])[0]
            new = body[:sl] + struct.pack('>H', len(text)) + text + body[sl + 2 + ln:]
            new += bytes(-(len(new) + 8) % 4)
            chunk = t + struct.pack('>I', len(new) + 8) + new
            out = d[:o] + chunk + d[o + s:]
            return out[:8] + struct.pack('>I', len(out)) + out[12:]
    raise SystemExit('no text box %s' % tag)


def blo_set_rect(d, off, x, y, w, h):
    d = bytearray(d)
    struct.pack_into('>hhhh', d, off + 16, x, y, w, h)
    return bytes(d)


def bti_size(d):
    return struct.unpack('>HH', d[2:6])


# ---------------------------------------------------------------- packs
def build_option(us_option, pal_option, lx):
    """The US option.szs with language `lx`'s menus (see the module docstring)."""
    a = Rarc(us_option)
    p = Rarc(pal_option)
    pf = p.files()
    lang_imgs = {k.split('/')[-1]: e['data'] for k, e in pf.items() if k.startswith('/timg/%s/' % lx)}
    us_imgs = {k.split('/')[-1]: e['data'] for k, e in a.files().items() if k.startswith('/timg/')}

    # text: the memory card messages, and option.blo's help line
    lm_pal = pf['/loadmessage_%s.bmg' % lx]['data']
    a.put('/loadmessage.bmg', convert_bmg(lm_pal, a.get('/loadmessage.bmg'), 'loadmessage', LOADMESSAGE_PAL_ONLY))
    help_line = bmg_text(lm_pal, LOADMESSAGE_PAL_ONLY).rstrip(b' ')
    help_line = help_line.replace(b'*', HELP_ICON % b'*', 1).replace(b'@', HELP_ICON % b'@', 1)

    # the title and score screens: the language's own layouts, with every
    # picture they show from the European disc (the title's is its own logo,
    # which those layouts are drawn around, and up to 15 PRESS START letters)
    for blo in ('title_1', 'load_score'):
        k = '/scrn/%s_%s.blo' % (blo, lx)
        a.put('/scrn/%s.blo' % blo, pf[k]['data'])
        for v in blo_panes(pf[k]['data']).values():
            n = v[6].lower()
            if not n:
                continue
            img = lang_imgs.get(n) or (pf['/timg/' + n]['data'] if '/timg/' + n in pf else None)
            if img is not None:
                a.put('/timg/' + n, img)
            # else the US archive's own, or one the game finds in another archive

    # the word pictures of the US file select and options screens, from the
    # language's
    for n, img in sorted(lang_imgs.items()):
        if n in us_imgs:
            a.put('/timg/' + n, img)

    # load.blo and option.blo stay the US layouts: each word's box is resized
    # as its picture is, about the box's centre (its children kept where they
    # were); the file menus' windows widen to fit their widest word, keeping
    # their margins and the screen's edges, with the words centred again
    for blo in ('load', 'option'):
        d = a.get('/scrn/%s.blo' % blo)
        kids = blo_children(d)

        parent = {k: p for p, ks in kids.items() for k in ks}

        def left(d, tag):  # its x on the screen
            x = 0
            while tag in blo_panes(d):
                x += blo_panes(d)[tag][2]
                tag = parent.get(tag)
            return x

        def move(d, tag, dx, dy, w=None, h=None):
            off, kind, x, y, ow, oh, tex = blo_panes(d)[tag]
            d = blo_set_rect(d, off, x + dx, y + dy, ow if w is None else w, oh if h is None else h)
            for k in kids.get(tag, []):  # children are placed relative to it
                ko, kk, kx, ky, kw, kh, kt = blo_panes(d)[k]
                d = blo_set_rect(d, ko, kx - dx, ky - dy, kw, kh)
            return d

        for tag, (off, kind, x, y, w, h, tex) in list(blo_panes(d).items()):
            tex = tex.lower()
            if kind == b'PIC1' and tex in lang_imgs and tex in us_imgs:
                (uw, uh), (lw, lh) = bti_size(us_imgs[tex]), bti_size(lang_imgs[tex])
                nw, nh = round(w * lw / uw), round(h * lh / uh)
                dx = -((nw - w) // 2)
                sx = left(d, tag) + dx  # kept inside the screen's 600 units
                dx += max(0, 6 - sx) - max(0, sx + nw - 594)
                d = move(d, tag, dx, -((nh - h) // 2), nw, nh)
        for win in MENU_WINDOWS.get(blo, ()):
            panes = blo_panes(d)
            off, kind, x, y, w, h, tex = panes[win]
            words = [panes[k] for k in kids[win]]
            margin = 26  # the US menus': (150 - 97) / 2
            nw = max(w, max(p[4] for p in words) + 2 * margin)
            nx = min(max(x - (nw - w) // 2, 24), 600 - 24 - nw)  # room for the selected word, drawn larger
            d = blo_set_rect(d, off, nx, y, nw, h)
            d = bytearray(d)  # its inner fill grows with it (x, y, w, h at +29)
            cw = struct.unpack('>h', d[off + 33:off + 35])[0]
            struct.pack_into('>h', d, off + 33, cw + nw - w)
            d = bytes(d)
            for k in kids[win]:
                ko, kk, kx, ky, kw, kh, kt = blo_panes(d)[k]
                d = blo_set_rect(d, ko, (nw - kw) // 2, ky, kw, kh)
        if blo == 'option':
            for tag in ('m_0a', 'm_0b'):
                d = blo_set_text(d, tag, help_line)
        a.put('/scrn/%s.blo' % blo, d)
    return a.build()


def main():
    args = sys.argv[1:]
    if len(args) < 3:
        sys.exit(__doc__)
    pal, us, out = Disc(args[0]), Disc(args[1]), args[2]
    langs = args[3:] or list(LANGS)
    if not pal.id.startswith('GMSP') or not us.id.startswith('GMSE'):
        sys.exit('need the European (GMSP01) and North American (GMSE01) discs, got %s and %s' % (pal.id, us.id))
    for lang in langs:
        if lang not in LANGS:
            sys.exit('unknown language %s (use %s)' % (lang, ', '.join(LANGS)))

    def put(lang, rel, blob):
        path = os.path.join(out, lang, 'files', rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(blob)

    us_common = Rarc(yaz0_decode(us.read('/data/common.szs')))
    us_option = yaz0_decode(us.read('/data/option.szs'))
    pal_option = yaz0_decode(pal.read('/data/option.szs'))
    pal_font = Rarc(yaz0_decode(pal.read('/data/nintendo.szs'))).get('/font/standard_fontex.bfn')
    for lang in langs:
        lx = LANGS[lang]
        for n in WHOLE:
            src = pal.read('/data/%s_%s.szs' % (n, lx))
            if n in ('game_6', 'guide') and struct.unpack('>I', src[4:8])[0] > 0x64000:
                sys.exit('%s_%s unpacks to more than the game\'s 0x64000-byte buffer' % (n, lx))
            put(lang, 'data/%s.szs' % n, src)
        cmn2d = Rarc(yaz0_decode(pal.read('/data/cmn2d_%s.szs' % lx)))
        for n in COMMON_TEXT:
            put(lang, 'data/common.szs/2d/%s.bmg' % n,
                convert_bmg(cmn2d.get('/%s.bmg' % n), us_common.get('/2d/%s.bmg' % n), n))
        put(lang, 'data/common.szs/2d/wipe_gameover.bti', cmn2d.get('/wipe_gameover.bti'))
        put(lang, 'data/nintendo.szs/font/standard_fontex.bfn', pal_font)
        put(lang, 'data/option.szs', yaz0_store(build_option(us_option, pal_option, lx)))
        print('%s: menus done' % lang, flush=True)

    scenes = sorted(p for p in us.files if p.startswith('/data/scene/') and p.endswith('.szs'))
    for i, p in enumerate(scenes):
        u = Rarc(yaz0_decode(us.read(p)))
        if not u.has('/map/message.bmg'):
            continue
        pv = Rarc(yaz0_decode(pal.read(p)))
        for lang in langs:
            msg = convert_bmg(pv.get('/map/message_%s.bmg' % LANGS[lang]), u.get('/map/message.bmg'), p)
            put(lang, 'data/scene/%s/map/message.bmg' % os.path.basename(p), msg)
        print('\rstages: %d/%d' % (i + 1, len(scenes)), end='', flush=True)
    print()
    for lang in langs:
        print('%s -> %s' % (lang, os.path.join(out, lang)))


if __name__ == '__main__':
    main()
