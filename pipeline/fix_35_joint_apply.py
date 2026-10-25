"""Apply the joint tagger (models/joint.pt, else joint_cv.pt) to every chained hadith.
  python pipeline/fix_35_joint_apply.py score [N]   # resumable; writes labels/joint_pred.db (hadith_id, ms, me, conf, n_tokens, spans json [[a,b,minp],...]) in text offsets
  python pipeline/fix_35_joint_apply.py pilot [N] [seed]   # eye check of would-be boundary changes
  python pipeline/fix_35_joint_apply.py apply        # writes matn_start / matn_end where conf >= CONF (surgery_log step fix_35, flags joint_start / joint_end)
Rules: gold never changes; the move must change more than connector words; end change must add/remove Arabic letters; text longer than the 450-token window never gets a new end
unless the model's end lies inside the window; a start that moves earlier may not swallow a chain mention."""
from paths import *
from fix_34_joint_model import Net, tok_feats, batchify, decode, predict, MAXTOK2
from boundary_metric import conn_only
from labels_lib import plain
import sqlite3, sys, os, re, json, random, time, collections, torch
MODE = sys.argv[1]; ARG = int(sys.argv[2]) if len(sys.argv) > 2 else None
CONF = 0.9; PRED = 'labels/joint_pred.db'; DBP = OUT + 'hadith_master.db'
AR = re.compile('[ء-يٱ-ە]'); TOK = re.compile(r'\S+')
def model():
    net = Net(); net.load_state_dict(torch.load('models/joint.pt' if os.path.exists('models/joint.pt') else 'models/joint_cv.pt')); net.eval(); return net
if MODE == 'score':
    net = model(); c = sqlite3.connect('file:' + DBP + '?mode=ro', uri=True)
    p = sqlite3.connect(PRED); p.execute('create table if not exists pred(hadith_id text primary key, ms int, me int, conf real, ntok int, spans text)')
    have = {r[0] for r in p.execute('select hadith_id from pred')}
    ids = [r[0] for r in c.execute("select id from hadith where chain_tier in ('A','B','C') order by id") if r[0] not in have]
    if ARG: ids = ids[:ARG]
    print('to score', len(ids), flush=True); t0 = time.time(); done = 0
    from fix_34_joint_model import conf as confd
    for k in range(0, len(ids), 2000):
        chunk = ids[k:k + 2000]; ex = []
        for h in chunk:
            text = c.execute('select text from hadith where id=?', (h,)).fetchone()[0]
            offs = [(m.start(), m.end()) for m in TOK.finditer(text)][:MAXTOK2]
            e = dict(id=h, tokens=[text[a:b] for a, b in offs], offs=offs, tags=[0] * len(offs)); e['ids'], e['fl'] = tok_feats(e['tokens']); ex.append(e)
        order = sorted(range(len(ex)), key=lambda i: len(ex[i]['tokens'])); res = {}
        for i in range(0, len(order), 32):
            b = [ex[j] for j in order[i:i + 32]]
            for e, P in zip(b, predict(net, b)): res[e['id']] = (e, P)
        rows = []
        for h in chunk:
            e, P = res[h]
            if not e['tokens']: rows.append((h, None, None, 0.0, 0, '[]')); continue
            sp, ms, me = decode(P)
            spans = [[e['offs'][a][0], e['offs'][b - 1][1], float(P[a:b].max(1).min())] for a, b in sp]
            rows.append((h, e['offs'][ms][0] if ms is not None else None, e['offs'][me - 1][1] if me else None, confd(P, ms, me), len(e['tokens']), json.dumps(spans)))
        p.executemany('insert or ignore into pred values(?,?,?,?,?,?)', rows); p.commit(); done += len(chunk)
        print(f'{done:,}/{len(ids):,} {time.time() - t0:.0f}s', flush=True)
else:
    db = sqlite3.connect(DBP, timeout=120); c = db.cursor(); p = sqlite3.connect(PRED)
    gold = {json.loads(l)['hadith_id'] for l in open('gold/gold_chains.jsonl', encoding='utf-8')}
    chg = []; skip = collections.Counter()
    for h, ms_p, me_p, cf, nt, _ in p.execute('select * from pred where conf>=?', (CONF,)):
        if h in gold: skip['gold'] += 1; continue
        text, ms, me, fl = c.execute('select text,matn_start,matn_end,flags from hadith where id=?', (h,)).fetchone(); me0 = me if me is not None else len(text)
        if ms_p is None or me_p is None: continue
        nms, nme = ms, me
        if ms is None or (abs(ms_p - ms) > 3 and not conn_only(text, ms, ms_p)): nms = ms_p
        trunc = nt >= MAXTOK2 and me_p >= len(text) - 5
        if not trunc and abs(me_p - me0) > 10 and not conn_only(text, me0, me_p):
            a, b = sorted((me_p, me0))
            if not AR.search(text[a:b]): skip['punct_only_end'] += 1
            elif me_p > me0 and (me_p - me0 > 25 or re.search(r'حدثنا|اخبرنا|انبانا|ثنا|نا ', plain(text[me0:me_p])[0])): skip['rej_end_later'] += 1
            else: nme = me_p
        if nms is not None and ms is not None and nms < ms and c.execute('select 1 from chain_mention where hadith_id=? and start is not null and coalesce(chain_no,1)=1 and end>? and start<? limit 1', (h, nms, ms)).fetchone(): nms = ms; skip['mention_in_matn'] += 1
        if nms is not None and nme is not None and nms >= nme: skip['start>=end'] += 1; continue
        if nms == ms and nme == me: continue
        chg.append((h, text, ms, me, nms, nme, fl))
    print('would change', len(chg), '| start', sum(1 for x in chg if x[4] != x[2]), '| end', sum(1 for x in chg if x[5] != x[3]), dict(skip))
    if MODE == 'pilot':
        random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 5)
        for h, text, ms, me, nms, nme, fl in random.sample(chg, min(ARG or 30, len(chg))):
            if nms != ms:
                a, b = sorted((ms or 0, nms)); print(h, 'START', 'later' if nms > (ms or 0) else 'earlier', '|', text[max(0, a - 40):a].replace('\n', ' '), '[[', text[a:b][:100].replace('\n', ' '), ']]', text[b:b + 30].replace('\n', ' '))
            if nme != me:
                m0 = me if me is not None else len(text); a, b = sorted((m0, nme)); print(h, 'END  ', 'earlier' if nme < m0 else 'later', '|', text[max(0, a - 40):a].replace('\n', ' '), '[[', text[a:b][:120].replace('\n', ' '), ']]', text[b:b + 20].replace('\n', ' '))
    else:
        n = 0
        for h, text, ms, me, nms, nme, fl in chg:
            if nms != ms: c.execute("insert into surgery_log(step,kind,key,old,new) values('fix_35','matn_start',?,?,?)", (h, ms, nms)); c.execute('update hadith set matn_start=? where id=?', (nms, h))
            if nme != me: c.execute("insert into surgery_log(step,kind,key,old,new) values('fix_35','matn_end',?,?,?)", (h, me, nme)); c.execute('update hadith set matn_end=? where id=?', (nme, h))
            c.execute('update hadith set flags=? where id=?', (((fl or '') + (' joint_start' if nms != ms else '') + (' joint_end' if nme != me else '')).strip(), h)); n += 1
            if n % 20000 == 0: db.commit(); print(n, flush=True)
        db.commit(); print('applied', n)
