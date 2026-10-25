from paths import *
import sqlite3, re, collections, time
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
HM = OUT + ''
DIAC = re.compile('[\u064B-\u0652\u0670\u0640\u0653-\u0655\u200f\u200e]'); KEEP = re.compile('[^\u0621-\u064A ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def norm(s): return re.sub(r'\s+', ' ', KEEP.sub(' ', DIAC.sub('', str(s or '')).translate(TR))).strip()
STOP = {'قال', 'عن', 'حدثنا', 'اخبرنا', 'حدثني', 'اخبرني', 'ثنا', 'سمعت', 'رجل', 'رجلا', 'بعض', 'شيخ', 'من', 'اهل', 'غيره', 'اخرين', 'ابيه', 'جده', 'عمه'}
def key(surface):
    t = norm(surface).split()
    if t and len(t[0]) > 2 and t[0][0] == 'و': t[0] = t[0][1:]
    if t and t[0] in ('ابا', 'ابي'): t[0] = 'ابو'
    return ' '.join(t)
db = sqlite3.connect(HM + 'hadith_master.db'); c = db.cursor()
mx = int(c.execute("select max(cast(substr(id,2) as integer)) from narrator").fetchone()[0]); log('highest existing narrator number:', mx)
rows = c.execute('''SELECT m.rowid, m.surface, h.tradition FROM chain_mention m JOIN hadith h ON h.id=m.hadith_id
                    WHERE m.narrator_id IS NULL AND m.surface IS NOT NULL''').fetchall()
log('mentions without id:', len(rows))
groups = collections.defaultdict(lambda: {'rows': [], 'forms': collections.Counter(), 'trad': collections.Counter()}); skipped = collections.Counter()
for rid, surf, trad in rows:
    k = key(surf); toks = k.split()
    if len(toks) < 3: skipped['fewer than 3 words (too ambiguous to name one person)'] += 1; continue
    if any(t in STOP for t in toks[:2]) and len(toks) < 4: skipped['looks like a filler / transmission phrase'] += 1; continue
    if len(toks) > 14: skipped['implausibly long (merged text)'] += 1; continue
    g = groups[k]; g['rows'].append(rid); g['forms'][surf.strip()] += 1; g['trad'][trad] += 1
log('new narrator candidates (distinct full names):', len(groups), '| mentions covered:', sum(len(g['rows']) for g in groups.values()), '| skipped:', dict(skipped))
n = mx; upd = []; ins_n = []; ins_name = []; ins_src = []
for k, g in sorted(groups.items(), key=lambda kv: -len(kv[1]['rows'])):
    n += 1; nid = 'N%07d' % n; best = g['forms'].most_common(1)[0][0]; trad = g['trad'].most_common(1)[0][0]
    ins_n.append((nid, best, 'chains_new', trad, None, None, None, None, None, None, None, None, 1))
    for form, cnt in g['forms'].items(): ins_name.append((nid, form, norm(form), 'observed', 'chains', cnt))
    ins_src.append((nid, 'chains', k, best))
    for rid in g['rows']: upd.append((nid, 'new_narrator_from_full_name', 0.6, rid))
c.executemany('INSERT INTO narrator VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', ins_n)
c.executemany('INSERT INTO narrator_name(narrator_id,form,norm,type,source,observed_count) VALUES(?,?,?,?,?,?)', ins_name)
c.executemany('INSERT INTO narrator_source_id VALUES(?,?,?,?)', ins_src)
c.executemany('UPDATE chain_mention SET narrator_id=?, id_method=?, id_confidence=? WHERE rowid=?', upd); db.commit()
tot = c.execute('select count(*) from chain_mention').fetchone()[0]; nul = c.execute('select count(*) from chain_mention where narrator_id is null').fetchone()[0]
log(f'created {len(ins_n):,} new narrators | mentions still without id: {nul:,} of {tot:,} ({nul/tot:.1%}) | narrators now: {c.execute("select count(*) from narrator").fetchone()[0]:,}')
