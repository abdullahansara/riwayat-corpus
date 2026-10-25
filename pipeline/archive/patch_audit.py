import sys, ast, csv, collections, gc
sys.path.insert(0,'<WORKDIR>')
from link_lib import *
P=load_profiles()
info={i:(p['full_name'][:34],p['grade_en'][:3],len(p.get('teachers') or [])+len(p.get('students') or [])) for i,p in P.items()}
del P; gc.collect()
tally=collections.defaultdict(collections.Counter); freq=collections.Counter()
with open(S+'sanadset_linked.csv',encoding='utf-8-sig',newline='') as f:
    r=csv.reader(f); next(r)
    for x in r:
        raw=ast.literal_eval(x[4]); ids=ast.literal_eval(x[5])
        for n,i in zip(raw,ids):
            k=norm2(n)
            if k.startswith('ابن ') and len(k.split())==2 or k in ('عبد الله بن عمر','عبد الله بن عباس','عبد الله بن مسعود','عبد الله بن عمرو','ابو العباس محمد بن يعقوب','ابو عبد الله الحافظ'):
                tally[k][i]+=1; freq[k]+=1
print('single-word "ابن X" keys, top 30 by frequency -> chosen profile (share):')
for k,n in freq.most_common(30):
    t=tally[k].most_common(2); f=lambda c:'∅' if c is None else f"{c}:{info[c][0]}[{info[c][1]},deg{info[c][2]}]"
    print(f'{k:22s} {n:6d} | {f(t[0][0])} {t[0][1]/n:4.0%}'+(f' | {f(t[1][0])} {t[1][1]/n:.0%}' if len(t)>1 else ''))
