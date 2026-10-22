#!/usr/bin/env python3
"""Pack the language packs into dist/ for a release.

usage: package_languages.py PACKS_DIR [PAGE_URL]

PACKS_DIR is make_language_packs.py's output (<lang>/files/...). Writes
dist/sms-language-<lang>-<LANGUAGES_VERSION>.zip for each language, each
holding <lang>/files/..., and dist/language-packs.json, the pin the PC port's
tools/mods/language-packs.json takes. Entries are sorted with fixed dates,
so the same packs always give the same files (and checksums).
"""
import hashlib
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAMES = {'fr': 'Français', 'de': 'Deutsch', 'es': 'Español', 'it': 'Italiano', 'pl': 'Polski', 'pt-br': 'Português (Brasil)'}
REPO = 'https://github.com/chasem-dev/sms-hd-texture-extras'


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    packs = sys.argv[1]
    version = open(os.path.join(ROOT, 'LANGUAGES_VERSION')).read().strip()
    tag = 'languages-v%s' % version
    os.makedirs(os.path.join(ROOT, 'dist'), exist_ok=True)
    pin = {'name': 'Super Mario Sunshine language packs v%s' % version, 'page': REPO + '#language-packs',
           'languages': {}}
    for lang in sorted(os.listdir(packs)):
        src = os.path.join(packs, lang)
        if lang not in NAMES or not os.path.isdir(os.path.join(src, 'files')):
            continue
        name = 'sms-language-%s-%s.zip' % (lang, version)
        out = os.path.join(ROOT, 'dist', name)
        files = sorted(os.path.relpath(os.path.join(dp, f), src).replace(os.sep, '/')
                       for dp, _, fs in os.walk(src) for f in fs if f != '.release')
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for rel in files:
                info = zipfile.ZipInfo('%s/%s' % (lang, rel), (2020, 1, 1, 0, 0, 0))
                info.external_attr = 0o644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                with open(os.path.join(src, rel), 'rb') as f:
                    z.writestr(info, f.read())
        data = open(out, 'rb').read()
        pin['languages'][lang] = {'name': NAMES[lang], 'url': '%s/releases/download/%s/%s' % (REPO, tag, name),
                                  'file': name, 'md5': hashlib.md5(data).hexdigest(), 'size': len(data)}
        print('%s: %d files, %d bytes, MD5 %s' % (os.path.relpath(out, ROOT), len(files), len(data),
                                                  hashlib.md5(data).hexdigest()))
    with open(os.path.join(ROOT, 'dist', 'language-packs.json'), 'w', encoding='utf-8') as f:
        json.dump(pin, f, indent=2, ensure_ascii=False)
        f.write('\n')
    print('dist/language-packs.json: the pin for the port (tools/mods/language-packs.json); release tag %s' % tag)


if __name__ == '__main__':
    main()
