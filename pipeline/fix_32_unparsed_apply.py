"""Phase 2 - apply Claude's labels for the 457 chain_unparsed hadith (labels/unparsed_out): matn boundaries plus the narrator names the parser missed
(located in the text before the matn, inserted as chain_no 1 mentions, id only for a unique registry owner with >= 3 words; pos renumbered by start).
  python pipeline/fix_32_unparsed_apply.py pilot [N] [seed]  |  apply     (surgery_log step fix_32; flags claude_matn claude_parsed)"""
from paths import *
from labels_lib import load_labels, find, plain
import sqlite3, sys, json, glob, random, re, collections
MODE = sys.argv[1]; ARG = int(sys.argv[2]) if len(sys.argv) > 2 else None
DBP = OUT + 'hadith_master.db'
c = sqlite3.connect(DBP if MODE == 'apply' else 'file:' + DBP + '?mode=ro', timeout=120, uri=(MODE != 'apply'))
ids = {json.loads(l)['id'] for f in glob.glob('labels/unparsed_out/chunk_*.jsonl') for l in open(f, encoding='utf-8') if l.strip()}
texts = {h: t for h, t in c.execute('select id,text from hadith') if h in ids}
L = load_labels(['labels/unparsed_out'], texts)
gold = {json.loads(l)['hadith_id'] for l in open('gold/gold_chains.jsonl', encoding='utf-8')}
DIAC = re.compile('[ً-ْٰـٓ-ٕ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
norm = lambda s: re.sub(r'\s+', ' ', re.sub('[^ء-ي ]', ' ', DIAC.sub('', s or '').translate(TR))).strip()
res = {}; skip = collections.Counter()
for h, o in L.items():
    if h in gold: skip['gold'] += 1; continue
    text = texts[h]; ms, me = o['matn_start'], o['matn_end']
    ms0, me0, fl = c.execute('select matn_start,matn_end,flags from hadith where id=?', (h,)).fetchone()
    if o.get('chain_status') == 'no_sanad_in_source' and ms is None: ms = ms0
    if ms is None or me is None or me <= ms + 5: skip['matn_not_found'] += 1; ms, me = ms0, me0     # keep old boundaries, still take names
    old = c.execute('select start,end from chain_mention where hadith_id=? and start is not null and coalesce(chain_no,1)=1 order by start', (h,)).fetchall()
    lim = (ms if ms is not None else len(text)) + 3; new = []; pos = 0
    for nm in o.get('missed', []):
        r = find(text[:lim][pos:], nm)
        if not r: skip['missed_not_found'] += 1; continue
        a, b = pos + r[0], pos + r[1]; pos = b
        if any(a < y and b > x for x, y in old): skip['missed_overlap'] += 1; continue
        new.append((a, b))
    res[h] = (text, ms0, me0, ms, me, fl, new)
print('labels', len(L), 'hadith', len(res), 'new mentions', sum(len(v[6]) for v in res.values()), dict(skip))
if MODE == 'pilot':
    random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 1)
    for h in random.sample(list(res), min(ARG or 15, len(res))):
        text, ms0, me0, ms, me, fl, new = res[h]
        print(h, '| matn:', text[ms:ms + 60].replace('\n', ' '), '...', text[max(ms, me - 25):me].replace('\n', ' '), '| before:', text[max(0, ms - 40):ms].replace('\n', ' '), '| new:', [text[a:b] for a, b in new][:6])
else:
    exact = collections.defaultdict(set)
    for nid, nn in c.execute("select narrator_id,norm from narrator_name where norm is not null and type!='observed'"): exact[nn].add(nid)
    INS = 'INSERT INTO chain_mention(hadith_id,pos,start,end,surface,narrator_id,id_method,id_confidence,flags,chain_no,guess_narrator_id,guess_confidence) VALUES(?,?,?,?,?,?,?,?,?,1,?,?)'
    n = k = 0
    for h, (text, ms0, me0, ms, me, fl, new) in res.items():
        if (ms, me) != (ms0, me0):
            c.execute("insert into surgery_log(step,kind,key,old,new) values('fix_32','matn',?,?,?)", (h, json.dumps([ms0, me0]), json.dumps([ms, me])))
        for a, b in new:
            surf = text[a:b]; ow = sorted(exact.get(norm(surf)) or []); nid = gid = None; meth = 'claude_missed_unresolved'
            if len(ow) == 1 and len(norm(surf).split()) >= 3: nid, meth = ow[0], 'claude_missed_unique'
            elif ow: gid, meth = ow[0], 'claude_missed_candidates'
            cur = c.execute(INS, (h, 0, a, b, surf, nid, meth, 0.8 if nid else 0.0, 'claude_missed', gid, 0.3 if gid else None)); k += 1
            c.execute("insert into surgery_log(step,kind,key,old,new) values('fix_32','mention_inserted',?,?,?)", (cur.lastrowid, h, None))
        rows = c.execute('select rowid from chain_mention where hadith_id=? and coalesce(chain_no,1)=1 order by (start is null), start, pos', (h,)).fetchall()
        for p, (rid,) in enumerate(rows, 1): c.execute('update chain_mention set pos=? where rowid=?', (p, rid))
        c.execute('update hadith set matn_start=?,matn_end=?,flags=?,n_narrators=? where id=?', (ms, me, ((fl or '') + ' claude_matn claude_parsed').strip(), len(rows), h)); n += 1
    c.commit(); print('applied', n, 'mentions', k)
