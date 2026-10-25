import csv, re, pickle, collections, json, importlib.util, random
csv.field_size_limit(10**9); random.seed(12)
spec=importlib.util.spec_from_file_location('er','extend_rule.py'); er=importlib.util.module_from_spec(spec); spec.loader.exec_module(er)
sc=er.sc; N=er.N; crf=pickle.load(open('v4.pkl','rb'))
S=r'<ROOT>/Sanadset/'
# neighbours from the original file
orig=[]
with open(S+'sanadset.csv',encoding='utf-8',newline='') as f:
    r=csv.reader(f); next(r)
    for row in r: orig.append((row[1],int(row[2]) if row[2].isdigit() else -1,row[4].strip()=='No SANAD',row[3]))
rows=[]; tot=collections.Counter()
with open(S+'nosanad_parsed_v2.csv',encoding='utf-8-sig',newline='') as f:
    r=csv.reader(f); next(r)
    for x in r:
        tot[x[1]]+=1
        if x[8]=='no_chain': rows.append(x)
# rerun with the fixed rule
rest=[]; rescued=0
for s in range(0,len(rows),2000):
    ch=rows[s:s+2000]; tk=[sc.tokenize(x[3])[:sc.MAXTOK] for x in ch]
    labs=crf.predict([sc.tok_feats([t[0] for t in t_]) for t_ in tk])
    for x,t_,lab in zip(ch,tk,labs):
        lab=er.drop_prophet(t_,er.extend_labels(t_,list(lab)))
        if er.names_from(x[3],t_,lab): rescued+=1
        else: rest.append(x)
print('no_chain before:',len(rows),' rescued by fixed rule:',rescued,' still no chain:',len(rest))
bookshare={b:sum(1 for x in rest if x[1]==b)/tot[b] for b in tot}
BY_DESIGN={b for b in tot if sum(1 for x in rest if x[1]==b)>=30 and bookshare[b]>=0.6}
REF=re.compile(r'^(?:و|ف|ثم )?(?:باسناده|بإسناده|بهذا الاسناد|بهذا السند|به|بمثله|بنحوه|بمثل|بنحو|بالاسناد|بالاسناد المتقدم|بهذا|بسنده|بالسند|باسنادهم|باسناد)\b')
def cat(x):
    t=N(x[3]); w=t.split()
    if x[1] in BY_DESIGN: return '1 book without chains by design'
    first=' '.join(w[:3])
    if REF.match(w[0]) or re.match(r'^(حديث|وحديث|وفي حديث)\s*:?',t) and len(w)<400 and w[0].startswith('حديث'): return '2 referential opening (وبه / وبإسناده / حديث:)'
    if re.search(r'\b(حدثنا|حدثني|اخبرنا|اخبرني|ثنا|ثني|انبانا|نا|انا)\b',' '.join(w[8:]) if len(w)>8 else ''): return '4 chain verb later in text (trailing/embedded chain)'
    if re.match(r'^(ثم )?(قال|وقال|قلت|قالوا|فقال|وقلت|قالت)\b',t) : return '3 starts with a say-word (continuation fragment)'
    if t.startswith('"') or re.match(r'^(ان|وان|من|لا|ما|اذا|كان|كانت)\b',w[0]): return '5 starts directly with matn text'
    return '6 other'
C=collections.defaultdict(list)
for x in rest: C[cat(x)].append(x)
print('\nBY-DESIGN books:',sorted(BY_DESIGN, key=lambda b:-sum(1 for x in rest if x[1]==b))[:14])
for k in sorted(C): print(f'{k}: {len(C[k])}')
# neighbour test: is the previous row (same book) a row with a chain / is it itself no-SANAD?
def prev(x):
    i=int(x[0])-2
    if i<=0: return None
    b,n,ns,m=orig[i-1]
    return (b==x[1], n, ns)
print('\nNEIGHBOUR CHECK (previous row in original file):')
for k in sorted(C):
    if k.startswith('1'): continue
    st=collections.Counter()
    for x in C[k]:
        p=prev(x)
        if not p: st['no prev']+=1
        elif not p[0]: st['prev is another book']+=1
        elif p[2]: st['prev is also No SANAD']+=1
        else: st['prev has a chain']+=1
    print(' ',k,dict(st))
json.dump({k:[x[0] for x in v] for k,v in C.items()},open('nochain_cats.json','w'))
for k in sorted(C):
    print('\n=====',k)
    for x in random.sample(C[k],min(7,len(C[k]))): print(f'#{x[0]} [{x[1][:24]}] {x[3][:170]}')
