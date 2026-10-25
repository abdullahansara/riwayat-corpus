import csv, random, ast, re, json
csv.field_size_limit(10**9); random.seed(777)
S=r'<ROOT>/Sanadset/'
used=set(json.load(open('sample_ids.json'))['eval']+json.load(open('sample_ids.json'))['train']+json.load(open('round2_ids.json')))
rows=[]
with open(S+'nosanad_parsed_v3.csv',encoding='utf-8-sig',newline='') as f:
    r=csv.reader(f); next(r)
    for x in r:
        if x[8]=='parsed' and x[9]=='model' and x[0] not in used and random.random()<0.0003: rows.append(x)
random.shuffle(rows); rows=rows[:30]
json.dump([x[0] for x in rows],open('qa2_ids.json','w'))
for x in rows:
    t=re.sub(r'\s+',' ',x[3]).strip()
    print(f'#{x[0]} [{x[1][:22]}]\n  TEXT : {t[:300]}\n  NAMES: {" ; ".join(ast.literal_eval(x[5]))[:240]}\n')
