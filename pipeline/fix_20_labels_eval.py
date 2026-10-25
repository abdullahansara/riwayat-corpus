"""Phase 1 - turn Claude labels (phrases) into offsets and compare them with the database.
  python pipeline/fix_20_labels_eval.py LABEL_DIR_OUT [--show N]
Reads LABEL_DIR_OUT/chunk_*.jsonl.  Prints: label coverage, matn start/end agreement with the DB (exact / within 10 chars), where the labeller
disagrees, mention-kind counts, ID agreement (label choice vs asserted ID / guess), and examples of each disagreement for eye reading.
Writes LABEL_DIR_OUT/_resolved.jsonl with offsets (matn_start, matn_end) for every label whose phrases were found exactly once-or-first in the text."""
from paths import *
import sqlite3, sys, json, glob, os, re, collections
D = sys.argv[1]; SHOW = int(sys.argv[sys.argv.index('--show') + 1]) if '--show' in sys.argv else 6
c = sqlite3.connect('file:' + OUT + 'hadith_master.db?mode=ro', uri=True)
DIAC = re.compile('[ً-ْٰـٓ-ٕ]')
TRN = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def plain(text):
    """letters only (no diacritics, no punctuation), single spaces; keep[i] = text offset of plain char i"""
    out = []; keep = []; sp = False
    for i, ch in enumerate(text):
        if DIAC.match(ch): continue
        ch2 = ch.translate(TRN)
        if 'ء' <= ch2 <= 'ي': out.append(ch2); keep.append(i); sp = False
        elif not sp and out: out.append(' '); keep.append(i); sp = True
    return ''.join(out), keep
def find(text, phrase, after=0, last=False):
    """offset of phrase in text, diacritic/punctuation-insensitive; returns (start,end) in text offsets or None"""
    if not phrase: return None
    pt, keep = plain(text); pp = plain(phrase)[0].strip()
    if not pp: return None
    i = pt.rfind(pp) if last else pt.find(pp)
    if i < 0: return None
    j = i + len(pp) - 1
    return keep[i], keep[j] + 1
rows = []
for fn in sorted(glob.glob(os.path.join(D, 'chunk_*.jsonl'))):
    for l in open(fn, encoding='utf-8'):
        l = l.strip()
        if l: rows.append(json.loads(l))
print('labels', len(rows))
st = collections.Counter(); show = collections.defaultdict(list); res = []
kinds = collections.Counter(); idc = collections.Counter()
for r in rows:
    h = c.execute('select text,matn_start,matn_end,chain_tier from hadith where id=?', (r['id'],)).fetchone()
    if not h: st['unknown id'] += 1; continue
    text, ms, me, tier = h
    ls = find(text, r.get('matn_start_phrase', '')); le = find(text, r.get('matn_end_phrase', ''), last=True)
    st['status ' + r.get('chain_status', '?')] += 1
    if r.get('chain_status') == 'no_sanad_in_source' and not r.get('matn_start_phrase'): ls = (0, 0)
    if ls is None: st['start phrase not found'] += 1
    if le is None: st['end phrase not found'] += 1
    if ls and ms is not None:
        d = ls[0] - ms
        k = 'start exact(<=2)' if abs(d) <= 2 else 'start near(<=10)' if abs(d) <= 10 else ('start label EARLIER' if d < 0 else 'start label LATER')
        st[k] += 1
        if k.startswith('start label'): show[k].append((r['id'], d, text[max(0, ms - 50):ms].replace('\n', ' '), '||', text[ms:ms + 50].replace('\n', ' '), '| LABEL:', r['matn_start_phrase'][:50]))
    elif ls and ms is None: st['start: DB has none, label has'] += 1
    if le and me is not None:
        d = le[1] - me
        k = 'end exact(<=2)' if abs(d) <= 2 else 'end near(<=10)' if abs(d) <= 10 else ('end label EARLIER' if d < 0 else 'end label LATER')
        st[k] += 1
        if k.startswith('end label'): show[k].append((r['id'], d, text[max(0, me - 50):me].replace('\n', ' '), '||', text[me:me + 40].replace('\n', ' '), '| LABEL:', r['matn_end_phrase'][-50:]))
    res.append({**r, 'matn_start': ls[0] if ls else None, 'matn_end': le[1] if le else None, 'tier': tier})
    ments = {m['i']: m for m in json.load(open(os.path.join(os.path.dirname(D.rstrip('/\\')), os.path.basename(D.rstrip('/\\')).replace('_out', ''), 'chunk_000.json'), encoding='utf-8'))} if False else None
json.dump(res, open(os.path.join(D, '_resolved.json'), 'w', encoding='utf-8'), ensure_ascii=False)
for k, v in sorted(st.items()): print(f'  {k:40s} {v}')
for k, v in show.items():
    print('==', k, len(v))
    for x in v[:SHOW]: print('  ', x)
