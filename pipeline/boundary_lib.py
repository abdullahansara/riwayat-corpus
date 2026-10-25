"""Candidate generation and features for the matn start/end models (used by fix_21 for training and fix_22 for scoring).
A boundary index j means "between word j-1 and word j".  start offset = T[j][0]; end offset = T[j-1][1]."""
import re, bisect
from labels_lib import plain
W = 450                                                    # window half-width in characters around the DB boundary
CONN = set('حدثنا حدثني اخبرنا اخبرني ثنا نا انا عن قال وقال قالت يقول سمعت ان انه ان ثم ف و ح'.split())
def tok(text):
    return [(m.start(), m.end(), plain(m.group())[0]) for m in re.finditer(r'\S+', text)]
def off(T, j, target): return T[j][0] if target == 'start' else T[j - 1][1]
def candidates(text, anchor, mentions, target, lower=0):
    """boundary indexes j whose offset is within [anchor-W, anchor+W]; start: not before the end of the first mention; end: not before `lower`"""
    lo = max(0, anchor - W); hi = min(len(text), anchor + W)
    first_end = mentions[0][1] if (mentions and target == 'start') else lower
    T = tok(text); out = []
    for j in range(1 if target == 'end' else 0, len(T) + (1 if target == 'end' else 0)):
        if j >= len(T) and target == 'start': continue
        o = off(T, j, target)
        if o < lo or o > hi or o < first_end: continue
        if target == 'start' and not T[j][2]: continue
        out.append(j)
    return T, out
def feats(text, T, k, anchor, mentions, target, ST=None):
    f = {}
    ST = ST if ST is not None else [t[0] for t in T]
    w = lambda j: T[j][2] if 0 <= j < len(T) else '<s>' if j < 0 else '</s>'
    for d in (1, 2, 3, 4): f[f'p{d}={w(k - d)}'] = 1
    for d in (0, 1, 2, 3): f[f'n{d}={w(k + d)}'] = 1
    f[f'p2p1={w(k - 2)}_{w(k - 1)}'] = 1; f[f'p1n0={w(k - 1)}_{w(k)}'] = 1; f[f'p1n0n1={w(k - 1)}_{w(k)}_{w(k + 1)}'] = 1
    s = off(T, k, target); before = text[max(0, s - 6):s]; after_ = text[s:s + 6]
    for ch in ('.', ':', '،', '"', 'ﷺ'):
        if ch in after_: f['a' + ch] = 1
    f['at_text_end'] = int(s >= len(text) - 1)
    for ch in (':', '،', ',', '"', '.', '؟', '«', '(', 'ﷺ'):
        if ch in before: f['b' + ch] = 1
    if k and T[k - 1][2].startswith(('ال',)): f['p1_al'] = 1
    jd = next((j for j in range(0 if target == 'start' else 1, len(T) + (0 if target == 'start' else 1)) if off(T, j, target) >= anchor), len(T))
    f[f'delta={max(-12, min(12, k - jd))}'] = 1
    ends = [e for st, e in mentions if e <= s]
    starts = ST
    if ends:
        le = max(ends); i0 = bisect.bisect_left(starts, le); i1 = bisect.bisect_left(starts, s)
        n = i1 - i0
        f[f'gapn={min(n, 12)}'] = 1
        f['gap_all_conn'] = int(all(T[i][2] in CONN or not T[i][2] for i in range(i0, i1)))
        f['gap_last=' + (T[i1 - 1][2] if n > 0 else '<m>')] = 1
    else: f['no_mention_before'] = 1
    f['inside_mention'] = int(any(st < s < e for st, e in mentions))
    nxt = [st for st, e in mentions if st >= s]
    f[f'dist_next_mention={min((bisect.bisect_left(starts, nxt[0]) - bisect.bisect_left(starts, s)) if nxt else 99, 15)}'] = 1
    return f
def build(text, anchor, label, mentions, target, lower=0):
    """-> (feature dicts, 0/1 targets, boundary offsets) or None.  label may be None (inference)"""
    T, cand = candidates(text, anchor, mentions, target, lower)
    if not cand: return None
    ST = [t[0] for t in T]
    X = [feats(text, T, k, anchor, mentions, target, ST) for k in cand]
    offs = [off(T, k, target) for k in cand]
    y = [int(abs(o - label) <= 2) for o in offs] if label is not None else [0] * len(cand)
    return X, y, offs
