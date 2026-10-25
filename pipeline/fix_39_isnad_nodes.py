"""Isnad-map nodes for relatives and anonymous transmitters ('أبيه', 'جده', 'عمي', 'رجل', 'بعض أصحابنا', ...).  These stay unknown people, but they must appear in isnad maps.
Layer (additive; nothing is overwritten):
  chain_mention.node_key   key of the map node for UNKNOWN-type mentions (NULL for identified mentions: their node is narrator_id)
  isnad_node(node_key PK, kind, label, relation, base_key, fl_from, fl_to, fl_basis, n_mentions, n_hadith)
  view mention_node(mention_rowid, hadith_id, chain_no, pos, node)   node = node_key when set, else narrator_id (the catch-all record N0003708 is never used as a node)
Node keys:  relative of an identified base B:      rel:<relation>:<B>      (father / grandfather / paternal_uncle / maternal_uncle / mother / brother / son / forefathers)
            relative of an unknown base node X:    rel:<relation>:<X>
            relative with no earlier mention in the chain (speaker = the collector):  rel:<relation>:collector:<book>
            anonymous:                             anon:<class>:<student node>:<teacher node>   (an unnamed link between the same two neighbours is one node)
Floruit (fl. lo/hi, years AH): the unknown X narrated from the next mention T and was narrated from by the previous mention S.  lo = death of T, hi = death of S, taken from the nearest
identified neighbours (up to 3 positions away), swapped if reversed; only one side known -> the other side is set 40 years away; none known -> NULL.
For relatives (older generation than the base) hi is capped at the base's death year.   fl_basis records which neighbours were used.
  python pipeline/fix_39_isnad_nodes.py pilot [N] [seed]  |  apply"""
from paths import *
import sqlite3, sys, re, json, random, collections, statistics
MODE = sys.argv[1]; ARG = int(sys.argv[2]) if len(sys.argv) > 2 else None
DBP = OUT + 'hadith_master.db'; HUB = 'N0003708'
db = sqlite3.connect(DBP if MODE == 'apply' else 'file:' + DBP + '?mode=ro', timeout=120, uri=(MODE != 'apply')); c = db.cursor()
DIAC = re.compile('[ً-ْٰـٓ-ٕ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
def nrm(s): return re.sub(r'\s+', ' ', re.sub(r'[^ء-ي ]', ' ', re.sub(r'[A-Za-z]-?\d+', ' ', DIAC.sub('', s or '')).translate(TR))).strip()
REL = [('father', 'ابيه ابيها ابوه اباه ابيهم ابيهما ابيك', 'ابي ابانا ابى'), ('grandfather', 'جده جدها جدهم جدهما', 'جدي'), ('paternal_uncle', 'عمه عمها عمهم', 'عمي عمى'),
       ('maternal_uncle', 'خاله خالها', 'خالي'), ('mother', 'امه امها امهم', 'امي'), ('brother', 'اخيه اخوه اخيها', 'اخي'), ('son', 'ابنه ابنها', 'ابني'),
       ('forefathers', 'ابائه ابايه اجداده ابايهم', '')]
RELMAP = {}
for rel, third, first in REL:
    for w in (third + ' ' + first).split(): RELMAP[w] = rel
ANON = [('man', 'رجل رجلا رجال رجلين رجلان'), ('woman', 'امراه امراة نساء'), ('shaykh', 'شيخ شيخا اشياخ اشياخه اشياخنا شيوخ'), ('trusted', 'الثقه ثقه'),
        ('group', 'اصحاب اصحابنا اصحابه ناس قوم اهل عده'), ('some', 'بعض بعضهم غير واحد غيره وغيره احدهما'), ('who', 'من عمن ممن'), ('mawla', 'مولى مولي'), ('so_and_so', 'فلان فلانا')]
HONOR = set('رضي الله عنه عنهما رحمه رحمهما ره قال حدثني حدثنا ثني ني عليه عليهم عليهما السلام ص ع صلى وسلم'.split())
def classify(surf):
    n = nrm(surf)
    if not n: return None
    w = n.split()
    w2 = [x for x in w if x not in HONOR]       # 'أبي رضي الله عنه قال', 'حدثني أبي رحمه الله' = bare relative
    if len(w2) == 1 and w2[0] in RELMAP: return ('relative', RELMAP[w2[0]])
    if w[0] in RELMAP and len(w) <= 3: return ('relative', RELMAP[w[0]])
    for cls, forms in ANON:
        if w[0] in forms.split() or n in forms.split(): return ('anonymous', cls)
    return None
DEATH = dict(c.execute('select id,death_year from narrator where death_year is not null'))
rows = c.execute("""select m.rowid,m.hadith_id,m.surface,m.narrator_id,m.id_method,m.guess_narrator_id,h.book
   from chain_mention m join hadith h on h.id=m.hadith_id where m.start is not null and (m.narrator_id=? or m.narrator_id is null or m.id_method like '%relative%' or m.id_method like '%anonymous%')""", (HUB,)).fetchall()
unk = {}
for rid, h, surf, nid, meth, g, book in rows:
    meth = meth or ''
    if nid and nid != HUB and not meth.endswith(('relative_father', 'relative_father_edges')): continue
    if g and nid is None and not meth.endswith(('unresolved', 'anonymous')) and 'relative' not in meth: continue
    k = classify(surf)
    if k: unk.setdefault(h, set()).add((rid, k, book))
print('hadith with unknown-type mentions', len(unk), '| mentions', sum(len(v) for v in unk.values()), flush=True)
nodes = {}; mnode = []; samples = []
for h, lst in unk.items():
    allm = c.execute('select rowid,coalesce(chain_no,1),pos,narrator_id from chain_mention where hadith_id=? and start is not null order by 2,3', (h,)).fetchall()
    bychain = collections.defaultdict(list)
    for r in allm: bychain[r[1]].append(r)
    keyof = {r[0]: r[3] for r in allm if r[3] and r[3] != HUB}
    pos_of = {r[0]: (r[1], r[2]) for r in allm}
    for rid, (kind, cls), book in sorted(lst, key=lambda x: pos_of.get(x[0], (9, 9))):
        if rid not in pos_of: continue
        ch = bychain[pos_of[rid][0]]; idx = next(i for i, r in enumerate(ch) if r[0] == rid)
        def neigh(step):
            hop = 0; j = idx + step
            while 0 <= j < len(ch) and hop < 3:
                nid = ch[j][3]
                if nid and nid != HUB and nid in DEATH: return nid, DEATH[nid]
                hop += 1; j += step
            return None
        def adj(step):
            j = idx + step
            if not (0 <= j < len(ch)): return None
            return keyof.get(ch[j][0]) or f'u{h}.{ch[j][2]}'          # unidentified neighbour: its own unique key (never merged with other unknowns)
        S = neigh(-1); T = neigh(+1)
        if kind == 'relative':
            base = adj(-1) or ('collector:' + (book or '')[:30]); key = f'rel:{cls}:{base}'; label = f'{cls} of {base}'
        else:
            key = f"anon:{cls}:{adj(-1) or '^'}:{adj(+1) or '$'}"; label = f'anonymous ({cls})'
        keyof[rid] = key
        lo = T[1] if T else None; hi = S[1] if S else None; basis = ('T=' + T[0] if T else '') + (' S=' + S[0] if S else '')
        if lo is not None and hi is not None and lo > hi: lo, hi = hi, lo
        if lo is None and hi is not None: lo = hi - 40; basis += ' (lo=S-40)'
        if hi is None and lo is not None: hi = lo + 40; basis += ' (hi=T+40)'
        if kind == 'relative' and S and hi is not None and S[1] < hi: hi = S[1]
        n = nodes.setdefault(key, dict(kind=kind, label=label, relation=cls, base=key.split(':', 2)[2] if kind == 'relative' else None, lo=[], hi=[], basis=basis, hs=set(), n=0))
        if lo is not None: n['lo'].append(lo); n['hi'].append(hi)
        n['hs'].add(h); n['n'] += 1; mnode.append((key, rid))
        if len(samples) < 6000: samples.append((h, c.execute('select surface from chain_mention where rowid=?', (rid,)).fetchone()[0], key, lo, hi, basis, idx, len(ch)))
print('nodes', len(nodes), collections.Counter(n['kind'] for n in nodes.values()), '| mentions', len(mnode), '| nodes with fl', sum(1 for n in nodes.values() if n['lo']), flush=True)
if MODE == 'pilot':
    random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 1)
    for h, surf, key, lo, hi, basis, idx, L in random.sample(samples, min(ARG or 25, len(samples))): print(h, f'#{idx + 1}/{L}', nrm(surf)[:18], '->', key[:72], '| fl.', f'{lo}/{hi}' if lo is not None else '-', '|', basis)
    print('\nbusiest nodes:')
    for k, v in sorted(nodes.items(), key=lambda kv: -kv[1]['n'])[:12]: print(' ', k[:72], v['n'], 'mentions', len(v['hs']), 'hadith')
else:
    c.executescript('CREATE TABLE IF NOT EXISTS isnad_node(node_key TEXT PRIMARY KEY, kind TEXT, label TEXT, relation TEXT, base_key TEXT, fl_from INT, fl_to INT, fl_basis TEXT, n_mentions INT, n_hadith INT);')
    if 'node_key' not in [r[1] for r in c.execute('pragma table_info(chain_mention)')]: c.execute('ALTER TABLE chain_mention ADD COLUMN node_key TEXT')
    c.execute('CREATE INDEX IF NOT EXISTS ix_cm_nodekey ON chain_mention(node_key)')
    c.execute('DELETE FROM isnad_node')
    c.executemany('INSERT INTO isnad_node VALUES(?,?,?,?,?,?,?,?,?,?)', [(k, v['kind'], v['label'], v['relation'], v['base'], int(statistics.median(v['lo'])) if v['lo'] else None,
                                                                         int(statistics.median(v['hi'])) if v['hi'] else None, v['basis'] if v['lo'] else None, v['n'], len(v['hs'])) for k, v in nodes.items()])
    for i in range(0, len(mnode), 5000):
        chunk = mnode[i:i + 5000]
        c.executemany("insert into surgery_log(step,kind,key,old,new) select 'fix_39','node_key',?,node_key,? from chain_mention where rowid=?", [(rid, k, rid) for k, rid in chunk])
        c.executemany('update chain_mention set node_key=? where rowid=?', chunk)
    c.executescript("DROP VIEW IF EXISTS mention_node; CREATE VIEW mention_node AS SELECT rowid AS mention_rowid, hadith_id, coalesce(chain_no,1) AS chain_no, pos, "
                    "CASE WHEN node_key IS NOT NULL THEN node_key WHEN narrator_id='N0003708' THEN NULL ELSE narrator_id END AS node FROM chain_mention;")
    db.commit(); print('applied', len(nodes), 'nodes,', len(mnode), 'mentions')
