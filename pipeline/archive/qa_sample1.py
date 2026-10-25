import csv, random, ast, re, json
csv.field_size_limit(10**9); random.seed(20261007)
S=r'<ROOT>/Sanadset/'
rows=[]
with open(S+'sanadset.csv',encoding='utf-8',newline='') as f:
    r=csv.reader(f); next(r)
    for i,row in enumerate(r,2):
        if row[4].strip()!='No SANAD' and random.random()<0.00008: rows.append((i,row))
random.shuffle(rows); rows=rows[:30]
json.dump([i for i,_ in rows],open('qa1_ids.json','w'))
for i,row in rows:
    t=re.sub(r'\s+',' ',re.sub(r'</?(?:SANAD|MATN|NAR|IDF)>','',row[0])).strip()
    names=[re.sub(r'\s+',' ',re.sub(r'<[^>]*>','',n)).strip() for n in ast.literal_eval(row[4])]
    print(f'#{i} [{row[1][:22]}] len={row[5]}\n  TEXT : {t[:330]}\n  NAMES: {" ; ".join(names)[:260]}\n')
