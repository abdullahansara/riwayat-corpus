import sys, random, pickle
sys.path.insert(0,'<WORKDIR>')
sys.argv=['x']
from link_engine import *
chains, keys, kc, klev = pickle.load(open('link_stage1.pkl','rb'))
random.seed(7); sub=random.sample(chains,30000)
L=Linker(sub,keys,kc,klev); L.pass0()
res,newpair,own_new,mention=L.run(); L.update(newpair,own_new,mention); res2,_,_,_=L.run()
def nm(c): return '∅' if c is None else f"{P[c]['full_name'][:34]}[{P[c]['grade_en'][:4]}{','+str(death[c]) if c in death else ''}]"
random.seed(11); shown=0
targets=['سفيان','حماد','مالك','شعبه','ابن جريج','يحيي','عبد الله بن محمد','محمد بن عبد الله','ابو بكر','سليمان','ابراهيم','حسن']
for t in targets:
    pool=[(ch,out,i) for ch,out in zip(sub,res2) for i,k in enumerate(ch[4]) if L.keys[k]==t and len(L.cl[k])>1]
    print(f'\n##### "{t}"  ({len(pool)} ambiguous mentions in sample; candidates {len(L.cl[pool[0][0][4][pool[0][2]]]) if pool else 0})')
    for ch,out,i in random.sample(pool,min(3,len(pool))):
        raws=[n[:22] for n in ch[5]]
        print('  chain:',' ← '.join(raws)[:150])
        print(f'     -> {nm(out[i][0])}  conf={out[i][1]:.2f}   | prev: {nm(out[i-1][0]) if i>0 else "-"} | next: {nm(out[i+1][0]) if i+1<len(out) else "-"}')
