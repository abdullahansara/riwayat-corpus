"""Build gold/gold_chains.jsonl from the database chains plus hand corrections in gold/edits/*.txt.

Edit file format (one hadith per block; refs use the ORIGINAL mention positions shown by gold_view.py):
    @H0440942            start a block (the hadith is gold only if it has a block)
    ok                   every shown mention and ID was verified correct (no change)
    +2|حَجَّاجٌ|N0012345  insert a mention after original pos 2: surface exactly as it occurs in the text, narrator id (? = unknown)
    -7                   remove original mention 7 (not a narrator)
    =1|N0000999          set narrator id of original pos 1 ('?' = real narrator but no matching record)
    ~3                   keep id of original pos 3 but mark it unverifiable
    ^3|بَنِي فُلَانٍ        replace the surface text of original pos 3 (new boundaries; surface must occur in the text)
    #comment
Lines starting with # are ignored.  Each mention gets id_verified=true unless marked ~ .
Usage: python tools/gold_apply.py            (writes gold/gold_chains.jsonl and prints a summary)
       python tools/gold_apply.py --db       (additionally writes the corrections into the database)"""
import sqlite3, sys, os, re, json, glob, pathlib, collections
ROOT = pathlib.Path(__file__).resolve().parent.parent
dbp = os.environ.get('HADITH_DB', str(ROOT / 'data' / 'HadithMaster' / 'hadith_master.db'))
WRITE = '--db' in sys.argv
c = sqlite3.connect(('file:%s?mode=ro' % pathlib.Path(dbp).resolve().as_posix()) if not WRITE else pathlib.Path(dbp).resolve().as_posix(), uri=not WRITE)
DIAC = re.compile('[ً-ْٰـٓ-ٕ‏‎]')
def find_nd(text, surface, frm):
    """find `surface` in `text` at/after offset `frm`, ignoring diacritics; returns (start, end) in original text or None"""
    keep = [i for i, ch in enumerate(text) if not DIAC.match(ch)]
    plain = ''.join(text[i] for i in keep); target = DIAC.sub('', surface)
    pf = next((k for k, i in enumerate(keep) if i >= frm), len(keep))
    k = plain.find(target, pf)
    if k < 0: return None
    st = keep[k]; en = keep[k + len(target) - 1] + 1
    while en < len(text) and DIAC.match(text[en]): en += 1
    return st, en
blocks = collections.OrderedDict(); cur = None
for f in sorted(glob.glob(str(ROOT / 'gold' / 'edits' / '*.txt'))):
    for line in open(f, encoding='utf-8'):
        line = line.strip()
        if not line or line.startswith('#'): continue
        if line.startswith('@'): cur = line[1:].split()[0]; blocks[cur] = []; continue
        blocks[cur].append(line.split('#')[0].strip() if '|' not in line else line)
out = []; stats = collections.Counter(); problems = []
for hid, ops in blocks.items():
    text, tier, trad = c.execute('select text, chain_tier, tradition from hadith where id=?', (hid,)).fetchone()
    orig = [dict(pos=p, start=s, end=e, surface=t, narrator_id=n, method=m) for p, s, e, t, n, m in c.execute(
        'select pos,start,end,surface,narrator_id,id_method from chain_mention where hadith_id=? order by pos', (hid,))]
    byp = {o['pos']: o for o in orig}; ins = collections.defaultdict(list); removed = set(); unver = set(); edited = set()
    for op in ops:
        if op == 'ok': continue
        k, rest = op[0], op[1:]
        if k == '-': removed.add(int(rest)); stats['removed'] += 1
        elif k == '=': p, nid = rest.split('|'); byp[int(p)]['narrator_id'] = None if nid.strip() == '?' else nid.strip(); edited.add(int(p)); stats['id_changed'] += 1
        elif k == '~': unver.add(int(rest))
        elif k == '+': p, surf, nid = rest.split('|'); ins[int(p)].append((surf.strip(), None if nid.strip() == '?' else nid.strip())); stats['added'] += 1
        elif k == '^': p, surf = rest.split('|'); byp[int(p)]['new_surface'] = surf.strip(); stats['boundary_changed'] += 1
        else: problems.append((hid, 'bad op', op))
    final = []; cursor = 0
    def emit(surface, nid, src, verified, start=None, end=None):
        global cursor
        if start is None:
            r = find_nd(text, surface, cursor)
            if r is None: problems.append((hid, 'surface not found after offset', surface)); return
            start, end = r
        cursor = max(cursor, end)
        std = c.execute('select std_name from narrator where id=?', (nid,)).fetchone() if nid else None
        final.append(dict(surface=text[start:end], start=start, end=end, narrator_id=nid, narrator_name=std[0] if std else None, id_verified=verified, source=src))
    for p in [0] + sorted(byp):
        if p != 0 and p not in removed:
            o = byp[p]
            if 'new_surface' in o:
                r = find_nd(text, o['new_surface'], max(0, o['start'] - 40))
                if r is None: problems.append((hid, 'new surface not found', o['new_surface'])); continue
                emit(o['new_surface'], o['narrator_id'], 'edited', p not in unver, r[0], r[1])
            else: emit(o['surface'].strip() if False else text[o['start']:o['end']], o['narrator_id'], 'edited' if p in edited else 'kept', p not in unver, o['start'], o['end'])
        for surf, nid in ins.get(p, []): emit(surf, nid, 'added', True)
    for a, b in zip(final, final[1:]):
        if b['start'] < a['end']: problems.append((hid, 'overlap/out of order', a['surface'] + ' / ' + b['surface']))
    out.append(dict(hadith_id=hid, tradition=trad, tier=tier, text=text, mentions=final, n_original=len(orig), changed=bool(removed or ins or edited or any('new_surface' in o for o in orig))))
    stats['hadith'] += 1; stats['changed_hadith'] += out[-1]['changed']
(ROOT / 'gold').mkdir(exist_ok=True)
with open(ROOT / 'gold' / 'gold_chains.jsonl', 'w', encoding='utf-8') as f:
    for o in out: f.write(json.dumps(o, ensure_ascii=False) + '\n')
print(dict(stats), '| problems:', len(problems))
for p in problems[:20]: print('  PROBLEM', p)
if WRITE and not problems:
    n = 0
    for o in out:
        if not o['changed'] and all(m['id_verified'] for m in o['mentions']): c.execute("UPDATE chain_mention SET id_method='manual_gold', id_confidence=1.0 WHERE hadith_id=? AND narrator_id IS NOT NULL", (o['hadith_id'],)); continue
        c.execute('DELETE FROM chain_mention WHERE hadith_id=?', (o['hadith_id'],))
        for i, m in enumerate(o['mentions'], 1):
            c.execute('INSERT INTO chain_mention(hadith_id,pos,start,end,surface,narrator_id,id_method,id_confidence,id_source_ref,alternatives,flags) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                      (o['hadith_id'], i, m['start'], m['end'], m['surface'], m['narrator_id'], 'manual_gold' if m['id_verified'] and m['narrator_id'] else 'manual_gold_unverified_id', 1.0 if m['id_verified'] else 0.5, None, None, 'gold'))
        c.execute('UPDATE hadith SET n_narrators=?, flags=trim(coalesce(flags,"")||" gold_reviewed") WHERE id=?', (len(o['mentions']), o['hadith_id'])); n += 1
    c.commit(); print('database updated for', n, 'rewritten hadith')
