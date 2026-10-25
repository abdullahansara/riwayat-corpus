import sys, csv, random, ast, gc, json
sys.path.insert(0,'<WORKDIR>')
from link_lib import *
random.seed(4242)
P=load_profiles(); info={i:(p['full_name'][:42],p.get('kunya'),str(p.get('death') or '')[:14],p['grade_en'][:4]) for i,p in P.items()}; del P; gc.collect()
want={'unique':12,'context':14,'prior_only':10}; pools=collections.defaultdict(list) if False else {}
import collections
pools=collections.defaultdict(list)
with open(S+'hadith_unified.csv',encoding='utf-8-sig',newline='') as f:
    r=csv.reader(f); next(r)
    for x in r:
        if x[9]=='none' or not x[4] or random.random()>0.02: continue
        names=ast.literal_eval(x[4]); ids=ast.literal_eval(x[6]); cf=ast.literal_eval(x[7]); mt=ast.literal_eval(x[8])
        for j,m in enumerate(mt):
            if m in want and ids[j] is not None and len(pools[m])<4000: pools[m].append((x[0],x[1],names,ids,cf,mt,j))
out=[]
for m,k in want.items():
    for item in random.sample(pools[m],k): out.append(item)
json.dump([(o[0],o[6]) for o in out],open('qa3_items.json','w'))
for rid,book,names,ids,cf,mt,j in out:
    ctx=' | '.join(('>>'+n[:20]+'<<' if k==j else n[:14]) for k,n in enumerate(names))
    p=info[ids[j]]
    print(f'#{rid} [{book[:18]}] {mt[j]} conf={cf[j]}\n  CHAIN : {ctx[:210]}\n  LINKED: {p[0]} | kunya={p[1]} | d={p[2]} | {p[3]}\n')
