from paths import *
import json, collections
src=open('fix_muslim_ids.py',encoding='utf-8').read()
exec(compile(src[:src.index("validate('BEFORE merging duplicates')")],'fm','exec'))
mm=src_map('mids')
srcs=collections.defaultdict(set)
for nid,s in c.execute('select narrator_id, source from narrator_source_id'): srcs[nid].add(s)
std=dict(c.execute('select id,std_name from narrator'))
def toks(n): return nk(std.get(n,'')).split()
def related(a,b):
    x,y=toks(a),toks(b)
    if len(x)<2 or len(y)<2: return False
    s,l=(x,y) if len(x)<=len(y) else (y,x)
    return l[:len(s)]==s
votes=collections.Counter()
for num,unit,kid in triples:
    hid=kg2h.get(kid)
    if not hid: continue
    O={r[0] for r in c.execute('select narrator_id from chain_mention where hadith_id=? and narrator_id is not null',(hid,))}
    M={mm.get(i) for i in mp.get(unit,set())}; M.discard(None)
    do,dm=sorted(O-M),sorted(M-O)
    if len(do)==1 and len(dm)==1: votes[(dm[0],do[0])]+=1
log('1-1 candidate pairs',len(votes))
tgt=collections.defaultdict(set)
for (a,b) in votes: tgt[a].add(b)
merges={}
for (a,b),n in votes.items():
    if len(tgt[a])>1 or srcs[a]!={'mids'} or 'mids' in srcs[b] or not related(a,b): continue
    merges[a]=b
log('safe prefix-name merges',len(merges))
c.executescript('CREATE TABLE IF NOT EXISTS narrator_merge(old_id TEXT PRIMARY KEY, new_id TEXT, reason TEXT, jaccard REAL, n_hadith INT);')
for a,b in merges.items():
    c.execute('INSERT OR REPLACE INTO narrator_merge VALUES(?,?,?,?,?)',(a,b,'MIDS-only id; name is token-prefix variant of chain id; 1-1 difference on clean Muslim hadith',None,votes[(a,b)]))
    for t in ('chain_mention','narrator_name','narrator_source_id'): c.execute(f'UPDATE {t} SET narrator_id=? WHERE narrator_id=?',(b,a))
    old=c.execute('select death_year,birth_year,tabaqa,city from narrator where id=?',(a,)).fetchone()
    if old:
        for col,v in zip(('death_year','birth_year','tabaqa','city'),old):
            if v is not None: c.execute(f'UPDATE narrator SET {col}=? WHERE id=? AND {col} IS NULL',(v,b))
    c.execute('UPDATE narrator SET n_sources=(select count(distinct source) from narrator_source_id where narrator_id=?) WHERE id=?',(b,b))
    c.execute('DELETE FROM narrator WHERE id=?',(a,))
db.commit()
fixed=0
for rid,ids in c.execute('select rowid, narrator_ids from reference_chain').fetchall():
    L=json.loads(ids)
    if any(x in merges for x in L): c.execute('UPDATE reference_chain SET narrator_ids=? WHERE rowid=?',(json.dumps([merges.get(x,x) for x in L]),rid)); fixed+=1
db.commit(); log('reference chains updated',fixed)
validate('AFTER prefix merges')
log('narrators now',c.execute('select count(*) from narrator').fetchone()[0])
