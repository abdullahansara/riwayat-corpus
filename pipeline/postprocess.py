from paths import *
import sqlite3, re, csv, json, collections, time, os, sys
t0 = time.time()
def log(*a): print(f'[{time.time()-t0:4.0f}s]', *a, flush=True)
HM = OUT + ''; H = SRC + 'HadithKG/'
HERE = PIPE
DIAC = re.compile('[\u064B-\u0652\u0670\u0640\u0653-\u0655\u200f\u200e]'); KEEP = re.compile('[^\u0621-\u064A ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def norm(s): return re.sub(r'\s+', ' ', KEEP.sub(' ', DIAC.sub('', str(s or '')).translate(TR))).strip()
db = sqlite3.connect(HM + 'hadith_master.db'); c = db.cursor()
# ---- 1. teacher -> student edges observed in the chains (position p = student of position p+1)
c.executescript('DROP TABLE IF EXISTS narrator_edge; CREATE TABLE narrator_edge(student TEXT, teacher TEXT, n_hadith INT, n_tier_a INT);')
c.execute('''INSERT INTO narrator_edge
  SELECT a.narrator_id, b.narrator_id, count(*), sum(h.chain_tier='A')
  FROM chain_mention a JOIN chain_mention b ON a.hadith_id=b.hadith_id AND b.pos=a.pos+1 JOIN hadith h ON h.id=a.hadith_id
  WHERE a.narrator_id IS NOT NULL AND b.narrator_id IS NOT NULL AND a.narrator_id<>b.narrator_id GROUP BY 1,2''')
c.execute('CREATE INDEX IF NOT EXISTS ix_edge_s ON narrator_edge(student); CREATE INDEX IF NOT EXISTS ix_edge_t ON narrator_edge(teacher)') if False else None
c.executescript('CREATE INDEX IF NOT EXISTS ix_edge_s ON narrator_edge(student); CREATE INDEX IF NOT EXISTS ix_edge_t ON narrator_edge(teacher);'); db.commit()
log('narrator_edge rows:', c.execute('select count(*) from narrator_edge').fetchone()[0])
# ---- 2. surface forms actually used in the chains -> narrator_name (type observed) with counts
c.execute("DELETE FROM narrator_name WHERE type='observed'"); c.execute('UPDATE narrator_name SET observed_count=0'); db.commit()   # idempotent re-runs
obs = collections.defaultdict(lambda: [0, ''])
for nid, surf, n in c.execute('SELECT narrator_id, surface, count(*) FROM chain_mention WHERE narrator_id IS NOT NULL AND surface IS NOT NULL GROUP BY 1,2'):
    k = (nid, norm(surf))
    if len(k[1]) < 2: continue
    o = obs[k]; o[0] += n
    if not o[1]: o[1] = surf
existing = {(nid, nn): rid for rid, nid, nn in c.execute('SELECT rowid, narrator_id, norm FROM narrator_name')}
upd = []; ins = []
for (nid, nn), (cnt, form) in obs.items():
    rid = existing.get((nid, nn))
    if rid: upd.append((cnt, rid))
    else: ins.append((nid, form, nn, 'observed', 'chains', cnt))
c.executemany('UPDATE narrator_name SET observed_count=observed_count+? WHERE rowid=?', upd)
c.executemany('INSERT INTO narrator_name(narrator_id,form,norm,type,source,observed_count) VALUES(?,?,?,?,?,?)', ins); db.commit()
log(f'observed surface forms: {len(obs)} | already known: {len(upd)} | new alternative names added: {len(ins)}')
# ---- 3. exports
n_exp = 0
with open(HM + 'narrators.csv', 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f); w.writerow(['narrator_id', 'standard_name', 'death_year', 'tradition', 'n_hadith', 'source_ids', 'alternative_names'])
    cnt = dict(c.execute('SELECT narrator_id, count(*) FROM chain_mention WHERE narrator_id IS NOT NULL GROUP BY 1').fetchall())
    names = collections.defaultdict(list)
    for nid, form, o in c.execute('SELECT narrator_id, form, observed_count FROM narrator_name ORDER BY observed_count DESC'):
        if len(names[nid]) < 25 and form not in names[nid]: names[nid].append(form)
    sids = collections.defaultdict(list)
    for nid, src, sid in c.execute('SELECT narrator_id, source, source_id FROM narrator_source_id'): sids[nid].append(f'{src}:{sid}')
    for nid, nm, dy, tr in c.execute('SELECT id, std_name, death_year, tradition FROM narrator ORDER BY id'):
        w.writerow([nid, nm, dy, tr, cnt.get(nid, 0), ' '.join(sids[nid]), ' | '.join(names[nid])]); n_exp += 1
log('narrators.csv rows:', n_exp)
# ---- 4. integrity checks + quality report
tot_h = c.execute('select count(*) from hadith').fetchone()[0]; tot_m = c.execute('select count(*) from chain_mention').fetchone()[0]
q = lambda sql: c.execute(sql).fetchall()
tiers = q("select tradition, chain_tier, count(*) from hadith group by 1,2 order by 1,2")
meth = q('select id_method, count(*), avg(id_confidence) from chain_mention group by 1 order by 2 desc')
no_id = c.execute('select count(*) from chain_mention where narrator_id is null').fetchone()[0]
no_span = c.execute("select count(*) from chain_mention where start is null").fetchone()[0]
tagged = c.execute('select count(*) from hadith where text_tagged is not null').fetchone()[0]
bad_range = c.execute('select count(*) from chain_mention m join hadith h on h.id=m.hadith_id where m.start is not null and (m.end>length(h.text) or m.start<0 or m.end<=m.start)').fetchone()[0]
nar = c.execute('select count(*) from narrator').fetchone()[0]; nnames = c.execute('select count(*) from narrator_name').fetchone()[0]
used = c.execute('select count(distinct narrator_id) from chain_mention where narrator_id is not null').fetchone()[0]
ref = c.execute('select source, count(*) from reference_chain group by 1').fetchall()
def scores(fn):
    out = []
    if os.path.exists(HERE + fn):
        for line in open(HERE + fn, encoding='utf-8', errors='ignore'):
            if 'chain exact' in line: out.append(line.strip())
    return out
sc_lines = scores('train6_attempt1.log') or scores('train6_attempt2.log') or scores('train6_attempt3.log') or scores('train5.log')
samples = []
for tier in ('A', 'B', 'C'):
    r = c.execute("select id, tradition, book, number, text_tagged from hadith where chain_tier=? and text_tagged is not null order by random() limit 1", (tier,)).fetchone()
    if r: samples.append((tier, r))
with open(HM + 'QUALITY_REPORT.md', 'w', encoding='utf-8') as f:
    f.write('# Hadith master database - build report\n\n')
    f.write(f'- hadith: **{tot_h:,}**  |  chain mentions: **{tot_m:,}**  |  canonical narrators: **{nar:,}** ({used:,} appear in at least one chain)  |  narrator name forms: **{nnames:,}**\n')
    f.write(f'- hadith with inline-tagged text (narrator ids embedded): {tagged:,}\n- mentions with a narrator id: {tot_m-no_id:,} ({(tot_m-no_id)/tot_m:.1%}); without: {no_id:,}\n- mentions whose character span was located in the text: {tot_m-no_span:,} ({(tot_m-no_span)/tot_m:.1%}); span range errors: {bad_range}\n\n')
    f.write('## Chain tiers (by tradition)\n- **A** chain confirmed by two independent annotations (hadith-kg and Sanadset agree)\n- **B** one curated annotation (hadith-kg, Sanadset tags, or Thaqalayn hyperlinks)\n- **C** produced by our parser / our parse of Sanadset (lower confidence)\n- **none** no chain found in the text\n\n| tradition | tier | hadith |\n|---|---|---|\n')
    for t, ti, n in tiers: f.write(f'| {t} | {ti} | {n:,} |\n')
    f.write('\n## How narrator ids were assigned (mentions)\n\n| method | mentions | mean confidence |\n|---|---|---|\n')
    for m, n, a in meth: f.write(f'| {m} | {n:,} | {a:.2f} |\n')
    f.write('\n## Parser scores on data never used in training\n```\n' + '\n'.join(sc_lines) + '\n```\n')
    f.write('\n## Reference chains kept separately (full multi-isnad, not merged into hadith)\n' + ', '.join(f'{s}: {n:,}' for s, n in ref) + '\n')
    f.write('\n## Sample records\n')
    for tier, r in samples: f.write(f'\n**Tier {tier}** {r[0]} ({r[1]}, {r[2]} #{r[3]})\n\n{r[4][:700]}\n')
    f.write('\n## Tables\n`hadith`, `chain_mention` (one row per narrator with span, id, method, confidence, source reference, alternatives), `narrator` (our id, standard name, attributes), `narrator_name` (every name form with type, source and observed count), `narrator_source_id` (our id <-> each source id), `narrator_edge` (teacher->student counts from the chains), `narrator_edge_seed` (teacher/student links from Itqan/AR-Sanad), `reference_chain` (MIDS Sahih Muslim and SemanticHadith full isnads).\n')
    f.write('\n## Known limits\n- Whole-chain exactness of the parser is 69-81% on held-out data (narrator-level F1 0.94-0.97); tiers say how much to trust each chain.\n- hadith-kg and SemanticHadith share an upstream annotation, so their agreement is not fully independent; MIDS (Sahih Muslim) was the independent check.\n- Rare narrators may still be duplicated across sources where co-occurrence or exact-name evidence was insufficient.\n- Shi\'i narrator ids from Thaqalayn are kept separate from Sunni ids (no cross-tradition merging).\n')
log('quality report written; hadith', tot_h, 'mentions', tot_m)
