"""Surgery step 18 - resolve ambiguous names without ID using the neighbours in the chain.
A mention with no ID/guess whose surface equals a registry name form of several narrators gets the candidate that has the most
narrator_edge links to the asserted previous/next narrator of the same chain (min 3 hadith, >=5x the runner-up), provided the surface shares
a content word with the candidate's standard name (kunya surfaces 'ابو ..' are exempt from that test).
Asserted (id_method 'edge_context') when score>=10, ratio>=10 and the surface is not a kunya; otherwise only a weak guess.
Every change is logged in surgery_log (step fix_18, kind mention).  python pipeline/fix_18_edge_context.py [pilot|apply]"""
from paths import *
import sqlite3, sys, re, collections, json
MODE = sys.argv[1] if len(sys.argv) > 1 else 'pilot'
db = sqlite3.connect(OUT + 'hadith_master.db', timeout=120); c = db.cursor()
DIAC = re.compile('[ً-ْٰـٓ-ٕ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def norm(s): return re.sub(r'\s+', ' ', re.sub('[^ء-ي ]', ' ', DIAC.sub('', s or '').translate(TR))).strip()
exact = collections.defaultdict(set)
for n, f in c.execute("select narrator_id,norm from narrator_name where norm is not null and type!='observed'"): exact[f].add(n)
edge = {(s, t): n for s, t, n in c.execute('select student,teacher,n_hadith from narrator_edge')}
names = dict(c.execute('select id,std_name from narrator'))
STOP = ('ابن', 'بن', 'ابو', 'ابي', 'عبد', 'الله')
def decide(prev, nxt, surf):
    sn = norm(surf); ow = exact.get(sn) or set()
    if len(ow) < 2: return None
    kun = sn.startswith(('ابو ', 'ابي ', 'ابا '))
    toks = [w for w in sn.split() if w not in STOP]
    def compat(o):
        n = set(norm(names[o]).split()); n |= {w[2:] for w in n if w.startswith('ال')}
        return kun or any(w in n or (w[2:] if w.startswith('ال') else w) in n or w.lstrip('و') in n for w in toks)
    sc = {o: (edge.get((prev, o), 0) if prev else 0) + (edge.get((o, nxt), 0) if nxt else 0) for o in ow if compat(o)}
    if not sc: return None
    r = sorted(sc.items(), key=lambda x: -x[1]); s1 = r[0][1]; s2 = r[1][1] if len(r) > 1 else 0
    if s1 < 3 or s1 < 5 * max(1, s2): return None
    return r[0][0], (s1 >= 10 and s1 >= 10 * max(1, s2) and not kun)
rows = c.execute("select rowid,hadith_id,pos,coalesce(chain_no,1),surface,id_method from chain_mention where narrator_id is null and guess_narrator_id is null and surface is not null").fetchall()
print('candidates', len(rows), flush=True)
nA = nG = 0; shown = 0
for k, (rid, h, p, cn, s, meth) in enumerate(rows):
    pv = c.execute('select narrator_id from chain_mention where hadith_id=? and coalesce(chain_no,1)=? and pos=?', (h, cn, p - 1)).fetchone()
    nx = c.execute('select narrator_id from chain_mention where hadith_id=? and coalesce(chain_no,1)=? and pos=?', (h, cn, p + 1)).fetchone()
    d = decide(pv[0] if pv else None, nx[0] if nx else None, s)
    if not d: continue
    nid, assert_ = d
    if MODE == 'pilot':
        if shown < 40 and k % 7 == 0: shown += 1; print(h, p, s, '->', nid, names[nid][:40], 'ASSERT' if assert_ else 'guess')
        nA += assert_; nG += not assert_; continue
    c.execute("INSERT INTO surgery_log(step,kind,key,old,new) VALUES('fix_18','mention',?,?,?)", (rid, meth, nid))
    if assert_: c.execute("update chain_mention set narrator_id=?, id_method='edge_context', id_confidence=0.7 where rowid=?", (nid, rid)); nA += 1
    else: c.execute("update chain_mention set guess_narrator_id=?, guess_confidence=0.4, id_method=case when id_method like 'demoted:%' then id_method else 'candidates_only' end where rowid=?", (nid, rid)); nG += 1
    if (nA + nG) % 5000 == 0: db.commit()
db.commit(); print('asserted', nA, 'guessed', nG)
