"""Retrain the joint chain/matn tagger on ALL agent-produced data so far and compare it with the previous model on the SAME untouched hold-out.
Training data = the earlier labelled set (80%, as before) + wave 3 (partial) + the Claude re-parse lists (labels/reparse_pilot_out [only where run A and run B agree], labels/reparse1_out):
for a re-parsed hadith the transmitter spans are the agent's list (or the database list when the agent said ok) and the matn start is the (corrected) start; tokens after the matn start are
masked (-100) because those runs did not label the matn end.  The hold-out is the 20% of the earlier set that no model has seen (same shuffle as fix_34) and the 100 gold chains.
  python pipeline/fix_46_retrain_joint.py train [epochs]    # writes models/joint2_cv.pt after every epoch
  python pipeline/fix_46_retrain_joint.py eval              # old vs new on the hold-out: matn start/end, transmitter spans, whole-chain exact (strict and end-name tolerant)
Env: TORCH_THREADS (default 2)."""
import os
os.environ.setdefault('TORCH_THREADS', '2')
from paths import *
from fix_33_joint_data import build, TOK, MAXTOK
from fix_34_joint_model import Net, prep, predict, decode, train
from labels_lib import find, plain
import sqlite3, sys, json, glob, random, re, collections, torch
MODE = sys.argv[1]; EP = int(sys.argv[2]) if len(sys.argv) > 2 else 8
DBP = OUT + 'hadith_master.db'; MARK = '⟦MATN⟧'
OLD = [('labels/' + a, 'labels/' + b) for a, b in (('pilot', 'pilot_out'), ('wave1', 'wave1_out'), ('defects', 'defects_out'), ('unparsed', 'unparsed_out'), ('wave2', 'wave2_out'))]
def split():
    ex = build(OLD); random.seed(0); random.shuffle(ex); cut = int(len(ex) * 0.8); return ex[:cut], ex[cut:]
def loadjl(od):
    L = {}
    for f in glob.glob(os.path.join(od, 'chunk_*.jsonl')):
        for l in open(f, encoding='utf-8'):
            if l.strip():
                try: o = json.loads(l); L[o['id']] = o
                except Exception: pass
    return L
def reparse_examples(excl):
    c = sqlite3.connect('file:' + DBP + '?mode=ro', uri=True); out = []; stats = collections.Counter()
    for cd, od, od2 in (('labels/reparse_pilot', 'labels/reparse_pilot_out', 'labels/reparse_pilot_out2'), ('labels/reparse1', 'labels/reparse1_out', None)):
        items = {}
        for f in glob.glob(os.path.join(cd, 'chunk_*.json')):
            for it in json.load(open(f, encoding='utf-8')): items[it['id']] = it
        A = loadjl(od); B = loadjl(od2) if od2 else None
        for h, o in A.items():
            if h in excl or h not in items: continue
            text, tier, trad = c.execute('select text,chain_tier,tradition from hadith where id=?', (h,)).fetchone(); ms0 = items[h]['text'].find(MARK)
            if ms0 < 0: continue
            if B is not None:
                b = B.get(h)
                if not b or [t['text'] for t in o.get('transmitters', [])] != [t['text'] for t in b.get('transmitters', [])] or o.get('ok') != b.get('ok'): stats['pilot: runs differ'] += 1; continue
            if o.get('ok') is True and not o.get('transmitters'):
                spans = [(a, e) for a, e in c.execute('select start,end from chain_mention where hadith_id=? and start is not null and start<?', (h, ms0 + 3))]
            else:
                spans = []; pos = 0; okf = True
                for t in o.get('transmitters', []):
                    r = find(text[:ms0 + 700][pos:], t['text'])
                    if not r: okf = False; break
                    a, e = pos + r[0], pos + r[1]; pos = e; spans.append((a, e))
                if not okf or not spans: stats['transmitter text not found / empty'] += 1; continue
            ms = ms0
            if o.get('matn_ok') is False:
                r = find(text, o.get('matn_start_phrase', ''))
                if not r: stats['matn phrase not found'] += 1; continue
                ms = r[0]
            spans = sorted(s for s in spans if s[0] < ms + 3)
            if not spans: continue
            toks = [(m.start(), m.end()) for m in TOK.finditer(text)][:MAXTOK]; tags = []; prev = None; first = True
            for ts, te in toks:
                if ts >= ms:
                    tags.append(3 if first else -100); first = False; prev = None; continue
                t = 0
                for j, (a, e) in enumerate(spans):
                    if ts < e and te > a: t = 1 if j != prev else 2; prev = j; break
                else: prev = None
                tags.append(t)
            out.append(dict(id=h, tokens=[text[a:b] for a, b in toks], offs=toks, tags=tags, spans=spans, ms=ms, me=len(text), tier=tier, tradition=trad)); stats['ok'] += 1
    print('re-parse examples:', dict(stats), flush=True); return out
close = lambda a, B: any(abs(a - b) <= 3 for b in B)
CONNECT = set('عن ثنا نا حدثنا حدثني اخبرنا اخبرني انا انبانا انبا حدثنى اخبرنى ح و'.split())
def tol_ok(pred, gold, e):
    if all(close(a, pred) for a in gold) and all(close(b, gold) for b in pred): return True, True
    pm = [b for b in pred if not close(b, gold)]; gm = [a for a in gold if not close(a, pred)]
    if len(pm) + len(gm) != 1: return False, False
    x = pm[0] if pm else gm[0]
    if x != max(pred if pm else gold): return False, False
    k = max((i for i, (a, b) in enumerate(e['offs']) if a < x), default=None); prev = plain(e['tokens'][k])[0].strip() if k is not None else ''
    return False, prev not in CONNECT
def evaluate(net, hold, name):
    P = predict(net, hold); st = tl = n = sa = ea = tp = fp = fn = 0; from boundary_metric import CONN
    for e, pr in zip(hold, P):
        gold = [a for a, b in e['spans'] if a < e['ms'] + 3]; sp, ms, me = decode(pr); pred = [e['offs'][a][0] for a, b in sp if e['offs'][a][0] < e['ms'] + 3]
        s, t = tol_ok(pred, gold, e); st += s; tl += (s or t); n += 1
        tp += sum(close(a, pred) for a in gold); fn += sum(not close(a, pred) for a in gold); fp += sum(not close(b, gold) for b in pred)
        tg = e['tags']; gms = next((i for i, x in enumerate(tg) if x == 3), None)
        if gms is not None and ms is not None:
            a, b = sorted((ms, gms)); sa += int(b - a <= 1 or all(plain(x)[0].strip() in CONN for x in e['tokens'][a:b]))
    print(f'{name:5} whole chain exact {st / n:.3f} | tolerant {tl / n:.3f} | transmitters found {tp / max(1, tp + fn):.3f} | listed that are real {tp / max(1, tp + fp):.3f} | matn start (connector-tolerant) {sa / n:.3f}  (n={n})', flush=True)
if __name__ == '__main__':
    tr_old, hold = split(); hold_ids = {e['id'] for e in hold}
    if MODE == 'train':
        extra = reparse_examples(hold_ids) + build([('labels/wave3', 'labels/wave3_out')])
        extra = [e for e in extra if e['id'] not in hold_ids]
        tr = tr_old + extra; prep(tr); print(len(tr_old), 'earlier training hadith +', len(extra), 'new =', len(tr), flush=True)
        net = train(tr, EP); torch.save(net.state_dict(), 'models/joint2_cv.pt'); print('saved models/joint2_cv.pt')
    else:
        prep(hold)
        for name, path in (('OLD', 'models/joint_cv.pt'), ('NEW', 'models/joint2_cv.pt')):
            net = Net(); net.load_state_dict(torch.load(path)); net.eval(); evaluate(net, hold, name)
