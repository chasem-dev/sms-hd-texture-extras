#!/usr/bin/env python3
"""Make the translation kit: everything a new translation of Super Mario
Sunshine needs, from the North American disc, as one zip.

usage: tools/make_translation_kit.py US_ISO OUT.zip [--reference PACKS_DIR]

The kit holds:
  text.pot          every line of the game's text once, in English, as a
                    gettext template: where it appears, and the game's
                    control codes and button icons as readable {tags}
  images/           every picture with words in it, as PNG, and images.csv
                    saying where each one shows and what it may change
  info.json         the translation's name, language and authors, to fill in
  README.md         how to translate it
With --reference, reference/<lang>.po holds the official European
translations (make_language_packs.py's packs) to compare with.
A translation is the kit with text.pot filled in as text.po (and any
pictures redrawn); a later script turns that into a pack for the PC port.
"""
import csv, io, json, os, re, struct, sys, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_language_packs import Disc, Rarc, yaz0_decode, bmg_sections, bmg_entries  # noqa: E402
import gcdisc  # noqa: E402
from decode import decode  # noqa: E402

KIT_VERSION = '1.0.0'

# ---------------------------------------------------------------- the text
# (kit name, archive, file in it, what it is)
TEXT_FILES = [
    ('common/sys_message', '/data/common.szs', '/2d/sys_message.bmg',
     'Characters\' speech bubbles shared by every level: yes/no questions, rewards, mini-games.'),
    ('common/balloon', '/data/common.szs', '/2d/balloon.bmg', 'FLUDD\'s tips, in the balloon over his gauge.'),
    ('common/infomess', '/data/common.szs', '/2d/infomess.bmg', 'The news ticker along the bottom of the screen.'),
    ('common/stagename', '/data/common.szs', '/2d/stagename.bmg',
     'Level names: the pause menu, the guide and the level\'s opening title. Upper case.'),
    ('common/scenarioname', '/data/common.szs', '/2d/scenarioname.bmg',
     'Episode names: the episode select, the pause menu and the level\'s opening title.'),
    ('common/savemessage', '/data/common.szs', '/2d/savemessage.bmg',
     'Saving after a Shine Sprite, in a fixed-size window (at most 6 lines).'),
    ('option/loadmessage', '/data/option.szs', '/loadmessage.bmg',
     'The file select and memory card messages, in a fixed-size window (at most 5 lines).'),
    ('guide/guidemess', '/data/guide.szs', '/guidemess.bmg', 'The pause menu\'s guide: each place\'s description.'),
    ('title/marisun_stage', '/data/title.szs', '/marisun_stage.bmg', 'The title screen.'),
]
MOVIES = {
    'openinga': 'the opening: the plane lands', 'openingba': 'the opening: the goop on the airstrip',
    'openingbb': 'the opening: Mario finds FLUDD', 'openingbc': 'the opening: Mario is arrested',
    'entrance': 'the trial and arrival in Delfino Plaza', 'nozurua': 'Shadow Mario and the stolen nozzle',
    'nozurub': 'Shadow Mario returns the nozzle', 'kagemario': 'Shadow Mario unmasked',
    'stolenpeach': 'Peach is kidnapped', 'kuppajr': 'Bowser Jr. on Corona Mountain', 'mechakuppa': 'Mecha-Bowser',
    'bath': 'Bowser in the hot tub', 'epilogue': 'the ending',
}
STAGES = [  # stage archive prefixes, longest first
    ('pinnaBeach', 'Pinna Park (beach)'), ('pinnaParco', 'Pinna Park'), ('coronaBoss', 'Corona Mountain'),
    ('airport', 'Delfino Airstrip'), ('dolpic', 'Delfino Plaza'), ('bianco', 'Bianco Hills'),
    ('ricco', 'Ricco Harbor'), ('rico', 'Ricco Harbor'), ('mamma', 'Gelato Beach'), ('sirena', 'Sirena Beach'),
    ('delfino', 'Hotel Delfino'), ('mare', 'Noki Bay'), ('monte', 'Pianta Village'), ('casino', 'Casino Delfino'),
    ('test', 'a test level (unused)'),
]

# The font's button icons, in place of these characters.
ICONS = {'@': 'A', '#': 'B', '+': 'X', '\xa5': 'Y', '$': 'Z', '<': 'L', '>': 'R', '%': 'C', '{': 'left', '}': 'right',
         '[': 'left2', ']': 'right2'}
TAGS_HELP = '''{A} {B} {X} {Y} {Z} {L} {R}  button icons; {C} the C-stick; {left} {right} arrows
{choice1:Yes} {choice2:No}  the two answers of a question (translate the words, 16 letters at most)
{color:4} ... {color:0}     colours a word: 2 orange, 3 light blue, 4 yellow, 5 green, 0 or 1 white
{speed:n}                   how fast the text appears; {close} closes the bubble by itself
{value:n}                   the game puts a number in here (a time, a count)'''


def tag_text(t):
    """A message's bytes (Windows-1252, with 0x1A control codes) as kit text."""
    out, i = [], 0
    while i < len(t):
        b = t[i]
        if b == 0x1A:
            n = t[i + 1]
            tag = t[i:i + n]
            group, kind, data = tag[2], struct.unpack('>H', tag[3:5])[0], tag[5:]
            if group == 0 and kind == 0 and len(data) == 1:
                out.append('{speed:%d}' % data[0])
            elif group == 0 and kind == 1 and not data:
                out.append('{close}')
            elif group == 1 and kind in (0, 1):
                out.append('{choice%d:%s}' % (kind + 1, data.decode('cp1252')))
            elif group == 2 and len(data) <= 1:
                out.append('{value:%d}' % kind if not data else '{value:%d:%d}' % (kind, data[0]))
            elif group == 0xFF and kind == 0 and len(data) == 1:
                out.append('{color:%d}' % data[0])
            else:
                out.append('{code:%s}' % tag.hex())
            i += n
            continue
        c = bytes([b]).decode('cp1252', 'replace')
        out.append('{%s}' % ICONS[c] if c in ICONS else c)
        i += 1
    return ''.join(out)


def messages(d):
    """[(index, message bytes)] of a BMG, its control codes kept whole."""
    _, secs = bmg_sections(d)
    es, ents = bmg_entries(d)
    dat = [s for s in secs if s[0] == b'DAT1'][0][1]
    out = []
    for k, e in enumerate(ents):
        o = i = struct.unpack('>I', e[:4])[0]
        while dat[i]:
            i += dat[i + 1] if dat[i] == 0x1A else 1
        out.append((k, dat[o:i]))
    return out


def text_files(us):
    """[(kit name, description, {index: kit text})] for every text the game shows."""
    out = []
    cache = {}

    def arc(p):
        if p not in cache:
            cache[p] = Rarc(yaz0_decode(us.read(p)))
        return cache[p]

    for name, a, f, what in TEXT_FILES:
        out.append((name, what, {k: tag_text(t) for k, t in messages(arc(a).get(f))}))
    sub = arc('/data/subtitle.szs')
    for k in sorted(sub.files()):
        if k.endswith('.bmg'):
            n = k[1:-4]
            out.append(('subtitle/' + n, 'Cutscene subtitles: %s.' % MOVIES.get(n, n),
                        {i: tag_text(t) for i, t in messages(sub.get(k))}))
    for p in sorted(x for x in us.files if x.startswith('/data/scene/') and x.endswith('.szs')):
        r = Rarc(yaz0_decode(us.read(p)))
        if not r.has('/map/message.bmg'):
            continue
        stage = os.path.basename(p)[:-4]
        place = next(n for k, n in STAGES if stage.startswith(k))
        m = re.search(r'(_ex)?(\d+)$', stage)
        kind = 'a secret course' if '_ex' in stage else 'episode/visit %s' % m.group(2) if m else ''
        out.append(('scene/' + stage, 'Characters and signs in %s (%s).' % (place, kind),
                    {k: tag_text(t) for k, t in messages(r.get('/map/message.bmg'))}))
    return out


def po_string(s):
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    parts = s.split('\n')
    if len(parts) == 1:
        return '"%s"' % parts[0]
    return '""\n' + '\n'.join('"%s\\n"' % p for p in parts[:-1]) + ('\n"%s"' % parts[-1] if parts[-1] else '')


def po(files, translations=None, language=''):
    """A gettext file of every distinct line, with where each appears.
    translations: {(kit name, index): text} for a .po, None for the template."""
    entries = {}  # English -> [(kit name, index)]
    for name, what, msgs in files:
        for k, s in msgs.items():
            if s:
                entries.setdefault(s, []).append((name, k))
    what = {n: w for n, w, _ in files}
    out = io.StringIO()
    out.write('# Super Mario Sunshine (North American, GMSE01): the game\'s text.\n'
              '# Tags: see README.md. Keep \\n line breaks about where the English has them.\n'
              'msgid ""\nmsgstr ""\n"Project-Id-Version: sms-translation-kit %s\\n"\n'
              '"PO-Revision-Date: \\n"\n"Last-Translator: \\n"\n"Language-Team: \\n"\n'
              '"Language: %s\\n"\n"MIME-Version: 1.0\\n"\n"Content-Type: text/plain; charset=UTF-8\\n"\n'
              '"Content-Transfer-Encoding: 8bit\\n"\n\n' % (KIT_VERSION, language))
    for s, places in entries.items():
        names = []
        for n, _ in places:
            if n not in names:
                names.append(n)
        for n in names[:3]:
            out.write('#. %s\n' % what[n])
        if len(names) > 3:
            out.write('#. (and %d more places)\n' % (len(names) - 3))
        lines = s.split('\n')
        out.write('#. %d line%s, the longest %d characters\n' % (len(lines), 's' * (len(lines) > 1),
                                                                 max(len(re.sub(r'\{[^}]*\}', 'W', l)) for l in lines)))
        out.write('#: %s\n' % ' '.join('%s:%d' % p for p in places))
        out.write('msgid %s\n' % po_string(s))
        tr = ''
        if translations:
            tr = next((translations[p] for p in places if translations.get(p)), '')
            if tr:  # a leading or trailing line break on both or neither, as gettext expects
                if s.endswith('\n') != tr.endswith('\n'):
                    tr = tr + '\n' if s.endswith('\n') else tr.rstrip('\n')
                if s.startswith('\n') != tr.startswith('\n'):
                    tr = '\n' + tr if s.startswith('\n') else tr.lstrip('\n')
        out.write('msgstr %s\n\n' % po_string(tr))
    return out.getvalue()


# ---------------------------------------------------------------- pictures
# (archive, file in it, what it shows, what it may change); the ones the
# European release translated, plus the North American game's own that have
# words and the GO!/SHINE!/TOO BAD! letters
IMAGES = [
    ('/data/option.szs', '/timg/title_start_%02d.bti' % i, 'PRESS START, letter %d (one picture per letter)' % i,
     'title letters: 10 to 15 letters in all (more or fewer letters is fine)') for i in range(1, 12)
] + [
    ('/data/option.szs', '/timg/select_%s.bti' % n, w, 'a menu word: may be wider than the English (its box widens)')
    for n, w in [('start', 'START (file menu)'), ('copy', 'COPY (file menu)'), ('erase', 'ERASE (file menu)'),
                 ('score', 'SCORE (file menu)'), ('new', 'NEW (empty file)'), ('options', 'OPTIONS (file select)'),
                 ('yes', 'YES (file select)'), ('no', 'NO (file select)'), ('quit', 'QUIT (options)'),
                 ('rumble', 'RUMBLE (options)'), ('sound', 'SOUND (options)'), ('subtitles', 'SUBTITLES (options)'),
                 ('on', 'ON (options)'), ('off', 'OFF (options)'), ('mono', 'MONO (options)'),
                 ('stereo', 'STEREO (options)'), ('surround', 'SURROUND (options)'), ('total', 'TOTAL (score screen)')]
] + [
    ('/data/option.szs', '/timg/stage_%s.bti' % n, '%s (score screen)' % w, 'a level name: may be wider')
    for n, w in [('airport', 'DELFINO AIRSTRIP'), ('bianco', 'BIANCO HILLS'), ('dolpictown', 'DELFINO PLAZA'),
                 ('mamma', 'GELATO BEACH'), ('mare', 'NOKI BAY'), ('monte', 'PIANTA VILLAGE'), ('pinna', 'PINNA PARK'),
                 ('ricco', 'RICCO HARBOR'), ('sirena', 'SIRENA BEACH')]
] + [
    ('/data/option.szs', '/timg/shine_icon_min.bti', 'the file select\'s Shine icon (no words; German redrew it)', 'same size'),
    ('/data/game_6.szs', '/timg/water_text.bti', 'TANK, on FLUDD\'s gauge', 'same size'),
    ('/data/game_6.szs', '/timg/water_text_0.bti', 'WATER, on FLUDD\'s gauge', 'same size'),
    ('/data/game_6.szs', '/timg/juice_text_0.bti', 'FRUIT, on Yoshi\'s gauge', 'same size'),
    ('/data/game_6.szs', '/timg/juice_text_1.bti', 'JUICE, on Yoshi\'s gauge', 'same size'),
    ('/data/game_6.szs', '/timg/life_text.bti', 'LIFE, on the life meter', 'same size'),
    ('/data/game_6.szs', '/timg/time_text.bti', 'TIME, over the timer', 'same size'),
    ('/data/game_6.szs', '/timg/pause_tx_1.bti', 'the pause menu\'s first choice (CONTINUE)', 'same size'),
    ('/data/game_6.szs', '/timg/pause_tx_2.bti', 'the pause menu\'s second choice (SAVE)', 'same size'),
    ('/data/game_6.szs', '/timg/pause_tx_3.bti', 'the pause menu\'s third choice (EXIT AREA)', 'same size'),
    ('/data/game_6.szs', '/timg/select_yes.bti', 'YES, in the game\'s speech bubbles', 'same size'),
    ('/data/game_6.szs', '/timg/select_no.bti', 'NO, in the game\'s speech bubbles', 'same size'),
    ('/data/endsave.szs', '/timg/end_text_1.bti', 'THE END', 'same size'),
    ('/data/endsave.szs', '/timg/end_text_2.bti', 'Have a relaxing vacation! (after THE END)', 'same size'),
    ('/data/endsave.szs', '/timg/select_yes.bti', 'YES, saving after the ending', 'same size'),
    ('/data/endsave.szs', '/timg/select_no.bti', 'NO, saving after the ending', 'same size'),
    ('/data/common.szs', '/2d/wipe_gameover.bti', 'GAME OVER', 'same size'),
    ('/data/subtitle.szs', '/timg/title_mini.bti', 'Nintendo presents SUPER MARIO SUNSHINE (the opening\'s credit)', 'same size'),
] + [
    ('/data/guide.szs', '/timg/%s.bti' % n, w, 'same size') for n, w in
    [('guide_title', 'ISLE DELFINO, the guide map\'s heading'),
     ('guide_tx_1', 'the guide map\'s welcome paragraph (Welcome to Isle Delfino...)'),
     ('guide_tx_2', 'the guide map\'s second paragraph (Picturesque bays...)'), ('guide_tx_click', 'CLICK!, on the guide map'),
     ('guide_tx_score', 'TOTALS, on the guide map'), ('guide_total', 'TOTAL, in the guide'),
     ('sc_myscore', 'SCORE, in the guide'), ('guide_map_dolphic_title', 'Delfino Plaza, a label on the guide map'),
     ('guide_map_pinna', 'the guide\'s map of Pinna Park, with its labels')]
     + [('guide_guide_title_%02d' % i, 'a level name, the heading of its guide page (%d)' % i) for i in range(10)]
     + [('guide_place_name_%02d' % i, 'a level name on the guide map (%d)' % i) for i in range(10)]
     + [('guide_picture_%02d' % i, 'a level\'s picture in the guide, with its name on it (%d)' % i)
        for i in (2, 3, 4, 6, 7, 8, 9)]
] + [
    ('/data/select.szs', '/timg/sc_map_%s.bti' % n, 'the episode select\'s map of %s, with its name' % w, 'same size')
    for n, w in [('bianco', 'Bianco Hills'), ('mamma', 'Gelato Beach'), ('mare', 'Noki Bay'),
                 ('monte', 'Pianta Village'), ('pinna', 'Pinna Park'), ('ricco', 'Ricco Harbor'),
                 ('sirena', 'Sirena Beach'), ('corona', 'Corona Mountain')]
] + [
    ('/data/select.szs', '/timg/sc_myscore.bti', 'SCORE, on the episode select', 'same size'),
    ('/data/select.szs', '/timg/sc_story.bti', 'EPISODE, on the episode select', 'same size'),
]


def png(buf):
    t = gcdisc.bti_texture(buf)
    fmt, w, h, data, pal, tfmt, _ = t
    img = decode(data, fmt, w, h, pal, tfmt)
    out = io.BytesIO()
    img.save(out, 'PNG')
    return out.getvalue(), fmt, w, h


FORMATS = {0: 'I4', 1: 'I8', 2: 'IA4', 3: 'IA8', 4: 'RGB565', 5: 'RGB5A3', 6: 'RGBA8', 8: 'C4', 9: 'C8', 10: 'C14X2',
           14: 'CMPR'}


# ---------------------------------------------------------------- the kit
README = '''# Super Mario Sunshine translation kit

Everything to translate Super Mario Sunshine for the PC port into a new language:
all of the game's text, and every picture with words in it.

## Text: `text.pot`

Every line of the game's text, once, in English: about 1,570 lines, 19,000 words.
Copy `text.pot` to `text.po` and fill in each `msgstr` with an editor such as
[Poedit](https://poedit.net), or any text editor.
Above each line, `#.` says where it appears and how long the English is, and
`#:` lists every place it is used (a line used in several levels is
translated once).

- Keep the `\\n` line breaks about where the English has them. Speech bubbles
  scroll, so a few more lines are fine; the memory card and save windows have
  room for 5 or 6 lines only. A line much longer than the English may not fit.
- The `{tags}` are the game's control codes and button icons; keep them, and move
  them with the words they belong to:

```
%s
```

- Letters: the game's font has the Western European ones (Windows-1252: é è ê ë
  à â ä ç ñ ö ü ß œ ¿ ¡ « » …). Languages that need other letters need a font too.
- Leave a line empty to keep the English.

## Pictures: `images/`

Every picture with words in it, as PNG, in folders named after the game's
archives. `images/images.csv` says what each shows and what it may change:
menu words may be wider than the English (their boxes widen to fit), the rest
should keep their size. Redraw the ones you translate under the same names;
leave the others as they are.

PRESS START (`option/title_start_NN.png`) and the shouts GO! SHINE! TOO BAD!
(`letters/`) are one picture per letter: PRESS START may have 10 to 15
letters, a shout up to 12. Add letters as new pictures in the same style.

## `reference/`

The official French, German, Spanish and Italian translations in the same form
(`fr.po`, `de.po`, `es.po`, `it.po`), to see how a line was handled, or to start
from a language close to yours.

## `info.json`

The translation's name in its own language, its language code, and its authors.

Send the kit back with `text.po`, any redrawn pictures and `info.json`; a script
turns it into a language pack for the port.
''' % TAGS_HELP


def main():
    args = sys.argv[1:]
    ref = None
    if '--reference' in args:
        i = args.index('--reference')
        ref = args[i + 1]
        del args[i:i + 2]
    if len(args) != 2:
        sys.exit(__doc__)
    us = Disc(args[0])
    if not us.id.startswith('GMSE'):
        sys.exit('need the North American disc (GMSE01), got %s' % us.id)
    files = text_files(us)
    count = sum(len(m) for _, _, m in files)
    z = zipfile.ZipFile(args[1], 'w', zipfile.ZIP_DEFLATED, compresslevel=9)

    def put(name, data):
        info = zipfile.ZipInfo('sms-translation-kit/' + name, (2020, 1, 1, 0, 0, 0))
        info.external_attr = 0o644 << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, data)

    pot = po(files)
    put('text.pot', pot)
    put('README.md', README)
    put('info.json', json.dumps({'language': 'xx', 'name': 'Language name, in that language',
                                 'english_name': 'Language name in English', 'authors': [''], 'version': '0.1'},
                                indent=2, ensure_ascii=False) + '\n')
    # pictures
    rows = []
    cache = {}
    for a, f, what, rule in IMAGES:
        if a not in cache:
            cache[a] = Rarc(yaz0_decode(us.read(a)))
        if not cache[a].has(f):
            continue
        data, fmt, w, h = png(cache[a].get(f))
        name = '%s/%s.png' % (os.path.basename(a)[:-4], os.path.basename(f)[:-4])
        put('images/' + name, data)
        rows.append([name, what, '%dx%d' % (w, h), FORMATS.get(fmt, fmt), rule])
    g6 = cache.get('/data/game_6.szs') or Rarc(yaz0_decode(us.read('/data/game_6.szs')))
    for k in sorted(g6.files()):
        if k.startswith('/timg/big_tx_'):
            data, fmt, w, h = png(g6.get(k))
            name = 'letters/%s.png' % os.path.basename(k)[:-4]
            put('images/' + name, data)
            rows.append([name, 'a letter of the shouts GO!, SHINE!, TOO BAD!, READY', '%dx%d' % (w, h),
                         FORMATS.get(fmt, fmt), 'add the letters your shouts need, in this style'])
    s = io.StringIO()
    csv.writer(s).writerows([['file', 'shows', 'size', 'format', 'may change']] + rows)
    put('images/images.csv', s.getvalue())
    # the official translations, as examples
    if ref:
        for lang in sorted(os.listdir(ref)):
            base = os.path.join(ref, lang, 'files', 'data')
            if not os.path.isdir(base):
                continue
            tr = {}
            arcs = {}
            for name, _, msgs in files:
                kind, _, n = name.partition('/')
                if kind == 'scene':
                    path = os.path.join(base, 'scene', n + '.szs', 'map', 'message.bmg')
                    d = open(path, 'rb').read() if os.path.exists(path) else None
                elif kind == 'common':
                    path = os.path.join(base, 'common.szs', '2d', n + '.bmg')
                    d = open(path, 'rb').read() if os.path.exists(path) else None
                else:
                    a = {'option': 'option.szs', 'guide': 'guide.szs', 'subtitle': 'subtitle.szs'}.get(kind)
                    d = None
                    if a and os.path.exists(os.path.join(base, a)):
                        if a not in arcs:
                            arcs[a] = Rarc(yaz0_decode(open(os.path.join(base, a), 'rb').read()))
                        f = '/loadmessage.bmg' if kind == 'option' else '/%s.bmg' % n
                        d = arcs[a].get(f) if arcs[a].has(f) else None
                if d:
                    for k, t in messages(d):
                        tr[(name, k)] = tag_text(t)
            put('reference/%s.po' % lang, po(files, tr, lang))
    z.close()
    print('%s: %d lines (%d distinct), %d pictures%s' % (args[1], count, pot.count('\nmsgid ') - 1, len(rows),
                                                          ', with references' if ref else ''))


if __name__ == '__main__':
    main()
