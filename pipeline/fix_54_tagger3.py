"""Joint tagger v3: retrain on the old training set + ALL agent re-parses (reparse_pilot, reparse1, reparse2, reparse3 [tranche 1], reparse4g [tranche 2]) and test on 200 held-out RISKY hadith
(reparse4g chunks 14-18) against the agent lists as gold.  Three systems are compared on that hold-out: the DB chain as it was BEFORE the rewrite (October-12 backup), the old tagger, the new tagger.
  python pipeline/fix_54_tagger3.py train [epochs]   # models/joint3.pt
  python pipeline/fix_54_tagger3.py eval             # DB-before vs OLD vs NEW on the risky hold-out (+ the earlier random hold-out)"""
import os, sys
os.environ.setdefault('TORCH_THREADS', '2')
sys.argv = [sys.argv[0], sys.argv[1], *(sys.argv[2:3] or ['8'])]
from paths import *
import fix_46_retrain_joint as T
from fix_33_joint_data import TOK, MAXTOK
from fix_34_joint_model import Net, prep, predict, decode, train
from labels_lib import find
import sqlite3, json, glob, collections, torch, random
MARK = '⟦MATN⟧'; BACKUP = OUT + 'hadith_master.PRE_AUDIT_P0_20261023.db'; CUR = OUT + 'hadith_master.db'
SETS = [('labels/reparse2', 'labels/reparse2_out'), ('labels/reparse3', 'labels/reparse3_out'), ('labels/reparse4g', 'labels/reparse4g_out')]
HOLD_CHUNKS = {f'chunk_{k:04d}' for k in range(14, 19)}
def agent_examples(sets, only_chunks=None, skip_chunks=None):
    c = sqlite3.connect('file:' + BACKUP + '?mode=ro', uri=True); out = []; st = collections.Counter()
    for cd, od in sets:
        items = {}
        for f in sorted(glob.glob(os.path.join(cd, 'chunk_*.json'))):
            nm = os.path.basename(f)[:-5]
            if (only_chunks and nm not in only_chunks) or (skip_chunks and nm in skip_chunks and cd.endswith('reparse4g')): continue
            for it in json.load(open(f, encoding='utf-8')): items[it['id']] = it
        A = T.loadjl(od)
        for h, o in A.items():
            if h not in items or not o.get('transmitters'): continue
            text, tier, trad = c.execute('select text,chain_tier,tradition from hadith where id=?', (h,)).fetchone(); ms0 = items[h]['text'].find(MARK)
            if ms0 < 0: st['no marker'] += 1; continue
            spans = []; pos = 0; ok = True
            for t in o['transmitters']:
                r = find(text[:ms0 + 700][pos:], t['text'])
                if not r: ok = False; break
                spans.append((pos + r[0], pos + r[1])); pos += r[1]
            if not ok: st['not found'] += 1; continue
            ms = ms0
            if o.get('matn_ok') is False:
                r = find(text, o.get('matn_start_phrase', ''))
                if not r: st['phrase not found'] += 1; continue
                ms = r[0]
            spans = sorted(s for s in spans if s[0] < ms + 3)
            if not spans: continue
            toks = [(m.start(), m.end()) for m in TOK.finditer(text)][:MAXTOK]; tags = []; prev = None; first = True
            for ts, te in toks:
                if ts >= ms: tags.append(3 if first else -100); first = False; prev = None; continue
                t = 0
                for j, (a, e) in enumerate(spans):
                    if ts < e and te > a: t = 1 if j != prev else 2; prev = j; break
                else: prev = None
                tags.append(t)
            db = [a for a, in c.execute('select start from chain_mention where hadith_id=? and start is not null and start<?', (h, ms + 3))]
            out.append(dict(id=h, tokens=[text[a:b] for a, b in toks], offs=toks, tags=tags, spans=spans, ms=ms, me=len(text), tier=tier, tradition=trad, db_before=db)); st['ok'] += 1
    print('agent examples', dict(st), flush=True); return out
if __name__ == '__main__':
    MODE = sys.argv[1]; EP = int(sys.argv[2])
    tr_old, hold_old = T.split(); hold_ids_old = {e['id'] for e in hold_old}
    hold = agent_examples(SETS[2:], only_chunks=HOLD_CHUNKS); hold_ids = {e['id'] for e in hold}
    if MODE == 'train':
        extra = agent_examples(SETS[:2]) + agent_examples(SETS[2:], skip_chunks=HOLD_CHUNKS) + T.reparse_examples(hold_ids_old | hold_ids)
        extra = [e for e in extra if e['id'] not in hold_ids and e['id'] not in hold_ids_old]
        tr = tr_old + extra; prep(tr); print(len(tr_old), 'old +', len(extra), 'agent/other =', len(tr), 'train hadith | risky hold-out', len(hold), flush=True)
        net = train(tr, EP); torch.save(net.state_dict(), 'models/joint3.pt'); print('saved models/joint3.pt')
    else:
        prep(hold); close = T.close
        n = len(hold); ex = tol = 0
        for e in hold:                                        # system 0: the DB chain before the rewrite
            gold = [a for a, b in e['spans'] if a < e['ms'] + 3]; pred = e['db_before']
            s, t = T.tol_ok(pred, gold, e); ex += s; tol += (s or t)
        print(f'DB-before  whole chain exact {ex / n:.3f} | tolerant {tol / n:.3f}  (n={n}, risky hold-out, gold = agent lists)')
        for name, path in (('OLD tagger', 'models/joint_cv.pt'), ('NEW tagger', 'models/joint3.pt')):
            net = Net(); net.load_state_dict(torch.load(path)); net.eval(); T.evaluate(net, hold, name)
        prep(hold_old)
        for name, path in (('OLD tagger', 'models/joint_cv.pt'), ('NEW tagger', 'models/joint3.pt')):
            net = Net(); net.load_state_dict(torch.load(path)); net.eval(); T.evaluate(net, hold_old, name + ' [earlier random hold-out]')
