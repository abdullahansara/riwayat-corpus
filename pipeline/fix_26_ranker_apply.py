"""Phase 3 - run models/ranker.pkl (fix_25) over every mention that has no asserted ID and apply the confident results.
  python pipeline/fix_26_ranker_apply.py score [MAX_HADITH]   # resumable; writes labels/ranker_pred.db (rowid, cand, p, p2)
  python pipeline/fix_26_ranker_apply.py pilot [N] [seed]     # N random would-be assertions with context (eye check)
  python pipeline/fix_26_ranker_apply.py apply                # p >= ASSERT_P -> narrator_id (id_method 'ranker'); GUESS_P <= p < ASSERT_P -> weak guess.  Logged in surgery_log (fix_26)
Relatives / anonymous mentions (أبيه, جده, رجل ...) are skipped; gold hadith never change."""
from paths import *
from id_lib import Ctx, candidates, feats, norm
import sqlite3, sys, os, json, pickle, random, time, itertools, collections
import numpy as np
ASSERT_P, GUESS_P = 0.85, 0.5
PRED = 'labels/ranker_pred.db'; DBP = OUT + 'hadith_master.db'
SKIP = set('ابي ابيه ابوه اباه جدي جده عمي عمه خالي خالتي امه امي اخي اخيه ابنه ابني ابيها ابيهم جدها رجل رجلا امراة امرأة رجال من'.split())
if __name__ == '__main__':
    MODE = sys.argv[1]; ARG = int(sys.argv[2]) if len(sys.argv) > 2 else None
    if MODE == 'score':
        c = sqlite3.connect('file:' + DBP + '?mode=ro', uri=True); ctx = Ctx(c)
        m, dv = pickle.load(open('models/ranker.pkl', 'rb'))
        gold = {json.loads(l)['hadith_id'] for l in open('gold/gold_chains.jsonl', encoding='utf-8')}
        p = sqlite3.connect(PRED); p.execute('create table if not exists pred(rid int primary key, cand text, p real, p2 real)'); p.execute('create table if not exists done(hadith_id text primary key)')
        done = {r[0] for r in p.execute('select hadith_id from done')}
        cur = c.execute('select m.rowid,m.hadith_id,m.start,m.surface,m.narrator_id,m.guess_narrator_id,m.id_method,h.tradition from chain_mention m join hadith h on h.id=m.hadith_id where m.start is not null order by m.hadith_id,m.start')
        t0 = time.time(); nh = nm = 0; buf = []; keys = []; hids = []
        def flush():
            global buf, keys, hids
            if buf:
                pr = m.predict_proba(dv.transform(buf))[:, 1]; best = {}
                for (rid, cd), pp in zip(keys, pr): best.setdefault(rid, []).append((float(pp), cd))
                rows = []
                for rid, v in best.items():
                    v.sort(reverse=True); rows.append((rid, v[0][1], v[0][0], v[1][0] if len(v) > 1 else 0.0))
                p.executemany('insert or replace into pred values(?,?,?,?)', rows)
            p.executemany('insert or ignore into done values(?)', [(h,) for h in hids]); p.commit(); buf, keys, hids = [], [], []
        for hid, grp in itertools.groupby(cur, key=lambda r: r[1]):
            if hid in done or hid in gold or hid < os.environ.get('FROM', ''): continue
            M = list(grp); nh += 1; hids.append(hid)
            for k, (rid, h, st, surf, nid, gid, meth, trad) in enumerate(M):
                if nid or norm(surf) in SKIP or (meth and 'relative' in meth) or (meth and 'anonymous' in meth): continue
                prev_id = next((M[j][4] for j in range(k - 1, -1, -1) if M[j][4]), None); next_id = next((M[j][4] for j in range(k + 1, len(M)) if M[j][4]), None)
                cands = candidates(ctx, surf, nid, gid, prev_id)
                for cd in cands: buf.append(feats(ctx, surf, cd, cands, nid, gid, meth, prev_id, next_id, trad, k, len(M))); keys.append((rid, cd))
                nm += 1
            if len(hids) >= 3000: flush(); print(f'{nh:,} hadith, {nm:,} mentions, {time.time() - t0:.0f}s', flush=True)
            if ARG and nh >= ARG: break
        flush(); print('scored', nh, 'hadith', nm, 'mentions')
    else:
        db = sqlite3.connect(DBP, timeout=120); c = db.cursor(); p = sqlite3.connect(PRED)
        rows = p.execute('select rid,cand,p,p2 from pred where p>=?', (GUESS_P,)).fetchall()
        print('predictions >= guess threshold:', len(rows), '| >= assert threshold:', sum(1 for r in rows if r[2] >= ASSERT_P))
        if MODE == 'pilot':
            random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 1)
            sel = [r for r in rows if r[2] >= ASSERT_P]; names = dict(c.execute('select id,std_name from narrator'))
            for rid, cd, pp, p2 in random.sample(sel, min(ARG or 40, len(sel))):
                h, st, e, surf, g, meth = c.execute('select hadith_id,start,end,surface,guess_narrator_id,id_method from chain_mention where rowid=?', (rid,)).fetchone()
                text = c.execute('select text from hadith where id=?', (h,)).fetchone()[0]
                print(h, round(pp, 2), meth, '|', text[max(0, st - 30):st].replace('\n', ' '), '[[', surf, ']]', text[e:e + 25].replace('\n', ' '), '=>', cd, (names.get(cd) or '')[:45], '| old guess', g)
        else:
            nA = nG = 0
            for rid, cd, pp, p2 in rows:
                r = c.execute('select narrator_id,guess_narrator_id,id_method from chain_mention where rowid=?', (rid,)).fetchone()
                if not r or r[0]: continue                                  # already asserted since scoring
                c.execute("insert into surgery_log(step,kind,key,old,new) values('fix_26','mention',?,?,?)", (rid, f'{r[0]}|{r[1]}|{r[2]}', cd))
                if pp >= ASSERT_P: c.execute("update chain_mention set narrator_id=?, id_method='ranker', id_confidence=? where rowid=?", (cd, round(pp, 3), rid)); nA += 1
                elif r[1] != cd and (not r[1] or pp >= 0.6): c.execute("update chain_mention set guess_narrator_id=?, guess_confidence=?, id_method=case when id_method like 'demoted:%' then id_method else 'candidates_only' end where rowid=?", (cd, round(pp, 3), rid)); nG += 1
                if (nA + nG) % 20000 == 0: db.commit()
            db.commit(); print('asserted', nA, 'guessed', nG)
