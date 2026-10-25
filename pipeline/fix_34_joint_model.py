"""Joint chain/matn tagger: BiGRU over hashed word embeddings (+ a few surface flags), softmax over 5 tags (see fix_33).
Decoding gives, in one pass, narrator spans, matn start and matn end that are consistent with each other.
  python pipeline/fix_34_joint_model.py cv [epochs]     # 80/20 split by hadith id: token accuracy, narrator-span P/R, matn start / end accuracy vs labels (and vs DB boundaries)
  python pipeline/fix_34_joint_model.py fit [epochs]    # train on everything -> models/joint.pt"""
from paths import *
from labels_lib import plain
from fix_33_joint_data import build
import sys, random, re, time, os, zlib, collections
import numpy as np, torch, torch.nn as nn
torch.set_num_threads(int(os.environ.get("TORCH_THREADS", "4"))); torch.manual_seed(0)
MAXTOK2 = 450
H = 1 << 17; PUNCT = re.compile(r'[:،,.؛"«»()\[\]\-–]')
def tok_feats(tokens):
    ids = []; fl = []
    for i, t in enumerate(tokens):
        p = plain(t)[0].strip() or t
        ids.append(zlib.crc32(p.encode()) % H + 1)
        fl.append([float(bool(PUNCT.search(t))), float(t.endswith((':', '،', ','))), float(t.startswith(('"', '«'))), float(i == 0), float(bool(re.search('[ً-ْ]', t))), min(i, 400) / 400.0])
    return ids, fl
class Net(nn.Module):
    def __init__(s, d=96, h=128):
        super().__init__(); s.emb = nn.Embedding(H + 1, d, padding_idx=0); s.fp = nn.Linear(6, 16)
        s.rnn = nn.GRU(d + 16, h, num_layers=2, bidirectional=True, batch_first=True, dropout=0.2); s.out = nn.Linear(2 * h, 5); s.dp = nn.Dropout(0.25)
    def forward(s, ids, fl):
        x = torch.cat([s.dp(s.emb(ids)), torch.relu(s.fp(fl))], -1); y, _ = s.rnn(x); return s.out(s.dp(y))
def batchify(exs):
    L = max(len(e['tokens']) for e in exs); I = torch.zeros(len(exs), L, dtype=torch.long); F = torch.zeros(len(exs), L, 6); Y = torch.full((len(exs), L), -100, dtype=torch.long)
    for k, e in enumerate(exs):
        n = len(e['tokens']); I[k, :n] = torch.tensor(e['ids']); F[k, :n] = torch.tensor(e['fl']); Y[k, :n] = torch.tensor(e['tags'])
    return I, F, Y
def prep(ex):
    for e in ex: e['ids'], e['fl'] = tok_feats(e['tokens'])
def train(tr, epochs):
    net = Net(); opt = torch.optim.Adam(net.parameters(), lr=2e-3); w = torch.tensor([1.0, 3.0, 2.0, 1.0, 1.0]); ck = os.environ.get('CKPT'); start = int(os.environ.get('START_EP', '0'))
    if ck and start > 0 and os.path.exists(ck): net.load_state_dict(torch.load(ck)); print('resumed from', ck, 'at epoch', start, flush=True)
    for ep in range(start, epochs):
        net.train(); random.shuffle(tr); tr.sort(key=lambda e: len(e['tokens']) // 40 + random.random()); t0 = time.time(); tot = 0
        bs = [tr[i:i + 16] for i in range(0, len(tr), 16)]; random.shuffle(bs)
        for b in bs:
            I, F, Y = batchify(b); lo = nn.functional.cross_entropy(net(I, F).reshape(-1, 5), Y.reshape(-1), weight=w, ignore_index=-100)
            opt.zero_grad(); lo.backward(); nn.utils.clip_grad_norm_(net.parameters(), 1.0); opt.step(); tot += lo.item()
        print(f'epoch {ep + 1}/{epochs} loss {tot / len(bs):.4f} {time.time() - t0:.0f}s', flush=True)
        if ck: torch.save(net.state_dict(), ck)
    return net
def predict(net, exs):
    net.eval(); out = []
    with torch.no_grad():
        for i in range(0, len(exs), 32):
            b = exs[i:i + 32]; I, F, _ = batchify(b); P = torch.softmax(net(I, F), -1).numpy()
            for k, e in enumerate(b): out.append(P[k, :len(e['tokens'])])
    return out
def decode(P):
    """-> (narrator token spans [(i,j)], matn token start, matn token end(exclusive)); matn = argmax==3 region, first run after the last narrator span"""
    tg = P.argmax(1); n = len(tg); spans = []; i = 0
    while i < n:
        if tg[i] in (1, 2):
            j = i + 1
            while j < n and tg[j] == 2: j += 1
            spans.append((i, j)); i = j
        else: i += 1
    last = spans[-1][1] if spans else 0
    ms = next((i for i in range(last, n) if tg[i] == 3), None)
    if ms is None: return spans, None, None
    me = ms
    while me < n and tg[me] == 3: me += 1
    # later matn tokens after a short gap (a quotation mark etc.) still belong to the matn
    k = me
    while k < n and k - me < 3 and tg[k] != 4: k += 1
    while k < n and tg[k] == 3: k += 1; me = k
    return spans, ms, me
from boundary_metric import CONN
def tol(e, a, b):
    if a is None or b is None: return False
    a, b = sorted((a, b)); return b - a <= 1 or all(plain(t)[0].strip() in CONN for t in e['tokens'][a:b])
def conf(P, ms, me):
    # confidence = lowest max-probability among the tokens just around the two boundaries
    if ms is None or me is None: return 0.0
    c = [P[i].max() for i in (ms - 1, ms, me - 1, me) if ms is not None and 0 <= i < len(P)]
    return float(min(c)) if c else 0.0
def evaluate(net, te):
    pr = predict(net, te); tot = ok = 0; sa = sb = ea = eb = 0; tp = fp = fn = 0; n = 0; rows = []
    for e, P in zip(te, pr):
        tg = np.array(e['tags']); tot += len(tg); ok += int((P.argmax(1) == tg).sum())
        sp, ms, me = decode(P); n += 1
        gold = {(i) for i, t in enumerate(tg) if t == 1}; pred = {a for a, b in sp}
        tp += len(gold & pred); fp += len(pred - gold); fn += len(gold - pred)
        gms = next((i for i, t in enumerate(tg) if t == 3), None); gme = len(tg) - sum(1 for t in tg if t == 4) if (tg == 4).any() else len(tg)
        if gms is not None:
            sa += int(ms is not None and abs(ms - gms) <= 1); ea += int(me is not None and abs(me - gme) <= 1)
            rows.append((conf(P, ms, me), tol(e, ms, gms), tol(e, me, gme) or len(e['tokens']) >= MAXTOK2))
    import numpy as _np
    for th in (0.0, 0.8, 0.9, 0.95, 0.98):
        sel = [r for r in rows if r[0] >= th]
        if sel: print(f'  conf>={th}: {len(sel)/len(rows):.1%} of hadith | start ok (connector-tolerant) {sum(r[1] for r in sel)/len(sel):.3f} | end ok {sum(r[2] for r in sel)/len(sel):.3f} | both {sum(r[1] and r[2] for r in sel)/len(sel):.3f}')
    print(f'tokens acc {ok / tot:.3f} | narrator-start P {tp / max(1, tp + fp):.3f} R {tp / max(1, tp + fn):.3f} | matn start (+-1 token) {sa / n:.3f} | matn end (+-1 token, may be truncated) {ea / n:.3f}  n={n}')
if __name__ == '__main__':
    MODE = sys.argv[1]; EP = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    pairs = [('labels/' + a, 'labels/' + b) for a, b in (('pilot', 'pilot_out'), ('wave1', 'wave1_out'), ('defects', 'defects_out'), ('unparsed', 'unparsed_out'), ('wave2', 'wave2_out'))]
    ex = build(pairs); prep(ex); random.seed(0); random.shuffle(ex); print(len(ex), 'examples', flush=True)
    if MODE == 'eval':
        cut = int(len(ex) * 0.8); net = Net(); net.load_state_dict(torch.load('models/joint_cv.pt')); evaluate(net, ex[cut:])
    elif MODE == 'cv':
        cut = int(len(ex) * 0.8); net = train(ex[:cut], EP); os.makedirs('models', exist_ok=True); torch.save(net.state_dict(), 'models/joint_cv.pt'); evaluate(net, ex[cut:])
    else:
        net = train(ex, EP); os.makedirs('models', exist_ok=True); torch.save(net.state_dict(), 'models/joint.pt'); print('saved models/joint.pt')
