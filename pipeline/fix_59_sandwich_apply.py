"""Apply sandwich transfers (labels/sandwich.json 'transfer') with gates.
Gate: mention still unresolved (narrator_id NULL), proposal unambiguous (one candidate id), no chronology conflict with identified neighbours (fix_55 rule), inside the chain (not in matn), and
  EITHER >= 2 parallel votes  OR 1 vote with a non-bare surface (>= 2 content tokens besides الله/عبد-only names) whose tokens are all contained in the candidate's name forms.
  python pipeline/fix_59_sandwich_apply.py cand   -> labels/sandwich_cand.json + labels/sandwich_review.jsonl (sample for an independent reviewer)
  python pipeline/fix_59_sandwich_apply.py apply [verdict.json]  -> writes narrator_id (id_method 'sandwich'), logs old values in surgery_log (step fix_59)"""
from paths import *
import sqlite3, sys, json, re, random, collections
MODE = sys.argv[1]
DBP = OUT + 'hadith_master.db'
db = sqlite3.connect(DBP if MODE == 'apply' else 'file:' + DBP + '?mode=ro', timeout=300, uri=(MODE != 'apply')); c = db.cursor()
DIAC = re.compile('[ً-ْٰـٓ-ٕ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def toks(s): return [t[2:] if t.startswith('ال') and len(t) > 4 else t for t in re.sub('[^ء-ي ]', ' ', DIAC.sub('', s or '').translate(TR)).split() if t not in ('بن', 'ابن', 'ابي', 'ابو')]
death = dict(c.execute('select id,death_year from narrator where death_year is not null'))
def conf(nid, prev, nxt):
    dc = death.get(nid)
    if not dc: return False
    return bool((prev and (dc > prev + 15 or dc < prev - 80)) or (nxt and (dc < nxt - 5 or dc > nxt + 100)))
d = json.load(open('labels/sandwich.json'))['transfer']
names = dict(c.execute('select id,std_name from narrator'))
forms = collections.defaultdict(set)
def ftoks(nid):
    if nid not in forms:
        s = set(toks(names.get(nid)))
        for (f,) in c.execute('select form from narrator_name where narrator_id=?', (nid,)): s |= set(toks(f))
        forms[nid] = s
    return forms[nid]
REL = {'ابيه', 'ابي', 'جده', 'جدته', 'عمه', 'امه', 'اخيه', 'عمي', 'عم', 'خاله', 'ابنه', 'ابنها', 'ابيها', 'جدي', 'ابي', 'جدها'}
def tk(s):
    t = re.sub('[^ء-ي ]', ' ', DIAC.sub('', s or '').translate(TR)).split()
    t = [x[1:] if x.startswith('و') and len(x) > 3 else x for x in t]
    return [(x[2:] if x.startswith('ال') and len(x) > 4 else x).rstrip('ا') if len(x) > 3 else x for x in t]
def parts(s):
    t = tk(s)
    if not t: return None, None
    return t[0], (t[2] if len(t) >= 3 and t[1] in ('بن', 'ابن') else None)
def gate(sf, nid, votes):
    t = tk(sf)
    if not t: return False
    if t[0] in ('ابو', 'ام'): return True
    if t[0] in REL or len(t) == 1 and t[0] in REL: return votes >= 2
    a, b = parts(sf); x, y = parts(names.get(nid))
    return a == x and not (b and y and b != y)
cand = []; why = collections.Counter()
for rid, v in d.items():
    rid = int(rid)
    if len(v) != 1: why['ambiguous'] += 1; continue
    nid, votes = next(iter(v.items()))
    r = c.execute('select hadith_id,coalesce(chain_no,1),surface,narrator_id,start from chain_mention where rowid=?', (rid,)).fetchone()
    if not r or r[3]: why['already resolved'] += 1; continue
    h, cn, sf, _, st = r
    ms = c.execute('select matn_start from hadith where id=?', (h,)).fetchone()[0]
    if ms is not None and st >= ms: why['in matn'] += 1; continue
    ch = c.execute('select rowid,narrator_id from chain_mention where hadith_id=? and coalesce(chain_no,1)=? and start is not null order by pos,rowid', (h, cn)).fetchall()
    k = next((i for i, x in enumerate(ch) if x[0] == rid), None)
    prev = next((death.get(x[1]) for x in reversed(ch[:k]) if x[1] and death.get(x[1])), None); nxt = next((death.get(x[1]) for x in ch[k + 1:] if x[1] and death.get(x[1])), None)
    if conf(nid, prev, nxt): why['chronology'] += 1; continue
    if not gate(sf, nid, votes): why['name gate'] += 1; continue
    cand.append({'rowid': rid, 'hadith_id': h, 'surface': sf, 'proposed': nid, 'name': names.get(nid), 'votes': votes}); why['kept'] += 1
print(dict(why))
json.dump(cand, open('labels/sandwich_cand.json', 'w'), ensure_ascii=False)
if MODE == 'cand':
    random.seed(11); s = random.sample([x for x in cand if x['votes'] >= 2], min(30, sum(1 for x in cand if x['votes'] >= 2))) + random.sample([x for x in cand if x['votes'] < 2], min(30, sum(1 for x in cand if x['votes'] < 2)))
    with open('labels/sandwich_review.jsonl', 'w', encoding='utf-8') as f:
        for x in s:
            t = c.execute('select text from hadith where id=?', (x['hadith_id'],)).fetchone()[0]
            ch = c.execute('select surface,narrator_id from chain_mention where hadith_id=? and start is not null order by coalesce(chain_no,1),pos', (x['hadith_id'],)).fetchall()
            x['chain'] = [[a, names.get(b, '') if b else None] for a, b in ch]; x['text_head'] = t[:600]; f.write(json.dumps(x, ensure_ascii=False) + '\n')
    print('kept', len(cand), '| votes>=2:', sum(1 for x in cand if x['votes'] >= 2), '| review sample', len(s))
else:
    bad = set(json.load(open(sys.argv[2]))) if len(sys.argv) > 2 else set(); k = 0
    for x in cand:
        if x['rowid'] in bad: continue
        r = c.execute('select narrator_id,id_method,id_confidence from chain_mention where rowid=?', (x['rowid'],)).fetchone()
        if r[0]: continue
        c.execute("insert into surgery_log(step,kind,key,old,new) values('fix_59','mention_narrator_id',?,?,?)", (str(x['rowid']), '|'.join(str(v) for v in r), x['proposed']))
        c.execute("update chain_mention set narrator_id=?, id_method='sandwich', id_confidence=? where rowid=?", (x['proposed'], 0.95 if x['votes'] >= 2 else 0.9, x['rowid'])); k += 1
    db.commit(); print('applied', k)
