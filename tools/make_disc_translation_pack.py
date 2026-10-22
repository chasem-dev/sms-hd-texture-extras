#!/usr/bin/env python3
"""Turn a fan translation made on a European disc into a language pack.

usage: tools/make_disc_translation_pack.py PAL_ISO US_ISO TRANSLATED_DISC SLOT CODE OUT_DIR [FIXES.json]

Some fan translations replace one of the European disc's five languages
(GMSP01): Brazilian Portuguese, for example, takes the Spanish slot of the
disc inside Super Mario 3D All-Stars. TRANSLATED_DISC is that disc (a
GameCube image, or 3D All-Stars' .gcm), SLOT the language it replaced (fr,
de, es or it) and CODE the pack's code (pt-br). Writes OUT_DIR/<CODE>/files/...
as make_language_packs.py does for the official languages.

The pack is the retail European disc's language SLOT with the translation's
text and the pictures it redrew (those whose pixels differ from the retail
ones). Everything else, layouts, subtitle timings and fonts, stays the
retail disc's, so a translation made on 3D All-Stars, which changed some of
those, still fits the GameCube game. A line the translation left in the
slot's language takes its translation of the same line elsewhere, if any.

The text is checked against the retail disc, message by message: the same
number of messages, the same ones empty, the same control codes, and no
English that 3D All-Stars reworded for the Switch's controls (with button
icons the GameCube font lacks). What fails is fixed in FIXES.json:
  {"remove": "¡¿",                         letters dropped from every message
   "messages": {"common/balloon 54": "text", "subtitle/nozurub 9": null},
                                           a message's text; null: keep the translation's
   "insert": {"common/scenarioname": {"26": "text"}},
                                           messages the translation left out
   "source": {"scene/monte6": "scene/mare6"},
                                           a file's text, from the file it was put in
   "files": {"scene/mare6": ["text", ...]}}  a file's whole text
Names are the kit's (common/<name>, option/loadmessage, guide/guidemess,
subtitle/<movie>, scene/<stage>), indexes the European disc's, and text uses
the translation kit's tags ({A}, {R}, {speed:50}, ...).
"""
import collections, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_language_packs import Disc, Rarc, yaz0_decode, yaz0_store, build, LANGS, WHOLE  # noqa: E402
from make_translation_kit import messages, tag_text  # noqa: E402
from make_translation_pack import encode_text, rebuild_bmg  # noqa: E402
from bfn import Font  # noqa: E402
import gcdisc  # noqa: E402
from decode import decode  # noqa: E402

SWITCH_ICONS = '|~'  # 3D All-Stars' ZR and right stick: no such pictures in the GameCube font
TAG = re.compile(r'\{[^}]*\}')
KIND = {'cmn2d': 'common'}  # archive -> kit name


def pixels(bti):
    fmt, w, h, data, pal, tfmt, _ = gcdisc.bti_texture(bti)
    return decode(data, fmt, w, h, pal, tfmt).convert('RGBA').tobytes()


class Translated:
    """The retail European disc, as make_language_packs.build reads it, with language `lx` taken from a
    translated one."""

    def __init__(self, pal, tr, lx, fixes):
        self.pal, self.tr, self.lx, self.fixes = pal, tr, lx, fixes
        self.id, self.files = pal.id, pal.files
        self.arcs, self.cache, self.used, self.pictures, self.texts, self.untranslated = {}, {}, set(), [], {}, {}
        self.scan()

    def arc(self, disc, path):
        key = (disc is self.pal, path)
        if key not in self.arcs:
            self.arcs[key] = Rarc(yaz0_decode(disc.read(path)))
        return self.arcs[key]

    def where(self, name, lx=None):
        """(archive, file) of a kit text file in language lx (the slot's)"""
        lx = lx or self.lx
        kind, _, n = name.partition('/')
        if kind == 'scene':
            return '/data/scene/%s.szs' % n, '/map/message_%s.bmg' % lx
        if kind == 'option':
            return '/data/option.szs', '/loadmessage_%s.bmg' % lx
        return '/data/%s_%s.szs' % ({v: k for k, v in KIND.items()}.get(kind, kind), lx), '/%s.bmg' % n

    def names(self):
        out = []
        for n in WHOLE + ['cmn2d']:
            out += ['%s/%s' % (KIND.get(n, n), k[1:-4]) for k in self.arc(self.pal, '/data/%s_%s.szs' % (n, self.lx))
                    .files() if k.endswith('.bmg')]
        out.append('option/loadmessage')
        return out + ['scene/' + os.path.basename(p)[:-4] for p in sorted(self.pal.files)
                      if p.startswith('/data/scene/') and p.endswith('.szs')]

    # ------------------------------------------------------------ the text
    def scan(self):
        """Read each text file on both discs once: its messages, the English 3D All-Stars reworded, and a
        translation memory (each retail line's translation)"""
        self.msgs = {}
        memory = collections.defaultdict(collections.Counter)
        names = self.names()
        for i, name in enumerate(names):
            print('\rreading the text: %d/%d' % (i + 1, len(names)), end='', flush=True)
            a, f = self.where(name)
            if not self.arc(self.pal, a).has(f):
                continue
            rm = [m for _, m in messages(self.arc(self.pal, a).get(f))]
            ea, ef = self.where(name, 'en')
            en_r = dict(messages(self.arc(self.pal, ea).get(ef))) if self.arc(self.pal, ea).has(ef) else {}
            en_t = dict(messages(self.arc(self.tr, ea).get(ef))) if self.arc(self.tr, ea).has(ef) else {}
            if name in self.fixes.get('files', {}):
                self.used.add(name)
                tr = [encode_text(t, None) for t in self.fixes['files'][name]]
            else:
                src = self.fixes.get('source', {}).get(name)
                if src:
                    self.used.add(name)
                sa, sf = self.where(src or name)
                tr = [m for _, m in messages(self.arc(self.tr, sa).get(sf))]
            if name in self.fixes.get('insert', {}):
                self.used.add(name)
                for k, text in sorted((int(k), t) for k, t in self.fixes['insert'][name].items()):
                    tr.insert(k, encode_text(text, None))
            if len(tr) != len(rm):
                sys.exit('\n%s: %d messages, the retail disc has %d (FIXES.json "insert", "source" or "files")'
                         % (name, len(tr), len(rm)))
            off = [k for k, (m, r) in enumerate(zip(tr, rm)) if bool(m) != bool(r)]
            if off:
                sys.exit('\n%s: messages %s are empty on one disc and not the other: out of step? (FIXES.json'
                         ' "insert", "source" or "files")' % (name, off))
            self.msgs[name] = (rm, tr, {k for k in en_r if en_r[k] != en_t.get(k)})
            for r, m in zip(rm, tr):
                if m != r:
                    memory[r][m] += 1
            if name.startswith('scene/'):  # don't keep whole stages
                for d in (True, False):
                    self.arcs.pop((d, a), None)
        print()
        self.memory = {r: c.most_common(1)[0][0] for r, c in memory.items()}

    def text(self, name, retail):
        """The retail BMG (its attributes) with the translated messages"""
        rm, tr, reworded = self.msgs[name]
        out, left = {}, []
        for k, (r, m) in enumerate(zip(rm, tr)):
            key = '%s %d' % (name, k)
            fixed = key in self.fixes['messages']
            if fixed:
                self.used.add(key)
                if self.fixes['messages'][key] is not None:
                    m = encode_text(self.fixes['messages'][key], None)
            elif k in reworded:
                sys.exit('%s: 3D All-Stars reworded the English of this line; the translation is %r. Put it in'
                         ' FIXES.json' % (key, tag_text(m)))
            if m == r and r.strip() and r in self.memory:
                m = self.memory[r]  # left untranslated here, translated elsewhere
            if m == r and len(TAG.sub('', tag_text(r)).strip()) > 12:
                left.append(k)
            t = tag_text(m)
            for ch in self.fixes.get('remove', ''):
                t = t.replace(ch, '')
            if not fixed and any(ch in t for ch in SWITCH_ICONS):
                sys.exit('%s: %r has a Switch button icon; put it in FIXES.json' % (key, t))
            if not fixed and sorted(TAG.findall(t)) != sorted(TAG.findall(tag_text(r))):
                sys.exit('%s: the control codes differ from the retail disc\'s:\n  retail:      %r\n  translation:'
                         ' %r\nPut it in FIXES.json' % (key, tag_text(r), t))
            out[k] = encode_text(t, None)
        if left:
            self.untranslated[name] = left
        bmg = rebuild_bmg(retail, out)
        self.texts[name] = bmg
        return bmg

    # ------------------------------------------------------------ the archives
    def read(self, path):
        if path in self.cache:
            return self.cache[path]
        lx, base = self.lx, os.path.basename(path)[:-4]
        if path.startswith('/data/scene/') and 'scene/' + base in self.msgs:
            r = Rarc(yaz0_decode(self.pal.read(path)))
            f = '/map/message_%s.bmg' % lx
            r.put(f, self.text('scene/' + base, r.get(f)))
        elif path == '/data/option.szs' or any(path == '/data/%s_%s.szs' % (n, lx) for n in WHOLE + ['cmn2d']):
            r = Rarc(yaz0_decode(self.pal.read(path)))
            tf = self.arc(self.tr, path).files()
            for k in list(r.files()):
                if path == '/data/option.szs' and k != '/loadmessage_%s.bmg' % lx and \
                        not k.startswith('/timg/%s/' % lx):
                    continue  # not the language's
                if k.endswith('.bmg'):
                    kind = base.rsplit('_', 1)[0]
                    name = 'option/loadmessage' if kind == 'option' else '%s/%s' % (KIND.get(kind, kind), k[1:-4])
                    r.put(k, self.text(name, r.get(k)))
                elif k.endswith('.bti'):
                    leaf = k.split('/')[-1]
                    # 3D All-Stars' names: timg/_sp_select_new.bti, timg/title_start_01_sp.bti
                    src = next((a for a in (k, '/timg/_%s_%s' % (lx, leaf), '/timg/%s_%s.bti' % (leaf[:-4], lx))
                                if a in tf), None)
                    if src and tf[src]['data'] != r.get(k) and pixels(tf[src]['data']) != pixels(r.get(k)):
                        r.put(k, tf[src]['data'])
                        self.pictures.append(path + k)
                # layouts, subtitle timings and fonts stay the retail disc's
        else:
            return self.pal.read(path)
        self.cache[path] = yaz0_store(r.build())
        return self.cache[path]


def check_letters(pal, disc, lx):
    """Every letter the translation uses has a picture in the font that draws it."""
    fonts = {'text': Font(Rarc(yaz0_decode(pal.read('/data/nintendo.szs'))).get('/font/standard_fontex.bfn')),
             'subtitle': Font(Rarc(yaz0_decode(pal.read('/data/subtitle_%s.szs' % lx))).get('/font/demo_font.bfn'))}
    used = {'text': set(), 'subtitle': set()}
    for name, bmg in disc.texts.items():
        for _, m in messages(bmg):
            i = 0
            while i < len(m):
                if m[i] == 0x1A:
                    i += m[i + 1]
                    continue
                used['subtitle' if name.startswith('subtitle/') else 'text'].add(m[i])
                i += 1
    for which, codes in used.items():
        f = fonts[which]
        blank = [c for c in sorted(codes) if c > 0x20 and c != 0x0A
                 and (c < f.map_first or c > f.map_last or f.get(c)[1].getbbox() is None)]
        if blank:
            sys.exit('the %s font has no picture for %s' % (which, bytes(blank).decode('cp1252', 'replace')))


def main():
    args = sys.argv[1:]
    if len(args) not in (6, 7):
        sys.exit(__doc__)
    pal, us, tr = Disc(args[0]), Disc(args[1]), Disc(args[2])
    slot, code, out = args[3], args[4], args[5]
    fixes = {}
    if len(args) == 7:
        with open(args[6], encoding='utf-8') as f:
            fixes = json.load(f)
    fixes.setdefault('messages', {})
    if not pal.id.startswith('GMSP') or not tr.id.startswith('GMSP') or not us.id.startswith('GMSE'):
        sys.exit('need the European (GMSP01), North American (GMSE01) and translated European discs, got %s, %s'
                 ' and %s' % (pal.id, us.id, tr.id))
    if slot not in LANGS:
        sys.exit('SLOT is the language the translation replaced: %s' % ', '.join(LANGS))
    if not code or not all(c.isalnum() or c in '-_' for c in code):
        sys.exit('CODE is letters, digits, - and _ (pt-br)')
    lx = LANGS[slot]
    disc = Translated(pal, tr, lx, fixes)
    build(disc, us, out, {code: lx})
    named = set(fixes['messages']) | set(fixes.get('insert', {})) | set(fixes.get('source', {})) | \
        set(fixes.get('files', {}))
    if named - disc.used:
        sys.exit('FIXES.json names messages the disc has not: %s' % ', '.join(sorted(named - disc.used)))
    check_letters(pal, disc, lx)
    print('%s: text from %d files, %d redrawn pictures:' % (code, len(disc.texts), len(disc.pictures)))
    for p in disc.pictures:
        print('  ' + p)
    if disc.untranslated:
        print('lines left in the slot\'s language, with no translation of the same line elsewhere:')
        for name, ks in sorted(disc.untranslated.items()):
            print('  %s %s' % (name, ks))


if __name__ == '__main__':
    main()
