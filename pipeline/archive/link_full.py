import sys, pickle, time, csv, collections, math
sys.path.insert(0,'<WORKDIR>')
sys.argv=['x']
import link_engine as E
from link_engine import *
chains, keys, kc, klev = pickle.load(open('link_stage1.pkl','rb'))
t0=time.time(); L=Linker(chains,keys,kc,klev); L.pass0(); print('pass0 pairs',len(L.pair),round(time.time()-t0),'s',flush=True)
res,newpair,own_new,mention=L.run(); print('pass1 done',round(time.time()-t0),'s; confident pairs',len(newpair),flush=True)
L.update(newpair,own_new,mention); res,newpair2,own2,mention2=L.run(); print('pass2 done',round(time.time()-t0),'s',flush=True)
FATHER={'ابيه','ابوه','اباه','ابي','ابيها','ابوها','ابيهم','ابا'}
def father_of(x):
    t=fullkey[x].split()
    if 'بن' in t[:-1]:
        j=t.index('بن'); return t[j+1]
    return None
S=r'<ROOT>/Sanadset/'
w=csv.writer(open(S+'sanadset_linked.csv','w',encoding='utf-8-sig',newline=''))
w.writerow(['source','src_row','Book','Num_hadith','Narrators_raw','Rijal_ids','Link_conf','Link_method'])
meth=collections.Counter(); links=0; edges=0; pairs_all=0
for ch,out in zip(chains,res):
    ids=[];cf=[];mt=[]
    for i,(k,(c,conf,ev)) in enumerate(zip(ch[4],out)):
        lev=klev[k]; n=len(L.cl[k])
        if lev=='anon': ids.append(None);cf.append(0);mt.append('anonymous')
        elif lev=='rel':
            m='relative_unresolved'; cid=None; cc=0
            if i>0 and keys[k] in FATHER and out[i-1][0] is not None and out[i-1][1]>=0.5:
                x=out[i-1][0]; fn=father_of(x)
                if fn:
                    ms=[t for t in teach[x] if t in P and fullkey[t].split()[:1]==[fn]]
                    if len(ms)==1: cid,cc,m=ms[0],0.9,'relative_father'
            ids.append(cid);cf.append(cc);mt.append(m)
        elif c is None: ids.append(None);cf.append(0);mt.append('unmatched')
        else:
            ids.append(c);cf.append(round(conf,3))
            m=('unique' if n==1 else 'context' if ev else 'prior_only')
            if lev not in (0,) and n>=1: m+='+backoff'
            mt.append(m)
        meth[mt[-1]]+=1
    for a,b in zip(ids,ids[1:]):
        if a is not None and b is not None:
            pairs_all+=1; edges+= (b in teach[a] or a in stud[b])
    w.writerow([ch[0],ch[1],ch[2],ch[3],repr(ch[5]),repr(ids),repr(cf),repr(mt)])
tot=sum(meth.values()); print('\nMETHODS:'); 
for k,v in meth.most_common(): print(f'  {k:28s} {v:9d} {v/tot:6.1%}')
print('adjacent resolved pairs',pairs_all,'that are known rijal teacher/student edges:',f'{edges/pairs_all:.1%}')
pickle.dump((res,),open('link_results.pkl','wb')); print('done',round(time.time()-t0),'s')
