"""Surgery step 16 - validate narrator IDs against the surface text (a surface and its narrator must share a content word).
Found by eye: one hub narrator (N0000600, Ibn Abbas) had absorbed observed name forms of unrelated narrators (علي, عائشة, مجاهد, الأعمش ...),
so it was the weak guess for 74K mentions, and some linker/graph IDs contradicted their own surface (عثمان بن عفان -> مالك بن أنس).
  A  delete observed name forms (count < 30) that share no content word with any registry form of their narrator (23K, logged in purged_name_form)
  B  weak guesses that contradict the surface: replace by a compatible alternative, else the most popular narrator whose registry form equals the surface, else NULL
  C  asserted IDs from the weaker methods that contradict a real name surface are demoted to weak guesses (id_method 'demoted:<old method>')
  python pipeline/fix_16_validate_ids.py pilot | apply"""
import sys, os, random, collections, re, json, sqlite3
from paths import *
c = sqlite3.connect(OUT + 'hadith_master.db', timeout=120)
DIAC = re.compile('[ً-ْٰـٓ-ٕ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def norm(s): return re.sub(r'\s+', ' ', re.sub('[^ء-ي ]', ' ', DIAC.sub('', s or '').translate(TR))).strip()
STOP={'ابن','بن','ابو','ابي','ابا','ابيه','ابوه','جده','عن','بنت','ام','الله','عبد','محمد','احمد','قال','حدثنا'}
def toks(s):
    out=set()
    for w in s.split():
        vs={w}
        if re.match(r'^[وفبلك][ء-ي]{3,}',w): vs.add(w[1:])
        for v in list(vs):
            if v.startswith('ال') and len(v)>4: vs.add(v[2:])
        for v in list(vs):
            if len(v)>3 and v.endswith('ا'): vs.add(v[:-1])
        out|=vs
    return out
reg=collections.defaultdict(set)
for nid,nn in c.execute("select narrator_id,norm from narrator_name where norm is not null and type!='observed'"): reg[nid]|=toks(nn)
for nid,nm in c.execute('select id,std_name from narrator'): reg[nid]|=toks(norm(nm))
def ok(surf,nid):
    t=toks(norm(surf))-STOP
    if not t: return None        # generic word (relative, kunya-only): cannot judge
    return bool(t&(reg[nid]-STOP))
exact=collections.defaultdict(set)
for nid,nn in c.execute("select narrator_id,norm from narrator_name where norm is not null and type!='observed'"): exact[nn].add(nid)
pop=dict(c.execute('select narrator_id,count(*) from chain_mention where narrator_id is not null group by 1'))
def fallback(s):
    n=norm(s); n=re.sub(r'^و(?=[ء-ي]{3})','',n)
    cand=exact.get(n) or exact.get(re.sub(r'^(?:ابن|بن) ','',n)) or ()
    cand=sorted(cand,key=lambda x:-pop.get(x,0))
    return cand[0] if cand and (len(cand)==1 or pop.get(cand[0],0)>=3*pop.get(cand[1],0)) else None

MODE = sys.argv[1] if len(sys.argv) > 1 else 'pilot'
exact = collections.defaultdict(set)
for nid, nn in c.execute("select narrator_id,norm from narrator_name where norm is not null and type!='observed'"): exact[nn].add(nid)
pop = dict(c.execute('select narrator_id,count(*) from chain_mention where narrator_id is not null group by 1'))
def fallback(s):
    n = norm(s); n = re.sub(r'^و(?=[ء-ي]{3})', '', n)
    cand = exact.get(n) or exact.get(re.sub(r'^(?:ابن|بن) ', '', n)) or ()
    cand = sorted(cand, key=lambda x: -pop.get(x, 0))
    return cand[0] if cand and (len(cand) == 1 or pop.get(cand[0], 0) >= 3 * pop.get(cand[1], 0)) else None
def best(s, alts):
    for a in json.loads(alts or '[]'):
        if ok(s, a): return a
    return fallback(s)
# A  observed forms
bad = []
for rid, nid, nn, cnt in c.execute("select rowid,narrator_id,norm,observed_count from narrator_name where type='observed' and norm is not null and observed_count<30"):
    t = toks(nn) - STOP
    if (t and not (t & (reg[nid] - STOP))) or (not t and not (toks(nn) & reg[nid])): bad.append(rid)
print('A observed forms to delete (judged against registry forms):', len(bad))
# B weak guesses
B = []
for rid, s, g, alts in c.execute("select rowid,surface,guess_narrator_id,alternatives from chain_mention where id_method='candidates_only' and surface is not null"):
    if ok(s, g) is False: B.append((rid, g, best(s, alts)))
print('B contradicting weak guesses:', len(B), '| replaced', sum(1 for x in B if x[2]))
# C weak-method assertions that contradict the surface
WEAK = ('linker_context', 'linker_unique', 'linker_context+backoff', 'linker_unique+backoff', 'linker_alias_patch', 'name_plus_graph_edges', 'name_lookup_unique_v2')
C = []
for rid, s, n, m, alts in c.execute("select rowid,surface,narrator_id,id_method,alternatives from chain_mention where narrator_id is not null and narrator_id!='N0003708' and surface is not null and chain_no=1"):
    if m in WEAK and ok(s, n) is False: C.append((rid, n, m, best(s, alts)))
print('C contradicting asserted IDs to demote:', len(C), collections.Counter(x[2] for x in C).most_common(4))
if MODE == 'pilot':
    nm = dict(c.execute('select id,std_name from narrator')); random.seed(2)
    for rid, n, m, new in random.sample(C, 25): print('  ', c.execute('select surface from chain_mention where rowid=?', (rid,)).fetchone()[0][:36], '|', nm[n][:30], '->', (nm.get(new) or '-')[:30])
elif MODE == 'apply':
    c.executemany('INSERT INTO purged_name_form SELECT narrator_id, form, norm, observed_count FROM narrator_name WHERE rowid=?', [(r,) for r in bad])
    c.executemany("INSERT INTO surgery_log(step,kind,key,old,new) SELECT 'fix_16','delete_name_form',narrator_id,form,NULL FROM narrator_name WHERE rowid=?", [(r,) for r in bad])
    c.executemany('DELETE FROM narrator_name WHERE rowid=?', [(r,) for r in bad])
    c.executemany("INSERT INTO surgery_log(step,kind,key,old,new) VALUES('fix_16','guess_narrator_id',?,?,?)", B)
    c.executemany('UPDATE chain_mention SET guess_narrator_id=?, guess_confidence=CASE WHEN ? IS NULL THEN NULL ELSE 0.3 END WHERE rowid=?', [(n, n, r) for r, g, n in B])
    c.executemany("INSERT INTO surgery_log(step,kind,key,old,new) VALUES('fix_16','demote_narrator_id',?,?,?)", [(r, n + '|' + m, new) for r, n, m, new in C])
    c.executemany("UPDATE chain_mention SET narrator_id=NULL, guess_narrator_id=?, guess_confidence=CASE WHEN ? IS NULL THEN NULL ELSE 0.3 END, id_method='demoted:'||id_method, id_confidence=0 WHERE rowid=?", [(new, new, r) for r, n, m, new in C])
    c.commit(); print('applied')
