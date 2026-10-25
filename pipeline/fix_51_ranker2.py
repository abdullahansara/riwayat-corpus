"""P5 - narrator-ID ranker v2, trained on ALL Claude labels in the DB (claude_label_mention, kind='narrator', choice = narrator id; ~38K) instead of the 1.7K-hadith pilot set.
Mention features are rebuilt from the current chain (the mention's own ID/guess/method are hidden to avoid leakage); extra chain-context features: second-order
neighbours, shared teacher/student overlap with neighbours, tradition and book match.
  python pipeline/fix_51_ranker2.py recall           # label coverage of the candidate generator
  python pipeline/fix_51_ranker2.py cv               # 5-fold CV by hadith, precision/recall at thresholds
  python pipeline/fix_51_ranker2.py fit              # models/ranker2.pkl
  python pipeline/fix_51_ranker2.py score [FROM]     # unresolved mentions -> labels/ranker2_pred.db (resumable)
  python pipeline/fix_51_ranker2.py pilot [N] [seed] | apply [P]"""
from paths import *
from id_lib import Ctx, candidates, feats, norm, compatible, STOP
import sqlite3, sys, os, json, pickle, random, time, itertools, collections, math
import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.ensemble import HistGradientBoostingClassifier
DBP = OUT + 'hadith_master.db'; PRED = 'labels/ranker2_pred.db'
SKIP = set('ابي ابيه ابوه اباه جدي جده عمي عمه خالي خالتي امه امي اخي اخيه ابنه ابني ابيها ابيهم جدها رجل رجلا امراة امرأة رجال من'.split())

HON = set('عليه عليهم عليهما السلام ع رضي الله عنه عنها عنهم رحمه ره ص صلى وسلم'.split())
def norm2(s):
    """norm + unify kunya cases (ابي/ابا -> ابو), drop honorifics, strip a leading و/ل/ف/ب attached to the first word"""
    w = [{'ابي': 'ابو', 'ابا': 'ابو', 'ابى': 'ابو'}.get(x, x) for x in norm(s).split() if x not in HON]
    if w and len(w[0]) > 3 and w[0][0] in 'ولفب' and w[0][1:2] != 'ل' or (w and w[0].startswith('لا') and len(w[0]) > 4): w[0] = w[0][1:]
    return ' '.join(w)
class Ctx2(Ctx):
    def __init__(self, c):
        super().__init__(c)
        self.exact2 = collections.defaultdict(set); self.prefix2 = collections.defaultdict(set)
        for nid, nn in c.execute("select narrator_id,norm from narrator_name where norm is not null and type!='observed' and length(norm)<80"):
            n2 = norm2(nn); t = n2.split()
            if not t: continue
            self.exact2[n2].add(nid)
            for L in range(2, min(len(t), 7)): self.prefix2[' '.join(t[:L])].add(nid)
        for nid, i in self.info.items(): self.exact2[norm2(i[0])].add(nid)
def cands2(ctx, surface, prev_id, limit=16):
    """-> list of (cand, mtype) mtype 0 exact, 1 sub-span, 2 prefix-of-form, 3 graph edge"""
    t = norm2(surface).split(); out = {}
    if not t: return []
    key = ' '.join(t)
    for x in sorted(ctx.exact2.get(key, ()), key=lambda x: -ctx.pop.get(x, 0))[:8]: out.setdefault(x, 0)
    if len(t) >= 2:
        for x in sorted(ctx.prefix2.get(key, ()), key=lambda x: -ctx.pop.get(x, 0))[:4]: out.setdefault(x, 2)
        got = 0
        for L in range(len(t) - 1, 1, -1):
            for i in range(0, len(t) - L + 1):
                for x in sorted(ctx.exact2.get(' '.join(t[i:i + L]), ()), key=lambda x: -ctx.pop.get(x, 0))[:3]:
                    if x not in out and got < 4: out[x] = 1; got += 1
    if prev_id:
        st = set(w for w in t if w not in STOP)
        for tt, n in sorted(ctx.out_edges.get(prev_id, {}).items(), key=lambda x: -x[1])[:3]:
            if tt not in out and tt in ctx.info and st & set(ctx.info[tt][0].split()): out[tt] = 3
    sn = norm(surface)
    return [(x, m) for x, m in out.items() if x in ctx.info and (m != 3 or compatible(ctx, sn, x))][:limit]
def ext_feats(ctx, cand, prev2, next2, prev_id, next_id, book_trad):
    """second-order chain context: shared neighbours in the narrator graph"""
    f = {}
    f['e_prev2'] = math.log1p(ctx.edge.get((prev2, cand), 0)) if prev2 else -1.0
    f['e_next2'] = math.log1p(ctx.edge.get((cand, next2), 0)) if next2 else -1.0
    out = ctx.out_edges.get(cand, {})                                   # teachers of cand
    f['n_teachers'] = math.log1p(len(out))
    if prev_id: f['prev_shares_teacher'] = float(bool(out) and any(t in out for t in ctx.out_edges.get(prev_id, {})))
    else: f['prev_shares_teacher'] = -1.0
    f['next_is_teacher'] = float(next_id in out) if next_id else -1.0
    return f
def mention_rows(ctx, M, trad, book):
    """M: list of dict(rid,start,surface,nid,gid,meth) in chain order; yields (k, cands, [feat dicts]) for mentions"""
    out = []
    for k, m in enumerate(M):
        prev_ids = [x['nid'] for x in M[:k] if x['nid']]; next_ids = [x['nid'] for x in M[k + 1:] if x['nid']]
        prev_id = prev_ids[-1] if prev_ids else None; next_id = next_ids[0] if next_ids else None
        prev2 = prev_ids[-2] if len(prev_ids) > 1 else None; next2 = next_ids[1] if len(next_ids) > 1 else None
        cm = cands2(ctx, m['surface'], prev_id); cands = [x for x, _ in cm]
        if not cands: out.append((k, [], [])); continue
        fl = []; nsurf = len(norm2(m['surface']).split())
        for cd, mt in cm:
            f = feats(ctx, m['surface'], cd, cands, None, None, None, prev_id, next_id, trad, k, len(M)); f.update(ext_feats(ctx, cd, prev2, next2, prev_id, next_id, trad))
            for q in range(4): f['mt%d' % q] = float(mt == q)
            f['exact2'] = float(norm2(m['surface']) in ctx.exact2 and cd in ctx.exact2[norm2(m['surface'])]); f['nsurf'] = nsurf; fl.append(f)
        out.append((k, cands, fl))
    return out
def chain_of(c, h):
    rows = c.execute('select rowid,start,surface,narrator_id,guess_narrator_id,id_method,coalesce(chain_no,1) from chain_mention where hadith_id=? and start is not null order by 7,start', (h,)).fetchall()
    return [dict(rid=r[0], start=r[1], surface=r[2], nid=r[3], gid=r[4], meth=r[5], cn=r[6]) for r in rows]
def mk(): return HistGradientBoostingClassifier(max_iter=250, learning_rate=0.08, max_leaf_nodes=20, l2_regularization=1.0, random_state=0)
def truth_of(c):
    """label truth: for mentions currently asserted by claude_label use the mention's own (post-merge) narrator_id, else the label mapped through merges"""
    merge = dict(c.execute('select old_id,new_id from narrator_merge')); cur = {}
    for h, st, nid in c.execute("select hadith_id,start,narrator_id from chain_mention where id_method='claude_label' and narrator_id is not null"): cur[(h, st)] = nid
    class _M(dict):
        def get(self, k, d=None):
            seen = set()
            while k in dict.keys(self) and k not in seen: seen.add(k); k = dict.__getitem__(self, k)
            return k if seen else d
    return _M(merge), cur
def build_training(c, ctx):
    lab = collections.defaultdict(dict)
    for h, st, ch, src in c.execute("select hadith_id,start,choice,source from claude_label_mention where kind='narrator' and choice like 'N%'"): lab[h][st] = ch
    rows = []; stats = collections.Counter(); merge, curt = truth_of(c)
    for h, L in lab.items():
        hr = c.execute('select tradition,book from hadith where id=?', (h,)).fetchone()
        if not hr: continue
        M0 = chain_of(c, h)
        for var in (0, 1):                      # var 1: ~half of the OTHER mentions' IDs hidden, like the unresolved chains we will score
            rnd = random.Random(h + str(var))
            M = M0 if var == 0 else [dict(x, nid=(None if (x['start'] not in L and rnd.random() < 0.5) else x['nid'])) for x in M0]
            res = mention_rows(ctx, M, hr[0], hr[1])
            for (k, cands, fl), m in zip(res, M):
                if m['start'] not in L: continue
                y = curt.get((h, m['start'])) or merge.get(L[m['start']], L[m['start']])
                if not cands: stats['no candidates'] += 1; continue
                if y not in cands: stats['label not in candidates'] += 1; continue
                stats['usable'] += 1
                for cd, f in zip(cands, fl): rows.append((h, (h, m['start'], var), cd, f, int(cd == y)))
    return rows, stats
if __name__ == '__main__':
    MODE = sys.argv[1]
    c = sqlite3.connect('file:' + DBP + '?mode=ro', uri=True); t0 = time.time()
    if MODE in ('recall', 'cv', 'fit'):
        ctx = Ctx2(c); print('ctx loaded', round(time.time() - t0), 's', flush=True)
        rows, stats = build_training(c, ctx); print(dict(stats), 'candidate rows', len(rows), round(time.time() - t0), 's', flush=True)
        if MODE == 'recall': sys.exit()
        dv = DictVectorizer(sparse=False); X = dv.fit_transform([r[3] for r in rows]); y = np.array([r[4] for r in rows])
        hs = sorted(set(r[0] for r in rows)); random.seed(0); random.shuffle(hs); fold = {h: i % 5 for i, h in enumerate(hs)}
        keys = [r[1] for r in rows]
        if MODE == 'cv':
            pred = {}
            for f in range(5):
                te = np.array([fold[r[0]] == f for r in rows]); tr = ~te
                p = mk().fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
                for r, pp in zip([r for r, t in zip(rows, te) if t], p): pred.setdefault(r[1], []).append((pp, r[4]))
            res = []
            for k, v in pred.items():
                if k[2] != 1: continue                      # evaluate on the masked variant only
                v.sort(reverse=True); res.append((v[0][0], bool(v[0][1])))
            n = len(res); print(f'MASKED-context test: mentions {n}; top-1 accuracy {sum(r[1] for r in res) / n:.3f}')
            for th in (0.5, 0.7, 0.8, 0.85, 0.9, 0.95, 0.98):
                sel = [r for r in res if r[0] >= th]
                if sel: print(f'  p>={th}: {len(sel)} mentions ({len(sel) / n:.1%}); precision {sum(r[1] for r in sel) / len(sel):.3f}')
        else:
            os.makedirs('models', exist_ok=True); pickle.dump((mk().fit(X, y), dv), open('models/ranker2.pkl', 'wb')); print('saved models/ranker2.pkl', round(time.time() - t0), 's')
    elif MODE == 'score':
        ctx = Ctx2(c); m, dv = pickle.load(open('models/ranker2.pkl', 'rb'))
        gold = {json.loads(l)['hadith_id'] for l in open('gold/gold_chains.jsonl', encoding='utf-8')}
        p = sqlite3.connect(PRED); p.execute('create table if not exists pred(rid int primary key, cand text, p real, p2 real)'); p.execute('create table if not exists done(hadith_id text primary key)')
        done = {r[0] for r in p.execute('select hadith_id from done')}
        hids_all = [r[0] for r in c.execute("select distinct hadith_id from chain_mention where narrator_id is null and node_key is null and start is not null order by 1")]
        print('hadith with unresolved mentions', len(hids_all), 'already done', len(done), flush=True)
        buf, keys, hb, nm = [], [], [], 0
        def flush():
            global buf, keys, hb
            if buf:
                pr = m.predict_proba(dv.transform(buf))[:, 1]; best = {}
                for (rid, cd), pp in zip(keys, pr): best.setdefault(rid, []).append((float(pp), cd))
                p.executemany('insert or replace into pred values(?,?,?,?)', [(rid, v[0][1], v[0][0], v[1][0] if len(v) > 1 else 0.0) for rid, v in ((r, sorted(v, reverse=True)) for r, v in best.items())])
            p.executemany('insert or ignore into done values(?)', [(h,) for h in hb]); p.commit(); buf, keys, hb = [], [], []
        for i, h in enumerate(hids_all):
            if h in done or h in gold or h < os.environ.get('FROM', ''): continue
            hr = c.execute('select tradition,book from hadith where id=?', (h,)).fetchone(); M = chain_of(c, h)
            for (k, cands, fl), mm in zip(mention_rows(ctx, M, hr[0], hr[1]), M):
                if mm['nid'] or mm['surface'] is None or norm(mm['surface']) in SKIP or not cands: continue
                if mm['meth'] and ('relative' in mm['meth'] or 'anonymous' in mm['meth']): continue
                for cd, f in zip(cands, fl): buf.append(f); keys.append((mm['rid'], cd))
                nm += 1
            hb.append(h)
            if len(hb) >= 2000: flush(); print(f'{i + 1:,}/{len(hids_all):,} hadith, {nm:,} mentions, {time.time() - t0:.0f}s', flush=True)
        flush(); print('scored', nm, 'mentions')
    elif MODE == 'filter':
        # exclusion rules from the 2026-10-23 gate reviews (162 reviewed p>=0.95 items: 93.7% -> ~96.6% decided precision):
        #  bare surface (<=1 content token) as the LAST chain element (story persons / addressees), chronology conflict with identified neighbours, surface names not in the candidate's forms
        HEADW = {'ابن', 'بن', 'و', 'ابو', 'ابي', 'ام', 'ابا'}
        death = dict(c.execute('select id,death_year from narrator where death_year is not null')); names = dict(c.execute('select id,std_name from narrator'))
        forms = collections.defaultdict(set)
        p = sqlite3.connect(PRED); rows = p.execute('select rid,cand,p from pred where p>=0.97').fetchall(); print('p>=0.97', len(rows), flush=True)
        byh = collections.defaultdict(list)
        for rid, cd, pp in rows:
            h = c.execute('select hadith_id from chain_mention where rowid=?', (rid,)).fetchone()
            if h: byh[h[0]].append((rid, cd, pp))
        out = sqlite3.connect('labels/ranker2_final.db'); out.execute('drop table if exists sel'); out.execute('create table sel(rid int primary key, cand text, p real)'); out.execute('drop table if exists excl'); out.execute('create table excl(rid int primary key, why text)')
        stats = collections.Counter(); batch = []; ex = []
        for h, lst in byh.items():
            M = chain_of(c, h); pos = {x['rid']: i for i, x in enumerate(M)}
            for rid, cd, pp in lst:
                k = pos.get(rid)
                if k is None or M[k]['nid']: stats['stale'] += 1; continue
                t = [w for w in norm(M[k]['surface'] or '').split() if w not in HEADW]
                dc = death.get(cd); cn = M[k]['cn']
                prevs = [x for x in M[:k] if x['nid'] and death.get(x['nid']) and x['cn'] == cn]; nxts = [x for x in M[k + 1:] if x['nid'] and death.get(x['nid']) and x['cn'] == cn]
                conflict = bool(dc and ((prevs and (dc > death[prevs[-1]['nid']] + 15 or dc < death[prevs[-1]['nid']] - 80)) or (nxts and (dc < death[nxts[0]['nid']] - 5 or dc > death[nxts[0]['nid']] + 100))))
                if cd not in forms:
                    forms[cd] = [set(norm(names.get(cd) or '').split())] + [set(norm(f).split()) for (f,) in c.execute('select form from narrator_name where narrator_id=? and type!="observed" and length(form)<80', (cd,))]
                def sub(a, b): bb = {x.lstrip('وال') for x in b}; return all(w in b or w.lstrip('وال') in bb for w in a)
                mismatch = not any(sub(set(t), f) for f in forms[cd])            # one single registered form must contain every surface token
                ms = c.execute('select matn_start from hadith where id=?', (h,)).fetchone()[0]
                in_matn = ms is not None and M[k]['start'] is not None and M[k]['start'] >= ms
                last = not any(x['cn'] == cn for x in M[k + 1:])
                why = 'in_matn' if in_matn else 'bare_last' if (len(t) <= 1 and last) else 'conflict' if conflict else 'mismatch' if mismatch else None
                if why: stats[why] += 1; ex.append((rid, why))
                else: stats['kept'] += 1; batch.append((rid, cd, pp))
        out.executemany('insert into sel values(?,?,?)', batch); out.executemany('insert into excl values(?,?)', ex); out.commit(); print(dict(stats))
    else:
        ASSERT_P = float(sys.argv[2]) if MODE == 'apply' and len(sys.argv) > 2 else 0.9
        db = sqlite3.connect(DBP, timeout=120); cc = db.cursor()
        p = sqlite3.connect('labels/ranker2_final.db'); rows = [r + (0,) for r in p.execute('select rid,cand,p from sel where p>=?', (ASSERT_P,)).fetchall()]
        print('predictions >=', ASSERT_P, ':', len(rows))
        if MODE == 'pilot':
            N = int(sys.argv[2]) if len(sys.argv) > 2 else 40; random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 1); names = dict(cc.execute('select id,std_name from narrator'))
            for rid, cd, pp, p2 in random.sample(rows, min(N, len(rows))):
                h, st, e, surf = cc.execute('select hadith_id,start,end,surface from chain_mention where rowid=?', (rid,)).fetchone()
                M = chain_of(cc, h); k = next(i for i, x in enumerate(M) if x['rid'] == rid)
                ctxs = ' | '.join((x['surface'] or '?')[:20] + ('*' if x['nid'] else '') for x in M[max(0, k - 2):k + 3])
                print(h, round(pp, 2), f'"{surf[:30]}" => {cd} {(names.get(cd) or "")[:42]}   ctx: {ctxs}')
        else:
            n = 0
            for rid, cd, pp, p2 in rows:
                r = cc.execute('select narrator_id,guess_narrator_id,id_method from chain_mention where rowid=?', (rid,)).fetchone()
                if not r or r[0]: continue
                cc.execute("insert into surgery_log(step,kind,key,old,new) values('fix_51','mention',?,?,?)", (rid, f'{r[0]}|{r[1]}|{r[2]}', cd))
                cc.execute("update chain_mention set narrator_id=?, id_method='ranker2', id_confidence=?, guess_narrator_id=NULL, guess_confidence=NULL where rowid=?", (cd, round(pp, 3), rid)); n += 1
                if n % 20000 == 0: db.commit()
            db.commit(); print('asserted', n)
