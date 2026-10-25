"""P1b: repair corrupted narrator.std_name and poisoned name forms (Itqan 'full' forms copied onto unrelated narrators).
Rule A  a long name form (norm >= 25 chars) shared by >= 3 narrators is poison for every sharer whose OTHER forms do not match it (token Jaccard < 0.5); it is kept only for sharers that match.
        Poison rows are deleted from narrator_name (all have observed_count 0).
Rule B  a narrator whose std_name is poison (A) or has token Jaccard < 0.3 against its own kg 'full' form gets a new std_name.
        Priority: kg 'full' form; else most-observed non-poison form with >= 3 name tokens (observed/variant/full/popular), ties -> longer; else keep the old one and log 'no_better_form'.
Nothing about narrator IDs or mentions changes; old values go to surgery_log.
  python pipeline/fix_48_std_names.py pilot [N] [seed] | apply"""
from paths import *
import sqlite3, sys, re, random, collections
MODE = sys.argv[1]
DBP = OUT + 'hadith_master.db'
db = sqlite3.connect(DBP if MODE == 'apply' else 'file:' + DBP + '?mode=ro', timeout=120, uri=(MODE != 'apply')); c = db.cursor()
DIAC = re.compile('[ً-ْٰـٓ-ٕ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def nrm(s): return re.sub(r'\s+', ' ', re.sub(r'[^ء-ي ]', ' ', re.sub(r'[A-Za-z]-?\d+', ' ', DIAC.sub('', s or '')).translate(TR))).strip()
def toks(n): return set(n.split()) - {'بن', 'و'}
def jac(a, b): return len(a & b) / len(a | b) if a and b else 0.0
def ovl(a, b): return len(a & b) / min(len(a), len(b)) if a and b else 0.0
PROSE = set('حدث ولد روايته ذكر قرأ صدوق أرسل عن'.split()) | set(nrm(x) for x in 'حدث ولد روايته ذكر قرأ صدوق أرسل عن'.split())
nar = {r[0]: r[1:] for r in c.execute('select id,std_name,std_name_source,tradition from narrator')}
forms = collections.defaultdict(list)       # nid -> [(form, norm, type, source, observed)]
for nid, form, norm, typ, src, obs in c.execute('select narrator_id,form,norm,type,source,observed_count from narrator_name'): forms[nid].append((form, norm or nrm(form), typ, src, obs or 0))
share = collections.defaultdict(set)        # long norm -> narrators carrying it
for nid, fl in forms.items():
    for f in fl:
        if len(f[1]) >= 25: share[f[1]].add(nid)
poison = {n: s for n, s in share.items() if len(s) >= 3}
print('long shared forms (>=3 narrators)', len(poison), '| rows', sum(len(s) for s in poison.values()), flush=True)
drop = collections.defaultdict(set)         # nid -> poison norms to delete
for p, sharers in poison.items():
    pt = toks(p)
    for nid in sharers:
        others = [toks(f[1]) for f in forms[nid] if f[1] != p and f[1] not in poison]
        if not others: continue              # the form is this record's only evidence (duplicate record): keep, merge later
        best = max([jac(pt, o) for o in others], default=0.0)
        if best < 0.5: drop[nid].add(p)
print('narrators losing poison forms', len(drop), '| form rows to delete', sum(len(v) for v in drop.values()), flush=True)
PROSE |= set(nrm(x) for x in 'ثقة صدوق مقبول سكن يروي يلقب ولد نزيل كان أحسب شيخ قيل وكان أخو والد عنى حفظ أرسل'.split())
CODE = re.compile(r'^(?:[ء-ي]{1,3}\s?){1,4}:\s*')
def clean(form):
    f = CODE.sub('', form.strip()).strip(' ،,.:؛'); out = []
    for w in f.split():
        if nrm(w) in PROSE: break
        out.append(w)
    if out and out[0].startswith('و') and len(out[0]) > 2 and nrm(out[0])[1:] and out[0][1] not in 'ًٌٍَُِّْ': out[0] = out[0][1:]
    return ' '.join(out).strip(' ،,.:؛')
def kunya_like(n): w = n.split(); return len(w) <= 3 and w[0] in ('ابو', 'ابي', 'ابن', 'ام') and 'بن' not in w
def pick(nid, banned):
    fl = [f for f in forms[nid] if f[1] not in banned and f[1] not in poison]
    kg = [f for f in fl if f[3] == 'kg' and f[2] == 'full' and len(f[1].split()) >= 2]
    if kg: return max(kg, key=lambda f: (f[4], len(f[1])))[0], 'kg_full'
    cands = []
    for f in fl:
        cf = clean(f[0]); t = toks(nrm(cf))
        if 2 <= len(t) <= 14: cands.append((f[4], 'بن' in nrm(cf).split() or 'ابن' in nrm(cf).split(), -abs(len(t) - 5), cf))
    if cands:
        b = max(cands)[3]; return b, ('kunya_only' if kunya_like(nrm(b)) else 'best_observed')
    return None, 'no_better_form'
rewrite = {}
for nid, (std, src, trad) in nar.items():
    ns = nrm(std); banned = drop.get(nid, set())
    bad = ns in banned
    own_obs = max([f[4] for f in forms[nid] if f[1] == ns], default=0)
    if not bad and src == 'itq' and own_obs == 0:
        kg = [f for f in forms[nid] if f[3] == 'kg' and f[2] == 'full']
        if kg and max(ovl(toks(ns), toks(f[1])) for f in kg) < 0.5: bad = True
    if bad:
        new, how = pick(nid, banned)
        rewrite[nid] = (std, new, how)
print('std_name rewrites', len(rewrite), collections.Counter(v[2] for v in rewrite.values()), flush=True)
if MODE == 'pilot':
    N = int(sys.argv[2]) if len(sys.argv) > 2 else 40; random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 1)
    for nid in random.sample(sorted(rewrite), min(N, len(rewrite))):
        old, new, how = rewrite[nid]
        top = sorted([f for f in forms[nid] if f[1] not in poison], key=lambda f: -f[4])[:3]
        print(f'{nid} [{how}] OLD: {old}\n      NEW: {new}\n      forms: ' + ' | '.join(f'{f[0]}({f[4]})' for f in top))
else:
    n = 0
    for nid, (old, new, how) in rewrite.items():
        if new and new != old:
            c.execute("insert into surgery_log values('fix_48','std_name',?,?,?)", (nid, old, new)); c.execute("update narrator set std_name=?, std_name_source=? where id=?", (new, how, nid)); n += 1
        elif not new: c.execute("insert into surgery_log values('fix_48','std_name_no_better_form',?,?,NULL)", (nid, old))
    d = 0
    for nid, ps in drop.items():
        for f in forms[nid]:
            if f[1] in ps:
                c.execute("insert into surgery_log values('fix_48','poison_form',?,?,'deleted')", (nid, '|'.join(str(x) for x in f)))
                c.execute('delete from narrator_name where narrator_id=? and norm=?', (nid, f[1])); d += 1
    db.commit(); print('applied: std_name rewritten', n, '| poison form rows deleted (by norm, may cover duplicates)', d)
