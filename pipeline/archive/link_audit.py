import sys, pickle, random, collections, ast, csv
sys.path.insert(0,'<WORKDIR>')
sys.argv=['x']
import link_engine as E
from link_engine import *
csv.field_size_limit(10**9)
rows=[]
with open(r'<ROOT>/Sanadset/sanadset_linked.csv',encoding='utf-8-sig',newline='') as f:
    r=csv.reader(f); next(r)
    for x in r: rows.append((x[0],x[1],x[2],ast.literal_eval(x[4]),ast.literal_eval(x[5]),ast.literal_eval(x[6]),ast.literal_eval(x[7])))
# baseline: pairs where BOTH sides were 'unique' (no disambiguation involved)
uu=ue=0; cc=ce=0
for s,i,b,raw,ids,cf,mt in rows:
    for j in range(len(ids)-1):
        a,c=ids[j],ids[j+1]
        if a is None or c is None: continue
        e = (c in teach[a] or a in stud[c])
        if mt[j]=='unique' and mt[j+1]=='unique': uu+=1; ue+=e
        elif mt[j]=='context' and mt[j+1]=='context': cc+=1; ce+=e
print(f'unique->unique adjacent pairs: {uu}, known edge: {ue/uu:.1%}  (DB recall ceiling on never-ambiguous pairs)')
print(f'context->context adjacent pairs: {cc}, known edge: {ce/cc:.1%}')
def nm(c): return '∅' if c is None else f"{P[c]['full_name'][:30]}[{P[c]['grade_en'][:3]}{','+str(death[c]) if c in death else ''}]"
random.seed(99)
def sample(method,minconf,maxconf,n,label):
    pool=[(r_,j) for r_ in rows for j in range(len(r_[4])) if r_[6][j]==method and minconf<=r_[5][j]<=maxconf and len(r_[3][j])<40 ]
    print(f'\n######## {label}  (pool {len(pool)})')
    for r_,j in random.sample(pool,n):
        raw=[x[:18] for x in r_[3]]; mark=' | '.join(('>>'+x+'<<' if k==j else x) for k,x in enumerate(raw))
        print(' ',mark[:170]); print(f'      => {nm(r_[4][j])}  conf={r_[5][j]}  (prev: {nm(r_[4][j-1]) if j>0 else "-"} ; next: {nm(r_[4][j+1]) if j+1<len(r_[4]) else "-"})')
sample('context',0.85,1.0,9,'CONTEXT, high confidence')
sample('context',0.0,0.6,5,'CONTEXT, low confidence')
sample('prior_only',0.0,1.0,6,'PRIOR_ONLY (no chain evidence)')
sample('relative_father',0.0,1.0,4,'RELATIVE father resolution')
