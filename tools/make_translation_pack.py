#!/usr/bin/env python3
"""Turn a finished translation (the translation kit's text.pot filled in as a
.po) into a language pack for the PC port.

usage: tools/make_translation_pack.py US_ISO TEXT.po CODE OUT_DIR

Writes OUT_DIR/<CODE>/files/... in the port's pack layout: each text file the
translation changes, rebuilt from the North American one, as a file the port
puts inside that archive as it loads (files/data/scene/bianco0.szs/map/
message.bmg and so on). Every message keeps the North American file's
settings (voice, box style); an untranslated line stays English, and so do
the pictures. When the text needs letters the fonts lack (Polish: ą ć ę ł ń
ś ź ż), they are drawn into both text fonts (extra_letters.py).

The pack is used as a language (mods/languages/<CODE>, `language = CODE`)
by a port that knows the code, or as a mod by any: `mod = /path/to/<CODE>`.
"""
import os, re, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_language_packs import Disc, Rarc, yaz0_decode, bmg_sections, bmg_build  # noqa: E402
from make_translation_kit import text_files, messages, tag_text, ICONS  # noqa: E402
from bfn import Font  # noqa: E402
import extra_letters  # noqa: E402

ICON_CHAR = {v: k for k, v in ICONS.items()}
# where each of the kit's text files lives: (archive, file in it); None: kept
# English (the title screen's copy of the level names is drawn with a
# Japanese-encoded font and never shown to players)
def place(name):
    kind, _, n = name.partition('/')
    if kind == 'common':
        return 'data/common.szs', '2d/%s.bmg' % n
    if kind == 'option':
        return 'data/option.szs', 'loadmessage.bmg'
    if kind == 'guide':
        return 'data/guide.szs', 'guidemess.bmg'
    if kind == 'subtitle':
        return 'data/subtitle.szs', '%s.bmg' % n
    if kind == 'scene':
        return 'data/scene/%s.szs' % n, 'map/message.bmg'
    return None


def parse_po(path):
    """[(msgid, msgstr, [(file, index)])]"""
    out, cur, key = [], None, None

    def flush():
        if cur and cur['msgid']:
            out.append((cur['msgid'], cur['msgstr'], cur['refs']))

    def unq(s):
        s = s.strip()[1:-1]
        return re.sub(r'\\(.)', lambda m: {'n': '\n', 't': '\t'}.get(m.group(1), m.group(1)), s)

    for line in open(path, encoding='utf-8'):
        line = line.rstrip('\n')
        if line.startswith('#:'):
            if cur is None or key == 'msgstr':
                flush()
                cur, key = {'msgid': '', 'msgstr': '', 'refs': []}, None
            for r in line[2:].split():
                n, _, i = r.rpartition(':')
                cur['refs'].append((n, int(i)))
        elif line.startswith('msgid '):
            if cur is None or key == 'msgstr':
                flush()
                cur = {'msgid': '', 'msgstr': '', 'refs': []}
            key, cur['msgid'] = 'msgid', unq(line[6:])
        elif line.startswith('msgstr '):
            key, cur['msgstr'] = 'msgstr', unq(line[7:])
        elif line.startswith('"') and cur is not None and key:
            cur[key] += unq(line)
    flush()
    return out


TAG = re.compile(r'\{([a-zA-Z0-9]+)(?::([^}]*))?\}')


def encode_text(s, slots):
    """Kit text to the game's bytes: {tags} back to control codes and icons."""
    out, pos = bytearray(), 0
    for m in TAG.finditer(s):
        out += extra_letters.encode(s[pos:m.start()], slots)
        name, arg = m.group(1), m.group(2)
        if name in ICON_CHAR:
            out += ICON_CHAR[name].encode('cp1252')
        elif name == 'speed':
            out += bytes([0x1A, 6, 0, 0, 0, int(arg)])
        elif name == 'close':
            out += bytes([0x1A, 5, 0, 0, 1])
        elif name in ('choice1', 'choice2'):
            t = extra_letters.encode(arg, slots)
            if len(t) > 16:
                raise ValueError('the answer "%s" is longer than 16 letters' % arg)
            out += bytes([0x1A, 5 + len(t), 1, 0, int(name[-1]) - 1]) + t
        elif name == 'value':
            k, _, d = arg.partition(':')
            out += bytes([0x1A, 6 if d else 5, 2, 0, int(k)]) + (bytes([int(d)]) if d else b'')
        elif name == 'color':
            out += bytes([0x1A, 6, 0xFF, 0, 0, int(arg)])
        elif name == 'code':
            out += bytes.fromhex(arg)
        else:
            raise ValueError('unknown tag {%s}' % m.group(0)[1:-1])
        pos = m.end()
    out += extra_letters.encode(s[pos:], slots)
    return bytes(out)


def rebuild_bmg(us_bmg, texts):
    """The North American BMG with messages replaced: {index: bytes}."""
    head, secs = bmg_sections(us_bmg)
    i_inf = [k for k, s in enumerate(secs) if s[0] == b'INF1'][0]
    i_dat = [k for k, s in enumerate(secs) if s[0] == b'DAT1'][0]
    inf = secs[i_inf][1]
    n, es = struct.unpack('>HH', inf[:4])
    old = dict(messages(us_bmg))
    dat = bytearray(b'\0')
    ents = []
    for k in range(n):
        e = inf[8 + k * es:8 + (k + 1) * es]
        t = texts.get(k, old[k])
        if t:
            ents.append(struct.pack('>I', len(dat)) + e[4:])
            dat += t + b'\0'
        else:
            ents.append(struct.pack('>I', 0) + e[4:])
    secs[i_inf][1] = inf[:8] + b''.join(ents)
    secs[i_dat][1] = bytes(dat)
    return bmg_build(head, secs)


def main():
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    iso, po_path, code, out = sys.argv[1:]
    us = Disc(iso)
    if not us.id.startswith('GMSE'):
        sys.exit('need the North American disc (GMSE01), got %s' % us.id)
    entries = parse_po(po_path)
    files = text_files(us)
    english = {(name, k): s for name, _, msgs in files for k, s in msgs.items()}

    # the letters the fonts lack
    used = set(''.join(re.sub(r'\{[^}]*\}', '', ms) + ''.join(re.findall(r'\{choice\d:([^}]*)\}', ms))
                       for _, ms, _ in entries))
    missing = sorted(ch for ch in used if ch not in '\n' and not _cp1252(ch))
    slots, builder = None, None
    if missing:
        slots, builder = extra_letters.LANGUAGES.get(code, (None, None))
        lacking = [ch for ch in missing if not slots or ch not in slots]
        if lacking:
            sys.exit('the fonts have no %s, and no extra letters are defined for "%s"' % (' '.join(lacking), code))

    # the translation of each place, checked against the English it was made from
    tr, stale, problems = {}, 0, []
    for mid, ms, refs in entries:
        if not ms:
            continue
        for ref in refs:
            if english.get(ref) != mid:
                stale += 1
                continue
            try:
                tr[ref] = encode_text(ms, slots)
            except (ValueError, UnicodeEncodeError) as e:
                problems.append('%s:%d: %s' % (ref[0], ref[1], e))
    if problems:
        sys.exit('\n'.join(problems[:30]))

    def put(rel, data):
        path = os.path.join(out, code, 'files', rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data)

    cache, written, lines, kept = {}, 0, 0, []
    for name, _, msgs in files:
        texts = {k: tr[(name, k)] for k in msgs if (name, k) in tr}
        if not texts:
            continue
        where = place(name)
        if where is None:
            kept.append(name)
            continue
        archive, member = where
        if archive not in cache:
            cache[archive] = Rarc(yaz0_decode(us.read('/' + archive)))
        bmg = rebuild_bmg(cache[archive].get('/' + member), texts)
        # read back: the same text as the .po
        for k, t in messages(bmg):
            if k in texts and t != texts[k]:
                sys.exit('%s:%d did not read back' % (name, k))
        put('%s/%s' % (archive, member), bmg)
        written += 1
        lines += len(texts)
    if builder:
        sysf = Rarc(yaz0_decode(us.read('/data/nintendo.szs'))).get('/font/standard_fontex.bfn')
        subf = Rarc(yaz0_decode(us.read('/data/subtitle.szs'))).get('/font/demo_font.bfn')
        put('data/nintendo.szs/font/standard_fontex.bfn', bytes(builder(Font(sysf), False).d))
        put('data/subtitle.szs/font/demo_font.bfn', bytes(builder(Font(subf), True).d))
    print('%s: %d text files, %d lines translated%s%s%s' % (
        os.path.join(out, code), written, lines,
        ', letters added to the fonts: %s' % ' '.join(missing) if builder else '',
        '; %d places skipped whose English differs from the .po (an older kit?)' % stale if stale else '',
        '; kept English: %s' % ', '.join(kept) if kept else ''))


def _cp1252(ch):
    try:
        ch.encode('cp1252')
        return True
    except UnicodeEncodeError:
        return False


if __name__ == '__main__':
    main()
