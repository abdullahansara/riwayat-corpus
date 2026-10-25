"""Surgery step 09 - purge implausible *observed* name forms.
Observed forms were copied from chain surfaces onto whatever narrator the mention had been assigned to, including wrong assignments,
so a narrator (esp. Ibn Abbas, Abu Hurayra ...) collected unrelated names (سفيان, عطاء, هشيم ...) which then attracted new wrong assignments.
Rule (after pilot review; a looser rule deleted valid nisba/kunya extensions): delete an observed form only when
  (a) it has >= 2 content words, NONE of them occurs (even within one letter of spelling) AND the form is exactly another narrator's own name in the narrator's own name data, or (b) it contains chain text (comma, حدثنا/أخبرنا/ثنا/قال/عن as words).
Original idea: some content word of it does not occur in the narrator's own name data
(standard name + full/variant/kunya/laqab forms, alif-lam stripped).  Words like بن, ابن, ابو, ابي, أم, عبد, الله are ignored.
  python pipeline/fix_09_purge_observed_forms.py pilot [N]   show N random deletions (and N random kept forms) for manual review
  python pipeline/fix_09_purge_observed_forms.py apply       delete; removed forms are logged in table purged_name_form"""
from paths import *
import sqlite3, sys, re, random, collections
MODE = sys.argv[1] if len(sys.argv) > 1 else 'pilot'
db = sqlite3.connect(OUT + 'hadith_master.db'); c = db.cursor()
STOP = {'بن', 'ابن', 'بنت', 'ابو', 'ابي', 'ابا', 'ام', 'عبد', 'الله', 'ابو', 'بني', 'و'}
def toks(n):
    out = set()
    for t in (n or '').split():
        t = t[2:] if t.startswith('ال') and len(t) > 3 else t
        if t.startswith('و') and len(t) > 3: t = t[1:]
        if t.endswith('ا') and len(t) > 3: t = t[:-1]                      # accusative ending (حسينا -> حسين)
        if t not in STOP and len(t) > 1: out.add(t)
    return out
def lev1(a, b):
    if a == b: return True
    if abs(len(a) - len(b)) > 1 or min(len(a), len(b)) < 4: return False
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]: i += 1
    return a[i + 1:] == b[i + 1:] or a[i:] == b[i + 1:] or a[i + 1:] == b[i:]
def fuzzy_overlap(t, own_t):
    return any((x in own_t) or any(lev1(x, y) for y in own_t) for x in t)
KIN = ('ابن', 'ابو', 'ابي', 'ابا', 'ام', 'بنت', 'اخو', 'اخي', 'عم', 'ال')
def first_name(norm_form):
    w = (norm_form or '').split()
    if not w: return None
    t = w[0]
    if t.startswith('و') and len(t) > 3: t = t[1:]
    return t
print('loading name data ...', flush=True)
own = collections.defaultdict(set)
own_forms = collections.defaultdict(set)     # exact normalised non-observed forms per narrator
own_first = collections.defaultdict(set)     # given names (first word) of the narrator's own non-observed forms
other_names = collections.defaultdict(set)      # normalised non-observed name form -> narrators that really own it
for nid, nn in c.execute("SELECT narrator_id, norm FROM narrator_name WHERE type!='observed' AND norm IS NOT NULL AND length(norm)>=7"): other_names[nn].add(nid)
for nid, nn in c.execute("SELECT narrator_id, norm FROM narrator_name WHERE type!='observed' AND norm IS NOT NULL"):
    own[nid] |= toks(nn); own_forms[nid].add(nn); ff = first_name(nn)
    if ff: own_first[nid].add(ff)
for nid, s in c.execute('SELECT id, std_name FROM narrator'):
    nm = re.sub('[ً-ْٰـ]', '', s or '').translate(str.maketrans('أإآٱىةؤئ', 'اااايهوي')); nm = re.sub(r'\s+', ' ', re.sub('[^ء-ي ]', ' ', nm)).strip(); own[nid] |= toks(nm); ff = first_name(nm)
    if ff: own_first[nid].add(ff)
bad = []; keep = []
for rid, nid, form, nn, cnt in c.execute("SELECT rowid, narrator_id, form, norm, observed_count FROM narrator_name WHERE type='observed' AND norm IS NOT NULL"):
    t = toks(nn)
    if not t: continue
    raw = re.sub('[ً-ْٰـ]', '', form or '')
    marker = bool(re.search(r'[،,]|(?:^|\s)(?:حدثنا|حدثني|أخبرنا|أخبرني|أنبأنا|ثنا|ثني|قال|عن|عنه|قالا)(?:\s|$)', raw))
    owners = other_names.get(nn, set()) - {nid}
    zero = len(t) >= 2 and not fuzzy_overlap(t, own[nid]) and bool(owners)   # belongs to someone else
    if not zero and len(t) >= 1 and owners and nn not in own_forms[nid] and not fuzzy_overlap(t, own[nid]): zero = True   # 1-word forms like 'ابن أبي نجيح' that are another narrator's registered name
    ff = first_name(nn)
    wrong_first = bool(ff) and len(t) >= 2 and ff not in KIN and not any(ff.startswith(k) for k in ('ابن', 'ابو', 'ابي', 'ابا')) and own_first[nid] and not any(ff == o or lev1(ff, o) for o in own_first[nid]) and bool(other_names.get(nn, set()) - {nid})
    (bad if (zero or marker) else keep).append((rid, nid, form, cnt, 'zero_overlap' if zero else 'chain_text' if marker else 'first_name'))
print(f'observed forms: {len(bad)+len(keep):,} | implausible (to delete): {len(bad):,} | kept: {len(keep):,}', flush=True)
std = dict(c.execute('SELECT id, std_name FROM narrator'))
if MODE == 'pilot':
    N = int(sys.argv[2]) if len(sys.argv) > 2 else 60; random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 8)
    print('\n--- DELETE candidates (narrator | form | times observed)')
    zero_only = [b for b in bad if b[4] == (sys.argv[4] if len(sys.argv) > 4 else 'zero_overlap')]
    print(f'zero-overlap deletions: {len(zero_only):,} | chain-text deletions: {len(bad)-len(zero_only):,}')
    for rid, nid, form, cnt, why in random.sample(zero_only, N): print(f'   {why[:4]} {std[nid][:30]:32s} | {form[:44]:46s} | {cnt}')
    print('\n--- KEPT (sanity)')
    for rid, nid, form, cnt, why in random.sample(keep, 10): print(f'   {std[nid][:34]:36s} | {form[:40]:42s} | {cnt}')
else:
    c.executescript('CREATE TABLE IF NOT EXISTS purged_name_form(narrator_id TEXT, form TEXT, norm TEXT, observed_count INT);')
    c.executemany('INSERT INTO purged_name_form SELECT narrator_id, form, norm, observed_count FROM narrator_name WHERE rowid=?', [(r[0],) for r in bad])
    c.executemany('DELETE FROM narrator_name WHERE rowid=?', [(r[0],) for r in bad]); db.commit(); print('deleted', len(bad), 'forms')
