"""Phase 2 - add the narrators the parser missed, using models/gap_model.pkl (fix_23).
  python pipeline/fix_24_gap_apply.py pilot [N] [seed]   # N random proposals with context (eye check), no writes
  python pipeline/fix_24_gap_apply.py score [N]          # resumable; writes labels/gap_pred.db (hadith_id, json list of [start,end,p])
  python pipeline/fix_24_gap_apply.py apply              # inserts mentions with p >= GAP_P as new chain_mention rows (flag gap_model), renumbers pos
IDs: asserted (id_method gap_model_unique) only when exactly one registry narrator owns the full surface and it has >= 3 words; a unique owner with
fewer words, or a clearly most popular owner, becomes a weak guess; otherwise no ID.  Gold hadith and hadith flagged gold_reviewed never change."""
from paths import *
from fix_23_gap_model import toks, tfeats, decode
import sqlite3, sys, os, re, json, pickle, random, time, bisect, collections
import numpy as np
from multiprocessing import Pool
GAP_P = 0.75
HEAD = ('ابو', 'ابي', 'ابا', 'بن', 'ابن', 'بنت', 'عبد', 'ام')              # a span may not end with one of these (cut-off name) or start right after one
DBP = OUT + 'hadith_master.db'; PRED = 'labels/gap_pred.db'
VERBISH = set('سال ركب قام خرج راي كان قلت سمعت رايت دخل جاء جاءه اتي اتيت وقد حدث قدم قضي امر نهي ذكر وذكر قوله فيه فيها'.split())
_g = {}
def init():
    _g['m'], _g['h'] = pickle.load(open('models/gap_model.pkl', 'rb'))
    _g['c'] = sqlite3.connect('file:' + DBP + '?mode=ro', uri=True)
def propose(h):
    c = _g['c']
    text, ms = c.execute('select text,matn_start from hadith where id=?', (h,)).fetchone()
    ments = c.execute('select start,end from chain_mention where hadith_id=? and start is not null order by start', (h,)).fetchall()
    T = toks(text, ms)
    if not T: return []
    starts = [t[0] for t in T]; cov = [False] * len(T)
    for s, e in ments:
        a = bisect.bisect_left(starts, s); b = bisect.bisect_left(starts, e)
        for j in range(a, min(b, len(T))): cov[j] = True
    P = _g['m'].predict_proba(_g['h'].transform([tfeats(T, i, cov) for i in range(len(T))]))
    out = []
    for s, e, p in decode(T, cov, P):
        if p < GAP_P: continue
        words = [t[2] for t in T if s <= t[0] < e]
        if not words or len(words) > 8 or any(w in VERBISH for w in words): continue
        if words[-1] in HEAD or (len(words) == 1 and words[0] in HEAD): continue
        k0 = bisect.bisect_left(starts, s)
        if words[0] == 'بن': continue
        if k0 > 0 and (T[k0 - 1][2] in HEAD or T[k0 - 1][2].lstrip('و') in HEAD): continue
        if k0 + len(words) < len(T) and T[k0 + len(words)][2] in ('بن', 'ابن') and not (T[k0 + len(words) - 1][2] in ('بن', 'ابن')): continue   # the name continues with بن ...
        if any(x < e and s < y for x, y in ments): continue
        out.append((s, e, round(float(p), 3)))
    return out
def work(ids): return [(h, json.dumps(propose(h))) for h in ids]
if __name__ == '__main__':
    MODE = sys.argv[1]; ARG = int(sys.argv[2]) if len(sys.argv) > 2 else None
    if MODE == 'pilot':
        init(); c = _g['c']; random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 1)
        ids = [r[0] for r in c.execute("select id from hadith where matn_start is not null and chain_tier in ('A','B','C') order by random() limit %d" % ((ARG or 40) * 3))]
        n = 0
        for h in ids:
            text = c.execute('select text from hadith where id=?', (h,)).fetchone()[0]
            for s, e, p in propose(h):
                print(h, p, '|', text[max(0, s - 40):s].replace('\n', ' '), '[[', text[s:e], ']]', text[e:e + 20].replace('\n', ' ')); n += 1
            if n >= (ARG or 40): break
    elif MODE == 'score':
        c = sqlite3.connect('file:' + DBP + '?mode=ro', uri=True)
        gold = {json.loads(l)['hadith_id'] for l in open('gold/gold_chains.jsonl', encoding='utf-8')}
        p = sqlite3.connect(PRED); p.execute('create table if not exists pred(hadith_id text primary key, spans text)')
        have = {r[0] for r in p.execute('select hadith_id from pred')}
        ids = [r[0] for r in c.execute("select id from hadith where matn_start is not null and chain_tier in ('A','B','C') order by id") if r[0] not in gold and r[0] not in have]
        print('to score', len(ids), flush=True)
        if ARG: ids = ids[:ARG]
        c.close(); t0 = time.time(); done = 0; BATCH = 10000
        with Pool(2, initializer=init, maxtasksperchild=50) as pool:
            for k in range(0, len(ids), BATCH):
                for res in pool.imap(work, [ids[i:i + 250] for i in range(k, min(k + BATCH, len(ids)), 250)]):
                    p.executemany('insert or ignore into pred values(?,?)', res); done += len(res)
                p.commit(); print(f'{done:,}/{len(ids):,} {time.time() - t0:.0f}s', flush=True)
        print('scored', done)
    elif MODE == 'apply':
        db = sqlite3.connect(DBP, timeout=120); c = db.cursor(); p = sqlite3.connect(PRED)
        DIAC = re.compile('[ً-ْٰـٓ-ٕ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي')
        norm = lambda s: re.sub(r'\s+', ' ', re.sub('[^ء-ي ]', ' ', DIAC.sub('', s or '').translate(TR))).strip()
        exact = collections.defaultdict(set)
        for nid, nn in c.execute("select narrator_id,norm from narrator_name where norm is not null and type!='observed'"): exact[nn].add(nid)
        pop = dict(c.execute('select narrator_id,count(*) from chain_mention where narrator_id is not null group by 1'))
        REL = set('ابي ابيه ابوه اباه جدي جده عمي عمه خالي خالتي امه امي اخي اخيه ابنه ابني'.split())
        INS = 'INSERT INTO chain_mention(hadith_id,pos,start,end,surface,narrator_id,id_method,id_confidence,alternatives,flags,chain_no,guess_narrator_id,guess_confidence) VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?)'
        n_h = n_m = 0
        for h, js in p.execute('select hadith_id,spans from pred').fetchall():
            spans = json.loads(js)
            if not spans: continue
            fl = c.execute('select flags,text from hadith where id=?', (h,)).fetchone()
            if 'gold_reviewed' in (fl[0] or '').split() or 'gap_model' in (fl[0] or '').split(): continue
            text = fl[1]
            rows = c.execute('select rowid,pos,start,end,chain_no from chain_mention where hadith_id=?', (h,)).fetchall()
            if any(r[2] is None for r in rows if (r[4] or 1) == 1): continue
            c.execute("INSERT INTO surgery_log(step,kind,key,old,new) VALUES('fix_24','positions',?,?,NULL)", (h, json.dumps({r[0]: r[1] for r in rows})))
            for s, e, pr in spans:
                if any(r[2] < e and s < r[3] for r in rows): continue
                surf = text[s:e]; name = norm(surf); nid = gid = None; conf = 0.0; meth = 'gap_model_unresolved'
                if name in REL: meth = 'gap_relative_unresolved'
                else:
                    ow = sorted(exact.get(name) or exact.get(re.sub(r'^و(?=[ء-ي]{3})', '', name)) or [], key=lambda x: -pop.get(x, 0))
                    if len(ow) == 1 and len(name.split()) >= 3: nid, conf, meth = ow[0], 0.8, 'gap_model_unique'
                    elif len(ow) == 1: gid, meth = ow[0], 'gap_model_candidates'
                    elif ow and pop.get(ow[0], 0) >= 3 * pop.get(ow[1], 0): gid, meth = ow[0], 'gap_model_candidates'
                c.execute(INS, (h, 900000, s, e, surf, nid, meth, conf, None, 'gap_model', gid, 0.3 if gid else None)); n_m += 1
            main = [r[0] for r in c.execute('select rowid from chain_mention where hadith_id=? and coalesce(chain_no,1)=1 order by start', (h,))]
            c.execute('update chain_mention set pos=pos+100000 where hadith_id=? and coalesce(chain_no,1)=1', (h,))
            c.executemany('update chain_mention set pos=? where rowid=?', [(i + 1, rid) for i, rid in enumerate(main)])
            c.execute('update hadith set flags=?, n_narrators=(select count(*) from chain_mention where hadith_id=?) where id=?', (((fl[0] or '') + ' gap_model').strip(), h, h)); n_h += 1
            if n_h % 5000 == 0: db.commit(); print(n_h, n_m, flush=True)
        db.commit(); print('done: hadith', n_h, 'mentions added', n_m)
