"""Junk-mention filter: decides whether a parsed mention is a real link of the isnad or a matn phrase / story figure / fragment.
Trained on the Claude mention labels (table claude_label_mention: kind narrator|relative|anonymous = real, not_a_narrator = junk).
Features: the 1-3 tokens before the surface (the connector!), the 1-2 tokens after, punctuation before, words in the surface, first/last word, position relative to the matn start (tokens),
index in the chain, whether it is the last mention, id_method group, whether it has a firm ID, whether the surface contains a connector word.
  python pipeline/fix_45_junk_filter.py cv     # precision / recall of 'junk' at thresholds (5-fold CV by hadith)
  python pipeline/fix_45_junk_filter.py fit    # models/junk_filter.pkl
  python pipeline/fix_45_junk_filter.py score  # resumable, SLICE=20000 hadith per call -> labels/junk_pred.db (repeat until 'total done' reaches ~910K)
  python pipeline/fix_45_junk_filter.py pilot [N] [seed]   # N would-be deletions with context (eye check; TAU env, default 0.95)
  python pipeline/fix_45_junk_filter.py apply  # delete mentions with P(junk) >= TAU (full row stored in surgery_log step fix_45), renumber pos, n_narrators
Never touches gold hadith, mentions Claude labelled as real, firm IDs from gold, or mentions of hadith that are the only mention."""
from paths import *
from labels_lib import plain
import sqlite3, sys, re, json, random, pickle, os, collections, time
import numpy as np
from sklearn.feature_extraction import FeatureHasher
from sklearn.linear_model import LogisticRegression
MODE = sys.argv[1]; ARG = int(sys.argv[2]) if len(sys.argv) > 2 else None
DBP = OUT + 'hadith_master.db'; TAU = float(os.environ.get('TAU', '0.95'))
CONNW = set('حدثنا حدثني حدثنى ثنا نا اخبرنا اخبرني اخبرنى انا انبانا انبا قال قالا قالت يقول سمعت عن ح ان انه'.split())
H = FeatureHasher(2 ** 18)
def toks_before(text, a, k=3):
    seg = plain(text[max(0, a - 80):a])[0].split(); return seg[-k:]
def toks_after(text, b, k=2):
    seg = plain(text[b:b + 60])[0].split(); return seg[:k]
def feats(text, ms, a, b, idx, n, last, meth, firm):
    pre = toks_before(text, a); post = toks_after(text, b); sw = plain(text[a:b])[0].split(); f = {}
    for i, t in enumerate(reversed(pre)): f[f'pre{i}_{t}'] = 1
    if pre: f['pre_last_conn'] = int(pre[-1] in CONNW)
    f['pre_any_conn'] = int(any(t in CONNW for t in pre))
    for i, t in enumerate(post): f[f'post{i}_{t}'] = 1
    ch = text[max(0, a - 3):a]; f['punct_before'] = int(bool(re.search(r'[,،:.؛]\s*$', ch))); f['punct_before_any'] = int(bool(re.search(r'[,،:.؛]', text[max(0, a - 6):a])))
    f['n_words'] = min(len(sw), 8); f['first_' + (sw[0] if sw else '')] = 1; f['last_' + (sw[-1] if sw else '')] = 1; f['has_conn'] = int(any(t in CONNW for t in sw))
    d = len(plain(text[b:ms])[0].split()) if ms is not None and b < ms else -len(plain(text[ms:a])[0].split()) if ms is not None else 0
    f['dist_to_matn'] = max(-60, min(60, d)) / 60.0; f['after_matn'] = int(ms is not None and a >= ms); f['idx'] = min(idx, 30) / 30.0; f['is_last'] = int(last); f['is_first'] = int(idx == 0); f['n'] = min(n, 30) / 30.0
    f['meth_' + (meth or 'none').split('+')[0][:22]] = 1; f['firm'] = int(bool(firm))
    return f
def labelled():
    c = sqlite3.connect('file:' + DBP + '?mode=ro', uri=True); X = []; y = []; ids = []
    rows = c.execute("""select l.hadith_id,l.start,l.kind,m.end,m.narrator_id,m.id_method,h.text,h.matn_start
       from claude_label_mention l join chain_mention m on m.hadith_id=l.hadith_id and m.start=l.start and coalesce(m.chain_no,1)=coalesce(m.chain_no,1)
       join hadith h on h.id=l.hadith_id where l.kind in ('narrator','relative','anonymous','not_a_narrator')""").fetchall()
    cnt = {}
    for h, st, kind, en, nid, meth, text, ms in rows:
        if en is None: continue
        if h not in cnt: cnt[h] = c.execute('select count(*) from chain_mention where hadith_id=? and start is not null', (h,)).fetchone()[0]
        idx = c.execute('select count(*) from chain_mention where hadith_id=? and start is not null and start<?', (h, st)).fetchone()[0]
        X.append(feats(text, ms, st, en, idx, cnt[h], idx == cnt[h] - 1, meth, nid)); y.append(1 if kind == 'not_a_narrator' else 0); ids.append(h)
    # pooled agent data: mentions the re-parse agents DELETED outright (no overlapping replacement) are junk; the mentions they kept in re-parsed hadith are real
    try:
        dele = c.execute("select old from surgery_log where step='fix_42' and kind='mention_row'").fetchall(); done = set(ids)
        for (js,) in dele:
            r = json.loads(js); h = r['hadith_id']
            if r.get('start') is None or r.get('end') is None or h in done: continue
            if c.execute('select 1 from chain_mention where hadith_id=? and start<? and end>? limit 1', (h, r['end'], r['start'])).fetchone(): continue
            text, ms = c.execute('select text,matn_start from hadith where id=?', (h,)).fetchone()
            n = c.execute('select count(*) from chain_mention where hadith_id=? and start is not null', (h,)).fetchone()[0]; idx = c.execute('select count(*) from chain_mention where hadith_id=? and start is not null and start<?', (h, r['start'])).fetchone()[0]
            X.append(feats(text, ms, r['start'], r['end'], idx, n + 1, False, r.get('id_method'), r.get('narrator_id'))); y.append(1); ids.append(h + '#del')
        nreal = 0
        for h, text, ms in c.execute("select id,text,matn_start from hadith where flags like '%claude_reparsed%'").fetchall():
            if h in done: continue
            ms_ = c.execute('select start,end,narrator_id,id_method from chain_mention where hadith_id=? and start is not null and end is not null order by coalesce(chain_no,1),start', (h,)).fetchall()
            for i, (a, b, nid, meth) in enumerate(ms_):
                X.append(feats(text, ms, a, b, i, len(ms_), i == len(ms_) - 1, meth, nid)); y.append(0); ids.append(h); nreal += 1
        print('pooled agent data added: junk from re-parse deletions', sum(1 for i in ids if str(i).endswith('#del')), '| real mentions from re-parsed hadith', nreal, flush=True)
    except Exception as ex: print('pooled data skipped:', ex)
    return X, np.array(y), ids
def mk(): return LogisticRegression(C=2.0, max_iter=600, class_weight=None)
if MODE in ('cv', 'fit'):
    X, y, ids = labelled(); print(len(y), 'labelled mentions;', int(y.sum()), f'junk ({y.mean():.1%})', flush=True)
    M = H.transform(X)
    if MODE == 'cv':
        uh = sorted(set(ids)); random.seed(0); random.shuffle(uh); fold = {h: i % 5 for i, h in enumerate(uh)}; fo = np.array([fold[h] for h in ids]); pr = np.zeros(len(y))
        for f in range(5):
            tr = fo != f; pr[~tr] = mk().fit(M[tr], y[tr]).predict_proba(M[~tr])[:, 1]
        for th in (0.5, 0.7, 0.8, 0.9, 0.95, 0.98):
            sel = pr >= th
            if sel.sum(): print(f'  P(junk)>={th}: flags {int(sel.sum())} mentions; precision {y[sel].mean():.3f}; recall {y[sel].sum() / y.sum():.3f}')
    else:
        os.makedirs('models', exist_ok=True); pickle.dump(mk().fit(M, y), open('models/junk_filter.pkl', 'wb')); print('saved models/junk_filter.pkl')
elif MODE == 'score':
    # resumable: scores hadith not yet in labels/junk_pred.db (table done) in slices of SLICE hadith; flagged mentions (P >= 0.9) are stored with their probability
    m = pickle.load(open('models/junk_filter.pkl', 'rb')); db = sqlite3.connect('file:' + DBP + '?mode=ro', uri=True); c = db.cursor(); c2 = db.cursor()
    gold = {json.loads(l)['hadith_id'] for l in open('gold/gold_chains.jsonl', encoding='utf-8')}
    real = {r[0] for r in c.execute("select hadith_id||':'||start from claude_label_mention where kind in ('narrator','relative','anonymous')")}
    out = sqlite3.connect('labels/junk_pred.db'); out.executescript('create table if not exists done(hadith_id text primary key); create table if not exists flag(hadith_id text, rid int, start int, end int, p real);')
    have = {r[0] for r in out.execute('select hadith_id from done')}; SLICE = int(os.environ.get('SLICE', '20000')); t0 = time.time(); nh = 0; buf = []; hs = []
    def flush():
        global buf, hs
        if not buf: return
        P = m.predict_proba(H.transform([x[3] for x in buf]))[:, 1]
        out.executemany('insert into flag values(?,?,?,?,?)', [(x[0], x[1], x[2][0], x[2][1], float(p)) for x, p in zip(buf, P) if p >= 0.9]); out.executemany('insert or ignore into done values(?)', [(h,) for h in hs]); out.commit(); buf = []; hs = []
    for h, text, ms in c2.execute("select id,text,matn_start from hadith where chain_tier in ('A','B','C') and matn_start is not null order by id"):
        if h in have or h in gold: continue
        ms_ = c.execute('select rowid,start,end,narrator_id,id_method from chain_mention where hadith_id=? and start is not null and end is not null order by coalesce(chain_no,1),start', (h,)).fetchall(); n = len(ms_)
        for i, (rid, a_, b_, nid, meth) in enumerate(ms_):
            if n >= 2 and f'{h}:{a_}' not in real: buf.append((h, rid, (a_, b_), feats(text, ms, a_, b_, i, n, i == n - 1, meth, nid)))
        hs.append(h); nh += 1
        if len(buf) >= 4000: flush()
        if nh >= SLICE: break
    flush(); print('scored a slice of', nh, 'hadith', f'({time.time() - t0:.0f}s); total done', out.execute('select count(*) from done').fetchone()[0], flush=True)
else:
    out = sqlite3.connect('labels/junk_pred.db'); db = sqlite3.connect(DBP if MODE == 'apply' else 'file:' + DBP + '?mode=ro', timeout=120, uri=(MODE != 'apply')); c = db.cursor()
    cols = [r[1] for r in c.execute('pragma table_info(chain_mention)')]
    flagged = [(h, rid, a, b, None, p) for h, rid, a, b, p in out.execute('select hadith_id,rid,start,end,p from flag where p>=?', (TAU,))]
    print('flagged as junk at P>=', TAU, ':', len(flagged), 'of', out.execute('select count(*) from done').fetchone()[0], 'hadith scored', flush=True)
    if MODE == 'pilot':
        random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 1)
        for h, rid, a, b, _t, p in random.sample(flagged, min(ARG or 30, len(flagged))):
            text = c.execute('select text from hadith where id=?', (h,)).fetchone()[0]; print(h, round(p, 2), '|', text[max(0, a - 45):a].replace(chr(10), ' '), '[[', text[a:b].replace(chr(10), ' ')[:60], ']]', text[b:b + 25].replace(chr(10), ' '))
    else:
        by = collections.defaultdict(list)
        for h, rid, a, b, _t, p in flagged: by[h].append(rid)
        n = 0
        for h, rids in by.items():
            for rid in rids:
                row = c.execute('select * from chain_mention where rowid=?', (rid,)).fetchone()
                if not row: continue
                c.execute("insert into surgery_log(step,kind,key,old,new) values('fix_45','mention_row',?,?,NULL)", (rid, json.dumps(dict(zip(cols, row)), ensure_ascii=False)))
                c.execute('delete from chain_mention where rowid=?', (rid,))
            for k in {r[0] for r in c.execute('select distinct coalesce(chain_no,1) from chain_mention where hadith_id=?', (h,)).fetchall()}:
                rs = c.execute('select rowid,pos from chain_mention where hadith_id=? and coalesce(chain_no,1)=? and start is not null order by start', (h, k)).fetchall()
                for i, (r, old) in enumerate(rs, 1):
                    if old != i: c.execute('update chain_mention set pos=? where rowid=?', (i, r))
            c.execute("update hadith set n_narrators=(select count(*) from chain_mention where hadith_id=? and coalesce(chain_no,1)=1), flags=trim(coalesce(flags,'')||' junk_filtered') where id=?", (h, h)); n += 1
            if n % 5000 == 0: db.commit(); print(n, flush=True)
        db.commit(); print('applied: removed', len(flagged), 'mentions from', n, 'hadith')
