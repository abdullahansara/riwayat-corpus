"""Add narrator mentions that the joint tagger (labels/joint_pred.db spans) finds in the chain but no existing mention covers.
  python pipeline/fix_36_joint_names.py pilot [N] [seed]  |  apply
A span is used when its minimum token probability >= SPAN_P, it lies before matn_start (+3), has 1-8 words, no verb-ish word, does not end in a head word (ابو, بن ...),
does not overlap an existing chain_no 1 mention.  IDs as fix_24 (asserted only for a unique owner with >= 3 words).  Gold never changes. Flags: joint_names; mentions flag joint_tagger."""
from paths import *
from labels_lib import plain
from fix_24_gap_apply import HEAD, VERBISH
from boundary_metric import CONN
import sqlite3, sys, re, json, random, collections
MODE = sys.argv[1]; ARG = int(sys.argv[2]) if len(sys.argv) > 2 else None
SPAN_P = 0.9; DBP = OUT + 'hadith_master.db'; PRED = 'labels/joint_pred.db'
db = sqlite3.connect(DBP if MODE == 'apply' else 'file:' + DBP + '?mode=ro', timeout=120, uri=(MODE != 'apply')); c = db.cursor(); p = sqlite3.connect(PRED)
gold = {json.loads(l)['hadith_id'] for l in open('gold/gold_chains.jsonl', encoding='utf-8')}
prop = {}; skip = collections.Counter()
for h, js in p.execute('select hadith_id,spans from pred'):
    if h in gold: continue
    sp = json.loads(js)
    if not sp: continue
    text, ms, fl = c.execute('select text,matn_start,flags from hadith where id=?', (h,)).fetchone()
    if ms is None: continue
    ments = c.execute('select start,end from chain_mention where hadith_id=? and start is not null and coalesce(chain_no,1)=1', (h,)).fetchall()
    out = []
    for a, b, mp in sp:
        if mp < SPAN_P or b > ms + 3: continue
        w = plain(text[a:b])[0].split()
        if not w or len(w) > 8: skip['len'] += 1; continue
        if any(x in VERBISH for x in w) or all(x.lstrip('و') in CONN or x in CONN for x in w): skip['verbish'] += 1; continue
        if re.search(r'[A-Z]\d+|\d', text[a:b]): skip['digits'] += 1; continue
        if w[-1] in HEAD or w[0] == 'بن': skip['head'] += 1; continue
        if any(x < b and a < y for x, y in ments): continue
        out.append((a, b))
    if out: prop[h] = (text, fl, out)
print('hadith', len(prop), 'new mentions', sum(len(v[2]) for v in prop.values()), dict(skip))
if MODE == 'pilot':
    random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 1); n = 0
    for h in random.sample(list(prop), min(ARG or 40, len(prop))):
        text, fl, out = prop[h]; a, b = out[0]
        print(h, '|', text[max(0, a - 40):a].replace('\n', ' '), '[[', text[a:b], ']]', text[b:b + 25].replace('\n', ' '))
else:
    DIAC = re.compile('[ً-ْٰـٓ-ٕ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
    norm = lambda s: re.sub(r'\s+', ' ', re.sub('[^ء-ي ]', ' ', DIAC.sub('', s or '').translate(TR))).strip()
    exact = collections.defaultdict(set)
    for nid, nn in c.execute("select narrator_id,norm from narrator_name where norm is not null and type!='observed'"): exact[nn].add(nid)
    pop = dict(c.execute('select narrator_id,count(*) from chain_mention where narrator_id is not null group by 1'))
    REL = set('ابي ابيه ابوه اباه جدي جده عمي عمه خالي خالتي امه امي اخي اخيه ابنه ابني'.split())
    INS = 'INSERT INTO chain_mention(hadith_id,pos,start,end,surface,narrator_id,id_method,id_confidence,flags,chain_no,guess_narrator_id,guess_confidence) VALUES(?,?,?,?,?,?,?,?,?,1,?,?)'
    n_h = n_m = 0
    for h, (text, fl, out) in prop.items():
        if 'joint_names' in (fl or '').split(): continue
        rows = c.execute('select rowid,pos,start,end,chain_no from chain_mention where hadith_id=?', (h,)).fetchall()
        if any(r[2] is None for r in rows if (r[4] or 1) == 1): continue
        c.execute("INSERT INTO surgery_log(step,kind,key,old,new) VALUES('fix_36','positions',?,?,NULL)", (h, json.dumps({r[0]: r[1] for r in rows})))
        for a, b in out:
            surf = text[a:b]; name = norm(surf); nid = gid = None; meth = 'joint_unresolved'
            if name in REL: meth = 'joint_relative_unresolved'
            else:
                ow = sorted(exact.get(name) or exact.get(re.sub(r'^و(?=[ء-ي]{3})', '', name)) or [], key=lambda x: -pop.get(x, 0))
                if len(ow) == 1 and len(name.split()) >= 3: nid, meth = ow[0], 'joint_unique'
                elif len(ow) == 1 or (ow and pop.get(ow[0], 0) >= 3 * pop.get(ow[1], 0)): gid, meth = ow[0], 'joint_candidates'
            cur = c.execute(INS, (h, 900000, a, b, surf, nid, meth, 0.8 if nid else 0.0, 'joint_tagger', gid, 0.3 if gid else None)); n_m += 1
        main = [r[0] for r in c.execute('select rowid from chain_mention where hadith_id=? and coalesce(chain_no,1)=1 order by start', (h,))]
        c.execute('update chain_mention set pos=pos+100000 where hadith_id=? and coalesce(chain_no,1)=1', (h,))
        c.executemany('update chain_mention set pos=? where rowid=?', [(i + 1, rid) for i, rid in enumerate(main)])
        c.execute('update hadith set flags=?, n_narrators=(select count(*) from chain_mention where hadith_id=?) where id=?', (((fl or '') + ' joint_names').strip(), h, h)); n_h += 1
        if n_h % 5000 == 0: db.commit(); print(n_h, n_m, flush=True)
    db.commit(); print('done: hadith', n_h, 'mentions added', n_m)
