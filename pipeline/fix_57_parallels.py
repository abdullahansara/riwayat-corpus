"""Parallel-matn index (zero tokens, read-only).  No clustering: hadith that share >= MINSH sampled 4-word matn shingles are 'parallels' (pairs only).
Shingles are taken from the stored matn onward (so shared chains do not create false pairs); every 4th shingle (by hash) is sampled; buckets > CAP are common phrases and skipped.
  python pipeline/fix_57_parallels.py build      -> labels/parallels.npz (pairs a,b,shared) + labels/par_meta.npz (ids, matn word index)"""
from paths import *
import sqlite3, re, zlib, sys, time, numpy as np
DIAC = re.compile('[ً-ْٰـٓ-ٕ]'); TR = str.maketrans('أإآٱىةؤئ', 'اااايهوي'); NOT = re.compile('[^ء-ي ]')
K, MOD, CAP, MINSH = 4, 4, 25, 2
def words(s): return NOT.sub(' ', DIAC.sub('', s).translate(TR)).split()
if __name__ == '__main__':
    c = sqlite3.connect('file:' + OUT + 'hadith_master.db?mode=ro', uri=True); t0 = time.time()
    H, S, W, ids, mwi = [], [], [], [], []
    for i, (hid, t, ms) in enumerate(c.execute('select id,text,matn_start from hadith where text is not null and matn_start is not null')):
        # word index of matn start: words in text[:ms]
        a = len(words(t[:ms])); w = words(t[ms:]); ids.append(hid); mwi.append(a); k = len(ids) - 1
        for j in range(len(w) - K + 1):
            h = zlib.crc32(' '.join(w[j:j + K]).encode())
            if h % MOD == 0: H.append(h); S.append(k); W.append(j)
        if i % 100000 == 0: print(i, len(H), round(time.time() - t0), 's', flush=True)
    H = np.array(H, dtype=np.uint32); S = np.array(S, dtype=np.int32); W = np.array(W, dtype=np.int16)
    o = np.argsort(H, kind='stable'); H, S, W = H[o], S[o], W[o]
    cut = np.flatnonzero(np.diff(H)) + 1; st = np.concatenate([[0], cut]); en = np.concatenate([cut, [len(H)]])
    keys = []
    for s, e in zip(st, en):
        n = e - s
        if n < 2 or n > CAP: continue
        m = np.unique(S[s:e])
        if len(m) < 2: continue
        for x in range(len(m)):
            keys.append((m[x].astype(np.int64) << 32) | m[x + 1:].astype(np.int64))
        if len(keys) > 2_000_000: keys = [np.concatenate(keys)]
    keys = np.concatenate(keys); u, cnt = np.unique(keys, return_counts=True); sel = cnt >= MINSH
    pa = (u[sel] >> 32).astype(np.int32); pb = (u[sel] & 0xffffffff).astype(np.int32); sh = cnt[sel].astype(np.int16)
    np.savez('labels/parallels.npz', a=pa, b=pb, shared=sh); np.savez('labels/par_meta.npz', ids=np.array(ids), mwi=np.array(mwi, dtype=np.int32))
    has = np.zeros(len(ids), bool); has[pa] = True; has[pb] = True
    print('hadith indexed', len(ids), '| pairs', len(pa), '| hadith with >=1 parallel', int(has.sum()), f'({has.mean():.1%})', round(time.time() - t0), 's')
