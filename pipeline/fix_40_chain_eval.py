"""Chain-parsing evaluation on the held-out labelled hadith (the 20% the joint tagger never trained on).
Gold = narrator spans from Claude's labels (accepted parsed mentions + missed names) lying before the labelled matn start.
Compared: DB = current chain_mention spans (chain_no 1); TAG = joint tagger spans; UNION / AGREE of the two.
Hadith-level 'chain exact' = same set of transmitter starts (+-3 chars); also span recall / precision."""
from paths import *
from fix_33_joint_data import build
from fix_34_joint_model import Net, prep, predict, decode
import sqlite3, random, torch, collections, json
pairs = [('labels/' + a, 'labels/' + b) for a, b in (('pilot', 'pilot_out'), ('wave1', 'wave1_out'), ('defects', 'defects_out'), ('unparsed', 'unparsed_out'), ('wave2', 'wave2_out'))]
ex = build(pairs); prep(ex); random.seed(0); random.shuffle(ex); hold = ex[int(len(ex) * 0.8):]
net = Net(); net.load_state_dict(torch.load('models/joint_cv.pt')); net.eval()
c = sqlite3.connect('file:' + OUT + 'hadith_master.db?mode=ro', uri=True)
def close(a, B): return any(abs(a - b) <= 3 for b in B)
CONNECT = set('عن ثنا نا حدثنا حدثني اخبرنا اخبرني انا انبانا انبا اخبرنا حدثنى اخبرنى ح و'.split())
def prev_token(e, a):
    """the (normalised) token just before the span that starts at char a"""
    from labels_lib import plain
    k = max((i for i, (x, y) in enumerate(e['offs']) if x < a), default=None)
    return plain(e['tokens'][k])[0].strip() if k is not None else ''
def tol_ok(pred, gold, e):
    """chain right when the only difference is ONE name at the very end of the chain that is NOT introduced by a chain connector (عن / ثنا / حدثنا ...):
    e.g. 'سألت أبا جعفر' (the Imam in the story) may be counted or not.  A missing or extra name after a connector is a real error."""
    if all(close(a, pred) for a in gold) and all(close(b, gold) for b in pred): return True
    pm = [b for b in pred if not close(b, gold)]; gm = [a for a in gold if not close(a, pred)]
    if len(pm) + len(gm) != 1: return False
    x = pm[0] if pm else gm[0]
    if x != max(pred if pm else gold): return False
    return prev_token(e, x) not in CONNECT
def score(pred, gold):
    return (all(close(a, pred) for a in gold) and all(close(b, gold) for b in pred), sum(close(a, pred) for a in gold), len(gold), sum(close(b, gold) for b in pred), len(pred))
tl = collections.Counter(); agg = collections.Counter(); tot = collections.defaultdict(lambda: [0, 0, 0, 0, 0, 0]); P = predict(net, hold); detail = []
for e, pr in zip(hold, P):
    gold = [a for a, b in e['spans'] if a < e['ms'] + 3]
    sp, ms, me = decode(pr); tag = [e['offs'][a][0] for a, b in sp if e['offs'][a][0] < e['ms'] + 3]
    db = [r[0] for r in c.execute('select start from chain_mention where hadith_id=? and start is not null and coalesce(chain_no,1)=1 and start<?', (e['id'], e['ms'] + 3))]
    uni = sorted(set(db) | {a for a in tag if not close(a, db)}); agree = [a for a in db if close(a, tag)]
    for name, p in (('DB', db), ('TAG', tag), ('UNION', uni), ('AGREE', agree)):
        ok, tp_r, n_g, tp_p, n_p = score(p, gold); t = tot[name]; t[0] += ok; t[1] += tp_r; t[2] += n_g; t[3] += tp_p; t[4] += n_p; t[5] += 1
    for nm_, p_ in (('DB', db), ('TAG', tag), ('AGREE', agree)): tl[nm_] += tol_ok(p_, gold, e)
    same = len(db) == len(tag) and all(close(a, tag) for a in db)
    okdb = score(db, gold)[0]; oktag = score(tag, gold)[0]
    agg['same'] += same; agg['same_and_right'] += same and okdb; agg['diff'] += (not same); agg['diff_db_right'] += (not same) and okdb; agg['diff_tag_right'] += (not same) and oktag
    agg['diff_neither'] += (not same) and not okdb and not oktag; agg['n'] += 1
    detail.append((e['id'], len(gold), len(db), len(tag)))
for name, t in tot.items(): print(f'{name:6} hadith chain exact {t[0] / t[5]:.3f} | span recall {t[1] / t[2]:.3f} | span precision {t[3] / max(1, t[4]):.3f}  (n={t[5]} hadith, {t[2]} gold spans)')

print(dict(agg)); n=agg['n']; print(f"DB and TAG identical span sets: {agg['same']/n:.1%} of hadith, and then right {agg['same_and_right']/max(1,agg['same']):.1%} | they differ: {agg['diff']/n:.1%}: DB right {agg['diff_db_right']/max(1,agg['diff']):.1%}, TAG right {agg['diff_tag_right']/max(1,agg['diff']):.1%}, neither {agg['diff_neither']/max(1,agg['diff']):.1%}")

print({k: round(v / agg['n'], 3) for k, v in tl.items()}, 'chain right with a tolerated one-name difference at the end of the chain')
