import sys, ast, csv, collections, gc
sys.path.insert(0,'<WORKDIR>')
from link_lib import *
P=load_profiles()
nb={i:set(P[i].get('teachers') or [])|set(P[i].get('students') or []) for i in (120,1210)}
print({i:(P[i]['full_name'][:40],P[i].get('death')) for i in (120,1210,360,10)})
del P; gc.collect()
ch=collections.Counter(); meth=collections.Counter(); tot=0
w=csv.writer(open(S+'sanadset_linked_patched.csv','w',encoding='utf-8-sig',newline=''))
with open(S+'sanadset_linked.csv',encoding='utf-8-sig',newline='') as f:
    r=csv.reader(f); w.writerow(next(r))
    for x in r:
        raw=ast.literal_eval(x[4]); ids=ast.literal_eval(x[5]); cf=ast.literal_eval(x[6]); mt=ast.literal_eval(x[7]); dirty=False
        for j,n in enumerate(raw):
            k=norm2(n); old=ids[j]; new=None
            if k=='ابن عمر': new=120; c=0.85
            elif k=='عبد الله بن عمر':
                nbs=[ids[t] for t in (j-1,j+1) if 0<=t<len(ids) and ids[t] is not None]
                e120=any(t in nb[120] for t in nbs); e1210=any(t in nb[1210] for t in nbs)
                new=1210 if (e1210 and not e120) else 120; c=0.8 if (e120!=e1210) else 0.6
            elif k=='ابن عليه': new=360; c=0.85
            elif k=='ابو عبد الله الحافظ' and old==81151: new=10; c=0.85
            if new is not None and new!=old:
                ch[k]+=1; ids[j]=new; cf[j]=c; mt[j]='alias_patch'; dirty=True
        for m in mt: meth[m]+=1; tot+=1
        w.writerow([x[0],x[1],x[2],x[3],x[4],repr(ids) if dirty else x[5],repr(cf) if dirty else x[6],repr(mt) if dirty else x[7]])
print('mentions changed:',sum(ch.values()),dict(ch))
print('METHOD DISTRIBUTION (patched file):')
for k,v in meth.most_common(): print(f'  {k:24s} {v:9d} {v/tot:6.1%}')
