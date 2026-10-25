"""Phase 2 - score every hadith with the matn start / end models and (separately) apply the confident changes.
  python pipeline/fix_22_apply_boundaries.py score [N]     # writes labels/boundary_pred.db (N = only first N hadith, for timing)
  python pipeline/fix_22_apply_boundaries.py pilot [N]     # prints N random would-be changes with context (eye check)
  python pipeline/fix_22_apply_boundaries.py apply         # writes thresholds START_P / END_P changes to the DB, logged in surgery_log (step fix_22)
Rules: gold hadith never change; an end change must add/remove at least one Arabic letter (punctuation-only differences are left as they are);
a start change that would pull a chain mention into the matn is skipped; the new start must stay before the new end."""
from paths import *
from boundary_lib import build
import sqlite3, sys, os, pickle, re, json, random, time, collections
from labels_lib import plain
import numpy as np
from multiprocessing import Pool
MODE = sys.argv[1]; ARG = int(sys.argv[2]) if len(sys.argv) > 2 else None
START_P, END_P = 0.97, 0.90
PRED = 'labels/boundary_pred.db'
DBP = OUT + 'hadith_master.db'
AR = re.compile('[ء-يٱ-ە]')
_m = {}
def init():
    for t in ('start', 'end'): _m[t] = pickle.load(open(f'models/{t}_model.pkl', 'rb'))
    _m['c'] = sqlite3.connect('file:' + DBP + '?mode=ro', uri=True)
def best(t, text, anchor, ments, lower):
    b = build(text, anchor, None, ments, t, lower)
    if not b: return None, 0.0
    m, hs = _m[t]; p = m.predict_proba(hs.transform(b[0]))[:, 1]; i = int(np.argmax(p)); return b[2][i], float(p[i])
def work(ids):
    c = _m['c']; out = []
    for h in ids:
        text, ms, me = c.execute('select text,matn_start,matn_end from hadith where id=?', (h,)).fetchone()
        ments = c.execute('select start,end from chain_mention where hadith_id=? and start is not null and coalesce(chain_no,1)=1 order by start', (h,)).fetchall()
        sp, spp = best('start', text, ms, ments, 0)
        ep, epp = best('end', text, me if me is not None else len(text), ments, ms)
        out.append((h, sp, spp, ep, epp))
    return out
if __name__ == '__main__':
    if MODE == 'score':
        # resumable: scores only hadith that are not yet in labels/boundary_pred.db; ARG = max number of NEW hadith to score in this run
        c = sqlite3.connect('file:' + DBP + '?mode=ro', uri=True)
        gold = {json.loads(l)['hadith_id'] for l in open('gold/gold_chains.jsonl', encoding='utf-8')}
        os.makedirs('labels', exist_ok=True)
        p = sqlite3.connect(PRED); p.execute('create table if not exists pred(hadith_id text primary key, start_pred int, start_p real, end_pred int, end_p real)')
        have = {r[0] for r in p.execute('select hadith_id from pred')}
        ids = [r[0] for r in c.execute("select id from hadith where matn_start is not null and chain_tier in ('A','B','C') order by id") if r[0] not in gold and r[0] not in have]
        print('to score', len(ids), flush=True)
        if ARG: ids = ids[:ARG]
        c.close()
        BATCH = 10000; t0 = time.time(); done = 0
        with Pool(2, initializer=init, maxtasksperchild=50) as pool:
            for k in range(0, len(ids), BATCH):
                chunks = [ids[i:i + 250] for i in range(k, min(k + BATCH, len(ids)), 250)]
                for res in pool.imap(work, chunks): p.executemany('insert or ignore into pred values(?,?,?,?,?)', res); done += len(res)
                p.commit(); print(f'{done:,}/{len(ids):,} {time.time() - t0:.0f}s', flush=True)
        print('scored', done)
    elif MODE in ('pilot', 'apply'):
        db = sqlite3.connect(DBP, timeout=120, uri=False); c = db.cursor()
        p = sqlite3.connect(PRED)
        gold = {json.loads(l)['hadith_id'] for l in open('gold/gold_chains.jsonl', encoding='utf-8')}
        rows = p.execute('select * from pred').fetchall()
        chg = []; skip = collections.Counter()
        for h, sp, spp, ep, epp in rows:
            if h in gold: skip['gold'] += 1; continue
            text, ms, me, fl = c.execute('select text,matn_start,matn_end,flags from hadith where id=?', (h,)).fetchone()
            me0 = me if me is not None else len(text)
            nms, nme = ms, me
            if sp is not None and spp >= START_P and abs(sp - ms) > 2: nms = sp
            if ep is not None and epp >= END_P and abs(ep - me0) > 2:
                a, b = sorted((ep, me0))
                if AR.search(text[a:b]): nme = ep
                else: skip['punct_only_end'] += 1
            if nms < ms:                                           # start moves earlier: reject complementizer 'أن' and quotation formulas (gold convention keeps them out of the matn)
                added = text[nms:ms]; ap = plain(added)[0].strip(); aw = added.strip()
                if aw and ap in ('ان', 'انه', 'انها', 'انهم', 'انك', 'انا', 'انهما', 'انني', 'اني') and aw[0] in 'أٱ': nms = ms; skip['rej_an'] += 1
                elif re.search(r'قال|يقول|سمعت|حدث|اخبر', ap) and aw.rstrip().endswith((':', '"', '،')): nms = ms; skip['rej_formula_added'] += 1
            if nme is not None and nme > me0 and nme != me:        # end moves later: only a short stretch without chain verbs
                added = text[me0:nme]
                if len(added) > 25 or re.search(r'حدثنا|اخبرنا|انبانا|ثنا|نا ', plain(added)[0]): nme = me; skip['rej_end_later'] += 1
            if nms == ms and nme == me: continue
            if nms < ms:                                           # matn grows to the left: no chain mention may fall into the new part
                if c.execute('select 1 from chain_mention where hadith_id=? and start is not null and coalesce(chain_no,1)=1 and end>? and start<? limit 1', (h, nms, ms)).fetchone(): skip['mention_in_matn'] += 1; nms = ms
            if nms >= (nme if nme is not None else len(text)): skip['start>=end'] += 1; continue
            if nms == ms and nme == me: continue
            chg.append((h, text, ms, me, nms, nme, fl))
        print('would change', len(chg), 'of', len(rows), '| skipped', skip, '| start changes', sum(1 for x in chg if x[4] != x[2]), '| end changes', sum(1 for x in chg if x[5] != x[3]))
        if MODE == 'pilot':
            random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 5)
            for h, text, ms, me, nms, nme, fl in random.sample(chg, min(ARG or 30, len(chg))):
                if nms != ms:
                    a, b = sorted((ms, nms)); print(h, 'START', 'later' if nms > ms else 'earlier', '|', text[max(0, a - 40):a].replace('\n', ' '), '[[', text[a:b][:100].replace('\n', ' '), ']]', text[b:b + 30].replace('\n', ' '))
                if nme != me:
                    m0 = me if me is not None else len(text); a, b = sorted((m0, nme)); print(h, 'END  ', 'earlier' if nme < m0 else 'later', '|', text[max(0, a - 40):a].replace('\n', ' '), '[[', text[a:b][:120].replace('\n', ' '), ']]', text[b:b + 20].replace('\n', ' '))
        else:
            n = 0
            for h, text, ms, me, nms, nme, fl in chg:
                if nms != ms:
                    c.execute("insert into surgery_log(step,kind,key,old,new) values('fix_22','matn_start',?,?,?)", (h, ms, nms))
                    c.execute('update hadith set matn_start=? where id=?', (nms, h))
                if nme != me:
                    c.execute("insert into surgery_log(step,kind,key,old,new) values('fix_22','matn_end',?,?,?)", (h, me, nme))
                    c.execute('update hadith set matn_end=? where id=?', (nme, h))
                fl2 = ((fl or '') + (' model_start' if nms != ms else '') + (' model_end' if nme != me else '')).strip()
                c.execute('update hadith set flags=? where id=?', (fl2, h)); n += 1
                if n % 20000 == 0: db.commit(); print(n, flush=True)
            db.commit(); print('applied', n)
