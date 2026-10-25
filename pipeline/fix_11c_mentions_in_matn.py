"""Surgery step 11c - chain mentions that lie inside the matn range (second isnads / transmitter commentary glued to the end):
matn_end is moved back to the last sentence boundary ( . ؟ ! or closing quote ) in front of the first such mention, if >= 15 characters of matn remain;
otherwise the hadith is only flagged (matn_has_mentions).  matn_end_source keeps the old value.   python pipeline/fix_11c_mentions_in_matn.py [apply]"""
from paths import *
import sqlite3, sys, re
db = sqlite3.connect(OUT + 'hadith_master.db'); c = db.cursor(); APPLY = len(sys.argv) > 1 and sys.argv[1] == 'apply'
rows = c.execute("""SELECT h.id,h.text,h.matn_start,coalesce(h.matn_end,length(h.text)),min(m.start) FROM hadith h JOIN chain_mention m ON m.hadith_id=h.id
  WHERE h.matn_start IS NOT NULL AND m.start>=h.matn_start AND m.end<=coalesce(h.matn_end,length(h.text)) GROUP BY h.id""").fetchall()
n_cut = n_flag = 0
for hid, text, ms, me, fs in rows:
    seg = text[ms:fs]; cut = None
    for m in re.finditer(r'[.؟!»"”](?=\s|$)', seg): cut = ms + m.end()
    if cut is not None and cut - ms >= 15:
        n_cut += 1
        if APPLY:
            c.execute("INSERT INTO surgery_log VALUES('fix_11c','matn_end',?,?,?)", (hid, str(me), str(cut)))
            c.execute("UPDATE hadith SET matn_end=?, matn_end_source=COALESCE(matn_end_source,?), flags=trim(coalesce(flags,'')||' matn_isnad_cut') WHERE id=?", (cut, me, hid))
    else:
        n_flag += 1
        if APPLY: c.execute("UPDATE hadith SET flags=trim(coalesce(flags,'')||' matn_has_mentions') WHERE id=?", (hid,))
if APPLY: db.commit()
print('hadith', len(rows), 'cut', n_cut, 'flagged only', n_flag)
