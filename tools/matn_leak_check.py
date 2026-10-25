"""Check whether isnad material ends up in the matn (text[matn_start:]), or whether the matn boundary is missing.
Reports, by tier: (1) hadith with no matn_start, (2) chain mentions located after matn_start,
(3) transmission verbs (حدثنا, أخبرنا, ثنا ...) in the first 120 characters of the matn, (4) gap between the last chain mention and matn_start.
Prints examples.  Usage: python tools/matn_leak_check.py [db]"""
import sqlite3, sys, os, re, pathlib, collections, random
ROOT = pathlib.Path(__file__).resolve().parent.parent
db = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('HADITH_DB', str(ROOT / 'data' / 'HadithMaster' / 'hadith_master.db'))
c = sqlite3.connect('file:%s?mode=ro' % pathlib.Path(db).resolve().as_posix(), uri=True)
DIAC = re.compile('[ً-ْٰـٓ-ٕ]')
VERB = re.compile(r'(?:^|\s)(?:حدثنا|حدثني|اخبرنا|اخبرني|انبانا|انبا|ثنا|ثني|اخبرناه|حدثناه)(?:\s|$)')
def plain(s): return DIAC.sub('', s).translate(str.maketrans('أإآٱ', 'اااا'))
q = c.execute("""SELECT h.id, h.chain_tier, h.text, h.matn_start, h.matn_end,
                 (SELECT max(end) FROM chain_mention m WHERE m.hadith_id=h.id AND m.end IS NOT NULL),
                 (SELECT count(*) FROM chain_mention m WHERE m.hadith_id=h.id AND h.matn_start IS NOT NULL AND coalesce(m.chain_no,1)=1 AND m.start>=h.matn_start)
                 FROM hadith h WHERE h.chain_tier!='none'""")
S = collections.defaultdict(collections.Counter); ex = collections.defaultdict(list); random.seed(1)
for hid, tier, text, ms, me, last_end, n_after in q:
    s = S[tier]; s['hadith'] += 1
    if ms is None: s['no_matn_start'] += 1; continue
    if n_after: s['mentions_after_matn_start'] += 1; ex['mentions_after'].append(hid)
    seg = plain(text[ms:ms + 120])
    if VERB.search(seg): s['verbs_in_first_120_of_matn'] += 1; ex['verbs_in_matn'].append(hid)
    if last_end is not None:
        gap = ms - last_end
        if gap > 150: s['gap_gt_150'] += 1; ex['big_gap'].append(hid)
        if gap < 0: s['matn_starts_inside_chain'] += 1; ex['inside'].append(hid)
for tier, s in sorted(S.items()):
    n = s['hadith']; print(f"tier {tier}: {n:,} hadith | no matn_start {s['no_matn_start']:,} ({s['no_matn_start']/n:.1%})")
    d = n - s['no_matn_start']
    for k in ('mentions_after_matn_start', 'verbs_in_first_120_of_matn', 'gap_gt_150', 'matn_starts_inside_chain'):
        print(f"      {k:30s} {s[k]:8,}  ({s[k]/max(d,1):.1%} of hadith that have a matn_start)")
for k, v in ex.items():
    print('\nexamples', k, ':')
    for hid in random.sample(v, min(3, len(v))):
        t, ms = c.execute('select text, matn_start from hadith where id=?', (hid,)).fetchone()
        print('  ', hid, '| ...', plain(t[max(0, ms - 50):ms]).replace('\n', ' '), '[MATN→]', plain(t[ms:ms + 110]).replace('\n', ' '))
