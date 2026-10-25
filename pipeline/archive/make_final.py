import sys, ast, csv, collections, gc
sys.path.insert(0,'<WORKDIR>')
from link_lib import *
WEAK={'prior_only','prior_only+backoff'}
st=collections.Counter(); meth=collections.Counter(); freq=collections.Counter(); chosen=collections.defaultdict(collections.Counter)
fa=open(S+'sanadset_linked_patched.csv',encoding='utf-8-sig',newline=''); fb=open(S+'sanadset_linked_v2.csv',encoding='utf-8-sig',newline='')
ra=csv.reader(fa); rb=csv.reader(fb); h=next(ra); next(rb)
w=csv.writer(open(S+'sanadset_linked_final.csv','w',encoding='utf-8-sig',newline='')); w.writerow(h)
for a,b in zip(ra,rb):
    raw=ast.literal_eval(a[4]); ia=ast.literal_eval(a[5]); ca=ast.literal_eval(a[6]); ma=ast.literal_eval(a[7])
    ib=ast.literal_eval(b[5]); cb=ast.literal_eval(b[6]); mb=ast.literal_eval(b[7])
    oi=[];oc=[];om=[]
    for n,x,cx,mx,y,cy,my in zip(raw,ia,ca,ma,ib,cb,mb):
        if x==y: i,c,m=x,cx,mx; st['agree']+=1
        elif x is not None and y is None:
            if mx in WEAK: i,c,m=None,0,'unmatched_weak_dropped'; st['dropped_weak']+=1
            else: i,c,m=x,cx,mx; st['kept_run1_link']+=1
        elif x is None and y is not None: i,c,m=y,cy,my; st['took_run2_link']+=1
        else:
            if cy>cx: i,c,m=y,cy,my; st['disagree->run2']+=1
            else: i,c,m=x,cx,mx; st['disagree->run1']+=1
        oi.append(i);oc.append(c);om.append(m); meth[m]+=1
        k=norm2(n); freq[k]+=1; chosen[k][i]+=1
    w.writerow([a[0],a[1],a[2],a[3],a[4],repr(oi),repr(oc),repr(om)])
tot=sum(meth.values()); print('RECONCILIATION:',dict(st)); print('\nFINAL METHOD DISTRIBUTION:')
for k,v in meth.most_common(): print(f'  {k:26s} {v:9d} {v/tot:6.1%}')
linked=sum(v for k,v in meth.items() if k not in ('unmatched','unmatched_weak_dropped','anonymous','relative_unresolved'))
print(f'\nmentions with a profile link: {linked} ({linked/tot:.1%})')
import json; json.dump({k:{str(i):c for i,c in v.most_common(3)} for k,v in ((k,chosen[k]) for k,_ in freq.most_common(300))},open('final_top_keys.json','w'),ensure_ascii=False)
