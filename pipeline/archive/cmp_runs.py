import sys, ast, csv, collections, gc
sys.path.insert(0,'<WORKDIR>')
from link_lib import *
P=load_profiles(); info={i:(p['full_name'][:30],len(p.get('namings') or []),len(p.get('teachers') or [])+len(p.get('students') or [])) for i,p in P.items()}; del P; gc.collect()
agree=both_diff=lost=gained=0; lostprof=collections.Counter(); lostkey=collections.Counter(); diffpair=collections.Counter(); lost_by_method=collections.Counter()
fa=open(S+'sanadset_linked_patched.csv',encoding='utf-8-sig',newline=''); fb=open(S+'sanadset_linked_v2.csv',encoding='utf-8-sig',newline='')
ra=csv.reader(fa); rb=csv.reader(fb); next(ra); next(rb)
for a,b in zip(ra,rb):
    assert a[1]==b[1]
    raw=ast.literal_eval(a[4]); ia=ast.literal_eval(a[5]); ib=ast.literal_eval(b[5]); ma=ast.literal_eval(a[7])
    for n,x,y,m in zip(raw,ia,ib,ma):
        if x==y: agree+=1
        elif x is not None and y is None: lost+=1; lostprof[x]+=1; lostkey[norm2(n)]+=1; lost_by_method[m]+=1
        elif x is None and y is not None: gained+=1
        else: both_diff+=1; diffpair[(x,y)]+=1
tot=agree+both_diff+lost+gained
print(f'mentions {tot}: agree {agree/tot:.1%} | linked before -> unmatched now {lost} ({lost/tot:.1%}) | unmatched before -> linked now {gained} | both linked but different {both_diff} ({both_diff/tot:.2%})')
print('lost, by v1 method:',dict(lost_by_method))
print('\nTop profiles that lost links (profile, #lost, variants, degree) and top lost keys:')
for p,c in lostprof.most_common(12): print(f'  {c:6d}  id {p} {info[p][0]}  variants={info[p][1]} deg={info[p][2]}')
print('top lost keys:',[(k,c) for k,c in lostkey.most_common(14)])
print('\nshare of lost mentions on profiles with >=30 variants (merged-variant profiles):',sum(c for p,c in lostprof.items() if info[p][1]>=30)/lost)
print('share on profiles with degree>=100:',sum(c for p,c in lostprof.items() if info[p][2]>=100)/lost)
print('\nboth linked but different, top pairs (v1 id -> v2 id):')
for (x,y),c in diffpair.most_common(8): print(f'  {c:6d}  {info[x][0]} (deg{info[x][2]})  ->  {info[y][0]} (deg{info[y][2]})')
