import sys, random, pickle, copy
sys.path.insert(0,'<WORKDIR>')
sys.argv=['x']
import link_engine as E
from link_engine import *
chains, keys, kc, klev = pickle.load(open('link_stage1.pkl','rb'))
random.seed(3); sub=random.sample(chains,150000)
def sim(cfg, label, n_test=4000, ndis=4, use_pairs=True):
    E.CFG.update(cfg)
    L=Linker(sub,keys,kc,klev); L.pass0()
    # distractor pool: keys by first token
    byfirst=collections.defaultdict(set)
    for k,cs in enumerate(kc):
        if cs and not isinstance(klev[k],str) and keys[k]: byfirst[keys[k].split()[0]].update(cs)
    clean=[ch for ch in sub if len(ch[4])>=3 and all(len(kc[k])==1 and klev[k]==0 for k in ch[4])]
    random.seed(5); test=random.sample(clean,min(n_test,len(clean))); tot=ok=base=0
    for ch in test:
        ck=ch[4]; true=[kc[k][0] for k in ck]
        own=collections.Counter(zip(true,true[1:])) if use_pairs else {}
        cl=[]; lp=[]
        for t,k in zip(true,ck):
            pool=[c for c in byfirst[keys[k].split()[0]] if c!=t]; random.shuffle(pool); pool=sorted(pool[:60],key=lambda c:-L.pop[c])[:ndis]
            cs=[t]+pool; w=np.array([L.pop[c] for c in cs]); cl.append(cs); lp.append(CFG['prior_w']*np.log(w/w.sum()))
        # decode with a temporary candidate table
        L_cl,L_lp=L.cl,L.lp
        L.cl=[None]*0; L.lp=[None]*0
        class Tmp: pass
        # inline forward-backward
        al=[lp[0]]; T=[]
        pair_backup=L.pair
        if not use_pairs: L.pair=collections.Counter()
        for i in range(len(ck)-1):
            M=np.array([[L.tp(x,y,own) for y in cl[i+1]] for x in cl[i]]); T.append(M); al.append(lp[i+1]+np.logaddexp.reduce(al[i][:,None]+M,axis=0))
        be=[None]*len(ck); be[-1]=np.zeros(len(cl[-1]))
        for i in range(len(ck)-2,-1,-1): be[i]=np.logaddexp.reduce(T[i]+(lp[i+1]+be[i+1])[None,:],axis=1)
        for i in range(len(ck)):
            z=al[i]+be[i]; tot+=1; ok+= (cl[i][int(z.argmax())]==true[i]); base+=(cl[i][int(np.argmax(lp[i]))]==true[i])
        L.cl,L.lp=L_cl,L_lp; L.pair=pair_backup
    print(f'{label:34s} prior-only acc {base/tot:.3f} -> with chain context {ok/tot:.3f}   ({tot} mentions, {ndis} distractors each)',flush=True)
sim(dict(edge=3.0,pairw=0.9),'full model')
sim(dict(edge=0.0,pairw=0.9),'no rijal edges (pairs only)')
sim(dict(edge=3.0,pairw=0.0),'no corpus pairs (edges only)')
sim(dict(edge=0.0,pairw=0.0),'death-year compat only')
